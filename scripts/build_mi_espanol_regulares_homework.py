#!/usr/bin/env python3
"""Build the regular-verb sentence assignment ``verbos-regulares-frases-a1-a2``.

Upserts one assignment into ``examples/mi-espanol/homework.json``: 90 single_choice
sentences, each with one blank for a regular -ar / -er / -ir verb in the present
indicative, -ar / -er / -ir mixed as in class.

The verb + person of every item follows the learner's private worksheet
``ejercicio_verbos_regulares_A1_A2``, whose infinitives are already in
vocab.csv. The worksheet sentences themselves are NOT copied: every sentence
here was written for Mi Español. The answer key is the standard conjugation.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PROJECT = ROOT / "examples" / "mi-espanol"
HOMEWORK = PROJECT / "homework.json"
ASSIGNMENT_ID = "verbos-regulares-frases-a1-a2"
BLANK = "_______"
PERSONS = {
    "yo": 0, "tú": 1, "él": 2, "ella": 2, "usted": 2,
    "nosotros": 3, "nosotras": 3, "vosotros": 4, "vosotras": 4,
    "ellos": 5, "ellas": 5, "ustedes": 5,
}
ENDINGS = {
    "ar": ["o", "as", "a", "amos", "áis", "an"],
    "er": ["o", "es", "e", "emos", "éis", "en"],
    "ir": ["o", "es", "e", "imos", "ís", "en"],
}
MODELS = {"ar": ("hablar", "说话"), "er": ("comer", "吃"), "ir": ("vivir", "居住、生活")}
TABLE_PERSONS = [
    "yo", "tú", "él / ella / usted",
    "nosotros / nosotras", "vosotros / vosotras", "ellos / ellas / ustedes",
]

# (subject, sentence after the subject with BLANK, verb, translation)
SENTENCES = [
    ("Yo", "_______ una carta de mi madre.", "recibir", "我收到妈妈的一封信。"),
    ("Vosotras", "_______ el turno a los niños.", "ceder", "你们把顺序让给孩子们。"),
    ("Él", "_______ pan y fruta en la cocina.", "desayunar", "他在厨房吃面包和水果当早餐。"),
    ("Tú", "_______ en el parque por la mañana.", "correr", "你早上在公园跑步。"),
    ("Nosotros", "_______ las piezas del juego.", "unir", "我们把游戏的零件拼在一起。"),
    ("Ellas", "_______ pescado los viernes.", "cenar", "她们每周五晚饭吃鱼。"),
    ("Usted", "_______ el museo con su familia.", "visitar", "您和家人参观博物馆。"),
    ("Yo", "_______ arroz con verduras.", "comer", "我吃米饭配蔬菜。"),
    ("Vosotros", "_______ una palabra en la frase.", "omitir", "你们在句子里漏掉了一个词。"),
    ("Ella", "_______ en tren a Valencia.", "viajar", "她坐火车去瓦伦西亚。"),
    ("Tú", "_______ el piso con dos amigos.", "compartir", "你和两个朋友合住一套公寓。"),
    ("Ellos", "_______ fruta en la calle.", "vender", "他们在街上卖水果。"),
    ("Nosotros", "_______ un mapa de la ciudad.", "necesitar", "我们需要一张城市地图。"),
    ("Ella", "_______ a los perros grandes.", "temer", "她害怕大狗。"),
    ("Yo", "_______ mi nombre en el cuaderno.", "escribir", "我在本子上写我的名字。"),
    ("Tú", "_______ las fotos del viaje.", "mirar", "你看旅行的照片。"),
    ("Ustedes", "_______ agua fría en verano.", "beber", "你们（您各位）夏天喝冰水。"),
    ("Ella", "_______ una tienda nueva en el barrio.", "descubrir", "她在街区发现了一家新店。"),
    ("Vosotros", "_______ el piano en casa.", "practicar", "你们在家练钢琴。"),
    ("Yo", "_______ el periódico en el tren.", "leer", "我在火车上看报纸。"),
    ("Nosotras", "_______ sal a la sopa.", "añadir", "我们往汤里加盐。"),
    ("Ellos", "_______ en el sofá el domingo.", "descansar", "他们星期天在沙发上休息。"),
    ("Tú", "_______ estudiar más para el examen.", "deber", "你应该为考试多学习。"),
    ("Ella", "_______ un mensaje a su amiga.", "escribir", "她给朋友写一条消息。"),
    ("Yo", "_______ a la escuela con mi hermano.", "caminar", "我和哥哥（弟弟）走路去学校。"),
    ("Nosotros", "_______ un cuento a los niños.", "leer", "我们给孩子们读一个故事。"),
    ("Tú", "_______ el color de la camisa.", "decidir", "你决定衬衫的颜色。"),
    ("Ellas", "_______ en clase a las nueve.", "entrar", "她们九点进教室。"),
    ("Usted", "_______ la pizza en ocho trozos.", "dividir", "您把披萨分成八块。"),
    ("Él", "_______ un vaso en la cocina.", "romper", "他在厨房打碎了一个杯子。"),
    ("Yo", "_______ español todos los días.", "estudiar", "我每天学西班牙语。"),
    ("Vosotras", "_______ los libros en la clase.", "repartir", "你们在班上分发书。"),
    ("Tú", "_______ en tus amigos.", "creer", "你相信你的朋友们。"),
    ("Nosotros", "_______ a la profesora.", "ayudar", "我们帮助老师。"),
    ("Ellos", "_______ a la página web con su contraseña.", "acceder", "他们用密码登录网站。"),
    ("Yo", "_______ la puerta de la casa.", "abrir", "我打开家门。"),
    ("Vosotras", "_______ en el mar en verano.", "nadar", "你们夏天在海里游泳。"),
    ("Nosotros", "_______ en casa de mis abuelos.", "comer", "我们在我祖父母家吃饭。"),
    ("Ella", "_______ mucho con el frío.", "sufrir", "她很怕冷（冷的时候很难受）。"),
    ("Tú", "_______ la radio en el coche.", "escuchar", "你在车里听收音机。"),
    ("Ellos", "_______ a la montaña en verano.", "subir", "他们夏天爬山。"),
    ("Nosotras", "_______ un vestido para la fiesta.", "coser", "我们为聚会缝一条裙子。"),
    ("Él", "_______ los platos después de cenar.", "lavar", "他晚饭后洗碗。"),
    ("Tú", "_______ la pregunta del profesor.", "comprender", "你理解老师的问题。"),
    ("Nosotros", "_______ que es un problema.", "admitir", "我们承认这是个问题。"),
    ("Ustedes", "_______ el precio en la tienda.", "preguntar", "你们（您各位）在店里问价格。"),
    ("Yo", "_______ mi bicicleta vieja.", "vender", "我卖掉我的旧自行车。"),
    ("Vosotras", "_______ la cama con una manta.", "cubrir", "你们用毯子盖住床。"),
    ("Nosotros", "_______ a nuestros amigos en la estación.", "esperar", "我们在车站等朋友。"),
    ("Él", "_______ su ciudad en la clase.", "describir", "他在课上描述他的城市。"),
    ("Vosotros", "_______ porque estáis resfriados.", "toser", "你们咳嗽，因为你们感冒了。"),
    ("Tú", "_______ la cena para tu familia.", "cocinar", "你为家人做晚饭。"),
    ("Nosotros", "_______ del autobús para ir al trabajo.", "depender", "我们上班要靠公交车。"),
    ("Ellas", "_______ en el teatro.", "aplaudir", "她们在剧院里鼓掌。"),
    ("Yo", "_______ con mi madre por teléfono.", "hablar", "我和妈妈打电话。"),
    ("Usted", "_______ volver mañana.", "prometer", "您答应明天回来。"),
    ("Tú", "_______ a la clase de yoga los lunes.", "asistir", "你每周一去上瑜伽课。"),
    ("Vosotros", "_______ la comida a la playa.", "llevar", "你们把吃的带到海滩。"),
    ("Nosotras", "_______ a mamá con un regalo.", "sorprender", "我们用一份礼物给妈妈惊喜。"),
    ("Yo", "_______ al tercer piso a pie.", "subir", "我走楼梯上三楼。"),
    ("Ellos", "_______ las preguntas del examen.", "contestar", "他们回答考试的题目。"),
    ("Tú", "_______ al teléfono.", "responder", "你接电话。"),
    ("Ella", "_______ el problema con su jefe.", "discutir", "她和老板讨论这个问题。"),
    ("Yo", "_______ pan en la panadería.", "comprar", "我在面包店买面包。"),
    ("Vosotros", "_______ al parque por esta puerta.", "acceder", "你们从这扇门进入公园。"),
    ("Tú", "_______ a tu perro dormir en el sofá.", "permitir", "你允许你的狗在沙发上睡觉。"),
    ("Nosotras", "_______ la comida para la fiesta.", "preparar", "我们为聚会准备食物。"),
    ("Ellas", "_______ inglés en la universidad.", "aprender", "她们在大学学英语。"),
    ("Él", "_______ diez años mañana.", "cumplir", "他明天满十岁。"),
    ("Vosotros", "_______ un mapa en la pizarra.", "dibujar", "你们在黑板上画一张地图。"),
    ("Nosotras", "_______ una casa en el campo.", "poseer", "我们在乡下有一栋房子。"),
    ("Yo", "_______ en Madrid con mi familia.", "vivir", "我和家人住在马德里。"),
    ("Tú", "_______ muy bien en las fiestas.", "bailar", "你在聚会上跳舞跳得很好。"),
    ("Vosotros", "_______ pocos errores en el examen.", "cometer", "你们考试中犯的错误很少。"),
    ("Nosotras", "_______ en ayudar a la abuela.", "insistir", "我们坚持要帮奶奶。"),
    ("Ella", "_______ los libros en la estantería.", "ordenar", "她把书在书架上整理好。"),
    ("Vosotras", "_______ la ciudad en bicicleta.", "recorrer", "你们骑自行车游览城市。"),
    ("Ellos", "_______ mucha agua en verano.", "consumir", "他们夏天用很多水。"),
    ("Vosotras", "_______ café con leche por la mañana.", "tomar", "你们早上喝牛奶咖啡。"),
    ("Nosotras", "_______ el chocolate de los niños.", "esconder", "我们把孩子们的巧克力藏起来。"),
    ("Ustedes", "_______ la tienda a las diez.", "abrir", "你们（您各位）十点开店。"),
    ("Yo", "_______ en un hospital.", "trabajar", "我在一家医院工作。"),
    ("Él", "_______ la terraza los domingos.", "barrer", "他每周日扫露台。"),
    ("Vosotros", "_______ el pastel para todos.", "partir", "你们把蛋糕切开分给大家。"),
    ("Tú", "_______ en el coro de la escuela.", "cantar", "你在学校合唱团唱歌。"),
    ("Ella", "_______ la ropa en la maleta.", "meter", "她把衣服放进行李箱。"),
    ("Nosotras", "_______ las fotos del viaje.", "imprimir", "我们打印旅行的照片。"),
    ("Yo", "_______ un vaso de leche antes de dormir.", "beber", "我睡前喝一杯牛奶。"),
    ("Nosotros", "_______ el móvil para hacer fotos.", "usar", "我们用手机拍照。"),
    ("Ellos", "_______ cerca de la playa.", "vivir", "他们住在海滩附近。"),
]

# Content words in the sentences that vocab.csv lacks or lists in another form.
EXTRA_LEXICON = [
    ("el turno", ["turno"], "轮次、顺序", "turn"),
    ("la pieza", ["piezas"], "零件、块", "piece"),
    ("el juego", ["juego"], "游戏", "game"),
    ("el pescado", ["pescado"], "鱼（食物）", "fish (food)"),
    ("la palabra", ["palabra"], "词、单词", "word"),
    ("la frase", ["frase"], "句子", "sentence"),
    ("el amigo / la amiga", ["amigos", "amiga"], "朋友", "friend"),
    ("el barrio", ["barrio"], "街区", "neighborhood"),
    ("el periódico", ["periódico"], "报纸", "newspaper"),
    ("la sal", ["sal"], "盐", "salt"),
    ("el cuento", ["cuento"], "故事", "story"),
    ("la camisa", ["camisa"], "衬衫", "shirt"),
    ("el trozo", ["trozos"], "块、片", "piece"),
    ("ocho", ["ocho"], "八", "eight"),
    ("diez", ["diez"], "十", "ten"),
    ("tercero / tercer", ["tercer"], "第三", "third"),
    ("la página web", ["página web", "página", "web"], "网站、网页", "web page"),
    ("la contraseña", ["contraseña"], "密码", "password"),
    ("los abuelos", ["abuelos"], "祖父母", "grandparents"),
    ("la radio", ["radio"], "收音机、广播", "radio"),
    ("el vestido", ["vestido"], "连衣裙", "dress"),
    ("el plato", ["platos"], "盘子；碗碟", "plate; dish"),
    ("el precio", ["precio"], "价格", "price"),
    ("la manta", ["manta"], "毯子", "blanket"),
    ("resfriado / resfriada", ["resfriados"], "感冒的", "having a cold"),
    ("volver", ["volver"], "回来", "to come back"),
    ("el yoga", ["yoga"], "瑜伽", "yoga"),
    ("el jefe / la jefa", ["jefe"], "老板、上司", "boss"),
    ("la panadería", ["panadería"], "面包店", "bakery"),
    ("la pizarra", ["pizarra"], "黑板", "blackboard"),
    ("el error", ["errores"], "错误", "mistake"),
    ("poco / poca", ["pocos"], "很少的", "few; little"),
    ("la abuela", ["abuela"], "奶奶、外婆", "grandmother"),
    ("la estantería", ["estantería"], "书架", "bookshelf"),
    ("mucho / mucha", ["mucha", "mucho"], "很多", "a lot of"),
    ("la terraza", ["terraza"], "露台", "terrace"),
    ("el pastel", ["pastel"], "蛋糕", "cake"),
    ("todos / todas", ["todos"], "所有人；大家", "everyone; all"),
    ("el coro", ["coro"], "合唱团", "choir"),
    ("la maleta", ["maleta"], "行李箱", "suitcase"),
    ("hacer fotos", ["hacer fotos", "hacer"], "拍照", "to take photos"),
    ("antes de", ["antes de", "antes"], "在……之前", "before"),
    ("después de", ["después de", "después"], "在……之后", "after"),
    ("cerca de", ["cerca de", "cerca"], "在……附近", "near"),
    ("a pie", ["a pie", "pie"], "步行", "on foot"),
    ("el hermano", ["hermano"], "兄弟", "brother"),
    ("la madre / mamá", ["madre", "mamá"], "妈妈", "mother; mom"),
    ("la carta", ["carta"], "信", "letter"),
    ("el niño / la niña", ["niños"], "孩子", "child"),
    ("la verdura", ["verduras"], "蔬菜", "vegetable"),
    ("Valencia", ["Valencia"], "瓦伦西亚（城市）", "Valencia"),
    ("grande", ["grandes"], "大的", "big"),
    ("el viaje", ["viaje"], "旅行", "trip"),
    ("el piano", ["piano"], "钢琴", "piano"),
    ("el examen", ["examen"], "考试", "exam"),
    ("el mensaje", ["mensaje"], "消息、短信", "message"),
    ("nueve", ["nueve"], "九", "nine"),
    ("la pizza", ["pizza"], "披萨", "pizza"),
    ("el libro", ["libros"], "书", "book"),
    ("la pregunta", ["pregunta", "preguntas"], "问题", "question"),
    ("viejo / vieja", ["vieja"], "旧的；老的", "old"),
    ("el regalo", ["regalo"], "礼物", "gift"),
    ("el inglés", ["inglés"], "英语", "English"),
    ("el año", ["años"], "年；岁", "year"),
    ("el campo", ["campo"], "乡下；田野", "countryside"),
    ("Madrid", ["Madrid"], "马德里（城市）", "Madrid"),
    ("la fiesta", ["fiestas"], "聚会", "party"),
    ("domingo", ["domingos"], "星期日", "Sunday"),
    ("el móvil", ["móvil"], "手机", "mobile phone"),
]


def conjugate(verb: str) -> list[str]:
    return [verb[:-2] + ending for ending in ENDINGS[verb[-2:]]]


def _vocab_glosses() -> dict[str, tuple[str, str]]:
    with open(PROJECT / "vocab.csv", encoding="utf-8") as f:
        return {row["word"]: (row["gloss"], row.get("note") or "") for row in csv.DictReader(f)}


def _sentence_lexicon() -> list[dict]:
    glosses = _vocab_glosses()
    # Every present form, so the meaning panel can gloss each choice option.
    used: dict[str, list[str]] = {}
    for _, _, verb, _ in SENTENCES:
        used.setdefault(verb, conjugate(verb))
    lexicon = [
        {
            "id": f"vr-lx-{verb}",
            "word": verb,
            "forms": forms,
            "gloss": glosses[verb][0],
            "english": glosses[verb][1],
        }
        for verb, forms in used.items()
    ]
    for word, forms, gloss, english in EXTRA_LEXICON:
        slug = "".join(ch for ch in forms[0].lower() if ch.isalnum())
        lexicon.append({"id": f"vr-lx-x-{slug}", "word": word, "forms": forms, "gloss": gloss, "english": english})
    return lexicon


def _study_answers(gloss: str, english: str) -> list[str]:
    answers = []
    for part in re.split(r"[、；;，]", gloss) + re.split(r";", english):
        part = part.strip()
        if part and part not in answers:
            answers.append(part)
            if part.startswith("to "):
                answers.append(part[3:])
    return answers


def _study_words() -> list[dict]:
    """The assignment's own word list: the verbs to conjugate, then the other sentence words."""
    words = []
    for entry in _sentence_lexicon():
        if entry["word"][:1].isupper():
            continue  # place names
        is_verb = not entry["id"].startswith("vr-lx-x-")
        words.append({
            "id": entry["id"].replace("vr-lx-", "vr-sw-", 1),
            "word": entry["word"],
            "gloss": entry["gloss"],
            "english": entry["english"],
            "answers": _study_answers(entry["gloss"], entry["english"]),
            "role": "answer" if is_verb else "context",
        })
    return words


