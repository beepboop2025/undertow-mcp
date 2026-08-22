from __future__ import annotations

import json
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import smoke_live_mcp, verify_core_pin


ROOT = Path(__file__).resolve().parents[1]


def _contract() -> dict:
    return json.loads((ROOT / "contract.json").read_text(encoding="utf-8"))


def _hosted_source(contract: dict, *, move_public_to_subscriber: bool = False) -> str:
    lines = [
        f'MODERN_PROTOCOL_VERSION = {contract["protocolVersions"][0]!r}',
        f'PROTOCOL_VERSION = {contract["protocolVersions"][1]!r}',
        "LEGACY_PROTOCOL_VERSIONS = (",
        "    PROTOCOL_VERSION,",
        *[f"    {value!r}," for value in contract["protocolVersions"][2:]],
        ")",
        "SUPPORTED_PROTOCOL_VERSIONS = (",
        "    MODERN_PROTOCOL_VERSION,",
        "    *LEGACY_PROTOCOL_VERSIONS,",
        ")",
        "SERVER_NAME = 'undertow'",
        f'SERVER_VERSION = {contract["serverVersion"]!r}',
        "TOOLS = {",
    ]
    for index, name in enumerate(contract["publicTools"]):
        visible = not (move_public_to_subscriber and index == 0)
        lines.append(f"    {name!r}: ('', {{}}, None, {visible!r}),")
    for name in contract["subscriberTools"]:
        lines.append(f"    {name!r}: ('', {{}}, None, False),")
    lines.extend(["}", "PROMPTS = {"])
    for name in contract["prompts"]:
        lines.append(f"    {name!r}: ('', '', [], None),")
    lines.extend(["}", ""])
    return "\n".join(lines)


