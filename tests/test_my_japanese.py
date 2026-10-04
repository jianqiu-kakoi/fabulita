import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

from fabulita import build, vocab
from fabulita.project import Project
from scripts.build_docs import VOCAB_APPS


REPO = Path(__file__).parent.parent
MY_JAPANESE = REPO / "examples" / "my-japanese"


def _load_builder():
    spec = importlib.util.spec_from_file_location(
        "build_my_japanese_homework", REPO / "scripts" / "build_my_japanese_homework.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


japanese_builder = _load_builder()


def _local_assignments():
    local_path = MY_JAPANESE / "homework.local.json"
    if not local_path.exists():
        pytest.skip("private My Japanese homework is not present in this checkout")
    return Project(MY_JAPANESE).local_homeworks


def _items(assignment):
    return [
        item
        for section in assignment.get("sections", [])
        for item in section.get("items", [])
    ]


def test_my_japanese_is_an_independent_vocab_app(tmp_path):
    project = Project(MY_JAPANESE)
    config = project.config

    assert config["name"] == "My Japanese"
    assert config["lang"] == "ja"
    assert config["gloss_lang"] == "zh"
    assert config["layout"] == "vocab"
    assert config["review_id"] == "my-japanese-core-v1"
    assert config["qa_id"] == "my-japanese"
    assert config["history_id"] == "my-japanese"
    assert config["homework_id"] == "my-japanese"
    assert config["tts"]["voice"] == "ja-JP-NanamiNeural"
    assert VOCAB_APPS["my-japanese"] == "my-japanese.html"

    # Public homework is independently written practice; the classroom
    # worksheets stay in the private homework.local.json.
    assert [assignment["id"] for assignment in project.homeworks] == [
        assignment["id"] for assignment in japanese_builder.build_assignments()
    ]
    assert all(
        assignment["contentOrigin"] == "independently_written_public_practice"
        for assignment in project.homeworks
    )
    vocab.import_file(project, MY_JAPANESE / "vocab.csv")
    assert len(project.vocab) == 83
    assert {
        "企画",
        "興味",
        "洗濯",
        "選択",
        "足元",
        "歩む",
        "繰り返す",
        "穏やか",
        "足元が悪い",
        "など",
        "続ける",
    }.issubset({entry["w"] for entry in project.vocab})
    page, _, _, _ = build.build(
        project,
        out=tmp_path / "my-japanese.html",
        include_candidates=False,
    )
    html = page.read_text(encoding="utf-8")
    assert '"lang": "ja"' in html
    assert '"layout": "vocab"' in html
    assert '"homework_id": "my-japanese"' in html
    assert '"id": "jp-practice-potential"' in html


def test_private_japanese_homework_is_structurally_complete(tmp_path):
    assignments = _local_assignments()
    assert len(assignments) == 7
    assert len({assignment["id"] for assignment in assignments}) == 7

    open_assignment = next(
        assignment
        for assignment in assignments
        if assignment["answerKeyBasis"] == "model_answers_not_exclusive"
        and assignment["contentOrigin"] == "user_supplied_notes_editorially_corrected"
    )
    quiz_assignment = next(
        assignment
        for assignment in assignments
        if assignment["answerKeyBasis"] == "standard_japanese_conjugation"
    )
    verbatim_assignment = next(
        assignment
        for assignment in assignments
        if assignment["contentOrigin"] == "user_supplied_notes_verbatim"
    )
    new_assignments = {
        assignment["id"]: assignment
        for assignment in assignments
        if assignment["id"].endswith("2026-09-04")
    }
    assert len(new_assignments) == 4

    open_items = _items(open_assignment)
    quiz_items = _items(quiz_assignment)
    verbatim_items = _items(verbatim_assignment)
    all_items = open_items + quiz_items + verbatim_items
    assert len(open_items) == 14
    assert len(quiz_items) == 18
    assert len(verbatim_items) == 32
    assert len(all_items) == 64
    assert len({item["id"] for item in all_items}) == 64
    assert all(section["type"] == "open_response" for section in open_assignment["sections"])
    assert all(item["answerMode"] == "self_review" for item in open_items)
    assert all(item["answers"] and item["canonicalAnswer"] for item in open_items)

    def _check_two_blank_quiz(sections):
        # Every quiz row mirrors the teacher's table: one verb, a casual blank
        # and a formal blank side by side, with distinct blank ids for history.
        assert all(section["type"] == "multi_input" for section in sections)
        assert all(len(section["items"]) == 9 for section in sections)
        blank_ids = []
        for section in sections:
            for item in section["items"]:
                assert len(item["blanks"]) == 2
                for blank in item["blanks"]:
                    assert blank["answers"]
                    assert blank["canonicalAnswer"] in blank["answers"]
                    blank_ids.append(blank["id"])
        assert len(blank_ids) == len(set(blank_ids))

    assert len(quiz_assignment["sections"]) == 2
    _check_two_blank_quiz(quiz_assignment["sections"])

    # The verbatim assignment mirrors the raw notes: 3 open sections plus the
    # two quiz tables, prompts untouched.
    verbatim_open = [s for s in verbatim_assignment["sections"] if s["type"] == "open_response"]
    verbatim_quiz = [s for s in verbatim_assignment["sections"] if s["type"] == "multi_input"]
    assert len(verbatim_open) == 3
    assert len(verbatim_quiz) == 2
    assert sum(len(s["items"]) for s in verbatim_open) == 14
    _check_two_blank_quiz(verbatim_quiz)
    assert any("さいしゅうのしゅうまつ" in item["prompt"] for item in verbatim_items)

    assert sorted(len(_items(assignment)) for assignment in new_assignments.values()) == [
        14,
        21,
        22,
        47,
    ]
    for assignment in new_assignments.values():
        assert assignment["answerKeyBasis"] == "standard_japanese_grammar_and_model_answers"
        assert assignment["contentOrigin"] == "user_supplied_notes_editorially_corrected"
        assert assignment["studyWords"]

    every_item = [item for assignment in assignments for item in _items(assignment)]
    assert len(every_item) == 168
    assert len({item["id"] for item in every_item}) == 168

    potential = next(
        assignment for assignment in new_assignments.values() if len(_items(assignment)) == 47
    )
    assert {section["type"] for section in potential["sections"]} == {
        "open_response",
        "text_input",
        "single_choice",
    }
    scenario = next(
        assignment for assignment in new_assignments.values() if len(_items(assignment)) == 14
    )
    cash_item = next(item for item in _items(scenario) if item["id"] == "jp-scenario-03")
    assert "警察" in cash_item["canonicalAnswer"]
    assert "届けます" in cash_item["canonicalAnswer"]

    project = Project(MY_JAPANESE)
    public_payload = build.payload(project)
    local_payload = build.payload(project, include_local_homework=True)
    public_ids = [assignment["id"] for assignment in public_payload["homeworks"]]
    assert all(assignment_id.startswith("jp-practice-") for assignment_id in public_ids)
    assert len(local_payload["homeworks"]) == 7 + len(public_ids)

    page, _, _, _ = build.build(
        project,
        out=tmp_path / "my-japanese.local.html",
        include_candidates=False,
        include_local_homework=True,
    )
    embedded = page.read_text(encoding="utf-8")
    assert json.dumps(open_assignment["id"], ensure_ascii=False) in embedded
    assert json.dumps(quiz_assignment["id"], ensure_ascii=False) in embedded
    assert json.dumps(verbatim_assignment["id"], ensure_ascii=False) in embedded
    for assignment_id in new_assignments:
        assert json.dumps(assignment_id, ensure_ascii=False) in embedded


def test_private_japanese_homework_never_ships_in_public_files():
    assignments = _local_assignments()
    private_phrases = []
    for assignment in assignments:
        private_phrases.extend(
            value
            for value in (
                assignment.get("id"),
                assignment.get("title"),
                assignment.get("sourceTitle"),
                assignment.get("editorialNote"),
            )
            if isinstance(value, str) and len(value) >= 12
        )
        for item in _items(assignment):
            blank_answers = [
                blank.get("canonicalAnswer") for blank in item.get("blanks", [])
            ]
            private_phrases.extend(
                value
                for value in [item.get("prompt"), item.get("canonicalAnswer"), *blank_answers]
                if isinstance(value, str) and len(value) >= 12
            )

    candidates = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    assert candidates
    for rel in candidates:
        path = REPO / rel
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError):
            continue
        for phrase in private_phrases:
            assert phrase not in text, f"private Japanese homework leaked into {rel}"


