"""
Tasks Status API endpoints.

Provides status change operations: complete, skip, and reopen tasks.
"""
from datetime import datetime, timedelta, timezone
from typing import Annotated, Union

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from starlette.responses import Response
from sqlalchemy import delete, select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.auth import CurrentUser
from app.core.db import get_db
from app.core.time import utc_now
from app.models.dependency import DependencyRule
from app.models.task import Task
from app.models.task_completion import TaskCompletion
from app.schemas.dependency import DependencyBlockedResponse, DependencyStatusResponse
from app.schemas.tasks import (
    AffectedDownstreamEntry,
    CompleteTaskRequest,
    ReopenTaskRequest,
    SkipChainTaskRequest,
    SkipTaskPreviewResponse,
    SkipTaskRequest,
    TaskResponse,
    TransitiveHardDependentPreviewEntry,
)
from app.api.helpers.task_helpers import (
    get_task_or_404,
    task_to_response,
    update_goal_progress,
    assign_sort_order_for_anytime,
    clear_sort_order_for_completed,
)
from app.services.dependency_service import (
    check_dependencies,
    get_qualifying_upstream_ids,
    get_transitive_unmet_hard_prerequisites,
    record_resolutions,
)
from app.services.skip_dependency_service import (
    build_transitive_hard_dependent_preview_rows,
    evaluate_skip_hard_downstream_impact,
    get_transitive_hard_dependents_toposort,
)

router = APIRouter(prefix="/tasks", tags=["tasks"])


def _effective_local_date_for_recurring_occurrence(
    task: Task,
    body_local_date: str | None,
    scheduled_for: datetime | None,
) -> str | None:
    """
    Calendar YYYY-MM-DD for this occurrence.

    Prefer the client's ``local_date`` (required for Rule B with Time Machine / timezones).
    If omitted for a recurring task, fall back to the UTC calendar date of ``scheduled_for``
    (same convention as task list ``date_key`` when ``local_date`` is null on a row).
    """
    if body_local_date:
        return body_local_date
    if not task.is_recurring or scheduled_for is None:
        return None
    sf = scheduled_for
    if sf.tzinfo is None:
        sf = sf.replace(tzinfo=timezone.utc)
    return sf.astimezone(timezone.utc).date().isoformat()


async def _persist_task_skip(
    db: AsyncSession,
    task: Task,
    reason: str | None,
    scheduled_for: datetime | None,
    local_date: str | None,
) -> None:
    """Record skip for one task (recurring: TaskCompletion row; one-time: task row)."""
    if task.is_recurring:
        completion = TaskCompletion(
            task_id=task.id,
            status="skipped",
            skip_reason=reason,
            completed_at=utc_now(),
            scheduled_for=scheduled_for,
            local_date=local_date,
        )
        db.add(completion)
        return
    if task.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only skip pending tasks",
        )
    task.status = "skipped"
    task.skip_reason = reason
    task.updated_at = utc_now()
    await clear_sort_order_for_completed(db, task)
    # Mirror one-time complete: record TaskCompletion so dependency rules can treat
    # skip like an upstream occurrence (e.g. downstream may complete after "keep pending").
    db.add(
        TaskCompletion(
            task_id=task.id,
            status="skipped",
            skip_reason=reason,
            completed_at=utc_now(),
            scheduled_for=scheduled_for,
            local_date=local_date,
        )
    )


