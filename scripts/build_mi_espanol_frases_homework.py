#!/usr/bin/env python3
"""Build the sentence-building assignment ``frases-a1-01``.

Upserts one assignment into ``examples/mi-espanol/homework.json``:

  1. 连词成句      text_input + wordTiles: tap the chunks in order
  2. 完整句回答    text_input: answer a question with a whole sentence
  3. 整句中译西    text_input: translate a sentence that mixes ser and estar
  4. 小对话        multi_input: fill three gaps in a short A/B dialogue
  5. 写一写        open_response: free writing, compared with a model answer

Everything reuses the learner's class notes (question words, ser / estar,
porque / para, como) and words already in vocab.csv. Typed answers also accept
text written without ¿ / ¡; an answer that keeps the meaning but drops words
is scored "意思表达对了" through ``meaningPatterns`` instead of "wrong".
"""

from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
HOMEWORK = ROOT / "examples" / "mi-espanol" / "homework.json"
ASSIGNMENT_ID = "frases-a1-01"
GAP = "______"

# (chunks shown in this order, accepted answers, translation)
ORDER = [
    (["español", "porque", "estudio", "me gusta"],
     ["Estudio español porque me gusta."], "我学西班牙语，因为我喜欢。"),
    (["el baño", "está", "dónde"],
     ["¿Dónde está el baño?"], "洗手间在哪里？"),
    (["bien", "mi padre", "está"],
     ["Mi padre está bien."], "我父亲很好。"),
    (["pequeño", "es", "mi perro"],
     ["Mi perro es pequeño."], "我的狗很小。"),
    (["perros", "cuántos", "tienes"],
     ["¿Cuántos perros tienes?"], "你有几只狗？"),
    (["viajar a España", "estudio", "para", "español"],
     ["Estudio español para viajar a España."], "我学西班牙语是为了去西班牙旅行。"),
    (["en casa", "nosotros", "estamos"],
     ["Nosotros estamos en casa."], "我们在家。"),
    (["es", "el azul", "mi color favorito"],
     ["Mi color favorito es el azul.", "El azul es mi color favorito."], "我最喜欢的颜色是蓝色。"),
    (["como tú", "quiero", "ser"],
     ["Quiero ser como tú."], "我想成为像你一样的人。"),
    (["no puedo beber", "no tengo agua", "como"],
     ["Como no tengo agua, no puedo beber."], "因为我没有水，所以我不能喝。"),
]

# (question, cue in Chinese, accepted answers, translation, meaning terms, note)
ANSWER = [
    ("¿Cómo te llamas?", "用 Ana 回答",
     ["Me llamo Ana.", "Yo me llamo Ana.", "Soy Ana.", "Yo soy Ana."],
     "我叫 Ana。", ["ana"], ""),
    ("¿Qué estudias?", "你学西班牙语",
     ["Estudio español.", "Yo estudio español."],
     "我学西班牙语。", ["español"], ""),
    ("¿Dónde estás?", "你在家",
     ["Estoy en casa.", "Yo estoy en casa."],
     "我在家。", {"all": ["casa"], "none": ["soy"]}, "位置用 estar：estoy en…"),
    ("¿Cómo estás?", "你很好",
     ["Estoy bien.", "Estoy muy bien.", "Yo estoy bien.", "Yo estoy muy bien."],
     "我很好。", {"all": ["bien"], "none": ["soy"]}, "状态用 estar：estoy bien。"),
    ("¿Cómo es tu perro?", "小而且白",
     ["Mi perro es pequeño y blanco.", "Es pequeño y blanco."],
     "我的狗又小又白。", {"all": ["pequeño", "blanco"], "none": ["está"]}, "特征用 ser：es pequeño。"),
    ("¿Cuándo vienes a casa?", "星期一",
     ["Vengo a casa el lunes.", "Vengo el lunes.", "El lunes vengo a casa.", "Voy a casa el lunes."],
     "我星期一来家里。", ["lunes"], "只回答 El lunes 也能听懂；这里练习说整句：Vengo a casa el lunes."),
    ("¿Por qué estudias español?", "因为我喜欢",
     ["Estudio español porque me gusta.", "Porque me gusta."],
     "因为我喜欢。", ["gusta"], "回答原因用 porque。"),
    ("¿Para qué estudias español?", "为了去西班牙旅行",
     ["Estudio español para viajar a España.", "Para viajar a España."],
     "为了去西班牙旅行。", ["viajar"], "回答目的用 para + 动词原形。"),
    ("¿Cuántos perros tienes?", "两只",
     ["Tengo dos perros.", "Yo tengo dos perros."],
     "我有两只狗。", ["dos"], ""),
    ("¿De dónde eres?", "中国",
     ["Soy de China.", "Yo soy de China."],
     "我来自中国。", {"all": ["china"], "none": ["estoy"]}, "来源、国籍用 ser：soy de…"),
]

