#!/usr/bin/env python3
"""Build the preposition assignment ``preposiciones-a-en-a1``.

Upserts one assignment into ``examples/mi-espanol/homework.json``:

  1. ¿a, al o en?        single_choice: 去哪儿 / 在哪儿 / 几点 / 给谁
  2. ¿al o a la? ¿del?   single_choice: a + el → al, de + el → del
  3. el, al, a o en      single_choice: mix, incl. el lunes and jugar al fútbol
  4. 连词成句             text_input + wordTiles, with decoy prepositions
  5. 中译西               text_input

Original sentences written for the learner's question about el / al / a / en;
the answer key is standard grammar.
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
ASSIGNMENT_ID = "preposiciones-a-en-a1"
BLANK = "_______"

OPTION_NOTES = {
    "a": ("介词：去往（有移动）/ 给某人 / 在几点 / 人当宾语", "to / at (time)"),
    "al": ("a + el 的缩合，后面是阳性单数名词", "to the (a + el)"),
    "en": ("介词：在…里 / 上（静止）；乘（交通）；在（月份、年份）", "in / on / at / by"),
    "el": ("阳性单数定冠词（the）；星期几前也用 el", "the (masculine)"),
    "a la": ("a + la：阴性不合并", "to the (feminine)"),
    "a el": ("✗ 错误形式：a + el 必须合并成 al", "✗ must be al"),
    "del": ("de + el 的缩合：…的 / 从…", "of / from the (de + el)"),
    "de la": ("de + la：阴性不合并", "of / from the (feminine)"),
    "de el": ("✗ 错误形式：de + el 必须合并成 del", "✗ must be del"),
}

# (prompt, answer, translation, note)
A_AL_EN = [
    ("Voy _______ Madrid mañana.", "a", "我明天去马德里。", "去某地（有移动）用 a；城市名前没有冠词，所以不是 al。"),
    ("Vivo _______ Madrid.", "en", "我住在马德里。", "住在哪里是静止的位置，用 en。"),
    ("Voy _______ cine con mis amigos.", "al", "我和朋友们去电影院。", "去 + el cine → a + el = al。"),
    ("Estoy _______ el cine.", "en", "我在电影院。", "“在”某处用 en；en 不和 el 合并，所以是 en el。"),
    ("Mis padres van _______ la playa.", "a", "我父母去海滩。", "后面已经有 la，a + la 不合并。"),
    ("Comemos _______ casa.", "en", "我们在家吃饭。", "在家：en casa（casa 前不加冠词）。"),
    ("Vuelvo _______ casa a las seis.", "a", "我六点回家。", "回家有移动：a casa。"),
    ("La clase empieza _______ las nueve.", "a", "课九点开始。", "几点钟用 a：a las nueve。"),
    ("Viajo _______ tren.", "en", "我坐火车旅行。", "交通工具用 en：en tren, en coche, en avión。"),
    ("Veo _______ mi hermana.", "a", "我看见我姐姐。", "宾语是人时要加 a（personal a）。"),
    ("Llamo _______ médico.", "al", "我给医生打电话。", "宾语是人（el médico）→ a + el = al。"),
    ("Mi cumpleaños es _______ marzo.", "en", "我的生日在三月。", "月份、年份、季节前用 en。"),
    ("Voy _______ comer ahora.", "a", "我现在要去吃饭。", "ir a + 动词原形：要去做某事。"),
    ("El libro está _______ la mesa.", "en", "书在桌子上。", "在…上面也用 en。"),
    ("Llego _______ aeropuerto a las diez.", "al", "我十点到机场。", "llegar a（到达）+ el aeropuerto → al。"),
    ("Hablo _______ español con mi profesora.", "en", "我和老师说西班牙语。", "用某种语言说：en español。"),
    ("Escribo un mensaje _______ profesor.", "al", "我给老师写一条消息。", "给某人：a + el profesor → al。"),
    ("Trabajo _______ un hospital.", "en", "我在一家医院工作。", "在某处工作（静止）用 en。"),
]

# (prompt, options, answer, translation, note)
CONTRACTIONS = [
    ("Vamos _______ parque.", ["al", "a la", "a el"], "al", "我们去公园。", "parque 是阳性（el parque）→ al。"),
    ("Vamos _______ escuela.", ["al", "a la", "a el"], "a la", "我们去学校。", "escuela 是阴性（la escuela）→ a la，不合并。"),
    ("Voy _______ mercado.", ["al", "a la", "a el"], "al", "我去市场。", "el mercado → al。"),
    ("Voy _______ biblioteca.", ["al", "a la", "a el"], "a la", "我去图书馆。", "la biblioteca → a la。"),
    ("Vamos _______ restaurante.", ["al", "a la", "a el"], "al", "我们去餐馆。", "el restaurante → al。"),
    ("Vengo _______ trabajo.", ["del", "de la", "de el"], "del", "我下班回来（从工作的地方来）。", "de + el trabajo → del。"),
    ("Salgo _______ oficina a las cinco.", ["del", "de la", "de el"], "de la", "我五点离开办公室。", "la oficina → de la，不合并。"),
    ("Es el coche _______ profesor.", ["del", "de la", "de el"], "del", "这是老师的车。", "…的：de + el profesor → del。"),
    ("Es la casa _______ abuela.", ["del", "de la", "de el"], "de la", "这是奶奶的房子。", "la abuela → de la。"),
]

# (prompt, answer, translation, note)
MIX = [
    ("Me gusta _______ fútbol.", "el", "我喜欢足球。", "这里不需要介词，只要冠词 el（喜欢的东西前加冠词）。"),
    ("Juego _______ fútbol los sábados.", "al", "我每周六踢足球。", "jugar a + 运动 → a + el fútbol = al。"),
    ("Veo _______ partido en la tele.", "el", "我在电视上看比赛。", "宾语是东西，不加 personal a，只要冠词 el。"),
    ("Veo _______ profesor en la calle.", "al", "我在街上看到老师。", "宾语是人 → a + el profesor = al。"),
    ("Estoy _______ el parque.", "en", "我在公园。", "在哪儿用 en（en el，不合并）。"),
    ("Voy _______ parque.", "al", "我去公园。", "去哪儿：a + el parque = al。"),
    ("Abro _______ libro.", "el", "我打开书。", "东西当宾语，只要冠词 el。"),
    ("Vivo _______ España.", "en", "我住在西班牙。", "国家名前没有冠词：en España。"),
    ("Los domingos voy _______ Barcelona.", "a", "每个星期天我去巴塞罗那。", "城市名前没有冠词，所以是 a，不是 al。"),
    ("Tengo clase _______ lunes.", "el", "我星期一有课。", "星期几前用 el（el lunes），不用 en。"),
    ("Pregunto _______ camarero.", "al", "我问服务员。", "问某人：a + el camarero = al。"),
    ("Tomo _______ autobús.", "el", "我坐公交车。", "tomar（搭乘）后面直接接 el autobús；比较 voy en autobús。"),
]
MIX_OPTIONS = ["el", "al", "a", "en"]

# (chunks in order, extra decoy tiles, accepted answers, translation)
ORDER = [
    (["Voy", "al", "cine", "con", "Ana"], ["en", "el"], ["Voy al cine con Ana."], "我和 Ana 去电影院。"),
    (["Estamos", "en", "la", "playa"], ["a", "al"], ["Estamos en la playa."], "我们在海滩。"),
    (["Mi", "hermano", "trabaja", "en", "un", "hospital"], ["a", "al"], ["Mi hermano trabaja en un hospital."], "我哥哥在医院工作。"),
    (["Vuelvo", "a", "casa", "a", "las", "siete"], ["en", "al"], ["Vuelvo a casa a las siete."], "我七点回家。"),
    (["Llamo", "al", "médico"], ["a", "el", "en"], ["Llamo al médico."], "我给医生打电话。"),
    (["Viajamos", "a", "Japón", "en", "avión"], ["al", "de"], ["Viajamos a Japón en avión.", "Viajamos en avión a Japón."], "我们坐飞机去日本。"),
    (["Tengo", "clase", "el", "lunes"], ["en", "al"], ["Tengo clase el lunes.", "El lunes tengo clase."], "我星期一有课。"),
    (["Juego", "al", "fútbol", "en", "el", "parque"], ["a", "del"], ["Juego al fútbol en el parque.", "En el parque juego al fútbol."], "我在公园踢足球。"),
]

# (Chinese prompt, accepted Spanish answers, first one canonical)
TRANSLATE = [
    ("我去学校。", ["Voy a la escuela.", "Yo voy a la escuela.", "Voy al colegio.", "Yo voy al colegio."]),
    ("我在学校。", ["Estoy en la escuela.", "Yo estoy en la escuela.", "Estoy en el colegio.", "Yo estoy en el colegio."]),
    ("我们去公园。", ["Vamos al parque.", "Nosotros vamos al parque.", "Nosotras vamos al parque."]),
    ("她住在马德里。", ["Vive en Madrid.", "Ella vive en Madrid."]),
    ("我坐火车去。", ["Voy en tren.", "Yo voy en tren."]),
    ("课八点开始。", ["La clase empieza a las ocho.", "La clase comienza a las ocho."]),
    ("我给医生打电话。", ["Llamo al médico.", "Yo llamo al médico."]),
    ("我星期一有课。", ["Tengo clase el lunes.", "El lunes tengo clase.", "Yo tengo clase el lunes."]),
]

LESSON_NOTES = [
    {
        "title": "先分清：el 是冠词，al 是缩合",
        "points": [
            "el = 阳性单数定冠词（the），不是介词：el libro, el cine。",
            "a + el 必须合并成 al；de + el 必须合并成 del。没有 “a el / de el” 这种写法。",
            "只有 el 会合并：a la, a los, a las, de la 都不合并。",
            "城市、国家名前没有冠词，所以 voy a Madrid（不是 al）。",
        ],
        "examples": [
            {"text": "Voy al cine.", "translation": "我去电影院。（a + el cine）"},
            {"text": "Voy a la playa.", "translation": "我去海滩。（a + la 不合并）"},
        ],
    },
    {
        "title": "a：往哪儿去、给谁、几点",
        "points": [
            "去某地（有移动）：ir a, llegar a, volver a。",
            "给某人 / 对某人：escribo a, llamo a, pregunto a。",
            "宾语是人要加 a（personal a）：veo a Ana；宾语是东西就不加：veo el partido。",
            "几点：a las ocho。ir a + 动词原形：voy a comer（我要去吃）。",
        ],
        "examples": [
            {"text": "Vuelvo a casa a las seis.", "translation": "我六点回家。"},
            {"text": "Veo a mi hermana.", "translation": "我看见我姐姐。"},
        ],
    },
    {
        "title": "en：在哪儿（静止）、乘什么、什么时候",
        "points": [
            "在…里 / 上：estoy en casa, el libro está en la mesa。",
            "交通工具：en tren, en coche, en avión。",
            "月份、年份、季节：en marzo, en 2026, en verano。语言：en español。",
            "判断：ir / llegar / volver 等移动动词 → a；estar / vivir / trabajar 等静止动词 → en。",
        ],
        "examples": [
            {"text": "Voy a la escuela.", "translation": "我去学校。（移动 → a）"},
            {"text": "Estoy en la escuela.", "translation": "我在学校。（静止 → en）"},
        ],
    },
    {
        "title": "容易错的几个点",
        "points": [
            "星期几用 el，不用 en：el lunes tengo clase。",
            "jugar a + 运动：juego al fútbol。",
            "casa 表示“自己家”时不加冠词：a casa, en casa。",
        ],
        "examples": [
            {"text": "Tengo clase el lunes.", "translation": "我星期一有课。"},
            {"text": "Juego al fútbol.", "translation": "我踢足球。"},
        ],
    },
]

# Words in the answer sentences that vocab.csv lists only in another form.
SENTENCE_LEXICON = [
    ("ir", ["voy", "vamos", "van"], "去", "to go"),
    ("vivir", ["vivo"], "住；生活", "to live"),
    ("comer", ["comemos"], "吃", "to eat"),
    ("volver", ["vuelvo"], "回来；回去", "to return"),
    ("empezar", ["empieza"], "开始", "to start"),
    ("viajar", ["viajo"], "旅行", "to travel"),
    ("ver", ["veo"], "看；看见", "to see"),
    ("llamar", ["llamo"], "打电话；叫", "to call"),
    ("llegar", ["llego"], "到达", "to arrive"),
    ("hablar", ["hablo"], "说（语言）", "to speak"),
    ("escribir", ["escribo"], "写", "to write"),
    ("venir", ["vengo"], "来", "to come"),
    ("salir", ["salgo"], "出去；离开", "to go out / leave"),
    ("gustar", ["me gusta", "gusta"], "使喜欢（me gusta = 我喜欢）", "to like"),
    ("jugar", ["juego"], "玩；踢（球）", "to play"),
    ("preguntar", ["pregunto"], "问", "to ask"),
    ("tomar", ["tomo"], "搭乘；拿", "to take"),
    ("amigo", ["amigos"], "朋友", "friend"),
    ("el cumpleaños", ["cumpleaños"], "生日", "birthday"),
    ("el partido", ["partido"], "比赛", "match / game"),
    ("el camarero", ["camarero"], "服务员", "waiter"),
    ("domingo", ["domingos"], "星期天（los domingos = 每个星期天）", "Sunday"),
    ("sábado", ["sábados"], "星期六（los sábados = 每个星期六）", "Saturday"),
    ("Madrid", ["Madrid"], "马德里", "Madrid"),
    ("Barcelona", ["Barcelona"], "巴塞罗那", "Barcelona"),
]


def _seed(*parts: object) -> int:
    digest = hashlib.sha256(":".join(str(p) for p in (ASSIGNMENT_ID, *parts)).encode("utf-8")).hexdigest()
    return int(digest, 16)


def _shuffled(options: list[str], *seed: object) -> list[str]:
    out = list(options)
    random.Random(_seed(*seed)).shuffle(out)
    return out


def _slug(word: str) -> str:
    folded = unicodedata.normalize("NFD", word.lower())
    return "".join(ch for ch in folded if ch.isascii() and ch.isalnum())


def _with_bare_variants(answers: list[str]) -> list[str]:
    out: list[str] = []
    for answer in answers:
        for variant in (answer, answer.replace("¿", "").replace("¡", "")):
            if variant not in out:
                out.append(variant)
    return out


def _option_notes(options: list[str]) -> dict:
    return {option: {"gloss": OPTION_NOTES[option][0], "english": OPTION_NOTES[option][1]} for option in options}


def _choice(prefix: str, number: int, prompt: str, options: list[str], answer: str,
            translation: str, note: str) -> dict:
    assert prompt.count(BLANK) == 1 and answer in options, (prefix, number)
    sentence = prompt.replace(BLANK, answer)
    return {
        "id": f"{prefix}-{number:02d}",
        "number": number,
        "prompt": prompt,
        "options": _shuffled(options, prefix, number),
        "answers": [answer],
        "canonicalAnswer": answer,
        "sentenceTranslations": {answer: translation},
        "answerTranslation": translation,
        "optionNotes": _option_notes(options),
        "ambiguityNote": f"完整句：{sentence}　提示：{note}",
    }


def _tiles(number: int, chunks: list[str], decoys: list[str]) -> list[str]:
    tiles = chunks + decoys
    rng = random.Random(_seed("order", number))
    rng.shuffle(tiles)
    while tiles[:len(chunks)] == chunks:
        rng.shuffle(tiles)
    return tiles


def build_assignment() -> dict:
    sections = [
        {
            "id": "prep-a-al-en",
            "title": "Parte 1 - ¿a, al o en?",
            "instructions": "有移动（去哪儿、给谁、几点）→ a；后面是 el 时 a + el = al；静止（在哪儿、乘什么、几月）→ en。",
            "type": "single_choice",
            "items": [_choice("prep-ae", n, p, ["a", "al", "en"], a, t, note)
                      for n, (p, a, t, note) in enumerate(A_AL_EN, start=1)],
        },
        {
            "id": "prep-contractions",
            "title": "Parte 2 - ¿al o a la? ¿del o de la?",
            "instructions": "只有 el 会和 a / de 合并：a + el = al，de + el = del；la 不合并。",
            "type": "single_choice",
            "items": [_choice("prep-con", n, p, o, a, t, note)
                      for n, (p, o, a, t, note) in enumerate(CONTRACTIONS, start=1)],
        },
        {
            "id": "prep-mix",
            "title": "Parte 3 - ¿el, al, a o en?",
            "instructions": "混合练习：有时只需要冠词 el，有时需要介词。注意 el lunes、jugar al fútbol。",
            "type": "single_choice",
            "items": [_choice("prep-mix", n, p, MIX_OPTIONS, a, t, note)
                      for n, (p, a, t, note) in enumerate(MIX, start=1)],
        },
        {
            "id": "prep-order",
            "title": "Parte 4 - Ordena la frase",
            "instructions": "按顺序点词组成句子。里面混了多余的介词，别全部用上。",
            "type": "text_input",
            "items": [
                {
                    "id": f"prep-order-{n:02d}",
                    "number": n,
                    "prompt": "排成句子：" + translation,
                    "wordTiles": _tiles(n, chunks, decoys),
                    "answers": _with_bare_variants(answers),
                    "canonicalAnswer": answers[0],
                    "answerTranslation": translation,
                    "ambiguityNote": "翻译：" + translation,
                }
                for n, (chunks, decoys, answers, translation) in enumerate(ORDER, start=1)
            ],
        },
        {
            "id": "prep-translate",
            "title": "Parte 5 - Traduce al español",
            "instructions": "把中文翻译成西班牙语，注意用 a / al / en。忘了重音会提示“很接近”。",
            "type": "text_input",
            "items": [
                {
                    "id": f"prep-tr-{n:02d}",
                    "number": n,
                    "prompt": prompt,
                    "answers": _with_bare_variants(answers),
                    "canonicalAnswer": answers[0],
                    "answerTranslation": prompt,
                }
                for n, (prompt, answers) in enumerate(TRANSLATE, start=1)
            ],
        },
    ]
    assignment = {
        "id": ASSIGNMENT_ID,
        "title": "介词 a / al / en（和 el）练习 A1",
        "badge": "新练习",
        "sourceTitle": "Práctica: a, al, en y el",
        "level": "A1",
        "answerKeyBasis": "standard_grammar",
        "lessonNotes": LESSON_NOTES,
        "lessonNotesHeading": "先读笔记：a / al / en / el 的区别",
        "sections": sections,
    }
    if SENTENCE_LEXICON:
        assignment["sentenceLexicon"] = [
            {"id": "prep-lx-" + _slug(word), "word": word, "forms": forms, "gloss": gloss, "english": english}
            for word, forms, gloss, english in SENTENCE_LEXICON
        ]
    return assignment


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
