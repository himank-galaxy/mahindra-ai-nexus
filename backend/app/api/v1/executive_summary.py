"""Executive summary endpoint (top-level, shared by catalogue + simulation)."""

from __future__ import annotations

from fastapi import APIRouter

from app.schemas.copilot import ExecutiveSummaryIn, ExecutiveSummaryOut
from app.services import ExecutiveSummaryService

router = APIRouter()


@router.post(
    "/executive-summary",
    response_model=ExecutiveSummaryOut,
    summary="Generate the 9-field executive summary for a use case",
)
async def generate_executive_summary(payload: ExecutiveSummaryIn) -> ExecutiveSummaryOut:
    return ExecutiveSummaryService.generate(payload.use_case)
