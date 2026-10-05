import hashlib
import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MI_ESPANOL = REPO / "examples" / "mi-espanol"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, REPO / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


topic_builder = _load("build_mi_espanol_topic_visual_homework")
conjugation_builder = _load("build_mi_espanol_conjugation_homework")


def _topics():
    return json.loads(
        (MI_ESPANOL / "assets" / "vocab-images" / "a1-topics.json").read_text(encoding="utf-8")
    )["topics"]


def _homework():
    data = json.loads((MI_ESPANOL / "homework.json").read_text(encoding="utf-8"))
    return {assignment["id"]: assignment for assignment in data["assignments"]}


def test_every_topic_has_one_committed_assignment_matching_the_builder():
    homework = _homework()
    for topic in _topics():
        assignment = topic_builder.build_assignment(topic)
        assert homework[assignment["id"]] == assignment
        assert assignment["badge"] == topic["title"]
        assert [len(section["items"]) for section in assignment["sections"]] == [len(topic["entries"])] * 3


def test_topic_questions_stay_inside_their_topic_and_include_the_answer():
    for topic in _topics():
        words = {entry["spanish"] for entry in topic["entries"]}
        choice, typed, picture = topic_builder.build_assignment(topic)["sections"]
        for item in choice["items"]:
            assert len(set(item["options"])) == 4 and set(item["options"]) <= words
            assert item["answers"][0] in item["options"]
        for item in picture["items"]:
            assert len({option["imageId"] for option in item["imageOptions"]}) == 3
            assert item["answers"][0] in item["options"]
        for item in typed["items"]:
            assert item["spanish"] in item["answers"]


def test_typed_answers_accept_bare_noun_and_adjective_gender():
    topics = {topic["id"]: topic for topic in _topics()}
    typed = {
        item["spanish"]: item["answers"]
        for topic_id in ("comida", "colores")
        for item in topic_builder.build_assignment(topics[topic_id])["sections"][1]["items"]
    }
    assert typed["el agua"] == ["el agua", "agua"]
    assert typed["rojo"] == ["rojo", "roja"]


def test_topic_images_are_reviewed_licensed_files():
    licenses = {
        "Icons8": ("Icons8 free with link attribution", "https://icons8.com/license"),
        "Mi Español": ("CC0-1.0", "https://creativecommons.org/publicdomain/zero/1.0/"),
    }
    for topic in _topics():
        for image_id, image in topic_builder.build_assignment(topic)["images"].items():
            assert image["deliver"] == "file" and image["reviewed"] is True, image_id
            assert (image["license"], image["licenseUrl"]) == licenses[image["provider"]], image_id
            path = MI_ESPANOL / image["file"]
            assert hashlib.sha256(path.read_bytes()).hexdigest() == image["sha256"], image_id


def test_conjugation_assignment_is_committed_and_correct():
    assignment = conjugation_builder.build_assignment()
    assert _homework()["presente-verbos-a1"] == assignment
    assert conjugation_builder.conjugate("tener") == ["tengo", "tienes", "tiene", "tenemos", "tenéis", "tienen"]
    assert conjugation_builder.conjugate("salir") == ["salgo", "sales", "sale", "salimos", "salís", "salen"]
    assert conjugation_builder.conjugate("hablar") == ["hablo", "hablas", "habla", "hablamos", "habláis", "hablan"]
    assert conjugation_builder.conjugate("comer") == ["como", "comes", "come", "comemos", "coméis", "comen"]
    assert conjugation_builder.conjugate("vivir") == ["vivo", "vives", "vive", "vivimos", "vivís", "viven"]
    choice, tener, salir, regular = assignment["sections"]
    assert len(choice["items"]) == 24 and len(tener["items"]) == 6
    assert len(salir["items"]) == 6 and len(regular["items"]) == 36
    for item in choice["items"]:
        assert len(set(item["options"])) == 4 and item["answers"][0] in item["options"]
        assert set(item["options"]) <= set(conjugation_builder.conjugate(item["verb"]))
    ids = [item["id"] for section in assignment["sections"] for item in section["items"]]
    assert len(ids) == len(set(ids)) == 72


