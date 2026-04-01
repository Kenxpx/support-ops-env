"""Typed models for the support operations environment."""

from __future__ import annotations

from typing import Any, Literal

from openenv.core.env_server.types import Action, Observation, State
from pydantic import BaseModel, Field


ActionType = Literal[
    "noop",
    "search_tickets",
    "search_kb",
    "view_ticket",
    "set_queue",
    "set_priority",
    "add_tag",
    "add_internal_note",
    "send_reply",
    "mark_status",
    "link_duplicate",
    "create_incident",
    "set_incident_severity",
    "post_status_update",
]

QueueType = Literal[
    "triage",
    "billing",
    "technical_support",
    "incident_response",
    "customer_success",
]
PriorityType = Literal["low", "medium", "high", "urgent"]
StatusType = Literal["open", "pending", "resolved", "escalated"]
DifficultyType = Literal["easy", "medium", "hard"]
IncidentSeverityType = Literal["sev3", "sev2", "sev1"]


class TicketSummary(BaseModel):
    ticket_id: str = Field(..., description="Stable ticket identifier")
    subject: str = Field(..., description="Ticket subject")
    customer: str = Field(..., description="Customer name")
    customer_tier: str = Field(..., description="Customer plan or tier")
    queue: str = Field(..., description="Current queue")
    priority: str = Field(..., description="Current priority")
    status: str = Field(..., description="Current status")
    tags: list[str] = Field(default_factory=list, description="Current tags")
    region: str = Field(..., description="Customer region")
    product: str = Field(..., description="Affected product area")
    impacted_users: int = Field(default=1, description="Approximate impacted user count")
    sla_minutes: int = Field(default=240, description="SLA response target in minutes")


class TicketDetail(TicketSummary):
    body: str = Field(..., description="Full ticket body")
    account_owner: str = Field(..., description="Internal account owner")
    opened_minutes_ago: int = Field(..., description="Ticket age in minutes")
    related_ticket_ids: list[str] = Field(
        default_factory=list,
        description="Potentially related tickets from the same account or incident",
    )
    internal_notes: list[str] = Field(
        default_factory=list, description="Internal notes added so far"
    )
    replies: list[str] = Field(default_factory=list, description="Replies sent so far")
    duplicate_of: str | None = Field(
        default=None, description="Primary ticket if this ticket was linked as duplicate"
    )


class KnowledgeBaseArticleSummary(BaseModel):
    article_id: str = Field(..., description="Knowledge base article identifier")
    title: str = Field(..., description="Knowledge base article title")
    summary: str = Field(..., description="Short searchable summary")
    key_facts: list[str] = Field(
        default_factory=list,
        description="Structured facts surfaced from the article",
    )


class IncidentSummary(BaseModel):
    incident_id: str = Field(..., description="Incident identifier")
    title: str = Field(..., description="Incident title")
    severity: IncidentSeverityType = Field(..., description="Current incident severity")
    status: str = Field(..., description="Current incident status")
    owner_queue: str = Field(..., description="Owning operational queue")
    linked_ticket_ids: list[str] = Field(
        default_factory=list,
        description="Tickets currently attached to the incident",
    )
    public_updates_count: int = Field(
        default=0,
        description="Number of public status updates sent",
    )


class StatusPageUpdate(BaseModel):
    incident_id: str = Field(..., description="Incident this update belongs to")
    sequence: int = Field(..., description="1-based sequence number")
    message: str = Field(..., description="Published status-page message")


class MilestoneProgress(BaseModel):
    milestone_id: str = Field(..., description="Stable milestone identifier")
    description: str = Field(..., description="Human-readable milestone")
    weight: float = Field(..., description="Fraction of task score represented here")
    completed: bool = Field(default=False, description="Whether milestone is complete")


class GuardrailViolation(BaseModel):
    violation_id: str = Field(..., description="Stable guardrail violation identifier")
    description: str = Field(..., description="Human-readable guardrail description")
    penalty: float = Field(..., description="Penalty applied if this violation is triggered")


class SupportOpsAction(Action):
    """Single structured action sent to the environment."""

    action_type: ActionType = Field(..., description="Action to execute")
    ticket_id: str | None = Field(default=None, description="Target ticket id")
    queue: QueueType | None = Field(default=None, description="Queue to assign")
    priority: PriorityType | None = Field(
        default=None, description="Priority to assign"
    )
    tag: str | None = Field(default=None, description="Tag to add")
    note: str | None = Field(default=None, description="Internal note body")
    reply: str | None = Field(default=None, description="Customer reply body")
    status: StatusType | None = Field(default=None, description="New ticket status")
    duplicate_of: str | None = Field(
        default=None, description="Primary ticket id for duplicate linking"
    )
    query: str | None = Field(default=None, description="Search query text")
    incident_id: str | None = Field(default=None, description="Target incident id")
    incident_title: str | None = Field(
        default=None,
        description="Incident title used when creating a new incident",
    )
    severity: IncidentSeverityType | None = Field(
        default=None,
        description="Incident severity to apply",
    )
    message: str | None = Field(
        default=None,
        description="Generic status-page or workflow message body",
    )


