# Submission Ready Checklist

Use this checklist right before you submit the environment.

## Canonical URLs

- GitHub repository: `https://github.com/Kenxpx/support-ops-env`
- Hugging Face Space: `https://huggingface.co/spaces/Kenxpx/support-ops-env`

## Local Validation

Run these commands from the repository root:

```bash
python scripts/self_check.py
python scripts/submission_report.py
python -m py_compile models.py client.py inference.py server/*.py
python -m unittest discover -s tests -v
docker build -t support-ops-env:latest -f server/Dockerfile .
```

If you want to validate a running server after starting the container locally:

```bash
openenv validate --url http://localhost:8000
```

## Runtime Configuration

- Copy `.env.example` to `.env` if you want to use a hosted model.
- Set `HF_TOKEN` to your Hugging Face token.
- Set `MODEL_NAME` to the router model you want to call.
- If `MODEL_NAME` or the token is missing, `inference.py` falls back to the deterministic heuristic policy.

## Submission Form Values

Use these exact values in the form:

- GitHub Repository URL: `https://github.com/Kenxpx/support-ops-env`
- Hugging Face Space URL: `https://huggingface.co/spaces/Kenxpx/support-ops-env`

## Final Sanity Check

- Confirm the latest code is pushed to GitHub.
- Confirm the Hugging Face Space points at the same repository state.
- Confirm the Docker image serves the environment on port `8000`.
- Confirm the environment responds on `/health`, `/metadata`, `/schema`, `/reset`, `/step`, and `/state`.
