"""Regression tests for the support operations benchmark."""

from __future__ import annotations

import importlib
import sys
import unittest

from fastapi.testclient import TestClient

from support_ops_env.inference import TASK_IDS, heuristic_action
from support_ops_env.models import SupportOpsAction
from support_ops_env.server.app import app
from support_ops_env.server.support_ops_env_environment import SupportOpsEnvironment


class SupportOpsEnvironmentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.env = SupportOpsEnvironment()

    def test_reset_selects_requested_task(self) -> None:
        observation = self.env.reset(task_id="medium_sso_lockout")

        self.assertEqual(observation.task_id, "medium_sso_lockout")
        self.assertEqual(observation.difficulty, "medium")
        self.assertEqual(observation.score, 0.0)
        self.assertFalse(observation.done)

    def test_invalid_duplicate_link_returns_error(self) -> None:
        self.env.reset(task_id="hard_vip_outage_duplicate")

        observation = self.env.step(
            SupportOpsAction(
                action_type="link_duplicate",
                ticket_id="T-3002",
                duplicate_of="T-3002",
            )
        )

        self.assertEqual(observation.reward, -0.05)
        self.assertIn("cannot be a duplicate of itself", observation.last_error or "")

    def test_heuristic_policy_solves_all_tasks(self) -> None:
        for task_id in TASK_IDS:
            with self.subTest(task_id=task_id):
                observation = self.env.reset(task_id=task_id)

                while not observation.done:
                    action = heuristic_action(observation)
                    observation = self.env.step(action)

                self.assertGreaterEqual(observation.score, 0.9999)
                self.assertIsNone(observation.last_error)
                self.assertAlmostEqual(observation.guardrail_penalty_total, 0.0, places=6)

    def test_guardrail_penalty_reduces_score_for_premature_resolution(self) -> None:
        self.env.reset(task_id="medium_sso_lockout")
        observation = self.env.step(
            SupportOpsAction(
                action_type="search_kb",
                query="SAML metadata ACS URL entity ID IdP change",
            )
        )
        self.assertAlmostEqual(observation.score, 0.12, places=6)

        observation = self.env.step(
            SupportOpsAction(action_type="view_ticket", ticket_id="T-2001")
        )
        self.assertAlmostEqual(observation.score, 0.20, places=6)

        observation = self.env.step(
            SupportOpsAction(
                action_type="mark_status",
                ticket_id="T-2001",
                status="resolved",
            )
        )

        violation_ids = {
            violation.violation_id for violation in observation.guardrail_violations
        }
        self.assertIn("resolved_without_customer_input", violation_ids)
        self.assertAlmostEqual(observation.guardrail_penalty_total, 0.12, places=6)
        self.assertAlmostEqual(observation.score, 0.08, places=6)


class SupportOpsHttpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_http_reset_step_and_state_flow(self) -> None:
        reset_response = self.client.post("/reset", json={"task_id": "easy_refund_request"})
        self.assertEqual(reset_response.status_code, 200)
        self.assertEqual(
            reset_response.json()["observation"]["task_id"],
            "easy_refund_request",
        )

        step_response = self.client.post(
            "/step",
            json={
                "action": {
                    "action_type": "set_queue",
                    "ticket_id": "T-1001",
                    "queue": "billing",
                }
            },
        )
        self.assertEqual(step_response.status_code, 200)
        step_payload = step_response.json()
        self.assertAlmostEqual(step_payload["reward"], 0.15, places=6)
        self.assertEqual(
            step_payload["observation"]["last_action_summary"],
            "Moved T-1001 to queue 'billing'.",
        )

        state_response = self.client.get("/state")
        self.assertEqual(state_response.status_code, 200)
        self.assertEqual(state_response.json()["step_count"], 1)

    def test_top_level_server_app_import_works(self) -> None:
        # Hugging Face loads the ASGI app as `server.app`, so keep that import
        # path under test to catch packaging regressions early.
        sys.modules.pop("server.app", None)
        module = importlib.import_module("server.app")
        self.assertIsNotNone(getattr(module, "app", None))


if __name__ == "__main__":
    unittest.main()
