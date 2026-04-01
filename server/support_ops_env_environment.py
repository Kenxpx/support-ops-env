"""Environment implementation for support operations tasks."""

from __future__ import annotations

from copy import deepcopy
from typing import Any
from uuid import uuid4

from openenv.core.env_server.interfaces import Environment
from openenv.core.env_server.types import EnvironmentMetadata

try:
    from ..models import (
        GuardrailViolation,
        IncidentSummary,
        KnowledgeBaseArticleSummary,
        MilestoneProgress,
        StatusPageUpdate,
        SupportOpsAction,
        SupportOpsObservation,
        SupportOpsState,
        TicketDetail,
        TicketSummary,
    )
    from .tasks import TASKS, TASKS_BY_ID, GuardrailSpec, TaskSpec
except ImportError:
    from models import (
        GuardrailViolation,
        IncidentSummary,
        KnowledgeBaseArticleSummary,
        MilestoneProgress,
        StatusPageUpdate,
        SupportOpsAction,
        SupportOpsObservation,
        SupportOpsState,
        TicketDetail,
        TicketSummary,
    )
    from server.tasks import TASKS, TASKS_BY_ID, GuardrailSpec, TaskSpec


AVAILABLE_ACTIONS = [
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
QUEUE_OPTIONS = [
    "triage",
    "billing",
    "technical_support",
    "incident_response",
    "customer_success",
]
PRIORITY_OPTIONS = ["low", "medium", "high", "urgent"]
STATUS_OPTIONS = ["open", "pending", "resolved", "escalated"]
INCIDENT_SEVERITIES = ["sev3", "sev2", "sev1"]


class SupportOpsEnvironment(Environment[SupportOpsAction, SupportOpsObservation, SupportOpsState]):
    """Stateful support-ticket environment with programmatic graders."""

    SUPPORTS_CONCURRENT_SESSIONS = False

    def __init__(self) -> None:
        super().__init__()
        self._state = SupportOpsState(episode_id=str(uuid4()), step_count=0)
        self._task: TaskSpec | None = None
        self._last_error: str | None = None
        self._last_action_summary = "Environment created."
        self._ticket_search_text: dict[str, str] = {}
        self._kb_search_text: dict[str, str] = {}

    def reset(
        self,
        seed: int | None = None,
        episode_id: str | None = None,
        task_id: str | None = None,
        difficulty: str | None = None,
        **_: Any,
    ) -> SupportOpsObservation:
        selected_task = self._select_task(seed=seed, task_id=task_id, difficulty=difficulty)
        self._task = selected_task
        self._state = SupportOpsState(
            episode_id=episode_id or str(uuid4()),
            step_count=0,
            task_id=selected_task.task_id,
            task_title=selected_task.title,
            difficulty=selected_task.difficulty,
            focused_ticket_id=None,
            primary_incident_id=None,
            completed_milestones=[],
            guardrail_violations=[],
            guardrail_penalty_total=0.0,
            score=0.0,
            step_limit=selected_task.step_limit,
            last_action_type="reset",
            tickets=self._build_ticket_store(selected_task),
            kb_articles=self._build_kb_store(selected_task),
            incidents={},
            last_ticket_search_results=[],
            last_kb_search_results=[],
            viewed_ticket_ids=[],
            retrieved_ticket_ids=[],
            retrieved_kb_article_ids=[],
            status_page_updates=[],
            action_history=[],
        )
        self._last_error = None
        self._rebuild_search_indexes()
        self._log_event(f"Loaded task '{selected_task.task_id}'.")
        self._last_action_summary = f"Loaded task '{selected_task.task_id}'."
        return self._build_observation(reward=0.0, done=False)

    def step(
        self,
        action: SupportOpsAction,
        timeout_s: float | None = None,
        **_: Any,
    ) -> SupportOpsObservation:
        del timeout_s
        if self._task is None:
            raise RuntimeError("Environment has not been reset.")

        if self._is_done():
            self._last_error = "Episode is already complete. Reset before taking more steps."
            self._last_action_summary = "Rejected action after episode completion."
            self._log_event(self._last_action_summary)
            return self._build_observation(reward=-0.05, done=True)

        self._state.step_count += 1
        self._state.last_action_type = action.action_type
        self._last_error = None
        previous_violations = set(self._state.guardrail_violations)

        try:
            self._apply_action(action)
            self._maybe_record_guardrail_violation(action)
        except ValueError as exc:
            self._last_error = str(exc)
            self._last_action_summary = f"Action rejected: {exc}"
            self._log_event(self._last_action_summary)
            done = self._is_done()
            return self._build_observation(reward=-0.05, done=done)

        reward = self._update_progress(previous_violations)
        done = self._is_done()
        return self._build_observation(reward=reward, done=done)

    @property
    def state(self) -> SupportOpsState:
        return self._state

    def get_metadata(self) -> EnvironmentMetadata:
        return EnvironmentMetadata(
            name="support_ops_env",
            description=(
                "A deterministic support-ticket operations benchmark with realistic "
                "routing, retrieval, incident response, sticky guardrail penalties, "
                "and public-update workflows."
            ),
            version="0.3.0",
            author="Codex scaffold",
        )

    def _select_task(
        self,
        seed: int | None,
        task_id: str | None,
        difficulty: str | None,
    ) -> TaskSpec:
        if task_id:
            if task_id not in TASKS_BY_ID:
                raise ValueError(f"Unknown task_id '{task_id}'.")
            return TASKS_BY_ID[task_id]

        if difficulty:
            difficulty_matches = [task for task in TASKS if task.difficulty == difficulty]
            if not difficulty_matches:
                raise ValueError(f"Unknown difficulty '{difficulty}'.")
            return difficulty_matches[0]

        if seed is None:
            return TASKS[0]
        return TASKS[seed % len(TASKS)]

    def _build_ticket_store(self, task: TaskSpec) -> dict[str, dict[str, Any]]:
        store: dict[str, dict[str, Any]] = {}
        for seed_ticket in task.tickets:
            store[seed_ticket.ticket_id] = {
                "ticket_id": seed_ticket.ticket_id,
                "subject": seed_ticket.subject,
                "customer": seed_ticket.customer,
                "customer_tier": seed_ticket.customer_tier,
                "region": seed_ticket.region,
                "product": seed_ticket.product,
                "body": seed_ticket.body,
                "account_owner": seed_ticket.account_owner,
                "impacted_users": seed_ticket.impacted_users,
                "opened_minutes_ago": seed_ticket.opened_minutes_ago,
                "sla_minutes": seed_ticket.sla_minutes,
                "related_ticket_ids": list(seed_ticket.related_ticket_ids),
                "queue": seed_ticket.queue,
                "priority": seed_ticket.priority,
                "status": seed_ticket.status,
                "tags": list(seed_ticket.tags),
                "internal_notes": [],
                "replies": [],
                "duplicate_of": None,
            }
        return store

    def _build_kb_store(self, task: TaskSpec) -> dict[str, dict[str, Any]]:
        return {
            article.article_id: {
                "article_id": article.article_id,
                "title": article.title,
                "summary": article.summary,
                "body": article.body,
                "key_facts": list(article.key_facts),
                "keywords": list(article.keywords),
            }
            for article in task.knowledge_base
        }

    def _build_observation(self, reward: float, done: bool) -> SupportOpsObservation:
        assert self._task is not None

        ticket_summaries = [
            self._ticket_summary(self._state.tickets[ticket_id])
            for ticket_id in sorted(self._state.tickets)
        ]
        ticket_search_results = [
            self._ticket_summary(self._state.tickets[ticket_id])
            for ticket_id in self._state.last_ticket_search_results
            if ticket_id in self._state.tickets
        ]
        kb_search_results = [
            self._kb_summary(self._state.kb_articles[article_id])
            for article_id in self._state.last_kb_search_results
            if article_id in self._state.kb_articles
        ]
        incidents = [
            self._incident_summary(self._state.incidents[incident_id])
            for incident_id in sorted(self._state.incidents)
        ]
        recent_status_updates = [
            StatusPageUpdate.model_validate(update)
            for update in self._state.status_page_updates[-3:]
        ]

        focused_ticket = None
        if self._state.focused_ticket_id:
            focused_ticket = self._ticket_detail(
                self._state.tickets[self._state.focused_ticket_id]
            )

        milestones = [
            MilestoneProgress(
                milestone_id=milestone.milestone_id,
                description=milestone.description,
                weight=milestone.weight,
                completed=milestone.milestone_id in self._state.completed_milestones,
            )
            for milestone in self._task.milestones
        ]
        guardrail_violations = [
            GuardrailViolation(
                violation_id=guardrail.violation_id,
                description=guardrail.description,
                penalty=guardrail.penalty,
            )
            for guardrail in self._task.guardrails
            if guardrail.violation_id in self._state.guardrail_violations
        ]
        steps_remaining = max(self._state.step_limit - self._state.step_count, 0)

        return SupportOpsObservation(
            task_id=self._task.task_id,
            task_title=self._task.title,
            difficulty=self._task.difficulty,
            goal=self._task.goal,
            scenario=self._task.scenario,
            instructions=list(self._task.instructions),
            ticket_summaries=ticket_summaries,
            focused_ticket=focused_ticket,
            ticket_search_results=ticket_search_results,
            kb_search_results=kb_search_results,
            incidents=incidents,
            recent_status_updates=recent_status_updates,
            milestones=milestones,
            guardrail_violations=guardrail_violations,
            available_actions=AVAILABLE_ACTIONS,
            queue_options=QUEUE_OPTIONS,
            priority_options=PRIORITY_OPTIONS,
            status_options=STATUS_OPTIONS,
            incident_severity_options=INCIDENT_SEVERITIES,
            tag_options=list(self._task.allowed_tags),
            progress=self._state.score,
            score=self._state.score,
            guardrail_penalty_total=self._state.guardrail_penalty_total,
            last_action_summary=self._last_action_summary,
            last_error=self._last_error,
            step_limit=self._state.step_limit,
            steps_remaining=steps_remaining,
            activity_log=self._state.action_history[-6:],
            done=done,
            reward=reward,
            metadata={
                "task_score": self._state.score,
                "task_id": self._task.task_id,
                "focused_ticket_id": self._state.focused_ticket_id,
                "completed_milestones": deepcopy(self._state.completed_milestones),
                "guardrail_violations": deepcopy(self._state.guardrail_violations),
                "guardrail_penalty_total": self._state.guardrail_penalty_total,
                "primary_incident_id": self._state.primary_incident_id,
            },
        )

    def _apply_action(self, action: SupportOpsAction) -> None:
        if action.action_type == "noop":
            self._last_action_summary = "No-op action executed."
            self._log_event(self._last_action_summary)
            return

        if action.action_type == "search_tickets":
            query = self._require_text(action.query, "search_tickets requires 'query'.")
            results = self._search_tickets(query)
            result_ids = [ticket["ticket_id"] for ticket in results]
            self._state.last_ticket_search_results = result_ids
            self._merge_unique(self._state.retrieved_ticket_ids, result_ids)
            self._last_action_summary = (
                f"Ticket search for '{query}' returned {', '.join(result_ids) or 'no matches'}."
            )
            self._log_event(self._last_action_summary)
            return

        if action.action_type == "search_kb":
            query = self._require_text(action.query, "search_kb requires 'query'.")
            results = self._search_kb(query)
            result_ids = [article["article_id"] for article in results]
            self._state.last_kb_search_results = result_ids
            self._merge_unique(self._state.retrieved_kb_article_ids, result_ids)
            self._last_action_summary = (
                f"KB search for '{query}' returned {', '.join(result_ids) or 'no matches'}."
            )
            self._log_event(self._last_action_summary)
            return

        if action.action_type == "view_ticket":
            ticket = self._require_ticket(action.ticket_id)
            self._state.focused_ticket_id = ticket["ticket_id"]
            self._merge_unique(self._state.viewed_ticket_ids, [ticket["ticket_id"]])
            self._last_action_summary = f"Opened ticket {ticket['ticket_id']}."
            self._log_event(self._last_action_summary)
            return

        ticket = self._require_ticket(action.ticket_id)

        if action.action_type == "set_queue":
            if not action.queue:
                raise ValueError("set_queue requires 'queue'.")
            if action.queue not in QUEUE_OPTIONS:
                raise ValueError(f"Unsupported queue '{action.queue}'.")
            ticket["queue"] = action.queue
            incident = self._find_incident_for_ticket(ticket["ticket_id"])
            if incident is not None:
                incident["owner_queue"] = action.queue
            self._last_action_summary = f"Moved {ticket['ticket_id']} to queue '{action.queue}'."
            self._log_event(self._last_action_summary)
            return

        if action.action_type == "set_priority":
            if not action.priority:
                raise ValueError("set_priority requires 'priority'.")
            if action.priority not in PRIORITY_OPTIONS:
                raise ValueError(f"Unsupported priority '{action.priority}'.")
            ticket["priority"] = action.priority
            self._last_action_summary = (
                f"Set priority for {ticket['ticket_id']} to '{action.priority}'."
            )
            self._log_event(self._last_action_summary)
            return

        if action.action_type == "add_tag":
            normalized_tag = self._require_text(
                action.tag,
                "add_tag requires non-empty 'tag'.",
            ).lower()
            assert self._task is not None
            if normalized_tag not in self._task.allowed_tags:
                raise ValueError(
                    f"Unsupported tag '{normalized_tag}'. Allowed tags: {', '.join(self._task.allowed_tags)}"
                )
            if normalized_tag not in ticket["tags"]:
                ticket["tags"].append(normalized_tag)
                ticket["tags"].sort()
                self._update_ticket_search_text(ticket["ticket_id"])
            self._last_action_summary = (
                f"Added tag '{normalized_tag}' to {ticket['ticket_id']}."
            )
            self._log_event(self._last_action_summary)
            return

        if action.action_type == "add_internal_note":
            note = self._require_text(
                action.note,
                "add_internal_note requires non-empty 'note'.",
            )
            ticket["internal_notes"].append(note)
            self._last_action_summary = f"Added internal note to {ticket['ticket_id']}."
            self._log_event(self._last_action_summary)
            return

        if action.action_type == "send_reply":
            reply = self._require_text(
                action.reply,
                "send_reply requires non-empty 'reply'.",
            )
            ticket["replies"].append(reply)
            self._last_action_summary = f"Sent customer reply on {ticket['ticket_id']}."
            self._log_event(self._last_action_summary)
            return

        if action.action_type == "mark_status":
            if not action.status:
                raise ValueError("mark_status requires 'status'.")
            if action.status not in STATUS_OPTIONS:
                raise ValueError(f"Unsupported status '{action.status}'.")
            ticket["status"] = action.status
            self._last_action_summary = (
                f"Marked {ticket['ticket_id']} as '{action.status}'."
            )
            self._log_event(self._last_action_summary)
            return

        if action.action_type == "link_duplicate":
            duplicate_of = self._require_text(
                action.duplicate_of,
                "link_duplicate requires 'duplicate_of'.",
            )
            if duplicate_of not in self._state.tickets:
                raise ValueError(f"Unknown primary ticket '{duplicate_of}'.")
            if duplicate_of == ticket["ticket_id"]:
                raise ValueError("A ticket cannot be a duplicate of itself.")
            ticket["duplicate_of"] = duplicate_of
            incident = self._find_incident_for_ticket(duplicate_of)
            if incident is not None and ticket["ticket_id"] not in incident["linked_ticket_ids"]:
                incident["linked_ticket_ids"].append(ticket["ticket_id"])
            self._last_action_summary = (
                f"Linked {ticket['ticket_id']} as a duplicate of {duplicate_of}."
            )
            self._log_event(self._last_action_summary)
            return

        if action.action_type == "create_incident":
            title = self._require_text(
                action.incident_title,
                "create_incident requires 'incident_title'.",
            )
            existing = self._find_incident_for_ticket(ticket["ticket_id"])
            if existing is not None:
                self._state.primary_incident_id = existing["incident_id"]
                self._last_action_summary = (
                    f"Incident {existing['incident_id']} already exists for {ticket['ticket_id']}."
                )
                self._log_event(self._last_action_summary)
                return

            incident_id = f"INC-{len(self._state.incidents) + 1:03d}"
            incident = {
                "incident_id": incident_id,
                "title": title,
                "severity": "sev3",
                "status": "investigating",
                "owner_queue": ticket["queue"],
                "linked_ticket_ids": [ticket["ticket_id"]],
                "public_updates_count": 0,
                "updates": [],
            }
            self._state.incidents[incident_id] = incident
            if ticket["ticket_id"] == self._task.primary_ticket_id:
                self._state.primary_incident_id = incident_id
            self._last_action_summary = (
                f"Created incident {incident_id} for ticket {ticket['ticket_id']}."
            )
            self._log_event(self._last_action_summary)
            return

        if action.action_type == "set_incident_severity":
            incident = self._require_incident(action.incident_id)
            if not action.severity:
                raise ValueError("set_incident_severity requires 'severity'.")
            if action.severity not in INCIDENT_SEVERITIES:
                raise ValueError(f"Unsupported severity '{action.severity}'.")
            incident["severity"] = action.severity
            self._last_action_summary = (
                f"Set severity for {incident['incident_id']} to {action.severity}."
            )
            self._log_event(self._last_action_summary)
            return

        if action.action_type == "post_status_update":
            incident = self._require_incident(action.incident_id)
            message = self._require_text(
                action.message,
                "post_status_update requires 'message'.",
            )
            update = {
                "incident_id": incident["incident_id"],
                "sequence": len(incident["updates"]) + 1,
                "message": message,
            }
            incident["updates"].append(update)
            incident["public_updates_count"] = len(incident["updates"])
            self._state.status_page_updates.append(update)
            self._last_action_summary = (
                f"Published status update #{update['sequence']} for {incident['incident_id']}."
            )
            self._log_event(self._last_action_summary)
            return

        raise ValueError(f"Unsupported action '{action.action_type}'.")

    def _ticket_summary(self, ticket: dict[str, Any]) -> TicketSummary:
        return TicketSummary(
            ticket_id=ticket["ticket_id"],
            subject=ticket["subject"],
            customer=ticket["customer"],
            customer_tier=ticket["customer_tier"],
            queue=ticket["queue"],
            priority=ticket["priority"],
            status=ticket["status"],
            tags=deepcopy(ticket["tags"]),
            region=ticket["region"],
            product=ticket["product"],
            impacted_users=ticket["impacted_users"],
            sla_minutes=ticket["sla_minutes"],
        )

    def _ticket_detail(self, ticket: dict[str, Any]) -> TicketDetail:
        return TicketDetail(
            ticket_id=ticket["ticket_id"],
            subject=ticket["subject"],
            customer=ticket["customer"],
            customer_tier=ticket["customer_tier"],
            queue=ticket["queue"],
            priority=ticket["priority"],
            status=ticket["status"],
            tags=deepcopy(ticket["tags"]),
            region=ticket["region"],
            product=ticket["product"],
            impacted_users=ticket["impacted_users"],
            sla_minutes=ticket["sla_minutes"],
            body=ticket["body"],
            account_owner=ticket["account_owner"],
            opened_minutes_ago=ticket["opened_minutes_ago"],
            related_ticket_ids=deepcopy(ticket["related_ticket_ids"]),
            internal_notes=deepcopy(ticket["internal_notes"]),
            replies=deepcopy(ticket["replies"]),
            duplicate_of=ticket["duplicate_of"],
        )

    def _kb_summary(self, article: dict[str, Any]) -> KnowledgeBaseArticleSummary:
        return KnowledgeBaseArticleSummary(
            article_id=article["article_id"],
            title=article["title"],
            summary=article["summary"],
            key_facts=deepcopy(article["key_facts"]),
        )

    def _incident_summary(self, incident: dict[str, Any]) -> IncidentSummary:
        return IncidentSummary(
            incident_id=incident["incident_id"],
            title=incident["title"],
            severity=incident["severity"],
            status=incident["status"],
            owner_queue=incident["owner_queue"],
            linked_ticket_ids=deepcopy(incident["linked_ticket_ids"]),
            public_updates_count=incident["public_updates_count"],
        )

    def _require_ticket(self, ticket_id: str | None) -> dict[str, Any]:
        if not ticket_id:
            raise ValueError("This action requires 'ticket_id'.")
        if ticket_id not in self._state.tickets:
            raise ValueError(f"Unknown ticket '{ticket_id}'.")
        return self._state.tickets[ticket_id]

    def _require_incident(self, incident_id: str | None) -> dict[str, Any]:
        if not incident_id:
            raise ValueError("This action requires 'incident_id'.")
        if incident_id not in self._state.incidents:
            raise ValueError(f"Unknown incident '{incident_id}'.")
        return self._state.incidents[incident_id]

    def _require_text(self, value: str | None, error_message: str) -> str:
        text = (value or "").strip()
        if not text:
            raise ValueError(error_message)
        return text

    def _search_tickets(self, query: str) -> list[dict[str, Any]]:
        tokens = self._tokenize(query)
        scored: list[tuple[int, dict[str, Any]]] = []
        for ticket_id, ticket in self._state.tickets.items():
            haystack = self._ticket_search_text[ticket_id]
            score = sum(1 for token in tokens if token in haystack)
            if score > 0:
                scored.append((score, ticket))
        scored.sort(key=lambda item: (-item[0], item[1]["ticket_id"]))
        return [ticket for _, ticket in scored[:4]]

    def _search_kb(self, query: str) -> list[dict[str, Any]]:
        tokens = self._tokenize(query)
        scored: list[tuple[int, dict[str, Any]]] = []
        for article_id, article in self._state.kb_articles.items():
            haystack = self._kb_search_text[article_id]
            score = sum(1 for token in tokens if token in haystack)
            if score > 0:
                scored.append((score, article))
        scored.sort(key=lambda item: (-item[0], item[1]["article_id"]))
        return [article for _, article in scored[:4]]

    def _find_incident_for_ticket(self, ticket_id: str) -> dict[str, Any] | None:
        for incident in self._state.incidents.values():
            if ticket_id in incident["linked_ticket_ids"]:
                return incident
        return None

    def _update_progress(self, previous_violations: set[str]) -> float:
        assert self._task is not None
        checks = self._evaluate_task()
        previous = set(self._state.completed_milestones)
        newly_completed: list[str] = []
        reward = 0.0

        for milestone in self._task.milestones:
            if checks.get(milestone.milestone_id) and milestone.milestone_id not in previous:
                newly_completed.append(milestone.milestone_id)
                reward += milestone.weight

        if newly_completed:
            self._state.completed_milestones.extend(newly_completed)
            self._state.completed_milestones.sort()

        score = 0.0
        for milestone in self._task.milestones:
            if milestone.milestone_id in self._state.completed_milestones:
                score += milestone.weight

        penalty_delta = self._guardrail_penalty(
            set(self._state.guardrail_violations) - previous_violations
        )
        reward -= penalty_delta
        self._state.guardrail_penalty_total = round(
            self._guardrail_penalty(set(self._state.guardrail_violations)),
            4,
        )
        self._state.score = round(
            max(0.0, min(score - self._state.guardrail_penalty_total, 1.0)),
            4,
        )
        return reward

    def _maybe_record_guardrail_violation(self, action: SupportOpsAction) -> None:
        assert self._task is not None
        task_id = self._task.task_id

        if task_id == "easy_refund_request":
            if action.action_type == "mark_status" and action.status == "resolved":
                ticket = self._state.tickets["T-1001"]
                if not any(
                    self._contains_all(reply, ["refund", "3-5", "business"])
                    for reply in ticket["replies"]
                ):
                    self._record_guardrail_violation("resolved_before_refund_guidance")
            return

        if task_id == "medium_sso_lockout":
            if action.action_type == "mark_status" and action.status == "resolved":
                self._record_guardrail_violation("resolved_without_customer_input")
            if action.action_type == "send_reply":
                reply = (action.reply or "").lower()
                has_metadata_request = (
                    "saml" in reply
                    and "metadata" in reply
                    and ("acs" in reply or "entity id" in reply)
                )
                if not has_metadata_request:
                    self._record_guardrail_violation("reply_missing_metadata_request")
            return

        if task_id == "hard_vip_outage_duplicate":
            if action.action_type == "mark_status" and action.status != "escalated":
                self._record_guardrail_violation("deescalated_live_outage")
            if action.action_type == "set_incident_severity" and action.severity != "sev1":
                self._record_guardrail_violation("under_severitized_major_outage")
            if action.action_type == "post_status_update":
                message = (action.message or "").lower()
                if "investigat" not in message or "eu-west" not in message:
                    self._record_guardrail_violation("weak_public_status_update")
            return

        if task_id == "hard_partner_token_leak":
            if action.action_type == "post_status_update":
                self._record_guardrail_violation("public_status_update_on_security_incident")
            if action.action_type == "set_incident_severity" and action.severity != "sev2":
                self._record_guardrail_violation("wrong_severity_for_security_incident")
            if action.action_type == "mark_status" and action.status != "escalated":
                self._record_guardrail_violation("premature_security_closure")
            return

    def _record_guardrail_violation(self, violation_id: str) -> None:
        if violation_id not in self._state.guardrail_violations:
            self._state.guardrail_violations.append(violation_id)
            self._state.guardrail_violations.sort()

    def _guardrail_penalty(self, violation_ids: set[str]) -> float:
        assert self._task is not None
        penalties = {
            guardrail.violation_id: guardrail.penalty for guardrail in self._task.guardrails
        }
        return round(sum(penalties[violation_id] for violation_id in violation_ids), 4)

    def _evaluate_task(self) -> dict[str, bool]:
        assert self._task is not None
        task_id = self._task.task_id

        if task_id == "easy_refund_request":
            ticket = self._state.tickets["T-1001"]
            return {
                "searched_kb_refund": "KB-REFUND-01" in self._state.retrieved_kb_article_ids,
                "opened_primary": "T-1001" in self._state.viewed_ticket_ids,
                "queue_billing": ticket["queue"] == "billing",
                "priority_medium": ticket["priority"] == "medium",
                "tag_refund_context": {"refund", "duplicate_charge"}.issubset(ticket["tags"]),
                "note_duplicate_charge": any(
                    self._contains_all(note, ["duplicate", "charge"])
                    or self._contains_all(note, ["charged", "twice"])
                    for note in ticket["internal_notes"]
                ),
                "reply_refund_window": any(
                    self._contains_all(reply, ["refund", "3-5", "business"])
                    for reply in ticket["replies"]
                ),
                "status_resolved": ticket["status"] == "resolved",
            }

        if task_id == "medium_sso_lockout":
            ticket = self._state.tickets["T-2001"]
            return {
                "searched_kb_sso": "KB-SSO-07" in self._state.retrieved_kb_article_ids,
                "opened_primary": "T-2001" in self._state.viewed_ticket_ids,
                "queue_technical_support": ticket["queue"] == "technical_support",
                "priority_high": ticket["priority"] == "high",
                "tag_sso_enterprise": {"sso", "enterprise_auth"}.issubset(ticket["tags"]),
                "note_idp_metadata": any(
                    self._contains_all(note, ["idp", "metadata"])
                    or self._contains_all(note, ["acs", "entity"])
                    for note in ticket["internal_notes"]
                ),
                "reply_saml_metadata": any(
                    self._contains_all(reply, ["saml", "metadata"])
                    and ("acs" in reply.lower() or "entity id" in reply.lower())
                    for reply in ticket["replies"]
                ),
                "status_pending": ticket["status"] == "pending",
            }

        if task_id == "hard_vip_outage_duplicate":
            primary = self._state.tickets["T-3001"]
            duplicate = self._state.tickets["T-3002"]
            incident = self._find_incident_for_ticket("T-3001")
            incident_update_ok = False
            customer_reply_ok = False
            incident_created = incident is not None
            severity_sev1 = False

            if incident is not None:
                severity_sev1 = incident["severity"] == "sev1"
                incident_update_ok = any(
                    self._contains_all(update["message"], ["investigat", "eu-west"])
                    and ("checkout" in update["message"].lower() or "status" in update["message"].lower())
                    for update in incident["updates"]
                )
                customer_reply_ok = any(
                    "status page" in reply.lower() and "investigat" in reply.lower()
                    for reply in primary["replies"]
                )

            return {
                "searched_related_tickets": "T-3002" in self._state.retrieved_ticket_ids,
                "searched_incident_playbook": "KB-INC-01" in self._state.retrieved_kb_article_ids,
                "opened_primary": "T-3001" in self._state.viewed_ticket_ids,
                "queue_incident_response": primary["queue"] == "incident_response",
                "priority_urgent": primary["priority"] == "urgent",
                "create_incident": incident_created,
                "severity_sev1": severity_sev1,
                "duplicate_linked": duplicate["duplicate_of"] == "T-3001",
                "tag_outage_vip": {"outage", "vip"}.issubset(primary["tags"]),
                "note_region_component": any(
                    self._contains_all(note, ["eu-west", "checkout", "api"])
                    for note in primary["internal_notes"]
                ),
                "status_page_update": incident_update_ok,
                "customer_reply_refs_status_page": customer_reply_ok,
                "status_escalated": primary["status"] == "escalated",
            }

        if task_id == "hard_partner_token_leak":
            primary = self._state.tickets["T-4001"]
            duplicate = self._state.tickets["T-4002"]
            incident = self._find_incident_for_ticket("T-4001")
            incident_created = incident is not None
            severity_sev2 = False

            if incident is not None:
                severity_sev2 = incident["severity"] == "sev2"

            return {
                "searched_related_tickets": "T-4002" in self._state.retrieved_ticket_ids,
                "searched_security_playbook": "KB-SEC-09" in self._state.retrieved_kb_article_ids,
                "opened_primary": "T-4001" in self._state.viewed_ticket_ids,
                "queue_incident_response": primary["queue"] == "incident_response",
                "priority_urgent": primary["priority"] == "urgent",
                "create_incident": incident_created,
                "severity_sev2": severity_sev2,
                "duplicate_linked": duplicate["duplicate_of"] == "T-4001",
                "tag_security_token_leak": {"security", "token_leak"}.issubset(primary["tags"]),
                "note_rotation_audit": any(
                    ("rotate" in note.lower() or "revoke" in note.lower())
                    and "audit" in note.lower()
                    and "logs" in note.lower()
                    for note in primary["internal_notes"]
                ),
                "reply_rotate_monitor": any(
                    ("rotate" in reply.lower() or "revoke" in reply.lower())
                    and ("audit logs" in reply.lower() or "monitor" in reply.lower())
                    for reply in primary["replies"]
                ),
                "status_escalated": primary["status"] == "escalated",
            }

        raise RuntimeError(f"Unhandled task '{task_id}'.")

    def _is_done(self) -> bool:
        assert self._task is not None
        return self._all_milestones_completed() or self._state.step_count >= self._task.step_limit

    def _all_milestones_completed(self) -> bool:
        assert self._task is not None
        completed = set(self._state.completed_milestones)
        return all(
            milestone.milestone_id in completed for milestone in self._task.milestones
        )

    def _merge_unique(self, target: list[str], values: list[str]) -> None:
        for value in values:
            if value not in target:
                target.append(value)

    def _rebuild_search_indexes(self) -> None:
        self._ticket_search_text = {}
        for ticket_id in self._state.tickets:
            self._update_ticket_search_text(ticket_id)

        self._kb_search_text = {
            article_id: " ".join(
                [
                    article["article_id"],
                    article["title"],
                    article["summary"],
                    article["body"],
                    " ".join(article["keywords"]),
                    " ".join(article["key_facts"]),
                ]
            ).lower()
            for article_id, article in self._state.kb_articles.items()
        }

    def _update_ticket_search_text(self, ticket_id: str) -> None:
        ticket = self._state.tickets[ticket_id]
        self._ticket_search_text[ticket_id] = " ".join(
            [
                ticket["ticket_id"],
                ticket["subject"],
                ticket["customer"],
                ticket["product"],
                ticket["region"],
                ticket["body"],
                " ".join(ticket["tags"]),
            ]
        ).lower()

    def _log_event(self, message: str) -> None:
        self._state.action_history.append(message)
        self._state.action_history = self._state.action_history[-20:]

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return [token for token in text.lower().replace("-", " ").split() if token]

    @staticmethod
    def _contains_all(text: str, needles: list[str]) -> bool:
        haystack = text.lower()
        return all(needle.lower() in haystack for needle in needles)
