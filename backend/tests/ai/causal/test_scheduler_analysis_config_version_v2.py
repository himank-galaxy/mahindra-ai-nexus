"""Regression tests for the CAUSAL_ANALYSIS_CONFIG_VERSION v1 -> v2 bump.

Context
-------
The persisted ``tau_min`` for LPCMCI with ``test_contemporaneous=True`` was
incorrectly recorded as 1 while the engine actually ran with tau_min=0 (see
test_lpcmci_profiling_logs.py for the fix in effective_tau_min /
_analysis_parameters / _configuration_parameters). Because the scheduler's
own tau_min resolution feeds ``_analysis_config_signature()`` too, scheduler
state persisted under the old, incorrect semantics must not fast-path reuse
against the corrected configuration -- CAUSAL_ANALYSIS_CONFIG_VERSION exists
exactly for this: bumping it forces every persisted scheduler-state row to
miss the fast path exactly once, deterministically converging back to fast
reuse afterward, using the identical mechanism already proven for the
PCMCI -> LPCMCI cutover (test_scheduler_analysis_config_cutover.py).

This file does not re-derive that mechanism; it verifies the version bump
itself is wired correctly and behaves as the same "changed config forces
one fresh service call, then reuse resumes" pattern.
"""

from __future__ import annotations

import uuid

import pytest
from app.ai.causal.manufacturing_filter import DEFAULT_MANUFACTURING_FILTER_CONFIG
from app.ai.causal.manufacturing_panel import DEFAULT_MANUFACTURING_PANEL_CONFIG
from app.ai.causal.telematics_filter import DEFAULT_TELEMATICS_FILTER_CONFIG
from app.ai.causal.telematics_panel import DEFAULT_TELEMATICS_PANEL_CONFIG
from app.models.causal_runtime_state import CausalSchedulerState
from app.scheduler import causal_scheduler
from app.scheduler.causal_scheduler import (
    CAUSAL_ANALYSIS_CONFIG_VERSION,
    _analysis_config_signature,
    _scheduler_reuse_decision,
)

DOMAINS = ("manufacturing", "telematics")

_PANEL_CONFIG = {
    "manufacturing": DEFAULT_MANUFACTURING_PANEL_CONFIG,
    "telematics": DEFAULT_TELEMATICS_PANEL_CONFIG,
}
_FILTER_CONFIG = {
    "manufacturing": DEFAULT_MANUFACTURING_FILTER_CONFIG,
    "telematics": DEFAULT_TELEMATICS_FILTER_CONFIG,
}


def _config_signature(
    domain: str,
    *,
    algorithm: str = "lpcmci",
    test_contemporaneous: bool = True,
    tau_max: int = 2,
    pc_alpha: float = 0.10,
) -> str:
    return _analysis_config_signature(
        domain=domain,
        algorithm=algorithm,
        test_contemporaneous=test_contemporaneous,
        tau_max=tau_max,
        pc_alpha=pc_alpha,
        algorithm_config=None,
        panel_config=_PANEL_CONFIG[domain],
        filter_config=_FILTER_CONFIG[domain],
    )


def _state(
    domain: str,
    *,
    source_signature: str = "source-1",
    analysis_config_signature: str | None,
    run_id: uuid.UUID | None = uuid.uuid4(),
) -> CausalSchedulerState:
    return CausalSchedulerState(
        domain=domain,
        status="READY",
        last_run_id=run_id,
        last_source_signature=source_signature,
        last_analysis_config_signature=analysis_config_signature,
    )


# ---------------------------------------------------------------------------
# (a) The version constant itself.
# ---------------------------------------------------------------------------


def test_a_config_version_is_v2() -> None:
    assert CAUSAL_ANALYSIS_CONFIG_VERSION == "v2"
    assert causal_scheduler.CAUSAL_ANALYSIS_CONFIG_VERSION == "v2"


