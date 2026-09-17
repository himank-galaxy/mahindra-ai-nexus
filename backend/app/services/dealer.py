"""Dealer Revenue Optimizer over canonical operational records."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select

from app.core.errors import DomainValidationError, NotFoundError
from app.database.runtime_schema import runtime_tables
from app.schemas.dealer import CoachOut, DealerLeadOut, DealerOut, LeadPitchOut
from app.services.base import BaseService

DEALERS = runtime_tables["dealers"]
LEADS = runtime_tables["leads"]
FOLLOWUPS = runtime_tables["followups"]
TEST_DRIVES = runtime_tables["test_drives"]
BOOKINGS = runtime_tables["bookings"]
CANCELLATIONS = runtime_tables["cancellations"]
SERVICE_EVENTS = runtime_tables["service_events"]
VEHICLE_MODELS = runtime_tables["vehicle_models"]
LEAD_NAMESPACE = uuid.UUID("de440a57-2285-42e8-aab0-e15de184512c")
HOT_INTENT_THRESHOLD = 0.65


def _lead_uuid(lead_id: str) -> uuid.UUID:
    return uuid.uuid5(LEAD_NAMESPACE, lead_id)


def _inr(amount: float) -> str:
    if amount >= 10_000_000:
        return f"₹{amount / 10_000_000:.1f} Cr"
    if amount >= 100_000:
        return f"₹{amount / 100_000:.1f}L"
    return f"₹{amount:,.0f}"


class DealerService(BaseService):
    async def _dealer_exists(self, dealer_id: str) -> bool:
        return (
            await self._session.execute(
                select(DEALERS.c.dealer_id).where(
                    DEALERS.c.dealer_id == dealer_id,
                    DEALERS.c.active.is_(True),
                )
            )
        ).scalar_one_or_none() is not None

    async def list_dealers(self) -> list[DealerOut]:
        dealers = (
            (
                await self._session.execute(
                    select(DEALERS).where(DEALERS.c.active.is_(True)).order_by(DEALERS.c.dealer_name)
                )
            )
            .mappings()
            .all()
        )

        lead_rows = (
            (
                await self._session.execute(
                    select(
                        LEADS.c.dealer_id,
                        func.count().label("leads"),
                        func.count().filter(LEADS.c.latent_purchase_intent >= HOT_INTENT_THRESHOLD).label("hot_leads"),
                    ).group_by(LEADS.c.dealer_id)
                )
            )
            .mappings()
            .all()
        )
        leads_by_dealer = {row["dealer_id"]: row for row in lead_rows}

        drive_rows = (
            (
                await self._session.execute(
                    select(
                        TEST_DRIVES.c.dealer_id,
                        func.count()
                        .filter(
                            TEST_DRIVES.c.completed.is_(False),
                            TEST_DRIVES.c.status != "NO_SHOW",
                        )
                        .label("pending"),
                    ).group_by(TEST_DRIVES.c.dealer_id)
                )
            )
            .mappings()
            .all()
        )
        drives_by_dealer = {row["dealer_id"]: row for row in drive_rows}

        booking_rows = (
            (
                await self._session.execute(
                    select(
                        BOOKINGS.c.dealer_id,
                        func.count().label("bookings"),
                    ).group_by(BOOKINGS.c.dealer_id)
                )
            )
            .mappings()
            .all()
        )
        bookings_by_dealer = {row["dealer_id"]: row for row in booking_rows}

        cancellation_rows = (
            (
                await self._session.execute(
                    select(
                        CANCELLATIONS.c.dealer_id,
                        func.count().label("cancellations"),
                        func.coalesce(
                            func.sum(CANCELLATIONS.c.booking_amount_inr),
                            0,
                        ).label("value_at_risk"),
                    ).group_by(CANCELLATIONS.c.dealer_id)
                )
            )
            .mappings()
            .all()
        )
        cancellations_by_dealer = {row["dealer_id"]: row for row in cancellation_rows}

        service_rows = (
            (
                await self._session.execute(
                    select(
                        SERVICE_EVENTS.c.service_dealer_id.label("dealer_id"),
                        func.coalesce(
                            func.sum(SERVICE_EVENTS.c.service_duration_hours),
                            0,
                        ).label("service_hours"),
                        func.min(SERVICE_EVENTS.c.service_started_at).label("period_start"),
                        func.max(SERVICE_EVENTS.c.service_completed_at).label("period_end"),
                    ).group_by(SERVICE_EVENTS.c.service_dealer_id)
                )
            )
            .mappings()
            .all()
        )
        service_by_dealer = {row["dealer_id"]: row for row in service_rows}

        output: list[DealerOut] = []
        for dealer in dealers:
            dealer_id = str(dealer["dealer_id"])
            lead = leads_by_dealer.get(dealer_id, {})
            drive = drives_by_dealer.get(dealer_id, {})
            booking = bookings_by_dealer.get(dealer_id, {})
            cancellation = cancellations_by_dealer.get(dealer_id, {})
            service = service_by_dealer.get(dealer_id, {})

            lead_count = int(lead.get("leads", 0) or 0)
            booking_count = int(booking.get("bookings", 0) or 0)
            cancellation_count = int(cancellation.get("cancellations", 0) or 0)
            booking_probability = round(booking_count / lead_count * 100) if lead_count else 0
            leakage = cancellation_count / booking_count * 100 if booking_count else 0.0

            bay_utilization = 0.0
            period_start = service.get("period_start")
            period_end = service.get("period_end")
            if period_start and period_end and period_end > period_start:
                available_hours = (period_end - period_start).total_seconds() / 3600 * int(dealer["service_bays"])
                if available_hours:
                    bay_utilization = min(
                        100.0,
                        float(service.get("service_hours", 0) or 0) / available_hours * 100,
                    )

            output.append(
                DealerOut(
                    id=dealer_id,
                    name=str(dealer["dealer_name"]),
                    leads=lead_count,
                    hotLeads=int(lead.get("hot_leads", 0) or 0),
                    testDrivesPending=int(drive.get("pending", 0) or 0),
                    bookingProb=booking_probability,
                    revenueAtRisk=_inr(float(cancellation.get("value_at_risk", 0) or 0)),
                    leakage=f"{leakage:.1f}%",
                    bayUtil=f"{bay_utilization:.1f}%",
                )
            )
        return output

    async def list_leads(self, dealer_code: str) -> list[DealerLeadOut]:
        if not await self._dealer_exists(dealer_code):
            raise NotFoundError(
                f"Dealer '{dealer_code}' not found.",
                code="dealer_not_found",
            )

        lead_rows = (
            (
                await self._session.execute(
                    select(
                        LEADS,
                        VEHICLE_MODELS.c.base_price,
                    )
                    .join(
                        VEHICLE_MODELS,
                        VEHICLE_MODELS.c.vehicle_model_id == LEADS.c.vehicle_model_id,
                    )
                    .where(LEADS.c.dealer_id == dealer_code)
                    .order_by(
                        LEADS.c.latent_purchase_intent.desc(),
                        LEADS.c.lead_created_at.desc(),
                    )
                )
            )
            .mappings()
            .all()
        )
        lead_ids = [row["lead_id"] for row in lead_rows]
        if not lead_ids:
            return []

        followup_ids = set(
            (
                await self._session.execute(
                    select(FOLLOWUPS.c.lead_id).where(
                        FOLLOWUPS.c.lead_id.in_(lead_ids),
                        FOLLOWUPS.c.completed.is_(True),
                    )
                )
            )
            .scalars()
            .all()
        )
        drive_ids = set(
            (await self._session.execute(select(TEST_DRIVES.c.lead_id).where(TEST_DRIVES.c.lead_id.in_(lead_ids))))
            .scalars()
            .all()
        )
        completed_drive_ids = set(
            (
                await self._session.execute(
                    select(TEST_DRIVES.c.lead_id).where(
                        TEST_DRIVES.c.lead_id.in_(lead_ids),
                        TEST_DRIVES.c.completed.is_(True),
                    )
                )
            )
            .scalars()
            .all()
        )
        booking_ids = set(
            (await self._session.execute(select(BOOKINGS.c.lead_id).where(BOOKINGS.c.lead_id.in_(lead_ids))))
            .scalars()
            .all()
        )

        result: list[DealerLeadOut] = []
        for row in lead_rows:
            lead_id = str(row["lead_id"])
            if lead_id in booking_ids:
                action = "Booking recorded"
                status = "Converted"
            elif lead_id in completed_drive_ids:
                action = "Follow up after completed test drive"
                status = "Test drive completed"
            elif lead_id in drive_ids:
                action = "Confirm scheduled test drive"
                status = "Test drive requested"
            elif lead_id in followup_ids:
                action = "Continue recorded follow-up"
                status = "Follow-up completed"
            else:
                action = "Start dealer follow-up"
                status = "New"

            result.append(
                DealerLeadOut(
                    id=_lead_uuid(lead_id),
                    name=str(row["customer_id"]),
                    vehicle=str(row["vehicle_model_name"]),
                    score=round(float(row["engagement_score"]) * 100),
                    prob=round(float(row["latent_purchase_intent"]) * 100),
                    action=action,
                    revenue=_inr(float(row["base_price"])),
                    status=status,
                )
            )
        return result

    async def get_coach(self, dealer_code: str) -> CoachOut:
        leads = await self.list_leads(dealer_code)
        dealers = {dealer.id: dealer for dealer in await self.list_dealers()}
        dealer = dealers[dealer_code]
        if not leads:
            return CoachOut(
                topAction="No open lead evidence is available",
                expected="No current opportunity could be calculated",
                bestOffer="No offer evidence is available",
                bestTime="No contact-time evidence is available",
                risk=(f"Recorded cancellation exposure: {dealer.revenue_at_risk}"),
            )

        top = leads[0]
        return CoachOut(
            topAction=f"{top.action} for {top.name}",
            expected=(f"{top.revenue} opportunity · {top.prob}% observed purchase intent"),
            bestOffer=(f"Continue the recorded {top.vehicle} customer journey"),
            bestTime="No contact-time evidence is available",
            risk=(f"Recorded cancellation exposure: {dealer.revenue_at_risk}"),
        )

    async def _lead_for_uuid(
        self,
        lead_id: uuid.UUID,
        dealer_code: str | None = None,
    ) -> DealerLeadOut:
        dealer_ids = (
            [dealer_code]
            if dealer_code is not None
            else (await self._session.execute(select(DEALERS.c.dealer_id).where(DEALERS.c.active.is_(True))))
            .scalars()
            .all()
        )
        for current_dealer in dealer_ids:
            for lead in await self.list_leads(str(current_dealer)):
                if lead.id == lead_id:
                    return lead
        raise NotFoundError(
            f"Lead '{lead_id}' not found.",
            code="lead_not_found",
        )

    async def generate_pitch(
        self,
        dealer_code: str,
        lead_id: uuid.UUID,
    ) -> LeadPitchOut:
        lead = await self._lead_for_uuid(lead_id, dealer_code)
        return LeadPitchOut(
            name=lead.name,
            text=(
                f"Hello {lead.name}, you registered interest in the "
                f"{lead.vehicle}. May the dealership help you continue "
                "with the next recorded step in your purchase journey?"
            ),
        )

    async def message_lead(self, lead_id: uuid.UUID) -> DealerLeadOut:
        await self._lead_for_uuid(lead_id)
        raise DomainValidationError(
            "The legacy message-status mutation has no lossless canonical runtime representation.",
            code="unsupported_legacy_dealer_mutation",
        )

    async def schedule_test_drive(
        self,
        lead_id: uuid.UUID,
        slot: str,
    ) -> DealerLeadOut:
        await self._lead_for_uuid(lead_id)
        raise DomainValidationError(
            "The free-text legacy slot cannot be written safely to canonical test-drive timestamps.",
            code="unsupported_legacy_dealer_mutation",
        )

    async def convert_lead(self, lead_id: uuid.UUID) -> DealerLeadOut:
        await self._lead_for_uuid(lead_id)
        raise DomainValidationError(
            "A canonical booking requires operational facts not present in the legacy convert request.",
            code="unsupported_legacy_dealer_mutation",
        )
