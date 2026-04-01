"""FastAPI application for the support operations environment."""

from __future__ import annotations

try:
    from openenv.core.env_server.http_server import create_app
except Exception as exc:  # pragma: no cover
    raise ImportError(
        "openenv is required for the web interface. Install dependencies with "
        "'pip install -e .' or 'uv sync'."
    ) from exc

try:
    from ..models import SupportOpsAction, SupportOpsObservation
    from .support_ops_env_environment import SupportOpsEnvironment
except ImportError:
    from models import SupportOpsAction, SupportOpsObservation
    from server.support_ops_env_environment import SupportOpsEnvironment


# Use one shared environment instance so the HTTP reset/step/state contract is
# stateful across requests. This matches the Round 1 validator expectations and
# keeps behavior aligned with the baseline agent loop. WebSocket usage still
# works for a single active session, which is sufficient for local validation
# and hackathon evaluation.
_SHARED_ENV = SupportOpsEnvironment()

app = create_app(
    lambda: _SHARED_ENV,
    SupportOpsAction,
    SupportOpsObservation,
    env_name="support_ops_env",
    max_concurrent_envs=1,
)


def main(host: str = "0.0.0.0", port: int = 8000) -> None:
    import uvicorn

    uvicorn.run(app, host=host, port=port)


def run_default() -> None:
    """Run the server with default host and port."""

    main()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Run the support_ops_env FastAPI server."
    )
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    main(host=args.host, port=args.port)
