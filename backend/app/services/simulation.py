"""Simulation Center: reference options and the run lifecycle for all five engines.

All five domains (Auto Sales, Dealer Allocation, Collections, Logistics
Delay, Credit Pricing) are fully wired through the run lifecycle with
real trained models/optimizers/calibrated functions — see
docs/simulation_centre_implementation.md §4/§13.
"""

from __future__ import annotations

import json
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.causal.drivers import CAUSAL_DRIVERS, SIMULATION_DOMAINS
from app.ai.llm.provider import RuleBasedProvider
from app.ai.llm.registry import get_llm_provider
from app.ai.prompts.simulation_summary import build_prompt, parse_polished_summary, polish_is_grounded
from app.ai.simulation import auto_sales, causal_panel, collections_sim, credit_pricing, dealer_allocation, logistics_delay
from app.ai.utils import format_inr
from app.core.cache import cached_read
from app.core.config import get_settings
from app.core.errors import ConflictError, DomainValidationError, NotFoundError
from app.core.logging import get_logger
from app.models.simulation import SimulationRun
from app.repositories import (
    AutoSalesRepository,
    CollectionsSimulationRepository,
    CreditPricingSimulationRepository,
    DealerAllocationRepository,
    LogisticsDelaySimulationRepository,
    ReferenceRepository,
    SimulationRunRepository,
)
from app.repositories.collections_simulation import CHANNEL_DISPLAY_NAMES, OFFER_DISPLAY_NAMES
from app.repositories.credit_pricing_simulation import CREDIT_TYPE_DISPLAY_NAMES
from app.repositories.logistics_delay_simulation import PRIORITY_DISPLAY_NAMES
from app.schemas.simulation import (
    AutoSalesSimIn,
    AutoSalesSimOut,
    CausalDriversOut,
    CollectionsSimIn,
    CollectionsSimOut,
    CreditPricingSimIn,
    CreditPricingSimOut,
    DealerAllocationSimIn,
    DealerAllocationSimOut,
    LogisticsDelaySimIn,
    LogisticsDelaySimOut,
    RouteOption,
    SimulationApprovalOut,
    SimulationCausalEdgeItem,
    SimulationDriverItem,
    SimulationDriversOut,
    SimulationMetaOut,
    SimulationRunDetailOut,
    SimulationSummaryOut,
)
from app.services.base import BaseService

logger = get_logger(__name__)

DEFAULT_SCENARIO = "Baseline FY26"
_DECIDED_STATUSES = {"APPROVED", "REJECTED"}
_DOMAINS_WITH_SUMMARY = {"auto-sales", "dealer-allocation", "collections", "logistics-delay", "credit-pricing"}


