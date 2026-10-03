"""Pure-logic tests for scripts/fetch_mi_espanol_cc0_images.py."""

from scripts.fetch_mi_espanol_cc0_images import (
    normalize_candidate,
    plan_entries,
    query_for,
)


def _pdf_entries():
    return [
        {"number": 11, "spanish": "el pez", "english": "fish", "category": "Animales"},
        {"number": 82, "spanish": "lunes", "english": "Monday", "category": "Calendario y estaciones"},
        {"number": 89, "spanish": "enero", "english": "January", "category": "Calendario y estaciones"},
        {"number": 101, "spanish": "primavera", "english": "spring", "category": "Calendario y estaciones"},
        {"number": 209, "spanish": "el pez", "english": "fish", "category": "La playa"},
        {"number": 151, "spanish": "el ventilador", "english": "fan", "category": "Electrodomésticos"},
        {"number": 206, "spanish": "el ventilador", "english": "electric fan", "category": "La playa"},
    ]


def test_plan_entries_dedupes_spanish_and_skips_days_and_months():
    planned = plan_entries(_pdf_entries())
    by_spanish = {entry["spanish"]: entry for entry in planned}
    assert list(by_spanish) == ["el pez", "primavera", "el ventilador"]
    assert by_spanish["el pez"]["numbers"] == [11, 209]
    assert by_spanish["el pez"]["category"] == "Animales"
    assert by_spanish["el ventilador"]["numbers"] == [151, 206]
    assert all(entry["candidates"] == [] and entry["selected"] is None for entry in planned)


def test_query_for_uses_overrides_for_ambiguous_glosses():
    assert query_for({"spanish": "el murciélago", "english": "bat"}) == "bat animal"
    assert query_for({"spanish": "la plancha", "english": "iron"}) == "clothes iron"
    assert query_for({"spanish": "la espalda", "english": "back"}) == "human back"
    assert query_for({"spanish": "la manzana", "english": "apple"}) == "apple"


def test_normalize_candidate_keeps_provenance_and_rejects_non_free_licenses():
    result = {
        "id": "abc-123",
        "title": "A toaster",
        "url": "https://live.staticflickr.com/1/2_b.jpg",
        "thumbnail": "https://api.openverse.org/v1/images/abc-123/thumb/",
        "foreign_landing_url": "https://www.flickr.com/photos/x/2",
        "creator": "Someone",
        "license": "cc0",
        "license_version": "1.0",
        "license_url": "https://creativecommons.org/publicdomain/zero/1.0/",
        "source": "flickr",
        "width": 1024,
        "height": 768,
    }
    candidate = normalize_candidate(result)
    assert candidate == {
        "id": "abc-123",
        "title": "A toaster",
        "url": "https://live.staticflickr.com/1/2_b.jpg",
        "thumbnail": "https://api.openverse.org/v1/images/abc-123/thumb/",
        "landing": "https://www.flickr.com/photos/x/2",
        "creator": "Someone",
        "license": "cc0",
        "licenseVersion": "1.0",
        "licenseUrl": "https://creativecommons.org/publicdomain/zero/1.0/",
        "source": "flickr",
        "width": 1024,
        "height": 768,
    }
    assert normalize_candidate({**result, "license": "by"}) is None
    assert normalize_candidate({**result, "license": "pdm"})["license"] == "pdm"
    assert normalize_candidate({**result, "url": ""}) is None


def test_rank_candidates_prefers_photos_whose_title_matches_the_query():
    from scripts.fetch_mi_espanol_cc0_images import rank_candidates

    def cand(id, title, source="flickr", license="cc0", width=1024, height=768):
        return {"id": id, "title": title, "source": source, "license": license, "width": width, "height": height}

    candidates = [
        cand("poster", "If you go chasing rabbits poster", license="pdm", width=357, height=500),
        cand("engraving", "Rabbit engraving from an old book", source="wikimedia"),
        cand("photo", "Rabbit. Explored."),
        cand("stock", "rabbit in grass", source="stocksnap"),
        cand("unrelated", "Sacramento Airport", license="pdm"),
    ]
    ranked = [c["id"] for c in rank_candidates(candidates, "rabbit")]
    assert ranked[0] == "stock"
    assert ranked[1] == "photo"
    assert ranked[-1] in {"poster", "engraving", "unrelated"}
    assert ranked.index("unrelated") > ranked.index("photo")


def test_reselect_only_touches_entries_not_reviewed_by_a_human():
    from scripts.fetch_mi_espanol_cc0_images import reselect_entries

    def cand(id, title, **kw):
        base = {"id": id, "title": title, "source": "flickr", "license": "cc0", "width": 1024, "height": 768}
        base.update(kw)
        return base

    manifest = {"entries": [
        {"spanish": "el conejo", "query": "rabbit", "selected": "bad", "reviewed": False,
         "candidates": [cand("bad", "advertisement poster", license="pdm"), cand("good", "Rabbit photo")],
         "image": {"candidateId": "bad", "file": "x"}},
        {"spanish": "el gato", "query": "cat", "selected": "human", "reviewed": True,
         "candidates": [cand("human", "old drawing"), cand("auto", "cat photo")],
         "image": {"candidateId": "human", "file": "y"}},
    ]}
    changed = reselect_entries(manifest)
    assert changed == ["el conejo"]
    assert manifest["entries"][0]["selected"] == "good" and manifest["entries"][0]["image"] is None
    assert manifest["entries"][1]["selected"] == "human" and manifest["entries"][1]["image"] is not None
