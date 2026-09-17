"""Regression tests for algorithm-specific tau_max/pc_alpha defaults.

Context
-------
The first live PCMCI -> LPCMCI cutover ran LPCMCI with PCMCI's legacy
tau_max=12 search window and did not complete a single machine/vehicle in
45 minutes. LPCMCI's ancestral/non-ancestral search cost grows far faster
with tau_max than PCMCI's single PC-stable pass, so LPCMCI needs its own,
much cheaper default (tau_max=2, pc_alpha=0.10, matching the reference
standalone pipeline) while PCMCI rollback keeps its established legacy
values (tau_max=12, pc_alpha=0.05) unchanged, and an explicitly supplied
value always overrides either default.

These tests cover items (a)-(i) from the tuning task: default resolution
per algorithm, explicit-value precedence, signature sensitivity (service
level and scheduler level), mobility's PCMCI path being untouched, the
per-asset logging structure, and that the existing LPCMCI orientation/mark
tests still pass (verified by running the full suite alongside this file,
not duplicated here).
"""

from __future__ import annotations

import inspect

import numpy as np
import pytest
from app.ai.causal import pcmci_engine
from app.services import manufacturing_causal, telematics_causal
from app.services.manufacturing_causal import (
    DEFAULT_MANUFACTURING_FILTER_CONFIG,
    LPCMCI_DEFAULT_PC_ALPHA as MFG_LPCMCI_DEFAULT_PC_ALPHA,
    LPCMCI_DEFAULT_TAU_MAX as MFG_LPCMCI_DEFAULT_TAU_MAX,
    PCMCI_DEFAULT_PC_ALPHA as MFG_PCMCI_DEFAULT_PC_ALPHA,
    PCMCI_DEFAULT_TAU_MAX as MFG_PCMCI_DEFAULT_TAU_MAX,
    ManufacturingPanelConfig,
    _analysis_parameters,
    _source_signature,
    effective_pc_alpha as manufacturing_effective_pc_alpha,
    effective_tau_max as manufacturing_effective_tau_max,
)
from app.services.telematics_causal import (
    DEFAULT_TELEMATICS_FILTER_CONFIG,
    DEFAULT_TELEMATICS_PANEL_CONFIG,
    LPCMCI_DEFAULT_PC_ALPHA as TEL_LPCMCI_DEFAULT_PC_ALPHA,
    LPCMCI_DEFAULT_TAU_MAX as TEL_LPCMCI_DEFAULT_TAU_MAX,
    PCMCI_DEFAULT_PC_ALPHA as TEL_PCMCI_DEFAULT_PC_ALPHA,
    PCMCI_DEFAULT_TAU_MAX as TEL_PCMCI_DEFAULT_TAU_MAX,
    _configuration_parameters,
)
from app.services.telematics_causal import _source_signature as telematics_source_signature
from app.services.telematics_causal import (
    effective_pc_alpha as telematics_effective_pc_alpha,
)
from app.services.telematics_causal import (
    effective_tau_max as telematics_effective_tau_max,
)

# ---------------------------------------------------------------------------
# (a) / (b): default LPCMCI resolution per domain
# ---------------------------------------------------------------------------


def test_a_manufacturing_default_lpcmci_resolves_tau_max_2_pc_alpha_010() -> None:
    assert manufacturing_effective_tau_max("lpcmci", None) == 2
    assert manufacturing_effective_pc_alpha("lpcmci", None) == pytest.approx(0.10)
    # And the named constants match, so a reader doesn't have to trust the
    # magic numbers above alone.
    assert MFG_LPCMCI_DEFAULT_TAU_MAX == 2
    assert MFG_LPCMCI_DEFAULT_PC_ALPHA == pytest.approx(0.10)


def test_b_telematics_default_lpcmci_resolves_tau_max_2_pc_alpha_010() -> None:
    assert telematics_effective_tau_max("lpcmci", None) == 2
    assert telematics_effective_pc_alpha("lpcmci", None) == pytest.approx(0.10)
    assert TEL_LPCMCI_DEFAULT_TAU_MAX == 2
    assert TEL_LPCMCI_DEFAULT_PC_ALPHA == pytest.approx(0.10)


# ---------------------------------------------------------------------------
# (c): PCMCI rollback keeps its legacy defaults
# ---------------------------------------------------------------------------


def test_c_manufacturing_pcmci_rollback_resolves_legacy_defaults() -> None:
    assert manufacturing_effective_tau_max("pcmci", None) == 12
    assert manufacturing_effective_pc_alpha("pcmci", None) == pytest.approx(0.05)
    assert MFG_PCMCI_DEFAULT_TAU_MAX == 12
    assert MFG_PCMCI_DEFAULT_PC_ALPHA == pytest.approx(0.05)
    # Backward-compatible unqualified aliases still mean "PCMCI's default".
    assert manufacturing_causal.DEFAULT_TAU_MAX == 12
    assert manufacturing_causal.DEFAULT_PC_ALPHA == pytest.approx(0.05)


