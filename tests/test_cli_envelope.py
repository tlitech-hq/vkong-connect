"""Contract tests for the ``{ok, data, code, error}`` envelope printed by current VKong CLIs.

The fake mirrors the real CLI's observable behavior: ``run`` has no JSON output and
no idempotency flag, the App and Run are recorded before renting, App names are not
unique, and there is no log command.
"""

from __future__ import annotations

import json
import os
import stat
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from vkong_connect.client import CLIContext, VKongCLI
from vkong_connect.errors import CapabilityUnavailableError, ContractError, VKongCLIError


FAKE_CLI = '''\
#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

state_path = Path(os.environ["FAKE_STATE"])
state = json.loads(state_path.read_text())
args = sys.argv[1:]
workspace = None
if args[:1] == ["--workspace"]:
    workspace, args = args[1], args[2:]
json_mode = "--json" in args
args = [arg for arg in args if arg != "--json"]
state["calls"].append(args)

def ok(data):
    print(json.dumps({"ok": True, "data": data}))

def fail(message, code="execution_failed", exit_code=1):
    print(json.dumps({"ok": False, "code": code, "error": message}))
    state_path.write_text(json.dumps(state))
    raise SystemExit(exit_code)

def app_by(identifier):
    matches = [app for app in state["apps"] if identifier in (app["id"], app["name"])]
    if not matches:
        fail(f"App {identifier!r} not found")
    if len(matches) > 1:
        fail("multiple Apps are named [opaque] - use an App ID")
    return matches[0]

if args[:1] == ["version"]:
    ok({"version": "0.0.0-dev"})
elif args[:1] == ["whoami"]:
    ok({"login": "alice", "workspace_id": state["workspace"], "workspace_role": "owner"})
elif args[:1] == ["validate"]:
    ok({"root": args[-1], "warnings": [], "scan": "clean", "findings": []})
elif args[:2] == ["app", "list"]:
    ok({"apps": state["apps"]})
elif args[:2] == ["app", "show"]:
    app = app_by(args[2])
    run = next((r for r in state["runs"] if r["app_id"] == app["id"] and r["status"] == "running"), None)
    ok({"app": app, "active_run": run, "domain": None})
elif args[:2] == ["app", "stop"]:
    if "--yes" not in args:
        fail("App stop requires --yes.", code="app_confirmation_required", exit_code=2)
    app = app_by(args[2])
    app["status"] = app["runtime_status"] = "stopped"
    app["active_instance_id"] = ""
    for run in state["runs"]:
        if run["app_id"] == app["id"]:
            run["status"] = "stopped"
    ok({"app": app})
elif args[:1] == ["runs"]:
    ok({"runs": state["runs"]})
elif args[:1] == ["run"]:
    if workspace != state["workspace"] or os.environ.get("SERVER_PUBLIC_URL") != "https://vkong.test":
        fail("run was not bound to the expected server and workspace")
    if json_mode:
        fail("JSON output is not available for vkong run yet.", code="json_not_supported")
    if state.get("run_fails"):
        print("no machine available", file=sys.stderr)
        state_path.write_text(json.dumps(state))
        raise SystemExit(1)
    number = len(state["apps"]) + 1
    name = state.get("next_app_name")
    config = Path(args[args.index("-C") + 1]) / "vkong.yaml"
    if config.is_file():
        name = json.loads(next(l for l in config.read_text().splitlines() if l.startswith("app:"))[4:])
    app = {"id": f"app_{number}", "name": name, "kind": "ephemeral",
           "status": "running", "runtime_status": "running", "archived": False,
           "active_instance_id": f"vk_{number}"}
    state["apps"].append(app)
    state["runs"].append({"id": f"run_{number}", "app_id": app["id"], "instance_id": f"vk_{number}",
                          "operation": "run", "status": "running", "created_at": "2026-09-29T00:00:00Z"})
    print("Human progress output that must never be parsed")
else:
    fail(f"unknown command {args!r}")
state_path.write_text(json.dumps(state))
'''


