"""Collections & Recovery views over canonical finance operations."""

from __future__ import annotations

import uuid
from collections import defaultdict

from sqlalchemy import func, select

from app.core.errors import DomainValidationError, NotFoundError
from app.database.runtime_schema import runtime_tables
from app.schemas.collections import (
    CollectionsAgentOut,
    CollectionsCaseOut,
    MetricTileOut,
)
from app.services.base import BaseService

COLLECTION_CASES = runtime_tables["collection_cases"]
COLLECTION_INTERACTIONS = runtime_tables["collection_interactions"]
LOAN_ACCOUNTS = runtime_tables["loan_accounts"]
PAYMENT_HISTORY = runtime_tables["payment_history"]
FINANCE_CUSTOMERS = runtime_tables["finance_customers"]
CASE_NAMESPACE = uuid.UUID("aaad670c-3b50-4580-b21f-ec2f6a857938")


def _case_uuid(case_id: str) -> uuid.UUID:
    return uuid.uuid5(CASE_NAMESPACE, case_id)


def _inr(amount: float) -> str:
    if amount >= 10_000_000:
        return f"₹{amount / 10_000_000:.1f} Cr"
    if amount >= 100_000:
        return f"₹{amount / 100_000:.1f}L"
    return f"₹{amount:,.0f}"


def _priority_action(current_dpd: int, latest_offer: str | None) -> str:
    if latest_offer and latest_offer != "NONE":
        return latest_offer.replace("_", " ").title()
    if current_dpd >= 90:
        return "Field review"
    if current_dpd >= 30:
        return "Structured contact"
    return "Digital reminder"


