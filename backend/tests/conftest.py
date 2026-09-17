"""Shared pytest fixtures.

``client`` boots the real FastAPI app in-process via ASGI transport, so
API tests exercise middleware, exception handlers and routing exactly as
in production. The ``get_db`` dependency is overridden with a seeded
SQLite (aiosqlite) engine — the portable column variants in
``app.database.base`` make every table creatable without PostgreSQL.
"""

from __future__ import annotations

import os
import random
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

# Tests fire hundreds of requests in seconds; disable the limiter so suites
# never hit 429. Must be set before ``app.main`` builds the app.
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
# Keep the suite hermetic even though backend/.env carries real LLM
# credentials for local dev — tests must never make a live network call.
# LLM-dependent behavior (e.g. the executive-summary polish pass) is
# exercised by injecting a fake provider, not the real one.
os.environ["AI_PROVIDER"] = "rule"

import app.models  # noqa: F401,E402 — register every model on Base.metadata
import app.models.simulation  # noqa: F401,E402 — register on AiStateBase.metadata
import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from app.ai.simulation import causal_panel  # noqa: E402
from app.ai.simulation.models import (  # noqa: E402
    auto_sales_model,
    collections_model,
    credit_pricing_model,
    logistics_delay_model,
)
from app.core.cache import clear_read_cache  # noqa: E402
from app.database.ai_state_base import AiStateBase  # noqa: E402
from app.database.base import Base  # noqa: E402
from app.database.runtime_schema import runtime_metadata, runtime_tables  # noqa: E402
from app.database.session import get_db  # noqa: E402
from app.main import app  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_simulation_caches() -> None:
    """Auto Sales trains/caches in-process for the app's lifetime (§14 of the
    implementation plan); tests share one process, so each test needs a
    clean slate rather than silently reusing a previous test's model."""
    auto_sales_model.reset_cache_for_tests()
    causal_panel.reset_cache_for_tests()
    collections_model.reset_cache_for_tests()
    logistics_delay_model.reset_cache_for_tests()
    credit_pricing_model.reset_cache_for_tests()


@pytest_asyncio.fixture
async def test_engine() -> AsyncIterator[AsyncEngine]:
    """In-memory SQLite engine shared across all connections via StaticPool.

    ``AiStateBase`` tables are schema-qualified (``ai_state.*``) for
    PostgreSQL; SQLite has no schema support, so ``schema_translate_map``
    maps ``ai_state`` onto the default (unqualified) schema for this engine
    only — a standard SQLAlchemy pattern for testing schema-qualified models
    against SQLite, not a change to production DDL.
    """
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    ).execution_options(schema_translate_map={"ai_state": None})
    async with engine.begin() as connection:
        # ``runtime_metadata`` first: several legacy ``Base`` models share a
        # table name with a runtime-schema table (e.g. ``dealers``,
        # ``bookings``) but define different columns. ``create_all`` skips a
        # name that already exists, so creating the runtime shape first
        # matches what real Postgres actually has — the legacy shape was
        # never migrated there either (see app/database/runtime_schema.py).
        await connection.run_sync(runtime_metadata.create_all)
        await connection.run_sync(Base.metadata.create_all)
        await connection.run_sync(AiStateBase.metadata.create_all)
    yield engine
    await engine.dispose()


try:  # pragma: no cover - import shape depends on the data-layer generation
    from app.database.seed import seed_database  # noqa: E402
except ModuleNotFoundError:  # pragma: no cover
    # The presentation-oriented seed module was deliberately removed when the
    # runtime moved to generated synthetic records; keeping collection working
    # lets the live-pipeline suites run. Suites that still assume the old mock
    # rows fail loudly on empty tables instead of hiding behind a collect error.
    seed_database = None  # type: ignore[assignment]


