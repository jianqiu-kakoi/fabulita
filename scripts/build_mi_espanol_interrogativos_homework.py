#!/usr/bin/env python3
"""Build the question-word assignment ``interrogativos-ser-estar-a1``.

Upserts one assignment into ``examples/mi-espanol/homework.json``:

  1. 选疑问词      single_choice: pick the question word that fits the answer
  2. por qué ...   single_choice: por qué / porque / para qué / para
  3. ser o estar   single_choice: es / está, soy / estoy, ...
  4. 变位填空      text_input: present tense of ser and estar in a sentence
  5. 中译西        text_input: translate short questions into Spanish

The sentences follow the learner's own class notes on question words and
ser / estar; the answer key is standard grammar, not taken from a worksheet.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
import unicodedata
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
HOMEWORK = ROOT / "examples" / "mi-espanol" / "homework.json"
ASSIGNMENT_ID = "interrogativos-ser-estar-a1"
BLANK = "_______"
PERSONS = [
    "yo", "tú", "él / ella",
    "nosotros / nosotras", "vosotros / vosotras", "ellos / ellas",
]
SER = ["soy", "eres", "es", "somos", "sois", "son"]
ESTAR = ["estoy", "estás", "está", "estamos", "estáis", "están"]

# (prompt, options, answer, translation, note)
QUESTION_WORDS = [
    ("¿_______ estudias? — Estudio español.", ["qué", "quién", "dónde"], "qué",
     "你学什么？——我学西班牙语。", ""),
    ("¿_______ eres? — Soy Juan.", ["quién", "cuándo", "cuántos"], "quién",
     "你是谁？——我是 Juan。", ""),
    ("¿_______ es tu color favorito? — El azul.", ["cuál", "quién", "dónde"], "cuál",
     "你最喜欢什么颜色？——蓝色。", "问“哪一个”时用 cuál，后面常接 es / son。"),
    ("¿_______ te llamas? — Me llamo Juan.", ["cómo", "dónde", "cuántos"], "cómo",
     "你叫什么名字？——我叫 Juan。", "西语说“你怎么称呼自己”，所以用 cómo，不用 qué。"),
    ("¿_______ estás? — Estoy bien.", ["cómo", "quién", "cuándo"], "cómo",
     "你好吗？——我很好。", ""),
    ("¿_______ vienes a casa? — El lunes.", ["cuándo", "cómo", "quién"], "cuándo",
     "你什么时候来家里？——星期一。", ""),
    ("¿_______ estás? — Estoy en casa.", ["dónde", "quién", "cuándo"], "dónde",
     "你在哪儿？——我在家。", ""),
    ("¿_______ está el baño? — A la derecha.", ["dónde", "cuándo", "quién"], "dónde",
     "洗手间在哪里？——在右边。", ""),
    ("¿_______ perros tienes? — Tengo un perro.", ["cuántos", "cuál", "cómo"], "cuántos",
     "你有几只狗？——我有一只狗。", "perros 是阳性复数，所以用 cuántos。"),
    ("¿_______ abro la puerta?", ["cómo", "quién", "cuántos"], "cómo",
     "我怎么开门？", ""),
]

WHY_FOR = [
    ("¿_______ estudias español? — Porque me gusta.", "por qué",
     "你为什么学西班牙语？——因为我喜欢。", "回答用 porque（因为），所以问的是原因：¿por qué?"),
    ("¿Por qué estudias español? — _______ me gusta.", "porque",
     "你为什么学西班牙语？——因为我喜欢。", "回答原因用 porque：连写、不带重音。"),
    ("¿_______ estudias español? — Para viajar a España.", "para qué",
     "你学西班牙语是为了什么？——为了去西班牙旅行。", "回答是 para + 动词原形（目的），所以问 ¿para qué?"),
    ("¿Para qué estudias español? — _______ viajar a España.", "para",
     "你学西班牙语是为了什么？——为了去西班牙旅行。", "表示目的：para + 动词原形。"),
    ("No puedo beber _______ no tengo agua.", "porque",
     "我不能喝，因为我没有水。", ""),
    ("¿_______ no bebes? — Porque no tengo agua.", "por qué",
     "你为什么不喝？——因为我没有水。", ""),
]
WHY_FOR_OPTIONS = ["por qué", "porque", "para qué", "para"]

# (prompt, options, answer, translation, note)
SER_ESTAR = [
    ("¿Cómo _______ tu perro? — Es pequeño y blanco.", ["es", "está"], "es",
     "你的狗是什么样的？——它又小又白。", "问特征（长什么样）用 ser：¿cómo es…?"),
    ("¿Cómo _______ tu hermano? — Está cansado.", ["es", "está"], "está",
     "你兄弟现在怎么样？——他累了。", "问现在的状态用 estar：¿cómo está…?"),
    ("¿Dónde _______ el baño?", ["es", "está"], "está",
     "洗手间在哪里？", "位置用 estar。"),
    ("Mi padre _______ bien.", ["es", "está"], "está",
     "我父亲很好。", "状态（好不好）用 estar。"),
    ("Yo _______ Juan.", ["soy", "estoy"], "soy",
     "我是 Juan。", "名字用 ser。"),
    ("¿Quién _______? — Soy Juan.", ["eres", "estás"], "eres",
     "你是谁？——我是 Juan。", "问身份用 ser。"),
    ("Nosotros _______ en casa.", ["somos", "estamos"], "estamos",
     "我们在家。", "位置用 estar。"),
    ("Ellos _______ de España.", ["son", "están"], "son",
     "他们来自西班牙。", "国籍、来源用 ser。"),
    ("María _______ muy contenta hoy.", ["es", "está"], "está",
     "María 今天很开心。", "心情（暂时）用 estar。"),
    ("Vosotros _______ amigos.", ["sois", "estáis"], "sois",
     "你们是朋友。", "身份、关系用 ser。"),
    ("Quiero _______ como tú.", ["ser", "estar"], "ser",
     "我想成为像你一样的人。", "“成为什么样的人”是特征，用 ser。"),
]

# (prompt, verb, person index, translation)
CONJUGATION = [
    ("Yo _______ Juan. (ser)", "ser", 0, "我是 Juan。"),
    ("Tú _______ mi amigo. (ser)", "ser", 1, "你是我的朋友。"),
    ("Ella _______ profesora. (ser)", "ser", 2, "她是老师。"),
    ("Nosotros _______ estudiantes. (ser)", "ser", 3, "我们是学生。"),
    ("Vosotras _______ de China. (ser)", "ser", 4, "你们来自中国。"),
    ("Ellos _______ altos. (ser)", "ser", 5, "他们个子高。"),
    ("Yo _______ bien. (estar)", "estar", 0, "我很好。"),
    ("¿Dónde _______ tú? (estar)", "estar", 1, "你在哪儿？"),
    ("Mi hermano _______ cansado. (estar)", "estar", 2, "我兄弟累了。"),
    ("Nosotras _______ en casa. (estar)", "estar", 3, "我们在家。"),
    ("¿Cómo _______ vosotros? (estar)", "estar", 4, "你们好吗？"),
    ("Mis padres _______ en España. (estar)", "estar", 5, "我父母在西班牙。"),
]

# (Chinese prompt, accepted Spanish answers, first one canonical)
TRANSLATE = [
    ("你叫什么名字？", ["¿Cómo te llamas?", "¿Cómo te llamas tú?", "¿Tú cómo te llamas?"]),
    ("你是谁？", ["¿Quién eres?", "¿Quién eres tú?"]),
    ("你学什么？", ["¿Qué estudias?", "¿Qué estudias tú?"]),
    ("你好吗？", ["¿Cómo estás?", "¿Cómo estás tú?", "¿Qué tal?"]),
    ("洗手间在哪里？", ["¿Dónde está el baño?", "¿Dónde está el servicio?", "¿Dónde está el aseo?"]),
    ("你最喜欢什么颜色？", ["¿Cuál es tu color favorito?"]),
    ("你什么时候来家里？", ["¿Cuándo vienes a casa?"]),
    ("你为什么学西班牙语？", ["¿Por qué estudias español?", "¿Por qué estudias tú español?"]),
    ("你有几只狗？", ["¿Cuántos perros tienes?", "¿Cuántos perros tienes tú?"]),
    ("我想成为像你一样的人。", ["Quiero ser como tú.", "Yo quiero ser como tú."]),
]

# Words in the answer sentences that vocab.csv only lists in another form, so
# the learner page can still underline and gloss them.
SENTENCE_LEXICON = [
    ("estudiar", ["estudio", "estudias"], "学习", "to study"),
    ("llamarse", ["te llamas", "me llamo", "llamas", "llamo"], "叫（名字）", "to be called"),
    ("tener", ["tienes", "tengo"], "有", "to have"),
    ("beber", ["bebes"], "喝", "to drink"),
    ("gustar", ["me gusta", "gusta"], "使喜欢（me gusta = 我喜欢）", "to like"),
    ("¿cuántos?", ["cuántos"], "多少个？", "how many?"),
    ("amigo", ["amigos", "amigo"], "朋友", "friend"),
    ("estudiante", ["estudiantes"], "学生", "student"),
    ("alto", ["altos"], "高的；个子高", "tall"),
    ("China", ["China"], "中国", "China"),
    ("Juan", ["Juan"], "胡安（人名）", "Juan (name)"),
    ("María", ["María"], "玛丽亚（人名）", "María (name)"),
]


def _shuffled(options: list[str], *seed: object) -> list[str]:
    digest = hashlib.sha256(":".join(str(part) for part in (ASSIGNMENT_ID, *seed)).encode("utf-8")).hexdigest()
    shuffled = list(options)
    random.Random(int(digest, 16)).shuffle(shuffled)
    return shuffled


def _slug(word: str) -> str:
    folded = unicodedata.normalize("NFD", word.lower())
    return "".join(ch for ch in folded if ch.isascii() and ch.isalnum())


def _with_bare_variants(answers: list[str]) -> list[str]:
    """The checker strips ? and . but not ¿ / ¡, so also accept answers typed without them."""
    out: list[str] = []
    for answer in answers:
        for variant in (answer, answer.replace("¿", "").replace("¡", "")):
            if variant not in out:
                out.append(variant)
    return out


def _choice_item(prefix: str, number: int, prompt: str, options: list[str], answer: str,
                 translation: str, note: str = "") -> dict:
    item = {
        "id": f"{prefix}-{number:02d}",
        "number": number,
        "prompt": prompt,
        "options": _shuffled(options, prefix, number),
        "answers": [answer],
        "canonicalAnswer": answer,
        "sentenceTranslations": {answer: translation},
    }
    if note:
        item["ambiguityNote"] = "提示：" + note
    return item


def build_assignment() -> dict:
    question_items = [
        _choice_item("int-qw", number, prompt, options, answer, translation, note)
        for number, (prompt, options, answer, translation, note) in enumerate(QUESTION_WORDS, start=1)
    ]
    why_items = [
        _choice_item("int-why", number, prompt, list(WHY_FOR_OPTIONS), answer, translation, note)
        for number, (prompt, answer, translation, note) in enumerate(WHY_FOR, start=1)
    ]
    ser_estar_items = [
        _choice_item("int-se", number, prompt, options, answer, translation, note)
        for number, (prompt, options, answer, translation, note) in enumerate(SER_ESTAR, start=1)
    ]
    conjugation_items = []
    for number, (prompt, verb, person, translation) in enumerate(CONJUGATION, start=1):
        form = (SER if verb == "ser" else ESTAR)[person]
        conjugation_items.append({
            "id": f"int-conj-{number:02d}",
            "number": number,
            "person": PERSONS[person],
            "verb": verb,
            "prompt": prompt,
            "answers": [form],
            "canonicalAnswer": form,
            "sentenceTranslations": {form: translation},
        })
    translate_items = [
        {
            "id": f"int-tr-{number:02d}",
            "number": number,
            "prompt": prompt,
            "answers": _with_bare_variants(answers),
            "canonicalAnswer": answers[0],
        }
        for number, (prompt, answers) in enumerate(TRANSLATE, start=1)
    ]
    for items in (question_items, why_items, ser_estar_items, conjugation_items):
        for item in items:
            assert item["prompt"].count(BLANK) == 1, item["id"]
            assert "options" not in item or item["answers"][0] in item["options"], item["id"]

    return {
        "id": ASSIGNMENT_ID,
        "title": "疑问词 + Ser / Estar 练习 A1",
        "badge": "新练习",
        "sourceTitle": "Práctica: palabras interrogativas, ser y estar",
        "level": "A1",
        "answerKeyBasis": "standard_grammar",
        "sentenceLexicon": [
            {
                "id": "int-lx-" + _slug(word),
                "word": word,
                "forms": forms,
                "gloss": gloss,
                "english": english,
            }
            for word, forms, gloss, english in SENTENCE_LEXICON
        ],
        "referenceTables": [
            {
                "id": "int-ser-reference",
                "verb": "ser",
                "title": "Ser：what? 名字、特征、国籍、宗教（较“永久”）",
                "rows": [{"person": person, "form": form} for person, form in zip(PERSONS, SER)],
            },
            {
                "id": "int-estar-reference",
                "verb": "estar",
                "title": "Estar：how? where? 心情、状态、位置（较“暂时”）",
                "rows": [{"person": person, "form": form} for person, form in zip(PERSONS, ESTAR)],
            },
        ],
        "sections": [
            {
                "id": "int-question-words",
                "title": "Parte 1 - Elige la palabra interrogativa",
                "instructions": "看回答，选出合适的疑问词：qué 什么 · quién 谁 · cuál 哪个 · cómo 怎样 · "
                                "cuándo 什么时候 · dónde 哪里 · cuántos 多少。",
                "type": "single_choice",
                "items": question_items,
            },
            {
                "id": "int-por-que",
                "title": "Parte 2 - ¿Por qué?, porque, ¿para qué? o para",
                "instructions": "¿por qué? 问原因 → porque…（因为）；¿para qué? 问目的 → para + 动词原形（为了）。",
                "type": "single_choice",
                "items": why_items,
            },
            {
                "id": "int-ser-estar",
                "title": "Parte 3 - ¿Ser o estar?",
                "instructions": "Ser：名字、特征、国籍；Estar：心情、状态、位置。选出正确的形式。",
                "type": "single_choice",
                "items": ser_estar_items,
            },
            {
                "id": "int-conjugation",
                "title": "Parte 4 - Conjuga ser y estar",
                "instructions": "写出括号里动词的正确现在时形式。",
                "type": "text_input",
                "items": conjugation_items,
            },
            {
                "id": "int-translate",
                "title": "Parte 5 - Traduce al español",
                "instructions": "把中文翻译成西班牙语。问号 ¿? 可写可不写；忘了重音会提示“很接近”。",
                "type": "text_input",
                "items": translate_items,
            },
        ],
    }


def upsert(homework_path: Path, assignment: dict) -> None:
    data = json.loads(homework_path.read_text(encoding="utf-8"))
    assignments = data.get("assignments", [])
    for index, item in enumerate(assignments):
        if item.get("id") == assignment["id"]:
            assignments[index] = assignment
            break
    else:
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
