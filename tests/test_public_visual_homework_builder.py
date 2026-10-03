"""Public (CC0 photo) A0 visual homework assembled from the vocab-images manifest."""

import json
import pytest

from scripts.build_mi_espanol_public_visual_homework import build_assignment


def _manifest():
    entries = []
    words = [
        ("la tortuga", "turtle", "Animales", [1]), ("el perro", "dog", "Animales", [2]),
        ("el gato", "cat", "Animales", [3]), ("el caballo", "horse", "Animales", [4]),
        ("el cerdo", "pig", "Animales", [5]), ("el pez", "fish", "Animales", [11, 209]),
        ("el fútbol", "soccer", "Deportes", [57]), ("el tenis", "tennis", "Deportes", [66]),
        ("el golf", "golf", "Deportes", [70]), ("el boxeo", "boxing", "Deportes", [60]),
        ("el yoga", "yoga", "Deportes", [77]),
    ]
    for spanish, english, category, numbers in words:
        entries.append({
            "spanish": spanish, "english": english, "category": category, "numbers": numbers,
            "query": english, "selected": "id-" + english,
            "candidates": [{"id": "id-" + english, "title": english, "url": "https://x/" + english + ".jpg",
                            "thumbnail": "", "landing": "https://x/" + english, "creator": "Someone",
                            "license": "cc0", "licenseVersion": "1.0",
                            "licenseUrl": "https://creativecommons.org/publicdomain/zero/1.0/",
                            "source": "flickr", "width": 800, "height": 600}],
            "image": {"file": f"images/{numbers[0]:03d}-{english}.jpg", "sha256": "ab" * 32,
                      "bytes": 1000, "candidateId": "id-" + english},
        })
    # one entry the reviewer rejected (no usable picture) and one never searched
    entries.append({"spanish": "la niebla", "english": "fog", "category": "El tiempo", "numbers": [179],
                    "query": "fog", "selected": None, "candidates": [], "image": None})
    return {"version": 1, "provider": "openverse", "licenses": ["cc0", "pdm"], "entries": entries}


def test_build_assignment_uses_only_entries_with_images():
    assignment = build_assignment(_manifest())
    assert assignment["id"] == "vocabulario-a0-visual"
    assert assignment["localOnly"] is False
    assert assignment["contentOrigin"] == "adapted_public"
    assert len(assignment["images"]) == 11
    for image in assignment["images"].values():
        assert image["deliver"] == "file"
        assert image["file"].startswith("assets/vocab-images/images/")
        assert image["license"] in {"cc0", "pdm"}
        assert image["sourceUrl"] and image["landing"]
    choice, typed, image_choice = assignment["sections"]
    assert [s["type"] for s in (choice, typed, image_choice)] == ["single_choice", "text_input", "single_choice"]
    assert len(choice["items"]) == len(typed["items"]) == len(image_choice["items"]) == 11
    assert not any("niebla" in json.dumps(section, ensure_ascii=False) for section in assignment["sections"])


def test_choice_items_have_four_spanish_options_from_the_same_category():
    assignment = build_assignment(_manifest())
    for item in assignment["sections"][0]["items"]:
        assert len(item["options"]) == len(set(item["options"])) == 4
        assert item["answers"] == [item["spanish"]]
        assert item["answerLanguage"] == "es"
        assert item["imageId"] in assignment["images"]
        assert "localOnlyGrading" not in item


def test_typed_items_accept_the_noun_without_its_article():
    assignment = build_assignment(_manifest())
    tortuga = next(i for i in assignment["sections"][1]["items"] if i["spanish"] == "la tortuga")
    assert tortuga["answers"] == ["la tortuga", "tortuga"]
    assert tortuga["canonicalAnswer"] == "la tortuga"
    assert tortuga["answerLanguage"] == "es"


def test_image_choice_items_offer_three_pictures_including_the_right_one():
    assignment = build_assignment(_manifest())
    for item in assignment["sections"][2]["items"]:
        assert len(item["imageOptions"]) == 3
        assert [o["value"] for o in item["imageOptions"]] == item["options"]
        assert item["spanish"] in item["options"]
        assert item["answers"] == [item["spanish"]]


def test_assignment_is_deterministic():
    assert build_assignment(_manifest()) == build_assignment(_manifest())


def test_curated_replacement_preserves_questions_and_credits():
    original = build_assignment(_manifest())
    replacement = {
        "reviewed": True, "file": "assets/vocab-images/curated/001-turtle.png",
        "sha256": "cd" * 32, "license": "Icons8 free with link attribution",
        "licenseUrl": "https://icons8.com/license", "creator": "Icons8",
        "sourceUrl": "https://img.icons8.com/color/100/turtle.png",
        "landing": "https://icons8.com/icons/set/turtle", "provider": "Icons8",
        "creditUrl": "https://icons8.com/", "presentation": "icon",
    }
    curated = {"images": {"vocab-a0-001": replacement}}
    updated = build_assignment(_manifest(), curated)
    assert updated["id"] == original["id"]
    assert updated["sections"] == original["sections"]
    assert updated["images"]["vocab-a0-001"] == {**replacement, "deliver": "file"}
    assert updated["images"]["vocab-a0-002"] == original["images"]["vocab-a0-002"]
    assert "CC0" not in updated["source"]["license"]
    replacement["reviewed"] = False
    with pytest.raises(ValueError, match="unreviewed"):
        build_assignment(_manifest(), curated)


def test_curated_unknown_image_is_rejected():
    with pytest.raises(ValueError, match="unknown curated image"):
        build_assignment(_manifest(), {"images": {"typo": {"reviewed": True}}})
