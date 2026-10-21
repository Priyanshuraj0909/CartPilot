"""Persist bounded plan summaries; operational decisions remain read-only."""
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_run import AgentRun
from app.schemas.orchestration import ActionPlan


async def save_plan_run(plan: ActionPlan, session: AsyncSession) -> None:
    session.add(AgentRun(
        merchant_id=plan.merchant_id,
        agent_name="orchestrator",
        status="completed",
        started_at=plan.created_at,
        completed_at=datetime.now(timezone.utc),
        input_summary={"goal": plan.goal.value},
        output_summary={
            "summary": plan.summary,
            "complete": plan.complete,
            "products_analyzed": plan.products_analyzed or len({result.product_id for result in plan.agent_results}),
            "recommendations": len(plan.recommendations),
            "failed_analyses": sum(not result.success for result in plan.agent_results),
        },
    ))
    await session.commit()