class SimulationService(BaseService):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self._ref_repo = ReferenceRepository(session)
        self._run_repo = SimulationRunRepository(session)

    async def get_meta(self) -> SimulationMetaOut:
        return await cached_read("simulations:meta", self._load_meta)

    async def _load_meta(self) -> SimulationMetaOut:
        regions = await self._ref_repo.list_regions()
        models = await self._ref_repo.list_vehicle_models()
        routes = await LogisticsDelaySimulationRepository(self._session).list_routes()
        return SimulationMetaOut(
            regions=list(regions),
            models=list(models),
            routes=[RouteOption(**route) for route in routes],
        )

    async def causal_drivers(self, domain: str) -> CausalDriversOut:
        if domain not in SIMULATION_DOMAINS:
            raise NotFoundError(
                f"Simulation domain '{domain}' is not known.",
                code="unknown_simulation_domain",
            )
        return CausalDriversOut(domain=domain, drivers=list(CAUSAL_DRIVERS))

    async def run_auto_sales(
        self,
        payload: AutoSalesSimIn,
        *,
        scenario_name: str = DEFAULT_SCENARIO,
    ) -> AutoSalesSimOut:
        repo = AutoSalesRepository(self._session)
        result = await auto_sales.run(payload, repo)
        baseline_reference = result.pop("_baseline_reference")
        recommendation = result.pop("_recommendation")
        predictive_drivers = result.pop("_predictive_drivers")

        causal = await causal_panel.get_or_compute_causal_evidence(repo)
        driver_json = {
            "predictive_drivers": predictive_drivers,
            "causal_evidence": [
                {
                    "source": edge.source,
                    "target": edge.target,
                    "lag_days": edge.lag,
                    "score": round(edge.score, 4),
                    "p_value": round(edge.p_value, 4),
                }
                for edge in causal.edges
            ],
            "causal_evidence_note": causal.note,
        }

        run = await self._run_repo.create_run(
            domain="auto-sales",
            scenario_name=scenario_name,
            status="PROPOSED",
            inputs=payload.model_dump(by_alias=True),
            outputs=result,
            baseline_reference=baseline_reference,
            driver_json=driver_json,
            recommendation_json=recommendation,
            confidence=result["conf"],
            confidence_band=result["confidence_band"],
            confidence_basis=result["confidence_basis"],
            model_name=auto_sales.MODEL_NAME,
            model_version=auto_sales.MODEL_VERSION,
        )
        return AutoSalesSimOut(run_id=run.id, status=run.status, **result)

    async def run_dealer_allocation(
        self,
        payload: DealerAllocationSimIn,
        *,
        scenario_name: str = DEFAULT_SCENARIO,
    ) -> DealerAllocationSimOut:
        repo = DealerAllocationRepository(self._session)
        result = await dealer_allocation.run(payload, repo)
        baseline_reference = result.pop("_baseline_reference")
        recommendation = result.pop("_recommendation")
        predictive_drivers = result.pop("_predictive_drivers")

        driver_json = {
            "predictive_drivers": predictive_drivers,
            "causal_evidence": [],
            "causal_evidence_note": (
                "Dealer Allocation is an optimization problem over real demand/quality "
                "weights, not a discovered time-series relationship — see predictive_drivers "
                "for the real data basis of this split."
            ),
        }

        run = await self._run_repo.create_run(
            domain="dealer-allocation",
            scenario_name=scenario_name,
            status="PROPOSED",
            inputs=payload.model_dump(by_alias=True),
            outputs=result,
            baseline_reference=baseline_reference,
            driver_json=driver_json,
            recommendation_json=recommendation,
            confidence=result["conf"],
            confidence_band=result["confidence_band"],
            confidence_basis=result["confidence_basis"],
            model_name=dealer_allocation.MODEL_NAME,
            model_version=dealer_allocation.MODEL_VERSION,
        )
        return DealerAllocationSimOut(run_id=run.id, status=run.status, **result)

    async def run_collections(
        self,
        payload: CollectionsSimIn,
        *,
        scenario_name: str = DEFAULT_SCENARIO,
    ) -> CollectionsSimOut:
        repo = CollectionsSimulationRepository(self._session)
        result = await collections_sim.run(payload, repo)
        baseline_reference = result.pop("_baseline_reference")
        recommendation = result.pop("_recommendation")
        predictive_drivers = result.pop("_predictive_drivers")

        driver_json = {
            "predictive_drivers": predictive_drivers,
            "causal_evidence": [],
            "causal_evidence_note": (
                "Collections uses a real trained recovery model plus a strategy sweep over the real "
                "action space — see predictive_drivers for the real data basis, not a discovered "
                "time-series relationship."
            ),
        }

        run = await self._run_repo.create_run(
            domain="collections",
            scenario_name=scenario_name,
            status="PROPOSED",
            inputs=payload.model_dump(by_alias=True),
            outputs=result,
            baseline_reference=baseline_reference,
            driver_json=driver_json,
            recommendation_json=recommendation,
            confidence=result["conf"],
            confidence_band=result["confidence_band"],
            confidence_basis=result["confidence_basis"],
            model_name=collections_sim.MODEL_NAME,
            model_version=collections_sim.MODEL_VERSION,
        )
        return CollectionsSimOut(run_id=run.id, status=run.status, **result)

    async def run_logistics_delay(
        self,
        payload: LogisticsDelaySimIn,
        *,
        scenario_name: str = DEFAULT_SCENARIO,
    ) -> LogisticsDelaySimOut:
        repo = LogisticsDelaySimulationRepository(self._session)
        result = await logistics_delay.run(payload, repo)
        baseline_reference = result.pop("_baseline_reference")
        recommendation = result.pop("_recommendation")
        predictive_drivers = result.pop("_predictive_drivers")

        driver_json = {
            "predictive_drivers": predictive_drivers,
            "causal_evidence": [],
            "causal_evidence_note": (
                "Logistics Delay uses two trained classifiers plus a reroute sweep over the real "
                "alternative routes on this corridor — see predictive_drivers for the real data basis, "
                "not a discovered time-series relationship."
            ),
        }

        run = await self._run_repo.create_run(
            domain="logistics-delay",
            scenario_name=scenario_name,
            status="PROPOSED",
            inputs=payload.model_dump(by_alias=True),
            outputs=result,
            baseline_reference=baseline_reference,
            driver_json=driver_json,
            recommendation_json=recommendation,
            confidence=result["conf"],
            confidence_band=result["confidence_band"],
            confidence_basis=result["confidence_basis"],
            model_name=logistics_delay.MODEL_NAME,
            model_version=logistics_delay.MODEL_VERSION,
        )
        return LogisticsDelaySimOut(run_id=run.id, status=run.status, **result)

    async def run_credit_pricing(
        self,
        payload: CreditPricingSimIn,
        *,
        scenario_name: str = DEFAULT_SCENARIO,
    ) -> CreditPricingSimOut:
        repo = CreditPricingSimulationRepository(self._session)
        result = await credit_pricing.run(payload, repo)
        baseline_reference = result.pop("_baseline_reference")
        recommendation = result.pop("_recommendation")
        predictive_drivers = result.pop("_predictive_drivers")

        driver_json = {
            "predictive_drivers": predictive_drivers,
            "causal_evidence": [],
            "causal_evidence_note": (
                "Credit Pricing uses two trained regressions plus a calibrated closure-probability sweep — "
                "see predictive_drivers for the real data basis, not a discovered time-series relationship."
            ),
        }

        run = await self._run_repo.create_run(
            domain="credit-pricing",
            scenario_name=scenario_name,
            status="PROPOSED",
            inputs=payload.model_dump(by_alias=True),
            outputs=result,
            baseline_reference=baseline_reference,
            driver_json=driver_json,
            recommendation_json=recommendation,
            confidence=result["conf"],
            confidence_band=result["confidence_band"],
            confidence_basis=result["confidence_basis"],
            model_name=credit_pricing.MODEL_NAME,
            model_version=credit_pricing.MODEL_VERSION,
        )
        return CreditPricingSimOut(run_id=run.id, status=run.status, **result)

    async def get_run(self, run_id: uuid.UUID) -> SimulationRunDetailOut:
        run = await self._get_run_or_404(run_id)
        return self._detail_out(run)

    async def get_drivers(self, run_id: uuid.UUID) -> SimulationDriversOut:
        run = await self._get_run_or_404(run_id)
        stored = run.driver_json or {}
        return SimulationDriversOut(
            run_id=run.id,
            domain=run.domain,
            predictive_drivers=[SimulationDriverItem(**item) for item in stored.get("predictive_drivers", [])],
            causal_evidence=[SimulationCausalEdgeItem(**item) for item in stored.get("causal_evidence", [])],
            causal_evidence_note=stored.get("causal_evidence_note", "No driver evidence was persisted for this run."),
        )

    async def generate_summary(self, run_id: uuid.UUID) -> SimulationSummaryOut:
        run = await self._get_run_or_404(run_id)
        if run.domain not in _DOMAINS_WITH_SUMMARY:
            raise DomainValidationError(
                f"Executive summary is not yet available for '{run.domain}' runs.",
                code="summary_not_supported_for_domain",
            )
        builders = {
            "auto-sales": self._auto_sales_summary,
            "dealer-allocation": self._dealer_allocation_summary,
            "collections": self._collections_summary,
            "logistics-delay": self._logistics_delay_summary,
            "credit-pricing": self._credit_pricing_summary,
        }
        builder = builders[run.domain]
        deterministic = builder(run)
        return await self._polish_summary(deterministic)

    @staticmethod
    async def _polish_summary(summary: SimulationSummaryOut) -> SimulationSummaryOut:
        """LLM wording pass over an already-computed summary.

        The LLM never sees raw run data and is never allowed to add a
        number that wasn't already in ``summary`` — ``polish_is_grounded``
        rejects any reply that drops or alters a figure or the driver set,
        falling back to the deterministic text untouched. No LLM configured
        (or any failure) silently uses the deterministic version — the
        button always works either way.
        """
        llm = get_llm_provider(get_settings())
        if isinstance(llm, RuleBasedProvider):
            return summary
        original = summary.model_dump(mode="json", exclude={"run_id"})
        try:
            raw = await llm.complete(build_prompt(json.dumps(original)))
            polished = parse_polished_summary(raw)
        except Exception as exc:  # noqa: BLE001 — any LLM failure falls back, never breaks the button
            logger.warning("simulation_summary_llm_call_failed", run_id=str(summary.run_id), error=str(exc))
            return summary
        if polished is None:
            logger.warning("simulation_summary_llm_reply_unparseable", run_id=str(summary.run_id), raw=raw[:500])
            return summary
        if not polish_is_grounded(original, polished):
            logger.warning("simulation_summary_llm_reply_ungrounded", run_id=str(summary.run_id), reply=polished)
            return summary
        try:
            result = SimulationSummaryOut(run_id=summary.run_id, **polished)
        except Exception as exc:  # noqa: BLE001 — malformed field types also fall back
            logger.warning("simulation_summary_llm_reply_invalid_shape", run_id=str(summary.run_id), error=str(exc))
            return summary
        logger.info("simulation_summary_llm_polish_applied", run_id=str(summary.run_id))
        return result

    @staticmethod
    def _auto_sales_summary(run: SimulationRun) -> SimulationSummaryOut:
        inputs = run.inputs
        outputs = run.outputs
        baseline = run.baseline_reference or {}
        drivers = run.driver_json or {}

        scenario = f"{run.scenario_name} — {inputs.get('region')} / {inputs.get('model')}"
        inputs_summary = (
            f"Discount {inputs.get('discount')}%, exchange bonus {format_inr(inputs.get('bonus', 0))}, "
            f"campaign spend ₹{inputs.get('campaign')} Cr, "
            f"{str(inputs.get('intensity', '')).lower()} dealer follow-up."
        )
        if baseline:
            baseline_conv = round((baseline.get("baseline_conversion_probability") or 0) * 100)
            baseline_cancel = round((baseline.get("baseline_cancellation_probability") or 0) * 100)
            baseline_text = (
                f"Historical baseline for this cohort ({baseline.get('cohort_lead_count', 0)} leads observed): "
                f"~{baseline_conv}% predicted booking conversion, ~{baseline_cancel}% predicted cancellation rate."
            )
        else:
            baseline_text = "Baseline reference unavailable for this run."
        predicted_outcome = (
            f"Booking uplift {outputs.get('uplift')}%, margin impact {outputs.get('margin')}%, "
            f"cancellation risk {outputs.get('cancel')}%, net revenue impact ₹{outputs.get('rev')} Cr."
        )
        major_drivers = [item["name"] for item in (drivers.get("predictive_drivers") or [])[:4]]
        confidence_basis_text = (
            "a documented incentive-response assumption (no historical discount/bonus/campaign variation "
            "exists to fit one) combined with a trained booking-conversion/cancellation baseline"
            if run.confidence_basis == "calibrated_heuristic"
            else "a calibrated model prediction"
        )
        return SimulationSummaryOut(
            run_id=run.id,
            scenario=scenario,
            inputs_summary=inputs_summary,
            baseline=baseline_text,
            predicted_outcome=predicted_outcome,
            major_drivers=major_drivers or ["No driver evidence persisted for this run."],
            trade_off=(
                "Higher exchange bonus and campaign spend raise projected bookings and revenue but increase "
                "discount/bonus cost and reduce margin — the net revenue figure already nets this trade-off out."
            ),
            recommendation=str(outputs.get("recommendedAction", "")),
            confidence=f"{run.confidence}% ({run.confidence_band}) — {confidence_basis_text}.",
            risk=(
                "No historical discount/exchange-bonus/campaign-spend variation exists in the business data, "
                "so the incentive-response estimate is a calibrated assumption, not a trained pattern — "
                "validate against a real pilot before scaling spend."
            ),
        )

    @staticmethod
    def _dealer_allocation_summary(run: SimulationRun) -> SimulationSummaryOut:
        inputs = run.inputs
        outputs = run.outputs
        baseline = run.baseline_reference or {}
        drivers = run.driver_json or {}

        scenario = f"{run.scenario_name} — {inputs.get('units')} units, {inputs.get('capacity')}% dealer capacity"
        inputs_summary = (
            f"{inputs.get('units')} units available, {inputs.get('demand')}% region demand intensity, "
            f"{inputs.get('capacity')}% dealer capacity, {inputs.get('wait')}-day waiting-period target."
        )
        if baseline:
            baseline_text = (
                f"Real average delivery timeline across {baseline.get('dealer_count', 0)} active dealers: "
                f"~{baseline.get('baseline_wait_days', 0):.1f} days; a naive capacity-proportional split "
                f"(ignoring demand/quality) would average ~{baseline.get('naive_wait_days', 0):.1f} days."
            )
        else:
            baseline_text = "Baseline reference unavailable for this run."
        predicted_outcome = (
            f"Recommended split: {outputs.get('suggestedSplit')}. Delay reduction {outputs.get('delay')} days, "
            f"CSAT {outputs.get('csat')}, incremental value ₹{outputs.get('rev')} L vs. the naive split."
        )
        major_drivers = [item["name"] for item in (drivers.get("predictive_drivers") or [])[:4]]
        confidence_basis_text = (
            "a calibrated waiting-period/CSAT assumption (no historical shortage example exists in the data "
            "to fit a queueing model against) applied on top of a real linear-program allocation over real "
            "dealer demand share and delivery reliability"
        )
        return SimulationSummaryOut(
            run_id=run.id,
            scenario=scenario,
            inputs_summary=inputs_summary,
            baseline=baseline_text,
            predicted_outcome=predicted_outcome,
            major_drivers=major_drivers or ["No driver evidence persisted for this run."],
            trade_off=(
                "Concentrating units on higher-demand, more-reliable dealers improves expected sell-through and "
                "delivery speed versus spreading units proportionally by raw capacity, but leaves less headroom "
                "for lower-performing dealers — the optimizer already trades this off explicitly."
            ),
            recommendation=str(outputs.get("recommendedAction", "")),
            confidence=f"{run.confidence}% ({run.confidence_band}) — {confidence_basis_text}.",
            risk=(
                "No historical example of unmet demand exists in the business data (requested units always "
                "matched allocated units historically), so the waiting-period and CSAT impact are calibrated "
                "assumptions, not trained patterns — validate against a real constrained-supply period before "
                "committing to this split."
            ),
        )

    @staticmethod
    def _collections_summary(run: SimulationRun) -> SimulationSummaryOut:
        inputs = run.inputs
        outputs = run.outputs
        baseline = run.baseline_reference or {}
        drivers = run.driver_json or {}

        channel_label = CHANNEL_DISPLAY_NAMES.get(inputs.get("channel"), inputs.get("channel"))
        offer_label = OFFER_DISPLAY_NAMES.get(inputs.get("offer"), inputs.get("offer"))
        scenario = f"{run.scenario_name} — {inputs.get('risk')} risk, {channel_label} / {offer_label}"
        inputs_summary = (
            f"{inputs.get('risk')} risk segment, {channel_label} channel, {offer_label} offer, "
            f"{inputs.get('field')}% field-visit intensity."
        )
        if baseline:
            baseline_text = (
                f"Real average outstanding for this risk band ({baseline.get('cohort_interaction_count', 0)} "
                f"interactions observed): ₹{baseline.get('avg_outstanding_inr', 0):,.0f}; predicted roll-forward "
                f"(delinquency-worsening) risk {round((baseline.get('roll_forward_risk_probability') or 0) * 100)}%."
            )
        else:
            baseline_text = "Baseline reference unavailable for this run."
        predicted_outcome = (
            f"Recovery probability {outputs.get('prob')}%, cost of recovery ₹{outputs.get('cost')}, "
            f"friction score {outputs.get('friction')}, net recovery value ₹{outputs.get('net')}K."
        )
        major_drivers = [item["name"] for item in (drivers.get("predictive_drivers") or [])[:4]]
        return SimulationSummaryOut(
            run_id=run.id,
            scenario=scenario,
            inputs_summary=inputs_summary,
            baseline=baseline_text,
            predicted_outcome=predicted_outcome,
            major_drivers=major_drivers or ["No driver evidence persisted for this run."],
            trade_off=(
                "Higher-touch channels (field visits) and more generous offers can raise recovery probability "
                "but cost more and increase customer friction — the strategy sweep already nets this out when "
                "recommending an alternative channel/offer."
            ),
            recommendation=str(outputs.get("recommendedAction", "")),
            confidence=(
                f"{run.confidence}% ({run.confidence_band}) — a trained recovery-probability model fit on "
                "real recorded contact outcomes across every channel and offer this screen offers."
            ),
            risk=(
                "No real cost-per-contact field exists in the business data, so recovery cost and friction "
                "are documented calibrated assumptions rather than trained patterns — the recovery "
                "probability itself, and the recommendation, are trained on real outcomes."
            ),
        )

    @staticmethod
    def _logistics_delay_summary(run: SimulationRun) -> SimulationSummaryOut:
        inputs = run.inputs
        outputs = run.outputs
        baseline = run.baseline_reference or {}
        drivers = run.driver_json or {}

        priority_label = PRIORITY_DISPLAY_NAMES.get(inputs.get("sla"), inputs.get("sla"))
        route_label = baseline.get("route_label", inputs.get("route"))
        scenario = f"{run.scenario_name} — {route_label}, {priority_label} priority"
        inputs_summary = (
            f"{route_label} route, {priority_label} priority, {inputs.get('warehouse')}% warehouse load, "
            f"{inputs.get('vehicle')}% vehicle availability, {inputs.get('weather')}% weather disruption."
        )
        if baseline:
            baseline_text = (
                f"Real average for this route ({baseline.get('route_shipment_count', 0)} shipments observed): "
                f"typical transit {baseline.get('typical_transit_hours', 0):.1f}h against a "
                f"{baseline.get('route_sla_hours', 0)}h SLA; base transport cost "
                f"₹{baseline.get('route_baseline_cost_inr', 0):,.0f}."
            )
        else:
            baseline_text = "Baseline reference unavailable for this run."
        predicted_outcome = (
            f"Delay probability {outputs.get('delay')}%, SLA breach risk {outputs.get('breach')}%, "
            f"expected cost impact ₹{outputs.get('cost'):,}. {outputs.get('reroute')}."
        )
        major_drivers = [item["name"] for item in (drivers.get("predictive_drivers") or [])[:4]]
        return SimulationSummaryOut(
            run_id=run.id,
            scenario=scenario,
            inputs_summary=inputs_summary,
            baseline=baseline_text,
            predicted_outcome=predicted_outcome,
            major_drivers=major_drivers or ["No driver evidence persisted for this run."],
            trade_off=(
                "Rerouting to a lower-risk alternative can cut expected delay/breach cost but may carry a "
                "different base transport cost or distance — the reroute sweep already nets this out when "
                "recommending an alternative route."
            ),
            recommendation=str(outputs.get("recommendedAction", "")),
            confidence=(
                f"{run.confidence}% ({run.confidence_band}) — two trained classifiers (any-delay, SLA-breach) "
                "fit on real recorded shipment outcomes for this route and priority tier."
            ),
            risk=(
                "No real per-minute delay-cost or per-breach-penalty field exists in the business data, so "
                "the rupee cost impact is a documented calibrated assumption — the delay and breach "
                "probabilities themselves, and the reroute recommendation, are trained on real outcomes."
            ),
        )

    @staticmethod
    def _credit_pricing_summary(run: SimulationRun) -> SimulationSummaryOut:
        inputs = run.inputs
        outputs = run.outputs
        baseline = run.baseline_reference or {}
        drivers = run.driver_json or {}

        credit_type_label = CREDIT_TYPE_DISPLAY_NAMES.get(inputs.get("type"), inputs.get("type"))
        scenario = f"{run.scenario_name} — {credit_type_label}"
        inputs_summary = (
            f"{credit_type_label} credits, {inputs.get('supply')}% supply level, {inputs.get('demand')}% buyer "
            f"demand, {inputs.get('trace')}% traceability, {inputs.get('verif')}% verification readiness."
        )
        if baseline:
            baseline_text = (
                f"Real average for this credit type ({baseline.get('cohort_listing_count', 0)} listings observed): "
                f"market reference ₹{baseline.get('avg_market_reference_price_inr', 0):,.0f}/tCO2e, seller ask "
                f"₹{baseline.get('avg_seller_ask_price_inr', 0):,.0f}/tCO2e."
            )
        else:
            baseline_text = "Baseline reference unavailable for this run."
        predicted_outcome = (
            f"Recommended price band ₹{outputs.get('priceBandLow')}–₹{outputs.get('priceBandHigh')}/tCO2e, "
            f"{outputs.get('closure')}% closure probability, {outputs.get('match')}% buyer match, "
            f"{outputs.get('complianceRisk')} compliance risk."
        )
        major_drivers = [item["name"] for item in (drivers.get("predictive_drivers") or [])[:4]]
        return SimulationSummaryOut(
            run_id=run.id,
            scenario=scenario,
            inputs_summary=inputs_summary,
            baseline=baseline_text,
            predicted_outcome=predicted_outcome,
            major_drivers=major_drivers or ["No driver evidence persisted for this run."],
            trade_off=(
                "Asking further above the market reference price can raise expected per-credit value but lowers "
                "closure probability — the pricing sweep already nets this out when recommending a price."
            ),
            recommendation=str(outputs.get("recommendedAction", "")),
            confidence=(
                f"{run.confidence}% ({run.confidence_band}) — two trained price/buyer-interest regressions "
                "combined with a documented closure-probability calibration (no real closed/not-closed outcome "
                "exists in the business data to train a classifier against)."
            ),
            risk=(
                "listing_status is OPEN for every real listing in the business data, so trade-closure "
                "probability is a documented calibrated assumption, not a trained pattern — the price and "
                "buyer-interest predictions themselves are trained on real historical listings."
            ),
        )

    async def approve_run(self, run_id: uuid.UUID, reason: str | None) -> SimulationApprovalOut:
        return await self._decide_run(run_id, decision="approved", reason=reason)

    async def reject_run(self, run_id: uuid.UUID, reason: str | None) -> SimulationApprovalOut:
        return await self._decide_run(run_id, decision="rejected", reason=reason)

    async def _decide_run(
        self,
        run_id: uuid.UUID,
        *,
        decision: str,
        reason: str | None,
    ) -> SimulationApprovalOut:
        run = await self._get_run_or_404(run_id)
        if run.status in _DECIDED_STATUSES:
            raise ConflictError(
                f"Simulation run '{run_id}' was already {run.status.lower()} — a decision cannot be recorded twice.",
                code="simulation_run_already_decided",
            )
        approval = await self._run_repo.create_approval(run_id=run_id, decision=decision, reason=reason)
        new_status = "APPROVED" if decision == "approved" else "REJECTED"
        run = await self._run_repo.update_status(run, new_status)
        return SimulationApprovalOut(
            run_id=run.id,
            status=run.status,
            decision=approval.decision,
            decided_at=approval.decided_at,
            actor=approval.actor,
        )

    async def _get_run_or_404(self, run_id: uuid.UUID) -> SimulationRun:
        run = await self._run_repo.get_run(run_id)
        if run is None:
            raise NotFoundError(f"Simulation run '{run_id}' not found.", code="simulation_run_not_found")
        return run

    @staticmethod
    def _detail_out(run: SimulationRun) -> SimulationRunDetailOut:
        return SimulationRunDetailOut(
            run_id=run.id,
            status=run.status,
            domain=run.domain,
            scenario_name=run.scenario_name,
            inputs=run.inputs,
            baseline_reference=run.baseline_reference,
            outputs=run.outputs,
            driver_json=run.driver_json,
            recommendation_json=run.recommendation_json,
            confidence=run.confidence,
            confidence_band=run.confidence_band,
            confidence_basis=run.confidence_basis,
            model_name=run.model_name,
            model_version=run.model_version,
            created_at=run.created_at,
        )
