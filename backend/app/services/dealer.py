"""Dealer Revenue Optimizer: dealers, leads and lead actions."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.models import DealerLead
from app.models.enums import DealerLeadStatus
from app.repositories import DealerRepository
from app.schemas.dealer import CoachOut, DealerLeadOut, DealerOut, LeadPitchOut
from app.services.base import BaseService
from app.utils.display import DEALER_LEAD_STATUS_DISPLAY

# Exact port of the pitch template rendered in dealer.tsx.
PITCH_TEMPLATE = (
    "Hi {name}, based on your interest and profile, the XUV700 with our current ₹25,000 "
    "exchange bonus + 6.99% pre-approved finance would put your on-road cost within your "
    "target. I can hold a test drive slot at 6 PM tomorrow — would that work?"
)

# Static AI Dealer Coach panel content (dealer.tsx).
COACH_CONTENT = CoachOut(
    top_action="Call Rakesh Patil within 2h with ₹25K exchange bonus.",
    expected="+₹19.8L expected · 74% probability",
    best_offer="XUV700 exchange bonus + finance pre-approval",
    best_time="Weekdays 6–8 PM, Sat 11 AM–1 PM",
    risk="Potential ₹42L revenue leakage this week from top 5 stale hot leads.",
)


class DealerService(BaseService):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self._repo = DealerRepository(session)

    async def list_dealers(self) -> list[DealerOut]:
        dealers = await self._repo.list_all()
        return [
            DealerOut(
                id=dealer.code,
                name=dealer.name,
                leads=dealer.leads,
                hot_leads=dealer.hot_leads,
                test_drives_pending=dealer.test_drives_pending,
                booking_prob=dealer.booking_prob,
                revenue_at_risk=dealer.revenue_at_risk,
                leakage=f"{dealer.leakage_pct}%",
                bay_util=f"{dealer.bay_util_pct}%",
            )
            for dealer in dealers
        ]

    async def list_leads(self, dealer_code: str) -> list[DealerLeadOut]:
        dealer = await self._repo.get_by_code(dealer_code)
        if dealer is None:
            raise NotFoundError(f"Dealer '{dealer_code}' not found.", code="dealer_not_found")
        leads = await self._repo.list_leads(dealer.id)
        return [self._to_lead_out(lead) for lead in leads]

    async def get_coach(self, dealer_code: str) -> CoachOut:
        """AI Dealer Coach panel content for the selected dealership."""
        await self._get_dealer(dealer_code)
        return COACH_CONTENT.model_copy()

    async def generate_pitch(self, dealer_code: str, lead_id: uuid.UUID) -> LeadPitchOut:
        """Personalized pitch text for one lead of the selected dealer."""
        dealer = await self._get_dealer(dealer_code)
        lead = await self._get_lead(lead_id)
        if lead.dealer_id != dealer.id:
            raise NotFoundError(f"Lead '{lead_id}' not found.", code="lead_not_found")
        return LeadPitchOut(name=lead.name, text=PITCH_TEMPLATE.format(name=lead.name))

    async def message_lead(self, lead_id: uuid.UUID) -> DealerLeadOut:
        """Mark the WhatsApp follow-up as sent."""
        lead = await self._get_lead(lead_id)
        lead.status = DealerLeadStatus.MESSAGE_SENT
        lead.message_sent_at = datetime.now(UTC)
        await self._session.commit()
        return self._to_lead_out(lead)

    async def schedule_test_drive(self, lead_id: uuid.UUID, slot: str) -> DealerLeadOut:
        """Book a test-drive slot for the lead."""
        lead = await self._get_lead(lead_id)
        lead.test_drive_slot = slot
        await self._session.commit()
        return self._to_lead_out(lead)

    async def convert_lead(self, lead_id: uuid.UUID) -> DealerLeadOut:
        """Mark the lead as converted (booking secured)."""
        lead = await self._get_lead(lead_id)
        lead.status = DealerLeadStatus.CONVERTED
        lead.converted_at = datetime.now(UTC)
        await self._session.commit()
        return self._to_lead_out(lead)

    async def _get_dealer(self, dealer_code: str):
        dealer = await self._repo.get_by_code(dealer_code)
        if dealer is None:
            raise NotFoundError(f"Dealer '{dealer_code}' not found.", code="dealer_not_found")
        return dealer

    async def _get_lead(self, lead_id: uuid.UUID) -> DealerLead:
        lead = await self._repo.get_lead(lead_id)
        if lead is None:
            raise NotFoundError(f"Lead '{lead_id}' not found.", code="lead_not_found")
        return lead

    @staticmethod
    def _to_lead_out(lead: DealerLead) -> DealerLeadOut:
        return DealerLeadOut(
            id=lead.id,
            name=lead.name,
            vehicle=lead.vehicle,
            score=lead.score,
            prob=lead.prob,
            action=lead.action,
            revenue=lead.revenue,
            status=DEALER_LEAD_STATUS_DISPLAY[lead.status],
        )
