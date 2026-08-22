#!/usr/bin/env python3
"""Scheduled anonymous, read-only end-to-end smoke for Undertow MCP."""

from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
MAX_RESPONSE_BYTES = 2_000_000
TIMEOUT_SECONDS = 20
USER_AGENT = "undertow-mcp-scheduled-smoke/1.0"


def _strict_loads(value: bytes | str) -> Any:
    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in pairs:
            if key in result:
                raise RuntimeError(f"duplicate JSON key in live response: {key}")
            result[key] = item
        return result

    def reject_constant(token: str) -> None:
        raise RuntimeError(f"nonfinite JSON value in live response: {token}")

    return json.loads(
        value,
        object_pairs_hook=unique_object,
        parse_constant=reject_constant,
    )


def _strict_file(path: Path) -> dict[str, Any]:
    value = _strict_loads(path.read_bytes())
    if not isinstance(value, dict):
        raise RuntimeError(f"{path.name} must contain a JSON object")
    return value


def _decode_envelope(
    body: bytes, content_type: str, request_id: int
) -> dict[str, Any]:
    media_type = content_type.partition(";")[0].strip().lower()
    candidates: list[Any]
    if media_type == "application/json":
        candidates = [_strict_loads(body)]
    elif media_type == "text/event-stream":
        candidates = []
        data_lines: list[bytes] = []
        for line in body.splitlines() + [b""]:
            if line.startswith(b"data:"):
                data_lines.append(line[5:].lstrip())
            elif not line and data_lines:
                candidates.append(_strict_loads(b"\n".join(data_lines)))
                data_lines = []
    else:
        raise RuntimeError(f"unexpected MCP response type {content_type!r}")
    for value in candidates:
        if isinstance(value, dict) and value.get("id") == request_id:
            return value
    raise RuntimeError("MCP response did not contain the requested JSON-RPC id")


def _headers(protocol: str, method: str, name: str | None = None) -> dict[str, str]:
    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
        "MCP-Protocol-Version": protocol,
        "Mcp-Method": method,
        "User-Agent": USER_AGENT,
    }
    if name is not None:
        headers["Mcp-Name"] = name
    return headers


