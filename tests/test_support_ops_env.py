"""Regression tests for the support operations benchmark."""

from __future__ import annotations

import importlib
import subprocess
import sys
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from support_ops_env.inference import (
    BENCHMARK,
    TASK_IDS,
    candidate_docker_images,
    format_end_line,
    format_start_line,
    format_step_line,
    heuristic_action,
    resolve_local_docker_image,
)
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

    def test_search_actions_surface_expected_ticket_and_kb_matches(self) -> None:
        self.env.reset(task_id="hard_partner_token_leak")

        observation = self.env.step(
            SupportOpsAction(
                action_type="search_tickets",
                query="OrbitPay token exposure duplicate security",
            )
        )
        self.assertIn(
            "T-4002",
            [ticket.ticket_id for ticket in observation.ticket_search_results],
        )

        observation = self.env.step(
            SupportOpsAction(
                action_type="search_kb",
                query="partner API token leak audit logs rotate credential sev2",
            )
        )
        self.assertIn(
            "KB-SEC-09",
            [article.article_id for article in observation.kb_search_results],
        )

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

    def test_penalized_episode_still_finishes_after_all_milestones(self) -> None:
        self.env.reset(task_id="medium_sso_lockout")

        steps = [
            SupportOpsAction(
                action_type="send_reply",
                ticket_id="T-2001",
                reply="We are looking into this.",
            ),
            SupportOpsAction(
                action_type="search_kb",
                query="SAML metadata ACS URL entity ID IdP change",
            ),
            SupportOpsAction(action_type="view_ticket", ticket_id="T-2001"),
            SupportOpsAction(
                action_type="set_queue",
                ticket_id="T-2001",
                queue="technical_support",
            ),
            SupportOpsAction(
                action_type="set_priority",
                ticket_id="T-2001",
                priority="high",
            ),
            SupportOpsAction(action_type="add_tag", ticket_id="T-2001", tag="sso"),
            SupportOpsAction(
                action_type="add_tag",
                ticket_id="T-2001",
                tag="enterprise_auth",
            ),
            SupportOpsAction(
                action_type="add_internal_note",
                ticket_id="T-2001",
                note=(
                    "Likely IdP metadata mismatch after the change. Request fresh "
                    "SAML metadata and verify ACS URL and entity ID."
                ),
            ),
            SupportOpsAction(
                action_type="send_reply",
                ticket_id="T-2001",
                reply=(
                    "Please send a fresh SAML metadata XML export from your identity "
                    "provider and confirm the ACS URL and entity ID so we can compare "
                    "the configuration."
                ),
            ),
            SupportOpsAction(
                action_type="mark_status",
                ticket_id="T-2001",
                status="pending",
            ),
        ]

        for action in steps:
            observation = self.env.step(action)

        self.assertTrue(observation.done)
        self.assertAlmostEqual(observation.guardrail_penalty_total, 0.08, places=6)
        self.assertAlmostEqual(observation.score, 0.92, places=6)


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


class InferenceDockerTests(unittest.TestCase):
    def test_create_llm_client_prefers_injected_api_key(self) -> None:
        sys.modules.pop("support_ops_env.inference", None)
        with patch.dict(
            "os.environ",
            {
                "API_BASE_URL": "https://proxy.example/v1",
                "API_KEY": "validator-key",
                "HF_TOKEN": "hf-fallback-token",
                "MODEL_NAME": "proxy-model",
            },
            clear=False,
        ):
            inference_module = importlib.import_module("support_ops_env.inference")
            client = inference_module.create_llm_client()

        self.assertIsNotNone(client)
        self.assertEqual(str(client.base_url), "https://proxy.example/v1/")
        self.assertEqual(client.api_key, "validator-key")

    def test_candidate_docker_images_include_openenv_fallback(self) -> None:
        self.assertEqual(
            candidate_docker_images("support-ops-env:latest"),
            [
                "support-ops-env:latest",
                "support-ops-env",
                "openenv-support-ops-env:latest",
                "openenv-support-ops-env",
            ],
        )

    @patch("support_ops_env.inference.subprocess.run")
    def test_resolve_local_docker_image_prefers_existing_fallback(
        self,
        mock_run,
    ) -> None:
        mock_run.side_effect = [
            subprocess.CompletedProcess(
                ["docker", "image", "inspect", "support-ops-env:latest"],
                1,
                "",
                "No such image",
            ),
            subprocess.CompletedProcess(
                ["docker", "image", "inspect", "support-ops-env"],
                1,
                "",
                "No such image",
            ),
            subprocess.CompletedProcess(
                ["docker", "image", "inspect", "openenv-support-ops-env:latest"],
                0,
                "[]",
                "",
            ),
        ]

        self.assertEqual(
            resolve_local_docker_image("support-ops-env:latest"),
            "openenv-support-ops-env:latest",
        )

    def test_submission_log_format_matches_required_shape(self) -> None:
        action = SupportOpsAction(action_type="set_queue", ticket_id="T-1001", queue="billing")

        self.assertEqual(
            format_start_line("easy_refund_request", BENCHMARK, "heuristic"),
            "[START] task=easy_refund_request env=support_ops_env model=heuristic",
        )
        self.assertEqual(
            format_step_line(1, action, 0.15, False, None),
            "[STEP] step=1 action=set_queue(T-1001,billing) reward=0.15 done=false error=null",
        )
        self.assertEqual(
            format_end_line(True, 3, 1.0, [0.0, 0.0, 1.0]),
            "[END] success=true steps=3 score=1.00 rewards=0.00,0.00,1.00",
        )


if __name__ == "__main__":
    unittest.main()
