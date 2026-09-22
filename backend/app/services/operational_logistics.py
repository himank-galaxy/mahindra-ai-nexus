"""Logistics AI Control Tower: real database-backed route/shipment intelligence.

Two governance tracks over the same real ``shipments``, exactly mirroring
the Trust Ledger's canonical-vs-live split already proven for Collections
AI Swarm (see app/services/collections.py):

- **Canonical**: a subset of shipments already carry an immutable
  ``trust_decisions`` row (``target_entity_type='SHIPMENT'``,
  ``domain='LOGISTICS'``) from the Synthetic Data Factory's own
  governance history — real, historical, never re-decided from this
  screen.
- **Live**: every other shipment has no decision yet. Approve/Modify/
  Send-to-review here create/update exactly one
  ``RouteShipmentDecision`` row per shipment (app/models/logistics_route.py)
  — never a second decision for a shipment that already has one.

Delay/SLA-breach probability and the reroute recommendation are never
invented: they reuse the exact same trained models Logistics Delay
Simulation trains (app/ai/simulation/models/logistics_delay_model.py) and
the same real-alternative-route sweep (app/ai/simulation/logistics_delay.py)
— applied to each real shipment's own recorded features instead of a
scenario slider. Compliance reuses the same five-rule engine the Trust
Ledger applies to Simulation Center runs (app/services/compliance_engine.py).

Route cards remain a real aggregate over real shipments (unchanged shape
from before this work) — only the numbers behind "SLA Risk"/"Delay prob."
change, from a backward-looking historical rate to a forward-looking
real model prediction, averaged across that route's own real shipments.
Per-shipment governance/compliance detail lives one level down, in the
shipment drill-down and its Trust Ledger view — the route card itself
stays exactly as dense as it is today.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select

from app.ai.simulation.confidence import trained_model_confidence
from app.ai.simulation.logistics_delay import (
    MODEL_NAME,
    MODEL_VERSION,
    best_route_for_shipment,
    breach_drivers,
    expected_risk_cost_inr,
)
from app.ai.simulation.models.logistics_delay_model import LogisticsDelayModels, get_or_train_models
from app.core.errors import ConflictError, DomainValidationError, NotFoundError
from app.database.runtime_schema import runtime_tables
from app.models.logistics_route import RouteShipmentDecision
from app.repositories.logistics_delay_simulation import (
    LogisticsDelaySimulationRepository,
)
from app.repositories.logistics_route_decision import LogisticsRouteDecisionRepository
from app.schemas.logistics import (
    AutoHealOut,
    RouteOut,
    ShipmentOut,
    ShipmentTrustLedgerOut,
    SignalOut,
    SlaReportOut,
)
from app.schemas.trust import ComplianceCheckOut, OutcomeOut
from app.services.base import BaseService
from app.services.compliance_engine import ComplianceResult, derive_audit_status, evaluate_simulation_compliance
from app.services.logistics_priority import score_route_priority
from app.services.risk_engine import score_simulation_risk
from app.services.trust import TrustService

ROUTES = runtime_tables["routes"]
SHIPMENTS = runtime_tables["shipments"]
WAREHOUSES = runtime_tables["warehouses"]
WAREHOUSE_EVENTS = runtime_tables["warehouse_events"]
TRUST_DECISIONS = runtime_tables["trust_decisions"]
COMPLIANCE_CHECKS = runtime_tables["compliance_checks"]
ROUTE_NAMESPACE = uuid.UUID("29f51f15-83bb-4c73-ab36-a3353c089f56")

# A shipment is "at risk" (for the route card's at-risk count, and the
# canonical/human-review priority factors) when the real trained model's
# predicted SLA-breach probability crosses this threshold — the same
# spirit as risk_engine.py's own documented, reviewable percentage bands.
AT_RISK_BREACH_PROBABILITY = 25


def _route_uuid(route_id: str) -> uuid.UUID:
    return uuid.uuid5(ROUTE_NAMESPACE, route_id)


def _route_label(route: dict[str, object]) -> str:
    return f"{route['origin_city_name']} → {route['destination_city_name']}"


def _inr(amount: float) -> str:
    if amount >= 10_000_000:
        return f"₹{amount / 10_000_000:.1f} Cr"
    if amount >= 100_000:
        return f"₹{amount / 100_000:.1f}L"
    return f"₹{amount:,.0f}"


@dataclass(frozen=True)
class _ResultOnly:
    """Satisfies compliance_engine's ``_HasResult`` protocol for raw
    canonical ``compliance_checks`` mapping rows."""

    result: str


@dataclass(frozen=True)
class _ShipmentRecommendationSnapshot:
    """Satisfies compliance_engine's ``_HasComplianceFields`` protocol —
    a real shipment has no ``SimulationRun`` row, so this carries the
    same field names populated from the shipment's own real data instead."""

    model_name: str
    model_version: str
    inputs: dict[str, Any]
    outputs: dict[str, Any]
    baseline_reference: dict[str, Any] | None
    driver_json: dict[str, Any] | None
    confidence: int


def _shipment_predictive_features(shipment: dict[str, object]) -> dict[str, float]:
    return {
        "distance_km": float(shipment["distance_km"] or 0.0),
        "warehouse_utilization_pct": float(shipment["warehouse_utilization_pct"]),
        "dock_wait_minutes": float(shipment["dock_wait_minutes"]),
        "weather_disruption": 1.0 if shipment["weather_disruption"] else 0.0,
        "vehicle_breakdown": 1.0 if shipment["vehicle_breakdown"] else 0.0,
    }


