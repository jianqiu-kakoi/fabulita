import json
from pathlib import Path

import pytest

from fabulita import build, prompts, stories, vocab
from fabulita.project import Project, ProjectError
from fabulita.ui import UI_LANGS, UI_STRINGS

REPO = Path(__file__).parent.parent
DEMO = REPO / "examples" / "es-a1"


@pytest.fixture
def proj(tmp_path):
    p = Project(tmp_path)
    p.init(lang="es", gloss_lang="zh")
    return p


def make_story(**over):
    s = {
        "id": "el-perro",
        "title": "El perro",
        "sentences": [
            {"text": "El perro está en el jardín.", "trans": "狗在花园里。"},
            {"text": "Mira una flor.", "trans": "它看着一朵花。"},
        ],
        "vocab_used": ["perro", "jardín", "flor"],
        "glossary": {"perro": ["狗"], "jardín": ["花园"], "flor": ["花"]},
        "grammar": [],
    }
    s.update(over)
    return s


def write_story(tmp_path, story):
    p = tmp_path / "incoming.json"
    p.write_text(json.dumps(story, ensure_ascii=False), encoding="utf-8")
    return p


def seed_vocab(proj, tmp_path, rows):
    csv = tmp_path / "v.csv"
    csv.write_text("\n".join(rows), encoding="utf-8")
    return vocab.import_file(proj, csv)


def test_vocab_import_and_dedupe(proj, tmp_path):
    added, updated, total = seed_vocab(proj, tmp_path, ["word,gloss", "perro,狗", "flor,花"])
    assert (added, total) == (2, 2)
    added, updated, total = seed_vocab(proj, tmp_path, ["perro,狗狗"])
    assert (added, updated, total) == (0, 1, 2)
    assert proj.vocab[0]["gloss"] == "狗狗"


def test_add_accept_coverage(proj, tmp_path):
    seed_vocab(proj, tmp_path, ["perro,狗", "jardín,花园", "flor,花", "gato,猫"])
    stories.add(proj, write_story(tmp_path, make_story()))
    covered, uncovered = proj.coverage(include_candidates=True)
    assert len(covered) == 3
    assert [w["w"] for w in uncovered] == ["gato"]
    # candidates don't count toward accepted-only coverage
    covered, _ = proj.coverage(include_candidates=False)
    assert len(covered) == 0
    stories.set_status(proj, "el-perro", "accepted")
    covered, _ = proj.coverage(include_candidates=False)
    assert len(covered) == 3


def test_inflection_tolerated_but_missing_word_warned(proj, tmp_path):
    seed_vocab(proj, tmp_path, ["manzana,苹果", "luna,月亮"])
    s = make_story(id="m", title="M",
                   sentences=[{"text": "Elena compra dos manzanas."}],
                   vocab_used=["manzana", "luna"], glossary={})
    errors, warnings = stories.validate(proj, s)
    assert errors == []
    assert len(warnings) == 1 and "luna" in warnings[0]


def test_add_rejects_broken_story(proj, tmp_path):
    with pytest.raises(ProjectError):
        stories.add(proj, write_story(tmp_path, {"id": "x", "title": "X"}))
    with pytest.raises(ProjectError):
        stories.add(proj, write_story(tmp_path, make_story(id="Bad_ID")))


def test_next_prompt_batches_uncovered(proj, tmp_path):
    seed_vocab(proj, tmp_path, [f"palabra{i},词{i}" for i in range(30)])
    prompt, batch = prompts.next_prompt(proj, max_words=20)
    assert len(batch) == 20
    assert "palabra0" in prompt and "vocab_used" in prompt


def test_build_single_file(proj, tmp_path):
    seed_vocab(proj, tmp_path, ["perro,狗", "jardín,花园", "flor,花"])
    stories.add(proj, write_story(tmp_path, make_story()), accept=True)
    out, size, n_stories, n_clips = build.build(proj)
    html = out.read_text(encoding="utf-8")
    assert n_stories == 1 and n_clips == 0
    assert "El perro" in html
    assert "/*__PAYLOAD__*/" not in html
    assert "</script>" in html  # payload escaping didn't break the page
    for lang in UI_LANGS:
        assert UI_STRINGS[lang]["vocabList"] in html


def test_ui_strings_complete():
    keys = set(UI_STRINGS["en"])
    for lang in UI_LANGS:
        assert set(UI_STRINGS[lang]) == keys, f"{lang} missing keys"


def test_demo_stories_validate():
    proj = Project(DEMO)
    csv = DEMO / "vocab.csv"
    if not (DEMO / "vocab.json").exists():
        vocab.import_file(proj, csv)
    all_stories = proj.stories()
    assert len(all_stories) == 6
    for s in all_stories:
        errors, warnings = stories.validate(proj, s)
        assert errors == [], f"{s['id']}: {errors}"
        assert warnings == [], f"{s['id']}: {warnings}"
