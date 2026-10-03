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