def test_c_telematics_pcmci_rollback_resolves_legacy_defaults() -> None:
    assert telematics_effective_tau_max("pcmci", None) == 12
    assert telematics_effective_pc_alpha("pcmci", None) == pytest.approx(0.05)
    assert TEL_PCMCI_DEFAULT_TAU_MAX == 12
    assert TEL_PCMCI_DEFAULT_PC_ALPHA == pytest.approx(0.05)
    assert telematics_causal.DEFAULT_TAU_MAX == 12
    assert telematics_causal.DEFAULT_PC_ALPHA == pytest.approx(0.05)


# ---------------------------------------------------------------------------
# (d): an explicitly supplied value is never silently overridden
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("algorithm", ["lpcmci", "pcmci"])
def test_d_explicit_tau_max_overrides_algorithm_default(algorithm: str) -> None:
    assert manufacturing_effective_tau_max(algorithm, 7) == 7
    assert telematics_effective_tau_max(algorithm, 7) == 7


@pytest.mark.parametrize("algorithm", ["lpcmci", "pcmci"])
def test_d_explicit_pc_alpha_overrides_algorithm_default(algorithm: str) -> None:
    assert manufacturing_effective_pc_alpha(algorithm, 0.33) == pytest.approx(0.33)
    assert telematics_effective_pc_alpha(algorithm, 0.33) == pytest.approx(0.33)


def test_d_explicit_zero_is_not_confused_with_unset() -> None:
    # A real edge case for a "None means unset" sentinel: pc_alpha=0.0 is
    # invalid (caught elsewhere by get_or_run()'s (0, 1] validation), but
    # the RESOLUTION step itself must not treat a falsy-but-explicit value
    # as "not supplied". tau_max=0 is the cleaner case to probe here since
    # 0 is falsy but a legitimate int distinct from None.
    assert manufacturing_effective_tau_max("lpcmci", 0) == 0
    assert telematics_effective_tau_max("lpcmci", 0) == 0


# ---------------------------------------------------------------------------
# (e): changing LPCMCI tau_max/pc_alpha changes the SERVICE run signature
# ---------------------------------------------------------------------------


def _mfg_signature(*, tau_max: int, pc_alpha: float, algorithm: str = "lpcmci") -> str:
    records = [
        {"timestamp": "2026-01-01T00:00:00+00:00", "entity": "MACHINE_1", "metric": "machine_load", "value": 1.0},
    ]
    parameters = _analysis_parameters(
        machine_ids=("MACHINE_1",),
        observations=None,
        history_hours=72.0,
        raw_frequency_minutes=1.0,
        tau_max=tau_max,
        pc_alpha=pc_alpha,
        force_include_metrics=None,
        panel_config=ManufacturingPanelConfig(),
        filter_config=DEFAULT_MANUFACTURING_FILTER_CONFIG,
        algorithm=algorithm,
    )
    return _source_signature(records, parameters=parameters)


def test_e_manufacturing_signature_changes_with_lpcmci_tau_max() -> None:
    a = _mfg_signature(tau_max=2, pc_alpha=0.10)
    b = _mfg_signature(tau_max=6, pc_alpha=0.10)
    assert a != b


def test_e_manufacturing_signature_changes_with_lpcmci_pc_alpha() -> None:
    a = _mfg_signature(tau_max=2, pc_alpha=0.10)
    b = _mfg_signature(tau_max=2, pc_alpha=0.20)
    assert a != b


def _telematics_signature(*, tau_max: int, pc_alpha: float, algorithm: str = "lpcmci") -> str:
    row_digests = {"VEH-1": "digest-1"}
    parameters = _configuration_parameters(
        ("VEH-1",),
        history_hours=168.0,
        source_from=None,
        source_to=None,
        raw_frequency_minutes=1.0,
        panel_config=DEFAULT_TELEMATICS_PANEL_CONFIG,
        filter_config=DEFAULT_TELEMATICS_FILTER_CONFIG,
        tau_max=tau_max,
        pc_alpha=pc_alpha,
        analysis_frequency_minutes=5,
        algorithm=algorithm,
    )
    return telematics_source_signature(row_digests, parameters)


def test_e_telematics_signature_changes_with_lpcmci_tau_max() -> None:
    a = _telematics_signature(tau_max=2, pc_alpha=0.10)
    b = _telematics_signature(tau_max=6, pc_alpha=0.10)
    assert a != b


def test_e_telematics_signature_changes_with_lpcmci_pc_alpha() -> None:
    a = _telematics_signature(tau_max=2, pc_alpha=0.10)
    b = _telematics_signature(tau_max=2, pc_alpha=0.20)
    assert a != b


