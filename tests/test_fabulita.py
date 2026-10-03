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


def test_vocab_import_keeps_optional_learning_metadata(proj, tmp_path):
    seed_vocab(proj, tmp_path, [
        "word,gloss,note,category,kind,example,example_trans,answers,review_mode",
        "la llave,钥匙,key,家居,word,La llave está en la mesa.,钥匙在桌子上。,钥匙|key,meaning",
        "estar,表示位置和当前状态,to be,语法,grammar",
    ])
    assert proj.vocab[0] == {
        "w": "la llave",
        "gloss": "钥匙",
        "note": "key",
        "category": "家居",
        "kind": "word",
        "example": "La llave está en la mesa.",
        "example_trans": "钥匙在桌子上。",
        "answers": "钥匙|key",
        "review_mode": "meaning",
    }
    assert proj.vocab[1]["category"] == "语法"
    assert "example" not in proj.vocab[1]


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
    assert 'var REVIEW_LS = "fabulita.review.v1"' in html
    assert 'data-view="review"' in html
    assert "REVIEW_INTERVALS = [1, 3, 7, 14, 30]" in html
    assert "REVIEW_NEW_LIMIT = 10" in html and "REVIEW_SESSION_LIMIT = 20" in html
    assert "var vocabWords = P.vocab.filter" in html
    assert "if (vocabSeenWords[key]) return false" in html
    assert "var reviewWords = vocabWords.filter(reviewIsEligible)" in html
    assert 'data-review-action="hard"' not in html
    assert 'data-review-action="issue"' in html
    assert '["again", "known"].indexOf(result) === -1' in html
    assert '["again", "hard", "known"].indexOf(event.rating)' in html
    for lang in UI_LANGS:
        assert UI_STRINGS[lang]["vocabList"] in html


def test_ui_strings_complete():
    keys = set(UI_STRINGS["en"])
    for lang in UI_LANGS:
        assert set(UI_STRINGS[lang]) == keys, f"{lang} missing keys"
    for key in ("myBook", "delStory", "delConfirm", "readTab", "reviewTab",
                "reviewReveal", "reviewAnswerLabel", "reviewCheck", "reviewCorrect",
                "reviewIncorrect", "reviewAgain", "reviewHard", "reviewOther", "reviewOtherHint",
                "reviewIssueSaved", "reviewIssueFailed", "reviewKnow", "reviewNoWords"):
        for lang in UI_LANGS:
            assert UI_STRINGS[lang][key], f"{lang} missing {key}"


def test_japanese_substring_validation(proj, tmp_path):
    seed_vocab(proj, tmp_path, ["学生,学生", "映画,电影"])
    s = make_story(id="ja", title="ワタシ",
                   sentences=[{"text": "わたしは学生です。"}],
                   vocab_used=["学生", "映画"], glossary={})
    errors, warnings = stories.validate(proj, s)
    assert errors == []
    assert len(warnings) == 1 and "映画" in warnings[0]


def test_unpack_roundtrip(tmp_path):
    bundle = {
        "fabulita_bundle": 1,
        "config": {"name": "T", "lang": "es", "gloss_lang": "zh"},
        "vocab": [{"w": "perro", "gloss": "狗", "note": "dog",
                   "category": "动物", "kind": "word", "example": "El perro corre.",
                   "example_trans": "狗在跑。", "answers": "狗|犬|dog"}],
        "glossary": {"el": ["定冠词"]},
        "stories": [make_story(status="candidate")],
    }
    bp = tmp_path / "bundle.json"
    bp.write_text(json.dumps(bundle, ensure_ascii=False), encoding="utf-8")
    dest = tmp_path / "proj"
    build.unpack(bp, dest)
    p = Project(dest)
    assert p.config["lang"] == "es"
    assert len(p.vocab) == 1 and len(p.stories()) == 1
    assert p.vocab[0]["category"] == "动物"
    assert p.vocab[0]["example_trans"] == "狗在跑。"
    assert p.vocab[0]["answers"] == "狗|犬|dog"
    assert p.glossary["el"] == ["定冠词"]
    with pytest.raises(ValueError):
        build.unpack(bp, dest)  # refuses to overwrite


