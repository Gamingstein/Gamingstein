#!/usr/bin/env python3
"""Validate the GitHub profile README and its generated local assets.

The default checks are offline and safe for CI. Pass --check-links when an
online URL check is desired locally or from a workflow with network access.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from xml.etree import ElementTree


ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
REQUIRED_ANCHORS = ("about", "stack", "projects", "stats")
REQUIRED_ASSETS = (
    "assets/banner.webp",
    "assets/hero.svg",
    "assets/hd-about.svg",
    "assets/hd-stack.svg",
    "assets/hd-projects.svg",
    "assets/hd-stats.svg",
    "assets/stats.svg",
    "assets/langs.svg",
    "assets/streak.svg",
)
GENERATED_SVGS = ("assets/stats.svg", "assets/langs.svg", "assets/streak.svg")


def fail(message: str) -> None:
    print(f"FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def local_references(readme: str) -> set[str]:
    refs: set[str] = set()
    for match in re.findall(r"(?:src|href)=\"([^\"]+)\"|\]\(([^)]+)\)", readme):
        value = next(item for item in match if item)
        if value.startswith(("#", "http://", "https://", "mailto:")):
            continue
        refs.add(value.split("#", 1)[0])
    return refs


def external_urls(readme: str) -> set[str]:
    candidates = set(re.findall(r"https?://[^\s\"')>]+", readme))
    return {url.rstrip(".,") for url in candidates}


def check_external_url(url: str) -> None:
    request = Request(url, headers={"User-Agent": "Gamingstein-profile-validator"})
    try:
        with urlopen(request, timeout=12) as response:
            if response.status >= 400:
                fail(f"external URL returned {response.status}: {url}")
    except HTTPError as error:
        fail(f"external URL returned {error.code}: {url}")
    except URLError as error:
        fail(f"could not reach external URL {url}: {error.reason}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-links", action="store_true")
    args = parser.parse_args()

    if not README.is_file():
        fail("README.md is missing")
    readme = README.read_text(encoding="utf-8")

    for anchor in REQUIRED_ANCHORS:
        if f'id="{anchor}"' not in readme or f"#{anchor}" not in readme:
            fail(f"missing navigation anchor: {anchor}")

    if readme.count("<details>") != 5:
        fail("expected five collapsible flagship project sections")

    for image_tag in re.findall(r"<img\b[^>]*>", readme, flags=re.IGNORECASE):
        if not re.search(r"\balt=\"[^\"]+\"", image_tag, flags=re.IGNORECASE):
            fail("README image is missing alt text")

    refs = local_references(readme)
    for required in REQUIRED_ASSETS:
        refs.add(required)

    for reference in sorted(refs):
        path = ROOT / reference
        if not path.is_file():
            fail(f"missing local README reference: {reference}")

    for svg in sorted(ROOT.glob("assets/*.svg")):
        try:
            ElementTree.parse(svg)
        except ElementTree.ParseError as error:
            fail(f"malformed SVG {svg.relative_to(ROOT)}: {error}")

    for relative in GENERATED_SVGS:
        svg_text = (ROOT / relative).read_text(encoding="utf-8")
        if "<title" not in svg_text or "<desc" not in svg_text:
            fail(f"generated SVG lacks accessibility metadata: {relative}")

    for url in sorted(external_urls(readme)):
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            fail(f"malformed external URL: {url}")
        if args.check_links:
            check_external_url(url)

    checked = len(refs)
    print(f"profile validation passed: {checked} local references, {len(external_urls(readme))} external URLs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