# (dialogue with GAP markers, [(label, accepted, canonical)], translation)
DIALOGUE = [
    (f"A: ¿Cómo {GAP} llamas?　B: Me {GAP} Juan.　A: ¿De dónde {GAP}?　B: Soy de España.",
     [("A 第 1 空", ["te"]), ("B 第 2 空", ["llamo"]), ("A 第 3 空", ["eres"])],
     "A：你叫什么名字？ B：我叫 Juan。 A：你是哪里人？ B：我来自西班牙。"),
    (f"A: ¿Cómo {GAP} tu hermano?　B: {GAP} cansado.　A: ¿Dónde {GAP} ahora?　B: Está en casa.",
     [("A 第 1 空", ["está"]), ("B 第 2 空", ["Está"]), ("A 第 3 空", ["está"])],
     "A：你兄弟怎么样？ B：他累了。 A：他现在在哪儿？ B：他在家。"),
    (f"A: ¿{GAP} estudias español?　B: {GAP} me gusta.　A: ¿Y {GAP} qué?　B: Para viajar a España.",
     [("A 第 1 空", ["Por qué"]), ("B 第 2 空", ["Porque"]), ("A 第 3 空", ["para"])],
     "A：你为什么学西班牙语？ B：因为我喜欢。 A：那是为了什么？ B：为了去西班牙旅行。"),
    (f"A: ¿Cómo {GAP} tu perro?　B: {GAP} pequeño y muy bonito.　A: ¿Cuántos perros {GAP}?　B: Tengo un perro.",
     [("A 第 1 空", ["es"]), ("B 第 2 空", ["Es"]), ("A 第 3 空", ["tienes"])],
     "A：你的狗是什么样的？ B：它很小，非常漂亮。 A：你有几只狗？ B：我有一只狗。"),
]

