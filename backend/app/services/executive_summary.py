"""Executive summary generation (stateless 9-field template)."""

from __future__ import annotations

from app.ai.prompts.executive_summary import generate_executive_summary
from app.schemas.copilot import ExecutiveSummaryOut


class ExecutiveSummaryService:
    """Session-free: the summary is a pure template expansion."""

    @staticmethod
    def generate(use_case: str) -> ExecutiveSummaryOut:
        return ExecutiveSummaryOut.model_validate(generate_executive_summary(use_case))
