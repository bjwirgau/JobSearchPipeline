"""Auditable workflow state shared by orchestration layers."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import Enum
from uuid import uuid4

from utils.dates import utc_now


class WorkflowStage(str, Enum):
    SEARCH = "search"
    NORMALIZE = "normalize"
    PARSE = "parse"
    SCORE = "score"
    REVIEW = "review"
    TAILOR = "tailor"
    APPLY = "apply"
    TRACK = "track"


class WorkflowStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    REVIEW_REQUIRED = "review_required"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class StageRecord:
    stage: WorkflowStage
    status: WorkflowStatus
    message: str = ""
    occurred_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True, slots=True)
class WorkflowRun:
    workflow_name: str
    run_id: str = field(default_factory=lambda: uuid4().hex)
    status: WorkflowStatus = WorkflowStatus.PENDING
    stages: tuple[StageRecord, ...] = ()
    started_at: datetime = field(default_factory=utc_now)
    finished_at: datetime | None = None

    def record(
        self,
        stage: WorkflowStage,
        stage_status: WorkflowStatus,
        message: str = "",
        *,
        workflow_status: WorkflowStatus | None = None,
    ) -> "WorkflowRun":
        next_status = workflow_status
        if next_status is None:
            if stage_status is WorkflowStatus.FAILED:
                next_status = WorkflowStatus.FAILED
            elif self.status is WorkflowStatus.PENDING:
                next_status = WorkflowStatus.RUNNING
            else:
                next_status = self.status
        return replace(
            self,
            status=next_status,
            stages=self.stages + (StageRecord(stage, stage_status, message),),
            finished_at=(
                utc_now()
                if next_status in {WorkflowStatus.COMPLETED, WorkflowStatus.FAILED}
                else None
            ),
        )