def test_studio_build(tmp_path):
    out, size = build.build_studio(tmp_path / "studio.html")
    html = out.read_text(encoding="utf-8")
    assert '/*__READER_TPL_B64__*/""' not in html
    assert "/*__READER_UI__*/null" not in html
    assert UI_STRINGS["ja"]["vocabList"] in html  # reader UI strings embedded


@pytest.mark.parametrize("demo,n", [("es-a1", 6), ("en-a1", 1), ("ja-n5", 1),
                                     ("mi-espanol", 0), ("my-english", 1),
                                     ("my-japanese", 0)])
def test_example_projects_validate(demo, n):
    proj = Project(REPO / "examples" / demo)
    if not (proj.root / "vocab.json").exists():
        vocab.import_file(proj, proj.root / "vocab.csv")
    all_stories = proj.stories()
    assert len(all_stories) == n
    for s in all_stories:
        errors, warnings = stories.validate(proj, s)
        assert errors == [], f"{s['id']}: {errors}"
        assert warnings == [], f"{s['id']}: {warnings}"


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


def test_mi_espanol_vocab_dashboard_build():
    project_root = REPO / "examples" / "mi-espanol"
    project = Project(project_root)
    vocab.import_file(project, project_root / "vocab.csv")
    words = project.vocab
    assert len(words) == 795
    assert len({w["w"].casefold() for w in words}) == 795
    headwords = {w["w"] for w in words}
    assert {
        "la llave", "el queso", "¿cómo estás?", "ser", "estar",
        "la tortuga", "el baloncesto", "miércoles", "el frigorífico",
        "la playa", "el aguacate", "el helicóptero", "el sofá",
    } <= headwords
    assert "Yencho" not in headwords and "Budist" not in headwords
    by_word = {w["w"]: w for w in words}
    assert by_word["el profesor"]["answers"] == "男老师|老师|male teacher|teacher"
    assert by_word["en"]["answers"] == "在|在里面|in|at|on"
    assert by_word["inteligente"]["answers"] == "聪明|聪明的|intelligent|smart|clever"
    assert by_word["bien"]["answers"] == "好|好地|状态良好|well|good"
    assert "and" not in by_word["con"].get("answers", "").split("|")
    assert sum(word.get("kind") == "grammar" for word in words) == 14
    assert sum(word.get("review_mode") == "grammar" for word in words) == 12
    out, _, n_stories, _ = build.build(project)
    html = out.read_text(encoding="utf-8")
    assert n_stories == 0
    assert '"layout": "vocab"' in html
    assert "vocab-dashboard" in html and "vocab-search" in html
    assert 'data-vocab-category=""' in html
    assert 'data-review-action="hard"' not in html
    assert 'rateReview("hard", "button")' not in html
    assert 'data-review-action="issue"' in html
    assert "function reportReviewIssue" in html
    assert 'source: "review_answer_issue"' in html
    assert 'status: "open"' in html and 'issueType: "accepted_answer_or_gloss"' in html
    assert 'state.reviewIssueReported = saved' in html
    assert '["again", "known"].indexOf(result) === -1' in html
    assert '["again", "hard", "known"].indexOf(event.rating)' in html
    assert 'event.rating === "hard" ? "旧版中间项"' in html
    assert "2 其他" in html and "2 有点难" not in html
    assert 'id="review-answer-form"' in html
    assert "function reviewAnswerMatches" in html
    assert 'var sources = word.answers ? [word.answers] : [word.gloss || "", word.note || ""]' in html
    assert '["word", "noun"].indexOf(word.kind) !== -1' in html
    assert 'String(word.kind || "").toLowerCase().indexOf("verb") !== -1' in html
    assert 'var REVIEW_MATCHER_VERSION = "curated-aliases-v2"' in html
    assert "function reviewSpeechText" in html
    assert "SpeechSynthesisUtterance(reviewSpeechText(state.reviewQueue[0].w))" in html
    assert 'class="sent review-example-sentence"' in html
    assert 'class="review-example-source" lang="' in html
    assert 'class="say" type="button" aria-label="' in html
    assert 'sentEl.querySelector(".review-example-source")' in html
    assert 'inlineSource ? inlineSource.textContent' in html
    assert 'function reviewMode(word) { return String(word && word.review_mode || "meaning").toLowerCase(); }' in html
    assert 'function reviewIsEligible(word) { return !!word && reviewMode(word) === "meaning"; }' in html
    assert "if (!reviewIsEligible(word)) return false" in html
    assert "VOCAB_DASHBOARD && reviewIsEligible(word)" in html
    assert 'return { key: "excluded", label: "暂不复习" }' in html
    assert "var favoriteCount = vocabWords.filter(reviewIsFavorite).length" in html
    assert "reviewEligible: reviewIsEligible(word)" in html
    assert "reviewMode: reviewMode(word)" in html
    assert "var snapshotReviews = vocabWords.reduce" in html
    assert 'role="status"' in html
    assert '"qa_id": "mi-espanol"' in html
    assert '"history_id": "mi-espanol"' in html
    assert 'var QA_LS = "fabulita.qa.v1"' in html
    assert "var QA_MAX_LENGTH = 500" in html
    assert 'dashboardNavButton("qa", "?", "Q&amp;A"' in html
    assert 'id="qa-note-form"' in html and 'id="qa-question-input"' in html
    assert "function loadQaRoot" in html
    assert "function addQaQuestion" in html and "function deleteQaQuestion" in html
    assert 'data-qa-delete="' in html and 'data-qa-confirm-delete="' in html
    assert 'e.target.id === "qa-note-form"' in html
    assert 'id="qa-notice"' in html and 'aria-live="polite"' in html
    assert "esc(item.question)" in html
    assert "var reviewSurfaceVisible" in html
    assert 'var REVIEW_EVENTS_LS = "fabulita.review.events.v1"' in html
    assert "function buildReviewEvent" in html and "function appendReviewEvent" in html
    assert "event.historyScope !== historyScopeKey" in html
    assert "!Array.isArray(root.scopes)" in html
    assert "Array.isArray(latest.scopes)" in html
    assert "function dashboardProgressHtml" in html
    assert 'data-history-export="json"' in html and 'data-history-export="csv"' in html
    assert 'e.target.closest("[data-history-export]")' in html
    assert "exportReviewHistory(el.dataset.historyExport)" in html
    assert 'data-learning-export="json"' in html and 'data-learning-export="csv"' in html
    assert 'var LEARNING_EVENTS_LS = "fabulita.learning.events.v1"' in html
    assert "function recordLearningEvent" in html
    assert "function learningExportEnvelope" in html
    assert 'schema: "fabulita.learning-export.v1"' in html
    assert "function reviewHistoryCsv" in html and "function csvSafeValue" in html
    assert "typedAnswer" in html and "answerCorrect" in html and "ratingInput" in html
    assignments = project.homeworks
    assert len(assignments) == 19
    assignment = next(
        item for item in assignments
        if item["id"] == "ejercicios-vocabulario-a1-1"
    )
    conjugation = next(
        item for item in assignments
        if item["id"] == "ser-estar-conjugation-a1"
    )
    bilingual_ser_estar = next(
        item for item in assignments
        if item["id"] == "ser-estar-practice-a1-01"
    )
    present_ser_estar = next(
        item for item in assignments
        if item["id"] == "ser-estar-present-a1-02"
    )
    assert len(assignment["sections"]) == 2
    items = [item for section in assignment["sections"] for item in section["items"]]
    assert len(items) == 50 and len({item["id"] for item in items}) == 50
    conjugation_items = [
        item for section in conjugation["sections"] for item in section["items"]
    ]
    assert len(conjugation_items) == 12
    assert {section["type"] for section in conjugation["sections"]} == {"text_input"}
    assert sum(
        len(section["items"]) for section in bilingual_ser_estar["sections"]
    ) == 21
    assert sum(
        len(section["items"]) for section in present_ser_estar["sections"]
    ) == 31
    assert bilingual_ser_estar["source"] == {}
    assert present_ser_estar["source"] == {}
    assert assignment["answerKeyBasis"] == "inferred_from_context"
    assert assignment["sections"][0]["items"][11]["answers"] == ["zapato", "sombrero"]
    assert assignment["sections"][1]["items"][14]["answers"] == ["café"]
    payload = build.payload(project)
    source = next(
        item for item in payload["homeworks"]
        if item["id"] == "ejercicios-vocabulario-a1-1"
    )["source"]
    # The adapted classroom worksheet is not distributed: no file, no dataUrl.
    assert source == {}
    assert "Ejercicio de vocabulario español A1 - 1" in html
    assert "fabulita.homework.v1" in html
    assert 'dashboardNavButton("homework"' in html


