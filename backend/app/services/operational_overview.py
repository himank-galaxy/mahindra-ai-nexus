"""Executive Overview aggregations over canonical runtime business records.

This service intentionally queries the validated Synthetic Data Factory
runtime tables instead of the legacy POC ORM models.

Runtime sources
---------------
- bookings
- cancellations
- finance_applications
- shipments
- dmrv_records

The service derives KPI and recommendation outputs from operational evidence.
It does not read pre-rendered dashboard values and does not depend on legacy
ORM columns such as ``booking_code`` or ``booking_value``.
"""

from __future__ import annotations

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import DomainValidationError, NotFoundError
from app.database.runtime_schema import runtime_tables
from app.schemas.overview import KpiOut, RecommendationOut
from app.services.base import BaseService


BOOKINGS = runtime_tables["bookings"]
CANCELLATIONS = runtime_tables["cancellations"]
FINANCE_APPLICATIONS = runtime_tables["finance_applications"]
SHIPMENTS = runtime_tables["shipments"]
DMRV_RECORDS = runtime_tables["dmrv_records"]


def _cr(value: float | int | None) -> str:
    """Format INR as crore for the overview UI."""

    amount = float(value or 0)
    return f"₹{amount / 10_000_000:.1f} Cr"


def _ratio(
    numerator: float | int,
    denominator: float | int,
) -> float:
    """Safe 0..1 ratio."""

    if not denominator:
        return 0.0

    return max(
        0.0,
        min(
            1.0,
            float(numerator) / float(denominator),
        ),
    )


def _confidence(rate: float) -> int:
    """Convert an evidence-derived ratio to a bounded percentage."""

    return max(
        0,
        min(
            100,
            round(rate * 100),
        ),
    )


def _risk_from_rate(rate: float) -> str:
    """Derive simple intervention risk from observed prevalence."""

    if rate >= 0.25:
        return "High"

    if rate >= 0.10:
        return "Medium"

    return "Low"


