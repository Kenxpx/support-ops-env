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

Hugging Face Space URL - https://huggingface.co/spaces/Kenxpx/support-ops-env


# Support Operations Environment

`support_ops_env` is a deterministic, real-world OpenEnv environment for
training and evaluating agents on support and incident-response workflows.
Instead of solving a toy game, the agent must inspect tickets, retrieve policy
from the knowledge base, set the right queue and priority, communicate with
customers, manage incidents, publish status updates, and consolidate duplicate
cases using the standard `reset()`, `step()`, and `state()` APIs.

## Why This Fits Round 1

- Real-world domain: support operations and ticket handling
- Typed OpenEnv interface: action, observation, and state models
- Four graded tasks with easy, medium, and hard security/outage escalation paths
- Meaningful partial-credit rewards based on verified milestones
- Sticky guardrail penalties for operationally unsafe actions
- Deterministic task resets for reproducible baseline scores
- Docker and Hugging Face Space ready
- Judge-friendly benchmark spec and local self-check script included
- CI workflow and submission handoff sheet included

## Tasks

The environment exposes four built-in tasks:

1. `easy_refund_request`
   Route a duplicate charge complaint to Billing, use the refund policy, add the
   correct tags and note, reply with the right guidance, and resolve it.
2. `medium_sso_lockout`
   Triage an enterprise SSO lockout, retrieve the SSO article, note the likely
   identity-provider issue, respond with the correct next step, and keep the
   ticket pending.
3. `hard_vip_outage_duplicate`
   Handle an active VIP outage with duplicate tickets by searching related
   tickets, creating and escalating an incident, linking the duplicate, and
   sending the right status-page communication.
4. `hard_partner_token_leak`
   Handle a partner credential leak with duplicate SOC tickets, security
   incident severity, direct customer guidance, and no public status-page leak.

## Action Space

The environment accepts one structured `SupportOpsAction` per step:

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

All actions are fully typed in [models.py](./models.py).

## Observation Space

Every observation includes:

- task id, title, difficulty, goal, and scenario
- visible task instructions
- queue snapshot with visible tickets
- ticket-search and knowledge-base search results
- the currently focused ticket, if one has been opened
- visible incidents and recent public status updates
- milestone checklist with completion flags
- progress and normalized score in the `0.0` to `1.0` range
- last action summary, last error, recent activity log, and remaining step budget

## Reward Design

Each task is broken into milestone checks with weights that sum to `1.0`.
Examples:

- correct queue chosen
- correct priority chosen
- required retrieval actions completed
- required tag added
- internal note contains required evidence
- customer reply includes required remediation details
- incident creation, duplicate linking, or final status handled correctly

The reward emitted on each step is the *incremental* score earned by newly
completed milestones. Invalid actions receive a small penalty, but the final
task score remains the milestone-completion fraction.

The benchmark also uses sticky guardrail penalties for obviously unsafe actions,
such as resolving an enterprise auth outage before collecting input or posting
public updates for an isolated security incident. This makes the final score
reflect both task completion and operational judgment.

## Project Structure

```text
support_ops_env/
|-- __init__.py
|-- .env.example
|-- BENCHMARK_SPEC.md
|-- LICENSE
|-- SUBMISSION_READY.md
|-- client.py
|-- inference.py
|-- models.py
|-- openenv.yaml
|-- pyproject.toml
|-- README.md
|-- scripts/
|   |-- self_check.py
|   `-- submission_report.py
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

## Quick Start

### 1. Install dependencies

```bash
pip install -e .
```

Or with `uv`:

```bash
uv sync
```

Optional:

```bash
cp .env.example .env
```

### 2. Run locally

```bash
uv run server --host 0.0.0.0 --port 8000
```

Or:

```bash
python -m support_ops_env.server.app --port 8000
```

Or:

```bash
python -m support_ops_env.server
```

### 3. Build Docker image

```bash
docker build -t support-ops-env:latest -f server/Dockerfile .
```

### 4. Deploy to Hugging Face Spaces

```bash
openenv push --repo-id your-username/support-ops-env
```

## Baseline Inference

The submission baseline lives at [inference.py](./inference.py). It:

- reads `API_BASE_URL`, `MODEL_NAME`, and `HF_TOKEN`
- uses the OpenAI client for all LLM calls
- runs the three benchmark tasks
- follows an inspect -> retrieve -> decide -> act pattern
- prints per-task scores plus an average score

Useful optional environment variables:

- `ENV_BASE_URL`: connect to an already running server
- `DOCKER_IMAGE`: Docker image to launch when `ENV_BASE_URL` is not set

## Benchmark Notes

- [BENCHMARK_SPEC.md](./BENCHMARK_SPEC.md) gives a concise judge-facing summary
  of the environment goals, reward philosophy, and task matrix.
- [scripts/self_check.py](./scripts/self_check.py) performs static sanity checks
  without requiring the full runtime stack.
- [SUBMISSION_READY.md](./SUBMISSION_READY.md) contains the exact final steps and
  URL templates for the Round 1 form.
- [scripts/submission_report.py](./scripts/submission_report.py) runs a compact
  pre-submit report that is useful right before you push.

## Suggested Validation Flow

```bash
python scripts/self_check.py
python scripts/submission_report.py
python -m py_compile models.py client.py inference.py server/*.py
python -m unittest discover -s tests -v
docker build -t support-ops-env:latest -f server/Dockerfile .
openenv validate
```

## Notes

- The environment is deterministic when reset with the same `task_id`.
- Custom resets are supported through `reset(task_id="...")`.
- The hard task intentionally requires multi-ticket reasoning rather than only
  single-ticket classification.
