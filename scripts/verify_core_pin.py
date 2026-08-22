#!/usr/bin/env python3
"""Fail closed unless this listing matches the exact pinned Undertow source."""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
HOSTED_SERVER = Path("deploy/hetzner/undertow-mcp/undertow_mcp.py")
PIN_PATTERN = re.compile(r"[0-9a-f]{40}")


def _strict_json(path: Path) -> dict[str, Any]:
    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise ValueError(f"duplicate JSON key in {path}: {key}")
            value[key] = item
        return value

    def reject_constant(value: str) -> None:
        raise ValueError(f"nonfinite JSON value in {path}: {value}")

    parsed = json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=unique_object,
        parse_constant=reject_constant,
    )
    if not isinstance(parsed, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return parsed


def contract_pin() -> str:
    contract = _strict_json(ROOT / "contract.json")
    canonical = contract.get("canonical")
    if not isinstance(canonical, dict):
        raise ValueError("contract canonical field must be an object")
    pin = canonical.get("releaseCommit")
    if not isinstance(pin, str) or PIN_PATTERN.fullmatch(pin) is None:
        raise ValueError("contract releaseCommit must be an exact lowercase SHA-1")
    return pin


def _module(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _assignment(tree: ast.Module, name: str) -> ast.expr:
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == name and node.value is not None:
                return node.value
        if isinstance(node, ast.Assign):
            if any(
                isinstance(target, ast.Name) and target.id == name
                for target in node.targets
            ):
                return node.value
    raise ValueError(f"assignment {name} not found in hosted MCP source")


def _literal(tree: ast.Module, name: str) -> Any:
    return ast.literal_eval(_assignment(tree, name))


def _sequence(
    tree: ast.Module, name: str, resolved: dict[str, Any]
) -> list[Any]:
    node = _assignment(tree, name)
    if not isinstance(node, (ast.Tuple, ast.List)):
        raise ValueError(f"{name} must be a literal sequence")
    values: list[Any] = []
    for item in node.elts:
        if isinstance(item, ast.Starred) and isinstance(item.value, ast.Name):
            expansion = resolved.get(item.value.id)
            if not isinstance(expansion, list):
                raise ValueError(f"cannot resolve expansion in {name}")
            values.extend(expansion)
        elif isinstance(item, ast.Name) and item.id in resolved:
            values.append(resolved[item.id])
        else:
            values.append(ast.literal_eval(item))
    return values


def _mapping_keys(tree: ast.Module, name: str) -> list[str]:
    node = _assignment(tree, name)
    if not isinstance(node, ast.Dict):
        raise ValueError(f"{name} must be a dictionary literal")
    keys = [ast.literal_eval(key) for key in node.keys]
    if not all(isinstance(key, str) for key in keys):
        raise ValueError(f"{name} contains a non-string key")
    if len(keys) != len(set(keys)):
        raise ValueError(f"{name} contains a duplicate key")
    return keys


def _tool_inventories(tree: ast.Module) -> tuple[list[str], list[str]]:
    node = _assignment(tree, "TOOLS")
    if not isinstance(node, ast.Dict):
        raise ValueError("TOOLS must be a dictionary literal")
    public: list[str] = []
    subscriber: list[str] = []
    seen: set[str] = set()
    for key_node, value_node in zip(node.keys, node.values, strict=True):
        name = ast.literal_eval(key_node)
        if not isinstance(name, str):
            raise ValueError("TOOLS contains a non-string key")
        if name in seen:
            raise ValueError(f"TOOLS contains duplicate key {name}")
        seen.add(name)
        if not isinstance(value_node, (ast.Tuple, ast.List)):
            raise ValueError(f"TOOLS[{name!r}] must be a literal tuple")
        if len(value_node.elts) != 4:
            raise ValueError(f"TOOLS[{name!r}] must have four fields")
        is_public = ast.literal_eval(value_node.elts[3])
        if not isinstance(is_public, bool):
            raise ValueError(f"TOOLS[{name!r}] visibility must be boolean")
        (public if is_public else subscriber).append(name)
    return sorted(public), sorted(subscriber)


def _git_output(core: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(core), *args], text=True, stderr=subprocess.STDOUT
    ).strip()


def verify(core: Path) -> None:
    core = core.resolve()
    contract = _strict_json(ROOT / "contract.json")
    listing_server = _strict_json(ROOT / "server.json")
    expected_sha = contract_pin()
    actual_sha = _git_output(core, "rev-parse", "--verify", "HEAD^{commit}")
    if actual_sha != expected_sha:
        raise ValueError(f"core checkout is {actual_sha}, listing pins {expected_sha}")
    dirty = _git_output(core, "status", "--porcelain", "--untracked-files=all")
    if dirty:
        raise ValueError("pinned core checkout has modified tracked files")

    hosted_path = core / HOSTED_SERVER
    tree = _module(hosted_path)
    core_server = _strict_json(core / "server.json")
    public_tools, subscriber_tools = _tool_inventories(tree)
    prompts = sorted(_mapping_keys(tree, "PROMPTS"))

    modern = _literal(tree, "MODERN_PROTOCOL_VERSION")
    primary = _literal(tree, "PROTOCOL_VERSION")
    resolved: dict[str, Any] = {"PROTOCOL_VERSION": primary}
    legacy = _sequence(tree, "LEGACY_PROTOCOL_VERSIONS", resolved)
    resolved["MODERN_PROTOCOL_VERSION"] = modern
    resolved["LEGACY_PROTOCOL_VERSIONS"] = legacy
    protocols = _sequence(tree, "SUPPORTED_PROTOCOL_VERSIONS", resolved)

    comparisons = {
        "public tools": (public_tools, contract["publicTools"]),
        "subscriber tools": (subscriber_tools, contract["subscriberTools"]),
        "prompts": (prompts, contract["prompts"]),
        "protocol versions": (protocols, contract["protocolVersions"]),
        "server version": (
            _literal(tree, "SERVER_VERSION"),
            contract["serverVersion"],
        ),
        "server identity": (
            _literal(tree, "SERVER_NAME"),
            listing_server["name"].rsplit("/", 1)[-1],
        ),
        "registry manifest": (core_server, listing_server),
    }
    mismatches = [
        f"{label}: core={actual!r}, listing={expected!r}"
        for label, (actual, expected) in comparisons.items()
        if actual != expected
    ]
    if mismatches:
        raise ValueError("listing/core contract mismatch:\n" + "\n".join(mismatches))

    print(
        f"core pin valid: {expected_sha} exposes {len(public_tools)} public + "
        f"{len(subscriber_tools)} subscriber tools, {len(prompts)} prompts, "
        f"and MCP {contract['serverVersion']}"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--core", type=Path)
    group.add_argument("--print-pin", action="store_true")
    args = parser.parse_args()
    if args.print_pin:
        print(contract_pin())
    else:
        verify(args.core)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
