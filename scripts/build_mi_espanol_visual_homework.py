#!/usr/bin/env python3
"""Build the local-only A0 visual English homework from the supplied PDF.

The PDF contains six cover illustrations followed by one JPEG illustration for
each of its 287 numbered Spanish-English entries. This script preserves those
illustrations as local assets and upserts one assignment into the ignored
``examples/mi-espanol/homework.local.json`` file.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import shutil
import subprocess
import tempfile
import unicodedata
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT = ROOT / "examples" / "mi-espanol"
ASSET_ROOT = PROJECT_ROOT / "materials" / "vocabulario-a0-visual"
LOCAL_HOMEWORK = PROJECT_ROOT / "homework.local.json"
ASSIGNMENT_ID = "vocabulario-a0-visual-english"
EXPECTED_ENTRY_COUNT = 287
EXPECTED_COVER_IMAGE_COUNT = 6
EXPECTED_CATEGORY_COUNTS = {
    "Animales": 54,
    "Deportes": 27,
    "Calendario y estaciones": 23,
    "Partes del cuerpo": 34,
    "Electrodomésticos": 27,
    "El tiempo": 14,
    "La playa": 36,
    "Frutas y verduras": 31,
    "Transportes": 18,
    "Muebles": 23,
}


def _run(*args: str) -> None:
    subprocess.run(args, check=True)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _slug(value: str) -> str:
    ascii_value = (
        unicodedata.normalize("NFKD", value)
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower()
    )
    return re.sub(r"[^a-z0-9]+", "-", ascii_value).strip("-") or "entry"


def _split_columns(line: str) -> list[str]:
    return [part.strip() for part in re.split(r"\s{3,}", line.strip())]


def _extract_entries(pdf_path: Path, temp_dir: Path) -> list[dict]:
    text_path = temp_dir / "vocabulario-a0.txt"
    _run("pdftotext", "-layout", str(pdf_path), str(text_path))
    pages = text_path.read_text(encoding="utf-8").split("\f")
    entries: list[dict] = []

    # pages[0] is the cover. pages[1] is PDF page 2, where entry 1 starts.
    for source_page, page in enumerate(pages[1:], start=2):
        lines = page.splitlines()
        nonempty = [line.strip() for line in lines if line.strip()]
        if len(nonempty) < 2:
            continue
        category = _split_columns(nonempty[1])[0]
        index = 2
        while index < len(lines):
            number_line = lines[index].strip()
            if not re.fullmatch(r"\d+(?:\s+\d+)*", number_line):
                index += 1
                continue
            numbers = re.findall(r"\d+", number_line)
            value_rows: list[list[str]] = []
            cursor = index + 1
            while cursor < len(lines) and len(value_rows) < 2:
                if lines[cursor].strip():
                    value_rows.append(_split_columns(lines[cursor]))
                cursor += 1
            if (
                len(value_rows) == 2
                and len(numbers) == len(value_rows[0]) == len(value_rows[1])
            ):
                for number, spanish, english in zip(numbers, *value_rows):
                    entries.append(
                        {
                            "number": int(number),
                            "spanish": spanish,
                            "english": english,
                            "category": category,
                            "sourcePage": source_page,
                        }
                    )
            index = cursor

    numbers = [entry["number"] for entry in entries]
    if numbers != list(range(1, EXPECTED_ENTRY_COUNT + 1)):
        raise ValueError(
            "PDF entry numbering mismatch: "
            f"expected 1..{EXPECTED_ENTRY_COUNT}, got {numbers[:3]}..{numbers[-3:]}"
        )
    category_counts = Counter(entry["category"] for entry in entries)
    if category_counts != Counter(EXPECTED_CATEGORY_COUNTS):
        raise ValueError(f"PDF category counts changed: {dict(category_counts)}")
    return entries


def _extract_images(pdf_path: Path, temp_dir: Path) -> list[Path]:
    prefix = temp_dir / "raw"
    _run("pdfimages", "-j", str(pdf_path), str(prefix))
    images = sorted(temp_dir.glob("raw-*.jpg"))
    expected = EXPECTED_COVER_IMAGE_COUNT + EXPECTED_ENTRY_COUNT
    if len(images) != expected:
        raise ValueError(f"expected {expected} JPEG objects, found {len(images)}")
    return images[EXPECTED_COVER_IMAGE_COUNT:]


def _write_assets(entries: list[dict], raw_images: list[Path]) -> dict[str, dict]:
    image_dir = ASSET_ROOT / "images"
    image_dir.mkdir(parents=True, exist_ok=True)
    registry: dict[str, dict] = {}
    for entry, raw_image in zip(entries, raw_images):
        number = entry["number"]
        image_id = f"vocab-a0-{number:03d}"
        filename = f"{number:03d}-{_slug(entry['english'])}.jpg"
        target = image_dir / filename
        shutil.copyfile(raw_image, target)
        digest = _sha256(target)
        entry["imageId"] = image_id
        entry["imageFile"] = target.relative_to(PROJECT_ROOT).as_posix()
        entry["imageSha256"] = digest
        registry[image_id] = {
            "file": entry["imageFile"],
            "sha256": digest,
            "filename": filename,
        }
    return registry


def _distractors(entries: list[dict], entry: dict, source_sha256: str) -> list[dict]:
    target_english = entry["english"].casefold()
    candidates = [
        candidate
        for candidate in entries
        if candidate["category"] == entry["category"]
        and candidate["number"] != entry["number"]
        and candidate["english"].casefold() != target_english
    ]
    if len(candidates) < 2:
        raise ValueError(f"not enough distractors for entry {entry['number']}")
    seed_text = f"{source_sha256}:{entry['number']}:three-image-choice"
    rng = random.Random(int(hashlib.sha256(seed_text.encode()).hexdigest(), 16))
    return rng.sample(candidates, 2)


def _spanish_distractors(entries: list[dict], entry: dict, source_sha256: str) -> list[dict]:
    target_spanish = entry["spanish"].casefold()
    candidates = [
        candidate
        for candidate in entries
        if candidate["category"] == entry["category"]
        and candidate["number"] != entry["number"]
        and candidate["spanish"].casefold() != target_spanish
    ]
    if len(candidates) < 3:
        raise ValueError(f"not enough Spanish distractors for entry {entry['number']}")
    seed_text = f"{source_sha256}:{entry['number']}:four-spanish-choice"
    rng = random.Random(int(hashlib.sha256(seed_text.encode()).hexdigest(), 16))
    return rng.sample(candidates, 3)


def _assignment(entries: list[dict], registry: dict[str, dict], source_sha256: str) -> dict:
    write_items = []
    choice_items = []
    spanish_items = []
    for entry in entries:
        number = entry["number"]
        english = entry["english"]
        common = {
            "number": number,
            "sourcePage": entry["sourcePage"],
            "category": entry["category"],
            "spanish": entry["spanish"],
            "english": english,
            "localOnlyGrading": True,
        }
        write_items.append(
            {
                **common,
                "id": f"vocab-a0-image-write-{number:03d}",
                "prompt": "看图，写出对应的英语单词或短语。",
                "imageId": entry["imageId"],
                "answers": [english],
                "canonicalAnswer": english,
                "answerLanguage": "en",
                "answerLanguageLabel": "英语",
            }
        )

        option_entries = [entry, *_distractors(entries, entry, source_sha256)]
        choice_rng = random.Random(number * 1009 + 17)
        choice_rng.shuffle(option_entries)
        choice_items.append(
            {
                **common,
                "id": f"vocab-a0-english-image-{number:03d}",
                "prompt": f"选择与英语 “{english}” 对应的图片。",
                "options": [option["english"] for option in option_entries],
                "answers": [english],
                "canonicalAnswer": english,
                "answerLanguage": "en",
                "imageOptions": [
                    {
                        "value": option["english"],
                        "imageId": option["imageId"],
                    }
                    for option in option_entries
                ],
            }
        )

        spanish_options = [entry, *_spanish_distractors(entries, entry, source_sha256)]
        random.Random(number * 2003 + 29).shuffle(spanish_options)
        spanish_items.append(
            {
                **common,
                "id": f"vocab-a0-image-spanish-{number:03d}",
                "prompt": "看图，选出对应的西班牙语单词。",
                "imageId": entry["imageId"],
                "options": [option["spanish"] for option in spanish_options],
                "answers": [entry["spanish"]],
                "canonicalAnswer": entry["spanish"],
                "answerLanguage": "es",
                "answerLanguageLabel": "西班牙语",
            }
        )

    return {
        "id": ASSIGNMENT_ID,
        "title": "A0 图片词汇练习（287 词）",
        "badge": "本地图片练习",
        "sourceTitle": "Vocabulario A0 - Principiante - Cuaderno visual",
        "level": "A0",
        "answerKeyBasis": "source_provided",
        "contentOrigin": "verbatim_local_visual_source",
        "localOnly": True,
        "source": {
            "title": "Vocabulario A0 - Principiante - Cuaderno visual",
            "author": "Profesor de ejemplo",
            "sha256": source_sha256,
            "license": "仅限本地学习",
            "localOnly": True,
            "reusedImages": True,
            "attribution": "原始西语、英语词条与插图来自用户提供的本地 PDF。",
            "changes": "互动版新增中文说明、图片填空、图片三选一和看图选西语四选一，并保留原图。",
        },
        "images": registry,
        "sections": [
            {
                "id": "vocab-a0-image-to-spanish",
                "title": "第 1 部分 - 看图选西语",
                "type": "single_choice",
                "instructions": "观察图片，从四个西班牙语单词中选出正确的一个。",
                "items": spanish_items,
            },
            {
                "id": "vocab-a0-image-to-english",
                "title": "第 2 部分 - 看图写英文",
                "type": "text_input",
                "instructions": "观察图片，填写 PDF 中对应的英语单词或短语。",
                "items": write_items,
            },
            {
                "id": "vocab-a0-english-to-image",
                "title": "第 3 部分 - 英文选图片",
                "type": "single_choice",
                "instructions": "阅读英语单词或短语，从三张图片中选出正确的一张。",
                "items": choice_items,
            },
        ],
    }


def _write_manifest(entries: list[dict], source_path: Path, source_sha256: str) -> None:
    manifest = {
        "version": 1,
        "source": {
            "filename": source_path.name,
            "sha256": source_sha256,
            "title": "Vocabulario A0 - Principiante - Cuaderno visual",
            "author": "Profesor de ejemplo",
        },
        "coverImageCount": EXPECTED_COVER_IMAGE_COUNT,
        "entryCount": len(entries),
        "entries": entries,
    }
    (ASSET_ROOT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _upsert_local_homework(assignment: dict) -> None:
    if LOCAL_HOMEWORK.exists():
        data = json.loads(LOCAL_HOMEWORK.read_text(encoding="utf-8"))
    else:
        data = {"version": 1, "assignments": []}
    if not isinstance(data, dict) or not isinstance(data.get("assignments"), list):
        raise ValueError(f"invalid local homework file: {LOCAL_HOMEWORK}")
    assignments = [
        existing
        for existing in data["assignments"]
        if not isinstance(existing, dict) or existing.get("id") != ASSIGNMENT_ID
    ]
    assignments.append(assignment)
    data["version"] = 1
    data["assignments"] = assignments
    LOCAL_HOMEWORK.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", type=Path, help="path to the source vocabulary PDF")
    args = parser.parse_args()
    pdf_path = args.pdf.expanduser().resolve()
    if not pdf_path.is_file():
        raise SystemExit(f"source PDF not found: {pdf_path}")

    source_sha256 = _sha256(pdf_path)
    with tempfile.TemporaryDirectory(prefix="fabulita-vocab-a0-") as temp:
        temp_dir = Path(temp)
        entries = _extract_entries(pdf_path, temp_dir)
        raw_images = _extract_images(pdf_path, temp_dir)
        registry = _write_assets(entries, raw_images)

    assignment = _assignment(entries, registry, source_sha256)
    _write_manifest(entries, pdf_path, source_sha256)
    _upsert_local_homework(assignment)
    print(
        json.dumps(
            {
                "assignment": ASSIGNMENT_ID,
                "entries": len(entries),
                "images": len(registry),
                "questions": sum(
                    len(section["items"]) for section in assignment["sections"]
                ),
                "assetRoot": str(ASSET_ROOT),
                "localHomework": str(LOCAL_HOMEWORK),
                "sourceSha256": source_sha256,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
