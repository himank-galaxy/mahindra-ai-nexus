"""Financial Services views over canonical finance operations."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select

from app.ai.scoring.emi import simulate_offer
from app.core.errors import DomainValidationError, NotFoundError
from app.database.runtime_schema import runtime_tables
from app.schemas.finance import (
    CustomerTwinOut,
    FinanceProductOut,
    RmScriptOut,
    SimulateOfferIn,
    SimulateOfferOut,
    TwinExplainOut,
    TwinSummaryOut,
)
from app.services.base import BaseService

FINANCE_PRODUCTS = runtime_tables["finance_products"]
FINANCE_CUSTOMERS = runtime_tables["finance_customers"]
LOAN_ACCOUNTS = runtime_tables["loan_accounts"]
PAYMENT_HISTORY = runtime_tables["payment_history"]
CROSS_SELL_EVENTS = runtime_tables["cross_sell_events"]
TWIN_NAMESPACE = uuid.UUID("d797df2b-94a8-4c1f-b54c-8c5eea53883c")


def _twin_uuid(customer_id: str) -> uuid.UUID:
    return uuid.uuid5(TWIN_NAMESPACE, customer_id)


def _inr(amount: float) -> str:
    if amount >= 10_000_000:
        return f"₹{amount / 10_000_000:.1f} Cr"
    if amount >= 100_000:
        return f"₹{amount / 100_000:.1f}L"
    return f"₹{amount:,.0f}"


class FinanceService(BaseService):
    async def list_products(self) -> list[FinanceProductOut]:
        products = (
            (
                await self._session.execute(
                    select(FINANCE_PRODUCTS)
                    .where(FINANCE_PRODUCTS.c.active.is_(True))
                    .order_by(FINANCE_PRODUCTS.c.product_name)
                )
            )
            .mappings()
            .all()
        )
        loan_counts = dict(
            (
                await self._session.execute(
                    select(
                        LOAN_ACCOUNTS.c.finance_product_id,
                        func.count().label("count"),
                    ).group_by(LOAN_ACCOUNTS.c.finance_product_id)
                )
            ).all()
        )
        payment_rows = (
            await self._session.execute(
                select(
                    PAYMENT_HISTORY.c.finance_product_id,
                    func.count().label("payments"),
                    func.count().filter(PAYMENT_HISTORY.c.days_past_due_after_event >= 30).label("thirty_plus"),
                ).group_by(PAYMENT_HISTORY.c.finance_product_id)
            )
        ).all()
        risk_by_product = {
            product_id: (int(thirty_plus or 0) / int(payments) * 100 if payments else 0.0)
            for product_id, payments, thirty_plus in payment_rows
        }
        cross_sell_rows = (
            await self._session.execute(
                select(
                    CROSS_SELL_EVENTS.c.offered_finance_product_id,
                    func.count().label("offers"),
                    func.coalesce(
                        func.sum(CROSS_SELL_EVENTS.c.offer_amount_inr),
                        0,
                    ).label("opportunity"),
                ).group_by(CROSS_SELL_EVENTS.c.offered_finance_product_id)
            )
        ).all()
        cross_sell = {
            product_id: (int(offers), float(opportunity)) for product_id, offers, opportunity in cross_sell_rows
        }

        result = []
        for product in products:
            product_id = str(product["finance_product_id"])
            offers, opportunity = cross_sell.get(product_id, (0, 0.0))
            result.append(
                FinanceProductOut(
                    name=str(product["product_name"]),
                    customers=str(int(loan_counts.get(product_id, 0))),
                    risk=f"{risk_by_product.get(product_id, 0.0):.1f}% 30+ DPD",
                    cross=f"{offers} recorded offers",
                    opp=_inr(opportunity),
                )
            )
        return result

    async def list_twin_summaries(self) -> list[TwinSummaryOut]:
        rows = (
            (
                await self._session.execute(
                    select(FINANCE_CUSTOMERS.c.finance_customer_id).where(FINANCE_CUSTOMERS.c.active.is_(True))
                )
            )
            .scalars()
            .all()
        )
        return [TwinSummaryOut(id=_twin_uuid(str(customer_id)), name=str(customer_id)) for customer_id in rows]

    async def _customer_id(self, twin_id: uuid.UUID) -> str:
        rows = (
            (
                await self._session.execute(
                    select(FINANCE_CUSTOMERS.c.finance_customer_id).where(FINANCE_CUSTOMERS.c.active.is_(True))
                )
            )
            .scalars()
            .all()
        )
        for customer_id in rows:
            if _twin_uuid(str(customer_id)) == twin_id:
                return str(customer_id)
        raise NotFoundError(
            f"Customer twin '{twin_id}' not found.",
            code="twin_not_found",
        )

    async def get_twin(self, twin_id: uuid.UUID) -> CustomerTwinOut:
        customer_id = await self._customer_id(twin_id)
        customer = (
            (
                await self._session.execute(
                    select(FINANCE_CUSTOMERS).where(FINANCE_CUSTOMERS.c.finance_customer_id == customer_id)
                )
            )
            .mappings()
            .one()
        )
        loans = (
            (
                await self._session.execute(
                    select(LOAN_ACCOUNTS)
                    .where(LOAN_ACCOUNTS.c.finance_customer_id == customer_id)
                    .order_by(LOAN_ACCOUNTS.c.disbursed_at)
                )
            )
            .mappings()
            .all()
        )
        payments = (
            (
                await self._session.execute(
                    select(PAYMENT_HISTORY)
                    .where(PAYMENT_HISTORY.c.finance_customer_id == customer_id)
                    .order_by(PAYMENT_HISTORY.c.payment_due_at)
                )
            )
            .mappings()
            .all()
        )
        offers = (
            (
                await self._session.execute(
                    select(CROSS_SELL_EVENTS)
                    .where(CROSS_SELL_EVENTS.c.finance_customer_id == customer_id)
                    .order_by(CROSS_SELL_EVENTS.c.offered_at)
                )
            )
            .mappings()
            .all()
        )
        latest_payment = payments[-1] if payments else None
        latest_offer = offers[-1] if offers else None
        max_dpd = max(
            (int(payment["days_past_due_after_event"]) for payment in payments),
            default=0,
        )
        product_names = list(dict.fromkeys(str(loan["product_name"]) for loan in loans))
        nba = (
            {
                "product": latest_offer["offered_product_name"],
                "amount": float(latest_offer["offer_amount_inr"]),
                "channel": latest_offer["offer_channel"],
                "response": latest_offer["customer_response"],
            }
            if latest_offer
            else {"status": "No recorded cross-sell offer"}
        )
        cross_sell = (
            {
                "offer": str(latest_offer["offered_product_name"]),
                "response": str(latest_offer["customer_response"]),
            }
            if latest_offer
            else {"status": "No recorded cross-sell event"}
        )
        return CustomerTwinOut(
            id=twin_id,
            name=customer_id,
            location=f"{customer['city_name']}, {customer['region_name']}",
            income_stability=str(customer["income_stability"]).replace("_", " ").title(),
            repayment=(
                str(latest_payment["payment_status"]).replace("_", " ").title()
                if latest_payment
                else "No payment history"
            ),
            products=product_names,
            nba=nba,
            risk_decomposition={
                "maxDpd": str(max_dpd),
                "obligationToIncome": (f"{float(customer['obligation_to_income_ratio']) * 100:.1f}%"),
                "incomeStability": str(customer["income_stability"]),
            },
            cross_sell=cross_sell,
            approval_status="No approval state in runtime_0001",
        )

    async def submit_twin_approval(
        self,
        twin_id: uuid.UUID,
    ) -> CustomerTwinOut:
        await self._customer_id(twin_id)
        raise DomainValidationError(
            "The canonical finance schema has no customer-twin approval state.",
            code="unsupported_legacy_finance_mutation",
        )

    async def explain_twin(self, twin_id: uuid.UUID) -> TwinExplainOut:
        twin = await self.get_twin(twin_id)
        return TwinExplainOut(
            bullets=[
                f"Latest repayment state: {twin.repayment}",
                f"Income stability: {twin.income_stability}",
                (f"Maximum observed DPD: {twin.risk_decomposition['maxDpd']}"),
            ]
        )

    async def generate_rm_script(self, twin_id: uuid.UUID) -> RmScriptOut:
        await self._customer_id(twin_id)
        raise DomainValidationError(
            "No canonical runtime field supports a generated RM script.",
            code="rm_script_unavailable",
        )

    async def simulate_offer(
        self,
        twin_id: uuid.UUID,
        payload: SimulateOfferIn,
    ) -> SimulateOfferOut:
        await self._customer_id(twin_id)
        emi, risk = simulate_offer(payload.amount)
        return SimulateOfferOut(
            amount=int(payload.amount),
            emi=emi,
            risk=risk,
        )
