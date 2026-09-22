"""
ParCorr + LPCMCI wrapper.

This module is fully implemented and correct against the installed
tigramite package's real function signatures (verified by introspection
before writing this file - see IMPLEMENTATION_PLAN.md section 10), but is
NOT invoked anywhere in this phase.

Calling run_lpcmci() below is left for a later, explicitly approved phase.
Nothing in this codebase currently calls it - see the CLI entrypoints,
which stop right before this point and raise NotImplementedError if
--run-lpcmci is passed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tigramite.independence_tests.parcorr import ParCorr
from tigramite.lpcmci import LPCMCI

from config import DomainCausalConfig
from tigramite_adapter import TigramiteInput


@dataclass
class LPCMCIResult:
    graph: Any
    val_matrix: Any
    p_matrix: Any
    var_names: list[str]
    tau_min: int
    tau_max: int
    pc_alpha: float


def run_lpcmci(
    tigramite_input: TigramiteInput, config: DomainCausalConfig
) -> LPCMCIResult:
    """
    Run ParCorr-conditioned LPCMCI over the prepared panel.

    tau_min / tau_max / pc_alpha come straight from the domain's
    DomainCausalConfig (config.py) - see IMPLEMENTATION_PLAN.md section 9
    for exactly how those three values are chosen and independently
    configured per domain.

    THIS FUNCTION IS NOT CALLED IN THIS PHASE. It exists so the pipeline is
    complete and ready, per the task's explicit "implement, do not run"
    instruction.
    """

    cond_ind_test = ParCorr(significance="analytic")

    lpcmci = LPCMCI(
        dataframe=tigramite_input.dataframe,
        cond_ind_test=cond_ind_test,
    )

    results = lpcmci.run_lpcmci(
        tau_min=config.tau_min,
        tau_max=config.tau_max,
        pc_alpha=config.pc_alpha,
    )

    return LPCMCIResult(
        graph=results["graph"],
        val_matrix=results["val_matrix"],
        p_matrix=results["p_matrix"],
        var_names=tigramite_input.var_names,
        tau_min=config.tau_min,
        tau_max=config.tau_max,
        pc_alpha=config.pc_alpha,
    )
