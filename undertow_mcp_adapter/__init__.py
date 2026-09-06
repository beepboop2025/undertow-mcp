"""Anonymous, bounded stdio transport for the hosted Undertow public tools."""

from __future__ import annotations

import asyncio
import json
from importlib.resources import files
from typing import Any

import httpx
from mcp import types
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.shared.exceptions import MCPError

ENDPOINT = "https://api.seiche.info/undertow/mcp"
PROTOCOL = "2026-07-28"
VERSION = "0.1.0"
MAX_REQUEST_BYTES = 64 * 1024
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
TIMEOUT_SECONDS = 10.0
CONTRACT = json.loads(files(__package__).joinpath("contract.json").read_text())
INSTRUCTIONS = (
    "Anonymous read-only access to Undertow's hosted public evidence. "
    "Use exit_cost for approximate nearest-rung snapshot estimates; use "
    "trade_safety_exit_context only for its exact BTC/USD sell evidence contract. "
    "Inspect observation times, PARTIAL, ACCRUING and unavailable states. "
    "Rights refusals remain unavailable; no result authorizes execution. "
    "Subscriber tools require a direct hosted connection and are absent here. "
    "This adapter forwards evidence and does not calculate prices or place orders."
)


def _error(message: str) -> MCPError:
    return MCPError(-32000, message)


def _strict_json(body: bytes) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate_json_key")
            result[key] = value
        return result

    def invalid(_value: str) -> None:
        raise ValueError("nonfinite_json_number")

    return json.loads(body, object_pairs_hook=pairs, parse_constant=invalid)


