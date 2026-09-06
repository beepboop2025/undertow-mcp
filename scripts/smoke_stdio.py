#!/usr/bin/env python3
"""Bounded real stdio protocol check; --offline performs no upstream reads."""

import argparse
import json
import os
import selectors
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def smoke(command, *, offline):
    process = subprocess.Popen(
        command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    started = time.monotonic()
    results = {}

    def rpc(request_id, method, params):
        request = {"jsonrpc": "2.0", "method": method, "params": params}
        if request_id is not None:
            request["id"] = request_id
        process.stdin.write(json.dumps(request).encode() + b"\n")
        process.stdin.flush()
        if request_id is None:
            return None
        deadline = time.monotonic() + 20
        buffer = bytearray()
        while time.monotonic() < deadline:
            if not selector.select(max(0, deadline - time.monotonic())):
                break
            raw = os.read(process.stdout.fileno(), 65536)
            if not raw or len(buffer) + len(raw) > 3 * 1024 * 1024:
                raise RuntimeError("invalid_stdio_output")
            buffer.extend(raw)
            while b"\n" in buffer:
                line, _, rest = buffer.partition(b"\n")
                buffer = bytearray(rest)
                message = json.loads(line)
                if message.get("id") == request_id:
                    if "error" in message:
                        raise RuntimeError(str(message["error"]))
                    results[method] = message["result"]
                    return message["result"]
        raise RuntimeError("stdio_response_timeout")

    try:
        initialized = rpc(
            1,
            "initialize",
            {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {
                    "name": "undertow-adapter-validation",
                    "version": "0.1.0",
                },
            },
        )
        if initialized["serverInfo"]["name"] != "undertow-public-stdio-adapter":
            raise RuntimeError("adapter_identity_mismatch")
        rpc(None, "notifications/initialized", {})
        rpc(2, "ping", {})
        if not offline:
            contract = json.loads((ROOT / "contract.json").read_text())
            tools = rpc(3, "tools/list", {})
            if [t["name"] for t in tools["tools"]] != contract["publicTools"]:
                raise RuntimeError("public_inventory_mismatch")
            prompts = rpc(4, "prompts/list", {})
            if [p["name"] for p in prompts["prompts"]] != contract["prompts"]:
                raise RuntimeError("prompt_inventory_mismatch")
            access = rpc(
                5, "tools/call", {"name": "agent_access_status", "arguments": {}}
            )
            if (
                access.get("isError") is not False
                or access["structuredContent"].get("authenticated") is not False
            ):
                raise RuntimeError("anonymous_access_mismatch")
        print(
            json.dumps(
                {
                    "status": "PASS",
                    "offline": offline,
                    "seconds": round(time.monotonic() - started, 3),
                    "results": results,
                },
                indent=2,
            )
        )
    finally:
        selector.close()
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)
        for stream in (process.stdin, process.stdout, process.stderr):
            stream.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command or [
        sys.executable,
        "-c",
        "from undertow_mcp_adapter import main; main()",
    ]
    smoke(command, offline=args.offline)


if __name__ == "__main__":
    main()