@pytest_asyncio.fixture
async def db_session(test_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """Session over a freshly seeded test database."""
    clear_read_cache()  # never serve a previous test's cached reads
    factory = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
    if seed_database is not None:
        async with factory() as session:
            await seed_database(session)
    async with factory() as session:
        yield session


# --- Auto Sales funnel seed --------------------------------------------------
#
# Shared by every test that needs a successful ``auto-sales/run`` (Phase 2
# trains real models from the leads -> bookings -> cancellations funnel, so
# an empty runtime schema now correctly 422s — see
# tests/api/test_auto_sales_simulation.py). Labels are sampled
# probabilistically (never a hard threshold) so the fitted logistic
# regression sees real noise instead of hitting perfect separation, and the
# 60-day spread gives the causal-evidence panel enough daily observations.

AUTO_SALES_REGION = "West"
AUTO_SALES_MODEL = "XUV700"
AUTO_SALES_LEAD_COUNT = 320
_AUTO_SALES_SEED_START = datetime(2026, 1, 1, tzinfo=UTC)


def _auto_sales_seed_rows(rng: random.Random) -> tuple[list[dict], list[dict], list[dict], list[dict], list[dict]]:
    leads, test_drives, followups, bookings, cancellations = [], [], [], [], []
    for index in range(AUTO_SALES_LEAD_COUNT):
        lead_id = f"seed-lead-{index}"
        created_at = _AUTO_SALES_SEED_START + timedelta(days=index % 60, hours=rng.uniform(0, 23))
        engagement = rng.uniform(0.05, 0.99)
        budget_fit = rng.uniform(0.05, 0.99)
        leads.append(
            {
                "lead_id": lead_id,
                "customer_id": f"seed-cust-{index}",
                "customer_lead_number": 1,
                "dealer_id": "seed-dealer-1",
                "dealer_name": "Seed Dealer",
                "region_id": "seed-region-1",
                "region_name": AUTO_SALES_REGION,
                "city_id": "seed-city-1",
                "city_name": "Mumbai",
                "vehicle_model_id": "seed-model-1",
                "vehicle_model_name": AUTO_SALES_MODEL,
                "source_channel": "DIGITAL",
                "budget_fit": budget_fit,
                "engagement_score": engagement,
                "urgency_score": rng.uniform(0.05, 0.99),
                "model_interest_score": rng.uniform(0.05, 0.99),
                "source_quality": rng.uniform(0.05, 0.99),
                "latent_purchase_intent": rng.uniform(0, 1),
                "lead_created_at": created_at,
                "data_origin": "TEST_SEED",
                "generator_version": "test",
            }
        )

        completed_test_drive = rng.random() < (0.3 + 0.4 * engagement)
        within_sla = rng.random() < 0.6
        if rng.random() < 0.8:
            test_drives.append(
                {
                    "test_drive_id": f"seed-td-{index}",
                    "lead_id": lead_id,
                    "customer_id": f"seed-cust-{index}",
                    "dealer_id": "seed-dealer-1",
                    "dealer_name": "Seed Dealer",
                    "region_id": "seed-region-1",
                    "region_name": AUTO_SALES_REGION,
                    "city_id": "seed-city-1",
                    "city_name": "Mumbai",
                    "vehicle_model_id": "seed-model-1",
                    "vehicle_model_name": AUTO_SALES_MODEL,
                    "latent_purchase_intent": rng.uniform(0, 1),
                    "request_probability": rng.uniform(0, 1),
                    "followup_attempt_count": 1,
                    "completed_followup_count": 1,
                    "responded_followup_count": 1,
                    "any_within_sla_followup": within_sla,
                    "requested_at": created_at,
                    "scheduled_at": created_at + timedelta(days=1),
                    "wait_hours": rng.uniform(1, 48),
                    "reminder_sent": True,
                    "high_intent": rng.random() < 0.5,
                    "long_wait": rng.random() < 0.2,
                    "completion_probability": rng.uniform(0, 1),
                    "status": "COMPLETED" if completed_test_drive else "NO_SHOW",
                    "completed": completed_test_drive,
                    "data_origin": "TEST_SEED",
                    "generator_version": "test",
                }
            )

        followup_completed = rng.random() < 0.7
        followups.append(
            {
                "followup_id": f"seed-fu-{index}",
                "lead_id": lead_id,
                "customer_id": f"seed-cust-{index}",
                "dealer_id": "seed-dealer-1",
                "dealer_name": "Seed Dealer",
                "region_id": "seed-region-1",
                "region_name": AUTO_SALES_REGION,
                "city_id": "seed-city-1",
                "city_name": "Mumbai",
                "vehicle_model_id": "seed-model-1",
                "vehicle_model_name": AUTO_SALES_MODEL,
                "attempt_number": 1,
                "channel": "CALL",
                "scheduled_at": created_at,
                "completed": followup_completed,
                "dealer_sla_hours": 24,
                "within_sla": rng.random() < 0.65,
                "customer_responded": rng.random() < 0.5,
                "followup_status": "DONE" if followup_completed else "MISSED",
                "data_origin": "TEST_SEED",
                "generator_version": "test",
            }
        )

        booking_score = 0.15 + 0.35 * engagement + 0.15 * budget_fit + (0.15 if completed_test_drive else 0)
        if rng.random() < min(0.9, booking_score):
            finance_assisted = rng.random() < 0.6
            finance_preapproval = finance_assisted and rng.random() < 0.7
            good_followup = followup_completed and rng.random() < 0.8
            long_wait = rng.random() < 0.2
            booking_timestamp = created_at + timedelta(days=rng.uniform(1, 10))
            bookings.append(
                {
                    "booking_id": f"seed-bk-{index}",
                    "lead_id": lead_id,
                    "customer_id": f"seed-cust-{index}",
                    "test_drive_id": f"seed-td-{index}" if completed_test_drive else None,
                    "dealer_id": "seed-dealer-1",
                    "dealer_name": "Seed Dealer",
                    "region_id": "seed-region-1",
                    "region_name": AUTO_SALES_REGION,
                    "city_id": "seed-city-1",
                    "city_name": "Mumbai",
                    "vehicle_model_id": "seed-model-1",
                    "vehicle_model_name": AUTO_SALES_MODEL,
                    "vehicle_base_price_inr": 1_400_000,
                    "source_channel": "DIGITAL",
                    "latent_purchase_intent": rng.uniform(0, 1),
                    "completed_test_drive": completed_test_drive,
                    "good_followup": good_followup,
                    "finance_assisted": finance_assisted,
                    "finance_preapproval_signal": finance_preapproval,
                    "exchange_assisted": rng.random() < 0.3,
                    "long_test_drive_wait": long_wait,
                    "booking_probability": rng.uniform(0, 1),
                    "booking_amount_inr": 1_400_000,
                    "booking_timestamp": booking_timestamp,
                    "promised_delivery_date": booking_timestamp + timedelta(days=30),
                    "booking_status": "ACTIVE",
                    "data_origin": "TEST_SEED",
                    "generator_version": "test",
                }
            )

            cancel_score = 0.35 - 0.2 * (1 if good_followup else 0) - 0.15 * (1 if finance_preapproval else 0)
            if rng.random() < max(0.02, cancel_score):
                cancelled_at = booking_timestamp + timedelta(days=rng.uniform(1, 15))
                cancellations.append(
                    {
                        "cancellation_id": f"seed-cx-{index}",
                        "booking_id": f"seed-bk-{index}",
                        "lead_id": lead_id,
                        "customer_id": f"seed-cust-{index}",
                        "finance_application_id": None,
                        "finance_status": None,
                        "finance_risk_band": None,
                        "finance_approval_tat_hours": None,
                        "dealer_id": "seed-dealer-1",
                        "dealer_name": "Seed Dealer",
                        "region_id": "seed-region-1",
                        "region_name": AUTO_SALES_REGION,
                        "city_id": "seed-city-1",
                        "city_name": "Mumbai",
                        "vehicle_model_id": "seed-model-1",
                        "vehicle_model_name": AUTO_SALES_MODEL,
                        "good_followup": good_followup,
                        "long_test_drive_wait": long_wait,
                        "promised_delivery_wait_days": rng.uniform(1, 30),
                        "cancellation_probability": rng.uniform(0, 1),
                        "cancellation_reason": "CUSTOMER_CHANGE",
                        "cancelled_at": cancelled_at,
                        "booking_amount_inr": 1_400_000,
                        "refund_amount_inr": 50_000,
                        "retained_amount_inr": 0,
                        "cancellation_status": "COMPLETED",
                        "data_origin": "TEST_SEED",
                        "generator_version": "test",
                    }
                )
    return leads, test_drives, followups, bookings, cancellations


@pytest_asyncio.fixture
async def auto_sales_funnel(db_session: AsyncSession) -> None:
    """Seed a small, noisy but real leads -> bookings -> cancellations funnel."""
    rng = random.Random(20260916)
    leads, test_drives, followups, bookings, cancellations = _auto_sales_seed_rows(rng)
    await db_session.execute(runtime_tables["leads"].insert(), leads)
    await db_session.execute(runtime_tables["test_drives"].insert(), test_drives)
    await db_session.execute(runtime_tables["followups"].insert(), followups)
    await db_session.execute(runtime_tables["bookings"].insert(), bookings)
    if cancellations:
        await db_session.execute(runtime_tables["cancellations"].insert(), cancellations)
    await db_session.commit()


# --- Dealer Allocation seed --------------------------------------------------
#
# Real dealers with varying capacity/region, real allocation demand share,
# and real delivery reliability (delayed rate + transit days) so the LP
# optimizer (app/ai/simulation/optimizers/dealer_allocation_lp.py) has
# genuine per-dealer variation to distinguish, not a uniform tie.

DEALER_ALLOCATION_DEALER_COUNT = 10


def _dealer_allocation_seed_rows(
    rng: random.Random,
) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    regions = ["West", "North", "South", "East"]
    dealers, allocations, deliveries, bookings = [], [], [], []
    start = datetime(2026, 1, 1, tzinfo=UTC)
    for index in range(DEALER_ALLOCATION_DEALER_COUNT):
        dealer_id = f"seed-dealer-{index}"
        region = regions[index % len(regions)]
        capacity = rng.randint(60, 140)
        dealers.append(
            {
                "dealer_id": dealer_id,
                "dealer_name": f"Seed Dealer {index}",
                "city_id": "seed-city-1",
                "city_name": "Mumbai",
                "region_id": f"seed-region-{region}",
                "region_name": region,
                "dealer_tier": "TIER_1",
                "monthly_lead_capacity": capacity * 3,
                "monthly_test_drive_capacity": capacity * 2,
                "monthly_booking_capacity": capacity,
                "sales_consultants": 5,
                "service_bays": 3,
                "followup_sla_hours": 24,
                "active": True,
                "data_origin": "TEST_SEED",
                "generator_version": "test",
            }
        )
        requested_total = rng.randint(20, 100)
        for j in range(3):
            allocations.append(
                {
                    "allocation_id": f"seed-alloc-{index}-{j}",
                    "booking_id": f"seed-dabk-{index}-{j}",
                    "lead_id": f"seed-dalead-{index}-{j}",
                    "customer_id": f"seed-dacust-{index}-{j}",
                    "dealer_id": dealer_id,
                    "dealer_name": f"Seed Dealer {index}",
                    "region_id": f"seed-region-{region}",
                    "region_name": region,
                    "city_id": "seed-city-1",
                    "city_name": "Mumbai",
                    "vehicle_model_id": "seed-model-1",
                    "vehicle_model_name": "XUV700",
                    "vehicle_id": f"seed-veh-{index}-{j}",
                    "production_batch_id": "seed-batch-1",
                    "plant_id": "seed-plant-1",
                    "plant_name": "Seed Plant",
                    "production_line_id": "seed-line-1",
                    "production_line_name": "Seed Line",
                    "representative_machine_id": "seed-machine-1",
                    "representative_machine_name": "Seed Machine",
                    "variant": "STD",
                    "primary_supplier_id": "seed-supplier-1",
                    "primary_supplier_name": "Seed Supplier",
                    "primary_supplier_lot_id": "seed-lot-1",
                    "supplier_lot_quality_score": 0.9,
                    "production_quality_score": 0.9,
                    "allocation_date": start + timedelta(days=index, hours=j),
                    "requested_units": requested_total // 3,
                    "allocated_units": requested_total // 3,
                    "waiting_list": 0,
                    "dealer_capacity": capacity,
                    "dealer_capacity_source": "TEST_SEED",
                    "regional_demand_index": 0.5,
                    "allocation_priority_score": 0.5,
                    "allocation_priority": "MEDIUM",
                    "inventory_before": 10,
                    "inventory_after": 5,
                    "production_batch_inventory_before": 100,
                    "production_batch_inventory_after": 95,
                    "allocation_wait_hours": 20.0,
                    "allocation_status": "COMPLETED",
                    "data_origin": "TEST_SEED",
                    "generator_version": "test",
                }
            )
        delayed_rate = rng.uniform(0.1, 0.8)
        avg_transit_days = rng.uniform(3.0, 10.0)
        for j in range(4):
            delayed = rng.random() < delayed_rate
            transit_days = max(1.0, avg_transit_days + rng.uniform(-1, 1))
            booking_ts = start + timedelta(days=index, hours=j)
            deliveries.append(
                {
                    "delivery_id": f"seed-deliv-{index}-{j}",
                    "allocation_id": f"seed-alloc-{index}-{j % 3}",
                    "booking_id": f"seed-dabk-{index}-{j % 3}",
                    "lead_id": f"seed-dalead-{index}-{j % 3}",
                    "customer_id": f"seed-dacust-{index}-{j % 3}",
                    "vehicle_id": f"seed-veh-{index}-{j}",
                    "vehicle_model_id": "seed-model-1",
                    "vehicle_model_name": "XUV700",
                    "variant": "STD",
                    "dealer_id": dealer_id,
                    "dealer_name": f"Seed Dealer {index}",
                    "region_id": f"seed-region-{region}",
                    "region_name": region,
                    "city_id": "seed-city-1",
                    "city_name": "Mumbai",
                    "production_batch_id": "seed-batch-1",
                    "plant_id": "seed-plant-1",
                    "plant_name": "Seed Plant",
                    "production_line_id": "seed-line-1",
                    "production_line_name": "Seed Line",
                    "representative_machine_id": "seed-machine-1",
                    "representative_machine_name": "Seed Machine",
                    "primary_supplier_id": "seed-supplier-1",
                    "primary_supplier_name": "Seed Supplier",
                    "primary_supplier_lot_id": "seed-lot-1",
                    "supplier_lot_quality_score": 0.9,
                    "production_quality_score": 0.9,
                    "booking_timestamp": booking_ts,
                    "allocation_date": booking_ts,
                    "promised_delivery_date": booking_ts + timedelta(days=7),
                    "dispatch_at": booking_ts + timedelta(days=1),
                    "physical_ready_date": booking_ts,
                    "projected_delivery_date": booking_ts + timedelta(days=7),
                    "actual_delivery_date": booking_ts + timedelta(days=transit_days),
                    "dispatch_delay_hours": 2.0,
                    "base_transit_days": 5.0,
                    "transport_disruption": delayed,
                    "disruption_days": 1.0 if delayed else 0.0,
                    "total_transit_days": transit_days,
                    "regional_demand_index": 0.5,
                    "allocation_priority": "MEDIUM",
                    "allocation_wait_hours": 20.0,
                    "demand_pressure": False,
                    "quality_hold": False,
                    "normal_handover_delay": False,
                    "delivery_variance_days": transit_days - 5.0,
                    "delay_days": max(0.0, transit_days - 5.0),
                    "early_days": max(0.0, 5.0 - transit_days),
                    "delayed": delayed,
                    "delay_reason": "TRANSPORT" if delayed else "NONE",
                    "customer_handover_completed": True,
                    "handover_score": 0.8,
                    "delivery_status": "DELIVERED",
                    "data_origin": "TEST_SEED",
                    "generator_version": "test",
                }
            )
        bookings.append(
            {
                "booking_id": f"seed-dabk-{index}-0",
                "lead_id": f"seed-dalead-{index}-0",
                "customer_id": f"seed-dacust-{index}-0",
                "test_drive_id": None,
                "dealer_id": dealer_id,
                "dealer_name": f"Seed Dealer {index}",
                "region_id": f"seed-region-{region}",
                "region_name": region,
                "city_id": "seed-city-1",
                "city_name": "Mumbai",
                "vehicle_model_id": "seed-model-1",
                "vehicle_model_name": "XUV700",
                "vehicle_base_price_inr": 1_800_000,
                "source_channel": "DIGITAL",
                "latent_purchase_intent": 0.5,
                "completed_test_drive": True,
                "good_followup": True,
                "finance_assisted": False,
                "finance_preapproval_signal": False,
                "exchange_assisted": False,
                "long_test_drive_wait": False,
                "booking_probability": 0.5,
                "booking_amount_inr": 50_000,
                "booking_timestamp": start + timedelta(days=index),
                "promised_delivery_date": start + timedelta(days=index + 30),
                "booking_status": "ACTIVE",
                "data_origin": "TEST_SEED",
                "generator_version": "test",
            }
        )
    return dealers, allocations, deliveries, bookings


@pytest_asyncio.fixture
async def dealer_allocation_seed(db_session: AsyncSession) -> None:
    """Seed real-shaped dealers/allocations/deliveries/bookings for the LP optimizer."""
    rng = random.Random(20260917)
    dealers, allocations, deliveries, bookings = _dealer_allocation_seed_rows(rng)
    await db_session.execute(runtime_tables["dealers"].insert(), dealers)
    await db_session.execute(runtime_tables["allocations"].insert(), allocations)
    await db_session.execute(runtime_tables["deliveries"].insert(), deliveries)
    await db_session.execute(runtime_tables["bookings"].insert(), bookings)
    await db_session.commit()


# --- Collections seed ---------------------------------------------------------
#
# Real collection cases/interactions/loan accounts with probabilistic (not
# hard-threshold) outcomes so the recovery model sees genuine noise, and
# real per-loan variation (principal/interest/DSR/secured) for the
# roll-forward model.

COLLECTIONS_CASE_COUNT = 120
_CHANNEL_REAL_VALUES = ["SMS", "WHATSAPP", "EMAIL", "CALL", "FIELD_VISIT"]
_OFFER_REAL_VALUES = ["NONE", "PAYMENT_REMINDER", "PARTIAL_PAYMENT_PLAN", "REPAYMENT_PLAN_DISCUSSION"]


def _collections_seed_rows(rng: random.Random) -> tuple[list[dict], list[dict], list[dict]]:
    cases, interactions, loans = [], [], []
    start = datetime(2026, 1, 1, tzinfo=UTC)
    for index in range(COLLECTIONS_CASE_COUNT):
        loan_id = f"seed-loan-{index}"
        secured = rng.random() < 0.4
        principal = rng.uniform(200_000, 1_500_000)
        interest_rate = rng.uniform(9.0, 16.0)
        dsr = rng.uniform(0.2, 0.7)
        loans.append(
            {
                "loan_account_id": loan_id,
                "finance_customer_id": f"seed-fcust-{index}",
                "customer_loan_sequence": 1,
                "region_id": "seed-region-1",
                "region_name": "West",
                "city_id": "seed-city-1",
                "city_name": "Mumbai",
                "finance_product_id": "seed-product-1",
                "product_code": "AUTO-LOAN",
                "product_name": "Auto Loan",
                "product_category": "AUTO",
                "target_segment": "RETAIL",
                "secured": secured,
                "application_at": start,
                "disbursed_at": start,
                "scheduled_maturity_at": start + timedelta(days=365 * 5),
                "principal_inr": principal,
                "interest_rate_pct": interest_rate,
                "tenure_months": 60,
                "emi_amount_inr": principal / 60,
                "debt_service_ratio_at_origination": dsr,
                "data_origin": "TEST_SEED",
                "generator_version": "test",
            }
        )

        # Better loans (secured, lower DSR) are more likely to resolve —
        # real signal for the roll-forward model, sampled with noise.
        resolve_score = 0.3 + (0.3 if secured else 0.0) + (0.5 - dsr) * 0.4
        resolved = rng.random() < max(0.05, min(0.9, resolve_score))
        case_id = f"seed-case-{index}"
        dpd = rng.randint(1, 180)
        cases.append(
            {
                "collection_case_id": case_id,
                "loan_account_id": loan_id,
                "finance_customer_id": f"seed-fcust-{index}",
                "loan_case_sequence": 1,
                "region_id": "seed-region-1",
                "region_name": "West",
                "city_id": "seed-city-1",
                "city_name": "Mumbai",
                "finance_product_id": "seed-product-1",
                "product_code": "AUTO-LOAN",
                "product_name": "Auto Loan",
                "product_category": "AUTO",
                "case_created_at": start + timedelta(days=index % 60),
                "carried_into_generation_window": False,
                "case_trigger_source": "DPD_THRESHOLD",
                "trigger_payment_event_id": f"seed-pay-{index}",
                "case_trigger_dpd": 15,
                "observed_dpd_at_trigger_event": 15,
                "dpd_at_case_creation": 15,
                "arrears_at_trigger_event_inr": 5000.0,
                "priority_at_creation": "LOW",
                "peak_observed_dpd": dpd,
                "peak_observed_arrears_inr": dpd * 150.0,
                "case_status": "RESOLVED" if resolved else "OPEN",
                "current_dpd": 0 if resolved else dpd,
                "current_arrears_inr": 0.0 if resolved else dpd * 150.0,
                "resolved_at": (start + timedelta(days=index % 60 + 30)) if resolved else None,
                "resolution_payment_event_id": f"seed-pay-{index}" if resolved else None,
                "resolution_type": "PAYMENT_CURE" if resolved else None,
                "data_origin": "TEST_SEED",
                "generator_version": "test",
            }
        )

        for j in range(3):
            channel = _CHANNEL_REAL_VALUES[rng.randrange(len(_CHANNEL_REAL_VALUES))]
            offer = _OFFER_REAL_VALUES[rng.randrange(len(_OFFER_REAL_VALUES))]
            interaction_dpd = max(1, dpd - j * 10)
            # Real-shaped signal: field visits and repayment-plan
            # discussions recover somewhat better; higher DPD recovers worse.
            recovery_score = 0.25
            recovery_score += 0.08 if channel == "FIELD_VISIT" else 0.0
            recovery_score += 0.1 if offer == "REPAYMENT_PLAN_DISCUSSION" else 0.0
            recovery_score += 0.12 if offer == "PAYMENT_REMINDER" else 0.0
            recovery_score -= min(0.15, interaction_dpd / 1000)
            paid = rng.random() < max(0.03, min(0.85, recovery_score))
            interactions.append(
                {
                    "collection_interaction_id": f"seed-int-{index}-{j}",
                    "collection_case_id": case_id,
                    "loan_account_id": loan_id,
                    "finance_customer_id": f"seed-fcust-{index}",
                    "interaction_sequence": j + 1,
                    "interaction_at": start + timedelta(days=index % 60, hours=j),
                    "region_id": "seed-region-1",
                    "region_name": "West",
                    "city_id": "seed-city-1",
                    "city_name": "Mumbai",
                    "finance_product_id": "seed-product-1",
                    "product_code": "AUTO-LOAN",
                    "product_name": "Auto Loan",
                    "product_category": "AUTO",
                    "channel": channel,
                    "field_visit_flag": channel == "FIELD_VISIT",
                    "contact_success": True,
                    "dpd_at_interaction": interaction_dpd,
                    "arrears_at_interaction_inr": interaction_dpd * 150.0,
                    "outstanding_principal_at_interaction_inr": principal * 0.6,
                    "offer_type": offer,
                    "customer_response": "ACKNOWLEDGED",
                    "promise_to_pay": paid,
                    "payment_after_contact": paid,
                    "payment_after_contact_amount_inr": (interaction_dpd * 150.0) if paid else 0.0,
                    "data_origin": "TEST_SEED",
                    "generator_version": "test",
                }
            )
    return cases, interactions, loans


@pytest_asyncio.fixture
async def collections_seed(db_session: AsyncSession) -> None:
    """Seed real-shaped collection cases/interactions/loan accounts."""
    rng = random.Random(20260918)
    cases, interactions, loans = _collections_seed_rows(rng)
    await db_session.execute(runtime_tables["loan_accounts"].insert(), loans)
    await db_session.execute(runtime_tables["collection_cases"].insert(), cases)
    await db_session.execute(runtime_tables["collection_interactions"].insert(), interactions)
    await db_session.commit()


LOGISTICS_SHIPMENTS_PER_ROUTE = 150
LOGISTICS_PRIORITIES = ["LOW", "NORMAL", "HIGH", "CRITICAL"]
# Two real routes on the SAME West -> North corridor (different origin
# warehouses) so the reroute-optimizer's alternative-route sweep has
# something real to compare against.
LOGISTICS_ROUTES = [
    {
        "route_id": "seed-route-a",
        "origin_warehouse_id": "seed-wh-mumbai",
        "origin_warehouse_name": "Mumbai DC",
        "origin_city_id": "seed-city-mumbai",
        "origin_city_name": "Mumbai",
        "origin_region_id": "seed-region-west",
        "origin_region_name": "West",
        "destination_warehouse_id": "seed-wh-delhi",
        "destination_warehouse_name": "Delhi DC",
        "destination_city_id": "seed-city-delhi",
        "destination_city_name": "Delhi",
        "destination_region_id": "seed-region-north",
        "destination_region_name": "North",
        "distance_km": 1350.0,
        "typical_transit_hours": 24.0,
        "sla_hours": 36,
        "baseline_cost_inr": 85_000.0,
        "baseline_risk_score": 0.3,
    },
    {
        "route_id": "seed-route-b",
        "origin_warehouse_id": "seed-wh-pune",
        "origin_warehouse_name": "Pune DC",
        "origin_city_id": "seed-city-pune",
        "origin_city_name": "Pune",
        "origin_region_id": "seed-region-west",
        "origin_region_name": "West",
        "destination_warehouse_id": "seed-wh-delhi",
        "destination_warehouse_name": "Delhi DC",
        "destination_city_id": "seed-city-delhi",
        "destination_city_name": "Delhi",
        "destination_region_id": "seed-region-north",
        "destination_region_name": "North",
        "distance_km": 1420.0,
        "typical_transit_hours": 26.0,
        "sla_hours": 38,
        "baseline_cost_inr": 90_000.0,
        "baseline_risk_score": 0.34,
    },
]


def _logistics_delay_seed_rows(
    rng: random.Random,
) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    warehouse_ids = {
        (route["origin_warehouse_id"], route["origin_warehouse_name"], route["origin_city_id"], route["origin_city_name"], route["origin_region_id"], route["origin_region_name"])
        for route in LOGISTICS_ROUTES
    } | {
        (route["destination_warehouse_id"], route["destination_warehouse_name"], route["destination_city_id"], route["destination_city_name"], route["destination_region_id"], route["destination_region_name"])
        for route in LOGISTICS_ROUTES
    }
    warehouses = [
        {
            "warehouse_id": wid,
            "warehouse_name": wname,
            "city_id": city_id,
            "city_name": city_name,
            "region_id": region_id,
            "region_name": region_name,
            "warehouse_type": "DISTRIBUTION_CENTER",
            "storage_capacity_units": 50_000,
            "baseline_utilization_pct": 0.7,
            "daily_throughput_capacity": 2_000,
            "active": True,
            "data_origin": "TEST_SEED",
            "generator_version": "test",
        }
        for wid, wname, city_id, city_name, region_id, region_name in warehouse_ids
    ]
    routes = [
        {
            **route,
            "route_type": "INTER_REGION",
            "transport_mode": "ROAD",
            "active": True,
            "data_origin": "TEST_SEED",
            "generator_version": "test",
        }
        for route in LOGISTICS_ROUTES
    ]

    # Route B is a systematically safer corridor (same scenario inputs
    # yield a lower delay/breach chance) so the reroute optimizer's
    # alternative-route sweep has a genuine, learnable signal to act on —
    # not just noise around an identical distribution for both routes.
    risk_multiplier = {"seed-route-a": 1.0, "seed-route-b": 0.5}

    start = datetime(2026, 1, 1, tzinfo=UTC)
    shipments, warehouse_events = [], []
    index = 0
    for route in LOGISTICS_ROUTES:
        multiplier = risk_multiplier[route["route_id"]]
        for i in range(LOGISTICS_SHIPMENTS_PER_ROUTE):
            utilization = rng.uniform(0.4, 0.95)
            dock_wait = rng.uniform(0, 90)
            weather = rng.random() < 0.3
            vehicle_bad = rng.random() < 0.15
            priority = LOGISTICS_PRIORITIES[index % len(LOGISTICS_PRIORITIES)]

            # Real-shaped signal: higher warehouse utilization/dock wait,
            # weather disruption, and vehicle breakdown all raise the
            # chance of a delay; breach is a rarer subset of delay.
            delay_score = multiplier * (
                0.1 + 0.4 * utilization + 0.002 * dock_wait + (0.25 if weather else 0.0) + (0.2 if vehicle_bad else 0.0)
            )
            any_delay = rng.random() < max(0.05, min(0.95, delay_score))
            delay_minutes = rng.uniform(20, 300) if any_delay else 0.0
            breach_score = multiplier * (
                0.05 + 0.3 * utilization + (0.15 if weather else 0.0) + (0.15 if vehicle_bad else 0.0)
            )
            sla_breach = any_delay and rng.random() < max(0.02, min(0.7, breach_score))

            dispatch_time = start + timedelta(hours=index * 3)
            typical_hours = route["typical_transit_hours"]
            actual_hours = typical_hours + delay_minutes / 60
            shipment_id = f"seed-shipment-{index}"
            shipments.append(
                {
                    "shipment_id": shipment_id,
                    "route_id": route["route_id"],
                    "route_type": "INTER_REGION",
                    "transport_mode": "ROAD",
                    "origin_warehouse_id": route["origin_warehouse_id"],
                    "origin_warehouse_name": route["origin_warehouse_name"],
                    "origin_city_id": route["origin_city_id"],
                    "origin_city_name": route["origin_city_name"],
                    "origin_region_id": route["origin_region_id"],
                    "origin_region_name": route["origin_region_name"],
                    "destination_warehouse_id": route["destination_warehouse_id"],
                    "destination_warehouse_name": route["destination_warehouse_name"],
                    "destination_city_id": route["destination_city_id"],
                    "destination_city_name": route["destination_city_name"],
                    "destination_region_id": route["destination_region_id"],
                    "destination_region_name": route["destination_region_name"],
                    "distance_km": route["distance_km"],
                    "typical_transit_hours": typical_hours,
                    "sla_hours": float(route["sla_hours"]),
                    "baseline_cost_inr": route["baseline_cost_inr"],
                    "vehicle_id": f"seed-vehicle-{index % 20}",
                    "units": 10,
                    "priority": priority,
                    "desired_dispatch_time": dispatch_time,
                    "dispatch_time": dispatch_time,
                    "expected_arrival": dispatch_time + timedelta(hours=typical_hours),
                    "sla_deadline": dispatch_time + timedelta(hours=route["sla_hours"]),
                    "actual_arrival": dispatch_time + timedelta(hours=actual_hours),
                    "weather_disruption": weather,
                    "vehicle_breakdown": vehicle_bad,
                    "warehouse_delay": dock_wait > 45,
                    "port_delay": False,
                    "customs_delay": False,
                    "dispatch_delay_minutes": 0.0,
                    "actual_transit_hours": actual_hours,
                    "arrival_variance_minutes": delay_minutes,
                    "delay_minutes": delay_minutes,
                    "early_arrival_minutes": 0.0,
                    "sla_breach": sla_breach,
                    "shipment_status": "DELIVERED",
                    "data_origin": "TEST_SEED",
                    "generator_version": "test",
                }
            )
            warehouse_events.append(
                {
                    "warehouse_event_id": f"seed-wh-event-{index}",
                    "shipment_id": shipment_id,
                    "event_sequence": 1,
                    "route_id": route["route_id"],
                    "vehicle_id": f"seed-vehicle-{index % 20}",
                    "event_type": "DISPATCH",
                    "direction": "OUTBOUND",
                    "warehouse_id": route["origin_warehouse_id"],
                    "warehouse_name": route["origin_warehouse_name"],
                    "city_id": route["origin_city_id"],
                    "city_name": route["origin_city_name"],
                    "region_id": route["origin_region_id"],
                    "region_name": route["origin_region_name"],
                    "warehouse_type": "DISTRIBUTION_CENTER",
                    "event_at": dispatch_time,
                    "units_moved": 10,
                    "inventory_delta_units": -10,
                    "priority": priority,
                    "dock_id": f"seed-dock-{index % 5}",
                    "warehouse_utilization_pct": utilization,
                    "dock_queue_depth": int(dock_wait // 10),
                    "dock_wait_minutes": dock_wait,
                    "handling_minutes": 30.0,
                    "picking_delay_minutes": 0.0,
                    "putaway_delay_minutes": 0.0,
                    "congestion_flag": dock_wait > 45,
                    "event_status": "COMPLETED",
                    "data_origin": "TEST_SEED",
                    "generator_version": "test",
                }
            )
            index += 1
    return warehouses, routes, shipments, warehouse_events


@pytest_asyncio.fixture
async def logistics_delay_seed(db_session: AsyncSession) -> None:
    """Seed real-shaped warehouses/routes/shipments/warehouse_events."""
    rng = random.Random(20260916)
    warehouses, routes, shipments, warehouse_events = _logistics_delay_seed_rows(rng)
    await db_session.execute(runtime_tables["warehouses"].insert(), warehouses)
    await db_session.execute(runtime_tables["routes"].insert(), routes)
    await db_session.execute(runtime_tables["shipments"].insert(), shipments)
    await db_session.execute(runtime_tables["warehouse_events"].insert(), warehouse_events)
    await db_session.commit()


CREDIT_LISTING_COUNT = 150
_CREDIT_TYPE_REAL_VALUES = ["MIXED_CIRCULARITY", "RECYCLING_AVOIDANCE", "REUSE_AVOIDANCE"]


def _credit_pricing_seed_rows(rng: random.Random) -> tuple[list[dict], list[dict]]:
    listings, assessments = [], []
    start = datetime(2026, 1, 1, tzinfo=UTC)
    for index in range(CREDIT_LISTING_COUNT):
        assessment_id = f"seed-elv-{index}"
        credit_type = _CREDIT_TYPE_REAL_VALUES[index % len(_CREDIT_TYPE_REAL_VALUES)]
        traceability_score = rng.uniform(0.5, 0.95)
        document_completeness = rng.uniform(0.4, 0.95)
        buyer_demand_index = rng.uniform(0.2, 0.9)
        assessments.append(
            {
                "elv_assessment_id": assessment_id,
                "elv_vehicle_id": f"seed-vehicle-{index}",
                "vehicle_model_id": "seed-model-1",
                "model_name": "XUV700",
                "segment": "SUV",
                "city_id": "seed-city-1",
                "city_name": "Mumbai",
                "region_id": "seed-region-1",
                "region_name": "West",
                "assessment_at": start + timedelta(days=index % 60),
                "assessment_status": "COMPLETED",
                "source_channel": "RVSF",
                "manufacture_year": 2015,
                "vehicle_age_years": 10,
                "odometer_km": 120_000,
                "accident_history_count": 0,
                "major_accident_flag": False,
                "flood_exposure_flag": False,
                "condition_score": 0.7,
                "body_condition_score": 0.7,
                "chassis_integrity_score": 0.7,
                "powertrain_condition_score": 0.7,
                "interior_condition_score": 0.7,
                "engine_operable": True,
                "document_completeness": document_completeness,
                "document_status": "PARTIAL",
                "traceability_score": traceability_score,
                "traceability_status": "PARTIAL",
                "buyer_demand_index": buyer_demand_index,
                "estimated_vehicle_mass_kg": 1800.0,
                "assessed_reusable_parts_pct": 0.35,
                "assessed_recyclable_material_pct": 0.8,
                "battery_present": True,
                "tyre_set_present": True,
                "catalytic_converter_present": True,
                "hazardous_fluids_present": True,
                "data_origin": "TEST_SEED",
                "generator_version": "test",
            }
        )

        market_reference_price = rng.uniform(1400, 2500)
        # Real-shaped signal: higher traceability raises what sellers ask
        # relative to market reference; higher demand/traceability raise
        # buyer interest — mirrors the genuine correlations observed in
        # production (see the Phase 6 research: traceability_score/
        # buyer_demand_index both have real variance and plausibly drive
        # ask price and buyer_inquiry_count).
        seller_ask_price = market_reference_price * (0.92 + 0.2 * traceability_score + rng.uniform(-0.05, 0.05))
        dmrv_available_records = rng.choice([2, 3, 4])
        buyer_bid_count = rng.randint(0, 7)
        inquiry_score = 0.3 * buyer_demand_index + 0.25 * traceability_score + rng.uniform(0, 0.3)
        buyer_inquiry_count = max(0, min(10, round(inquiry_score * 10)))
        listings.append(
            {
                "carbon_credit_listing_id": f"seed-listing-{index}",
                "elv_assessment_id": assessment_id,
                "elv_vehicle_id": f"seed-vehicle-{index}",
                "vehicle_model_id": "seed-model-1",
                "model_name": "XUV700",
                "segment": "SUV",
                "rvsf_facility_id": "seed-rvsf-1",
                "rvsf_facility_name": "Mumbai RVSF",
                "city_id": "seed-city-1",
                "city_name": "Mumbai",
                "region_id": "seed-region-1",
                "region_name": "West",
                "credit_type": credit_type,
                "credit_unit": "TCO2E",
                "claim_basis": "AVOIDANCE",
                "claim_basis_version": "v1",
                "credit_vintage_start_at": start,
                "credit_vintage_end_at": start + timedelta(days=365),
                "listing_at": start + timedelta(days=index % 60),
                "listing_status": "OPEN",
                "seller_claimed_quantity_tco2e": 5.0,
                "minimum_trade_quantity_tco2e": 1.0,
                "market_reference_price_per_tco2e_inr": market_reference_price,
                "seller_ask_price_per_tco2e_inr": seller_ask_price,
                "buyer_inquiry_count": buyer_inquiry_count,
                "buyer_bid_count": buyer_bid_count,
                "highest_bid_price_per_tco2e_inr": (seller_ask_price * 0.95) if buyer_bid_count > 0 else None,
                "source_rvsf_job_count": 1,
                "source_rvsf_quality_pass_count": 1,
                "reusable_parts_mass_kg": 200.0,
                "recyclable_material_mass_kg": 400.0,
                "residual_waste_mass_kg": 50.0,
                "recovered_component_mass_kg": 100.0,
                "total_process_energy_kwh": 120.0,
                "total_process_water_liters": 300.0,
                "source_dmrv_record_count": 4,
                "dmrv_expected_records": 4,
                "dmrv_available_records": dmrv_available_records,
                "dmrv_missing_records": 4 - dmrv_available_records,
                "dmrv_source_reference_records": dmrv_available_records,
                "dmrv_attachment_records": dmrv_available_records,
                "dmrv_timestamp_verified_records": dmrv_available_records,
                "dmrv_signature_records": dmrv_available_records,
                "dmrv_operator_identity_records": dmrv_available_records,
                "dmrv_chain_of_custody_records": dmrv_available_records,
                "dmrv_calibration_records": dmrv_available_records,
                "data_origin": "TEST_SEED",
                "generator_version": "test",
            }
        )
    return listings, assessments


@pytest_asyncio.fixture
async def credit_pricing_seed(db_session: AsyncSession) -> None:
    """Seed real-shaped credit_listings/elv_assessments."""
    rng = random.Random(20260917)
    listings, assessments = _credit_pricing_seed_rows(rng)
    await db_session.execute(runtime_tables["elv_assessments"].insert(), assessments)
    await db_session.execute(runtime_tables["credit_listings"].insert(), listings)
    await db_session.commit()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    """Async HTTP client wired to the app with the test session injected."""

    async def override_get_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            yield ac
    finally:
        app.dependency_overrides.pop(get_db, None)