class HostedPublicClient:
    """One fixed origin, no credentials, redirects, retries or environment proxy."""

    def __init__(self, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.client = httpx.AsyncClient(
            transport=transport,
            follow_redirects=False,
            trust_env=False,
            timeout=httpx.Timeout(TIMEOUT_SECONDS),
            limits=httpx.Limits(max_connections=4, max_keepalive_connections=2),
        )
        self._slots = asyncio.Semaphore(4)

    async def aclose(self) -> None:
        await self.client.aclose()

    async def rpc(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        # Only constructed arguments cross the boundary; caller metadata, headers,
        # tasks and credentials never pass through to the remote service.
        params = dict(params)
        params["_meta"] = {
            "io.modelcontextprotocol/protocolVersion": PROTOCOL,
            "io.modelcontextprotocol/clientInfo": {
                "name": "undertow-public-stdio-adapter",
                "version": VERSION,
            },
            "io.modelcontextprotocol/clientCapabilities": {},
        }
        try:
            body = json.dumps(
                {"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
                separators=(",", ":"),
                allow_nan=False,
            ).encode()
        except (TypeError, ValueError, RecursionError) as exc:
            raise MCPError(-32602, "invalid_request_arguments") from exc
        if len(body) > MAX_REQUEST_BYTES:
            raise MCPError(-32602, "request_body_too_large")
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Accept-Encoding": "identity",
            "MCP-Protocol-Version": PROTOCOL,
            "Mcp-Method": method,
            "User-Agent": "undertow-public-stdio-adapter/" + VERSION,
        }
        if "name" in params:
            headers["Mcp-Name"] = params["name"]
        try:
            async with asyncio.timeout(TIMEOUT_SECONDS), self._slots:
                async with self.client.stream(
                    "POST",
                    ENDPOINT,
                    content=body,
                    headers=headers,
                ) as response:
                    if response.status_code != 200:
                        raise _error("upstream_http_" + str(response.status_code))
                    if (
                        response.headers.get("content-type", "")
                        .split(";")[0]
                        .strip()
                        .lower()
                        != "application/json"
                    ):
                        raise _error("upstream_content_type_invalid")
                    if (
                        response.headers.get("content-encoding", "identity")
                        .strip()
                        .lower()
                        != "identity"
                    ):
                        raise _error("upstream_content_encoding_invalid")
                    raw = bytearray()
                    async for chunk in response.aiter_bytes(chunk_size=65536):
                        if len(raw) + len(chunk) > MAX_RESPONSE_BYTES:
                            raise _error("upstream_body_too_large")
                        raw.extend(chunk)
            envelope = _strict_json(bytes(raw))
        except (httpx.HTTPError, TimeoutError) as exc:
            raise _error("upstream_unavailable") from exc
        except (ValueError, UnicodeError, RecursionError) as exc:
            raise _error("upstream_json_invalid") from exc
        if (
            not isinstance(envelope, dict)
            or envelope.get("jsonrpc") != "2.0"
            or type(envelope.get("id")) is not int
            or envelope["id"] != 1
            or ("error" in envelope) == ("result" in envelope)
        ):
            raise _error("upstream_envelope_invalid")
        if "error" in envelope:
            # Preserve the native RPC failure, without turning it into evidence.
            try:
                error = types.ErrorData.model_validate(envelope["error"])
            except ValueError as exc:
                raise _error("upstream_error_invalid") from exc
            raise MCPError(error.code, error.message, error.data)
        result = envelope["result"]
        if not isinstance(result, dict):
            raise _error("upstream_result_invalid")
        meta = result.get("_meta", {})
        info = (
            meta.get("io.modelcontextprotocol/serverInfo")
            if isinstance(meta, dict)
            else None
        )
        if not isinstance(info, dict) or any(
            info.get(key) != expected
            for key, expected in {
                "name": "undertow",
                "version": CONTRACT["serverVersion"],
            }.items()
        ):
            raise _error("upstream_identity_or_version_changed")
        return result

    async def list_tools(self, _ctx: Any, params: Any) -> types.ListToolsResult:
        if params is not None and params.cursor is not None:
            raise MCPError(-32602, "pagination_not_supported")
        result = await self.rpc("tools/list", {})
        rows = result.get("tools")
        if (
            not isinstance(rows, list)
            or [row.get("name") if isinstance(row, dict) else None for row in rows]
            != CONTRACT["publicTools"]
            or result.get("nextCursor") is not None
        ):
            raise _error("upstream_public_inventory_changed")
        for row in rows:
            hints = row.get("annotations", {})
            if (
                not isinstance(hints, dict)
                or any(
                    hints.get(key) is not expected
                    for key, expected in {
                        "readOnlyHint": True,
                        "idempotentHint": True,
                        "openWorldHint": False,
                    }.items()
                )
                or hints.get("destructiveHint", False) is not False
            ):
                raise _error("upstream_read_only_contract_changed")
        return types.ListToolsResult.model_validate(result)

    async def call_tool(
        self, _ctx: Any, params: types.CallToolRequestParams
    ) -> types.CallToolResult:
        if params.name not in CONTRACT["publicTools"]:
            raise MCPError(-32602, "unknown_public_tool")
        if (
            params.task is not None
            or params.input_responses is not None
            or params.request_state is not None
        ):
            raise MCPError(-32602, "interactive_or_task_execution_not_supported")
        result = await self.rpc(
            "tools/call", {"name": params.name, "arguments": params.arguments or {}}
        )
        return types.CallToolResult.model_validate(result)

    async def list_prompts(self, _ctx: Any, params: Any) -> types.ListPromptsResult:
        if params is not None and params.cursor is not None:
            raise MCPError(-32602, "pagination_not_supported")
        result = await self.rpc("prompts/list", {})
        rows = result.get("prompts")
        if (
            not isinstance(rows, list)
            or [row.get("name") if isinstance(row, dict) else None for row in rows]
            != CONTRACT["prompts"]
            or result.get("nextCursor") is not None
        ):
            raise _error("upstream_prompt_inventory_changed")
        return types.ListPromptsResult.model_validate(result)

    async def get_prompt(
        self, _ctx: Any, params: types.GetPromptRequestParams
    ) -> types.GetPromptResult:
        if params.name not in CONTRACT["prompts"]:
            raise MCPError(-32602, "unknown_public_prompt")
        result = await self.rpc(
            "prompts/get", {"name": params.name, "arguments": params.arguments or {}}
        )
        return types.GetPromptResult.model_validate(result)


def create_server(client: HostedPublicClient) -> Server:
    return Server(
        "undertow-public-stdio-adapter",
        version=VERSION,
        instructions=INSTRUCTIONS,
        website_url="https://liquilens-undertow.com",
        on_list_tools=client.list_tools,
        on_call_tool=client.call_tool,
        on_list_prompts=client.list_prompts,
        on_get_prompt=client.get_prompt,
    )


async def run() -> None:
    client = HostedPublicClient()
    try:
        server = create_server(client)
        async with stdio_server() as (reader, writer):
            await server.run(reader, writer, server.create_initialization_options())
    finally:
        await client.aclose()


def main() -> None:
    asyncio.run(run())