def _build_shipment_output(
    shipment: dict[str, object],
    route: dict[str, object],
    alternatives: list[dict[str, object]],
    models: LogisticsDelayModels,
    canonical: dict[str, object] | None,
    canonical_checks: list[dict[str, object]],
    live_decision: RouteShipmentDecision | None,
) -> dict[str, object]:
    """The one place shipment-level intelligence is computed — shared by
    the route-card aggregate (batched across all shipments) and every
    shipment-scoped action (single shipment), so list and detail can
    never disagree."""
    shipment_id = str(shipment["shipment_id"])
    priority = str(shipment["priority"])
    features = _shipment_predictive_features(shipment)
    categorical = {"route_id": route["route_id"], "priority": priority}

    delay_prob = models.any_delay.predict_proba(features, categorical)
    breach_prob = models.breach.predict_proba(features, categorical)

    best_route, best_delay, best_breach, best_cost = best_route_for_shipment(
        models, features, priority, route, alternatives
    )
    best_action = "MAINTAIN" if best_route["route_id"] == route["route_id"] else "REROUTE"

    # "Effective" = what should happen: the optimizer's own recommendation
    # unless a human has explicitly overridden it (mirrors Collections'
    # effective_channel = modified_channel or best_channel). This drives
    # the recommended_action/recommended_route display and the compliance
    # evaluation of that proposed action — it is NOT the shipment's real
    # current risk (see risk_* below), so it must never feed
    # delay_probability/breach_probability/expected_risk_cost_inr
    # directly — those describe today's actual situation, not a
    # not-yet-executed suggestion (docs/logistics_tower.md §3.1: "must
    # never be collapsed").
    modified_action = live_decision.modified_action if live_decision is not None else None
    modified_route_id = live_decision.modified_route_id if live_decision is not None else None
    if modified_action is not None:
        effective_action = modified_action
        effective_route_id = modified_route_id if modified_action == "REROUTE" else route["route_id"]
        if effective_route_id == best_route["route_id"]:
            effective_delay, effective_breach, effective_cost = best_delay, best_breach, best_cost
        else:
            effective_route = next(
                (r for r in [route, *alternatives] if r["route_id"] == effective_route_id), route
            )
            effective_features = {**features, "distance_km": float(effective_route["distance_km"])}
            effective_delay = models.any_delay.predict_proba(effective_features, categorical)
            effective_breach = models.breach.predict_proba(effective_features, categorical)
            effective_cost = float(effective_route["baseline_cost_inr"]) + expected_risk_cost_inr(
                models, effective_route["route_id"], effective_delay, effective_breach
            )
    else:
        effective_action = best_action
        effective_route_id = best_route["route_id"]
        effective_delay, effective_breach, effective_cost = best_delay, best_breach, best_cost

    # Risk numbers: the shipment's REAL current situation. It keeps
    # riding its own currently assigned route — and its predicted risk
    # must reflect that — until a decision has actually been APPROVED
    # (a merely-recommended-but-not-yet-approved reroute hasn't happened
    # yet). Once approved, the approved action (effective_*, computed
    # above) is genuinely what the shipment will do, so the risk numbers
    # switch to match it.
    is_approved = live_decision is not None and live_decision.status == "APPROVED"
    if is_approved:
        risk_delay, risk_breach, risk_cost = effective_delay, effective_breach, effective_cost
    else:
        risk_delay, risk_breach = delay_prob, breach_prob
        risk_cost = float(route["baseline_cost_inr"]) + expected_risk_cost_inr(
            models, route["route_id"], delay_prob, breach_prob
        )

    confidence, _band = trained_model_confidence(
        predicted_probability=effective_breach,
        in_training_range=True,
        cohort_sample_size=1,
    )
    risk = score_simulation_risk("logistics-delay", confidence, {"cost": effective_cost})

    compliance_checks: list[ComplianceCheckOut]
    if canonical is not None:
        audit_status = derive_audit_status([_ResultOnly(str(c["result"])) for c in canonical_checks])
        approval_status = str(canonical["decision"]).replace("_", " ").title()
        governance_track = "canonical"
        decision_code: str | None = str(canonical["decision_id"])
        compliance_checks = [
            ComplianceCheckOut(
                rule_code=str(c["rule_code"]),
                rule_name=str(c["rule_name"]),
                result=str(c["result"]),  # type: ignore[arg-type]
                reason=str(c["reason"]),
            )
            for c in canonical_checks
        ]
    else:
        snapshot = _ShipmentRecommendationSnapshot(
            model_name=MODEL_NAME,
            model_version=MODEL_VERSION,
            inputs={
                "route_id": route["route_id"],
                "priority": priority,
                "weather_disruption": features["weather_disruption"],
                "vehicle_breakdown": features["vehicle_breakdown"],
                "action": effective_action,
                "target_route_id": effective_route_id,
            },
            outputs={"recommendedAction": effective_action, "cost": effective_cost},
            baseline_reference={"shipment_id": shipment_id, "route_id": route["route_id"]},
            driver_json={
                "predictive_drivers": breach_drivers(
                    models, str(effective_route_id), _route_label(route if effective_route_id == route["route_id"] else best_route), priority
                )
            },
            confidence=confidence,
        )
        results: list[ComplianceResult] = evaluate_simulation_compliance(snapshot, risk)
        audit_status = derive_audit_status(results)
        approval_status = live_decision.status.title() if live_decision is not None else "Pending"
        governance_track = "live"
        decision_code = shipment_id if live_decision is not None else None
        compliance_checks = [
            ComplianceCheckOut(rule_code=r.rule_code, rule_name=r.rule_name, result=r.result, reason=r.reason)  # type: ignore[arg-type]
            for r in results
        ]

    return {
        "shipment_id": shipment_id,
        "route_id": str(route["route_id"]),
        "priority": priority,
        "dispatch_time": shipment["dispatch_time"],
        "expected_arrival": shipment["expected_arrival"],
        "actual_arrival": shipment["actual_arrival"],
        "sla_deadline": shipment["sla_deadline"],
        "delay_minutes": float(shipment["delay_minutes"] or 0.0),
        "sla_breach": bool(shipment["sla_breach"]),
        "vehicle_id": str(shipment["vehicle_id"]),
        "shipment_status": str(shipment["shipment_status"]),
        "delay_probability": round(risk_delay * 100),
        "breach_probability": round(risk_breach * 100),
        "expected_risk_cost_inr": risk_cost,
        "best_action": best_action,
        "best_route_id": str(best_route["route_id"]),
        "effective_action": effective_action,
        "effective_route_id": str(effective_route_id),
        "audit_status": audit_status,
        "approval_status": approval_status,
        "governance_track": governance_track,
        "decision_code": decision_code,
        "compliance_checks": compliance_checks,
        "modified_action": modified_action,
        "modified_route_id": modified_route_id,
        "modification_reason": live_decision.modification_reason if live_decision is not None else None,
    }


