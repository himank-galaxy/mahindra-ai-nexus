"""Regression tests for the PCMCI -> LPCMCI scheduler cutover bug.

Bug recap
---------
The scheduler's fast-path reuse check compared ONLY the source-data
signature (``CausalSchedulerState.last_source_signature`` vs.
``plan.signature``). A deployment-time configuration change -- e.g.
flipping ``causal_algorithm`` from "pcmci" to "lpcmci" -- touches no source
data at all, so it was invisible to that check: whenever the source
happened not to have changed, the scheduler would emit ``causal_run_reused``
and return BEFORE ever calling ``ManufacturingCausalService``/
``TelematicsCausalService``.get_or_run(), so the service never got the
chance to compute a fresh LPCMCI run signature. The historical PCMCI run
kept getting silently resurfaced as "reused" forever.

The fix adds an independent analysis-CONFIGURATION fingerprint
(``_analysis_config_signature``) alongside the existing source-data
signature, and a pure routing function (``_scheduler_reuse_decision``) that
requires BOTH to match before taking the fast path. These tests exercise
that routing function directly (no live DB/scheduler process involved) so
the fix is verifiable without touching a real database, per "keep the
schedulers stopped while fixing this."
"""

from __future__ import annotations

import uuid
from dataclasses import replace

import pytest
from app.ai.causal.manufacturing_filter import DEFAULT_MANUFACTURING_FILTER_CONFIG
from app.ai.causal.manufacturing_panel import DEFAULT_MANUFACTURING_PANEL_CONFIG
from app.ai.causal.telematics_filter import DEFAULT_TELEMATICS_FILTER_CONFIG
from app.ai.causal.telematics_panel import DEFAULT_TELEMATICS_PANEL_CONFIG
from app.models.causal_runtime_state import CausalSchedulerState
from app.scheduler.causal_scheduler import (
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
    tau_max: int = 12,
    pc_alpha: float = 0.05,
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
# _analysis_config_signature: pure fingerprint properties
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("domain", DOMAINS)
def test_config_signature_is_deterministic(domain: str) -> None:
    # (f) repeated identical requests are idempotent at the fingerprint level.
    first = _config_signature(domain)
    second = _config_signature(domain)
    assert first == second


@pytest.mark.parametrize("domain", DOMAINS)
def test_config_signature_changes_with_algorithm(domain: str) -> None:
    pcmci = _config_signature(domain, algorithm="pcmci")
    lpcmci = _config_signature(domain, algorithm="lpcmci")
    assert pcmci != lpcmci


@pytest.mark.parametrize("domain", DOMAINS)
def test_config_signature_ignores_test_contemporaneous_under_pcmci(domain: str) -> None:
    # test_contemporaneous is an LPCMCI-only knob; two otherwise-identical
    # PCMCI configs must fingerprint identically regardless of its value,
    # since PCMCI never consults it.
    a = _config_signature(domain, algorithm="pcmci", test_contemporaneous=True)
    b = _config_signature(domain, algorithm="pcmci", test_contemporaneous=False)
    assert a == b


@pytest.mark.parametrize("domain", DOMAINS)
def test_config_signature_changes_with_test_contemporaneous_under_lpcmci(domain: str) -> None:
    a = _config_signature(domain, algorithm="lpcmci", test_contemporaneous=True)
    b = _config_signature(domain, algorithm="lpcmci", test_contemporaneous=False)
    assert a != b


@pytest.mark.parametrize("domain", DOMAINS)
def test_config_signature_changes_with_tau_max(domain: str) -> None:
    a = _config_signature(domain, tau_max=12)
    b = _config_signature(domain, tau_max=6)
    assert a != b


@pytest.mark.parametrize("domain", DOMAINS)
def test_config_signature_changes_with_pc_alpha(domain: str) -> None:
    a = _config_signature(domain, pc_alpha=0.05)
    b = _config_signature(domain, pc_alpha=0.10)
    assert a != b


@pytest.mark.parametrize("domain", DOMAINS)
def test_config_signature_changes_with_panel_config(domain: str) -> None:
    baseline = _analysis_config_signature(
        domain=domain,
        algorithm="lpcmci",
        test_contemporaneous=True,
        tau_max=12,
        pc_alpha=0.05,
        algorithm_config=None,
        panel_config=_PANEL_CONFIG[domain],
        filter_config=_FILTER_CONFIG[domain],
    )
    changed_panel = replace(_PANEL_CONFIG[domain], normalize_data=not _PANEL_CONFIG[domain].normalize_data)
    changed = _analysis_config_signature(
        domain=domain,
        algorithm="lpcmci",
        test_contemporaneous=True,
        tau_max=12,
        pc_alpha=0.05,
        algorithm_config=None,
        panel_config=changed_panel,
        filter_config=_FILTER_CONFIG[domain],
    )
    assert baseline != changed


@pytest.mark.parametrize("domain", DOMAINS)
def test_config_signature_changes_with_filter_config(domain: str) -> None:
    baseline = _analysis_config_signature(
        domain=domain,
        algorithm="lpcmci",
        test_contemporaneous=True,
        tau_max=12,
        pc_alpha=0.05,
        algorithm_config=None,
        panel_config=_PANEL_CONFIG[domain],
        filter_config=_FILTER_CONFIG[domain],
    )
    changed_filter = replace(_FILTER_CONFIG[domain], min_abs_score=_FILTER_CONFIG[domain].min_abs_score + 0.1)
    changed = _analysis_config_signature(
        domain=domain,
        algorithm="lpcmci",
        test_contemporaneous=True,
        tau_max=12,
        pc_alpha=0.05,
        algorithm_config=None,
        panel_config=_PANEL_CONFIG[domain],
        filter_config=changed_filter,
    )
    assert baseline != changed


# ---------------------------------------------------------------------------
# _scheduler_reuse_decision: the actual bug-fix routing logic
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("domain", DOMAINS)
def test_a_same_source_same_lpcmci_config_reuses(domain: str) -> None:
    lpcmci_signature = _config_signature(domain, algorithm="lpcmci")
    state = _state(domain, source_signature="source-1", analysis_config_signature=lpcmci_signature)

    routing = _scheduler_reuse_decision(
        force_refresh=False,
        state=state,
        source_signature="source-1",
        analysis_config_signature=lpcmci_signature,
    )

    assert routing.reuse is True
    assert routing.decision == "source_signature_unchanged"


@pytest.mark.parametrize("domain", DOMAINS)
def test_b_same_source_pcmci_to_lpcmci_forces_service_call(domain: str) -> None:
    # This is the exact bug scenario: a historical run was persisted under
    # PCMCI, the deployment now requests LPCMCI, and the source data has
    # not changed at all.
    pcmci_signature = _config_signature(domain, algorithm="pcmci")
    lpcmci_signature = _config_signature(domain, algorithm="lpcmci")
    assert pcmci_signature != lpcmci_signature

    state = _state(domain, source_signature="source-1", analysis_config_signature=pcmci_signature)

    routing = _scheduler_reuse_decision(
        force_refresh=False,
        state=state,
        source_signature="source-1",  # unchanged
        analysis_config_signature=lpcmci_signature,  # PCMCI -> LPCMCI
    )

    assert routing.reuse is False
    assert routing.decision == "analysis_config_changed"


@pytest.mark.parametrize("domain", DOMAINS)
def test_c_same_source_changed_lpcmci_config_forces_service_call(domain: str) -> None:
    original = _config_signature(domain, algorithm="lpcmci", tau_max=12)
    changed = _config_signature(domain, algorithm="lpcmci", tau_max=6)
    assert original != changed

    state = _state(domain, source_signature="source-1", analysis_config_signature=original)

    routing = _scheduler_reuse_decision(
        force_refresh=False,
        state=state,
        source_signature="source-1",
        analysis_config_signature=changed,
    )

    assert routing.reuse is False
    assert routing.decision == "analysis_config_changed"


@pytest.mark.parametrize("domain", DOMAINS)
def test_d_changed_source_same_config_forces_service_call(domain: str) -> None:
    lpcmci_signature = _config_signature(domain, algorithm="lpcmci")
    state = _state(domain, source_signature="source-1", analysis_config_signature=lpcmci_signature)

    routing = _scheduler_reuse_decision(
        force_refresh=False,
        state=state,
        source_signature="source-2",  # changed
        analysis_config_signature=lpcmci_signature,
    )

    assert routing.reuse is False
    assert routing.decision == "source_signature_changed"


@pytest.mark.parametrize("domain", DOMAINS)
def test_e_lpcmci_request_cannot_surface_historical_pcmci_run(domain: str) -> None:
    # Same as (b), phrased as the specific invariant being protected: a
    # scheduler tick requesting LPCMCI must NEVER take the fast-path reuse
    # branch when the persisted state reflects a PCMCI run, regardless of
    # how many times the (unchanged-source) tick repeats.
    pcmci_signature = _config_signature(domain, algorithm="pcmci")
    lpcmci_signature = _config_signature(domain, algorithm="lpcmci")
    state = _state(domain, source_signature="source-1", analysis_config_signature=pcmci_signature)

    for _ in range(3):
        routing = _scheduler_reuse_decision(
            force_refresh=False,
            state=state,
            source_signature="source-1",
            analysis_config_signature=lpcmci_signature,
        )
        assert routing.reuse is False, "an LPCMCI request must never reuse a persisted PCMCI run"


@pytest.mark.parametrize("domain", DOMAINS)
def test_f_repeated_identical_lpcmci_request_is_idempotent(domain: str) -> None:
    # Simulates a two-tick session: tick 1 finds the config changed (service
    # must be called; imagine it persists a new LPCMCI run and the
    # scheduler state is updated to match). Tick 2, with the identical
    # request repeated, must now take the fast path -- proving the fix
    # converges to efficient reuse rather than calling the service forever.
    lpcmci_signature = _config_signature(domain, algorithm="lpcmci")
    pcmci_signature = _config_signature(domain, algorithm="pcmci")

    stale_state = _state(domain, source_signature="source-1", analysis_config_signature=pcmci_signature)
    tick_1 = _scheduler_reuse_decision(
        force_refresh=False,
        state=stale_state,
        source_signature="source-1",
        analysis_config_signature=lpcmci_signature,
    )
    assert tick_1.reuse is False

    # update_scheduler_state() would now persist last_analysis_config_signature
    # = lpcmci_signature (the value the scheduler just requested).
    updated_state = _state(domain, source_signature="source-1", analysis_config_signature=lpcmci_signature)
    tick_2 = _scheduler_reuse_decision(
        force_refresh=False,
        state=updated_state,
        source_signature="source-1",
        analysis_config_signature=lpcmci_signature,
    )
    assert tick_2.reuse is True
    assert tick_2.decision == "source_signature_unchanged"

    # And a third, identical tick remains stable at the fast path.
    tick_3 = _scheduler_reuse_decision(
        force_refresh=False,
        state=updated_state,
        source_signature="source-1",
        analysis_config_signature=lpcmci_signature,
    )
    assert tick_3.reuse is True


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("domain", DOMAINS)
def test_force_refresh_always_forces_a_service_call(domain: str) -> None:
    lpcmci_signature = _config_signature(domain, algorithm="lpcmci")
    state = _state(domain, source_signature="source-1", analysis_config_signature=lpcmci_signature)

    routing = _scheduler_reuse_decision(
        force_refresh=True,
        state=state,
        source_signature="source-1",
        analysis_config_signature=lpcmci_signature,
    )

    assert routing.reuse is False
    assert routing.decision == "force_refresh"


@pytest.mark.parametrize("domain", DOMAINS)
def test_no_prior_state_forces_a_service_call(domain: str) -> None:
    lpcmci_signature = _config_signature(domain, algorithm="lpcmci")

    routing = _scheduler_reuse_decision(
        force_refresh=False,
        state=None,
        source_signature="source-1",
        analysis_config_signature=lpcmci_signature,
    )

    assert routing.reuse is False
    assert routing.decision == "source_signature_changed"


@pytest.mark.parametrize("domain", DOMAINS)
def test_state_without_a_persisted_run_forces_a_service_call(domain: str) -> None:
    lpcmci_signature = _config_signature(domain, algorithm="lpcmci")
    state = _state(domain, source_signature="source-1", analysis_config_signature=lpcmci_signature, run_id=None)

    routing = _scheduler_reuse_decision(
        force_refresh=False,
        state=state,
        source_signature="source-1",
        analysis_config_signature=lpcmci_signature,
    )

    assert routing.reuse is False


def test_source_signature_builders_do_not_bake_in_algorithm() -> None:
    # (item 1) plan.signature must remain a PURE source-data signature.
    # Guard against a future regression that folds algorithm/config into
    # the source-plan builders themselves.
    import inspect

    from app.scheduler import causal_scheduler

    manufacturing_source = inspect.getsource(causal_scheduler.build_manufacturing_source_plan)
    telematics_source = inspect.getsource(causal_scheduler.build_telematics_source_plan)
    for source in (manufacturing_source, telematics_source):
        assert "causal_algorithm" not in source
        assert "lpcmci_test_contemporaneous" not in source
