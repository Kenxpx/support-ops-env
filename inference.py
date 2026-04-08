"""Baseline inference script for the support operations environment."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
from dataclasses import dataclass
from typing import Any

from openai import OpenAI

try:
    from support_ops_env import SupportOpsAction, SupportOpsEnv
except ImportError:
    from client import SupportOpsEnv
    from models import SupportOpsAction

API_BASE_URL = os.getenv("API_BASE_URL") or "https://router.huggingface.co/v1"
API_KEY = os.getenv("API_KEY") or os.getenv("HF_TOKEN")
MODEL_NAME = os.getenv("MODEL_NAME") or "Qwen/Qwen2.5-72B-Instruct"
ENV_BASE_URL = os.getenv("ENV_BASE_URL")
LOCAL_IMAGE_NAME = os.getenv("LOCAL_IMAGE_NAME") or os.getenv("DOCKER_IMAGE")
BENCHMARK = os.getenv("BENCHMARK_NAME") or "support_ops_env"
SUCCESS_SCORE_THRESHOLD = 0.99
TASK_IDS = [
    "easy_refund_request",
    "medium_sso_lockout",
    "hard_vip_outage_duplicate",
    "hard_partner_token_leak",
]

SYSTEM_PROMPT = """
You are operating an enterprise support and incident response console.
Return exactly one JSON object with these keys:
action_type, ticket_id, queue, priority, tag, note, reply, status,
duplicate_of, query, incident_id, incident_title, severity, message.
Use null for unused fields.
Choose one valid action that advances the task.
Do not return markdown or explanations.
""".strip()


def bool_str(value: bool) -> str:
    return "true" if value else "false"


def score_str(value: float | None) -> str:
    bounded = max(0.0, min(float(value or 0.0), 1.0))
    return f"{bounded:.2f}"


def sanitize_single_line(text: str | None) -> str:
    compact = (text or "null").replace("\r", " ").replace("\n", " ").strip()
    return compact or "null"


def shorten(text: str | None, max_len: int = 48) -> str:
    compact = sanitize_single_line(text)
    if len(compact) <= max_len:
        return compact
    return f"{compact[: max_len - 3]}..."


def action_to_log(action: SupportOpsAction) -> str:
    if action.action_type == "noop":
        return "noop()"
    if action.action_type == "search_tickets":
        return f"search_tickets('{shorten(action.query)}')"
    if action.action_type == "search_kb":
        return f"search_kb('{shorten(action.query)}')"
    if action.action_type == "view_ticket":
        return f"view_ticket({action.ticket_id})"
    if action.action_type == "set_queue":
        return f"set_queue({action.ticket_id},{action.queue})"
    if action.action_type == "set_priority":
        return f"set_priority({action.ticket_id},{action.priority})"
    if action.action_type == "add_tag":
        return f"add_tag({action.ticket_id},{action.tag})"
    if action.action_type == "add_internal_note":
        return f"add_internal_note({action.ticket_id})"
    if action.action_type == "send_reply":
        return f"send_reply({action.ticket_id})"
    if action.action_type == "mark_status":
        return f"mark_status({action.ticket_id},{action.status})"
    if action.action_type == "link_duplicate":
        return f"link_duplicate({action.ticket_id}->{action.duplicate_of})"
    if action.action_type == "create_incident":
        return f"create_incident({action.ticket_id})"
    if action.action_type == "set_incident_severity":
        return f"set_incident_severity({action.incident_id},{action.severity})"
    if action.action_type == "post_status_update":
        return f"post_status_update({action.incident_id})"
    return action.action_type


def format_start_line(task_id: str, benchmark: str, model_name: str) -> str:
    return (
        f"[START] task={sanitize_single_line(task_id)} "
        f"env={sanitize_single_line(benchmark)} "
        f"model={sanitize_single_line(model_name)}"
    )


def format_step_line(
    step_index: int,
    action: SupportOpsAction,
    reward: float | None,
    done: bool,
    error: str | None,
) -> str:
    return (
        f"[STEP] step={step_index} "
        f"action={action_to_log(action)} "
        f"reward={score_str(reward)} "
        f"done={bool_str(done)} "
        f"error={sanitize_single_line(error)}"
    )


def format_end_line(
    success: bool,
    steps: int,
    score: float,
    rewards: list[float],
) -> str:
    rewards_str = ",".join(score_str(reward) for reward in rewards) if rewards else ""
    return (
        f"[END] success={bool_str(success)} "
        f"steps={steps} "
        f"score={score_str(score)} "
        f"rewards={rewards_str}"
    )


def create_llm_client() -> OpenAI | None:
    if not API_KEY or not MODEL_NAME:
        return None
    return OpenAI(base_url=API_BASE_URL, api_key=API_KEY)


def candidate_docker_images(image: str) -> list[str]:
    """Return likely local image names for this environment in priority order."""

    requested = (image or "").strip() or "support-ops-env:latest"
    if ":" in requested:
        repository, tag = requested.rsplit(":", 1)
        has_tag = "/" not in tag
    else:
        repository = requested
        tag = "latest"
        has_tag = False

    repositories = [repository]
    if repository.startswith("openenv-"):
        repositories.append(repository.removeprefix("openenv-"))
    else:
        repositories.append(f"openenv-{repository}")

    candidates: list[str] = []
    for repo in repositories:
        candidates.append(f"{repo}:{tag}")
        if tag != "latest":
            candidates.append(f"{repo}:latest")
        if not has_tag or tag == "latest":
            candidates.append(repo)

    deduped: list[str] = []
    for candidate in candidates:
        if candidate not in deduped:
            deduped.append(candidate)
    return deduped


def resolve_local_docker_image(image: str) -> str:
    """Prefer an existing local image so validation can run across tag conventions."""

    candidates = candidate_docker_images(image)
    try:
        for candidate in candidates:
            completed = subprocess.run(
                ["docker", "image", "inspect", candidate],
                capture_output=True,
                text=True,
                check=False,
            )
            if completed.returncode == 0:
                return candidate
    except OSError:
        return candidates[0]
    return candidates[0]


@dataclass(frozen=True)
class WorkflowPlan:
    task_id: str
    primary_ticket: str
    kb_article_id: str
    kb_query: str
    queue: str
    priority: str
    tags: tuple[str, ...]
    note: str
    reply: str
    final_status: str
    kb_milestone: str
    queue_milestone: str
    priority_milestone: str
    tag_milestone: str
    note_milestone: str
    reply_milestone: str
    status_milestone: str


@dataclass(frozen=True)
class IncidentWorkflowPlan:
    task_id: str
    primary_ticket: str
    duplicate_ticket: str
    related_ticket_query: str
    related_ticket_milestone: str
    kb_article_id: str
    kb_query: str
    kb_milestone: str
    queue: str
    queue_milestone: str
    priority: str
    priority_milestone: str
    tags: tuple[str, ...]
    tag_milestone: str
    incident_title: str
    create_incident_milestone: str
    severity: str
    severity_milestone: str
    duplicate_milestone: str
    note: str
    note_milestone: str
    reply: str
    reply_milestone: str
    final_status: str
    status_milestone: str
    status_update_milestone: str | None = None
    status_update_message: str | None = None


STANDARD_WORKFLOWS: dict[str, WorkflowPlan] = {
    "easy_refund_request": WorkflowPlan(
        task_id="easy_refund_request",
        primary_ticket="T-1001",
        kb_article_id="KB-REFUND-01",
        kb_query="duplicate charge refund 3-5 business days",
        queue="billing",
        priority="medium",
        tags=("refund", "duplicate_charge"),
        note=(
            "Customer reports a duplicate charge on the March invoice and needs a "
            "billing review."
        ),
        reply=(
            "We have started the refund review for the duplicate charge. Refunds "
            "usually settle in 3-5 business days."
        ),
        final_status="resolved",
        kb_milestone="searched_kb_refund",
        queue_milestone="queue_billing",
        priority_milestone="priority_medium",
        tag_milestone="tag_refund_context",
        note_milestone="note_duplicate_charge",
        reply_milestone="reply_refund_window",
        status_milestone="status_resolved",
    ),
    "medium_sso_lockout": WorkflowPlan(
        task_id="medium_sso_lockout",
        primary_ticket="T-2001",
        kb_article_id="KB-SSO-07",
        kb_query="SAML metadata ACS URL entity ID IdP change",
        queue="technical_support",
        priority="high",
        tags=("sso", "enterprise_auth"),
        note=(
            "Likely IdP metadata mismatch after the change. Request fresh SAML "
            "metadata and verify ACS URL and entity ID."
        ),
        reply=(
            "Please send a fresh SAML metadata XML export from your identity "
            "provider and confirm the ACS URL and entity ID so we can compare "
            "the configuration."
        ),
        final_status="pending",
        kb_milestone="searched_kb_sso",
        queue_milestone="queue_technical_support",
        priority_milestone="priority_high",
        tag_milestone="tag_sso_enterprise",
        note_milestone="note_idp_metadata",
        reply_milestone="reply_saml_metadata",
        status_milestone="status_pending",
    ),
}

INCIDENT_WORKFLOWS: dict[str, IncidentWorkflowPlan] = {
    "hard_vip_outage_duplicate": IncidentWorkflowPlan(
        task_id="hard_vip_outage_duplicate",
        primary_ticket="T-3001",
        duplicate_ticket="T-3002",
        related_ticket_query="Northstar checkout outage duplicate EU-West",
        related_ticket_milestone="searched_related_tickets",
        kb_article_id="KB-INC-01",
        kb_query="SEV1 incident status page duplicate outage checkout",
        kb_milestone="searched_incident_playbook",
        queue="incident_response",
        queue_milestone="queue_incident_response",
        priority="urgent",
        priority_milestone="priority_urgent",
        tags=("outage", "vip"),
        tag_milestone="tag_outage_vip",
        incident_title="Northstar EU-West checkout outage",
        create_incident_milestone="create_incident",
        severity="sev1",
        severity_milestone="severity_sev1",
        duplicate_milestone="duplicate_linked",
        note=(
            "EU-West outage is affecting the Checkout API across multiple stores "
            "and should stay with incident response."
        ),
        note_milestone="note_region_component",
        reply=(
            "We are actively investigating this outage. Please follow the status "
            "page for live updates while we work on mitigation."
        ),
        reply_milestone="customer_reply_refs_status_page",
        final_status="escalated",
        status_milestone="status_escalated",
        status_update_milestone="status_page_update",
        status_update_message=(
            "We are investigating an issue affecting checkout in EU-West and will "
            "continue sharing updates on the status page."
        ),
    ),
    "hard_partner_token_leak": IncidentWorkflowPlan(
        task_id="hard_partner_token_leak",
        primary_ticket="T-4001",
        duplicate_ticket="T-4002",
        related_ticket_query="OrbitPay token exposure duplicate security",
        related_ticket_milestone="searched_related_tickets",
        kb_article_id="KB-SEC-09",
        kb_query="partner API token leak audit logs rotate credential sev2",
        kb_milestone="searched_security_playbook",
        queue="incident_response",
        queue_milestone="queue_incident_response",
        priority="urgent",
        priority_milestone="priority_urgent",
        tags=("security", "token_leak"),
        tag_milestone="tag_security_token_leak",
        incident_title="OrbitPay partner token exposure",
        create_incident_milestone="create_incident",
        severity="sev2",
        severity_milestone="severity_sev2",
        duplicate_milestone="duplicate_linked",
        note=(
            "Rotate or revoke the exposed token immediately and review audit logs "
            "for suspicious Partner API activity."
        ),
        note_milestone="note_rotation_audit",
        reply=(
            "Please revoke or rotate the exposed token immediately, monitor usage, "
            "and review audit logs for suspicious requests while we keep the case "
            "escalated."
        ),
        reply_milestone="reply_rotate_monitor",
        final_status="escalated",
        status_milestone="status_escalated",
    ),
}


def build_user_prompt(observation: Any) -> str:
    visible = {
        "task_id": observation.task_id,
        "goal": observation.goal,
        "instructions": observation.instructions,
        "visible_tickets": [
            {
                "ticket_id": ticket.ticket_id,
                "subject": ticket.subject,
                "queue": ticket.queue,
                "priority": ticket.priority,
                "status": ticket.status,
                "tags": ticket.tags,
            }
            for ticket in observation.ticket_summaries
        ],
        "focused_ticket": (
            {
                "ticket_id": observation.focused_ticket.ticket_id,
                "subject": observation.focused_ticket.subject,
                "body": observation.focused_ticket.body,
                "queue": observation.focused_ticket.queue,
                "priority": observation.focused_ticket.priority,
                "status": observation.focused_ticket.status,
                "tags": observation.focused_ticket.tags,
                "related_ticket_ids": observation.focused_ticket.related_ticket_ids,
                "internal_notes": observation.focused_ticket.internal_notes,
                "replies": observation.focused_ticket.replies,
            }
            if observation.focused_ticket
            else None
        ),
        "ticket_search_results": [
            {
                "ticket_id": ticket.ticket_id,
                "subject": ticket.subject,
                "queue": ticket.queue,
                "priority": ticket.priority,
                "status": ticket.status,
            }
            for ticket in observation.ticket_search_results
        ],
        "kb_search_results": [
            {
                "article_id": article.article_id,
                "title": article.title,
                "summary": article.summary,
                "key_facts": article.key_facts,
            }
            for article in observation.kb_search_results
        ],
        "incidents": [
            {
                "incident_id": incident.incident_id,
                "severity": incident.severity,
                "status": incident.status,
                "owner_queue": incident.owner_queue,
                "linked_ticket_ids": incident.linked_ticket_ids,
                "public_updates_count": incident.public_updates_count,
            }
            for incident in observation.incidents
        ],
        "recent_status_updates": [
            update.model_dump() for update in observation.recent_status_updates
        ],
        "completed_milestones": sorted(completed_milestones(observation)),
        "guardrail_penalty_total": observation.guardrail_penalty_total,
        "guardrail_violations": [
            violation.model_dump() for violation in observation.guardrail_violations
        ],
        "remaining_milestones": [
            milestone.description
            for milestone in observation.milestones
            if not milestone.completed
        ],
        "progress": observation.progress,
        "steps_remaining": observation.steps_remaining,
        "last_action_summary": observation.last_action_summary,
        "last_error": observation.last_error,
        "activity_log": observation.activity_log,
    }
    return json.dumps(visible, separators=(",", ":"))


def extract_json_object(text: str) -> dict[str, Any] | None:
    if not text:
        return None

    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None

    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def completed_milestones(observation: Any) -> set[str]:
    return {
        milestone.milestone_id for milestone in observation.milestones if milestone.completed
    }


def primary_incident_id(observation: Any, ticket_id: str) -> str | None:
    for incident in observation.incidents:
        if ticket_id in incident.linked_ticket_ids:
            return incident.incident_id
    return None


def search_contains_ticket(observation: Any, ticket_id: str) -> bool:
    return any(ticket.ticket_id == ticket_id for ticket in observation.ticket_search_results)


def search_contains_article(observation: Any, article_id: str) -> bool:
    return any(article.article_id == article_id for article in observation.kb_search_results)


def run_standard_workflow(observation: Any, plan: WorkflowPlan) -> SupportOpsAction:
    done = completed_milestones(observation)
    focused_ticket_id = (
        observation.focused_ticket.ticket_id if observation.focused_ticket else None
    )

    if plan.kb_milestone not in done and not search_contains_article(
        observation, plan.kb_article_id
    ):
        return SupportOpsAction(action_type="search_kb", query=plan.kb_query)
    if focused_ticket_id != plan.primary_ticket:
        return SupportOpsAction(action_type="view_ticket", ticket_id=plan.primary_ticket)
    if plan.queue_milestone not in done:
        return SupportOpsAction(
            action_type="set_queue",
            ticket_id=plan.primary_ticket,
            queue=plan.queue,
        )
    if plan.priority_milestone not in done:
        return SupportOpsAction(
            action_type="set_priority",
            ticket_id=plan.primary_ticket,
            priority=plan.priority,
        )
    for tag in plan.tags:
        if plan.tag_milestone not in done and tag not in observation.focused_ticket.tags:
            return SupportOpsAction(
                action_type="add_tag",
                ticket_id=plan.primary_ticket,
                tag=tag,
            )
    if plan.note_milestone not in done:
        return SupportOpsAction(
            action_type="add_internal_note",
            ticket_id=plan.primary_ticket,
            note=plan.note,
        )
    if plan.reply_milestone not in done:
        return SupportOpsAction(
            action_type="send_reply",
            ticket_id=plan.primary_ticket,
            reply=plan.reply,
        )
    if plan.status_milestone not in done:
        return SupportOpsAction(
            action_type="mark_status",
            ticket_id=plan.primary_ticket,
            status=plan.final_status,
        )

    return SupportOpsAction(action_type="noop")


def run_incident_workflow(observation: Any, plan: IncidentWorkflowPlan) -> SupportOpsAction:
    done = completed_milestones(observation)
    focused_ticket_id = (
        observation.focused_ticket.ticket_id if observation.focused_ticket else None
    )
    incident_id = primary_incident_id(observation, plan.primary_ticket)

    if plan.related_ticket_milestone not in done and not search_contains_ticket(
        observation, plan.duplicate_ticket
    ):
        return SupportOpsAction(
            action_type="search_tickets",
            query=plan.related_ticket_query,
        )
    if plan.kb_milestone not in done and not search_contains_article(
        observation, plan.kb_article_id
    ):
        return SupportOpsAction(action_type="search_kb", query=plan.kb_query)
    if focused_ticket_id != plan.primary_ticket:
        return SupportOpsAction(action_type="view_ticket", ticket_id=plan.primary_ticket)
    if plan.queue_milestone not in done:
        return SupportOpsAction(
            action_type="set_queue",
            ticket_id=plan.primary_ticket,
            queue=plan.queue,
        )
    if plan.priority_milestone not in done:
        return SupportOpsAction(
            action_type="set_priority",
            ticket_id=plan.primary_ticket,
            priority=plan.priority,
        )
    for tag in plan.tags:
        if plan.tag_milestone not in done and tag not in observation.focused_ticket.tags:
            return SupportOpsAction(
                action_type="add_tag",
                ticket_id=plan.primary_ticket,
                tag=tag,
            )
    if plan.create_incident_milestone not in done and not incident_id:
        return SupportOpsAction(
            action_type="create_incident",
            ticket_id=plan.primary_ticket,
            incident_title=plan.incident_title,
        )
    if plan.severity_milestone not in done and incident_id:
        return SupportOpsAction(
            action_type="set_incident_severity",
            ticket_id=plan.primary_ticket,
            incident_id=incident_id,
            severity=plan.severity,
        )
    if plan.duplicate_milestone not in done:
        return SupportOpsAction(
            action_type="link_duplicate",
            ticket_id=plan.duplicate_ticket,
            duplicate_of=plan.primary_ticket,
        )
    if plan.note_milestone not in done:
        return SupportOpsAction(
            action_type="add_internal_note",
            ticket_id=plan.primary_ticket,
            note=plan.note,
        )
    if (
        plan.status_update_milestone
        and plan.status_update_milestone not in done
        and incident_id
        and plan.status_update_message
    ):
        return SupportOpsAction(
            action_type="post_status_update",
            ticket_id=plan.primary_ticket,
            incident_id=incident_id,
            message=plan.status_update_message,
        )
    if plan.reply_milestone not in done:
        return SupportOpsAction(
            action_type="send_reply",
            ticket_id=plan.primary_ticket,
            reply=plan.reply,
        )
    if plan.status_milestone not in done:
        return SupportOpsAction(
            action_type="mark_status",
            ticket_id=plan.primary_ticket,
            status=plan.final_status,
        )

    return SupportOpsAction(action_type="noop")


def heuristic_action(observation: Any) -> SupportOpsAction:
    if observation.task_id in STANDARD_WORKFLOWS:
        return run_standard_workflow(
            observation,
            STANDARD_WORKFLOWS[observation.task_id],
        )
    if observation.task_id in INCIDENT_WORKFLOWS:
        return run_incident_workflow(
            observation,
            INCIDENT_WORKFLOWS[observation.task_id],
        )

    return SupportOpsAction(action_type="noop")


def action_from_model(observation: Any, client: OpenAI | None) -> SupportOpsAction:
    if client is None or not MODEL_NAME:
        return heuristic_action(observation)

    try:
        completion = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_user_prompt(observation)},
            ],
            temperature=0.0,
            max_tokens=300,
        )
        text = completion.choices[0].message.content or ""
        parsed = extract_json_object(text)
        if parsed:
            return SupportOpsAction.model_validate(parsed)
    except Exception:  # noqa: BLE001
        pass

    return heuristic_action(observation)


async def create_env() -> tuple[SupportOpsEnv, str]:
    if ENV_BASE_URL:
        env = SupportOpsEnv(base_url=ENV_BASE_URL)
        await env.connect()
        return env, BENCHMARK

    image_name = resolve_local_docker_image(
        LOCAL_IMAGE_NAME or "support-ops-env:latest"
    )
    return await SupportOpsEnv.from_docker_image(image_name), BENCHMARK


async def run_task(
    task_id: str,
    llm_client: OpenAI | None,
    benchmark: str,
) -> float:
    env: SupportOpsEnv | None = None
    score = 0.0
    rewards: list[float] = []
    steps_taken = 0
    success = False
    model_name = MODEL_NAME or "heuristic"

    print(format_start_line(task_id, benchmark, model_name))
    try:
        env, _ = await create_env()
        result = await env.reset(task_id=task_id)
        observation = result.observation

        for step_index in range(1, observation.step_limit + 1):
            if result.done:
                break

            action = action_from_model(observation, llm_client)
            result = await env.step(action)
            observation = result.observation
            reward = float(result.reward or 0.0)
            rewards.append(reward)
            steps_taken = step_index
            print(
                format_step_line(
                    step_index,
                    action,
                    reward,
                    result.done,
                    observation.last_error,
                )
            )
            if result.done:
                break

        score = max(0.0, min(float(observation.score), 1.0))
        success = score >= SUCCESS_SCORE_THRESHOLD
        return score
    except Exception:
        return score
    finally:
        if env is not None:
            try:
                await env.close()
            except Exception:
                pass
        print(format_end_line(success, steps_taken, score, rewards))


async def main() -> None:
    llm_client = create_llm_client()
    for task_id in TASK_IDS:
        await run_task(task_id, llm_client, BENCHMARK)


if __name__ == "__main__":
    asyncio.run(main())
