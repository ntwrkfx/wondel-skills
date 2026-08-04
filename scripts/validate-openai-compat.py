#!/usr/bin/env python3
"""Validate ChatGPT/Codex skill and plugin compatibility using stdlib only."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MARKETPLACE = ROOT / ".claude-plugin" / "marketplace.json"
OPENAI_METADATA = ROOT / "config" / "openai-plugin-metadata.json"
GENERATED_MARKETPLACE = ROOT / ".agents" / "plugins" / "marketplace.json"
PLUGINS = ROOT / "plugins"
EXPECTED_REPOSITORY = "https://github.com/ntwrkfx/wondel-skills"
EXPECTED_HOMEPAGE = "https://skills.wondel.ai"

METASKILLS = {
    "create-business",
    "create-website",
    "create-app",
    "improve-business",
    "improve-website",
    "improve-app",
    "grow-business",
    "grow-website",
    "grow-app",
    "improve-code-quality",
    "remove-technical-debt",
    "design-code-architecture",
}


class ValidationError(RuntimeError):
    pass


def fail(message: str) -> None:
    raise ValidationError(message)


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        fail(f"missing required file: {path.relative_to(ROOT)}")
    except json.JSONDecodeError as exc:
        fail(f"invalid JSON in {path.relative_to(ROOT)}: {exc}")
    if not isinstance(value, dict):
        fail(f"expected a JSON object in {path.relative_to(ROOT)}")
    return value


def frontmatter_value(text: str, key: str) -> str:
    if not text.startswith("---\n"):
        return ""
    end = text.find("\n---\n", 4)
    if end < 0:
        return ""
    match = re.search(rf"^{re.escape(key)}:\s*(.+)$", text[4:end], re.MULTILINE)
    return match.group(1).strip().strip("'\"") if match else ""


def listed_skills(source: dict) -> set[str]:
    """Return unique source skills while allowing reuse across collections."""
    result: set[str] = set()
    for plugin in source.get("plugins", []):
        seen_in_plugin: set[str] = set()
        for raw_path in plugin.get("skills", []):
            slug = raw_path.removeprefix("./")
            if slug in seen_in_plugin:
                fail(f"skill is duplicated inside plugin {plugin.get('name')}: {slug}")
            seen_in_plugin.add(slug)
            result.add(slug)
    return result


def validate_source_skills(source: dict) -> set[str]:
    listed = listed_skills(source)
    discovered = {
        path.name
        for path in ROOT.iterdir()
        if path.is_dir() and (path / "SKILL.md").is_file()
    }

    if discovered != listed:
        missing = sorted(listed - discovered)
        unlisted = sorted(discovered - listed)
        fail(f"marketplace/source mismatch; missing={missing}, unlisted={unlisted}")

    frontmatter_names: dict[str, str] = {}
    for slug in sorted(discovered):
        skill_file = ROOT / slug / "SKILL.md"
        text = skill_file.read_text(encoding="utf-8")
        name = frontmatter_value(text, "name")
        description = frontmatter_value(text, "description")
        if not name:
            fail(f"{slug}/SKILL.md lacks frontmatter name")
        if not description:
            fail(f"{slug}/SKILL.md lacks frontmatter description")
        if not 1 <= len(description) <= 1024:
            fail(
                f"{slug}/SKILL.md frontmatter description must be 1-1024 characters; "
                f"got {len(description)}"
            )
        if name in frontmatter_names:
            fail(f"duplicate skill name {name!r}: {frontmatter_names[name]} and {slug}")
        frontmatter_names[name] = slug

    if not METASKILLS.issubset(discovered):
        fail(f"missing guided journeys: {sorted(METASKILLS - discovered)}")

    return discovered


def validate_metaskill_metadata() -> None:
    required_fragments = (
        'display_name: "',
        'short_description: "',
        "- CHAT",
        "- CODEX",
        "allow_implicit_invocation: false",
        "If no writable workspace is available, use chat mode",
        "never claim files were written",
    )
    for slug in sorted(METASKILLS):
        path = ROOT / slug / "agents" / "openai.yaml"
        if not path.is_file():
            fail(f"missing OpenAI metadata: {path.relative_to(ROOT)}")
        text = path.read_text(encoding="utf-8")
        for fragment in required_fragments:
            if fragment not in text:
                fail(f"{path.relative_to(ROOT)} lacks required fragment: {fragment}")


def validate_listing_metadata(source: dict, listing_metadata: dict) -> None:
    source_names = {plugin["name"] for plugin in source.get("plugins", [])}
    metadata_names = set(listing_metadata)
    if source_names != metadata_names:
        missing = sorted(source_names - metadata_names)
        unknown = sorted(metadata_names - source_names)
        fail(f"OpenAI listing metadata mismatch; missing={missing}, unknown={unknown}")

    required = (
        "displayName",
        "shortDescription",
        "longDescription",
        "category",
        "defaultPrompt",
    )
    for name, metadata in listing_metadata.items():
        if not isinstance(metadata, dict):
            fail(f"OpenAI listing metadata for {name} must be an object")
        for field in required:
            if not metadata.get(field):
                fail(f"OpenAI listing metadata for {name} lacks {field}")


def validate_generated_plugins(source: dict, listing_metadata: dict) -> None:
    generated = read_json(GENERATED_MARKETPLACE)
    source_names = [plugin["name"] for plugin in source["plugins"]]
    generated_names = [plugin["name"] for plugin in generated.get("plugins", [])]
    if generated_names != source_names:
        fail("generated marketplace plugin order or membership is stale")

    for source_plugin in source["plugins"]:
        name = source_plugin["name"]
        manifest_path = PLUGINS / name / ".codex-plugin" / "plugin.json"
        manifest = read_json(manifest_path)
        required = (
            "name",
            "version",
            "description",
            "skills",
            "repository",
            "homepage",
            "interface",
        )
        for field in required:
            if not manifest.get(field):
                fail(f"{manifest_path.relative_to(ROOT)} lacks {field}")
        if manifest["name"] != name:
            fail(f"manifest name mismatch for {name}")
        if manifest["repository"] != EXPECTED_REPOSITORY:
            fail(f"stale repository URL in {manifest_path.relative_to(ROOT)}")
        if manifest["homepage"] != EXPECTED_HOMEPAGE:
            fail(f"stale homepage URL in {manifest_path.relative_to(ROOT)}")

        interface = manifest["interface"]
        expected = listing_metadata[name]
        comparisons = {
            "displayName": expected["displayName"],
            "shortDescription": expected["shortDescription"],
            "longDescription": expected["longDescription"],
            "category": expected["category"],
            "defaultPrompt": [expected["defaultPrompt"]],
        }
        for field, expected_value in comparisons.items():
            if interface.get(field) != expected_value:
                fail(
                    f"{manifest_path.relative_to(ROOT)} has stale interface.{field}; "
                    f"expected {expected_value!r}"
                )
        if interface.get("developerName") != "Wondel.ai":
            fail(f"{manifest_path.relative_to(ROOT)} lacks the Wondel.ai developer identity")

        expected_skills = [path.removeprefix("./") for path in source_plugin["skills"]]
        skills_dir = PLUGINS / name / "skills"
        actual_skills = sorted(path.name for path in skills_dir.iterdir())
        if actual_skills != sorted(expected_skills):
            fail(f"generated skill membership is stale for plugin {name}")
        for slug in expected_skills:
            link = skills_dir / slug
            if not link.exists():
                fail(f"broken generated skill link: {link.relative_to(ROOT)}")


def main() -> int:
    try:
        source = read_json(MARKETPLACE)
        listing_metadata = read_json(OPENAI_METADATA)
        skills = validate_source_skills(source)
        validate_metaskill_metadata()
        validate_listing_metadata(source, listing_metadata)
        validate_generated_plugins(source, listing_metadata)
    except ValidationError as exc:
        print(f"OpenAI compatibility validation failed: {exc}", file=sys.stderr)
        return 1

    print(
        "OpenAI compatibility validation passed: "
        f"{len(skills)} skills, {len(METASKILLS)} guided journeys, "
        f"{len(source['plugins'])} plugins"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
