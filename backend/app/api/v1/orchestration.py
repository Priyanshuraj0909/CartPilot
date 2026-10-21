"""Read-only orchestration API with merchant scope validation."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError
from app.agents.orchestrator import MasterOrchestrator
from app.api.deps import get_database_session
from app.schemas.orchestration import ActionPlan, OrchestrationRequest
from app.services.orchestration.context import ContextError
from app.services.orchestration.history import save_plan_run
from app.models.agent_run import AgentRun
from app.models.merchant import Merchant
from app.schemas.agent_run import AgentRunResponse

router = APIRouter(tags=["Master Orchestrator"])
orchestrator = MasterOrchestrator()


@router.post("/orchestrate", response_model=ActionPlan,
             summary="Build a goal-driven cross-agent merchant plan",
             description="Advisory only. Saves a scoped activity summary; no actions, approvals, or operational writes.")
async def orchestrate(
    request: OrchestrationRequest, session: AsyncSession = Depends(get_database_session),
) -> ActionPlan:
    try:
        plan = await orchestrator.analyze(request, session)
        await save_plan_run(plan, session)
        return plan
    except ContextError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    except SQLAlchemyError as exc:
        await session.rollback()
        raise HTTPException(503, "Store analysis is temporarily unavailable.") from exc


@router.get("/agent-runs", response_model=list[AgentRunResponse], summary="Saved orchestration activity for one merchant")
async def agent_runs(
    merchant_id: int = Query(gt=0), offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    session: AsyncSession = Depends(get_database_session),
) -> list[AgentRun]:
    if await session.get(Merchant, merchant_id) is None:
        raise HTTPException(404, "Merchant not found.")
    statement = select(AgentRun).where(
        AgentRun.merchant_id == merchant_id, AgentRun.agent_name == "orchestrator",
    ).order_by(AgentRun.started_at.desc(), AgentRun.id.desc()).offset(offset).limit(limit)
    return list((await session.scalars(statement)).all())
