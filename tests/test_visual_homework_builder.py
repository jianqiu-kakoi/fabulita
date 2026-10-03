"""Unit tests for scripts/build_mi_espanol_visual_homework.py section assembly."""

from scripts.build_mi_espanol_visual_homework import _assignment


def _entries():
    animals = [
        ("la tortuga", "turtle"), ("el perro", "dog"), ("el gato", "cat"),
        ("el caballo", "horse"), ("el cerdo", "pig"),
    ]
    sports = [
        ("el fútbol", "soccer"), ("el tenis", "tennis"), ("el golf", "golf"),
        ("el boxeo", "boxing"), ("el yoga", "yoga"),
    ]
    entries = []
    for number, (spanish, english) in enumerate(animals + sports, start=1):
        entries.append({
            "number": number,
            "sourcePage": 2,
            "category": "Animales" if number <= 5 else "Deportes",
            "spanish": spanish,
            "english": english,
            "imageId": f"vocab-a0-{number:03d}",
        })
    return entries


def _registry(entries):
    return {e["imageId"]: {"file": f"x/{e['number']}.jpg", "sha256": "0" * 64,
                           "filename": f"{e['number']}.jpg"} for e in entries}


def test_assignment_has_image_to_spanish_four_choice_section():
    entries = _entries()
    assignment = _assignment(entries, _registry(entries), "a" * 64)

    spanish_section, write_section, _english_choice = assignment["sections"]
    assert spanish_section["id"] == "vocab-a0-image-to-spanish"
    assert spanish_section["type"] == "single_choice"
    assert len(spanish_section["items"]) == len(entries)

    write_by_number = {item["number"]: item for item in write_section["items"]}
    for item in spanish_section["items"]:
        entry = entries[item["number"] - 1]
        assert item["imageId"] == write_by_number[item["number"]]["imageId"]
        assert "imageOptions" not in item
        assert len(item["options"]) == len(set(item["options"])) == 4
        assert entry["spanish"] in item["options"]
        assert item["answers"] == [entry["spanish"]]
        assert item["canonicalAnswer"] == entry["spanish"]
        assert item["answerLanguage"] == "es"
        assert item["localOnlyGrading"] is True
        same_category = {e["spanish"] for e in entries if e["category"] == entry["category"]}
        assert set(item["options"]) <= same_category


def test_image_to_spanish_options_are_deterministic():
    entries = _entries()
    first = _assignment(entries, _registry(entries), "a" * 64)["sections"][0]["items"]
    second = _assignment(entries, _registry(entries), "a" * 64)["sections"][0]["items"]
    assert [item["options"] for item in first] == [item["options"] for item in second]
    assert any(item["options"][0] != entries[item["number"] - 1]["spanish"] for item in first)