@router.post(
    "/{task_id}/complete",
    response_model=TaskResponse,
    summary="Complete task",
    responses={
        409: {
            "description": "Blocked by unmet hard dependencies",
            "model": DependencyBlockedResponse,
        }
    },
)
async def complete_task(
    task_id: str,
    request: CompleteTaskRequest,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Union[TaskResponse, Response]:
    """
    Mark a task as complete.
    
    For recurring tasks: records a completion but keeps task pending.
    For one-time tasks: sets status to 'completed'.
    For anytime tasks: also clears sort_order and shifts others down.
    
    Phase 4i: Checks dependencies before completing. If hard dependencies
    are unmet, returns 409 with blockers unless override_confirm=true
    with override_reason.
    """
    task = await get_task_or_404(db, task_id, user.id)

    eff_local_date = _effective_local_date_for_recurring_occurrence(
        task, request.local_date, request.scheduled_for
    )

    # Phase 4i: Check dependencies
    dep_status = await check_dependencies(
        db, task_id, user.id, request.scheduled_for, eff_local_date
    )
    
    # Get unmet hard blockers
    unmet_hard = [b for b in dep_status.dependencies if b.strength == "hard" and not b.is_met]
    
    # If hard deps unmet and no override, block
    if unmet_hard and not request.override_confirm:
        blocked_response = DependencyBlockedResponse(
            task_id=task_id,
            scheduled_for=request.scheduled_for,
            blockers=unmet_hard,
        )
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=blocked_response.model_dump(mode="json"),
        )
    
    # If override requested but no reason, reject
    if request.override_confirm and unmet_hard and not request.override_reason:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="override_reason is required when overriding unmet hard dependencies",
        )
    
    completion: TaskCompletion | None = None
    
    if task.is_recurring:
        # Record completion for this occurrence
        completion = TaskCompletion(
            task_id=task.id,
            status="completed",
            completed_at=utc_now(),
            scheduled_for=request.scheduled_for,
            local_date=eff_local_date,
        )
        db.add(completion)
        await db.flush()  # Get the ID
        # Task stays pending for next occurrence
    else:
        # One-time task: check if already completed
        if task.status == "completed":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Task is already completed",
            )
        # One-time task: mark as completed
        task.status = "completed"
        task.completed_at = utc_now()
        task.updated_at = utc_now()
        
        # Create a completion record for dependency tracking
        completion = TaskCompletion(
            task_id=task.id,
            status="completed",
            completed_at=task.completed_at,
            scheduled_for=request.scheduled_for,
            local_date=eff_local_date,
        )
        db.add(completion)
        await db.flush()
        
        # Phase 4e: Clear sort_order for completed anytime tasks
        await clear_sort_order_for_completed(db, task)
    
    # Phase 4i: Record dependency resolutions
    if completion and dep_status.dependencies:
        # Get upstream completion IDs for consumption
        upstream_ids: dict[str, list[str]] = {}
        for blocker in dep_status.dependencies:
            # Load the rule to get scope info
            rule_stmt = select(DependencyRule).where(DependencyRule.id == blocker.rule_id)
            result = await db.execute(rule_stmt)
            rule = result.scalar_one_or_none()
            if rule:
                ids = await get_qualifying_upstream_ids(
                    db,
                    rule,
                    request.scheduled_for,
                    blocker.required_count,
                    eff_local_date,
                )
                upstream_ids[blocker.rule_id] = ids
        
        # Determine resolution source
        if request.override_confirm and unmet_hard:
            resolution_source = "override"
        else:
            resolution_source = "manual"
        
        await record_resolutions(
            db,
            downstream_completion_id=completion.id,
            blockers=dep_status.dependencies,
            upstream_completion_ids=upstream_ids,
            resolution_source=resolution_source,
            override_reason=request.override_reason if request.override_confirm else None,
        )
    
    # Update goal progress
    await update_goal_progress(db, task.goal_id)
    
    await db.commit()
    task = await get_task_or_404(db, task.id, user.id)
    # For recurring tasks, we just completed it for today
    return task_to_response(task, completed_for_today=task.is_recurring)