def choice_options(item_id: str, verb: str, form: str) -> list[str]:
    """The answer plus three other present forms of the same verb, in a stable shuffled order."""
    digest = hashlib.sha256(f"{ASSIGNMENT_ID}:{item_id}".encode("utf-8")).hexdigest()
    rng = random.Random(int(digest, 16))
    others = rng.sample([other for other in conjugate(verb) if other != form], 3)
    options = [form, *others]
    rng.shuffle(options)
    return options


def _items(start: int, stop: int) -> list[dict]:
    items = []
    for number in range(start, stop + 1):
        subject, rest, verb, translation = SENTENCES[number - 1]
        assert rest.count(BLANK) == 1, number
        form = conjugate(verb)[PERSONS[subject.lower()]]
        items.append({
            "id": f"vr-{number:02d}",
            "number": number,
            "person": subject.lower(),
            "verb": verb,
            "prompt": f"{subject} {rest} ({verb})",
            "options": choice_options(f"vr-{number:02d}", verb, form),
            "answers": [form],
            "canonicalAnswer": form,
            "sentenceTranslations": {form: translation},
        })
    return items


def build_assignment() -> dict:
    assert len(SENTENCES) == 90
    reference_tables = []
    for ending, (verb, meaning) in MODELS.items():
        reference_tables.append({
            "id": f"vr-{ending}-reference",
            "verb": verb,
            "title": f"-{ending.upper()}（{verb}：{meaning}）：" + " · ".join("-" + e for e in ENDINGS[ending]),
            "rows": [{"person": person, "form": form} for person, form in zip(TABLE_PERSONS, conjugate(verb))],
        })
    sections = []
    for part, (start, stop) in enumerate([(1, 30), (31, 60), (61, 90)], start=1):
        sections.append({
            "id": f"vr-part-{part}",
            "title": f"Parte {part} - Ejercicios {start}–{stop}",
            "instructions": "选出括号里动词正确的现在时形式。-AR、-ER、-IR 动词混在一起：先看主语是谁，再看动词以什么结尾。"
                            "usted 和 él / ella 用同一个形式，ustedes 和 ellos / ellas 用同一个形式。",
            "type": "single_choice",
            "items": _items(start, stop),
        })
    return {
        "id": ASSIGNMENT_ID,
        "title": "规则动词现在时 · 90 句填空 A1–A2",
        "badge": "变位练习",
        "sourceTitle": "Verbos regulares en presente: frases",
        "level": "A1–A2",
        "answerKeyBasis": "standard_conjugation",
        "contentOrigin": "independently_rewritten_private_classroom_adaptation",
        "source": {},
        "referenceTables": reference_tables,
        "sentenceLexicon": _sentence_lexicon(),
        "studyWords": _study_words(),
        "sections": sections,
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