def test_public_japanese_practice_is_committed_and_well_formed():
    built = japanese_builder.build_assignments()
    committed = Project(MY_JAPANESE).homeworks
    assert committed == built
    items = [item for assignment in built for item in _items(assignment)]
    assert len(items) == len({item["id"] for item in items}) == 338
    assert [a["id"] for a in built[:4]] == ["jp-practice-te", "jp-practice-nai", "jp-practice-masu", "jp-practice-pictures"]
    # Picture questions only use reviewed images copied into this project.
    for assignment in built:
        for image in assignment.get("images", {}).values():
            assert image["reviewed"] is True and image["deliver"] == "file"
            assert (MY_JAPANESE / image["file"]).is_file()
    for assignment in built:
        # Every lesson opens with its own notes box.
        assert assignment["lessonNotes"]
        assert all(note["title"] and (note.get("points") or note.get("examples"))
                   for note in assignment["lessonNotes"])
    for assignment in built:
        for section in assignment["sections"]:
            for item in section["items"]:
                if section["type"] == "single_choice":
                    assert item["answers"][0] in item["options"]
                    # Every option is explained in the "选项的意思" panel.
                    assert set(item["optionNotes"]) == set(item["options"])
                    assert all(note["gloss"] for note in item["optionNotes"].values())
                    assert not item["optionNotes"][item["answers"][0]]["gloss"].startswith("✗")
                    assert len(set(item["options"])) == len(item["options"]) >= 3
                elif item.get("wordTiles"):
                    assert item["tileJoiner"] == ""
                    assert sorted(item["canonicalAnswer"]) == sorted("".join(item["wordTiles"]))
                else:
                    assert section["type"] == "open_response"
                    assert item["answerMode"] == "self_review" and item["answers"]


def test_option_notes_have_no_duplicate_keys():
    # A repeated key in a dict literal silently replaces the earlier meaning.
    import ast
    import collections
    tree = ast.parse((REPO / "scripts" / "my_japanese_option_notes.py").read_text(encoding="utf-8"))
    keys = [key.value for node in ast.walk(tree) if isinstance(node, ast.Dict) for key in node.keys if key is not None]
    assert [key for key, count in collections.Counter(keys).items() if count > 1] == []
