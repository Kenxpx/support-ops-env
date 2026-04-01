# Benchmark Spec

## Overview

`support_ops_env` is designed as a compact but realistic support-operations
benchmark for agent evaluation. The environment emphasizes:

- retrieval before action
- deterministic state transitions
- dense programmatic grading
- realistic enterprise support workflows
- long-horizon incident handling without requiring an actual browser

## Benchmark Design Goals

1. Reward good operational judgment, not just text generation.
2. Make most grading programmatic so runs are stable and reproducible.
3. Use one coherent world instead of unrelated toy tasks.
4. Keep tasks short enough for hackathon infrastructure while still requiring
   multi-step planning.

## Task Matrix

| Task | Difficulty | Core Skills | Failure Modes |
| --- | --- | --- | --- |
| `easy_refund_request` | Easy | inspect, retrieve policy, route, tag, reply, resolve | wrong queue, no policy retrieval, vague reply |
| `medium_sso_lockout` | Medium | inspect, retrieve KB, triage, explain likely cause, request artifact, leave pending | resolves too early, asks for wrong artifact, wrong queue |
| `hard_vip_outage_duplicate` | Hard | search, incident creation, severity setting, duplicate consolidation, public communication | misses duplicate, skips incident, weak status update, wrong severity |

## Reward Philosophy

Every task is decomposed into weighted milestones that sum to `1.0`.

Reward is:

- positive when the agent newly completes a milestone
- slightly negative for invalid actions
- deterministic for the same task and action sequence

This makes the benchmark:

- easy to debug
- easy to explain to judges
- more useful for baseline comparisons than sparse success-only scoring

## Why The Hard Task Matters

The hardest task was intentionally designed to feel benchmark-quality:

- duplicate and decoy tickets force retrieval, not memorization
- a public status update forces externally-facing communication
- incident creation and severity force workflow correctness
- the primary ticket must remain the operational source of truth

## Suggested Judge Talking Points

If you are demoing the project, highlight:

- deterministic resets and reproducible scoring
- retrieval-first design through `search_tickets` and `search_kb`
- dense milestone rewards with normalized `0.0-1.0` scores
- realistic support and incident handling rather than a toy environment
- clean packaging for OpenEnv, Docker, and Hugging Face Spaces