# (Chinese, accepted answers, meaning terms, note)
TRANSLATE = [
    ("我叫 Ana，我是中国人。（Ana 是女生）",
     ["Me llamo Ana y soy china.", "Me llamo Ana, soy china.", "Me llamo Ana y soy de China.",
      "Me llamo Ana, soy de China.", "Soy Ana y soy china.", "Soy Ana y soy de China."],
     {"all": ["ana", "china"], "none": ["estoy"]}, "国籍用 ser；女生用 china，男生用 chino。"),
    ("我今天很累。",
     ["Hoy estoy cansado.", "Hoy estoy cansada.", "Estoy cansado hoy.", "Estoy cansada hoy.",
      "Hoy estoy muy cansado.", "Hoy estoy muy cansada.", "Estoy muy cansado hoy.", "Estoy muy cansada hoy."],
     {"any": ["cansado", "cansada"], "none": ["soy"]}, "今天的状态用 estar。"),
    ("我的狗很小，而且（现在）很开心。",
     ["Mi perro es pequeño y está contento.", "Mi perro es pequeño y está feliz.",
      "Mi perro es pequeño y está muy contento.", "Mi perro es pequeño y ahora está contento.",
      "Mi perro es muy pequeño y está contento.", "Mi perro es muy pequeño y está muy contento.",
      "Mi perro es pequeño y está muy feliz.", "Mi perro es pequeño y ahora está feliz.",
      "Mi perro es pequeño y ahora está muy contento.", "Mi perro es pequeño y ahora está muy feliz."],
     {"all": ["perro", "es pequeño"], "any": ["está contento", "está feliz", "está muy contento", "está muy feliz"]}, "pequeño 是特征 → es；开心是现在的心情 → está。一句话里两个都用。"),
    ("洗手间在右边。",
     ["El baño está a la derecha."], {"all": ["baño", "está", "derecha"]}, "位置用 estar。"),
    ("我学西班牙语，因为我想去西班牙旅行。",
     ["Estudio español porque quiero viajar a España.", "Yo estudio español porque quiero viajar a España."],
     ["porque", "viajar"], ""),
    ("你在哪儿？我在家。",
     ["¿Dónde estás? Estoy en casa.", "¿Dónde estás tú? Estoy en casa.", "¿Dónde estás? Yo estoy en casa."],
     ["dónde", "casa"], ""),
    ("我的父亲是老师，他现在很好。",
     ["Mi padre es profesor y ahora está bien.", "Mi padre es profesor y está bien.",
      "Mi padre es profesor y ahora está muy bien.", "Mi padre es profesor. Ahora está bien.",
      "Mi padre es profesor y está bien ahora."],
     {"all": ["es profesor", "está bien"]}, "职业用 ser（es profesor），状态用 estar（está bien）。"),
    ("因为我没有水，所以我不能喝。",
     ["Como no tengo agua, no puedo beber.", "No puedo beber porque no tengo agua."],
     ["agua", "beber"], "como 放在句首表示“因为”；也可以说 …porque no tengo agua。"),
]

# (task, model answer, translation)
WRITE = [
    ("用 3 句话介绍你自己：叫什么、从哪里来、今天在哪里 / 心情怎么样。",
     "Me llamo Ana. Soy de China. Hoy estoy en casa y estoy muy contenta.",
     "我叫 Ana。我来自中国。今天我在家，我很开心。"),
    ("用两个不同的疑问词问同学两个问题，再替他回答。",
     "¿Cómo te llamas? Me llamo Juan. ¿Dónde estás? Estoy en casa.",
     "你叫什么名字？我叫 Juan。你在哪儿？我在家。"),
    ("介绍你的一位家人或宠物：他 / 它是什么样的（ser），现在怎么样（estar）。",
     "Mi perro es pequeño y blanco. Hoy está muy contento.",
     "我的狗又小又白。它今天很开心。"),
]

# Words in the answer sentences that vocab.csv only lists in another form.
SENTENCE_LEXICON = [
    ("estudiar", ["estudio", "estudias"], "学习", "to study"),
    ("llamarse", ["te llamas", "me llamo", "llamas", "llamo"], "叫（名字）", "to be called"),
    ("tener", ["tienes", "tengo"], "有", "to have"),
    ("venir", ["vengo", "vienes"], "来", "to come"),
    ("ir", ["voy"], "去", "to go"),
    ("querer", ["quiero"], "想要", "to want"),
    ("poder", ["puedo"], "能、可以", "can"),
    ("gustar", ["me gusta", "gusta"], "使喜欢（me gusta = 我喜欢）", "to like"),
    ("¿cuántos?", ["cuántos"], "多少个？", "how many?"),
    ("dos", ["dos"], "二、两个", "two"),
    ("chino / china", ["china", "chino"], "中国人；中国的", "Chinese"),
    ("China", ["China"], "中国", "China"),
    ("Ana", ["Ana"], "安娜（人名）", "Ana (name)"),
    ("Juan", ["Juan"], "胡安（人名）", "Juan (name)"),
]


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


def _meaning(terms: list[str] | dict) -> list[dict]:
    """A plain list means "all of these words"; a dict is passed through (all / any / none)."""
    if isinstance(terms, dict):
        return [terms]
    return [{"all": terms}] if terms else []


