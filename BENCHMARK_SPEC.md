# Benchmark Spec

## What This Benchmark Is Trying To Measure

`support_ops_env` is meant to evaluate whether an agent can behave like a solid
first-response operator, not whether it can produce polished paragraphs on
demand.

The benchmark is built around a single support-ops world with realistic
constraints:

- the agent needs to retrieve missing context before acting
- the correct answer is often a workflow choice, not a sentence
- unsafe actions should hurt the score even if the text looks reasonable
- tasks should be reproducible enough to compare runs fairly

I wanted the environment to feel like work a support team would actually do, so
the tasks revolve around queueing, escalation, incident handling, duplicate
management, and customer communication.

## Design Principles

### 1. One coherent world

All four tasks live in the same operational setting. That makes the benchmark
feel more believable than a bag of unrelated mini-problems.

### 2. Retrieval before judgment

The agent should not get full credit for guessing from the ticket body alone.
That is why `search_tickets` and `search_kb` exist, and why several milestones
depend on using them.

### 3. Dense scoring

Sparse “win or lose” signals are frustrating to debug in a hackathon setting.
This benchmark uses milestone weights so progress is visible and reproducible.

### 4. Guardrails matter

A support agent that closes a ticket too early or posts the wrong public update
should not score as if it behaved well just because it eventually touched the
right fields.

## Task Table

| Task | Difficulty | What Good Performance Looks Like | Common Failure Pattern |
| --- | --- | --- | --- |
| `easy_refund_request` | Easy | retrieve refund policy, route to Billing, tag correctly, add note, reply clearly, resolve | resolves without policy context or routes incorrectly |
| `medium_sso_lockout` | Medium | retrieve SSO KB article, identify likely metadata issue, ask for the right artifact, keep ticket pending | resolves too early or asks for the wrong next step |
| `hard_vip_outage_duplicate` | Hard | search related tickets, create incident, set severity, link duplicate, send customer reply, publish status update | misses duplicate, skips incident workflow, or weakens public communication |
| `hard_partner_token_leak` | Hard | escalate as a security incident, link duplicates, choose severity correctly, guide the customer directly | treats a sensitive case like a public outage or closes it too casually |

## Scoring

Every task is decomposed into milestone checks whose weights sum to `1.0`.

Examples of milestone categories:

- retrieved the right knowledge base article
- moved the ticket to the correct queue
- set the right priority
- added the required tag
- wrote the right internal note
- sent the right customer reply
- created and updated the right incident objects

The step reward is incremental. If a step completes a new milestone, the agent
gets that newly earned portion on that step. Invalid actions can introduce
small penalties, and sticky guardrail violations reduce the final score.

## Guardrail Philosophy

I treated some mistakes as qualitatively worse than “not quite optimal.”

Examples:

- resolving an enterprise auth issue before collecting the right customer input
- making a public status-style move for a contained security incident
- failing to consolidate duplicates during a live outage

That keeps the benchmark honest. A run should not look strong just because it
filled the right fields eventually.

## Why The Hard Tasks Matter

The hard tasks were not added just to increase step count.

The outage task checks whether the agent can keep track of multiple tickets,
distinguish the operational source of truth from the duplicate, and perform
customer-facing as well as incident-facing work in the same episode.

The token-leak task checks a different kind of judgment. It asks whether the
agent knows when *not* to treat a case like a public incident and whether it
can give useful customer guidance without leaking operational discipline.

## Baseline Behavior

The included deterministic policy solves the four bundled tasks reliably.

For submission-time logging, the baseline reports task scores strictly inside
`(0, 1)` because the validator rejects endpoint values like `0.00` and `1.00`.
That formatting choice is about validator compatibility; the environment still
tracks normalized progress internally.

## If I Were Demoing This In Three Minutes

These are the points I would emphasize:

- it models real support and incident workflows rather than a toy benchmark
- the action space is typed and operational, not just text-only
- retrieval is necessary, not decorative
- rewards are dense enough to debug but still meaningful
- guardrail penalties make bad judgment visible
- the whole thing is deterministic and packaging-ready for OpenEnv, Docker, and Spaces
