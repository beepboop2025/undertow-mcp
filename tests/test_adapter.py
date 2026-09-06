"""Synthetic network fixtures; no live market or subscriber calls."""

import asyncio
import copy
import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from mcp import Client, types
from mcp.shared.exceptions import MCPError

from undertow_mcp_adapter import (
    CONTRACT,
    ENDPOINT,
    MAX_REQUEST_BYTES,
    MAX_RESPONSE_BYTES,
    HostedPublicClient,
    create_server,
)


def native(result):
    return {
        **result,
        "_meta": {
            "io.modelcontextprotocol/serverInfo": {
                "name": "undertow",
                "version": "1.10.0",
            }
        },
    }


def tool_rows():
    return [
        {
            "name": name,
            "description": "Synthetic test description for " + name,
            "inputSchema": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            "annotations": {
                "readOnlyHint": True,
                "idempotentHint": True,
                "openWorldHint": False,
            },
        }
        for name in CONTRACT["publicTools"]
    ]


def response(result, *, raw=None, status=200, headers=None):
    return httpx.Response(
        status,
        content=raw
        if raw is not None
        else json.dumps({"jsonrpc": "2.0", "id": 1, "result": result}).encode(),
        headers=headers or {"Content-Type": "application/json"},
    )


class AdapterTests(unittest.IsolatedAsyncioTestCase):
    async def client(self, handler):
        client = HostedPublicClient(transport=httpx.MockTransport(handler))
        self.addAsyncCleanup(client.aclose)
        return client

    async def test_native_rights_hold_and_tool_error_preserved_exactly(self):
        for failed in (False, True):
            payload = native(
                {
                    "content": [
                        {
                            "type": "text",
                            "text": '{"status":"unavailable","reason":"rights_manifest_not_approved"}',
                        }
                    ],
                    "structuredContent": {
                        "status": "unavailable",
                        "reason": "rights_manifest_not_approved",
                        "executable": False,
                    },
                    "isError": failed,
                }
            )
            client = await self.client(lambda req: response(payload))
            got = await client.call_tool(
                None,
                types.CallToolRequestParams(
                    name="trade_safety_exit_context", arguments={}
                ),
            )
            self.assertEqual(
                got.model_dump(by_alias=True, exclude_none=True, exclude_unset=True),
                payload,
            )

    async def test_fixed_origin_no_auth_or_client_metadata_or_environment_proxy(self):
        seen = []

        def handler(req):
            seen.append(req)
            return response(native({"content": [], "isError": False}))

        with patch.dict(
            os.environ,
            {
                "Authorization": "Bearer do-not-forward",
                "HTTPS_PROXY": "http://do-not-use.invalid:1",
            },
        ):
            client = await self.client(handler)
            params = types.CallToolRequestParams.model_validate(
                {
                    "name": "exit_cost",
                    "arguments": {"size_usd": 1000},
                    "_meta": {"Authorization": "Bearer never-forward"},
                }
            )
            await client.call_tool(None, params)
        self.assertEqual(str(seen[0].url), ENDPOINT)
        self.assertNotIn("authorization", seen[0].headers)
        self.assertNotIn(b"never-forward", seen[0].content)
        self.assertEqual(
            json.loads(seen[0].content)["params"]["arguments"], {"size_usd": 1000}
        )
        self.assertEqual(seen[0].headers["Mcp-Name"], "exit_cost")
        self.assertFalse(client.client.follow_redirects)
        self.assertFalse(client.client.trust_env)

    async def test_unknown_subscriber_and_task_requests_never_reach_network(self):
        seen = []
        client = await self.client(lambda req: seen.append(req))
        for name in ("board_full", "arbitrary_url", "submit_order"):
            with self.subTest(name=name), self.assertRaises(MCPError):
                await client.call_tool(
                    None, types.CallToolRequestParams(name=name, arguments={})
                )
        with self.assertRaises(MCPError):
            await client.call_tool(
                None,
                types.CallToolRequestParams.model_validate(
                    {"name": "exit_cost", "task": {"ttl": 1000}}
                ),
            )
        self.assertEqual(seen, [])

    async def test_native_schema_annotations_and_descriptions_are_preserved(self):
        rows = tool_rows()
        rows[2]["inputSchema"] = {
            "type": "object",
            "properties": {"size_usd": {"type": "number", "description": "USD size"}},
            "additionalProperties": False,
        }
        payload = native({"tools": rows})
        client = await self.client(lambda req: response(payload))
        got = await client.list_tools(None, None)
        self.assertEqual(
            got.model_dump(by_alias=True, exclude_none=True, exclude_unset=True),
            payload,
        )

    async def test_inventory_version_and_readonly_drift_fail_closed(self):
        cases = []
        payload = native({"tools": tool_rows()})
        changed = copy.deepcopy(payload)
        changed["tools"].pop()
        cases.append(changed)
        changed = copy.deepcopy(payload)
        changed["tools"][0]["annotations"]["readOnlyHint"] = False
        cases.append(changed)
        changed = copy.deepcopy(payload)
        changed["tools"][0]["annotations"]["destructiveHint"] = True
        cases.append(changed)
        changed = copy.deepcopy(payload)
        changed["_meta"]["io.modelcontextprotocol/serverInfo"]["version"] = "1.9.0"
        cases.append(changed)
        changed = copy.deepcopy(payload)
        changed["_meta"]["io.modelcontextprotocol/serverInfo"]["name"] = "other"
        cases.append(changed)
        changed = copy.deepcopy(payload)
        changed["nextCursor"] = "uninspected-tools"
        cases.append(changed)
        for index, item in enumerate(cases):
            with self.subTest(index=index):
                client = await self.client(lambda req: response(item))
                with self.assertRaises(MCPError):
                    await client.list_tools(None, None)

    async def test_redirect_not_followed_http_errors_and_malformed_responses_fail(self):
        cases = [
            response(None, status=302, headers={"Location": "https://other.invalid"}),
            response(None, status=429),
            response(None, raw=b'{"jsonrpc":"2.0","id":1,"id":1,"result":{}}'),
            response(None, raw=b'{"jsonrpc":"2.0","id":2,"result":{}}'),
            response(None, raw=b'{"jsonrpc":"2.0","id":true,"result":{}}'),
            response(None, raw=b'{"jsonrpc":"2.0","id":1,"error":{},"result":{}}'),
            response(None, raw=b'{"jsonrpc":"2.0","id":1,"result":{"value":NaN}}'),
            response(None, headers={"Content-Type": "text/html"}),
            response(None, raw=b"x" * (MAX_RESPONSE_BYTES + 1)),
            response(
                None,
                headers={"Content-Type": "application/json", "Content-Encoding": "br"},
            ),
        ]
        for index, item in enumerate(cases):
            seen = []

            def handler(req):
                seen.append(req)
                return item

            client = await self.client(handler)
            with self.subTest(index=index), self.assertRaises(MCPError):
                await client.rpc("tools/list", {})
            self.assertEqual(len(seen), 1)

    async def test_native_rpc_error_is_not_converted_to_success(self):
        raw = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "error": {
                    "code": -32602,
                    "message": "unsupported size",
                    "data": {"allowed": [1000]},
                },
            }
        ).encode()
        client = await self.client(lambda req: response(None, raw=raw))
        with self.assertRaises(MCPError) as caught:
            await client.rpc("tools/list", {})
        self.assertEqual(caught.exception.code, -32602)
        self.assertEqual(caught.exception.data, {"allowed": [1000]})

    async def test_request_budget_timeout_and_cancellation(self):
        seen = []

        async def handler(req):
            seen.append(req)
            await asyncio.sleep(60)

        client = await self.client(handler)
        with self.assertRaises(MCPError):
            await client.rpc(
                "tools/call", {"arguments": {"x": "x" * MAX_REQUEST_BYTES}}
            )
        self.assertEqual(seen, [])
        with patch("undertow_mcp_adapter.TIMEOUT_SECONDS", 0.01):
            with self.assertRaises(MCPError) as caught:
                await client.rpc("tools/list", {})
        self.assertEqual(caught.exception.message, "upstream_unavailable")
        task = asyncio.create_task(client.rpc("tools/list", {}))
        await asyncio.sleep(0)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task

    async def test_real_sdk_server_client_roundtrip(self):
        """Actual official MCP dispatch and validation, fake only upstream HTTP."""
        seen = []

        def handler(req):
            method = json.loads(req.content)["method"]
            seen.append(method)
            result = {
                "tools/list": {"tools": tool_rows()},
                "tools/call": {
                    "content": [{"type": "text", "text": "synthetic refusal"}],
                    "isError": True,
                },
                "prompts/list": {
                    "prompts": [
                        {"name": n, "description": "Synthetic prompt"}
                        for n in CONTRACT["prompts"]
                    ]
                },
                "prompts/get": {
                    "messages": [
                        {
                            "role": "user",
                            "content": {"type": "text", "text": "synthetic guidance"},
                        }
                    ]
                },
            }[method]
            return response(native(result))

        upstream = await self.client(handler)
        async with Client(create_server(upstream)) as sdk:
            tools = await sdk.list_tools()
            self.assertEqual([t.name for t in tools.tools], CONTRACT["publicTools"])
            result = await sdk.call_tool("exit_cost", {})
            self.assertTrue(result.is_error)
            prompts = await sdk.list_prompts()
            self.assertEqual([p.name for p in prompts.prompts], CONTRACT["prompts"])
            prompt = await sdk.get_prompt("exit_cost_check", {})
            self.assertEqual(prompt.messages[0].content.text, "synthetic guidance")
        self.assertEqual(
            seen, ["tools/list", "tools/call", "prompts/list", "prompts/get"]
        )

    def test_installed_contract_is_exact_source_verified_contract(self):
        original = json.loads(
            (Path(__file__).resolve().parents[1] / "contract.json").read_text()
        )
        self.assertEqual(CONTRACT, original)