def build_assignment() -> dict:
    order_items = [
        {
            "id": f"fr-order-{number:02d}",
            "number": number,
            "prompt": "排成句子：" + translation,
            "wordTiles": chunks,
            "answers": _with_bare_variants(answers),
            "canonicalAnswer": answers[0],
            "answerTranslation": translation,
            "ambiguityNote": "翻译：" + translation,
        }
        for number, (chunks, answers, translation) in enumerate(ORDER, start=1)
    ]
    answer_items = []
    for number, (question, cue, answers, translation, terms, note) in enumerate(ANSWER, start=1):
        item = {
            "id": f"fr-answer-{number:02d}",
            "number": number,
            "prompt": f"{question}（{cue}，写完整句子）",
            "answers": _with_bare_variants(answers),
            "canonicalAnswer": answers[0],
            "answerTranslation": translation,
            "meaningPatterns": _meaning(terms),
            "polishNote": "意思对了；练习说完整句子：" + answers[0],
        }
        if note:
            item["ambiguityNote"] = "提示：" + note
        answer_items.append(item)
    dialogue_items = []
    for number, (prompt, blanks, translation) in enumerate(DIALOGUE, start=1):
        assert prompt.count(GAP) == len(blanks), number
        dialogue_items.append({
            "id": f"fr-dialogue-{number:02d}",
            "number": number,
            "prompt": prompt,
            "blanks": [
                {
                    "id": f"fr-dialogue-{number:02d}-{index}",
                    "label": label,
                    "answers": answers,
                    "canonicalAnswer": answers[0],
                }
                for index, (label, answers) in enumerate(blanks, start=1)
            ],
            "ambiguityNote": "翻译：" + translation,
        })
    translate_items = []
    for number, (chinese, answers, terms, note) in enumerate(TRANSLATE, start=1):
        item = {
            "id": f"fr-translate-{number:02d}",
            "number": number,
            "prompt": chinese,
            "answers": _with_bare_variants(answers),
            "canonicalAnswer": answers[0],
            "meaningPatterns": _meaning(terms),
            "polishNote": "意思基本对了；参考说法：" + answers[0],
        }
        if note:
            item["ambiguityNote"] = "提示：" + note
        translate_items.append(item)
    write_items = [
        {
            "id": f"fr-write-{number:02d}",
            "number": number,
            "prompt": task,
            "answerMode": "self_review",
            "answers": [model],
            "canonicalAnswer": model,
            "answerTranslation": translation,
        }
        for number, (task, model, translation) in enumerate(WRITE, start=1)
    ]

    return {
        "id": ASSIGNMENT_ID,
        "title": "成句练习 A1 - 1：疑问词与 Ser / Estar",
        "badge": "成句练习",
        "sourceTitle": "Práctica de frases: preguntas, ser y estar",
        "level": "A1",
        "answerKeyBasis": "standard_grammar",
        "sentenceLexicon": [
            {
                "id": "fr-lx-" + _slug(word),
                "word": word,
                "forms": forms,
                "gloss": gloss,
                "english": english,
            }
            for word, forms, gloss, english in SENTENCE_LEXICON
        ],
        "sections": [
            {
                "id": "fr-order",
                "title": "Parte 1 - Ordena la frase",
                "instructions": "看中文意思，按顺序点词块拼成句子。点错了，点上面已选的词块就能撤回。",
                "type": "text_input",
                "items": order_items,
            },
            {
                "id": "fr-answer",
                "title": "Parte 2 - Responde con una frase completa",
                "instructions": "按括号里的提示，用完整句子回答。只写一个词也能看懂，但会提示你说整句。",
                "type": "text_input",
                "items": answer_items,
            },
            {
                "id": "fr-translate",
                "title": "Parte 3 - Traduce la frase",
                "instructions": "把整句翻译成西班牙语。注意一句话里 ser 和 estar 可能都要用。",
                "type": "text_input",
                "items": translate_items,
            },
            {
                "id": "fr-dialogue",
                "title": "Parte 4 - Completa el diálogo",
                "instructions": "每段小对话有 3 个空，按顺序填写。",
                "type": "multi_input",
                "items": dialogue_items,
            },
            {
                "id": "fr-write",
                "title": "Parte 5 - Escribe sobre ti",
                "instructions": "自由写作，不自动判分。写完后对照参考作答，自己检查 ser / estar 和疑问词。",
                "type": "open_response",
                "items": write_items,
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