def _aggregate_route(route: dict[str, object], shipment_outputs: list[dict[str, object]]) -> dict[str, object]:
    """Real route-card aggregate over its own real shipments' per-
    shipment model predictions — never a hardcoded 2-way text branch."""
    shipments = len(shipment_outputs)
    at_risk = [s for s in shipment_outputs if int(s["breach_probability"]) >= AT_RISK_BREACH_PROBABILITY]  # type: ignore[arg-type]

    if shipments:
        avg_delay = round(sum(int(s["delay_probability"]) for s in shipment_outputs) / shipments)  # type: ignore[arg-type]
        avg_breach = round(sum(int(s["breach_probability"]) for s in shipment_outputs) / shipments)  # type: ignore[arg-type]
    else:
        avg_delay = avg_breach = 0

    total_risk_cost = sum(float(s["expected_risk_cost_inr"]) for s in at_risk)  # type: ignore[arg-type]

    reroute_targets = [str(s["effective_route_id"]) for s in at_risk if s["effective_action"] == "REROUTE"]
    if reroute_targets:
        # Majority vote among at-risk shipments recommending a reroute —
        # each shipment sweeps the same real alternative-route set but
        # may land on a different optimum due to its own real weather/
        # vehicle/congestion features, so the route card shows whichever
        # alternative most of its at-risk shipments actually prefer.
        target_route_id = max(set(reroute_targets), key=reroute_targets.count)
        action = f"Reroute at-risk shipments via route {target_route_id}"
    else:
        target_route_id = None
        action = "Maintain route with ETA monitoring"

    decided = [s for s in shipment_outputs if s["governance_track"] == "live" and s["decision_code"] is not None]
    if any(s["approval_status"] == "Approved" for s in decided):
        status = "Approved"
        rerouted = any(
            s["approval_status"] == "Approved" and s["effective_action"] == "REROUTE" for s in decided
        )
    elif any(s["approval_status"] == "Escalated" for s in decided):
        status = "Escalated"
        rerouted = False
    else:
        status = "Pending"
        rerouted = False

    priority = score_route_priority(
        total_expected_risk_cost_inr=total_risk_cost,
        breach_probability=avg_breach,
        affected_shipments=len(at_risk),
    )

    return {
        "route_id": str(route["route_id"]),
        "name": _route_label(route),
        "sla_risk": avg_breach,
        "delay_prob": avg_delay,
        "cost": _inr(float(route["avg_shipment_cost_inr"] or route["baseline_cost_inr"] or 0.0)),
        "action": action,
        "rerouted": rerouted,
        "active_shipments": shipments,
        "at_risk_shipments": len(at_risk),
        "status": status,
        "priority": priority.level,
        "priority_points": priority.points,
        "priority_reason": priority.reason,
        "reroute_target_route_id": target_route_id,
        "scored_at": datetime.now(UTC),
        "model_version": f"{MODEL_NAME} ({MODEL_VERSION})",
    }


def _to_route_out(route: dict[str, object]) -> RouteOut:
    return RouteOut(
        id=_route_uuid(str(route["route_id"])),
        route_id=str(route["route_id"]),
        name=str(route["name"]),
        slaRisk=int(route["sla_risk"]),  # type: ignore[arg-type]
        delayProb=int(route["delay_prob"]),  # type: ignore[arg-type]
        cost=str(route["cost"]),
        action=str(route["action"]),
        rerouted=bool(route["rerouted"]),
        active_shipments=int(route["active_shipments"]),  # type: ignore[arg-type]
        at_risk_shipments=int(route["at_risk_shipments"]),  # type: ignore[arg-type]
        status=str(route["status"]),
        priority=route["priority"],  # type: ignore[arg-type]
        priority_reason=str(route["priority_reason"]),
        scored_at=route["scored_at"],  # type: ignore[arg-type]
        model_version=str(route["model_version"]),
    )


def _to_shipment_out(shipment: dict[str, object], route_labels: dict[str, str]) -> ShipmentOut:
    effective_route_id = str(shipment["effective_route_id"])
    recommended_label = route_labels.get(effective_route_id) if shipment["effective_action"] == "REROUTE" else None
    return ShipmentOut(
        shipment_id=str(shipment["shipment_id"]),
        status=str(shipment["shipment_status"]),
        priority=str(shipment["priority"]),
        dispatch_time=shipment["dispatch_time"],  # type: ignore[arg-type]
        expected_arrival=shipment["expected_arrival"],  # type: ignore[arg-type]
        actual_arrival=shipment["actual_arrival"],  # type: ignore[arg-type]
        sla_deadline=shipment["sla_deadline"],  # type: ignore[arg-type]
        delay_minutes=float(shipment["delay_minutes"]),  # type: ignore[arg-type]
        sla_breach=bool(shipment["sla_breach"]),
        vehicle_id=str(shipment["vehicle_id"]),
        current_warehouse=route_labels.get(f"origin:{shipment['route_id']}"),
        delay_probability=int(shipment["delay_probability"]),  # type: ignore[arg-type]
        breach_probability=int(shipment["breach_probability"]),  # type: ignore[arg-type]
        recommended_action=str(shipment["effective_action"]).title(),
        recommended_route_label=recommended_label,
        governance_track=shipment["governance_track"],  # type: ignore[arg-type]
        decision_status=str(shipment["approval_status"]),
        decision_code=shipment["decision_code"],  # type: ignore[arg-type]
    )


