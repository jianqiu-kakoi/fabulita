#!/usr/bin/env python3
"""Build the present-tense conjugation assignment ``presente-verbos-a1``.

Upserts one assignment into ``examples/mi-espanol/homework.json``:

  1. 选变位   single_choice: pick the form of ser / estar / tener / salir
              that matches the person (``yo → estar``: estoy / estás / ...)
  2. tener    text_input, one item per person
  3. salir    text_input, one item per person
  4. 规则动词 text_input: trabajar, hablar, comer, beber, vivir, abrir

The answer key is the standard present indicative; nothing is taken from a
worksheet.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
HOMEWORK = ROOT / "examples" / "mi-espanol" / "homework.json"
ASSIGNMENT_ID = "presente-verbos-a1"
PERSONS = [
    "yo", "tú", "él / ella",
    "nosotros / nosotras", "vosotros / vosotras", "ellos / ellas",
]
IRREGULAR = {
    "ser": ("是：身份、职业、较稳定特征", ["soy", "eres", "es", "somos", "sois", "son"]),
    "estar": ("是 / 在：位置、当前状态", ["estoy", "estás", "está", "estamos", "estáis", "están"]),
    "tener": ("有", ["tengo", "tienes", "tiene", "tenemos", "tenéis", "tienen"]),
    "salir": ("出去、离开", ["salgo", "sales", "sale", "salimos", "salís", "salen"]),
}
REGULAR = {
    "trabajar": "工作", "hablar": "说话",
    "comer": "吃", "beber": "喝",
    "vivir": "居住、生活", "abrir": "打开",
}
ENDINGS = {
    "ar": ["o", "as", "a", "amos", "áis", "an"],
    "er": ["o", "es", "e", "emos", "éis", "en"],
    "ir": ["o", "es", "e", "imos", "ís", "en"],
}


def _seed(*parts: object) -> random.Random:
    digest = hashlib.sha256(":".join(str(part) for part in parts).encode("utf-8")).hexdigest()
    return random.Random(int(digest, 16))


def conjugate(verb: str) -> list[str]:
    if verb in IRREGULAR:
        return list(IRREGULAR[verb][1])
    return [verb[:-2] + ending for ending in ENDINGS[verb[-2:]]]


def _typed_section(verb: str, number_from: int = 1) -> list[dict]:
    return [
        {
            "id": f"presente-{verb}-{index:02d}",
            "number": number_from + index - 1,
            "person": person,
            "verb": verb,
            "prompt": f"{person} → {verb}",
            "answers": [form],
        }
        for index, (person, form) in enumerate(zip(PERSONS, conjugate(verb)), start=1)
    ]


def build_assignment() -> dict:
    meanings = {**{verb: meaning for verb, (meaning, _) in IRREGULAR.items()}, **REGULAR}
    reference_tables = [
        {
            "id": f"{verb}-reference",
            "verb": verb,
            "title": f"{verb.capitalize()}：{meanings[verb]}",
            "rows": [{"person": person, "form": form} for person, form in zip(PERSONS, conjugate(verb))],
        }
        for verb in [*IRREGULAR, *REGULAR]
    ]

    choice_items = []
    for verb in IRREGULAR:
        forms = conjugate(verb)
        for index, (person, form) in enumerate(zip(PERSONS, forms), start=1):
            others = _seed(ASSIGNMENT_ID, verb, person, "distractors").sample(
                [other for other in forms if other != form], 3
            )
            options = [form, *others]
            _seed(ASSIGNMENT_ID, verb, person, "shuffle").shuffle(options)
            choice_items.append({
                "id": f"presente-choice-{verb}-{index:02d}",
                "number": len(choice_items) + 1,
                "person": person,
                "verb": verb,
                "prompt": f"{person} → {verb}",
                "options": options,
                "answers": [form],
                "canonicalAnswer": form,
            })

    regular_items = []
    for verb in REGULAR:
        regular_items.extend(_typed_section(verb, number_from=len(regular_items) + 1))

    return {
        "id": ASSIGNMENT_ID,
        "title": "现在时变位：ser / estar / tener / salir 与规则动词 A1",
        "badge": "变位练习",
        "sourceTitle": "Práctica de conjugación: presente de indicativo",
        "level": "A1",
        "answerKeyBasis": "standard_conjugation",
        "referenceTables": reference_tables,
        "sections": [
            {
                "id": "presente-choice",
                "title": "Parte 1 - Elige la forma correcta",
                "instructions": "看人称，选出动词正确的现在时形式。",
                "type": "single_choice",
                "items": choice_items,
            },
            {
                "id": "presente-tener",
                "title": "Parte 2 - Conjuga tener",
                "instructions": "Escribe la forma correcta de tener para cada persona.",
                "type": "text_input",
                "verb": "tener",
                "items": _typed_section("tener"),
            },
            {
                "id": "presente-salir",
                "title": "Parte 3 - Conjuga salir",
                "instructions": "Escribe la forma correcta de salir para cada persona.",
                "type": "text_input",
                "verb": "salir",
                "items": _typed_section("salir"),
            },
            {
                "id": "presente-regulares",
                "title": "Parte 4 - Verbos regulares -ar / -er / -ir",
                "instructions": "Escribe la forma correcta del verbo regular para cada persona.",
                "type": "text_input",
                "items": regular_items,
            },
        ],
    }


def upsert(homework_path: Path, assignment: dict) -> None:
    data = json.loads(homework_path.read_text(encoding="utf-8"))
    assignments = [item for item in data.get("assignments", []) if item.get("id") != assignment["id"]]
    assignments.append(assignment)
    data["assignments"] = assignments
    homework_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--homework", type=Path, default=HOMEWORK)
    args = parser.parse_args(argv)
    assignment = build_assignment()
    upsert(args.homework, assignment)
    print(json.dumps({
        "assignment": assignment["id"],
        "questions": sum(len(section["items"]) for section in assignment["sections"]),
        "homework": str(args.homework),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
