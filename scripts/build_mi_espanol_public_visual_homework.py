#!/usr/bin/env python3
"""Build A0 visual homework from Openverse photos and reviewed library replacements.

Reads ``examples/mi-espanol/assets/vocab-images/manifest.json`` (produced by
``scripts/fetch_mi_espanol_cc0_images.py``) and upserts one assignment,
``vocabulario-a0-visual``, into ``examples/mi-espanol/homework.json``.

Only entries whose picture was downloaded are used. Curated replacements live
in ``curated.json`` separately so another Openverse download cannot undo them.
Every image is
delivered as a separate file (``deliver: "file"``) so the built page stays
small; provenance and license are copied into the image registry.

Three sections, all Spanish-facing:

  1. 看图选西语   single_choice, 4 Spanish options from the same topic
  2. 看图写西语   text_input, accepts the noun with or without its article
  3. 西语选图     single_choice, 3 pictures from the same topic
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT = ROOT / "examples" / "mi-espanol"
MANIFEST = PROJECT_ROOT / "assets" / "vocab-images" / "manifest.json"
HOMEWORK = PROJECT_ROOT / "homework.json"
ASSIGNMENT_ID = "vocabulario-a0-visual"
ARTICLE_RE = re.compile(r"^(el/la|el|la|los|las)\s+", re.IGNORECASE)


def _seed(*parts: object) -> random.Random:
    digest = hashlib.sha256(":".join(str(part) for part in parts).encode("utf-8")).hexdigest()
    return random.Random(int(digest, 16))


def _usable_entries(manifest: dict) -> list[dict]:
    usable = []
    for entry in manifest.get("entries", []):
        image = entry.get("image")
        candidate = next(
            (c for c in entry.get("candidates", []) if c.get("id") == entry.get("selected")),
            None,
        )
        if not image or not candidate or image.get("candidateId") != candidate["id"]:
            continue
        if candidate.get("license") not in {"cc0", "pdm"}:
            continue
        usable.append({**entry, "_candidate": candidate})
    return usable


def _distractors(entries: list[dict], entry: dict, count: int, tag: str) -> list[dict]:
    pool = [
        other for other in entries
        if other["category"] == entry["category"]
        and other["spanish"].casefold() != entry["spanish"].casefold()
    ]
    if len(pool) < count:
        # small topics fall back to the whole list so every word still gets a question
        pool = [other for other in entries if other["spanish"].casefold() != entry["spanish"].casefold()]
    return _seed(ASSIGNMENT_ID, entry["spanish"], tag).sample(pool, count)


def _answers_for(spanish: str) -> list[str]:
    bare = ARTICLE_RE.sub("", spanish).strip()
    return [spanish] if bare.casefold() == spanish.casefold() else [spanish, bare]


def build_assignment(manifest: dict, curated: dict | None = None) -> dict:
    entries = _usable_entries(manifest)
    images: dict[str, dict] = {}
    choice_items, typed_items, picture_items = [], [], []
    for entry in entries:
        number = min(entry["numbers"])
        image_id = f"vocab-a0-{number:03d}"
        candidate = entry["_candidate"]
        images[image_id] = {
            "file": "assets/vocab-images/" + entry["image"]["file"],
            "sha256": entry["image"]["sha256"],
            "deliver": "file",
            "license": candidate["license"],
            "licenseUrl": candidate.get("licenseUrl", ""),
            "creator": candidate.get("creator", ""),
            "sourceUrl": candidate["url"],
            "landing": candidate.get("landing", ""),
            "provider": candidate.get("source", ""),
        }
        entry["_imageId"] = image_id

    for entry in entries:
        number = min(entry["numbers"])
        spanish = entry["spanish"]
        common = {
            "number": number,
            "category": entry["category"],
            "spanish": spanish,
            "english": entry["english"],
        }
        options = [entry, *_distractors(entries, entry, 3, "four-spanish")]
        _seed(ASSIGNMENT_ID, spanish, "shuffle-four").shuffle(options)
        choice_items.append({
            **common,
            "id": f"vocab-a0-public-choice-{number:03d}",
            "prompt": "看图，选出对应的西班牙语单词。",
            "imageId": entry["_imageId"],
            "options": [option["spanish"] for option in options],
            "answers": [spanish],
            "canonicalAnswer": spanish,
            "answerLanguage": "es",
            "answerLanguageLabel": "西班牙语",
        })
        typed_items.append({
            **common,
            "id": f"vocab-a0-public-write-{number:03d}",
            "prompt": "看图，写出对应的西班牙语单词（可带冠词）。",
            "imageId": entry["_imageId"],
            "answers": _answers_for(spanish),
            "canonicalAnswer": spanish,
            "answerLanguage": "es",
            "answerLanguageLabel": "西班牙语",
        })
        pictures = [entry, *_distractors(entries, entry, 2, "three-pictures")]
        _seed(ASSIGNMENT_ID, spanish, "shuffle-three").shuffle(pictures)
        picture_items.append({
            **common,
            "id": f"vocab-a0-public-picture-{number:03d}",
            "prompt": f"选择与西班牙语 “{spanish}” 对应的图片。",
            "options": [option["spanish"] for option in pictures],
            "answers": [spanish],
            "canonicalAnswer": spanish,
            "answerLanguage": "es",
            "imageOptions": [
                {"value": option["spanish"], "imageId": option["_imageId"]} for option in pictures
            ],
        })

    count = len(entries)
    assignment = {
        "id": ASSIGNMENT_ID,
        "title": f"A0 图片词汇练习（{count} 词）",
        "badge": "图片练习",
        "sourceTitle": "A0 视觉词汇 · CC0 图片",
        "teacher": "Profesor de ejemplo",
        "level": "A0",
        "answerKeyBasis": "source_provided",
        "contentOrigin": "adapted_public",
        "localOnly": False,
        "source": {
            "title": "A0 visual vocabulary",
            "license": "CC0 / public domain photos via Openverse",
            "attribution": "词表来自 Mi Español 公开词表；图片均为 CC0 或公有领域，出处记录在每张图的 sourceUrl / landing 字段。",
        },
        "images": images,
        "sections": [
            {
                "id": "vocab-a0-public-image-to-spanish",
                "title": "第 1 部分 - 看图选西语",
                "type": "single_choice",
                "instructions": "观察图片，从四个西班牙语单词中选出正确的一个。",
                "items": choice_items,
            },
            {
                "id": "vocab-a0-public-image-write",
                "title": "第 2 部分 - 看图写西语",
                "type": "text_input",
                "instructions": "观察图片，写出对应的西班牙语单词。带不带冠词都算对。",
                "items": typed_items,
            },
            {
                "id": "vocab-a0-public-spanish-to-image",
                "title": "第 3 部分 - 西语选图",
                "type": "single_choice",
                "instructions": "阅读西班牙语单词，从三张图片中选出正确的一张。",
                "items": picture_items,
            },
        ],
    }
    if curated:
        apply_curated_images(assignment, curated)
    return assignment


def apply_curated_images(assignment: dict, curated: dict) -> None:
    """Replace only image metadata; preserve all question and progress identities."""
    for image_id, replacement in curated.get("images", {}).items():
        if image_id not in assignment["images"]:
            raise ValueError(f"unknown curated image: {image_id}")
        if replacement.get("reviewed") is not True:
            raise ValueError(f"unreviewed curated image: {image_id}")
        for field in ("file", "sha256", "license", "licenseUrl", "creator", "sourceUrl", "landing", "provider"):
            if not replacement.get(field):
                raise ValueError(f"missing {field} for curated image: {image_id}")
        assignment["images"][image_id] = {**replacement, "deliver": "file"}
    if curated.get("images"):
        assignment["sourceTitle"] = "A0 视觉词汇 · 精选配图"
        assignment["source"] = {
            "title": "A0 visual vocabulary",
            "license": "配图按各图库许可使用",
            "attribution": "词表来自 Mi Español 公开词表；插画与照片的作者、来源和许可随每张配图保留。",
        }


def upsert(homework_path: Path, assignment: dict) -> None:
    data = json.loads(homework_path.read_text(encoding="utf-8"))
    assignments = [item for item in data.get("assignments", []) if item.get("id") != assignment["id"]]
    assignments.append(assignment)
    data["assignments"] = assignments
    homework_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    parser.add_argument("--homework", type=Path, default=HOMEWORK)
    parser.add_argument("--curated", type=Path, help="reviewed replacements; defaults to curated.json beside manifest")
    args = parser.parse_args(argv)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    curated_path = args.curated or args.manifest.with_name("curated.json")
    curated = json.loads(curated_path.read_text(encoding="utf-8")) if curated_path.exists() else None
    assignment = build_assignment(manifest, curated)
    for image in assignment["images"].values():
        path = PROJECT_ROOT / image["file"]
        if not path.is_file():
            raise SystemExit(f"missing image file: {image['file']}")
        if hashlib.sha256(path.read_bytes()).hexdigest() != image["sha256"]:
            raise SystemExit(f"checksum mismatch: {image['file']}")
    upsert(args.homework, assignment)
    print(json.dumps({
        "assignment": assignment["id"],
        "words": len(assignment["images"]),
        "questions": sum(len(section["items"]) for section in assignment["sections"]),
        "homework": str(args.homework),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
