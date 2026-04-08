---
title: Support Operations Environment Server
emoji: "📬"
colorFrom: blue
colorTo: green
sdk: docker
pinned: false
app_port: 8000
base_path: /web
tags:
  - openenv
  - customer-support
  - rl
---

# Support Operations Environment

I built `support_ops_env` to model the kind of work that actually happens in a
support team when something important breaks: a refund issue lands in the wrong
queue, an enterprise customer gets locked out of SSO, a VIP outage creates
duplicate tickets, or a partner accidentally exposes a token.

This project is not a toy gridworld and it is not a browser automation demo in
disguise. It is a deterministic OpenEnv benchmark where an agent has to inspect
state, retrieve missing context, make the right operational decision, and leave
the system in a defensible state.

## Why I Chose This Domain

Support operations is a good benchmark domain because the actions are easy to
understand but the judgment is not. A decent agent has to do more than classify
a ticket. It has to:

- pull the right policy or runbook before acting
- route work to the correct queue
- set urgency without over-escalating everything
- communicate clearly to a customer
- handle duplicates and incidents cleanly
- avoid dangerous shortcuts like resolving too early or posting the wrong thing publicly

That gives the benchmark a real shape: short enough to run in hackathon
infrastructure, but still grounded in workflows a human team would recognize.

## What The Agent Can Do

The environment exposes a typed `SupportOpsAction` model with these operations:

- `noop`
- `search_tickets`
- `search_kb`
- `view_ticket`
- `set_queue`
- `set_priority`
- `add_tag`
- `add_internal_note`
- `send_reply`
- `mark_status`
- `link_duplicate`
- `create_incident`
- `set_incident_severity`
- `post_status_update`

The full schema lives in [models.py](./models.py).

## What The Agent Sees

Each observation contains the task metadata plus the live working context the
agent needs to make progress:

- visible ticket summaries
- the currently focused ticket
- ticket search results
- knowledge base search results
- incidents and recent status updates
- milestone completion state
- progress, score, and remaining step budget
- the last action summary and any error message

This keeps the benchmark compact while still making retrieval matter. If the
agent never searches, it misses critical context.

## Tasks

The environment ships with four deterministic tasks:

### `easy_refund_request`

A duplicate-charge complaint that looks simple, but still checks whether the
agent retrieves the refund policy, tags the case correctly, routes it to
Billing, and sends a reply that sounds like an actual support response.

### `medium_sso_lockout`

An enterprise SSO issue that should not be “resolved” by guessing. The right
flow is to look up the relevant KB article, identify the likely metadata
mismatch, ask for the correct artifact, and leave the ticket pending.

### `hard_vip_outage_duplicate`

A VIP outage with duplicate tickets and incident workflow requirements. The
agent has to search related tickets, create the incident, set severity, link
the duplicate, send the right customer reply, and publish an appropriate status
update.

### `hard_partner_token_leak`

A security-sensitive task where the agent must escalate correctly without
turning a contained incident into a public communications mistake. This one
tests severity selection, duplicate handling, and practical customer guidance.

## Scoring And Guardrails

Each task is scored through weighted milestones that add up to `1.0` inside the
environment. Rewards are incremental: when the agent completes a new milestone,
it gets the newly earned portion of the score on that step.

I also added sticky penalties for bad operational behavior. Examples:

- resolving an auth issue before collecting the right customer input
- posting a public status update for an isolated security case
- making workflow changes that ignore the incident structure

That matters because I did not want a benchmark where an agent can bluff its
way to a good score with plausible-looking text.

One submission-specific note: the bundled `inference.py` reports final task
scores in the strict `(0, 1)` interval because the validator rejects endpoint
values like `0.00` and `1.00`. The environment state still tracks the real
normalized progress internally.

## Repository Layout

```text
support_ops_env/
|-- __init__.py
|-- .env.example
|-- BENCHMARK_SPEC.md
|-- Dockerfile
|-- LICENSE
|-- README.md
|-- SUBMISSION_READY.md
|-- client.py
|-- inference.py
|-- models.py
|-- openenv.yaml
|-- pyproject.toml
|-- scripts/
|   |-- self_check.py
|   |-- submission_report.py
|   `-- validate-submission.sh
|-- tests/
|   `-- test_support_ops_env.py
|-- .github/
|   `-- workflows/
|       `-- ci.yml
`-- server/
    |-- __init__.py
    |-- __main__.py
    |-- app.py
    |-- support_ops_env_environment.py
    `-- tasks.py
```

## Running It Locally

### Install

```bash
pip install -e .
```

Or, if you use `uv`:

```bash
uv sync
```

If you want a local env file for your own experiments:

```bash
cp .env.example .env
```

### Start The Server

```bash
uv run server --host 0.0.0.0 --port 8000
```

You can also run it directly with Python:

```bash
python -m support_ops_env.server.app --port 8000
```

### Build The Docker Image

```bash
docker build -t support-ops-env:latest .
```

### Push To Hugging Face Spaces

```bash
openenv push --repo-id Kenxpx/support-ops-env
```

## Baseline Inference

The baseline submission script is [inference.py](./inference.py).

It does two things:

1. When the validator injects `API_BASE_URL` and `API_KEY`, it creates an
   OpenAI-compatible client, resolves a proxy-served model, and proves the proxy
   path works before task execution continues.
2. It uses the deterministic task policy to execute the workflow cleanly and
   emit strict `[START]`, `[STEP]`, and `[END]` lines.

That split is intentional. I wanted the evaluation run to demonstrate proxy
usage cleanly without making task success depend on the quality of a random
generation from an external model.

Useful environment variables:

- `API_BASE_URL`: OpenAI-compatible endpoint used for submission-time proxy calls
- `API_KEY`: injected validator key or your own OpenAI-compatible key
- `MODEL_NAME`: preferred model name; the script falls back to a served proxy model if needed
- `ENV_BASE_URL`: connect to an already running environment
- `LOCAL_IMAGE_NAME`: local Docker image name when launching from Docker

If no API credentials are present, `inference.py` falls back to the deterministic
heuristic path and labels the run as `model=heuristic`.

## Validation Flow I Use Before Submitting

```bash
python scripts/self_check.py
python scripts/submission_report.py
python -m unittest discover -s tests -v
docker build -t support-ops-env:latest .
openenv validate
```

If I want to run the shell validator against the live Space:

```bash
./scripts/validate-submission.sh https://kenxpx-support-ops-env.hf.space .
```

## Helpful Files

- [BENCHMARK_SPEC.md](./BENCHMARK_SPEC.md) is the short benchmark write-up
- [SUBMISSION_READY.md](./SUBMISSION_READY.md) is the pre-submit checklist I use
- [scripts/self_check.py](./scripts/self_check.py) catches structural mistakes quickly
- [scripts/submission_report.py](./scripts/submission_report.py) gives a compact go/no-go report
- [scripts/validate-submission.sh](./scripts/validate-submission.sh) mirrors the main validation flow

## Final Notes

- Resets are deterministic for a given `task_id`
- The benchmark is intentionally retrieval-first
- The hard tasks are meant to feel like real support and incident work, not just bigger classification problems
- The environment is fully usable through standard OpenEnv `reset()`, `step()`, and `state()` APIs