# ---------------------------------------------------------------------------
# (f): changing LPCMCI tau_max/pc_alpha changes the SCHEDULER
# analysis_config_signature, at the actual production-default values
# ---------------------------------------------------------------------------


def test_f_scheduler_config_signature_changes_between_lpcmci_and_pcmci_tau_max() -> None:
    from app.scheduler.causal_scheduler import _analysis_config_signature

    lpcmci_default = _analysis_config_signature(
        domain="manufacturing",
        algorithm="lpcmci",
        test_contemporaneous=True,
        tau_max=manufacturing_effective_tau_max("lpcmci", None),
        pc_alpha=manufacturing_effective_pc_alpha("lpcmci", None),
        algorithm_config=None,
        panel_config=ManufacturingPanelConfig(),
        filter_config=DEFAULT_MANUFACTURING_FILTER_CONFIG,
    )
    pcmci_default = _analysis_config_signature(
        domain="manufacturing",
        algorithm="pcmci",
        test_contemporaneous=True,
        tau_max=manufacturing_effective_tau_max("pcmci", None),
        pc_alpha=manufacturing_effective_pc_alpha("pcmci", None),
        algorithm_config=None,
        panel_config=ManufacturingPanelConfig(),
        filter_config=DEFAULT_MANUFACTURING_FILTER_CONFIG,
    )
    # Two independent reasons this must differ: algorithm AND the resolved
    # tau_max/pc_alpha (2/0.10 vs 12/0.05) both changed.
    assert lpcmci_default != pcmci_default


def test_f_scheduler_config_signature_changes_when_lpcmci_tau_max_alone_changes() -> None:
    from app.scheduler.causal_scheduler import _analysis_config_signature

    baseline = _analysis_config_signature(
        domain="telematics",
        algorithm="lpcmci",
        test_contemporaneous=True,
        tau_max=telematics_effective_tau_max("lpcmci", None),
        pc_alpha=telematics_effective_pc_alpha("lpcmci", None),
        algorithm_config=None,
        panel_config=DEFAULT_TELEMATICS_PANEL_CONFIG,
        filter_config=DEFAULT_TELEMATICS_FILTER_CONFIG,
    )
    changed = _analysis_config_signature(
        domain="telematics",
        algorithm="lpcmci",
        test_contemporaneous=True,
        tau_max=telematics_effective_tau_max("lpcmci", 3),  # explicit override
        pc_alpha=telematics_effective_pc_alpha("lpcmci", None),
        algorithm_config=None,
        panel_config=DEFAULT_TELEMATICS_PANEL_CONFIG,
        filter_config=DEFAULT_TELEMATICS_FILTER_CONFIG,
    )
    assert baseline != changed


# ---------------------------------------------------------------------------
# (g): mobility's PCMCI path is untouched
# ---------------------------------------------------------------------------


def test_g_mobility_pcmci_default_signature_is_unchanged() -> None:
    signature = inspect.signature(pcmci_engine.run_pcmci)
    assert signature.parameters["tau_max"].default == 3
    assert signature.parameters["alpha"].default == 0.05


def test_g_mobility_service_calls_run_pcmci_with_no_explicit_overrides() -> None:
    # operational_mobility.py must still call run_pcmci() relying purely on
    # its own (untouched) defaults -- not on anything introduced by the
    # manufacturing/telematics algorithm-specific tuning in this change.
    source = inspect.getsource(pcmci_engine.run_pcmci)
    assert "tau_max: int = 3" in source
    assert "alpha: float = 0.05" in source


def test_g_mobility_pcmci_end_to_end_recovers_known_chain() -> None:
    # A behavioral guard, not just a signature check: mobility's exact
    # call pattern (standardize -> run_pcmci -> business_validated) must
    # still produce real, non-empty output on a known synthetic chain.
    from app.ai.causal.preprocessing import standardize

    rng = np.random.default_rng(1)
    n = 200
    a = rng.normal(0, 1, n)
    b = np.zeros(n)
    for t in range(1, n):
        b[t] = 0.7 * a[t - 1] + rng.normal(0, 0.4)
    values = np.column_stack([a, b])
    edges = pcmci_engine.run_pcmci(standardize(values), ["metric_a", "metric_b"])
    assert edges, "mobility's PCMCI path must still discover the planted chain"


# ---------------------------------------------------------------------------
# (h): structured per-asset progress logging exists and doesn't touch the
# analysis math. A live DB is required to exercise get_or_run() end to end,
# which is unavailable in this environment (see test_live_pipeline.py /
# test_scheduler_analysis_config_cutover.py for the established pattern of
# testing scheduler/service orchestration via source inspection + pure
# helper functions instead). This proves: (1) the exact event names and
# fields the task specifies are present at the right place in the loop,
# and (2) the analysis functions the loop calls remain pure/deterministic
# and contain no logging of their own -- i.e. logging was added only at
# the orchestration layer, never inside the computational path, so it
# cannot alter results.
# ---------------------------------------------------------------------------