class OperationalOverviewService(BaseService):
    """Executive measures derived from canonical PostgreSQL runtime tables."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    # ------------------------------------------------------------------
    # Runtime fact aggregations
    # ------------------------------------------------------------------

    async def _booking_facts(self) -> dict[str, float | int]:
        stmt = select(
            func.count().label("rows"),
            func.coalesce(
                func.sum(
                    BOOKINGS.c.vehicle_base_price_inr
                ),
                0,
            ).label("vehicle_value_inr"),
            func.coalesce(
                func.sum(
                    BOOKINGS.c.booking_amount_inr
                ),
                0,
            ).label("booking_amount_inr"),
            func.count().filter(
                BOOKINGS.c.completed_test_drive.is_(True)
            ).label("completed_test_drive_bookings"),
            func.count().filter(
                BOOKINGS.c.finance_assisted.is_(True)
            ).label("finance_assisted_bookings"),
        )

        row = (
            await self._session.execute(stmt)
        ).one()

        return {
            "rows": int(row.rows or 0),
            "vehicle_value_inr": float(
                row.vehicle_value_inr or 0
            ),
            "booking_amount_inr": float(
                row.booking_amount_inr or 0
            ),
            "completed_test_drive_bookings": int(
                row.completed_test_drive_bookings or 0
            ),
            "finance_assisted_bookings": int(
                row.finance_assisted_bookings or 0
            ),
        }

    async def _cancellation_facts(
        self,
    ) -> dict[str, object]:
        aggregate_stmt = select(
            func.count().label("rows"),
            func.coalesce(
                func.sum(
                    CANCELLATIONS.c.booking_amount_inr
                ),
                0,
            ).label("booking_amount_inr"),
            func.coalesce(
                func.sum(
                    CANCELLATIONS.c.refund_amount_inr
                ),
                0,
            ).label("refund_amount_inr"),
            func.coalesce(
                func.sum(
                    CANCELLATIONS.c.retained_amount_inr
                ),
                0,
            ).label("retained_amount_inr"),
        )

        aggregate = (
            await self._session.execute(
                aggregate_stmt
            )
        ).one()

        reason_stmt = (
            select(
                CANCELLATIONS.c.cancellation_reason,
                func.count().label("rows"),
            )
            .group_by(
                CANCELLATIONS.c.cancellation_reason
            )
            .order_by(
                func.count().desc(),
                CANCELLATIONS.c.cancellation_reason,
            )
            .limit(1)
        )

        reason_row = (
            await self._session.execute(
                reason_stmt
            )
        ).first()

        return {
            "rows": int(
                aggregate.rows or 0
            ),
            "booking_amount_inr": float(
                aggregate.booking_amount_inr or 0
            ),
            "refund_amount_inr": float(
                aggregate.refund_amount_inr or 0
            ),
            "retained_amount_inr": float(
                aggregate.retained_amount_inr or 0
            ),
            "leading_reason": (
                str(reason_row.cancellation_reason)
                if reason_row
                else None
            ),
            "leading_reason_rows": (
                int(reason_row.rows)
                if reason_row
                else 0
            ),
        }

    async def _finance_facts(
        self,
    ) -> dict[str, float | int]:
        stmt = select(
            func.count().label("rows"),
            func.count().filter(
                FINANCE_APPLICATIONS.c.status
                == "APPROVED"
            ).label("approved"),
            func.count().filter(
                FINANCE_APPLICATIONS.c.status
                == "MANUAL_REVIEW"
            ).label("manual_review"),
            func.count().filter(
                FINANCE_APPLICATIONS.c.status
                == "PENDING"
            ).label("pending"),
            func.count().filter(
                FINANCE_APPLICATIONS.c.status
                == "REJECTED"
            ).label("rejected"),
            func.count().filter(
                FINANCE_APPLICATIONS.c.approval_tat_hours
                > 72
            ).label("over_72_hours"),
            func.coalesce(
                func.avg(
                    FINANCE_APPLICATIONS.c.approval_tat_hours
                ),
                0,
            ).label("avg_tat_hours"),
        )

        row = (
            await self._session.execute(stmt)
        ).one()

        return {
            "rows": int(row.rows or 0),
            "approved": int(
                row.approved or 0
            ),
            "manual_review": int(
                row.manual_review or 0
            ),
            "pending": int(
                row.pending or 0
            ),
            "rejected": int(
                row.rejected or 0
            ),
            "over_72_hours": int(
                row.over_72_hours or 0
            ),
            "avg_tat_hours": float(
                row.avg_tat_hours or 0
            ),
        }

    async def _shipment_facts(
        self,
    ) -> dict[str, float | int]:
        stmt = select(
            func.count().label("rows"),
            func.count().filter(
                SHIPMENTS.c.sla_breach.is_(True)
            ).label("sla_breaches"),
            func.count().filter(
                SHIPMENTS.c.sla_breach.is_(False)
            ).label("sla_met"),
            func.coalesce(
                func.sum(
                    SHIPMENTS.c.units
                ).filter(
                    SHIPMENTS.c.sla_breach.is_(True)
                ),
                0,
            ).label(
                "units_on_breached_shipments"
            ),
            func.coalesce(
                func.avg(
                    SHIPMENTS.c.delay_minutes
                ),
                0,
            ).label("avg_delay_minutes"),
        )

        row = (
            await self._session.execute(stmt)
        ).one()

        return {
            "rows": int(row.rows or 0),
            "sla_breaches": int(
                row.sla_breaches or 0
            ),
            "sla_met": int(
                row.sla_met or 0
            ),
            "units_on_breached_shipments": int(
                row.units_on_breached_shipments or 0
            ),
            "avg_delay_minutes": float(
                row.avg_delay_minutes or 0
            ),
        }

    async def _dmrv_facts(
        self,
    ) -> dict[str, int]:
        fully_evidenced = and_(
            DMRV_RECORDS.c.evidence_available.is_(True),
            DMRV_RECORDS.c.source_reference_present.is_(True),
            DMRV_RECORDS.c.evidence_attachment_present.is_(True),
            DMRV_RECORDS.c.timestamp_verified.is_(True),
            DMRV_RECORDS.c.digital_signature_present.is_(True),
            DMRV_RECORDS.c.operator_identity_present.is_(True),
            DMRV_RECORDS.c.chain_of_custody_present.is_(True),
            DMRV_RECORDS.c.measurement_calibration_present.is_(True),
            DMRV_RECORDS.c.source_job_quality_check_passed.is_(True),
        )

        stmt = select(
            func.count().label("rows"),
            func.count().filter(
                DMRV_RECORDS.c.evidence_available.is_(True)
            ).label("evidence_available"),
            func.count().filter(
                DMRV_RECORDS.c.evidence_status
                == "MISSING"
            ).label("missing"),
            func.count().filter(
                fully_evidenced
            ).label("fully_evidenced"),
        )

        row = (
            await self._session.execute(stmt)
        ).one()

        return {
            "rows": int(row.rows or 0),
            "evidence_available": int(
                row.evidence_available or 0
            ),
            "missing": int(
                row.missing or 0
            ),
            "fully_evidenced": int(
                row.fully_evidenced or 0
            ),
        }

    async def _facts(
        self,
    ) -> tuple[
        dict[str, float | int],
        dict[str, object],
        dict[str, float | int],
        dict[str, float | int],
        dict[str, int],
    ]:
        """Read the five canonical overview fact groups."""

        bookings = await self._booking_facts()
        cancellations = await self._cancellation_facts()
        finance = await self._finance_facts()
        shipments = await self._shipment_facts()
        dmrv = await self._dmrv_facts()

        return (
            bookings,
            cancellations,
            finance,
            shipments,
            dmrv,
        )

    # ------------------------------------------------------------------
    # KPI API
    # ------------------------------------------------------------------

    async def list_kpis(
        self,
    ) -> list[KpiOut]:
        (
            bookings,
            cancellations,
            finance,
            shipments,
            dmrv,
        ) = await self._facts()

        booking_rows = int(
            bookings["rows"]
        )

        if booking_rows == 0:
            return []

        cancellation_rows = int(
            cancellations["rows"]
        )

        retained_booking_ratio = _ratio(
            booking_rows - cancellation_rows,
            booking_rows,
        )

        test_drive_booking_ratio = _ratio(
            int(
                bookings[
                    "completed_test_drive_bookings"
                ]
            ),
            booking_rows,
        )

        approval_ratio = _ratio(
            int(
                finance["approved"]
            ),
            int(
                finance["rows"]
            ),
        )

        sla_met_ratio = _ratio(
            int(
                shipments["sla_met"]
            ),
            int(
                shipments["rows"]
            ),
        )

        evidence_readiness_ratio = _ratio(
            int(
                dmrv["fully_evidenced"]
            ),
            int(
                dmrv["rows"]
            ),
        )

        vehicle_value = float(
            bookings["vehicle_value_inr"]
        )

        cancelled_booking_amount = float(
            cancellations[
                "booking_amount_inr"
            ]
        )

        return [
            KpiOut(
                id="predicted-revenue-uplift",
                label="Predicted Revenue Uplift",
                value=_cr(
                    vehicle_value * 0.075
                ),
                trend=(
                    "Scenario value derived from "
                    "current booked vehicle value"
                ),
                up=True,
                confidence=_confidence(
                    retained_booking_ratio
                ),
                drivers=[
                    (
                        f"{booking_rows:,} "
                        "booking records"
                    ),
                    (
                        f"{_cr(vehicle_value)} "
                        "booked vehicle value"
                    ),
                    (
                        f"{retained_booking_ratio:.1%} "
                        "booking retention"
                    ),
                ],
            ),
            KpiOut(
                id="leakage-prevented",
                label="Leakage Prevented",
                value=_cr(
                    cancelled_booking_amount
                    * 0.35
                ),
                trend=(
                    "Recoverable scenario share of "
                    "observed cancellation exposure"
                ),
                up=True,
                confidence=_confidence(
                    retained_booking_ratio
                ),
                drivers=[
                    (
                        f"{cancellation_rows:,} "
                        "confirmed cancellations"
                    ),
                    (
                        f"{_cr(cancelled_booking_amount)} "
                        "cancelled booking amount"
                    ),
                    (
                        "Cancellation reason and "
                        "refund evidence"
                    ),
                ],
            ),
            KpiOut(
                id="dealer-conversion",
                label="Dealer Conversion Uplift",
                value=(
                    f"{test_drive_booking_ratio * 100:.1f}%"
                ),
                trend=(
                    "Share of bookings with a "
                    "completed test drive"
                ),
                up=test_drive_booking_ratio >= 0.40,
                confidence=_confidence(
                    test_drive_booking_ratio
                ),
                drivers=[
                    (
                        f"{int(bookings['completed_test_drive_bookings']):,} "
                        "bookings after completed test drives"
                    ),
                    (
                        f"{booking_rows:,} "
                        "total bookings"
                    ),
                ],
            ),
            KpiOut(
                id="financial-risk",
                label="Financial Risk Reduction",
                value=(
                    f"{approval_ratio * 100:.1f}%"
                ),
                trend=(
                    "Observed finance approval rate"
                ),
                up=approval_ratio >= 0.50,
                confidence=_confidence(
                    approval_ratio
                ),
                drivers=[
                    (
                        f"{int(finance['approved']):,} "
                        "approved applications"
                    ),
                    (
                        f"{int(finance['rows']):,} "
                        "finance applications"
                    ),
                    (
                        f"{float(finance['avg_tat_hours']):.1f}h "
                        "average decision TAT"
                    ),
                ],
            ),
            KpiOut(
                id="sla-avoidance",
                label="SLA Breach Avoidance",
                value=(
                    f"{sla_met_ratio * 100:.1f}%"
                ),
                trend=(
                    "Shipment records delivered "
                    "without SLA breach"
                ),
                up=sla_met_ratio >= 0.70,
                confidence=_confidence(
                    sla_met_ratio
                ),
                drivers=[
                    (
                        f"{int(shipments['sla_met']):,} "
                        "shipments met SLA"
                    ),
                    (
                        f"{int(shipments['sla_breaches']):,} "
                        "SLA breaches"
                    ),
                    (
                        f"{float(shipments['avg_delay_minutes']):.1f} "
                        "min average delay"
                    ),
                ],
            ),
            KpiOut(
                id="circularity-value",
                label="ESG / Circularity Evidence Readiness",
                value=(
                    f"{evidence_readiness_ratio * 100:.1f}%"
                ),
                trend=(
                    "dMRV records with complete "
                    "verification evidence chain"
                ),
                up=evidence_readiness_ratio >= 0.60,
                confidence=_confidence(
                    evidence_readiness_ratio
                ),
                drivers=[
                    (
                        f"{int(dmrv['fully_evidenced']):,} "
                        "fully evidenced dMRV records"
                    ),
                    (
                        f"{int(dmrv['rows']):,} "
                        "total dMRV records"
                    ),
                    (
                        f"{int(dmrv['missing']):,} "
                        "records marked missing"
                    ),
                ],
            ),
        ]

    # ------------------------------------------------------------------
    # Recommendation API
    # ------------------------------------------------------------------

    async def list_recommendations(
        self,
    ) -> list[RecommendationOut]:
        (
            bookings,
            cancellations,
            finance,
            shipments,
            dmrv,
        ) = await self._facts()

        results: list[
            RecommendationOut
        ] = []

        shipment_rows = int(
            shipments["rows"]
        )
        breached_shipments = int(
            shipments["sla_breaches"]
        )

        if breached_shipments:
            breach_rate = _ratio(
                breached_shipments,
                shipment_rows,
            )

            results.append(
                RecommendationOut(
                    id="shipment-intervention",
                    title=(
                        "Intervene on "
                        f"{breached_shipments:,} "
                        "SLA-breached shipment(s)"
                    ),
                    impact=(
                        f"{int(shipments['units_on_breached_shipments']):,} "
                        "unit(s) moved on breached shipments"
                    ),
                    confidence=_confidence(
                        breach_rate
                    ),
                    risk=_risk_from_rate(
                        breach_rate
                    ),
                    status="Pending",
                )
            )

        finance_rows = int(
            finance["rows"]
        )

        non_final_finance = (
            int(finance["manual_review"])
            + int(finance["pending"])
        )

        if non_final_finance:
            finance_rate = _ratio(
                non_final_finance,
                finance_rows,
            )

            results.append(
                RecommendationOut(
                    id="finance-intervention",
                    title=(
                        "Resolve "
                        f"{non_final_finance:,} "
                        "non-final finance decision(s)"
                    ),
                    impact=(
                        f"{int(finance['manual_review']):,} "
                        "manual-review and "
                        f"{int(finance['pending']):,} "
                        "pending application(s)"
                    ),
                    confidence=_confidence(
                        finance_rate
                    ),
                    risk=_risk_from_rate(
                        finance_rate
                    ),
                    status="Pending",
                )
            )

        cancellation_rows = int(
            cancellations["rows"]
        )

        if cancellation_rows:
            leading_reason = (
                str(
                    cancellations[
                        "leading_reason"
                    ]
                )
                if cancellations[
                    "leading_reason"
                ]
                else "UNKNOWN"
            )

            leading_reason_rows = int(
                cancellations[
                    "leading_reason_rows"
                ]
            )

            reason_rate = _ratio(
                leading_reason_rows,
                cancellation_rows,
            )

            results.append(
                RecommendationOut(
                    id="cancellation-intervention",
                    title=(
                        "Address leading cancellation "
                        "reason: "
                        + leading_reason.replace(
                            "_",
                            " ",
                        ).title()
                    ),
                    impact=(
                        f"{leading_reason_rows:,} of "
                        f"{cancellation_rows:,} "
                        "cancellations; "
                        f"{_cr(cancellations['booking_amount_inr'])} "
                        "booking amount exposed"
                    ),
                    confidence=_confidence(
                        reason_rate
                    ),
                    risk=_risk_from_rate(
                        reason_rate
                    ),
                    status="Pending",
                )
            )

        dmrv_rows = int(
            dmrv["rows"]
        )

        incomplete_dmrv = (
            dmrv_rows
            - int(
                dmrv["fully_evidenced"]
            )
        )

        if incomplete_dmrv:
            incomplete_rate = _ratio(
                incomplete_dmrv,
                dmrv_rows,
            )

            results.append(
                RecommendationOut(
                    id="dmrv-intervention",
                    title=(
                        "Close evidence gaps in "
                        f"{incomplete_dmrv:,} "
                        "dMRV record(s)"
                    ),
                    impact=(
                        f"{int(dmrv['fully_evidenced']):,} "
                        "of "
                        f"{dmrv_rows:,} "
                        "records currently have the "
                        "complete evidence chain"
                    ),
                    confidence=_confidence(
                        incomplete_rate
                    ),
                    risk=_risk_from_rate(
                        incomplete_rate
                    ),
                    status="Pending",
                )
            )

        return results

    # ------------------------------------------------------------------
    # Existing API compatibility
    # ------------------------------------------------------------------

    async def update_recommendation_status(
        self,
        code: str,
        status: str,
    ) -> RecommendationOut:
        """Preserve the existing Overview API response contract.

        Persistence of approvals into the governance decision workflow will
        be migrated separately; this method does not fabricate a database
        recommendation row.
        """

        if status not in {
            "Approved",
            "Under Review",
        }:
            raise DomainValidationError(
                (
                    "Status must be "
                    "'Approved' or 'Under Review'."
                ),
                code="invalid_recommendation_status",
            )

        item = next(
            (
                row
                for row
                in await self.list_recommendations()
                if row.id == code
            ),
            None,
        )

        if item is None:
            raise NotFoundError(
                f"Recommendation '{code}' not found.",
                code="recommendation_not_found",
            )

        return item.model_copy(
            update={
                "status": status,
            }
        )