@router.post(
    "/{task_id}/skip",
    response_model=TaskResponse | SkipTaskPreviewResponse,
    summary="Skip task",
)
async def skip_task(
    task_id: str,
    request: SkipTaskRequest,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TaskResponse | SkipTaskPreviewResponse:
    """
    Skip a task occurrence.

    For recurring tasks: records a skip but keeps task pending.
    For one-time tasks: sets status to 'skipped'.
    For anytime tasks: also clears sort_order and shifts others down.

    Phase 4i-4: If hard downstream rules require confirmation, returns
    `status: has_dependents` without persisting until `confirm_proceed=true`.
    """
    task = await get_task_or_404(db, task_id, user.id)

    impact = await evaluate_skip_hard_downstream_impact(
        db, task_id, user.id, request.scheduled_for, request.local_date
    )
    if impact.needs_confirmation and not request.confirm_proceed:
        transitive_rows = await build_transitive_hard_dependent_preview_rows(
            db, task_id, user.id, request.scheduled_for, request.local_date
        )
        return SkipTaskPreviewResponse(
            affected_downstream=[
                AffectedDownstreamEntry(
                    task_id=row["task_id"],
                    task_title=row["task_title"],
                    rule_id=row["rule_id"],
                    strength=row["strength"],
                    affected_occurrences=row["affected_occurrences"],
                )
                for row in impact.affected
            ],
            transitive_hard_dependents_toposort=[
                TransitiveHardDependentPreviewEntry(**row)
                for row in transitive_rows
            ],
        )

    await _persist_task_skip(
        db,
        task,
        request.reason,
        request.scheduled_for,
        request.local_date,
    )

    await db.commit()
    task = await get_task_or_404(db, task.id, user.id)
    return task_to_response(task, skipped_for_today=task.is_recurring)


@router.post(
    "/{task_id}/skip-chain",
    response_model=list[TaskResponse],
    summary="Skip task and cascade skip to hard dependents",
)
async def skip_task_chain(
    task_id: str,
    request: SkipChainTaskRequest,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[TaskResponse]:
    """
    Skip this task then skip all transitive hard dependents in topological order.

    Requires `cascade_skip=true`. Does not return the has_dependents preview;
    the client should use that flow on POST /skip before calling this endpoint.
    """
    if not request.cascade_skip:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="cascade_skip must be true to perform cascade skip",
        )

    root = await get_task_or_404(db, task_id, user.id)
    dependent_ids = await get_transitive_hard_dependents_toposort(
        db, task_id, user.id, request.scheduled_for, request.local_date
    )

    out: list[TaskResponse] = []

    await _persist_task_skip(
        db,
        root,
        request.reason,
        request.scheduled_for,
        request.local_date,
    )
    await db.flush()
    out.append(
        task_to_response(
            await get_task_or_404(db, root.id, user.id),
            skipped_for_today=root.is_recurring,
        )
    )

    for dep_id in dependent_ids:
        dep_task = await get_task_or_404(db, dep_id, user.id)
        await _persist_task_skip(
            db,
            dep_task,
            request.reason,
            request.scheduled_for,
            request.local_date,
        )
        await db.flush()
        refreshed = await get_task_or_404(db, dep_task.id, user.id)
        out.append(
            task_to_response(refreshed, skipped_for_today=refreshed.is_recurring)
        )

    await db.commit()
    return out


@router.post(
    "/{task_id}/reopen",
    response_model=TaskResponse,
    summary="Reopen task",
)
async def reopen_task(
    task_id: str,
    request: ReopenTaskRequest,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TaskResponse:
    """
    Reopen a completed or skipped task.
    
    For recurring tasks: deletes the completion record for the specified time slot.
    For one-time tasks: sets status back to pending and deletes all ``TaskCompletion``
    rows for this task so dependency checks and ``next_occurrence`` consumption match
    the reset state (resolutions CASCADE on completion delete).
    """
    task = await get_task_or_404(db, task_id, user.id)
    
    if task.is_recurring:
        # For recurring tasks, delete the completion for the specified time
        if not request.scheduled_for:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="scheduled_for is required to reopen a recurring task occurrence",
            )

        completion: TaskCompletion | None = None

        # Date-only recurring: `scheduled_for` is often end-of-local-day as UTC; building a
        # "calendar day" window from that instant uses UTC midnight–end, which can miss the
        # stored row. `local_date` matches complete/skip and is the stable occurrence key.
        if task.scheduled_at is None and request.local_date:
            local_stmt = (
                select(TaskCompletion)
                .where(
                    TaskCompletion.task_id == task.id,
                    TaskCompletion.local_date == request.local_date,
                )
                .order_by(TaskCompletion.completed_at.desc())
                .limit(1)
            )
            result = await db.execute(local_stmt)
            completion = result.scalar_one_or_none()

        if not completion:
            # Timed recurring, or legacy rows without local_date, or missing local_date request
            target_time = request.scheduled_for
            if task.scheduled_at is None:
                window_start = target_time.replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                window_end = target_time.replace(
                    hour=23, minute=59, second=59, microsecond=999999
                )
            else:
                target_time = target_time.replace(second=0, microsecond=0)
                window_start = target_time - timedelta(minutes=1)
                window_end = target_time + timedelta(minutes=1)

            completion_stmt = (
                select(TaskCompletion)
                .where(
                    and_(
                        TaskCompletion.task_id == task.id,
                        TaskCompletion.scheduled_for >= window_start,
                        TaskCompletion.scheduled_for <= window_end,
                    )
                )
                .order_by(TaskCompletion.completed_at.desc())
                .limit(1)
            )
            result = await db.execute(completion_stmt)
            completion = result.scalar_one_or_none()

        if not completion:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No completion found for that time slot",
            )
        
        await db.delete(completion)
        await db.commit()
        
        # Return updated task (still pending, but with updated completion counts)
        task = await get_task_or_404(db, task.id, user.id)
        return task_to_response(task)
    
    # For one-time tasks: reopen as before
    if task.status == "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Task is already pending",
        )

    await db.execute(delete(TaskCompletion).where(TaskCompletion.task_id == task.id))
    await db.flush()

    task.status = "pending"
    task.completed_at = None
    task.skip_reason = None
    task.updated_at = utc_now()
    
    # Phase 4e: Re-assign sort_order for reopened anytime tasks (at the bottom)
    await assign_sort_order_for_anytime(db, task)
    
    # Update goal progress
    await update_goal_progress(db, task.goal_id)
    
    await db.commit()
    task = await get_task_or_404(db, task.id, user.id)
    return task_to_response(task)


