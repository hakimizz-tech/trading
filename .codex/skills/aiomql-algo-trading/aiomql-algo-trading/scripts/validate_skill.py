#!/usr/bin/env python3
"""Validate a portable Agent Skill folder."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
XML_TAG_RE = re.compile(r"<[^>]+>")


def parse_frontmatter(text: str) -> dict[str, str]:
    match = FRONTMATTER_RE.match(text)
    if not match:
        raise ValueError("SKILL.md must start with YAML frontmatter delimited by ---")

    data: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if not line.strip() or line.startswith("  ") or line.startswith("-"):
            continue
        if ":" in line:
            key, value = line.split(":", 1)
            data[key.strip()] = value.strip()
    return data


def validate(skill_dir: Path) -> int:
    errors: list[str] = []
    warnings: list[str] = []

    if not NAME_RE.match(skill_dir.name):
        errors.append("Skill folder must be kebab-case with no spaces, underscores, or capitals")

    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        errors.append("Missing SKILL.md")
        text = ""
    else:
        text = skill_md.read_text(encoding="utf-8")

    if (skill_dir / "README.md").exists():
        errors.append("Do not include README.md inside the skill folder")

    if text:
        try:
            fm = parse_frontmatter(text)
        except ValueError as exc:
            errors.append(str(exc))
            fm = {}

        name = fm.get("name", "")
        description = fm.get("description", "")
        if not name:
            errors.append("Missing frontmatter name")
        elif not NAME_RE.match(name):
            errors.append("Frontmatter name must be kebab-case")
        elif name != skill_dir.name:
            warnings.append("Frontmatter name should match folder name")

        if not description:
            errors.append("Missing frontmatter description")
        else:
            if len(description) > 1024:
                errors.append("Description must be under 1024 characters")
            lowered = description.lower()
            if "use when" not in lowered:
                errors.append("Description should include trigger conditions using 'Use when'")
            if XML_TAG_RE.search(description):
                errors.append("Description must not include XML tags")

        if XML_TAG_RE.search(text):
            warnings.append("SKILL.md contains XML-like tags; remove them if upload fails")

    for ref in ["references/aiomql-api-map.md", "references/strategy-patterns.md", "references/risk-and-live-trading-safety.md", "references/testing-and-debugging.md"]:
        if not (skill_dir / ref).exists():
            warnings.append(f"Missing suggested reference: {ref}")

    for message in warnings:
        print(f"WARN: {message}")
    for message in errors:
        print(f"ERROR: {message}")

    if errors:
        return 1
    print("Skill validation passed")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a portable Agent Skill folder")
    parser.add_argument("skill_dir", nargs="?", default=".")
    args = parser.parse_args()
    return validate(Path(args.skill_dir).resolve())


if __name__ == "__main__":
    raise SystemExit(main())