class EnvelopeCLITests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.binary = root / "vkong"
        self.binary.write_text(textwrap.dedent(FAKE_CLI), encoding="utf-8")
        self.binary.chmod(self.binary.stat().st_mode | stat.S_IXUSR)
        self.state_path = root / "state.json"
        self.write_state(apps=[], runs=[])
        self.client = self.make_client("ws_team")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def make_client(self, workspace: str) -> VKongCLI:
        return VKongCLI(
            str(self.binary), timeout=10,
            env={"PATH": os.path.dirname(sys.executable) + os.pathsep + os.environ.get("PATH", ""),
                 "FAKE_STATE": str(self.state_path)},
            context=CLIContext("https://vkong.test", workspace),
        )

    def write_state(self, **values) -> None:
        state = {"workspace": "ws_team", "apps": [], "runs": [], "calls": [],
                 "next_app_name": "unsloth-job-abc"}
        state.update(values)
        self.state_path.write_text(json.dumps(state), encoding="utf-8")

    def state(self) -> dict:
        return json.loads(self.state_path.read_text(encoding="utf-8"))

    def run_calls(self) -> list[list[str]]:
        return [call for call in self.state()["calls"] if "run" in call]

    def test_readiness_maps_identity_and_rejects_other_workspace(self) -> None:
        self.assertEqual(self.client.version()["version"], "0.0.0-dev")
        identity = self.client.whoami()
        self.assertEqual((identity.user, identity.workspace), ("alice", "ws_team"))
        with self.assertRaisesRegex(ContractError, "different workspace"):
            self.make_client("ws_other").whoami()

    def test_validate_reports_valid_on_clean_scan(self) -> None:
        self.assertTrue(self.client.validate(Path(self.temporary.name))["valid"])

    def test_start_rents_once_and_retry_reconciles_same_app(self) -> None:
        project = Path(self.temporary.name)
        first = self.client.start_task(project, idempotency_key="k", app_name="unsloth-job-abc")
        self.assertEqual((first.app_id, first.run_id, first.instance_id), ("app_1", "run_1", "vk_1"))
        self.assertFalse(first.reconciled)
        call = self.run_calls()[0]
        self.assertEqual(call[:3], ["run", "-C", str(project)])
        self.assertIn("--detach", call)
        self.assertIn("--auto-stop", call)
        self.assertNotIn("--idempotency-key", call)

        retry = self.client.start_task(project, idempotency_key="k", app_name="unsloth-job-abc")
        self.assertTrue(retry.reconciled)
        self.assertEqual((retry.app_id, retry.run_id), ("app_1", "run_1"))
        self.assertEqual(len(self.run_calls()), 1)

    def test_start_refuses_to_guess_between_duplicate_app_names(self) -> None:
        app = {"kind": "ephemeral", "status": "stopped", "runtime_status": "stopped",
               "archived": False, "active_instance_id": "", "name": "unsloth-job-abc"}
        self.write_state(apps=[{**app, "id": "app_a"}, {**app, "id": "app_b"}])
        with self.assertRaisesRegex(ContractError, "2 VKong Apps"):
            self.client.start_task(Path(self.temporary.name), idempotency_key="k",
                                   app_name="unsloth-job-abc")
        self.assertEqual(self.run_calls(), [])

    def test_start_failure_is_reported_without_parsing_output(self) -> None:
        self.write_state(run_fails=True)
        with self.assertRaises(VKongCLIError) as caught:
            self.client.start_task(Path(self.temporary.name), idempotency_key="k",
                                   app_name="unsloth-job-abc")
        self.assertEqual(caught.exception.details["app_ids"], [])

    def test_start_requires_app_name(self) -> None:
        with self.assertRaisesRegex(ContractError, "App name"):
            self.client.start_task(Path(self.temporary.name), idempotency_key="k")

    def test_status_runs_and_stop(self) -> None:
        self.client.start_task(Path(self.temporary.name), idempotency_key="k",
                               app_name="unsloth-job-abc")
        status = self.client.app_show("app_1")
        self.assertEqual((status.state, status.run_id), ("running", "run_1"))
        self.assertEqual([run["id"] for run in self.client.runs("app_1")], ["run_1"])
        stopped = self.client.stop_app("app_1")
        self.assertEqual((stopped.state, stopped.run_id, stopped.instance_id), ("stopped", None, None))
        with self.assertRaisesRegex(ContractError, "App ID"):
            self.client.runs("unsloth-job-abc")

    def test_error_envelope_becomes_cli_error(self) -> None:
        with self.assertRaises(VKongCLIError) as caught:
            self.client.app_show("missing")
        self.assertEqual(caught.exception.cli_code, "execution_failed")

    def test_log_stream_is_reported_unavailable(self) -> None:
        with self.assertRaises(CapabilityUnavailableError):
            next(self.client.follow_logs("run_1"))


if __name__ == "__main__":
    unittest.main()
