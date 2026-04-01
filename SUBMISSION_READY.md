# Submission Ready

This file is the final handoff sheet for Round 1 submission.

## 1. Final checks to run

Run these from the project root:

```bash
python scripts/self_check.py
python -m unittest discover -s tests -v
openenv validate
docker build -t support-ops-env:latest -f server/Dockerfile .
```

If all four commands pass, the project is ready to submit.

## 2. Push to GitHub

Create a repository named `support-ops-env` or similar, then push:

```bash
git init
git add .
git commit -m "Round 1 submission"
git branch -M main
git remote add origin https://github.com/<your-username>/support-ops-env.git
git push -u origin main
```

## 3. Deploy to Hugging Face Spaces

Login and deploy:

```bash
huggingface-cli login
openenv push --repo-id <your-username>/support-ops-env
```

After deployment, keep both URLs:

- Space page URL:
  `https://huggingface.co/spaces/<your-username>/support-ops-env`
- Runtime URL used by validators:
  `https://<your-username>-support-ops-env.hf.space`

## 4. Paste these into the submission form

GitHub Repository URL:

```text
https://github.com/<your-username>/support-ops-env
```

Hugging Face Space URL:

```text
https://huggingface.co/spaces/<your-username>/support-ops-env
```

## 5. Submission notes

- Project name: `support_ops_env`
- Runtime: FastAPI
- Space SDK: Docker
- Baseline entrypoint: `inference.py`
- OpenEnv manifest: `openenv.yaml`
- Main server entrypoint: `server.app:app`

## 6. What this submission demonstrates

- Real-world enterprise support and incident-response environment
- Three graded tasks with easy, medium, and hard progression
- Typed OpenEnv models and deterministic state transitions
- Dense milestone-based rewards in the `0.0-1.0` range
- Baseline agent using the OpenAI client and required environment variables
- Docker- and Hugging Face-ready packaging
