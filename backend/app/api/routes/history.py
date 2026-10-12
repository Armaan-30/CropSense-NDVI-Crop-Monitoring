"""Read and delete locally persisted analysis history."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, ConfigDict

from app.api.dependencies import analysis_history_store
from app.services.history_store import AnalysisHistoryStore

router = APIRouter(prefix="/history", tags=["history"])


class HistorySummary(BaseModel):
    """Compact entry returned by the recent-history endpoint."""

    model_config = ConfigDict(extra="ignore")
    id: str
    mode: str
    created_at: str
    start_date: str | None = None
    end_date: str | None = None
    area_ha: float | None = None
    mean_ndvi: float | None = None
    scene_count: int | None = None


class HistoryDetail(HistorySummary):
    """Stored request and result; map tile URLs are intentionally omitted."""

    request: dict[str, Any]
    result: dict[str, Any]


@router.get("", response_model=list[HistorySummary])
def list_history(
    limit: int = Query(default=20, ge=1, le=100),
    store: AnalysisHistoryStore = Depends(analysis_history_store),
) -> list[dict[str, Any]]:
    return store.list_recent(limit=limit)


@router.get("/{history_id}", response_model=HistoryDetail)
def get_history(
    history_id: str,
    store: AnalysisHistoryStore = Depends(analysis_history_store),
) -> dict[str, Any]:
    entry = store.get(history_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Analysis history entry not found")
    return entry


@router.delete("/{history_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_history(
    history_id: str,
    store: AnalysisHistoryStore = Depends(analysis_history_store),
) -> Response:
    if not store.delete(history_id):
        raise HTTPException(status_code=404, detail="Analysis history entry not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
