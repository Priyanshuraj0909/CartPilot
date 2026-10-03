"""Read-only orchestration API with merchant scope validation."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError
from app.agents.orchestrator import MasterOrchestrator
from app.api.deps import get_database_session
from app.schemas.orchestration import ActionPlan, OrchestrationRequest
from app.services.orchestration.context import ContextError

router = APIRouter(tags=["Master Orchestrator"])
orchestrator = MasterOrchestrator()


@router.post("/orchestrate", response_model=ActionPlan,
             summary="Build a goal-driven cross-agent merchant plan",
             description="Advisory only. No actions, approvals, or operational writes are performed.")
async def orchestrate(
    request: OrchestrationRequest, session: AsyncSession = Depends(get_database_session),
) -> ActionPlan:
    try:
        return await orchestrator.analyze(request, session)
    except ContextError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    except SQLAlchemyError as exc:
        raise HTTPException(503, "Store analysis is temporarily unavailable.") from exc
