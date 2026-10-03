#!/usr/bin/env python3
"""Build one A1 picture-vocabulary assignment per topic.

Reads ``examples/mi-espanol/assets/vocab-images/a1-topics.json`` and upserts
one assignment per topic (``vocabulario-a1-<topic>``) into
``examples/mi-espanol/homework.json``, so the homework list is grouped by word
category. Each assignment has the same three sections as the A0 visual
homework:

  1. 看图选西语   single_choice, 4 Spanish options from the same topic
  2. 看图写西语   text_input, accepts the noun with or without its article
  3. 西语选图     single_choice, 3 pictures from the same topic

Every picture is delivered as a separate file (``deliver: "file"``); its
provenance and license are copied from the topics file into the image registry.
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
TOPICS = PROJECT_ROOT / "assets" / "vocab-images" / "a1-topics.json"
HOMEWORK = PROJECT_ROOT / "homework.json"
ID_PREFIX = "vocabulario-a1-"
ARTICLE_RE = re.compile(r"^(el/la|el|la|los|las)\s+", re.IGNORECASE)
IMAGE_FIELDS = ("file", "sha256", "license", "licenseUrl", "creator", "sourceUrl", "landing", "provider")


def _seed(*parts: object) -> random.Random:
    digest = hashlib.sha256(":".join(str(part) for part in parts).encode("utf-8")).hexdigest()
    return random.Random(int(digest, 16))


def _answers_for(entry: dict) -> list[str]:
    answers = []
    for spanish in [entry["spanish"], *entry.get("answers", [])]:
        for value in (spanish, ARTICLE_RE.sub("", spanish).strip()):
            if value and value not in answers:
                answers.append(value)
    return answers


def build_assignment(topic: dict) -> dict:
    assignment_id = ID_PREFIX + topic["id"]
    entries = topic["entries"]
    if len(entries) < 4:
        raise ValueError(f"topic {topic['id']} needs at least 4 words")
    images: dict[str, dict] = {}
    image_ids: dict[str, str] = {}
    for entry in entries:
        image = entry["image"]
        if image.get("reviewed") is not True:
            raise ValueError(f"unreviewed image: {entry['spanish']}")
        for field in IMAGE_FIELDS:
            if not image.get(field):
                raise ValueError(f"missing {field} for image: {entry['spanish']}")
        image_id = f"vocab-a1-{topic['id']}-{entry['key']}"
        if image_id in images:
            raise ValueError(f"duplicate image id: {image_id}")
        images[image_id] = {**image, "deliver": "file"}
        image_ids[entry["spanish"]] = image_id

    def distractors(entry: dict, count: int, tag: str) -> list[dict]:
        pool = [other for other in entries if other["spanish"] != entry["spanish"]]
        return _seed(assignment_id, entry["spanish"], tag).sample(pool, count)

    choice_items, typed_items, picture_items = [], [], []
    for number, entry in enumerate(entries, start=1):
        spanish = entry["spanish"]
        common = {
            "number": number,
            "category": topic["title"],
            "spanish": spanish,
            "english": entry["english"],
        }
        options = [entry, *distractors(entry, 3, "four-spanish")]
        _seed(assignment_id, spanish, "shuffle-four").shuffle(options)
        choice_items.append({
            **common,
            "id": f"{assignment_id}-choice-{entry['key']}",
            "prompt": "看图，选出对应的西班牙语单词。",
            "imageId": image_ids[spanish],
            "options": [option["spanish"] for option in options],
            "answers": [spanish],
            "canonicalAnswer": spanish,
            "answerLanguage": "es",
            "answerLanguageLabel": "西班牙语",
        })
        typed_items.append({
            **common,
            "id": f"{assignment_id}-write-{entry['key']}",
            "prompt": "看图，写出对应的西班牙语单词（可带冠词）。",
            "imageId": image_ids[spanish],
            "answers": _answers_for(entry),
            "canonicalAnswer": spanish,
            "answerLanguage": "es",
            "answerLanguageLabel": "西班牙语",
        })
        pictures = [entry, *distractors(entry, 2, "three-pictures")]
        _seed(assignment_id, spanish, "shuffle-three").shuffle(pictures)
        picture_items.append({
            **common,
            "id": f"{assignment_id}-picture-{entry['key']}",
            "prompt": f"选择与西班牙语 “{spanish}” 对应的图片。",
            "options": [option["spanish"] for option in pictures],
            "answers": [spanish],
            "canonicalAnswer": spanish,
            "answerLanguage": "es",
            "imageOptions": [
                {"value": option["spanish"], "imageId": image_ids[option["spanish"]]} for option in pictures
            ],
        })

    return {
        "id": assignment_id,
        "title": f"A1 图片词汇 · {topic['title']}（{len(entries)} 词）",
        "badge": topic["title"],
        "sourceTitle": f"Vocabulario A1 · {topic['spanishTitle']}",
        "teacher": "Profesor de ejemplo",
        "level": "A1",
        "answerKeyBasis": "source_provided",
        "contentOrigin": "adapted_public",
        "localOnly": False,
        "source": {
            "title": f"A1 vocabulary · {topic['spanishTitle']}",
            "license": "配图按各图库许可使用",
            "attribution": "词表来自 Mi Español 公开词表；插画的作者、来源和许可随每张配图保留。",
        },
        "images": images,
        "sections": [
            {
                "id": f"{assignment_id}-image-to-spanish",
                "title": "第 1 部分 - 看图选西语",
                "type": "single_choice",
                "instructions": "观察图片，从四个西班牙语单词中选出正确的一个。",
                "items": choice_items,
            },
            {
                "id": f"{assignment_id}-image-write",
                "title": "第 2 部分 - 看图写西语",
                "type": "text_input",
                "instructions": "观察图片，写出对应的西班牙语单词。带不带冠词都算对。",
                "items": typed_items,
            },
            {
                "id": f"{assignment_id}-spanish-to-image",
                "title": "第 3 部分 - 西语选图",
                "type": "single_choice",
                "instructions": "阅读西班牙语单词，从三张图片中选出正确的一张。",
                "items": picture_items,
            },
        ],
    }


def upsert(homework_path: Path, new_assignments: list[dict]) -> None:
    data = json.loads(homework_path.read_text(encoding="utf-8"))
    assignments = [
        item for item in data.get("assignments", [])
        if not str(item.get("id", "")).startswith(ID_PREFIX)
    ]
    data["assignments"] = assignments + new_assignments
    homework_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--topics", type=Path, default=TOPICS)
    parser.add_argument("--homework", type=Path, default=HOMEWORK)
    args = parser.parse_args(argv)
    topics = json.loads(args.topics.read_text(encoding="utf-8"))["topics"]
    assignments = [build_assignment(topic) for topic in topics]
    for assignment in assignments:
        for image in assignment["images"].values():
            path = PROJECT_ROOT / image["file"]
            if not path.is_file():
                raise SystemExit(f"missing image file: {image['file']}")
            if hashlib.sha256(path.read_bytes()).hexdigest() != image["sha256"]:
                raise SystemExit(f"checksum mismatch: {image['file']}")
    upsert(args.homework, assignments)
    print(json.dumps({
        "assignments": [assignment["id"] for assignment in assignments],
        "words": sum(len(assignment["images"]) for assignment in assignments),
        "homework": str(args.homework),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