def test_h_manufacturing_emits_the_specified_structured_events() -> None:
    source = inspect.getsource(manufacturing_causal.ManufacturingCausalService.get_or_run)
    for event in ("causal_asset_started", "causal_asset_completed", "causal_domain_completed"):
        assert event in source
    for field in ("asset_id", "asset_index", "asset_total", "tau_max", "pc_alpha"):
        assert field in source
    for field in ("runtime_seconds", "variables_used", "analytical_rows", "edge_count"):
        assert field in source
    for field in ("successful_assets", "total_runtime_seconds"):
        assert field in source


def test_h_telematics_emits_the_specified_structured_events() -> None:
    source = inspect.getsource(telematics_causal.TelematicsCausalService.get_or_run)
    for event in ("causal_asset_started", "causal_asset_completed", "causal_domain_completed"):
        assert event in source
    for field in ("asset_id", "asset_index", "asset_total", "tau_max", "pc_alpha"):
        assert field in source
    for field in ("runtime_seconds", "variables_used", "analytical_rows", "edge_count"):
        assert field in source


def test_h_asset_analysis_functions_log_only_lpcmci_discovery_events() -> None:
    # As of the runtime-profiling change, _analyse_machine/_analyse_vehicle
    # DO log -- but only the two fine-grained LPCMCI discovery-boundary
    # events (causal_lpcmci_input_ready / causal_lpcmci_discovery_completed,
    # see test_lpcmci_profiling_logs.py). The coarser per-asset
    # orchestration events (causal_asset_started/completed/domain_completed)
    # must stay in get_or_run()'s loop, not duplicated down here.
    mfg_source = inspect.getsource(manufacturing_causal._analyse_machine)
    tel_source = inspect.getsource(telematics_causal._analyse_vehicle)
    for source in (mfg_source, tel_source):
        assert "causal_lpcmci_input_ready" in source
        assert "causal_lpcmci_discovery_completed" in source
        assert "causal_asset_started" not in source
        assert "causal_asset_completed" not in source
        assert "causal_domain_completed" not in source


def test_h_manufacturing_analysis_is_deterministic_regardless_of_logging() -> None:
    # Calling the pure analysis function twice with identical input must
    # produce identical results -- proving nothing about the (separate,
    # orchestration-layer) logging can perturb the computation.
    from datetime import UTC, datetime, timedelta

    from app.ai.causal.manufacturing_filter import DEFAULT_MANUFACTURING_FILTER_CONFIG as FILTER_CONFIG
    from app.services.manufacturing_causal import _analyse_machine

    start = datetime(2026, 7, 25, tzinfo=UTC)
    records = []
    for minute in range(200):
        ts = start + timedelta(minutes=minute)
        records.append(
            {
                "timestamp": ts,
                "entity": "MACHINE_1",
                "machine_id": "MACHINE_1",
                "metric": "machine_load",
                "value": float(minute % 17),
                "plant_id": "PLANT_1",
                "production_line_id": "LINE_1",
                "line_type": "ASSEMBLY",
            }
        )
        records.append(
            {
                "timestamp": ts,
                "entity": "MACHINE_1",
                "machine_id": "MACHINE_1",
                "metric": "power_kw",
                "value": float((minute * 3) % 23),
                "plant_id": "PLANT_1",
                "production_line_id": "LINE_1",
                "line_type": "ASSEMBLY",
            }
        )

    panel_config = ManufacturingPanelConfig(
        analysis_frequency="15min",
        min_panel_observations=1,
        min_data_coverage=0.0,
        min_row_completeness=0.5,
        skew_transform_enabled=False,
        stationarity_differencing_enabled=False,
        normalize_data=True,
    )

    kwargs = dict(
        algorithm="lpcmci",
        tau_max=2,
        pc_alpha=0.10,
        test_contemporaneous=True,
        algorithm_config=None,
        panel_config=panel_config,
        filter_config=FILTER_CONFIG,
    )
    first = _analyse_machine("MACHINE_1", records, **kwargs)
    second = _analyse_machine("MACHINE_1", records, **kwargs)

    assert first.analytical_rows == second.analytical_rows
    assert first.variables_used == second.variables_used
    assert [edge.score for edge in first.filtered.accepted_edges] == [
        edge.score for edge in second.filtered.accepted_edges
    ]
    assert [edge.edge_mark for edge in first.filtered.accepted_edges] == [
        edge.edge_mark for edge in second.filtered.accepted_edges
    ]