class CollectionsService(BaseService):
    async def list_metrics(self) -> list[MetricTileOut]:
        cases = (
            await self._session.execute(
                select(
                    func.count().label("cases"),
                    func.count().filter(COLLECTION_CASES.c.case_status == "OPEN").label("open_cases"),
                    func.count().filter(COLLECTION_CASES.c.current_dpd >= 90).label("ninety_plus_dpd"),
                    func.coalesce(
                        func.sum(COLLECTION_CASES.c.current_arrears_inr),
                        0,
                    ).label("current_arrears"),
                )
            )
        ).one()
        interactions = (
            await self._session.execute(
                select(
                    func.count().label("interactions"),
                    func.count()
                    .filter(COLLECTION_INTERACTIONS.c.payment_after_contact.is_(True))
                    .label("payments_after_contact"),
                    func.count().filter(COLLECTION_INTERACTIONS.c.promise_to_pay.is_(True)).label("promises"),
                    func.count()
                    .filter(COLLECTION_INTERACTIONS.c.payment_after_promise.is_(True))
                    .label("payments_after_promise"),
                )
            )
        ).one()
        payments = (
            await self._session.execute(
                select(
                    func.coalesce(
                        func.sum(PAYMENT_HISTORY.c.actual_payment_amount_inr),
                        0,
                    ).label("actual"),
                    func.coalesce(
                        func.sum(PAYMENT_HISTORY.c.scheduled_payment_amount_inr),
                        0,
                    ).label("scheduled"),
                )
            )
        ).one()

        interaction_count = int(interactions.interactions or 0)
        promise_count = int(interactions.promises or 0)
        contact_recovery_rate = (
            int(interactions.payments_after_contact or 0) / interaction_count * 100 if interaction_count else 0.0
        )
        promise_kept_rate = (
            int(interactions.payments_after_promise or 0) / promise_count * 100 if promise_count else 0.0
        )
        payment_realization = (
            min(100.0, float(payments.actual or 0) / float(payments.scheduled) * 100)
            if float(payments.scheduled or 0)
            else 0.0
        )

        open_cases = int(cases.open_cases or 0)
        total_cases = int(cases.cases or 0)

        return [
            MetricTileOut(
                label="Open collection cases",
                value=str(open_cases),
                tone="warning" if open_cases else "success",
            ),
            MetricTileOut(
                label="Current arrears",
                value=_inr(float(cases.current_arrears or 0)),
                tone="danger" if float(cases.current_arrears or 0) else "success",
            ),
            MetricTileOut(
                label="90+ DPD cases",
                value=str(int(cases.ninety_plus_dpd or 0)),
                tone="danger" if int(cases.ninety_plus_dpd or 0) else "success",
            ),
            MetricTileOut(
                label="Payment after contact",
                value=f"{contact_recovery_rate:.1f}%",
                tone="success" if contact_recovery_rate >= 20 else "warning",
            ),
            MetricTileOut(
                label="Promise kept",
                value=f"{promise_kept_rate:.1f}%",
                tone="success" if promise_kept_rate >= 50 else "warning",
            ),
            MetricTileOut(
                label="Scheduled payment realization",
                value=f"{payment_realization:.1f}%",
                tone="success" if payment_realization >= 90 else "warning",
            ),
            MetricTileOut(
                label="Resolved cases",
                value=str(total_cases - open_cases),
                tone="success",
            ),
        ]

    async def list_agents(self) -> list[CollectionsAgentOut]:
        rows = (
            await self._session.execute(
                select(
                    COLLECTION_INTERACTIONS.c.channel,
                    func.count().label("interactions"),
                )
                .group_by(COLLECTION_INTERACTIONS.c.channel)
                .order_by(COLLECTION_INTERACTIONS.c.channel)
            )
        ).all()
        return [
            CollectionsAgentOut(
                name=f"{channel.replace('_', ' ').title()} workflow",
                status=f"{int(count)} observed interactions",
            )
            for channel, count in rows
        ]

    async def _case_rows(self) -> list[dict[str, object]]:
        cases = (
            (
                await self._session.execute(
                    select(
                        COLLECTION_CASES,
                        LOAN_ACCOUNTS.c.outstanding_principal_inr
                        if "outstanding_principal_inr" in LOAN_ACCOUNTS.c
                        else LOAN_ACCOUNTS.c.principal_inr,
                        FINANCE_CUSTOMERS.c.income_stability,
                    )
                    .join(
                        LOAN_ACCOUNTS,
                        LOAN_ACCOUNTS.c.loan_account_id == COLLECTION_CASES.c.loan_account_id,
                    )
                    .join(
                        FINANCE_CUSTOMERS,
                        FINANCE_CUSTOMERS.c.finance_customer_id == COLLECTION_CASES.c.finance_customer_id,
                    )
                    .order_by(
                        COLLECTION_CASES.c.current_dpd.desc(),
                        COLLECTION_CASES.c.current_arrears_inr.desc(),
                    )
                )
            )
            .mappings()
            .all()
        )

        interaction_rows = (
            (
                await self._session.execute(
                    select(COLLECTION_INTERACTIONS).order_by(
                        COLLECTION_INTERACTIONS.c.collection_case_id,
                        COLLECTION_INTERACTIONS.c.interaction_sequence,
                    )
                )
            )
            .mappings()
            .all()
        )
        interactions_by_case: dict[str, list[dict[str, object]]] = defaultdict(list)
        for row in interaction_rows:
            interactions_by_case[str(row["collection_case_id"])].append(dict(row))

        output: list[dict[str, object]] = []
        for case in cases:
            case_id = str(case["collection_case_id"])
            interactions = interactions_by_case.get(case_id, [])
            latest = interactions[-1] if interactions else {}
            payment_successes = sum(bool(row["payment_after_contact"]) for row in interactions)
            observed_probability = round(payment_successes / len(interactions) * 100) if interactions else 0
            output.append(
                {
                    **dict(case),
                    "latest_channel": latest.get("channel"),
                    "latest_offer": latest.get("offer_type"),
                    "observed_probability": observed_probability,
                    "interaction_count": len(interactions),
                }
            )
        return output

    async def list_cases(self) -> list[CollectionsCaseOut]:
        result: list[CollectionsCaseOut] = []
        for case in await self._case_rows():
            current_dpd = int(case["current_dpd"] or 0)
            channel = str(case.get("latest_channel") or "UNCONTACTED")
            result.append(
                CollectionsCaseOut(
                    id=_case_uuid(str(case["collection_case_id"])),
                    customer=str(case["finance_customer_id"]),
                    dpd=current_dpd,
                    out=_inr(float(case["current_arrears_inr"] or 0)),
                    roll=min(100, round(current_dpd / 90 * 100)),
                    channel=channel.replace("_", " ").title(),
                    action=_priority_action(
                        current_dpd,
                        (str(case["latest_offer"]) if case.get("latest_offer") else None),
                    ),
                    prob=int(case["observed_probability"]),
                    flag="Review" if current_dpd >= 90 else "OK",
                    status=str(case["case_status"]).replace("_", " ").title(),
                )
            )
        return result

    async def _case_by_uuid(
        self,
        case_id: uuid.UUID,
    ) -> dict[str, object]:
        for case in await self._case_rows():
            if _case_uuid(str(case["collection_case_id"])) == case_id:
                return case
        raise NotFoundError(
            f"Collections case '{case_id}' not found.",
            code="case_not_found",
        )

    async def approve_case(self, case_id: uuid.UUID) -> CollectionsCaseOut:
        await self._case_by_uuid(case_id)
        raise DomainValidationError(
            "Legacy action approval is not a canonical collection-case state.",
            code="unsupported_legacy_collections_mutation",
        )

    async def modify_case(
        self,
        case_id: uuid.UUID,
        action: str,
    ) -> CollectionsCaseOut:
        await self._case_by_uuid(case_id)
        raise DomainValidationError(
            "The canonical collection schema has no arbitrary action field.",
            code="unsupported_legacy_collections_mutation",
        )

    async def review_case(self, case_id: uuid.UUID) -> CollectionsCaseOut:
        await self._case_by_uuid(case_id)
        raise DomainValidationError(
            "Human review must be recorded through the canonical review workflow, not a dashboard-shaped case status.",
            code="unsupported_legacy_collections_mutation",
        )

    async def get_case_ledger(self, case_id: uuid.UUID) -> list[str]:
        case = await self._case_by_uuid(case_id)
        canonical_id = str(case["collection_case_id"])
        interactions = (
            (
                await self._session.execute(
                    select(COLLECTION_INTERACTIONS)
                    .where(COLLECTION_INTERACTIONS.c.collection_case_id == canonical_id)
                    .order_by(COLLECTION_INTERACTIONS.c.interaction_sequence)
                )
            )
            .mappings()
            .all()
        )
        ledger = [
            (
                f"{row['interaction_at'].isoformat()}: "
                f"{str(row['channel']).replace('_', ' ').title()} — "
                f"{str(row['customer_response']).replace('_', ' ').title()}"
            )
            for row in interactions
        ]
        if ledger:
            return ledger
        return [
            (
                f"Case created {case['case_created_at'].isoformat()} with "
                f"{int(case['current_dpd'])} DPD and no recorded interactions."
            )
        ]
