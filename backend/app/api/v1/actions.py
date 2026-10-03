"""Development-only human-reviewed local action endpoints."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_database_session
from app.core.config import settings
from app.models.action import Action
from app.models.recommendation import Recommendation
from app.models.audit_log import AuditLog
from app.models.merchant import Merchant
from app.schemas.actions import ActionCreate, ActionDecision, ExecutionRequest, ActionResponse, ActionAuditResponse
from app.services.actions import workflow
from app.services.actions.state import ActionError

router = APIRouter(tags=["Guarded local actions"])


def local_only() -> None:
    if not settings.is_local_environment:
        raise HTTPException(403, "Phase 9 local actions are available only in development/test environments.")


async def invoke(session: AsyncSession, call) -> ActionResponse:
    try:
        return await call
    except ActionError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(422, "Recommendation or stored action payload is invalid; regenerate and review it.") from exc
    except SQLAlchemyError as exc:
        await session.rollback()
        raise HTTPException(503, "Store action data is temporarily unavailable.") from exc


@router.post("/actions", response_model=ActionResponse, dependencies=[Depends(local_only)])
async def create(request: ActionCreate, session: AsyncSession = Depends(get_database_session)):
    return await invoke(session, workflow.create_action(session, request))


@router.get("/actions", response_model=list[ActionResponse])
async def actions(merchant_id: int = Query(gt=0), offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=100), session: AsyncSession = Depends(get_database_session)):
    if await session.get(Merchant, merchant_id) is None:
        raise HTTPException(404, "Merchant not found.")
    rows = (await session.execute(select(Action).join(Recommendation).where(Recommendation.merchant_id == merchant_id,
        Action.workflow_key.is_not(None)).order_by(Action.id.desc()).offset(offset).limit(limit))).scalars().all()
    return [await invoke(session, get_response(session, row.id, merchant_id)) for row in rows]


async def get_response(session: AsyncSession, action_id: int, merchant_id: int):
    return await workflow.response_for(session, *await workflow.load_action(session, action_id, merchant_id))


@router.get("/actions/{action_id}", response_model=ActionResponse)
async def action(action_id: int, merchant_id: int = Query(gt=0), session: AsyncSession = Depends(get_database_session)):
    return await invoke(session, get_response(session, action_id, merchant_id))


@router.post("/actions/{action_id}/approve", response_model=ActionResponse, dependencies=[Depends(local_only)])
async def approve(action_id: int, request: ActionDecision, session: AsyncSession = Depends(get_database_session)):
    return await invoke(session, workflow.decide_action(session, action_id, request, True))


@router.post("/actions/{action_id}/reject", response_model=ActionResponse, dependencies=[Depends(local_only)])
async def reject(action_id: int, request: ActionDecision, session: AsyncSession = Depends(get_database_session)):
    return await invoke(session, workflow.decide_action(session, action_id, request, False))


@router.post("/actions/{action_id}/execute", response_model=ActionResponse, dependencies=[Depends(local_only)])
async def execute(action_id: int, request: ExecutionRequest, session: AsyncSession = Depends(get_database_session)):
    return await invoke(session, workflow.execute_action(session, action_id, request))


@router.get("/action-history", response_model=list[ActionAuditResponse])
async def history(merchant_id: int = Query(gt=0), offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=200), session: AsyncSession = Depends(get_database_session)):
    if await session.get(Merchant, merchant_id) is None:
        raise HTTPException(404, "Merchant not found.")
    records = (await session.execute(select(AuditLog).where(AuditLog.merchant_id == merchant_id,
        AuditLog.entity_type == "action").order_by(AuditLog.id.desc()).offset(offset).limit(limit))).scalars().all()
    return [ActionAuditResponse(id=row.id, action_id=int(row.entity_id), merchant_id=merchant_id,
        event_type=row.event_type, message=row.message, metadata=row.metadata_, created_at=row.created_at) for row in records]