def test_build_reader(tmp_path):
    from fabulita import build
    out, size = build.build_reader(tmp_path / "reader.html")
    html = out.read_text(encoding="utf-8")
    assert size == len(html)
    assert "/*__PAYLOAD__*/null" not in html
    import json as _json, re
    m = re.search(r"<script>var P = (\{.*?\});</script>", html, re.S)
    assert m, "payload script tag not found"
    data = _json.loads(m.group(1))
    assert data["self"] is True
    assert data["stories"] == [] and data["vocab"] == []
    assert data["homeworks"] == []
    assert data["config"]["home"] == "index.html"
    assert data["config"]["review_id"] == "self"
    assert data["config"]["qa_id"] == "self"
    assert data["config"]["history_id"] == "self"
    assert "ui" in data and "uiLangs" in data
    assert "fabulita.review.v1" in html
    assert "reviewCardKey" in html and "rateReview" in html


def test_demo_data_js(proj, tmp_path):
    # Setup: seed vocab and create stories (one accepted, one candidate)
    seed_vocab(proj, tmp_path, ["perro,狗", "jardín,花园", "flor,花"])
    stories.add(proj, write_story(tmp_path, make_story()), accept=True)
    stories.add(proj, write_story(tmp_path, make_story(id="otro-perro", title="Otro perro")), accept=False)

    js = build.demo_data_js(proj)
    assert js.startswith("window.FABULITA_DEMO=window.FABULITA_DEMO||{};")
    data_json = js.split("=", 2)[2].rstrip(";\n")
    data = json.loads(data_json.replace("<\\/", "</"))
    assert data["lang"] == proj.config["lang"]
    # Verify only accepted stories are included, no candidates
    assert len(data["stories"]) == 1
    assert data["stories"][0]["id"] == "el-perro"
    assert all(s["status"] == "accepted" for s in data["stories"])
    out, size = build.build_demo_data(proj, tmp_path / "demo-data-es.js")
    assert out.exists() and size == len(js)