interrogativos_builder = _load("build_mi_espanol_interrogativos_homework")


def test_interrogativos_assignment_is_committed_and_correct():
    assignment = interrogativos_builder.build_assignment()
    assert _homework()["interrogativos-ser-estar-a1"] == assignment
    question_words, why_for, ser_estar, conjugation, translate = assignment["sections"]
    assert [len(section["items"]) for section in assignment["sections"]] == [10, 6, 11, 12, 10]
    for section in (question_words, why_for, ser_estar):
        for item in section["items"]:
            assert item["prompt"].count("_______") == 1
            assert item["answers"][0] in item["options"]
            assert len(set(item["options"])) == len(item["options"])
    assert [item["answers"] for item in conjugation["items"]] == [
        ["soy"], ["eres"], ["es"], ["somos"], ["sois"], ["son"],
        ["estoy"], ["estás"], ["está"], ["estamos"], ["estáis"], ["están"],
    ]
    first = translate["items"][0]
    assert first["canonicalAnswer"] == "¿Cómo te llamas?"
    assert "Cómo te llamas?" in first["answers"]
    ids = [item["id"] for section in assignment["sections"] for item in section["items"]]
    assert len(ids) == len(set(ids))


frases_builder = _load("build_mi_espanol_frases_homework")


def test_frases_assignment_is_committed_and_well_formed():
    assignment = frases_builder.build_assignment()
    assert _homework()["frases-a1-01"] == assignment
    # Sections of one type stay contiguous: the page groups questions by type.
    order, answer, translate, dialogue, write = assignment["sections"]
    assert [section["type"] for section in assignment["sections"]] == [
        "text_input", "text_input", "text_input", "multi_input", "open_response",
    ]
    assert [len(section["items"]) for section in assignment["sections"]] == [10, 10, 8, 4, 3]
    for item in dialogue["items"]:
        assert item["prompt"].count("______") == len(item["blanks"]) == 3
    for section in (order, answer, translate):
        for item in section["items"]:
            assert item["canonicalAnswer"] in item["answers"]
            bare = item["canonicalAnswer"].replace("¿", "")
            assert bare in item["answers"]
    for item in write["items"]:
        assert item["answerMode"] == "self_review" and item["answers"]
    for item in order["items"]:
        # Tapping every tile in the right order must rebuild an accepted answer.
        assert item["id"].startswith("fr-order-") and len(item["wordTiles"]) >= 3
        joined = " ".join(item["wordTiles"]).lower()
        assert sorted(joined.split()) == sorted(item["canonicalAnswer"].lower().replace(",", "").replace(".", "").replace("¿", "").replace("?", "").split())
    ids = [item["id"] for section in assignment["sections"] for item in section["items"]]
    assert len(ids) == len(set(ids))


regulares_builder = _load("build_mi_espanol_regulares_homework")


def test_regular_verb_sentences_are_committed_and_correct():
    assignment = regulares_builder.build_assignment()
    assert _homework()["verbos-regulares-frases-a1-a2"] == assignment
    assert regulares_builder.conjugate("recibir") == ["recibo", "recibes", "recibe", "recibimos", "recibís", "reciben"]
    assert regulares_builder.conjugate("leer") == ["leo", "lees", "lee", "leemos", "leéis", "leen"]
    items = [item for section in assignment["sections"] for item in section["items"]]
    assert len(items) == 90 and [item["number"] for item in items] == list(range(1, 91))
    expected = {"vr-01": "recibo", "vr-02": "cedéis", "vr-07": "visita", "vr-17": "beben",
                "vr-51": "toséis", "vr-81": "abren", "vr-90": "viven"}
    by_id = {item["id"]: item for item in items}
    for item_id, form in expected.items():
        assert by_id[item_id]["answers"] == [form]
    assert {section["type"] for section in assignment["sections"]} == {"single_choice"}
    for item in items:
        assert item["prompt"].count("_______") == 1 and item["prompt"].endswith(f"({item['verb']})")
        assert len(item["options"]) == len(set(item["options"])) == 4
        assert item["answers"][0] in item["options"]
        assert set(item["options"]) <= set(regulares_builder.conjugate(item["verb"]))
    positions = [item["options"].index(item["answers"][0]) for item in items]
    assert len(set(positions)) == 4