def _core_fixture(*, move_public_to_subscriber: bool = False) -> tempfile.TemporaryDirectory:
    directory = tempfile.TemporaryDirectory()
    core = Path(directory.name)
    hosted = core / "deploy" / "hetzner" / "undertow-mcp"
    hosted.mkdir(parents=True)
    contract = _contract()
    (hosted / "undertow_mcp.py").write_text(
        _hosted_source(
            contract, move_public_to_subscriber=move_public_to_subscriber
        ),
        encoding="utf-8",
    )
    (core / "server.json").write_text(
        (ROOT / "server.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    directory.core = core  # type: ignore[attr-defined]
    return directory


def _fixture_receipt(core: Path) -> dict:
    receipt = verify_core_pin.verify_receipt()
    receipt = dict(receipt)
    receipt["artifacts"] = {
        path.as_posix(): {
            "sha256": hashlib.sha256((core / path).read_bytes()).hexdigest()
        }
        for path in verify_core_pin.RECEIPT_ARTIFACTS
    }
    return receipt


def _modern_result(result: dict) -> dict:
    result = dict(result)
    result["_meta"] = {
        "io.modelcontextprotocol/serverInfo": {
            "name": "undertow",
            "version": _contract()["serverVersion"],
        }
    }
    return result


class CorePinVerifierTests(unittest.TestCase):
    def test_exact_clean_core_contract_passes(self) -> None:
        fixture = _core_fixture()
        self.addCleanup(fixture.cleanup)
        pin = _contract()["canonical"]["releaseCommit"]
        with mock.patch.object(
            verify_core_pin, "_git_output", side_effect=[pin, ""]
        ):
            core = fixture.core  # type: ignore[attr-defined]
            verify_core_pin.verify(core, _fixture_receipt(core))

    def test_visibility_drift_fails_closed(self) -> None:
        fixture = _core_fixture(move_public_to_subscriber=True)
        self.addCleanup(fixture.cleanup)
        pin = _contract()["canonical"]["releaseCommit"]
        with mock.patch.object(
            verify_core_pin, "_git_output", side_effect=[pin, ""]
        ):
            with self.assertRaisesRegex(ValueError, "public tools"):
                core = fixture.core  # type: ignore[attr-defined]
                verify_core_pin.verify(core, _fixture_receipt(core))

    def test_wrong_sha_and_dirty_checkout_fail_closed(self) -> None:
        fixture = _core_fixture()
        self.addCleanup(fixture.cleanup)
        core = fixture.core  # type: ignore[attr-defined]
        with mock.patch.object(
            verify_core_pin, "_git_output", return_value="0" * 40
        ):
            with self.assertRaisesRegex(ValueError, "listing pins"):
                verify_core_pin.verify(core, _fixture_receipt(core))
        pin = _contract()["canonical"]["releaseCommit"]
        with mock.patch.object(
            verify_core_pin,
            "_git_output",
            side_effect=[pin, " M deploy/hetzner/undertow-mcp/undertow_mcp.py"],
        ):
            with self.assertRaisesRegex(ValueError, "modified tracked files"):
                verify_core_pin.verify(core, _fixture_receipt(core))

    def test_source_receipt_is_bound_to_contract_and_exact_artifacts(self) -> None:
        receipt = verify_core_pin.verify_receipt()
        self.assertEqual(receipt["releaseCommit"], _contract()["canonical"]["releaseCommit"])

        fixture = _core_fixture()
        self.addCleanup(fixture.cleanup)
        core = fixture.core  # type: ignore[attr-defined]
        mismatched = _fixture_receipt(core)
        hosted_path = verify_core_pin.HOSTED_SERVER.as_posix()
        mismatched["artifacts"][hosted_path]["sha256"] = "0" * 64
        pin = _contract()["canonical"]["releaseCommit"]
        with mock.patch.object(
            verify_core_pin, "_git_output", side_effect=[pin, ""]
        ):
            with self.assertRaisesRegex(ValueError, "source-receipt mismatch"):
                verify_core_pin.verify(core, mismatched)


class LiveSmokeTests(unittest.TestCase):
    def test_strict_decoder_accepts_sse_and_rejects_duplicates(self) -> None:
        envelope = smoke_live_mcp._decode_envelope(
            b'event: message\ndata: {"jsonrpc":"2.0","id":4,"result":{}}\n\n',
            "text/event-stream; charset=utf-8",
            4,
        )
        self.assertEqual(envelope["result"], {})
        with self.assertRaisesRegex(RuntimeError, "duplicate JSON key"):
            smoke_live_mcp._decode_envelope(
                b'{"jsonrpc":"2.0","id":1,"id":1,"result":{}}',
                "application/json",
                1,
            )

    def test_smoke_covers_initialize_catalogs_and_representative_call(self) -> None:
        contract = _contract()
        seen: list[tuple[str, dict, dict]] = []

        def fake_rpc(endpoint, method, params, request_id, **kwargs):
            self.assertEqual(endpoint, "https://example.test/mcp")
            seen.append((method, params, kwargs))
            if method == "initialize":
                return {
                    "protocolVersion": "2025-11-25",
                    "serverInfo": {
                        "name": "undertow",
                        "version": contract["serverVersion"],
                    },
                }
            if method == "server/discover":
                return _modern_result(
                    {
                        "supportedVersions": contract["protocolVersions"],
                        "publicTools": contract["publicTools"],
                        "subscriberTools": contract["subscriberTools"],
                    }
                )
            if method == "tools/list":
                return _modern_result(
                    {
                        "tools": [
                            {
                                "name": name,
                                "inputSchema": {"type": "object"},
                                "annotations": {
                                    "readOnlyHint": True,
                                    "idempotentHint": True,
                                    "openWorldHint": False,
                                },
                            }
                            for name in contract["publicTools"]
                        ]
                    }
                )
            if method == "prompts/list":
                return {"prompts": [{"name": name} for name in contract["prompts"]]}
            if method == "resources/list":
                return {"resources": []}
            if method == "resources/templates/list":
                return {"resourceTemplates": contract["resourceTemplates"]}
            if method == "tools/call":
                return {
                    "isError": False,
                    "structuredContent": {
                        "authenticated": False,
                        "tier": "anon",
                        "subscriber_tools": contract["subscriberTools"],
                    },
                }
            self.fail(f"unexpected method {method}")

        with mock.patch.object(smoke_live_mcp, "_rpc", side_effect=fake_rpc), mock.patch.object(
            smoke_live_mcp, "_notify"
        ) as notify:
            smoke_live_mcp.smoke("https://example.test/mcp")

        self.assertEqual(
            [method for method, _, _ in seen],
            [
                "initialize",
                "server/discover",
                "tools/list",
                "prompts/list",
                "resources/list",
                "resources/templates/list",
                "tools/call",
            ],
        )
        call = seen[-1]
        self.assertEqual(call[1]["name"], "agent_access_status")
        self.assertEqual(call[1]["arguments"], {})
        self.assertEqual(call[2]["name"], "agent_access_status")
        notify.assert_called_once_with(
            "https://example.test/mcp",
            "notifications/initialized",
            {},
            protocol="2025-11-25",
        )


if __name__ == "__main__":
    unittest.main()
