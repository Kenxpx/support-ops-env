"""Task definitions for the support operations environment."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TicketSeed:
    ticket_id: str
    subject: str
    customer: str
    customer_tier: str
    region: str
    product: str
    body: str
    account_owner: str
    impacted_users: int
    opened_minutes_ago: int
    sla_minutes: int
    related_ticket_ids: tuple[str, ...] = ()
    queue: str = "triage"
    priority: str = "low"
    status: str = "open"
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class KnowledgeBaseSeed:
    article_id: str
    title: str
    summary: str
    body: str
    key_facts: tuple[str, ...]
    keywords: tuple[str, ...]


@dataclass(frozen=True)
class MilestoneSpec:
    milestone_id: str
    description: str
    weight: float


@dataclass(frozen=True)
class TaskSpec:
    task_id: str
    title: str
    difficulty: str
    scenario: str
    goal: str
    instructions: tuple[str, ...]
    primary_ticket_id: str
    step_limit: int
    allowed_tags: tuple[str, ...]
    tickets: tuple[TicketSeed, ...]
    knowledge_base: tuple[KnowledgeBaseSeed, ...]
    milestones: tuple[MilestoneSpec, ...]


TASKS: tuple[TaskSpec, ...] = (
    TaskSpec(
        task_id="easy_refund_request",
        title="Refund Request Triage",
        difficulty="easy",
        scenario=(
            "You are the first-line operator for a B2B SaaS support desk. Billing "
            "requests should be routed cleanly, documented, and closed with clear "
            "customer guidance."
        ),
        goal=(
            "Handle a duplicate charge complaint by inspecting the ticket, checking "
            "the refund policy, routing it correctly, adding the right tags, "
            "documenting the issue internally, replying with the refund timeline, "
            "and closing the ticket."
        ),
        instructions=(
            "Inspect before editing operational fields.",
            "Use the knowledge base for customer-facing billing guidance.",
            "Operational tags should help downstream reporting.",
            "Resolve only after the reply includes a concrete refund timeline.",
        ),
        primary_ticket_id="T-1001",
        step_limit=10,
        allowed_tags=("refund", "duplicate_charge", "billing_review"),
        tickets=(
            TicketSeed(
                ticket_id="T-1001",
                subject="Charged twice for March invoice",
                customer="Mia Chen",
                customer_tier="standard",
                region="US-East",
                product="Billing",
                body=(
                    "Hi team, my card was charged twice for the March invoice. "
                    "Please reverse the duplicate payment. I do not need a phone call."
                ),
                account_owner="Arjun Kapoor",
                impacted_users=1,
                opened_minutes_ago=35,
                sla_minutes=240,
            ),
            TicketSeed(
                ticket_id="T-1012",
                subject="Need VAT invoice for last month",
                customer="Brightline Studio",
                customer_tier="standard",
                region="EU-Central",
                product="Billing",
                body=(
                    "Can you send us the VAT-compliant invoice PDF for the previous "
                    "billing cycle? No charge issue here."
                ),
                account_owner="Arjun Kapoor",
                impacted_users=1,
                opened_minutes_ago=70,
                sla_minutes=240,
            ),
        ),
        knowledge_base=(
            KnowledgeBaseSeed(
                article_id="KB-REFUND-01",
                title="Duplicate charge refund workflow",
                summary=(
                    "Billing-owned workflow for duplicate card charges and refund "
                    "customer messaging."
                ),
                body=(
                    "If a customer reports a duplicate card charge, route the case to "
                    "Billing, use medium priority unless revenue-critical, tag the "
                    "case for refund reporting, and tell the customer refunds usually "
                    "settle in 3-5 business days. Do not promise same-day reversal."
                ),
                key_facts=(
                    "Owned by Billing queue",
                    "Default priority is medium",
                    "Customer reply should mention 3-5 business days",
                ),
                keywords=("refund", "duplicate charge", "billing", "3-5 business days"),
            ),
            KnowledgeBaseSeed(
                article_id="KB-VAT-02",
                title="VAT invoice delivery requests",
                summary="Procedure for customers requesting VAT-compliant invoices.",
                body=(
                    "VAT invoice requests are fulfilled by finance operations and do "
                    "not involve refund handling."
                ),
                key_facts=("Finance operations workflow", "No refund action required"),
                keywords=("invoice", "vat", "pdf", "finance"),
            ),
        ),
        milestones=(
            MilestoneSpec("searched_kb_refund", "Search the refund KB article.", 0.10),
            MilestoneSpec("opened_primary", "Open the primary ticket.", 0.10),
            MilestoneSpec("queue_billing", "Route the ticket to Billing.", 0.15),
            MilestoneSpec("priority_medium", "Set the correct priority.", 0.10),
            MilestoneSpec(
                "tag_refund_context",
                "Add both refund and duplicate-charge tags.",
                0.10,
            ),
            MilestoneSpec(
                "note_duplicate_charge",
                "Document the duplicate charge internally.",
                0.10,
            ),
            MilestoneSpec(
                "reply_refund_window",
                "Reply with the refund timeline from policy.",
                0.20,
            ),
            MilestoneSpec("status_resolved", "Resolve the ticket.", 0.15),
        ),
    ),
    TaskSpec(
        task_id="medium_sso_lockout",
        title="Enterprise SSO Lockout",
        difficulty="medium",
        scenario=(
            "You are covering enterprise authentication support. The customer is on a "
            "high-value plan and their workforce cannot log in after an IdP change."
        ),
        goal=(
            "Triage an enterprise SSO outage affecting 140 users. Inspect the ticket, "
            "check the SSO troubleshooting article, route it to the correct queue, "
            "set the right priority, add the right tags, capture the likely root "
            "cause internally, ask the customer for the correct artifact, and leave "
            "the case pending."
        ),
        instructions=(
            "This is an authentication workflow, not a generic import issue.",
            "Use the knowledge base before sending customer guidance.",
            "Internal notes should name the likely identity-provider problem.",
            "Do not resolve while support still needs customer input.",
        ),
        primary_ticket_id="T-2001",
        step_limit=12,
        allowed_tags=("sso", "enterprise_auth", "idp_change"),
        tickets=(
            TicketSeed(
                ticket_id="T-2001",
                subject="SSO login broken after IdP update",
                customer="Acme Robotics",
                customer_tier="enterprise",
                region="US-West",
                product="Authentication",
                body=(
                    "We rotated our identity provider settings yesterday and now "
                    "140 employees cannot sign in through SSO. Password logins are "
                    "disabled. Please help us restore access quickly."
                ),
                account_owner="Neha Sharma",
                impacted_users=140,
                opened_minutes_ago=22,
                sla_minutes=60,
            ),
            TicketSeed(
                ticket_id="T-2004",
                subject="CSV bulk user import validation errors",
                customer="Acme Robotics",
                customer_tier="enterprise",
                region="US-West",
                product="Admin Console",
                body=(
                    "Our HR team is seeing CSV mapping errors during bulk user import. "
                    "This is separate from login and not currently blocking access."
                ),
                account_owner="Neha Sharma",
                impacted_users=4,
                opened_minutes_ago=190,
                sla_minutes=240,
            ),
        ),
        knowledge_base=(
            KnowledgeBaseSeed(
                article_id="KB-SSO-07",
                title="SAML metadata mismatch triage",
                summary=(
                    "Checklist for enterprise SSO failures after identity-provider "
                    "configuration changes."
                ),
                body=(
                    "When SSO breaks after an IdP change, route to technical support, "
                    "mark priority high for multi-user access loss, and ask the admin "
                    "for a fresh SAML metadata XML export. Verify the ACS URL and "
                    "entity ID before resolving."
                ),
                key_facts=(
                    "Technical Support owns the issue",
                    "Ask for fresh SAML metadata XML",
                    "Check ACS URL and entity ID",
                ),
                keywords=("sso", "saml", "metadata", "acs url", "entity id", "idp"),
            ),
            KnowledgeBaseSeed(
                article_id="KB-CSV-02",
                title="Bulk user import troubleshooting",
                summary="Fixing validation issues during CSV user import.",
                body=(
                    "CSV import errors usually stem from header formatting and do not "
                    "involve SSO or identity-provider metadata."
                ),
                key_facts=("Admin console workflow", "Not an SSO playbook"),
                keywords=("csv", "import", "mapping", "headers"),
            ),
        ),
        milestones=(
            MilestoneSpec("searched_kb_sso", "Search the SSO KB article.", 0.12),
            MilestoneSpec("opened_primary", "Open the primary ticket.", 0.08),
            MilestoneSpec(
                "queue_technical_support",
                "Route the ticket to technical support.",
                0.12,
            ),
            MilestoneSpec("priority_high", "Set the correct priority.", 0.12),
            MilestoneSpec(
                "tag_sso_enterprise",
                "Add both SSO and enterprise-auth tags.",
                0.08,
            ),
            MilestoneSpec(
                "note_idp_metadata",
                "Leave an internal note naming the IdP metadata issue.",
                0.16,
            ),
            MilestoneSpec(
                "reply_saml_metadata",
                "Ask the customer for fresh SAML metadata and ACS details.",
                0.16,
            ),
            MilestoneSpec("status_pending", "Leave the ticket pending.", 0.16),
        ),
    ),
    TaskSpec(
        task_id="hard_vip_outage_duplicate",
        title="VIP Outage With Duplicate Incident",
        difficulty="hard",
        scenario=(
            "You are the incident commander on support duty. A VIP customer has a "
            "live production outage and multiple related tickets are arriving."
        ),
        goal=(
            "Handle an active production outage for a VIP customer. Search for related "
            "tickets, inspect the primary issue, consult the incident playbook, route "
            "the work correctly, tag it, create and escalate an incident, link the "
            "duplicate ticket, document the blast radius, publish a status-page update, "
            "reply to the customer with the status-page reference, and leave the "
            "primary ticket escalated."
        ),
        instructions=(
            "Keep T-3001 as the primary record for the outage.",
            "Use search to identify duplicate and decoy tickets before acting.",
            "Use the incident playbook before publishing a status update.",
            "A VIP production outage should be handled as an incident, not a normal ticket.",
        ),
        primary_ticket_id="T-3001",
        step_limit=15,
        allowed_tags=("outage", "vip", "checkout", "duplicate"),
        tickets=(
            TicketSeed(
                ticket_id="T-3001",
                subject="VIP checkout outage in EU-West",
                customer="Northstar Retail",
                customer_tier="vip",
                region="EU-West",
                product="Checkout API",
                body=(
                    "Our shoppers cannot complete purchases in EU-West. We are "
                    "seeing failures in the hosted checkout flow across multiple stores. "
                    "This is a live incident on our paid plan."
                ),
                account_owner="Ira Mehta",
                impacted_users=3200,
                opened_minutes_ago=11,
                sla_minutes=15,
                related_ticket_ids=("T-3002", "T-3003"),
            ),
            TicketSeed(
                ticket_id="T-3002",
                subject="Duplicate alert from finance team about checkout failures",
                customer="Northstar Retail",
                customer_tier="vip",
                region="EU-West",
                product="Checkout API",
                body=(
                    "Same incident as the production outage ticket. Finance saw "
                    "the same checkout failures and opened a second case."
                ),
                account_owner="Ira Mehta",
                impacted_users=20,
                opened_minutes_ago=9,
                sla_minutes=15,
                related_ticket_ids=("T-3001",),
            ),
            TicketSeed(
                ticket_id="T-3003",
                subject="Tax rounding mismatch in legacy checkout report",
                customer="Northstar Retail",
                customer_tier="vip",
                region="EU-West",
                product="Reporting",
                body=(
                    "We still need help with a tax rounding mismatch in last week's "
                    "finance export. This is unrelated to the live outage."
                ),
                account_owner="Ira Mehta",
                impacted_users=2,
                opened_minutes_ago=430,
                sla_minutes=240,
            ),
        ),
        knowledge_base=(
            KnowledgeBaseSeed(
                article_id="KB-INC-01",
                title="SEV1 incident handling for customer-facing outages",
                summary=(
                    "Playbook for VIP production outages requiring incident response "
                    "and public communication."
                ),
                body=(
                    "For a VIP production outage affecting checkout, route the issue to "
                    "incident response, set ticket priority urgent, create an incident, "
                    "set severity SEV1 for customer-wide payment impact, and post a "
                    "public update that says the team is investigating. Include the "
                    "affected region and service in the internal note."
                ),
                key_facts=(
                    "Use Incident Response queue",
                    "Urgent ticket priority",
                    "SEV1 for widespread checkout outage",
                    "Public status page should say investigating",
                ),
                keywords=("sev1", "incident", "status page", "outage", "checkout", "vip"),
            ),
            KnowledgeBaseSeed(
                article_id="KB-DUP-03",
                title="Duplicate ticket consolidation",
                summary="How to consolidate duplicate tickets during an active incident.",
                body=(
                    "Keep the earliest ticket as primary, link later duplicates to it, "
                    "and attach duplicate tickets to the same incident record."
                ),
                key_facts=(
                    "Keep earliest ticket as primary",
                    "Link duplicate tickets",
                    "Attach duplicates to same incident",
                ),
                keywords=("duplicate", "incident", "primary ticket", "consolidation"),
            ),
            KnowledgeBaseSeed(
                article_id="KB-TAX-04",
                title="Legacy tax report mismatch",
                summary="Finance-report troubleshooting guide for tax rounding issues.",
                body=(
                    "Tax rounding mismatches belong to reporting support and are not "
                    "handled as production incidents."
                ),
                key_facts=("Reporting workflow", "Not an outage playbook"),
                keywords=("tax", "reporting", "rounding", "finance"),
            ),
        ),
        milestones=(
            MilestoneSpec(
                "searched_related_tickets",
                "Search ticket data and surface the duplicate case.",
                0.05,
            ),
            MilestoneSpec(
                "searched_incident_playbook",
                "Search the incident playbook KB article.",
                0.05,
            ),
            MilestoneSpec("opened_primary", "Open the primary outage ticket.", 0.05),
            MilestoneSpec(
                "queue_incident_response",
                "Route the primary ticket to incident response.",
                0.08,
            ),
            MilestoneSpec("priority_urgent", "Set the correct ticket priority.", 0.08),
            MilestoneSpec(
                "create_incident",
                "Create an incident tied to the primary ticket.",
                0.12,
            ),
            MilestoneSpec(
                "severity_sev1",
                "Escalate the incident to SEV1.",
                0.12,
            ),
            MilestoneSpec(
                "duplicate_linked",
                "Link the duplicate ticket to the primary outage.",
                0.10,
            ),
            MilestoneSpec(
                "tag_outage_vip",
                "Tag the primary ticket as outage and VIP-impacting.",
                0.07,
            ),
            MilestoneSpec(
                "note_region_component",
                "Document affected region and component internally.",
                0.08,
            ),
            MilestoneSpec(
                "status_page_update",
                "Publish a public status-page update.",
                0.10,
            ),
            MilestoneSpec(
                "customer_reply_refs_status_page",
                "Reply with a status-page-oriented customer update.",
                0.05,
            ),
            MilestoneSpec("status_escalated", "Leave the ticket escalated.", 0.05),
        ),
    ),
)

TASKS_BY_ID = {task.task_id: task for task in TASKS}
