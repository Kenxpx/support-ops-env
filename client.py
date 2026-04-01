"""Support operations OpenEnv client."""

from __future__ import annotations

from typing import Any, Dict

from openenv.core import EnvClient
from openenv.core.client_types import StepResult

from .models import SupportOpsAction, SupportOpsObservation, SupportOpsState


class SupportOpsEnv(EnvClient[SupportOpsAction, SupportOpsObservation, SupportOpsState]):
    """Client for the support operations environment."""

    def _step_payload(self, action: SupportOpsAction) -> Dict[str, Any]:
        return action.model_dump(exclude_none=True)

    def _parse_result(self, payload: Dict[str, Any]) -> StepResult[SupportOpsObservation]:
        obs_data = payload.get("observation", {})
        observation = SupportOpsObservation.model_validate(
            {
                **obs_data,
                "done": payload.get("done", False),
                "reward": payload.get("reward"),
            }
        )
        return StepResult(
            observation=observation,
            reward=payload.get("reward"),
            done=payload.get("done", False),
        )

    def _parse_state(self, payload: Dict[str, Any]) -> SupportOpsState:
        return SupportOpsState.model_validate(payload)
