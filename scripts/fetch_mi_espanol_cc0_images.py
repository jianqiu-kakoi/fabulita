#!/usr/bin/env python3
"""Fetch CC0 / public-domain photos for the Mi Español A0 visual vocabulary.

Pipeline (each step is idempotent and resumable):

  uv run python scripts/fetch_mi_espanol_cc0_images.py plan      # build manifest entries
  uv run python scripts/fetch_mi_espanol_cc0_images.py search    # query Openverse (rate limited)
  uv run python scripts/fetch_mi_espanol_cc0_images.py download  # fetch + resize selected images
  uv run python scripts/fetch_mi_espanol_cc0_images.py status

Only ``cc0`` and ``pdm`` (public domain mark) results are ever kept, so the
resulting assets can ship in the public site.  Provenance (source URL, landing
page, creator, license) is recorded for every candidate anyway.

Word list: the numbered entries of the local PDF manifest.  Days of the week and
months have no meaningful picture and are skipped; seasons are kept.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT = ROOT / "examples" / "mi-espanol"
PDF_MANIFEST = PROJECT_ROOT / "materials" / "vocabulario-a0-visual" / "manifest.json"
ASSET_ROOT = PROJECT_ROOT / "assets" / "vocab-images"
MANIFEST = ASSET_ROOT / "manifest.json"
IMAGE_DIR = ASSET_ROOT / "images"

OPENVERSE_API = "https://api.openverse.org/v1/images/"
USER_AGENT = "fabulita-vocab-images/1.0 (+https://github.com/jianqiu-kakoi/fabulita)"
FREE_LICENSES = {"cc0", "pdm"}
CANDIDATES_PER_WORD = 8
MAX_WIDTH = 480
JPEG_QUALITY = 72

SKIP_ENGLISH = {
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "january", "february", "march", "april", "may", "june", "july", "august",
    "september", "october", "november", "december",
}

# English gloss -> photo search query, where the bare gloss is ambiguous.
QUERY_OVERRIDES = {
    "bat": "bat animal", "seal": "seal animal", "mouse": "mouse animal",
    "fish": "fish animal", "duck": "duck bird", "crab": "crab animal",
    "llama": "llama animal", "hen": "hen chicken", "bird": "small bird",
    "track and field": "athletics running track", "climbing": "rock climbing",
    "boxing": "boxing gloves", "skating": "ice skating", "Pilates": "pilates exercise",
    "CrossFit": "crossfit gym", "fencing": "fencing sport", "cycling": "cycling bicycle race",
    "hockey": "ice hockey", "soccer": "soccer ball", "surfing": "surfing wave",
    "golf": "golf course", "yoga": "yoga pose", "handball": "handball sport",
    "spring": "spring blossom", "summer": "summer beach sun",
    "autumn": "autumn leaves", "winter": "winter snow",
    "head": "human head", "eyes": "human eyes", "nose": "human nose",
    "mouth": "human mouth lips", "ears": "human ear", "cheeks": "cheeks face",
    "chin": "chin face", "forehead": "forehead face", "back": "human back",
    "waist": "waist body", "chest": "human chest", "belly button": "navel",
    "arm": "human arm", "hand": "human hand", "finger": "index finger",
    "leg": "human leg", "foot": "human foot", "hair": "hair head",
    "neck": "neck human", "bottom": "buttocks", "tummy": "belly stomach",
    "tongue": "tongue mouth",
    "iron": "clothes iron", "fan": "electric fan", "dryer": "clothes dryer",
    "radio": "radio receiver", "oven": "kitchen oven", "kettle": "electric kettle",
    "radiator": "heating radiator", "extractor hood": "range hood kitchen",
    "landline telephone": "landline phone", "hair straightener": "hair straightener flat iron",
    "electric razor": "electric shaver", "ceramic cooktop": "electric stove top",
    "television": "television set", "TV": "television set",
    "it is cold": "cold winter freezing", "it is windy": "windy wind trees",
    "air": "fresh air sky", "the weather is bad": "bad weather rain storm",
    "it is sunny": "sunny day sun", "it is hot": "hot summer heat sun",
    "the weather is nice": "nice weather sunny park", "to snow": "snowing snowfall",
    "to rain": "raining rain umbrella", "fog": "fog foggy", "storm": "thunderstorm lightning",
    "vacation": "vacation beach suitcase", "cap": "baseball cap",
    "swim ring": "inflatable swim ring", "soda": "soda can", "hat": "sun hat",
    "ball": "beach ball", "bucket": "beach bucket sand", "shovel": "sand shovel toy",
    "rake": "rake", "diving goggles": "swimming goggles", "hand fan": "folding hand fan",
    "beach paddles": "beach tennis rackets", "wave": "ocean wave", "small boat": "rowing boat",
    "mandarin": "mandarin orange", "fig": "fig fruit", "plum": "plum fruit",
    "kiwi": "kiwi fruit", "lime": "lime fruit", "orange": "orange fruit",
    "melon": "melon fruit", "mango": "mango fruit", "grape": "grapes",
    "scooter": "kick scooter", "subway": "subway train metro",
    "painting": "framed painting wall", "plant": "houseplant", "drawer": "drawer dresser",
    "beanbag": "bean bag chair", "vase": "flower vase", "cushion": "cushion pillow",
    "rug": "carpet", "lamp": "table lamp", "table": "dining table",
    "knee": "knee", "ceramic cooktop": "electric stove top", "citrus juicer": "lemon squeezer",
    "beach paddles": "beach tennis rackets",
}


def _slug(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "-", ascii_value).strip("-") or "entry"


def query_for(entry: dict) -> str:
    english = entry["english"]
    return QUERY_OVERRIDES.get(english, english)


def plan_entries(pdf_entries: list[dict]) -> list[dict]:
    """One manifest entry per unique Spanish word, skipping days and months."""
    planned: list[dict] = []
    by_spanish: dict[str, dict] = {}
    for raw in sorted(pdf_entries, key=lambda item: item["number"]):
        if raw["english"].lower() in SKIP_ENGLISH:
            continue
        key = raw["spanish"].casefold()
        if key in by_spanish:
            by_spanish[key]["numbers"].append(raw["number"])
            continue
        entry = {
            "spanish": raw["spanish"],
            "english": raw["english"],
            "category": raw["category"],
            "numbers": [raw["number"]],
            "query": query_for(raw),
            "candidates": [],
            "selected": None,
            "image": None,
        }
        by_spanish[key] = entry
        planned.append(entry)
    return planned


def normalize_candidate(result: dict) -> dict | None:
    license_name = str(result.get("license") or "").lower()
    if license_name not in FREE_LICENSES:
        return None
    url = result.get("url") or ""
    if not url or not result.get("id"):
        return None
    return {
        "id": result["id"],
        "title": (result.get("title") or "")[:120],
        "url": url,
        "thumbnail": result.get("thumbnail") or "",
        "landing": result.get("foreign_landing_url") or "",
        "creator": (result.get("creator") or "")[:120],
        "license": license_name,
        "licenseVersion": result.get("license_version") or "",
        "licenseUrl": result.get("license_url") or "",
        "source": result.get("source") or "",
        "width": result.get("width"),
        "height": result.get("height"),
    }


# ── candidate ranking ────────────────────────────────────────────────────────

SOURCE_SCORE = {
    "stocksnap": 3, "flickr": 1, "rawpixel": 1, "wordpress": 0, "wikimedia": 0,
    "bio_diversity": -2, "svgsilh": -3, "thingiverse": -3, "europeana": -10,
}
# Words that usually mean "not a plain photo of the thing": adverts, artworks,
# scans, toys, diagrams. Each hit costs points.
TITLE_PENALTIES = (
    "advertisement", "advert", "poster", "tattoo", "mosaic", "drawing", "drawn",
    "engraving", "illustration", "sketch", "diagram", "schematic", "print ", "plate",
    "book", "page", "manuscript", "liber", "museum", "statue", "sculpture", "toy",
    "lego", "mecha", "design", "logo", "map", "text", "file:", "costume", "mask",
    "cartoon", "painting", "woodcut", "lithograph", "stamp", "coin", "medal", "fossil",
    "skeleton", "skull", "specimen", "herbarium", "x-ray", "anatomy", "circus",
)
STOPWORDS = {"a", "an", "the", "of", "is", "it", "to", "in", "and", "human", "animal", "fruit", "sport"}


def _query_tokens(query: str) -> list[str]:
    return [token for token in re.split(r"[^a-z]+", query.lower()) if len(token) > 2 and token not in STOPWORDS]


def candidate_score(candidate: dict, query: str) -> float:
    title = (candidate.get("title") or "").lower()
    score = 0.0
    tokens = _query_tokens(query)
    matched = sum(1 for token in tokens if token in title)
    score += min(matched, 2) * 3
    if tokens and not matched:
        score -= 2
    score += SOURCE_SCORE.get(candidate.get("source") or "", -3)
    if candidate.get("license") == "pdm":
        score -= 1  # public-domain-marked = mostly old archive scans
    score -= 4 * sum(1 for word in TITLE_PENALTIES if word in title)
    if re.search(r"\b1[89]\d\d\b", title):
        score -= 3  # dated archive photo, usually black and white
    width, height = candidate.get("width") or 0, candidate.get("height") or 0
    if width < 500 or height < 400:
        score -= 2
    elif min(width, height) >= 600:
        score += 1
    if width and height and height > 1.6 * width:
        score -= 1
    return score


def rank_candidates(candidates: list[dict], query: str) -> list[dict]:
    indexed = list(enumerate(candidates))
    indexed.sort(key=lambda pair: (-candidate_score(pair[1], query), pair[0]))
    return [candidate for _, candidate in indexed]


def reselect_entries(manifest: dict) -> list[str]:
    """Pick the best-ranked candidate for every entry a human has not reviewed."""
    changed = []
    for entry in manifest.get("entries", []):
        if entry.get("reviewed") or not entry.get("candidates"):
            continue
        best = rank_candidates(entry["candidates"], entry.get("query", ""))[0]
        if entry.get("selected") != best["id"]:
            entry["selected"] = best["id"]
            entry["image"] = None
            changed.append(entry["spanish"])
    return changed


# ── manifest io ──────────────────────────────────────────────────────────────

def load_manifest() -> dict:
    if MANIFEST.exists():
        return json.loads(MANIFEST.read_text(encoding="utf-8"))
    return {"version": 1, "provider": "openverse", "licenses": sorted(FREE_LICENSES), "entries": []}


def save_manifest(manifest: dict) -> None:
    ASSET_ROOT.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def cmd_plan(_args) -> int:
    pdf_entries = json.loads(PDF_MANIFEST.read_text(encoding="utf-8"))["entries"]
    manifest = load_manifest()
    existing = {entry["spanish"].casefold(): entry for entry in manifest["entries"]}
    merged = []
    for entry in plan_entries(pdf_entries):
        old = existing.get(entry["spanish"].casefold())
        if old:
            old["numbers"] = entry["numbers"]
            old["category"] = entry["category"]
            if not old.get("candidates"):
                # let a refreshed query override reach words that found nothing
                old["query"] = entry["query"]
                old.pop("searchedAt", None)
            else:
                old.setdefault("query", entry["query"])
            merged.append(old)
        else:
            merged.append(entry)
    manifest["entries"] = merged
    save_manifest(manifest)
    print(f"planned {len(merged)} entries -> {MANIFEST}")
    return 0


# ── openverse search ─────────────────────────────────────────────────────────

def _http_get(url: str, timeout: float = 30.0):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    return urllib.request.urlopen(request, timeout=timeout)


def search_openverse(query: str) -> tuple[list[dict], dict]:
    params = urllib.parse.urlencode({
        "q": query,
        "license": ",".join(sorted(FREE_LICENSES)),
        "page_size": CANDIDATES_PER_WORD,
        "mature": "false",
    })
    with _http_get(OPENVERSE_API + "?" + params) as response:
        headers = {key.lower(): value for key, value in response.headers.items()}
        payload = json.loads(response.read().decode("utf-8"))
    candidates = [normalize_candidate(item) for item in payload.get("results", [])]
    return [item for item in candidates if item], headers


def cmd_search(args) -> int:
    manifest = load_manifest()
    pending = [entry for entry in manifest["entries"] if not entry.get("candidates") and not entry.get("searchedAt")]
    if args.limit:
        pending = pending[: args.limit]
    print(f"{len(pending)} entries to search")
    done = 0
    for entry in pending:
        candidates = headers = None
        for attempt in range(3):
            try:
                candidates, headers = search_openverse(entry["query"])
                break
            except urllib.error.HTTPError as exc:
                if exc.code == 429:
                    print("rate limited (429); stopping. Re-run later.")
                    return 0
                print(f"! {entry['spanish']}: HTTP {exc.code}")
                break
            except (urllib.error.URLError, OSError, ValueError) as exc:
                # transient network / TLS hiccup: back off and retry
                print(f"! {entry['spanish']}: {exc} (attempt {attempt + 1}/3)")
                time.sleep(5 * (attempt + 1))
        if headers is None:
            continue
        entry["candidates"] = candidates
        entry["searchedAt"] = int(time.time())
        if candidates and entry.get("selected") is None:
            entry["selected"] = candidates[0]["id"]
        done += 1
        save_manifest(manifest)
        remaining_day = headers.get("x-ratelimit-available-anon_sustained", "?")
        print(f"{done:3d} {entry['spanish']:<28} {len(candidates)} candidates  (day quota left {remaining_day})")
        if str(remaining_day).isdigit() and int(remaining_day) <= 1:
            print("daily quota exhausted; stopping. Re-run tomorrow.")
            break
        time.sleep(args.pause)
    return 0


# ── download + resize ────────────────────────────────────────────────────────

def _download(url: str, target: Path, attempts: int = 3) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(request, timeout=60) as response, target.open("wb") as handle:
                handle.write(response.read())
            return
        except Exception:  # noqa: BLE001 - URLError, IncompleteRead, timeouts
            if attempt == attempts - 1:
                raise
            time.sleep(3 * (attempt + 1))


def _resize_to_jpeg(source: Path, target: Path) -> None:
    subprocess.run(
        ["sips", "-s", "format", "jpeg", "-s", "formatOptions", str(JPEG_QUALITY),
         "-Z", str(MAX_WIDTH), str(source), "--out", str(target)],
        check=True, capture_output=True,
    )


def _selected_candidate(entry: dict) -> dict | None:
    for candidate in entry.get("candidates") or []:
        if candidate["id"] == entry.get("selected"):
            return candidate
    return None


def cmd_download(args) -> int:
    manifest = load_manifest()
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    done = skipped = failed = 0
    for entry in manifest["entries"]:
        candidate = _selected_candidate(entry)
        if not candidate:
            skipped += 1
            continue
        image = entry.get("image") or {}
        if image.get("candidateId") == candidate["id"] and (ASSET_ROOT / image.get("file", "")).is_file() and not args.force:
            continue
        filename = f"{min(entry['numbers']):03d}-{_slug(entry['english'])}.jpg"
        target = IMAGE_DIR / filename
        # Try the selected candidate first, then fall back to the next ones in
        # order (some source files are not decodable images).
        ordered = [candidate] + [c for c in entry["candidates"] if c["id"] != candidate["id"]]
        fetched = None
        for option in ordered:
            with tempfile.TemporaryDirectory() as temp:
                raw = Path(temp) / "raw"
                try:
                    _download(option["url"], raw)
                    _resize_to_jpeg(raw, target)
                except Exception as exc:  # noqa: BLE001 - report and try the next candidate
                    print(f"! {entry['spanish']}: {option['id']} {str(exc)[:80]}")
                    continue
            fetched = option
            break
        if not fetched:
            failed += 1
            continue
        if fetched["id"] != candidate["id"]:
            entry["selected"] = fetched["id"]
            candidate = fetched
        content = target.read_bytes()
        entry["image"] = {
            "file": f"images/{filename}",
            "sha256": hashlib.sha256(content).hexdigest(),
            "bytes": len(content),
            "candidateId": candidate["id"],
        }
        done += 1
        save_manifest(manifest)
        print(f"{entry['spanish']:<28} -> {filename} ({len(content) // 1024} KB)")
    print(f"downloaded {done}, failed {failed}, without selection {skipped}")
    return 0


def cmd_reselect(_args) -> int:
    manifest = load_manifest()
    changed = reselect_entries(manifest)
    save_manifest(manifest)
    print(f"reselected {len(changed)} entries: " + ", ".join(changed[:40]) + (" …" if len(changed) > 40 else ""))
    return 0


def cmd_status(_args) -> int:
    manifest = load_manifest()
    entries = manifest["entries"]
    searched = sum(1 for entry in entries if entry.get("searchedAt"))
    with_candidates = sum(1 for entry in entries if entry.get("candidates"))
    downloaded = sum(1 for entry in entries if entry.get("image"))
    print(f"entries {len(entries)} | searched {searched} | with candidates {with_candidates} | downloaded {downloaded}")
    for entry in entries:
        if entry.get("searchedAt") and not entry.get("candidates"):
            print(f"  no free result: {entry['spanish']} ({entry['query']})")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("plan").set_defaults(func=cmd_plan)
    search = sub.add_parser("search")
    search.add_argument("--limit", type=int, default=0)
    search.add_argument("--pause", type=float, default=3.2, help="seconds between requests (20/min anon limit)")
    search.set_defaults(func=cmd_search)
    download = sub.add_parser("download")
    download.add_argument("--force", action="store_true")
    download.set_defaults(func=cmd_download)
    sub.add_parser("reselect", help="re-rank candidates heuristically for unreviewed words").set_defaults(func=cmd_reselect)
    sub.add_parser("status").set_defaults(func=cmd_status)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
