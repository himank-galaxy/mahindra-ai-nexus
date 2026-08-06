"""API v1 aggregate router.

Every domain router is mounted here under ``/api/v1``. Phase 2 mounted all
read endpoints; Phase 3 adds the write (mutation) endpoints; Phase 4 adds
the AI layer (simulation engines, copilot chat, ask endpoints).
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    agents,
    catalogue,
    circularity,
    collections,
    copilot,
    dealers,
    executive_summary,
    finance,
    logistics,
    mobility,
    overview,
    poc,
    simulations,
    trust,
)

api_v1_router = APIRouter()

api_v1_router.include_router(executive_summary.router, tags=["executive-summary"])
api_v1_router.include_router(overview.router, prefix="/overview", tags=["overview"])
api_v1_router.include_router(overview.recommendations_router, tags=["overview"])
api_v1_router.include_router(catalogue.router, prefix="/catalogue", tags=["catalogue"])
api_v1_router.include_router(poc.router, prefix="/poc", tags=["poc"])
api_v1_router.include_router(dealers.router, prefix="/dealers", tags=["dealers"])
api_v1_router.include_router(dealers.leads_router, prefix="/dealer-leads", tags=["dealers"])
api_v1_router.include_router(finance.router, prefix="/finance", tags=["finance"])
api_v1_router.include_router(collections.router, prefix="/collections", tags=["collections"])
api_v1_router.include_router(logistics.router, prefix="/logistics", tags=["logistics"])
api_v1_router.include_router(circularity.router, prefix="/circularity", tags=["circularity"])
api_v1_router.include_router(trust.router, prefix="/trust", tags=["trust"])
api_v1_router.include_router(agents.router, prefix="/agents", tags=["agents"])
api_v1_router.include_router(agents.xr_router, prefix="/xr", tags=["xr"])
api_v1_router.include_router(mobility.router, prefix="/mobility-twin", tags=["mobility-twin"])
api_v1_router.include_router(simulations.router, prefix="/simulations", tags=["simulations"])
api_v1_router.include_router(copilot.router, prefix="/copilot", tags=["copilot"])
