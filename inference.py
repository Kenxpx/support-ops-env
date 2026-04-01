"""Baseline inference script for the support operations environment."""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from typing import Any

from openai import OpenAI

from support_ops_env import SupportOpsAction, SupportOpsEnv

API_BASE_URL = os.getenv("API_BASE_URL") or "https://router.huggingface.co/v1"
API_KEY = os.getenv("HF_TOKEN") or os.getenv("API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME")
ENV_BASE_URL = os.getenv("ENV_BASE_URL")
DOCKER_IMAGE = os.getenv("DOCKER_IMAGE") or "support-ops-env:latest"
TASK_IDS = [
    "easy_refund_request",
    "medium_sso_lockout",
    "hard_vip_outage_duplicate",
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


def heuristic_action(observation: Any) -> SupportOpsAction:
    if observation.task_id in STANDARD_WORKFLOWS:
        return run_standard_workflow(
            observation,
            STANDARD_WORKFLOWS[observation.task_id],
        )

    if observation.task_id == "hard_vip_outage_duplicate":
        done = completed_milestones(observation)
        focused_ticket_id = (
            observation.focused_ticket.ticket_id if observation.focused_ticket else None
        )
        primary_ticket = "T-3001"
        duplicate_ticket = "T-3002"
        incident_id = primary_incident_id(observation, primary_ticket)

        if "searched_related_tickets" not in done and not search_contains_ticket(observation, duplicate_ticket):
            return SupportOpsAction(
                action_type="search_tickets",
                query="Northstar checkout outage duplicate EU-West",
            )
        if "searched_incident_playbook" not in done and not search_contains_article(observation, "KB-INC-01"):
            return SupportOpsAction(
                action_type="search_kb",
                query="SEV1 incident status page duplicate outage checkout",
            )
        if focused_ticket_id != primary_ticket:
            return SupportOpsAction(action_type="view_ticket", ticket_id=primary_ticket)
        if "queue_incident_response" not in done:
            return SupportOpsAction(
                action_type="set_queue",
                ticket_id=primary_ticket,
                queue="incident_response",
            )
        if "priority_urgent" not in done:
            return SupportOpsAction(
                action_type="set_priority",
                ticket_id=primary_ticket,
                priority="urgent",
            )
        if "tag_outage_vip" not in done and "outage" not in observation.focused_ticket.tags:
            return SupportOpsAction(action_type="add_tag", ticket_id=primary_ticket, tag="outage")
        if "tag_outage_vip" not in done and "vip" not in observation.focused_ticket.tags:
            return SupportOpsAction(action_type="add_tag", ticket_id=primary_ticket, tag="vip")
        if "create_incident" not in done and not incident_id:
            return SupportOpsAction(
                action_type="create_incident",
                ticket_id=primary_ticket,
                incident_title="Northstar EU-West checkout outage",
            )
        if "severity_sev1" not in done and incident_id:
            return SupportOpsAction(
                action_type="set_incident_severity",
                incident_id=incident_id,
                severity="sev1",
                ticket_id=primary_ticket,
            )
        if "duplicate_linked" not in done:
            return SupportOpsAction(
                action_type="link_duplicate",
                ticket_id=duplicate_ticket,
                duplicate_of=primary_ticket,
            )
        if "note_region_component" not in done:
            return SupportOpsAction(
                action_type="add_internal_note",
                ticket_id=primary_ticket,
                note="EU-West outage is affecting the Checkout API across multiple stores and should stay with incident response.",
            )
        if "status_page_update" not in done and incident_id:
            return SupportOpsAction(
                action_type="post_status_update",
                incident_id=incident_id,
                ticket_id=primary_ticket,
                message="We are investigating an issue affecting checkout in EU-West and will continue sharing updates on the status page.",
            )
        if "customer_reply_refs_status_page" not in done:
            return SupportOpsAction(
                action_type="send_reply",
                ticket_id=primary_ticket,
                reply="We are actively investigating this outage. Please follow the status page for live updates while we work on mitigation.",
            )
        if "status_escalated" not in done:
            return SupportOpsAction(
                action_type="mark_status",
                ticket_id=primary_ticket,
                status="escalated",
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
    except Exception as exc:  # noqa: BLE001
        print(f"Model call failed, falling back to heuristic action: {exc}")

    return heuristic_action(observation)


async def create_env() -> SupportOpsEnv:
    if ENV_BASE_URL:
        env = SupportOpsEnv(base_url=ENV_BASE_URL)
        await env.connect()
        return env
    return await SupportOpsEnv.from_docker_image(DOCKER_IMAGE)


async def run_task(env: SupportOpsEnv, task_id: str, llm_client: OpenAI | None) -> float:
    result = await env.reset(task_id=task_id)
    observation = result.observation

    print(f"\n=== Running {task_id} ===")
    print(f"Goal: {observation.goal}")

    for step_index in range(1, observation.step_limit + 1):
        if result.done:
            break

        action = action_from_model(observation, llm_client)
        print(f"Step {step_index}: {action.model_dump(exclude_none=True)}")
        result = await env.step(action)
        observation = result.observation
        print(
            "  "
            f"reward={result.reward} score={observation.score:.2f} "
            f"done={result.done} error={observation.last_error}"
        )
        if result.done:
            break

    score = float(observation.score)
    print(f"Final score for {task_id}: {score:.2f}")
    return score


async def main() -> None:
    llm_client = None
    if API_KEY and MODEL_NAME:
        llm_client = OpenAI(base_url=API_BASE_URL, api_key=API_KEY)
    else:
        print("MODEL_NAME or API key missing; using heuristic fallback for baseline actions.")

    env = await create_env()
    try:
        scores: dict[str, float] = {}
        for task_id in TASK_IDS:
            scores[task_id] = await run_task(env, task_id, llm_client)

        average_score = sum(scores.values()) / len(scores)
        print("\n=== Score Summary ===")
        for task_id, score in scores.items():
            print(f"{task_id}: {score:.2f}")
        print(f"average_score: {average_score:.2f}")
    finally:
        await env.close()


if __name__ == "__main__":
    asyncio.run(main())