def _rpc(
    endpoint: str,
    method: str,
    params: dict[str, Any],
    request_id: int,
    *,
    protocol: str,
    name: str | None = None,
) -> dict[str, Any]:
    payload = json.dumps(
        {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params},
        separators=(",", ":"),
    ).encode()
    request = urllib.request.Request(
        endpoint, data=payload, headers=_headers(protocol, method, name)
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        body = response.read(MAX_RESPONSE_BYTES + 1)
        status = response.status
        content_type = response.headers.get("Content-Type", "")
    if status != 200:
        raise RuntimeError(f"{method} returned HTTP {status}")
    if len(body) > MAX_RESPONSE_BYTES:
        raise RuntimeError(f"{method} exceeded the smoke response budget")
    value = _decode_envelope(body, content_type, request_id)
    if value.get("jsonrpc") != "2.0":
        raise RuntimeError(f"{method} returned an invalid JSON-RPC envelope")
    if "error" in value:
        raise RuntimeError(f"{method} returned JSON-RPC error {value['error']!r}")
    result = value.get("result")
    if not isinstance(result, dict):
        raise RuntimeError(f"{method} returned no result object")
    return result


def _notify(
    endpoint: str, method: str, params: dict[str, Any], *, protocol: str
) -> None:
    payload = json.dumps(
        {"jsonrpc": "2.0", "method": method, "params": params},
        separators=(",", ":"),
    ).encode()
    request = urllib.request.Request(
        endpoint, data=payload, headers=_headers(protocol, method)
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        body = response.read(MAX_RESPONSE_BYTES + 1)
        status = response.status
    if status not in (202, 204) or body:
        raise RuntimeError(f"{method} notification returned an invalid response")


def modern_meta(protocol: str) -> dict[str, Any]:
    return {
        "io.modelcontextprotocol/protocolVersion": protocol,
        "io.modelcontextprotocol/clientInfo": {
            "name": "undertow-listing-smoke",
            "version": "1.0.0",
        },
        "io.modelcontextprotocol/clientCapabilities": {},
    }


def _assert_modern_version(result: dict[str, Any], version: str, label: str) -> None:
    meta = result.get("_meta")
    server_info = (
        meta.get("io.modelcontextprotocol/serverInfo")
        if isinstance(meta, dict)
        else None
    )
    if not isinstance(server_info, dict) or server_info.get("version") != version:
        raise RuntimeError(f"{label} did not attest the listed server version")


def smoke(endpoint: str | None = None) -> None:
    contract = _strict_file(ROOT / "contract.json")
    manifest = _strict_file(ROOT / "server.json")
    listed_endpoint = manifest["remotes"][0]["url"]
    endpoint = endpoint or listed_endpoint
    parsed = urlparse(endpoint)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username is not None:
        raise RuntimeError("live smoke endpoint must be an HTTPS URL without userinfo")

    legacy = "2025-11-25"
    if legacy not in contract["protocolVersions"]:
        raise RuntimeError("listing dropped the initialize protocol used by the smoke")
    initialized = _rpc(
        endpoint,
        "initialize",
        {
            "protocolVersion": legacy,
            "capabilities": {},
            "clientInfo": {"name": "undertow-listing-smoke", "version": "1.0.0"},
        },
        1,
        protocol=legacy,
    )
    expected_info = {
        "name": "undertow",
        "version": contract["serverVersion"],
    }
    server_info = initialized.get("serverInfo")
    if initialized.get("protocolVersion") != legacy or not isinstance(server_info, dict):
        raise RuntimeError("live initialize contract differs from the listing")
    if any(server_info.get(key) != value for key, value in expected_info.items()):
        raise RuntimeError("live server identity differs from the listing")
    _notify(endpoint, "notifications/initialized", {}, protocol=legacy)

    modern = contract["protocolVersions"][0]
    meta = modern_meta(modern)
    discovered = _rpc(
        endpoint, "server/discover", {"_meta": meta}, 2, protocol=modern
    )
    discovery_contract = {
        "supportedVersions": contract["protocolVersions"],
        "publicTools": contract["publicTools"],
        "subscriberTools": contract["subscriberTools"],
    }
    for field, expected in discovery_contract.items():
        if discovered.get(field) != expected:
            raise RuntimeError(f"live discovery {field} differs from the listing")
    _assert_modern_version(discovered, contract["serverVersion"], "server/discover")

    tools = _rpc(endpoint, "tools/list", {"_meta": meta}, 3, protocol=modern)
    tool_rows = tools.get("tools")
    if not isinstance(tool_rows, list) or not all(
        isinstance(item, dict) for item in tool_rows
    ):
        raise RuntimeError("live tools/list returned a malformed catalog")
    tool_names = [item.get("name") for item in tool_rows]
    if tool_names != contract["publicTools"]:
        raise RuntimeError("anonymous live tool inventory differs from the listing")
    if set(tool_names) & set(contract["subscriberTools"]):
        raise RuntimeError("subscriber tool leaked into anonymous tools/list")
    annotation_contract = {
        "readOnlyHint": True,
        "idempotentHint": True,
        "openWorldHint": False,
    }
    for item in tool_rows:
        schema = item.get("inputSchema")
        annotations = item.get("annotations")
        if not isinstance(schema, dict) or schema.get("type") != "object":
            raise RuntimeError(f"{item.get('name')} has no object input schema")
        if not isinstance(annotations, dict) or any(
            annotations.get(key) is not value
            for key, value in annotation_contract.items()
        ):
            raise RuntimeError(f"{item.get('name')} lost read-only annotations")
    _assert_modern_version(tools, contract["serverVersion"], "tools/list")

    prompts = _rpc(endpoint, "prompts/list", {"_meta": meta}, 4, protocol=modern)
    prompt_rows = prompts.get("prompts")
    if not isinstance(prompt_rows, list) or [
        item.get("name") if isinstance(item, dict) else None for item in prompt_rows
    ] != contract["prompts"]:
        raise RuntimeError("live prompt inventory differs from the listing")

    resources = _rpc(
        endpoint, "resources/list", {"_meta": meta}, 5, protocol=modern
    )
    if resources.get("resources") != []:
        raise RuntimeError("live resource inventory is not explicitly empty")
    templates = _rpc(
        endpoint,
        "resources/templates/list",
        {"_meta": meta},
        6,
        protocol=modern,
    )
    if templates.get("resourceTemplates") != contract["resourceTemplates"]:
        raise RuntimeError("live resource-template inventory differs from the listing")

    access = _rpc(
        endpoint,
        "tools/call",
        {"name": "agent_access_status", "arguments": {}, "_meta": meta},
        7,
        protocol=modern,
        name="agent_access_status",
    )
    structured = access.get("structuredContent")
    if access.get("isError") is not False or not isinstance(structured, dict):
        raise RuntimeError("agent_access_status did not return structured content")
    if structured.get("authenticated") is not False or structured.get("tier") != "anon":
        raise RuntimeError("anonymous representative call returned an authenticated tier")
    if structured.get("subscriber_tools") != contract["subscriberTools"]:
        raise RuntimeError("representative call subscriber inventory drifted")

    print(
        f"live MCP valid: {len(tool_names)} anonymous + "
        f"{len(contract['subscriberTools'])} subscriber tools, "
        f"{len(contract['prompts'])} prompts, version {contract['serverVersion']}"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--endpoint")
    args = parser.parse_args()
    smoke(args.endpoint)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