class SupportOpsObservation(Observation):
    """Observation returned after reset and every step."""

    task_id: str = Field(..., description="Current task identifier")
    task_title: str = Field(..., description="Task title")
    difficulty: DifficultyType = Field(..., description="Task difficulty")
    goal: str = Field(..., description="User-facing objective for the agent")
    scenario: str = Field(..., description="High-level operating context")
    instructions: list[str] = Field(
        default_factory=list, description="Visible operating instructions"
    )
    ticket_summaries: list[TicketSummary] = Field(
        default_factory=list,
        description="Visible ticket queue snapshot",
    )
    focused_ticket: TicketDetail | None = Field(
        default=None,
        description="Detailed ticket currently in focus",
    )
    ticket_search_results: list[TicketSummary] = Field(
        default_factory=list,
        description="Results from the latest ticket search action",
    )
    kb_search_results: list[KnowledgeBaseArticleSummary] = Field(
        default_factory=list,
        description="Results from the latest knowledge-base search action",
    )
    incidents: list[IncidentSummary] = Field(
        default_factory=list,
        description="Open incidents visible to the agent",
    )
    recent_status_updates: list[StatusPageUpdate] = Field(
        default_factory=list,
        description="Recent public status-page updates",
    )
    milestones: list[MilestoneProgress] = Field(
        default_factory=list,
        description="Visible progress checklist",
    )
    guardrail_violations: list[GuardrailViolation] = Field(
        default_factory=list,
        description="Triggered quality or safety violations that reduce final score",
    )
    available_actions: list[str] = Field(
        default_factory=list,
        description="Action types available to the agent",
    )
    queue_options: list[str] = Field(
        default_factory=list,
        description="Allowed queue names",
    )
    priority_options: list[str] = Field(
        default_factory=list,
        description="Allowed priority names",
    )
    status_options: list[str] = Field(
        default_factory=list,
        description="Allowed status values",
    )
    incident_severity_options: list[str] = Field(
        default_factory=list,
        description="Allowed incident severities",
    )
    tag_options: list[str] = Field(
        default_factory=list,
        description="Recommended operational tags for this scenario",
    )
    progress: float = Field(default=0.0, description="Fraction of task completed")
    score: float = Field(default=0.0, description="Normalized task score")
    guardrail_penalty_total: float = Field(
        default=0.0,
        description="Total sticky penalty from triggered guardrail violations",
    )
    last_action_summary: str = Field(
        default="Environment reset.",
        description="Short summary of the last environment event",
    )
    last_error: str | None = Field(
        default=None,
        description="Validation or execution error from the previous action",
    )
    step_limit: int = Field(default=12, description="Maximum steps allowed")
    steps_remaining: int = Field(default=12, description="Remaining step budget")
    activity_log: list[str] = Field(
        default_factory=list,
        description="Recent environment events for short-horizon planning",
    )


class SupportOpsState(State):
    """Internal state used for grading and diagnostics."""

    task_id: str | None = Field(default=None, description="Active task id")
    task_title: str | None = Field(default=None, description="Active task title")
    difficulty: DifficultyType | None = Field(default=None, description="Difficulty")
    focused_ticket_id: str | None = Field(
        default=None,
        description="Ticket currently opened by the agent",
    )
    primary_incident_id: str | None = Field(
        default=None,
        description="Main incident id for the task, when one exists",
    )
    completed_milestones: list[str] = Field(
        default_factory=list,
        description="Milestones that have been satisfied",
    )
    guardrail_violations: list[str] = Field(
        default_factory=list,
        description="Guardrail violations triggered during the episode",
    )
    guardrail_penalty_total: float = Field(
        default=0.0,
        description="Sum of sticky penalties from triggered guardrails",
    )
    score: float = Field(default=0.0, description="Current normalized score")
    step_limit: int = Field(default=12, description="Maximum steps for the task")
    last_action_type: str | None = Field(default=None, description="Last action type")
    tickets: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description="Mutable ticket store for the active episode",
    )
    kb_articles: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description="Knowledge base articles available in the active task",
    )
    incidents: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description="Mutable incident records created during the episode",
    )
    last_ticket_search_results: list[str] = Field(
        default_factory=list,
        description="Ticket ids from the most recent ticket search",
    )
    last_kb_search_results: list[str] = Field(
        default_factory=list,
        description="Article ids from the most recent knowledge-base search",
    )
    viewed_ticket_ids: list[str] = Field(
        default_factory=list,
        description="Ticket ids opened during this episode",
    )
    retrieved_ticket_ids: list[str] = Field(
        default_factory=list,
        description="Ticket ids surfaced by any search action",
    )
    retrieved_kb_article_ids: list[str] = Field(
        default_factory=list,
        description="Knowledge-base article ids surfaced by search",
    )
    status_page_updates: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Published public updates",
    )
    action_history: list[str] = Field(
        default_factory=list,
        description="Recent action/event log",
    )
