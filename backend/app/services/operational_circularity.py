"""Circular Economy API values derived from canonical runtime records."""

from __future__ import annotations

from sqlalchemy import func, select

from app.core.errors import DomainValidationError, NotFoundError
from app.database.runtime_schema import runtime_tables
from app.schemas.circularity import (
    CreditOut,
    DmrvAskIn,
    DmrvAskOut,
    ElvEstimateIn,
    ElvEstimateOut,
    RvsfMetricOut,
)
from app.services.base import BaseService

CREDIT_LISTINGS = runtime_tables["credit_listings"]
DMRV_RECORDS = runtime_tables["dmrv_records"]
ELV_ASSESSMENTS = runtime_tables["elv_assessments"]
RVSF_JOB_CARDS = runtime_tables["rvsf_job_cards"]


def _credit_out(row: dict[str, object]) -> CreditOut:
    expected = int(row["dmrv_expected_records"] or 0)
    available = int(row["dmrv_available_records"] or 0)
    trace_fields = (
        "dmrv_source_reference_records",
        "dmrv_attachment_records",
        "dmrv_timestamp_verified_records",
        "dmrv_signature_records",
        "dmrv_operator_identity_records",
        "dmrv_chain_of_custody_records",
        "dmrv_calibration_records",
    )
    trace_denominator = expected * len(trace_fields)
    trace_numerator = sum(int(row[field] or 0) for field in trace_fields)
    ask = float(row["seller_ask_price_per_tco2e_inr"] or 0)
    highest_bid = float(row["highest_bid_price_per_tco2e_inr"] or 0)
    match = min(100, round(highest_bid / ask * 100)) if ask else 0
    closure = round(available / expected * 100) if expected else 0
    trace = round(trace_numerator / trace_denominator * 100) if trace_denominator else 0
    return CreditOut(
        id=str(row["carbon_credit_listing_id"]),
        type=str(row["credit_type"]).replace("_", " ").title(),
        price=f"₹{ask:,.0f}/tCO₂e",
        match=match,
        closure=closure,
        trace=trace,
    )


class OperationalCircularityService(BaseService):
    async def list_credits(self) -> list[CreditOut]:
        rows = (
            (await self._session.execute(select(CREDIT_LISTINGS).order_by(CREDIT_LISTINGS.c.listing_at.desc())))
            .mappings()
            .all()
        )
        return [_credit_out(dict(row)) for row in rows]

    async def list_rvsf_metrics(self) -> list[RvsfMetricOut]:
        jobs = (
            await self._session.execute(
                select(
                    func.count().label("jobs"),
                    func.count().filter(RVSF_JOB_CARDS.c.job_status == "COMPLETED").label("completed"),
                    func.count().filter(RVSF_JOB_CARDS.c.quality_check_passed.is_(False)).label("quality_failures"),
                    func.coalesce(
                        func.avg(RVSF_JOB_CARDS.c.processing_duration_minutes),
                        0,
                    ).label("avg_duration"),
                    func.coalesce(
                        func.sum(RVSF_JOB_CARDS.c.reusable_parts_mass_kg),
                        0,
                    ).label("reused_mass"),
                    func.coalesce(
                        func.sum(RVSF_JOB_CARDS.c.recyclable_material_mass_kg),
                        0,
                    ).label("recycled_mass"),
                )
            )
        ).one()
        evidence = (
            await self._session.execute(
                select(
                    func.count().label("records"),
                    func.count().filter(DMRV_RECORDS.c.evidence_available.is_(True)).label("available"),
                )
            )
        ).one()
        record_count = int(evidence.records or 0)
        evidence_coverage = int(evidence.available or 0) / record_count * 100 if record_count else 0.0
        return [
            RvsfMetricOut(
                label="Job-card throughput",
                value=f"{int(jobs.completed or 0)}/{int(jobs.jobs or 0)} completed",
                tone="success",
            ),
            RvsfMetricOut(
                label="Average processing time",
                value=f"{float(jobs.avg_duration or 0):.1f} min",
                tone="default",
            ),
            RvsfMetricOut(
                label="Quality-check failures",
                value=str(int(jobs.quality_failures or 0)),
                tone=("warning" if int(jobs.quality_failures or 0) else "success"),
            ),
            RvsfMetricOut(
                label="Recovered reusable mass",
                value=f"{float(jobs.reused_mass or 0):,.0f} kg",
                tone="success",
            ),
            RvsfMetricOut(
                label="Recovered recyclable mass",
                value=f"{float(jobs.recycled_mass or 0):,.0f} kg",
                tone="success",
            ),
            RvsfMetricOut(
                label="dMRV evidence coverage",
                value=f"{evidence_coverage:.1f}%",
                tone="success" if evidence_coverage >= 95 else "warning",
            ),
        ]

    async def list_dmrv_prompts(self) -> list[str]:
        return [
            "Which facility has the lowest evidence availability?",
            "How many dMRV evidence records are available?",
            "Which evidence type has the lowest traceability coverage?",
        ]

    async def dmrv_ask(self, payload: DmrvAskIn) -> DmrvAskOut:
        question = " ".join(payload.question.split())
        lowered = question.lower()
        if "facility" in lowered:
            rows = (
                await self._session.execute(
                    select(
                        DMRV_RECORDS.c.rvsf_facility_name,
                        func.count().label("records"),
                        func.count().filter(DMRV_RECORDS.c.evidence_available.is_(True)).label("available"),
                    )
                    .group_by(DMRV_RECORDS.c.rvsf_facility_name)
                    .order_by(DMRV_RECORDS.c.rvsf_facility_name)
                )
            ).all()
            facility, records, available = min(
                rows,
                key=lambda row: int(row.available or 0) / int(row.records) if row.records else 0,
            )
            coverage = int(available or 0) / int(records) * 100
            answer = (
                f"{facility} has the lowest observed evidence availability "
                f"at {coverage:.1f}% across {int(records)} records."
            )
        else:
            totals = (
                await self._session.execute(
                    select(
                        func.count().label("records"),
                        func.count().filter(DMRV_RECORDS.c.evidence_available.is_(True)).label("available"),
                    )
                )
            ).one()
            answer = (
                f"{int(totals.available or 0)} of "
                f"{int(totals.records or 0)} canonical dMRV records have "
                "available evidence."
            )
        return DmrvAskOut(question=question, answer=answer)

    async def estimate_elv(
        self,
        payload: ElvEstimateIn,
    ) -> ElvEstimateOut:
        assessment_count = (await self._session.execute(select(func.count()).select_from(ELV_ASSESSMENTS))).scalar_one()
        raise DomainValidationError(
            f"{assessment_count} canonical ELV assessments exist, but the "
            "runtime schema contains no monetary valuation fields required "
            "by this legacy response.",
            code="elv_valuation_unavailable",
        )

    async def _credit_by_code(self, code: str) -> CreditOut:
        row = (
            (
                await self._session.execute(
                    select(CREDIT_LISTINGS).where(CREDIT_LISTINGS.c.carbon_credit_listing_id == code)
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise NotFoundError(
                f"Credit '{code}' not found.",
                code="credit_not_found",
            )
        return _credit_out(dict(row))

    async def reprice_credit(self, code: str) -> CreditOut:
        await self._credit_by_code(code)
        raise DomainValidationError(
            "Canonical credit repricing requires an explicit price input.",
            code="credit_reprice_input_required",
        )

    async def match_buyer(self, code: str) -> CreditOut:
        await self._credit_by_code(code)
        raise DomainValidationError(
            "Canonical buyer matching requires an identified buyer.",
            code="credit_buyer_required",
        )
