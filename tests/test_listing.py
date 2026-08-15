from __future__ import annotations

import json
import re
import unittest
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]


def _strict_json(path: Path) -> dict[str, Any]:
    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise ValueError(f"duplicate JSON key in {path.name}: {key}")
            value[key] = item
        return value

    def reject_constant(value: str) -> None:
        raise ValueError(f"nonfinite JSON value in {path.name}: {value}")

    parsed = json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=unique_object,
        parse_constant=reject_constant,
    )
    if not isinstance(parsed, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return parsed


def _section(markdown: str, heading: str, next_heading: str) -> str:
    start = markdown.index(heading)
    end = markdown.index(next_heading, start)
    return markdown[start:end]


class ListingContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = _strict_json(ROOT / "contract.json")
        cls.server = _strict_json(ROOT / "server.json")
        cls.glama = _strict_json(ROOT / "glama.json")
        cls.readme = (ROOT / "README.md").read_text(encoding="utf-8")

    def test_contract_shape_and_inventories_are_deterministic(self) -> None:
        self.assertEqual(
            set(self.contract),
            {
                "canonical",
                "serverVersion",
                "protocolVersions",
                "publicTools",
                "subscriberTools",
                "prompts",
                "resourceTemplates",
            },
        )
        self.assertRegex(
            self.contract["canonical"]["releaseCommit"], r"^[0-9a-f]{40}$"
        )
        for field in ("publicTools", "subscriberTools", "prompts"):
            names = self.contract[field]
            self.assertEqual(names, sorted(set(names)))
            self.assertTrue(
                all(re.fullmatch(r"[a-z][a-z0-9_]+", name) for name in names)
            )
        self.assertEqual(len(self.contract["publicTools"]), 9)
        self.assertEqual(len(self.contract["subscriberTools"]), 8)
        self.assertEqual(len(self.contract["prompts"]), 3)
        self.assertEqual(self.contract["resourceTemplates"], [])

    def test_server_manifest_matches_the_contract(self) -> None:
        self.assertEqual(self.server["version"], self.contract["serverVersion"])
        self.assertEqual(self.server["name"], "io.github.beepboop2025/undertow")
        self.assertEqual(
            self.server["repository"]["url"],
            self.contract["canonical"]["listingRepository"],
        )
        self.assertEqual(self.server["repository"]["source"], "github")
        self.assertLessEqual(len(self.server["description"]), 100)
        self.assertEqual(
            self.server["$schema"],
            "https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json",
        )
        self.assertEqual(
            self.server["remotes"],
            [{
                "type": "streamable-http",
                "url": "https://api.seiche.info/undertow/mcp",
            }],
        )
        parsed = urlparse(self.server["websiteUrl"])
        self.assertEqual(parsed.scheme, "https")
        self.assertTrue(parsed.netloc)

    def test_readme_advertises_every_capability_once(self) -> None:
        tool_section = _section(self.readme, "## Tools", "## Prompts")
        prompt_section = _section(self.readme, "## Prompts", "## Limitations")
        tool_pattern = re.compile(
            r"^\| `([a-z][a-z0-9_]+)` \|.*\| (free|subscriber) \|$",
            re.MULTILINE,
        )
        rows = tool_pattern.findall(tool_section)
        self.assertEqual(
            {name for name, surface in rows if surface == "free"},
            set(self.contract["publicTools"]),
        )
        self.assertEqual(
            {name for name, surface in rows if surface == "subscriber"},
            set(self.contract["subscriberTools"]),
        )
        self.assertEqual(len(rows), 17)
        prompt_pattern = re.compile(
            r"^\| `([a-z][a-z0-9_]+)` \|", re.MULTILINE
        )
        self.assertEqual(
            prompt_pattern.findall(prompt_section), self.contract["prompts"]
        )

    def test_readme_documents_versions_and_boundaries(self) -> None:
        self.assertIn(f"MCP {self.contract['serverVersion']}", self.readme)
        for version in self.contract["protocolVersions"]:
            self.assertIn(version, self.readme)
        self.assertIn("17 read-only tools", self.readme)
        self.assertIn("9 public and 8 subscriber", self.readme)
        self.assertIn("3 guided prompts", self.readme)
        self.assertIn("PARTIAL is not calm", self.readme)
        self.assertIn("No commodity futures", self.server["description"])
        self.assertNotIn("MCP 1.7.1", self.readme)

    def test_secondary_registry_metadata_is_minimal(self) -> None:
        self.assertEqual(
            self.glama,
            {
                "$schema": "https://glama.ai/mcp/schemas/server.json",
                "maintainers": ["beepboop2025"],
            },
        )


if __name__ == "__main__":
    unittest.main()
