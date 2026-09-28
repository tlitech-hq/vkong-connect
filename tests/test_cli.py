from __future__ import annotations

import os
import stat
import tempfile
import textwrap
import unittest
from pathlib import Path

from vkong_connect.client import CLIContext, VKongCLI
from vkong_connect.errors import ContractError, VKongCLIError


FAKE_CLI = '''\
#!/usr/bin/env python3
import json
import os
import sys

args = sys.argv[1:]
if args[:1] == ["--workspace"]:
    workspace = args[1]
    args = args[2:]
else:
    workspace = None
schema = {"schema_version": "vkong.cli.v1"}
if args[:1] == ["version"]:
    print(json.dumps({**schema, "version": "0.1.0"}))
elif args[:1] == ["whoami"]:
    print(json.dumps({**schema, "user": "alice", "workspace": "team"}))
elif args[:1] == ["validate"]:
    print(json.dumps({**schema, "valid": True}))
elif args[:1] == ["run"]:
    if workspace != "ws_team" or os.environ.get("SERVER_PUBLIC_URL") != "https://vkong.test":
        raise SystemExit(9)
    required = {"--detach", "--auto-stop", "--json", "--idempotency-key"}
    if not required.issubset(args):
        print(json.dumps({**schema, "error": {"code": "missing_flags", "message": repr(args), "retriable": False}}))
        raise SystemExit(2)
    key = args[args.index("--idempotency-key") + 1]
    print(json.dumps({**schema, "app_id": "app_1", "app_name": "unsloth-job", "run_id": "run_1", "instance_id": "vk_1", "state": "running", "hourly_price": 1.25, "currency": "USD", "key": key}))
elif args[:2] == ["app", "show"]:
    print(json.dumps({**schema, "app_id": "app_1", "app_name": "unsloth-job", "run_id": "run_1", "instance_id": "vk_1", "state": "running"}))
elif args[:1] == ["runs"]:
    print(json.dumps({**schema, "runs": [{"run_id": "run_1", "state": "running"}]}))
elif args[:2] == ["app", "stop"]:
    print(json.dumps({**schema, "app_id": "app_1", "app_name": "unsloth-job", "run_id": "run_1", "instance_id": None, "state": "stopping"}))
elif args[:1] == ["logs"]:
    if "--follow" not in args or args[args.index("--format") + 1] != "jsonl":
        raise SystemExit(2)
    print("diagnostic on stderr", file=sys.stderr)
    print(json.dumps({"seq": 1, "line": "first"}))
    print(json.dumps({"seq": 2, "line": "second"}))
elif args[:1] == ["fail"]:
    print(json.dumps({**schema, "error": {"code": "no_capacity", "message": "No GPU", "retriable": True}}))
    raise SystemExit(7)
else:
    print(json.dumps({**schema, "error": {"code": "bad_args", "message": repr(args), "retriable": False}}))
    raise SystemExit(2)
'''


class VKongCLITests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.binary = Path(self.temporary.name) / "vkong"
        self.binary.write_text(textwrap.dedent(FAKE_CLI), encoding="utf-8")
        self.binary.chmod(self.binary.stat().st_mode | stat.S_IXUSR)
        self.client = VKongCLI(
            str(self.binary), timeout=5,
            context=CLIContext("https://vkong.test", "ws_team"),
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_identity_start_status_logs_and_stop(self) -> None:
        identity = self.client.whoami()
        self.assertEqual(identity.workspace, "team")
        start = self.client.start_task(Path(self.temporary.name), idempotency_key="request-1")
        self.assertEqual(start.run_id, "run_1")
        self.assertEqual(start.hourly_price, 1.25)
        self.assertEqual(self.client.app_show("app_1").state, "running")
        self.assertEqual(self.client.runs("app_1")[0]["run_id"], "run_1")
        self.assertEqual([item["seq"] for item in self.client.follow_logs("run_1")], [1, 2])
        self.assertEqual(self.client.stop_app("app_1").state, "stopping")

    def test_structured_error_is_preserved(self) -> None:
        with self.assertRaises(VKongCLIError) as raised:
            self.client._run_json(["fail", "--json"])
        self.assertEqual(raised.exception.cli_code, "no_capacity")
        self.assertTrue(raised.exception.retriable)
        self.assertEqual(raised.exception.exit_code, 7)

    def test_unbound_rental_mutations_fail_before_spawning_cli(self) -> None:
        unbound = VKongCLI(str(self.binary))
        with self.assertRaisesRegex(ContractError, "bound server and workspace"):
            unbound.start_task(Path(self.temporary.name), idempotency_key="key")
        with self.assertRaisesRegex(ContractError, "bound server and workspace"):
            unbound.stop_app("app_1")

    def test_context_rejects_ambiguous_or_unsafe_values(self) -> None:
        for server, workspace in (
            ("http://vkong.test", "ws_team"),
            ("https://user@vkong.test", "ws_team"),
            ("https://vkong.test/path", "ws_team"),
            ("https://vkong.test", "--workspace"),
            ("https://vkong.test", "team-name"),
        ):
            with self.subTest(server=server, workspace=workspace):
                with self.assertRaises(ContractError):
                    CLIContext(server, workspace)

    def test_unknown_schema_fails_closed(self) -> None:
        with self.assertRaisesRegex(ContractError, "unsupported VKong CLI schema"):
            VKongCLI._schema({"version": "0.0.0-dev"})


if __name__ == "__main__":
    unittest.main()