# ============================================================================
# Dependency Status Endpoints (Phase 4i-2)
# ============================================================================


@router.get(
    "/{task_id}/dependency-status",
    response_model=DependencyStatusResponse,
    summary="Get dependency status for task",
)
async def get_dependency_status(
    task_id: str,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    scheduled_for: datetime | None = Query(
        default=None,
        description="For recurring tasks: which occurrence to check"
    ),
    local_date: str | None = Query(
        default=None,
        description="Client local calendar date (YYYY-MM-DD) for Rule B period alignment",
    ),
) -> DependencyStatusResponse:
    """
    Get dependency status for a task occurrence.
    
    Returns list of blockers (prerequisites), whether they're met,
    and the overall readiness state.
    Includes ``transitive_unmet_hard_prerequisites`` (topo order) for chained hard deps.
    """
    task = await get_task_or_404(db, task_id, user.id)
    eff_local_date = _effective_local_date_for_recurring_occurrence(
        task, local_date, scheduled_for
    )
    base = await check_dependencies(
        db, task_id, user.id, scheduled_for, eff_local_date
    )
    transitive = await get_transitive_unmet_hard_prerequisites(
        db, task_id, user.id, scheduled_for, eff_local_date
    )
    return DependencyStatusResponse(
        task_id=base.task_id,
        scheduled_for=base.scheduled_for,
        dependencies=base.dependencies,
        transitive_unmet_hard_prerequisites=transitive,
        dependents=base.dependents,
    )


