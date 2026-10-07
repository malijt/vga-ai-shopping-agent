"""3.1.3 (step 1, also needed by 3.1.2): fetch the licence-clean sample images listed in image_manifest.json.

Run:  uv run python 00_fetch_images.py

Source: Wikimedia Commons only (no retail sites). For every manifest entry this asks the
MediaWiki API for the file's licence metadata, REFUSES anything that is not CC0 / public
domain / CC BY / CC BY-SA, downloads a 500 px-wide thumbnail served by upload.wikimedia.org
into images/ (git-ignored, never committed), and records the source URL, licence, author
and thumbnail size in results/image_sources.json (the table in REPORT.md is generated from it).

Politeness: plain User-Agent "vga-shopping-agent-demo/0.1 (image-similarity spike)", no
personal data, one request at a time, at least 1.5 s between requests, and a Retry-After
backoff on HTTP 429. Re-running skips files already on disk.
"""

from __future__ import annotations

import html
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlencode

import httpx

import common

API = "https://commons.wikimedia.org/w/api.php"
MIN_GAP_SECONDS = 1.5
THUMB_WIDTH = 500
# LicenseShortName values we accept (permissive, no NC / ND). Checked as a prefix match.
ALLOWED_LICENCE_PREFIXES = ("CC0", "Public domain", "CC BY ", "CC BY-SA ")

_last_request = 0.0


def polite_get(client: httpx.Client, url: str, **kwargs) -> httpx.Response:
    global _last_request
    for attempt in range(5):
        wait = MIN_GAP_SECONDS - (time.monotonic() - _last_request)
        if wait > 0:
            time.sleep(wait)
        response = client.get(url, **kwargs)
        _last_request = time.monotonic()
        if response.status_code == 429:
            delay = int(response.headers.get("Retry-After", "10")) + 5 * attempt
            print(f"  429 from {httpx.URL(url).host}; waiting {delay}s", file=sys.stderr)
            time.sleep(delay)
            continue
        response.raise_for_status()
        return response
    raise RuntimeError(f"gave up on {url} after repeated 429s")


def strip_html(value: str | None) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", value or "")).strip()


def licence_ok(short_name: str | None) -> bool:
    return bool(short_name) and short_name.startswith(ALLOWED_LICENCE_PREFIXES)


def main() -> int:
    manifest = json.loads((common.SPIKE_DIR / "image_manifest.json").read_text())
    common.IMAGES_DIR.mkdir(exist_ok=True)
    sources: list[dict] = []
    rejected: list[dict] = []

    with httpx.Client(headers={"User-Agent": common.USER_AGENT}, timeout=30, follow_redirects=True) as client:
        # Resolve metadata in batches of 10 titles (one API call each).
        info_by_title: dict[str, dict] = {}
        titles = [entry["title"] for entry in manifest]
        for i in range(0, len(titles), 10):
            query = urlencode(
                {
                    "action": "query",
                    "format": "json",
                    "titles": "|".join(titles[i : i + 10]),
                    "prop": "imageinfo",
                    "iiprop": "url|size|mime|extmetadata",
                    "iiurlwidth": THUMB_WIDTH,
                    "redirects": 1,
                }
            )
            data = polite_get(client, f"{API}?{query}").json()
            # Titles can be normalised/redirected; map them back to what we asked for.
            renames = {}
            for key in ("normalized", "redirects"):
                for item in data["query"].get(key, []):
                    renames[item["from"]] = item["to"]
            for page in data["query"]["pages"].values():
                info_by_title[page["title"]] = page
            for requested in titles[i : i + 10]:
                resolved = renames.get(renames.get(requested, requested), renames.get(requested, requested))
                if resolved in info_by_title:
                    info_by_title[requested] = info_by_title[resolved]

        for index, entry in enumerate(manifest, start=1):
            page = info_by_title.get(entry["title"])
            if not page or "imageinfo" not in page:
                rejected.append({"title": entry["title"], "reason": "not found on Commons"})
                continue
            ii = page["imageinfo"][0]
            meta = ii.get("extmetadata", {})
            licence = meta.get("LicenseShortName", {}).get("value")
            if not licence_ok(licence):
                rejected.append({"title": entry["title"], "reason": f"licence not allowed: {licence}"})
                continue
            thumb_url = ii.get("thumburl") or ii["url"]
            extension = Path(httpx.URL(thumb_url).path).suffix.lower() or ".jpg"
            local = common.IMAGES_DIR / f"{index:02d}_{entry['category']}_{entry['kind']}{extension}"
            if not local.exists():
                response = polite_get(client, thumb_url)
                local.write_bytes(response.content)
            sources.append(
                {
                    "id": local.stem,
                    "file": f"images/{local.name}",
                    "category": entry["category"],
                    "kind": entry["kind"],
                    "title": page["title"],
                    "source_page": ii["descriptionurl"],
                    "thumbnail_url": thumb_url,
                    "original_size": [ii["width"], ii["height"]],
                    "licence": licence,
                    "licence_url": meta.get("LicenseUrl", {}).get("value"),
                    "author": strip_html(meta.get("Artist", {}).get("value")),
                    "credit": strip_html(meta.get("Credit", {}).get("value")),
                    "attribution_required": meta.get("AttributionRequired", {}).get("value"),
                }
            )
            print(f"ok  {local.name:45s} {licence}")

    path = common.write_json("image_sources.json", {"accessed": time.strftime("%Y-%m-%d"), "images": sources, "rejected": rejected})
    print(f"{len(sources)} images, {len(rejected)} rejected -> {path.relative_to(common.SPIKE_DIR)}")
    for item in rejected:
        print("rejected:", item)
    return 0


if __name__ == "__main__":
    sys.exit(main())