def test_regular_verb_order_assignment_is_committed_and_well_formed():
    assignment = regulares_builder.build_order_assignment()
    assert _homework()["verbos-regulares-ordenar-a1-a2"] == assignment
    items = [item for section in assignment["sections"] for item in section["items"]]
    assert len(items) == 90 and len({item["id"] for item in items}) == 90
    for item in items:
        chunks, full = regulares_builder.sentence_tiles(item["number"])
        assert sorted(item["wordTiles"]) == sorted(chunks) and item["wordTiles"] != chunks
        assert item["answers"][0] == item["canonicalAnswer"] == full
        assert " ".join(chunks).lower() == full.rstrip(".").replace(",", "").lower()
        assert item["prompt"] == "排成句子：" + item["answerTranslation"]
    by_id = {item["id"]: item for item in items}
    assert by_id["vo-01"]["answers"] == ["Yo recibo una carta de mi madre."]
    assert by_id["vo-04"]["answers"] == [
        "Tú corres en el parque por la mañana.", "Tú corres por la mañana en el parque.",
    ]


def test_new_picture_topics_cover_verbs_and_everyday_words():
    topics = {topic["id"]: topic for topic in _topics()}
    assert {"acciones", "cosas", "comida-2", "lugares-2", "personas-2"} <= set(topics)
    verbs = {entry["spanish"] for entry in topics["acciones"]["entries"]}
    assert {"correr", "nadar", "leer", "escribir", "dormir"} <= verbs and len(verbs) == 38



preposiciones_builder = _load("build_mi_espanol_preposiciones_homework")


def test_preposition_assignment_is_committed_and_correct():
    assignment = preposiciones_builder.build_assignment()
    assert _homework()["preposiciones-a-en-a1"] == assignment
    a_al_en, contractions, mix, order, translate = assignment["sections"]
    assert [section["type"] for section in assignment["sections"]] == [
        "single_choice", "single_choice", "single_choice", "text_input", "text_input",
    ]
    assert [len(section["items"]) for section in assignment["sections"]] == [18, 9, 12, 8, 8]
    by_id = {item["id"]: item for section in assignment["sections"] for item in section["items"]}
    assert len(by_id) == 55
    expected = {"prep-ae-01": "a", "prep-ae-02": "en", "prep-ae-03": "al", "prep-ae-04": "en",
                "prep-con-02": "a la", "prep-con-06": "del", "prep-mix-02": "al", "prep-mix-10": "el"}
    for item_id, answer in expected.items():
        assert by_id[item_id]["answers"] == [answer]
    for section in (a_al_en, contractions, mix):
        for item in section["items"]:
            assert item["prompt"].count("_______") == 1
            assert item["answers"][0] in item["options"]
            assert set(item["optionNotes"]) == set(item["options"])
            for option in item["answers"]:
                assert not item["optionNotes"][option]["gloss"].startswith("✗")
    for item in contractions["items"]:
        wrong = {"a el", "de el"} & set(item["options"])
        assert len(wrong) == 1 and item["optionNotes"][wrong.pop()]["gloss"].startswith("✗")
    for item in order["items"]:
        tiles = list(item["wordTiles"])
        words = item["canonicalAnswer"].rstrip(".").split()
        for word in words:
            tiles.remove(word)
        assert tiles, "each ordering item keeps at least one decoy tile"
    assert "Voy a la escuela." in translate["items"][0]["answers"]