@router.post(
    "/{task_id}/complete-chain",
    response_model=list[TaskResponse],
    summary="Complete task with all prerequisites",
)
async def complete_task_chain(
    task_id: str,
    request: CompleteTaskRequest,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[TaskResponse]:
    """
    Complete a task along with all its unmet prerequisites in topological order.
    
    This implements "Complete All Prerequisites" flow - finds all transitively
    unmet prerequisites and completes them in the correct order before
    completing the target task.
    
    Returns list of all completed tasks in completion order.
    """
    from app.services.dependency_service import get_transitive_blockers

    task = await get_task_or_404(db, task_id, user.id)

    eff_local_date = _effective_local_date_for_recurring_occurrence(
        task, request.local_date, request.scheduled_for
    )

    # Get all transitive blockers (already in topo order)
    transitive = await get_transitive_blockers(
        db, task_id, user.id, request.scheduled_for, eff_local_date
    )
    
    completed_tasks: list[TaskResponse] = []
    
    # Complete each prerequisite in order
    for blocker_info in transitive:
        prereq_task = await get_task_or_404(db, blocker_info["task_id"], user.id)
        
        # Record completion for prerequisite
        if prereq_task.is_recurring:
            prereq_completion = TaskCompletion(
                task_id=prereq_task.id,
                status="completed",
                completed_at=utc_now(),
                scheduled_for=request.scheduled_for,
                local_date=eff_local_date,
            )
            db.add(prereq_completion)
            await db.flush()
        else:
            if prereq_task.status == "pending":
                prereq_task.status = "completed"
                prereq_task.completed_at = utc_now()
                prereq_task.updated_at = utc_now()
                
                # Create completion record for dep tracking
                prereq_completion = TaskCompletion(
                    task_id=prereq_task.id,
                    status="completed",
                    completed_at=prereq_task.completed_at,
                    scheduled_for=request.scheduled_for,
                    local_date=eff_local_date,
                )
                db.add(prereq_completion)
                await db.flush()
                
                await clear_sort_order_for_completed(db, prereq_task)
        
        await update_goal_progress(db, prereq_task.goal_id)
        
        # Build response
        prereq_task = await get_task_or_404(db, prereq_task.id, user.id)
        completed_tasks.append(
            task_to_response(prereq_task, completed_for_today=prereq_task.is_recurring)
        )
    
    # Now complete the target task (dependencies should now be met)
    dep_status = await check_dependencies(
        db, task_id, user.id, request.scheduled_for, eff_local_date
    )
    
    # Complete target task
    target_completion: TaskCompletion | None = None
    if task.is_recurring:
        target_completion = TaskCompletion(
            task_id=task.id,
            status="completed",
            completed_at=utc_now(),
            scheduled_for=request.scheduled_for,
            local_date=eff_local_date,
        )
        db.add(target_completion)
        await db.flush()
    else:
        if task.status == "completed":
            await db.commit()
            return completed_tasks  # Already done, return what we completed
        
        task.status = "completed"
        task.completed_at = utc_now()
        task.updated_at = utc_now()
        
        target_completion = TaskCompletion(
            task_id=task.id,
            status="completed",
            completed_at=task.completed_at,
            scheduled_for=request.scheduled_for,
            local_date=eff_local_date,
        )
        db.add(target_completion)
        await db.flush()
        
        await clear_sort_order_for_completed(db, task)
    
    # Record resolutions for target task
    if target_completion and dep_status.dependencies:
        upstream_ids: dict[str, list[str]] = {}
        for blocker in dep_status.dependencies:
            rule_stmt = select(DependencyRule).where(DependencyRule.id == blocker.rule_id)
            result = await db.execute(rule_stmt)
            rule = result.scalar_one_or_none()
            if rule:
                ids = await get_qualifying_upstream_ids(
                    db,
                    rule,
                    request.scheduled_for,
                    blocker.required_count,
                    eff_local_date,
                )
                upstream_ids[blocker.rule_id] = ids
        
        await record_resolutions(
            db,
            downstream_completion_id=target_completion.id,
            blockers=dep_status.dependencies,
            upstream_completion_ids=upstream_ids,
            resolution_source="chain",
        )
    
    await update_goal_progress(db, task.goal_id)
    
    await db.commit()
    
    # Add target task to result
    task = await get_task_or_404(db, task.id, user.id)
    completed_tasks.append(task_to_response(task, completed_for_today=task.is_recurring))
    
    return completed_tasks