class OperationalLogisticsService(BaseService):
    async def _load_models(self) -> LogisticsDelayModels:
        return await get_or_train_models(LogisticsDelaySimulationRepository(self._session))

    async def _fetch_shipment_rows(
        self,
        models: LogisticsDelayModels,
        route_ids: list[str] | None = None,
    ) -> list[dict[str, object]]:
        statement = select(
            SHIPMENTS.c.shipment_id,
            SHIPMENTS.c.route_id,
            SHIPMENTS.c.priority,
            SHIPMENTS.c.distance_km,
            SHIPMENTS.c.weather_disruption,
            SHIPMENTS.c.vehicle_breakdown,
            SHIPMENTS.c.dispatch_time,
            SHIPMENTS.c.expected_arrival,
            SHIPMENTS.c.actual_arrival,
            SHIPMENTS.c.sla_deadline,
            SHIPMENTS.c.delay_minutes,
            SHIPMENTS.c.sla_breach,
            SHIPMENTS.c.vehicle_id,
            SHIPMENTS.c.shipment_status,
            SHIPMENTS.c.baseline_cost_inr,
        )
        if route_ids is not None:
            statement = statement.where(SHIPMENTS.c.route_id.in_(route_ids))
        rows = [dict(r) for r in (await self._session.execute(statement)).mappings().all()]
        if not rows:
            return []
        shipment_ids = [str(r["shipment_id"]) for r in rows]

        congestion_rows = (
            (
                await self._session.execute(
                    select(
                        WAREHOUSE_EVENTS.c.shipment_id,
                        func.avg(WAREHOUSE_EVENTS.c.warehouse_utilization_pct).label("warehouse_utilization_pct"),
                        func.avg(WAREHOUSE_EVENTS.c.dock_wait_minutes).label("dock_wait_minutes"),
                    )
                    .where(WAREHOUSE_EVENTS.c.shipment_id.in_(shipment_ids))
                    .group_by(WAREHOUSE_EVENTS.c.shipment_id)
                )
            )
            .mappings()
            .all()
        )
        congestion_by_shipment = {str(r["shipment_id"]): r for r in congestion_rows}

        # Same imputation the model was TRAINED with (see
        # LogisticsDelaySimulationRepository.load_shipment_frame) — the
        # global training-set mean, never a locally recomputed one, so a
        # single-route query imputes identically to how the model itself
        # was fit.
        fallback_utilization = float(models.frame["warehouse_utilization_pct"].mean())
        fallback_dock_wait = float(models.frame["dock_wait_minutes"].mean())

        for row in rows:
            congestion = congestion_by_shipment.get(str(row["shipment_id"]))
            utilization = congestion["warehouse_utilization_pct"] if congestion else None
            dock_wait = congestion["dock_wait_minutes"] if congestion else None
            row["warehouse_utilization_pct"] = float(utilization) if utilization is not None else fallback_utilization
            row["dock_wait_minutes"] = float(dock_wait) if dock_wait is not None else fallback_dock_wait
        return rows

    async def _fetch_routes(self, route_ids: list[str] | None = None) -> dict[str, dict[str, object]]:
        statement = select(
            ROUTES.c.route_id,
            ROUTES.c.origin_city_name,
            ROUTES.c.destination_city_name,
            ROUTES.c.origin_warehouse_name,
            ROUTES.c.origin_region_id,
            ROUTES.c.destination_region_id,
            ROUTES.c.distance_km,
            ROUTES.c.typical_transit_hours,
            ROUTES.c.sla_hours,
            ROUTES.c.baseline_cost_inr,
        ).where(ROUTES.c.active.is_(True))
        if route_ids is not None:
            statement = statement.where(ROUTES.c.route_id.in_(route_ids))
        rows = (await self._session.execute(statement)).mappings().all()
        return {str(r["route_id"]): dict(r) for r in rows}

    async def _fetch_alternatives(self, route: dict[str, object], all_routes: dict[str, dict]) -> list[dict]:
        return [
            candidate
            for candidate in all_routes.values()
            if candidate["route_id"] != route["route_id"]
            and candidate["origin_region_id"] == route["origin_region_id"]
            and candidate["destination_region_id"] == route["destination_region_id"]
        ]

    async def _canonical_lookup(
        self, shipment_ids: list[str]
    ) -> tuple[dict[str, dict], dict[str, list[dict]]]:
        canonical_rows = (
            (
                await self._session.execute(
                    select(TRUST_DECISIONS).where(
                        TRUST_DECISIONS.c.target_entity_type == "SHIPMENT",
                        TRUST_DECISIONS.c.target_entity_id.in_(shipment_ids),
                    )
                )
            )
            .mappings()
            .all()
        )
        canonical_by_shipment = {str(row["target_entity_id"]): dict(row) for row in canonical_rows}
        decision_ids = [row["decision_id"] for row in canonical_by_shipment.values()]
        checks_by_decision: dict[str, list[dict]] = defaultdict(list)
        if decision_ids:
            check_rows = (
                (
                    await self._session.execute(
                        select(COMPLIANCE_CHECKS).where(COMPLIANCE_CHECKS.c.decision_id.in_(decision_ids))
                    )
                )
                .mappings()
                .all()
            )
            for row in check_rows:
                checks_by_decision[str(row["decision_id"])].append(dict(row))
        return canonical_by_shipment, checks_by_decision

    async def _all_route_outputs(self) -> tuple[list[dict[str, object]], dict[str, dict[str, object]]]:
        models = await self._load_models()
        all_routes = await self._fetch_routes()
        shipment_rows = await self._fetch_shipment_rows(models)
        shipments_by_route: dict[str, list[dict]] = defaultdict(list)
        for row in shipment_rows:
            shipments_by_route[str(row["route_id"])].append(row)

        shipment_ids = [str(r["shipment_id"]) for r in shipment_rows]
        canonical_by_shipment, checks_by_decision = await self._canonical_lookup(shipment_ids)
        live_decisions = await LogisticsRouteDecisionRepository(self._session).get_decisions(shipment_ids)

        # Real average shipment freight cost per route — the metric
        # already shown before this work; kept exactly as-is.
        cost_totals: dict[str, list[float]] = defaultdict(list)
        for row in shipment_rows:
            cost_totals[str(row["route_id"])].append(float(row["baseline_cost_inr"] or 0.0))

        route_outputs: list[dict[str, object]] = []
        shipment_outputs_by_route: dict[str, list[dict[str, object]]] = {}
        for route_id, route in all_routes.items():
            shipments = shipments_by_route.get(route_id, [])
            alternatives = await self._fetch_alternatives(route, all_routes)
            outputs = []
            for shipment in shipments:
                shipment_id = str(shipment["shipment_id"])
                canonical = canonical_by_shipment.get(shipment_id)
                checks = checks_by_decision.get(str(canonical["decision_id"]), []) if canonical else []
                outputs.append(
                    _build_shipment_output(
                        shipment,
                        route,
                        alternatives,
                        models,
                        canonical,
                        checks,
                        live_decisions.get(shipment_id),
                    )
                )
            shipment_outputs_by_route[route_id] = outputs
            route_with_cost = {
                **route,
                "avg_shipment_cost_inr": (
                    sum(cost_totals[route_id]) / len(cost_totals[route_id]) if cost_totals.get(route_id) else None
                ),
            }
            route_outputs.append(_aggregate_route(route_with_cost, outputs))

        route_outputs.sort(key=lambda r: (r["priority_points"], r["at_risk_shipments"]), reverse=True)
        return route_outputs, shipment_outputs_by_route

    async def list_routes(self) -> list[RouteOut]:
        route_outputs, _ = await self._all_route_outputs()
        return [_to_route_out(r) for r in route_outputs]

    async def list_warehouse_signals(self) -> list[SignalOut]:
        statement = (
            select(
                WAREHOUSES.c.warehouse_id,
                WAREHOUSES.c.warehouse_name,
                WAREHOUSES.c.baseline_utilization_pct,
                func.count(WAREHOUSE_EVENTS.c.warehouse_event_id).label("event_count"),
                func.count(WAREHOUSE_EVENTS.c.warehouse_event_id)
                .filter(WAREHOUSE_EVENTS.c.congestion_flag.is_(True))
                .label("congestion_events"),
                func.coalesce(
                    func.avg(WAREHOUSE_EVENTS.c.warehouse_utilization_pct),
                    WAREHOUSES.c.baseline_utilization_pct,
                ).label("avg_utilization"),
                func.coalesce(
                    func.avg(WAREHOUSE_EVENTS.c.dock_wait_minutes),
                    0,
                ).label("avg_dock_wait"),
            )
            .select_from(
                WAREHOUSES.outerjoin(
                    WAREHOUSE_EVENTS,
                    WAREHOUSE_EVENTS.c.warehouse_id == WAREHOUSES.c.warehouse_id,
                )
            )
            .where(WAREHOUSES.c.active.is_(True))
            .group_by(
                WAREHOUSES.c.warehouse_id,
                WAREHOUSES.c.warehouse_name,
                WAREHOUSES.c.baseline_utilization_pct,
            )
            .order_by(WAREHOUSES.c.warehouse_name)
        )
        warehouse_rows = (await self._session.execute(statement)).mappings().all()

        # Real routes touching each warehouse (as origin or destination) —
        # a genuine join, never invented, for the explainability field.
        route_rows = (
            (
                await self._session.execute(
                    select(
                        ROUTES.c.origin_warehouse_id,
                        ROUTES.c.destination_warehouse_id,
                        ROUTES.c.origin_city_name,
                        ROUTES.c.destination_city_name,
                    ).where(ROUTES.c.active.is_(True))
                )
            )
            .mappings()
            .all()
        )
        routes_by_warehouse: dict[str, list[str]] = defaultdict(list)
        for row in route_rows:
            label = f"{row['origin_city_name']} → {row['destination_city_name']}"
            routes_by_warehouse[str(row["origin_warehouse_id"])].append(label)
            routes_by_warehouse[str(row["destination_warehouse_id"])].append(label)

        result: list[SignalOut] = []
        for row in warehouse_rows:
            events = int(row["event_count"] or 0)
            congestion = int(row["congestion_events"] or 0)
            utilization = float(row["avg_utilization"] or 0)
            dock_wait = float(row["avg_dock_wait"] or 0)
            congestion_rate = congestion / events if events else 0.0
            affected = routes_by_warehouse.get(str(row["warehouse_id"]), [])
            result.extend(
                [
                    SignalOut(
                        label=f"{row['warehouse_name']} utilization",
                        value=f"{utilization * 100:.1f}%",
                        tone="warning" if utilization >= 0.85 else "success",
                        threshold="Warning at ≥85% average utilization",
                        affected_routes=affected,
                    ),
                    SignalOut(
                        label=f"{row['warehouse_name']} congestion",
                        value=f"{congestion_rate * 100:.1f}%",
                        tone="danger" if congestion_rate >= 0.20 else "success",
                        threshold="Critical at ≥20% of events flagged congested",
                        affected_routes=affected,
                    ),
                    SignalOut(
                        label=f"{row['warehouse_name']} dock wait",
                        value=f"{dock_wait:.1f} min",
                        tone="warning" if dock_wait >= 30 else "success",
                        threshold="Warning at ≥30 minutes average dock wait",
                        affected_routes=affected,
                    ),
                ]
            )
        return result

    async def _find_route_id(self, route_uuid: uuid.UUID) -> str:
        rows = (await self._session.execute(select(ROUTES.c.route_id))).scalars().all()
        for candidate in rows:
            if _route_uuid(str(candidate)) == route_uuid:
                return str(candidate)
        raise NotFoundError(f"Operational route '{route_uuid}' not found.", code="route_not_found")

    async def _route_output_by_id(self, route_id: str) -> dict[str, object]:
        models = await self._load_models()
        all_routes = await self._fetch_routes()
        route = all_routes.get(route_id)
        if route is None:
            raise NotFoundError(f"Operational route '{route_id}' not found.", code="route_not_found")
        shipments = await self._fetch_shipment_rows(models, [route_id])
        alternatives = await self._fetch_alternatives(route, all_routes)
        shipment_ids = [str(s["shipment_id"]) for s in shipments]
        canonical_by_shipment, checks_by_decision = await self._canonical_lookup(shipment_ids)
        live_decisions = await LogisticsRouteDecisionRepository(self._session).get_decisions(shipment_ids)

        outputs = []
        for shipment in shipments:
            shipment_id = str(shipment["shipment_id"])
            canonical = canonical_by_shipment.get(shipment_id)
            checks = checks_by_decision.get(str(canonical["decision_id"]), []) if canonical else []
            outputs.append(
                _build_shipment_output(
                    shipment, route, alternatives, models, canonical, checks, live_decisions.get(shipment_id)
                )
            )
        avg_cost = sum(float(s["baseline_cost_inr"] or 0.0) for s in shipments) / len(shipments) if shipments else None
        route_with_cost = {**route, "avg_shipment_cost_inr": avg_cost}
        return _aggregate_route(route_with_cost, outputs)

    async def predict_delay(self, route_uuid: uuid.UUID) -> RouteOut:
        route_id = await self._find_route_id(route_uuid)
        return _to_route_out(await self._route_output_by_id(route_id))

    async def reroute(self, route_uuid: uuid.UUID) -> RouteOut:
        """Read-only preview of the real optimizer's recommendation — the
        same "Recommend Reroute" semantics as before, just backed by real
        computation now instead of a hardcoded 2-way string. Nothing is
        persisted here; persisting happens per-shipment via approve/
        modify/review, or in bulk via auto_heal below."""
        route_id = await self._find_route_id(route_uuid)
        return _to_route_out(await self._route_output_by_id(route_id))

    async def list_shipments(self, route_uuid: uuid.UUID) -> list[ShipmentOut]:
        route_id = await self._find_route_id(route_uuid)
        models = await self._load_models()
        all_routes = await self._fetch_routes()
        route = all_routes.get(route_id)
        if route is None:
            raise NotFoundError(f"Operational route '{route_id}' not found.", code="route_not_found")
        shipments = await self._fetch_shipment_rows(models, [route_id])
        alternatives = await self._fetch_alternatives(route, all_routes)
        shipment_ids = [str(s["shipment_id"]) for s in shipments]
        canonical_by_shipment, checks_by_decision = await self._canonical_lookup(shipment_ids)
        live_decisions = await LogisticsRouteDecisionRepository(self._session).get_decisions(shipment_ids)

        route_labels = {rid: _route_label(r) for rid, r in all_routes.items()}
        for rid, r in all_routes.items():
            route_labels[f"origin:{rid}"] = str(r["origin_warehouse_name"])

        outputs = []
        for shipment in shipments:
            shipment_id = str(shipment["shipment_id"])
            canonical = canonical_by_shipment.get(shipment_id)
            checks = checks_by_decision.get(str(canonical["decision_id"]), []) if canonical else []
            outputs.append(
                _build_shipment_output(
                    shipment, route, alternatives, models, canonical, checks, live_decisions.get(shipment_id)
                )
            )
        outputs.sort(key=lambda s: int(s["breach_probability"]), reverse=True)  # type: ignore[arg-type]
        return [_to_shipment_out(s, route_labels) for s in outputs]

    async def _find_shipment(self, shipment_id: str) -> dict[str, object]:
        models = await self._load_models()
        row = (
            (
                await self._session.execute(
                    select(
                        SHIPMENTS.c.shipment_id,
                        SHIPMENTS.c.route_id,
                        SHIPMENTS.c.priority,
                        SHIPMENTS.c.distance_km,
                        SHIPMENTS.c.weather_disruption,
                        SHIPMENTS.c.vehicle_breakdown,
                        SHIPMENTS.c.dispatch_time,
                        SHIPMENTS.c.expected_arrival,
                        SHIPMENTS.c.actual_arrival,
                        SHIPMENTS.c.sla_deadline,
                        SHIPMENTS.c.delay_minutes,
                        SHIPMENTS.c.sla_breach,
                        SHIPMENTS.c.vehicle_id,
                        SHIPMENTS.c.shipment_status,
                        SHIPMENTS.c.baseline_cost_inr,
                    ).where(SHIPMENTS.c.shipment_id == shipment_id)
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise NotFoundError(f"Shipment '{shipment_id}' not found.", code="shipment_not_found")
        shipment = dict(row)
        fallback_utilization = float(models.frame["warehouse_utilization_pct"].mean())
        fallback_dock_wait = float(models.frame["dock_wait_minutes"].mean())
        congestion = (
            (
                await self._session.execute(
                    select(
                        func.avg(WAREHOUSE_EVENTS.c.warehouse_utilization_pct).label("warehouse_utilization_pct"),
                        func.avg(WAREHOUSE_EVENTS.c.dock_wait_minutes).label("dock_wait_minutes"),
                    ).where(WAREHOUSE_EVENTS.c.shipment_id == shipment_id)
                )
            )
            .mappings()
            .one_or_none()
        )
        utilization = congestion["warehouse_utilization_pct"] if congestion else None
        dock_wait = congestion["dock_wait_minutes"] if congestion else None
        shipment["warehouse_utilization_pct"] = float(utilization) if utilization is not None else fallback_utilization
        shipment["dock_wait_minutes"] = float(dock_wait) if dock_wait is not None else fallback_dock_wait
        return shipment

    async def _shipment_output_by_id(self, shipment_id: str) -> dict[str, object]:
        shipment = await self._find_shipment(shipment_id)
        models = await self._load_models()
        all_routes = await self._fetch_routes()
        route = all_routes.get(str(shipment["route_id"]))
        if route is None:
            raise NotFoundError(f"Operational route for shipment '{shipment_id}' not found.", code="route_not_found")
        alternatives = await self._fetch_alternatives(route, all_routes)
        canonical_by_shipment, checks_by_decision = await self._canonical_lookup([shipment_id])
        canonical = canonical_by_shipment.get(shipment_id)
        checks = checks_by_decision.get(str(canonical["decision_id"]), []) if canonical else []
        live_decision = await LogisticsRouteDecisionRepository(self._session).get_decision(shipment_id)
        return _build_shipment_output(shipment, route, alternatives, models, canonical, checks, live_decision)

    async def _decide_shipment(
        self,
        shipment_id: str,
        *,
        status: str,
        modified_action: str | None = None,
        modified_route_id: str | None = None,
        modification_reason: str | None = None,
        reviewer_role: str | None = None,
        reason: str | None = None,
    ) -> dict[str, object]:
        current = await self._shipment_output_by_id(shipment_id)
        if current["governance_track"] == "canonical":
            raise DomainValidationError(
                "This shipment already has an immutable canonical governance decision from the Synthetic "
                "Data Factory's own audit history — view it via Trust Ledger; it cannot be re-decided from here.",
                code="immutable_trust_decision",
            )
        repo = LogisticsRouteDecisionRepository(self._session)
        existing = await repo.get_decision(shipment_id)
        if existing is not None and existing.status == "APPROVED":
            raise ConflictError(
                f"Shipment '{shipment_id}' was already approved — a decision cannot be recorded twice.",
                code="shipment_already_decided",
            )
        await repo.upsert_decision(
            shipment_id=shipment_id,
            status=status,
            recommended_action=str(current["best_action"]),
            recommended_route_id=str(current["best_route_id"]),
            modified_action=modified_action,
            modified_route_id=modified_route_id,
            modification_reason=modification_reason,
            reviewer_role=reviewer_role,
            reason=reason,
        )
        if status == "ESCALATED":
            await repo.create_human_review(shipment_id=shipment_id, reviewer_role=reviewer_role or "", reason=reason)
        return await self._shipment_output_by_id(shipment_id)

    async def approve_shipment(self, shipment_id: str) -> ShipmentOut:
        output = await self._decide_shipment(shipment_id, status="APPROVED")
        return await self._shipment_out_with_labels(output)

    async def modify_shipment(self, shipment_id: str, action: str, route_id: str | None, reason: str) -> ShipmentOut:
        if action == "REROUTE" and not route_id:
            raise DomainValidationError(
                "A modified action of REROUTE requires a real target route_id.", code="missing_route_id"
            )
        output = await self._decide_shipment(
            shipment_id,
            status="APPROVED",
            modified_action=action,
            modified_route_id=route_id if action == "REROUTE" else None,
            modification_reason=reason or None,
        )
        return await self._shipment_out_with_labels(output)

    async def review_shipment(self, shipment_id: str, reviewer_role: str, reason: str) -> ShipmentOut:
        output = await self._decide_shipment(
            shipment_id, status="ESCALATED", reviewer_role=reviewer_role, reason=reason or None
        )
        return await self._shipment_out_with_labels(output)

    async def _shipment_out_with_labels(self, output: dict[str, object]) -> ShipmentOut:
        all_routes = await self._fetch_routes()
        route_labels = {rid: _route_label(r) for rid, r in all_routes.items()}
        for rid, r in all_routes.items():
            route_labels[f"origin:{rid}"] = str(r["origin_warehouse_name"])
        return _to_shipment_out(output, route_labels)

    async def get_shipment_ledger(self, shipment_id: str) -> ShipmentTrustLedgerOut:
        case = await self._shipment_output_by_id(shipment_id)
        compliance = case["compliance_checks"]
        if case["governance_track"] == "canonical":
            outcome = await TrustService(self._session).get_outcome(str(case["decision_code"]))
            return ShipmentTrustLedgerOut(
                track="canonical",
                decision_code=case["decision_code"],  # type: ignore[arg-type]
                approval=str(case["approval_status"]),
                audit_status=str(case["audit_status"]),
                compliance=compliance,  # type: ignore[arg-type]
                priority="Medium",
                priority_reason="Canonical decisions are not re-scored for priority — see the route card.",
                scored_at=datetime.now(UTC),
                model_version=f"{MODEL_NAME} ({MODEL_VERSION})",
                outcome=outcome,
            )
        return ShipmentTrustLedgerOut(
            track="live" if case["decision_code"] else "none",
            decision_code=case["decision_code"],  # type: ignore[arg-type]
            approval=str(case["approval_status"]),
            audit_status=str(case["audit_status"]),
            compliance=compliance,  # type: ignore[arg-type]
            priority="Medium",
            priority_reason="Per-shipment priority is not separately scored — see the route card.",
            scored_at=datetime.now(UTC),
            model_version=f"{MODEL_NAME} ({MODEL_VERSION})",
            recommended_action=str(case["best_action"]).title(),
            recommended_route_id=str(case["best_route_id"]),
            modified_action=str(case["modified_action"]).title() if case["modified_action"] else None,
            modified_route_id=case["modified_route_id"],  # type: ignore[arg-type]
            modification_reason=case["modification_reason"],  # type: ignore[arg-type]
            # Logistics Control Tower has no execution/outcome mechanism
            # yet, the same honest gap Simulation Center runs have (see
            # app/services/trust.py's get_outcome) — never fabricated.
            outcome=OutcomeOut(outcome_status="PENDING"),
        )

    async def auto_heal(self, route_uuid: uuid.UUID) -> AutoHealOut:
        """The real "Approve & Execute" action: batch-approves every real,
        still-undecided, at-risk live shipment on this route, gated by
        the same compliance engine used everywhere else in this app. A
        canonical (already-decided) shipment is skipped, not overridden."""
        route_id = await self._find_route_id(route_uuid)
        route_output = await self._route_output_by_id(route_id)
        models = await self._load_models()
        all_routes = await self._fetch_routes()
        route = all_routes[route_id]
        shipments = await self._fetch_shipment_rows(models, [route_id])
        alternatives = await self._fetch_alternatives(route, all_routes)
        shipment_ids = [str(s["shipment_id"]) for s in shipments]
        canonical_by_shipment, checks_by_decision = await self._canonical_lookup(shipment_ids)
        repo = LogisticsRouteDecisionRepository(self._session)
        live_decisions = await repo.get_decisions(shipment_ids)

        approved = 0
        already_decided = 0
        for shipment in shipments:
            shipment_id = str(shipment["shipment_id"])
            canonical = canonical_by_shipment.get(shipment_id)
            if canonical is not None:
                already_decided += 1
                continue
            existing = live_decisions.get(shipment_id)
            if existing is not None and existing.status == "APPROVED":
                already_decided += 1
                continue
            checks = []
            output = _build_shipment_output(
                shipment, route, alternatives, models, canonical, checks, existing
            )
            if int(output["breach_probability"]) < AT_RISK_BREACH_PROBABILITY:  # type: ignore[arg-type]
                continue
            if output["audit_status"] == "Failed":
                # A mandatory compliance FAIL still blocks execution even
                # inside an "Approve & Execute" bulk action — same rule
                # as everywhere else in this app.
                continue
            await repo.upsert_decision(
                shipment_id=shipment_id,
                status="APPROVED",
                recommended_action=str(output["best_action"]),
                recommended_route_id=str(output["best_route_id"]),
            )
            approved += 1

        updated_route = await self._route_output_by_id(route_id)
        route_label = _route_label(route)
        steps = [
            f"Identify at-risk shipments on {route_label}",
            "Notify assigned transporter",
            "Publish recalculated ETA from shipment events",
            "Flag affected delivery commitments",
            "Monitor next-dispatch SLA",
        ]
        return AutoHealOut(
            route=_to_route_out(updated_route),
            steps=steps,
            approved_shipments=approved,
            already_decided_shipments=already_decided,
        )

    async def get_sla_report(self, route_uuid: uuid.UUID) -> SlaReportOut:
        route_id = await self._find_route_id(route_uuid)
        models = await self._load_models()
        all_routes = await self._fetch_routes()
        route = all_routes.get(route_id)
        if route is None:
            raise NotFoundError(f"Operational route '{route_id}' not found.", code="route_not_found")
        shipments = await self._fetch_shipment_rows(models, [route_id])
        alternatives = await self._fetch_alternatives(route, all_routes)
        canonical_by_shipment, checks_by_decision = await self._canonical_lookup(
            [str(s["shipment_id"]) for s in shipments]
        )
        live_decisions = await LogisticsRouteDecisionRepository(self._session).get_decisions(
            [str(s["shipment_id"]) for s in shipments]
        )

        outputs = []
        for shipment in shipments:
            shipment_id = str(shipment["shipment_id"])
            canonical = canonical_by_shipment.get(shipment_id)
            checks = checks_by_decision.get(str(canonical["decision_id"]), []) if canonical else []
            outputs.append(
                _build_shipment_output(
                    shipment, route, alternatives, models, canonical, checks, live_decisions.get(shipment_id)
                )
            )

        active = len(outputs)
        on_time = sum(1 for s in outputs if not s["sla_breach"])
        at_risk = [s for s in outputs if int(s["breach_probability"]) >= AT_RISK_BREACH_PROBABILITY]  # type: ignore[arg-type]
        expected_breaches = sum(float(s["breach_probability"]) / 100 for s in outputs)
        avg_delay = sum(float(s["delay_minutes"]) for s in outputs) / active if active else 0.0
        cost_exposure = sum(float(s["expected_risk_cost_inr"]) for s in at_risk)

        reroute_targets = [str(s["effective_route_id"]) for s in at_risk if s["effective_action"] == "REROUTE"]
        if reroute_targets:
            target_route_id = max(set(reroute_targets), key=reroute_targets.count)
            recommended_action = f"Reroute at-risk shipments via route {target_route_id}"
        else:
            recommended_action = "Maintain route with ETA monitoring"

        drivers = breach_drivers(models, route_id, _route_label(route), shipments[0]["priority"] if shipments else "NORMAL")

        return SlaReportOut(
            route_id=route_id,
            route_name=_route_label(route),
            active_shipments=active,
            on_time_shipments=on_time,
            at_risk_shipments=len(at_risk),
            expected_breaches=round(expected_breaches, 2),
            average_delay_minutes=round(avg_delay, 1),
            cost_exposure_inr=round(cost_exposure, 2),
            recommended_action=recommended_action,
            drivers=drivers,  # type: ignore[arg-type]
        )