def test_local_homework_appends_only_when_requested(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    (root / "fabulita.json").write_text(json.dumps({
        "name": "Local Test", "lang": "es",
    }), encoding="utf-8")
    (root / "homework.json").write_text(json.dumps({
        "version": 1,
        "assignments": [{"id": "public-1", "title": "公开", "sections": []}],
    }), encoding="utf-8")
    (root / "homework.local.json").write_text(json.dumps({
        "version": 1,
        "assignments": [{"id": "local-1", "title": "原样", "sections": []}],
    }), encoding="utf-8")
    project = Project(root)

    public = build.payload(project)["homeworks"]
    assert [a["id"] for a in public] == ["public-1"]

    combined = build.payload(project, include_local_homework=True)["homeworks"]
    assert [a["id"] for a in combined] == ["public-1", "local-1"]


def test_demo_manifest_js(proj, tmp_path):
    # Setup: seed vocab and create stories (one accepted, one candidate)
    seed_vocab(proj, tmp_path, ["perro,狗", "jardín,花园", "flor,花"])
    stories.add(proj, write_story(tmp_path, make_story()), accept=True)
    stories.add(proj, write_story(tmp_path, make_story(id="otro-perro", title="Otro perro")), accept=False)

    js = build.demo_manifest_js([proj])
    assert js.startswith("window.FABULITA_DEMO_COUNTS=")
    data = json.loads(js.split("=", 1)[1].rstrip(";\n").replace("<\\/", "</"))
    lang = proj.config["lang"]
    # Verify only accepted stories are counted, no candidates
    assert data[lang]["n"] == 1
    assert len(data[lang]["ids"]) == 1
    assert data[lang]["ids"][0] == "el-perro"