# ---------------------------------------------------------------------------
# (b) v2 fingerprint differs from the historical v1 fingerprint for
# otherwise-identical inputs.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("domain", DOMAINS)
def test_b_v2_signature_differs_from_historical_v1_signature(
    domain: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Capture what the fingerprint would have been under v1 by temporarily
    # restoring the module constant to its pre-fix value, WITHOUT touching
    # any other input (same algorithm/tau_max/pc_alpha/panel/filter config).
    monkeypatch.setattr(causal_scheduler, "CAUSAL_ANALYSIS_CONFIG_VERSION", "v1")
    historical_v1_signature = _config_signature(domain)

    monkeypatch.setattr(causal_scheduler, "CAUSAL_ANALYSIS_CONFIG_VERSION", "v2")
    current_v2_signature = _config_signature(domain)

    assert historical_v1_signature != current_v2_signature


@pytest.mark.parametrize("domain", DOMAINS)
def test_b_a_state_persisted_under_v1_cannot_fast_path_reuse_under_v2(
    domain: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The concrete scenario the version bump exists to prevent: a scheduler
    # state row whose last_analysis_config_signature was computed while
    # CAUSAL_ANALYSIS_CONFIG_VERSION was still "v1" must not satisfy the
    # fast path once the running code has moved to "v2", even with an
    # otherwise byte-identical configuration and unchanged source.
    monkeypatch.setattr(causal_scheduler, "CAUSAL_ANALYSIS_CONFIG_VERSION", "v1")
    v1_persisted_signature = _config_signature(domain)
    state = _state(domain, source_signature="source-1", analysis_config_signature=v1_persisted_signature)

    monkeypatch.setattr(causal_scheduler, "CAUSAL_ANALYSIS_CONFIG_VERSION", "v2")
    v2_requested_signature = _config_signature(domain)

    routing = _scheduler_reuse_decision(
        force_refresh=False,
        state=state,
        source_signature="source-1",
        analysis_config_signature=v2_requested_signature,
    )

    assert routing.reuse is False
    assert routing.decision == "analysis_config_changed"


# ---------------------------------------------------------------------------
# (c) Deterministic under v2: identical source + identical v2 config.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("domain", DOMAINS)
def test_c_v2_signature_is_deterministic(domain: str) -> None:
    first = _config_signature(domain)
    second = _config_signature(domain)
    assert first == second
    # And it genuinely reflects the LIVE module constant, not a stale import.
    assert causal_scheduler.CAUSAL_ANALYSIS_CONFIG_VERSION == "v2"


# ---------------------------------------------------------------------------
# (d) Identical source + same v2 config -> fast path still works.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("domain", DOMAINS)
def test_d_identical_v2_source_and_config_takes_fast_path(domain: str) -> None:
    v2_signature = _config_signature(domain)
    state = _state(domain, source_signature="source-1", analysis_config_signature=v2_signature)

    routing = _scheduler_reuse_decision(
        force_refresh=False,
        state=state,
        source_signature="source-1",
        analysis_config_signature=v2_signature,
    )

    assert routing.reuse is True
    assert routing.decision == "source_signature_unchanged"


@pytest.mark.parametrize("domain", DOMAINS)
def test_d_fast_path_recovers_on_the_tick_after_the_version_bump(domain: str) -> None:
    # Simulates the real deployment sequence: tick 1 under v1 state forces
    # a service call under v2 (proven in (b)); imagine the service persists
    # a new run and update_scheduler_state() records the v2 signature.
    # Tick 2, requesting the identical v2 configuration again, must take
    # the fast path -- the version bump causes exactly one forced
    # reconciliation, not permanent cache invalidation.
    v2_signature = _config_signature(domain)
    reconciled_state = _state(domain, source_signature="source-1", analysis_config_signature=v2_signature)

    routing = _scheduler_reuse_decision(
        force_refresh=False,
        state=reconciled_state,
        source_signature="source-1",
        analysis_config_signature=v2_signature,
    )
    assert routing.reuse is True


# ---------------------------------------------------------------------------
# (e) Missing/old config signature forces the service path.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("domain", DOMAINS)
def test_e_missing_config_signature_forces_service_path(domain: str) -> None:
    v2_signature = _config_signature(domain)
    # A scheduler-state row that predates last_analysis_config_signature
    # entirely (NULL in the database) must never satisfy the fast path.
    state = _state(domain, source_signature="source-1", analysis_config_signature=None)

    routing = _scheduler_reuse_decision(
        force_refresh=False,
        state=state,
        source_signature="source-1",
        analysis_config_signature=v2_signature,
    )

    assert routing.reuse is False
    assert routing.decision == "analysis_config_changed"


@pytest.mark.parametrize("domain", DOMAINS)
def test_e_old_v1_config_signature_forces_service_path(domain: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(causal_scheduler, "CAUSAL_ANALYSIS_CONFIG_VERSION", "v1")
    old_signature = _config_signature(domain)
    state = _state(domain, source_signature="source-1", analysis_config_signature=old_signature)

    monkeypatch.setattr(causal_scheduler, "CAUSAL_ANALYSIS_CONFIG_VERSION", "v2")
    new_signature = _config_signature(domain)

    routing = _scheduler_reuse_decision(
        force_refresh=False,
        state=state,
        source_signature="source-1",
        analysis_config_signature=new_signature,
    )

    assert routing.reuse is False
    assert routing.decision == "analysis_config_changed"


# ---------------------------------------------------------------------------
# (f) Manufacturing and telematics share the same versioned mechanism.
# ---------------------------------------------------------------------------


def test_f_both_domains_use_the_same_versioned_fingerprint_mechanism(monkeypatch: pytest.MonkeyPatch) -> None:
    # Flipping the shared module constant must move BOTH domains'
    # signatures simultaneously -- proving there is exactly one version
    # knob, not two independently-versioned per-domain mechanisms that
    # could drift out of sync with each other.
    monkeypatch.setattr(causal_scheduler, "CAUSAL_ANALYSIS_CONFIG_VERSION", "v1")
    manufacturing_v1 = _config_signature("manufacturing")
    telematics_v1 = _config_signature("telematics")

    monkeypatch.setattr(causal_scheduler, "CAUSAL_ANALYSIS_CONFIG_VERSION", "v2")
    manufacturing_v2 = _config_signature("manufacturing")
    telematics_v2 = _config_signature("telematics")

    assert manufacturing_v1 != manufacturing_v2
    assert telematics_v1 != telematics_v2
    # And the two domains never collide with each other regardless of
    # version (domain is itself part of the fingerprinted payload).
    assert manufacturing_v1 != telematics_v1
    assert manufacturing_v2 != telematics_v2


def test_f_config_version_is_a_single_module_level_constant() -> None:
    # There is exactly one CAUSAL_ANALYSIS_CONFIG_VERSION definition that
    # both _run_manufacturing_job and _run_telematics_job's fingerprint
    # calls resolve through -- not a per-domain literal that could be
    # bumped for one domain and forgotten for the other.
    import inspect

    source = inspect.getsource(causal_scheduler)
    assert source.count('CAUSAL_ANALYSIS_CONFIG_VERSION = "v2"') == 1
