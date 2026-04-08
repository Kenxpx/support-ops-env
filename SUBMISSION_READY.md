# Submission Notes

This is the short checklist I use before I hit submit.

## Canonical Links

- GitHub: `https://github.com/Kenxpx/support-ops-env`
- Hugging Face Space: `https://huggingface.co/spaces/Kenxpx/support-ops-env`

If the dashboard asks for anything else, I stop and double-check before
submitting.

## Pre-Submit Checks

Run these from the repository root:

```bash
python scripts/self_check.py
python scripts/submission_report.py
python -m unittest discover -s tests -v
docker build -t support-ops-env:latest .
openenv validate
```

If I want to run the shell validator against the live Space as well:

```bash
./scripts/validate-submission.sh https://kenxpx-support-ops-env.hf.space .
```

## Environment Variables

For local experimentation, I can copy `.env.example` to `.env`, but I do **not**
commit `.env`.

Relevant runtime variables:

- `API_BASE_URL`
- `API_KEY`
- `MODEL_NAME`
- `ENV_BASE_URL`
- `LOCAL_IMAGE_NAME`

For the hackathon validator, the important part is that `inference.py` reads the
injected `API_BASE_URL` and `API_KEY` at runtime and sends an OpenAI-compatible
request through that proxy before task execution continues.

## Submission-Specific Notes

- The inference script lives at the repo root as `inference.py`
- Structured output uses `[START]`, `[STEP]`, and `[END]`
- Reported task scores are kept strictly inside `(0, 1)` for validator compatibility
- The task policy is deterministic, so local reruns should be stable

## Final Sanity Pass

Right before submitting, I confirm:

- the latest code is pushed to GitHub
- the Hugging Face Space has been refreshed after the latest push
- the Space responds on `/health`, `/metadata`, and `POST /reset`
- `openenv validate` still passes
- unit tests still pass

## Exact Form Values

Use these exact URLs in the submission form:

- GitHub Repository URL: `https://github.com/Kenxpx/support-ops-env`
- Hugging Face Space URL: `https://huggingface.co/spaces/Kenxpx/support-ops-env`
