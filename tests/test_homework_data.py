import base64
import hashlib
import json
import re
import subprocess
import unicodedata
from collections import Counter
from pathlib import Path

import pytest

from fabulita import build
from fabulita.project import Project


REPO = Path(__file__).parent.parent
MI_ESPANOL = REPO / "examples" / "mi-espanol"
SER_ESTAR_VOCAB_PDF = (
    MI_ESPANOL / "materials" / "practica-ser-estar-vocabulario.pdf"
)
SER_ESTAR_VOCAB_PDF_SHA256 = (
    "0c206fdd4b3b89e1cdfd1bad6281c9f09062525d9ad700cae4a025a678e37c8e"
)
SER_ESTAR_VOCAB_PDF_SIZE = 5805


def _write_homework(project_root, source_file, checksum):
    homework = {
        "version": 1,
        "assignments": [
            {
                "id": "test-assignment",
                "title": "Test assignment",
                "source": {
                    "file": source_file,
                    "filename": "source.pdf",
                    "sha256": checksum,
                },
                "sections": [],
            }
        ],
    }
    (project_root / "homework.json").write_text(
        json.dumps(homework), encoding="utf-8"
    )


def _reader_payload(html):
    match = re.search(r"<script>var P = (\{.*?\});</script>", html, re.S)
    assert match, "reader payload script tag not found"
    return json.loads(match.group(1))


def _study_key(value):
    return " ".join(
        unicodedata.normalize("NFC", value).casefold().strip().split()
    )


def _assignment_by_id(assignments, assignment_id):
    matches = [
        assignment
        for assignment in assignments
        if assignment.get("id") == assignment_id
    ]
    assert len(matches) == 1, assignment_id
    return matches[0]


def test_mi_espanol_has_complete_vocabulary_homework_assignment():
    assignments = Project(MI_ESPANOL).homeworks

    assignment = _assignment_by_id(
        assignments, "ejercicios-vocabulario-a1-1"
    )
    assert len(assignment["sections"]) == 2

    items = [
        item
        for section in assignment["sections"]
        for item in section["items"]
    ]
    item_ids = [item["id"] for item in items]
    assert len(items) == 50
    assert len(item_ids) == len(set(item_ids)) == 50

    for section in assignment["sections"]:
        for item in section["items"]:
            answers = item.get("answers")
            assert isinstance(answers, list) and answers, item["id"]
            assert all(isinstance(answer, str) and answer for answer in answers)
            if section["type"] == "single_choice":
                options = item.get("options")
                assert isinstance(options, list) and options, item["id"]
                assert set(answers) <= set(options), item["id"]


def test_ser_estar_conjugation_homework_is_complete():
    assignment = _assignment_by_id(
        Project(MI_ESPANOL).homeworks, "ser-estar-conjugation-a1"
    )
    expected = {
        "ser": [
            ("yo", "soy"),
            ("tú", "eres"),
            ("él / ella", "es"),
            ("nosotros / nosotras", "somos"),
            ("vosotros / vosotras", "sois"),
            ("ellos / ellas", "son"),
        ],
        "estar": [
            ("yo", "estoy"),
            ("tú", "estás"),
            ("él / ella", "está"),
            ("nosotros / nosotras", "estamos"),
            ("vosotros / vosotras", "estáis"),
            ("ellos / ellas", "están"),
        ],
    }

    assert assignment["level"] == "A1"
    assert assignment["answerKeyBasis"] == "standard_conjugation"
    assert "studyWords" not in assignment
    assert "source" not in assignment

    reference_tables = assignment.get("referenceTables")
    assert isinstance(reference_tables, list)
    assert [table["verb"] for table in reference_tables] == ["ser", "estar"]
    for table in reference_tables:
        verb = table["verb"]
        assert [
            (row["person"], row["form"])
            for row in table["rows"]
        ] == expected[verb]

    sections = assignment.get("sections")
    assert isinstance(sections, list)
    assert [section["verb"] for section in sections] == ["ser", "estar"]
    assert all(section["type"] == "text_input" for section in sections)

    items = [
        item
        for section in sections
        for item in section["items"]
    ]
    item_ids = [item["id"] for item in items]
    assert len(items) == 12
    assert len(item_ids) == len(set(item_ids)) == 12

    for section in sections:
        verb = section["verb"]
        assert len(section["items"]) == 6
        assert [
            (item["person"], item["answers"][0])
            for item in section["items"]
        ] == expected[verb]
        for item in section["items"]:
            assert item["verb"] == verb
            assert item["prompt"] == f"{item['person']} → {verb}"
            assert item["answers"] == [
                dict(expected[verb])[item["person"]]
            ]


def test_mi_espanol_choice_sentences_cover_every_accepted_answer():
    assignment = _assignment_by_id(
        Project(MI_ESPANOL).homeworks,
        "ejercicios-vocabulario-a1-1",
    )
    part_1, part_2 = assignment["sections"]

    assert part_1["type"] == "single_choice"
    assert len(part_1["items"]) == 30
    for item in part_1["items"]:
        assert item["prompt"].count("_______") == 1, item["id"]
        translations = item.get("sentenceTranslations")
        assert isinstance(translations, dict), item["id"]
        assert set(translations) == set(item["answers"]), item["id"]
        assert all(
            isinstance(translation, str) and translation.strip()
            for translation in translations.values()
        ), item["id"]

    first = part_1["items"][0]
    assert first["sentenceTranslations"] == {
        "lunes": "星期一是一周的第一天。",
    }
    multi_answer = part_1["items"][6]
    assert multi_answer["sentenceTranslations"]["agua"] == "我口渴时喜欢喝水。"
    assert multi_answer["sentenceTranslations"]["leche"] == "我口渴时喜欢喝牛奶。"

    assert part_2["type"] == "text_input"
    assert all("sentenceTranslations" not in item for item in part_2["items"])

    sentence_lexicon = assignment.get("sentenceLexicon")
    assert isinstance(sentence_lexicon, list) and sentence_lexicon
    lexicon_ids = [entry.get("id") for entry in sentence_lexicon]
    assert all(isinstance(entry_id, str) and entry_id for entry_id in lexicon_ids)
    assert len(lexicon_ids) == len(set(lexicon_ids))
    for entry in sentence_lexicon:
        for field in ("word", "gloss", "english"):
            assert isinstance(entry.get(field), str) and entry[field].strip(), (
                entry.get("id"),
                field,
            )
        forms = entry.get("forms")
        assert isinstance(forms, list) and forms, entry["id"]
        assert all(isinstance(form, str) and form.strip() for form in forms)


def test_mi_espanol_study_words_cover_homework_vocabulary():
    assignment = _assignment_by_id(
        Project(MI_ESPANOL).homeworks,
        "ejercicios-vocabulario-a1-1",
    )
    study_words = assignment["studyWords"]

    assert len(study_words) == 93
    role_counts = Counter(word.get("role") for word in study_words)
    assert role_counts == {"answer": 51, "context": 42}

    ids = [word.get("id") for word in study_words]
    normalized_words = [_study_key(word.get("word", "")) for word in study_words]
    assert all(isinstance(word_id, str) and word_id.strip() for word_id in ids)
    assert len(ids) == len(set(ids)) == 93
    assert all(normalized_words)
    assert len(normalized_words) == len(set(normalized_words)) == 93

    for word in study_words:
        assert word["role"] in {"answer", "context"}, word.get("id")
        for field in ("word", "gloss", "english"):
            assert isinstance(word.get(field), str) and word[field].strip(), (
                word.get("id"),
                field,
            )
        answers = word.get("answers")
        assert isinstance(answers, list) and answers, word["id"]
        assert all(
            isinstance(answer, str) and answer.strip() for answer in answers
        ), word["id"]
        if "example" in word:
            assert isinstance(word["example"], str) and word["example"].strip()

    part_1, part_2 = assignment["sections"]
    part_1_options = [
        option
        for item in part_1["items"]
        for option in item["options"]
    ]
    part_2_canonical = [
        item.get("canonicalAnswer") or item["answers"][0]
        for item in part_2["items"]
    ]
    assert len(part_1_options) == 90
    assert len({_study_key(option) for option in part_1_options}) == 44

    required_answer_words = {
        _study_key(value)
        for value in part_1_options + part_2_canonical
    }
    answer_word_counts = Counter(
        _study_key(word["word"])
        for word in study_words
        if word["role"] == "answer"
    )
    assert len(required_answer_words) == 51
    assert set(answer_word_counts) == required_answer_words
    assert all(count == 1 for count in answer_word_counts.values())

    by_word = {_study_key(word["word"]): word for word in study_words}
    assert {
        field: by_word["lunes"][field]
        for field in ("gloss", "english", "answers")
    } == {
        "gloss": "星期一、周一",
        "english": "Monday",
        "answers": ["星期一", "周一", "Monday"],
    }
    assert {
        field: by_word["sol"][field]
        for field in ("gloss", "english", "answers")
    } == {
        "gloss": "太阳；阳光",
        "english": "sun; sunshine",
        "answers": ["太阳", "阳光", "sun", "sunshine"],
    }
    assert {
        field: by_word["frío"][field]
        for field in ("gloss", "english", "answers")
    } == {
        "gloss": "寒冷；冷的",
        "english": "cold",
        "answers": ["寒冷", "冷", "冷的", "cold"],
    }

    assert {
        field: by_word["primer día"][field]
        for field in ("role", "gloss", "english", "answers", "example")
    } == {
        "role": "context",
        "gloss": "第一天",
        "english": "first day",
        "answers": ["第一天", "first day"],
        "example": "El lunes es el primer día de la semana.",
    }
    assert {
        field: by_word["semana"][field]
        for field in ("role", "gloss", "english", "answers")
    } == {
        "role": "context",
        "gloss": "星期、周",
        "english": "week",
        "answers": ["星期", "周", "一周", "week"],
    }


def test_mi_espanol_does_not_ship_the_classroom_worksheet():
    # The original worksheet is third-party classroom material; the public
    # repo must never embed or reference it, only the adapted exercises.
    assignment = _assignment_by_id(
        build.payload(Project(MI_ESPANOL))["homeworks"],
        "ejercicios-vocabulario-a1-1",
    )
    assert assignment["source"] == {}
    assert assignment["teacher"] == "Profesor de ejemplo"


def test_rewritten_ser_estar_assignments_are_complete_and_private():
    assignments = Project(MI_ESPANOL).homeworks
    expected = {
        "ser-estar-practice-a1-01": {
            "title": "Ser / Estar 双语语境练习 A1 - 1",
            "section_id": "se01-context",
            "answers": [
                "está",
                "es",
                "estamos",
                "es",
                "están",
                "es",
                "están",
                "está",
                "es",
                "estoy",
                "estás",
                "está",
                "están",
                "es",
                "son",
                "están",
                "estáis",
                "es",
                "estoy",
                "está",
                "son",
            ],
        },
        "ser-estar-present-a1-02": {
            "title": "Ser / Estar 现在时语境练习 A1 - 2",
            "section_id": "se02-context",
            "answers": [
                "es",
                "estamos",
                "estás",
                "es",
                "están",
                "está",
                "soy",
                "están",
                "es",
                "están",
                "está",
                "somos",
                "está",
                "está",
                "está",
                "son",
                "es",
                "estoy",
                "son",
                "estás",
                "estamos",
                "son",
                "están",
                "es",
                "está",
                "están",
                "es",
                "están",
                "está",
                "somos",
                "estoy",
            ],
        },
    }

    for assignment_id, spec in expected.items():
        assignment = _assignment_by_id(assignments, assignment_id)
        assert assignment["title"] == spec["title"]
        assert assignment["badge"] == "新练习"
        assert assignment["teacher"] == "Profesor de ejemplo"
        assert assignment["level"] == "A1"
        assert assignment["answerKeyBasis"] == "inferred_from_context"
        assert (
            assignment["contentOrigin"]
            == "independently_rewritten_private_classroom_adaptation"
        )
        assert assignment["source"] == {}

        assert len(assignment["sections"]) == 1
        section = assignment["sections"][0]
        assert section["id"] == spec["section_id"]
        assert section["type"] == "text_input"
        items = section["items"]
        assert len(items) == len(spec["answers"])
        assert [item["number"] for item in items] == list(
            range(1, len(items) + 1)
        )
        assert [item["canonicalAnswer"] for item in items] == spec["answers"]
        assert len({item["id"] for item in items}) == len(items)

        for item in items:
            assert item["prompt"].count("_______") == 1, item["id"]
            assert item["canonicalAnswer"] == item["answers"][0]
            assert all(
                isinstance(answer, str) and answer.strip()
                for answer in item["answers"]
            ), item["id"]
            assert set(item["sentenceTranslations"]) == set(item["answers"])
            assert all(
                isinstance(translation, str) and translation.strip()
                for translation in item["sentenceTranslations"].values()
            ), item["id"]

        reference_tables = assignment["referenceTables"]
        assert [table["verb"] for table in reference_tables] == ["ser", "estar"]
        assert [
            row["form"]
            for table in reference_tables
            for row in table["rows"]
        ] == [
            "soy",
            "eres",
            "es",
            "somos",
            "sois",
            "son",
            "estoy",
            "estás",
            "está",
            "estamos",
            "estáis",
            "están",
        ]

    bilingual = _assignment_by_id(assignments, "ser-estar-practice-a1-01")
    bilingual_ambiguous = bilingual["sections"][0]["items"][11]
    assert set(bilingual_ambiguous["answers"]) == {"está", "es"}
    assert bilingual_ambiguous["ambiguityNote"]

    present = _assignment_by_id(assignments, "ser-estar-present-a1-02")
    present_rain_plants = present["sections"][0]["items"][9]
    assert set(present_rain_plants["answers"]) == {"están", "son"}
    assert present_rain_plants["ambiguityNote"]
    present_ambiguous = present["sections"][0]["items"][23]
    assert set(present_ambiguous["answers"]) == {"es", "está"}
    assert present_ambiguous["ambiguityNote"]
    present_gazpacho = present["sections"][0]["items"][28]
    assert set(present_gazpacho["answers"]) == {"está", "es"}
    assert present_gazpacho["ambiguityNote"]

    source_text = (MI_ESPANOL / "homework.json").read_text(encoding="utf-8")
    derived = _verbatim_fingerprints()
    if derived is not None:
        # The real teacher's name is derived from the gitignored local file so
        # it is never committed here in plaintext.
        assert derived["teacher"] not in source_text
    assert "Ejercicio_SER_y_ESTAR" not in source_text

    payload_assignments = build.payload(Project(MI_ESPANOL))["homeworks"]
    for assignment_id in expected:
        assignment = _assignment_by_id(payload_assignments, assignment_id)
        assert assignment["source"] == {}
        assert "dataUrl" not in assignment["source"]


def test_practica_ser_estar_vocabulario_assignment_is_complete():
    assignments = Project(MI_ESPANOL).homeworks
    assignment = _assignment_by_id(
        assignments, "practica-ser-estar-vocabulario-a0"
    )

    assert assignment["title"] == "Ser / Estar 与词汇练习 A0"
    assert assignment["badge"] == "新练习"
    assert assignment["sourceTitle"] == "Práctica de Español - Nivel A0"
    assert assignment["teacher"] == "Profesor de ejemplo"
    assert assignment["level"] == "A0"
    assert assignment["answerKeyBasis"] == "inferred_from_context"

    sections = assignment["sections"]
    assert [
        (section["id"], section["type"], len(section["items"]))
        for section in sections
    ] == [
        ("pse-a0-ser-estar", "text_input", 25),
        ("pse-a0-vocab-translate", "text_input", 25),
        ("pse-a0-vocab-choice", "single_choice", 25),
    ]

    assignment_ids = [item["id"] for item in assignments]
    section_ids = [
        section["id"]
        for homework in assignments
        for section in homework.get("sections", [])
    ]
    item_ids = [
        item["id"]
        for homework in assignments
        for section in homework.get("sections", [])
        for item in section.get("items", [])
    ]
    study_word_ids = [
        word["id"]
        for homework in assignments
        for word in homework.get("studyWords", [])
    ]
    for ids in (assignment_ids, section_ids, item_ids, study_word_ids):
        assert len(ids) == len(set(ids))

    for section in sections:
        assert [item["number"] for item in section["items"]] == list(
            range(1, 26)
        )
        for item in section["items"]:
            answers = item.get("answers")
            assert isinstance(answers, list) and answers, item["id"]
            assert all(
                isinstance(answer, str) and answer.strip()
                for answer in answers
            ), item["id"]
            assert item["sourcePage"] in {1, 2, 3}
            if section["type"] == "single_choice":
                assert len(item["options"]) == 3, item["id"]
                assert set(answers) <= set(item["options"]), item["id"]


def test_practica_ser_estar_answers_and_sentence_translations():
    assignment = _assignment_by_id(
        Project(MI_ESPANOL).homeworks,
        "practica-ser-estar-vocabulario-a0",
    )
    ser_estar, translate, choice = assignment["sections"]

    assert [item["canonicalAnswer"] for item in ser_estar["items"]] == [
        "soy",
        "está",
        "somos",
        "está",
        "son",
        "está",
        "eres",
        "es",
        "estamos",
        "está",
        "es",
        "están",
        "soy",
        "es",
        "están",
        "está",
        "eres",
        "está",
        "estamos",
        "está",
        "estoy",
        "está",
        "está",
        "son",
        "está",
    ]
    assert [item["canonicalAnswer"] for item in translate["items"]] == [
        "casa",
        "escuela",
        "libro",
        "puerta",
        "ciudad",
        "amigo",
        "madre",
        "restaurante",
        "mesa",
        "estudiante",
        "hospital",
        "parque",
        "comida",
        "tienda",
        "profesor",
        "padres",
        "jardín",
        "clase",
        "perro",
        "abierto",
        "cerrado",
        "grande",
        "pequeño",
        "cansado",
        "limpio",
    ]
    assert [item["canonicalAnswer"] for item in choice["items"]] == [
        "libro",
        "amigo",
        "mesa",
        "hospital",
        "escuela",
        "ciudad",
        "jardín",
        "escuela",
        "puerta",
        "padres",
        "estudiante",
        "mesa",
        "ciudad",
        "restaurante",
        "cerrada",
        "grande",
        "clase",
        "perro",
        "pequeña",
        "cansado",
        "ciudad",
        "caliente",
        "perro",
        "clase",
        "casa",
    ]

    for item in ser_estar["items"] + choice["items"]:
        assert item["prompt"].count("_______") == 1, item["id"]
        translations = item.get("sentenceTranslations")
        assert isinstance(translations, dict), item["id"]
        assert set(translations) == set(item["answers"]), item["id"]
        assert all(
            isinstance(text, str) and text.strip()
            for text in translations.values()
        ), item["id"]

    assert ser_estar["items"][15]["answers"] == ["está"]
    assert ser_estar["items"][22]["answers"] == ["está"]
    assert ser_estar["items"][15]["ambiguityNote"]
    assert ser_estar["items"][22]["ambiguityNote"]

    assert {"amigo", "amiga", "el amigo", "la amiga"} <= set(
        translate["items"][5]["answers"]
    )
    assert {"profesor", "profesora", "el profesor", "la profesora"} <= set(
        translate["items"][14]["answers"]
    )
    assert {"pequeño", "pequeña", "pequeños", "pequeñas"} == set(
        translate["items"][22]["answers"]
    )

    expected_ambiguous_answers = {
        10: {"estudiantes", "padres"},
        12: {"mesa", "tienda"},
        14: {"hospital", "restaurante"},
        18: {"perro", "restaurante"},
        24: {"clase", "tienda"},
        25: {"casa", "restaurante", "hospital"},
    }
    for number, expected in expected_ambiguous_answers.items():
        item = choice["items"][number - 1]
        assert set(item["answers"]) == expected
        assert item["canonicalAnswer"] in expected
        assert item["ambiguityNote"]

    for number in (3, 4, 5, 7, 8, 23):
        assert choice["items"][number - 1]["ambiguityNote"]


def test_practica_ser_estar_reference_tables_and_study_words():
    assignment = _assignment_by_id(
        Project(MI_ESPANOL).homeworks,
        "practica-ser-estar-vocabulario-a0",
    )
    expected_tables = {
        "ser": [
            ("yo", "soy"),
            ("tú", "eres"),
            ("él / ella", "es"),
            ("nosotros / nosotras", "somos"),
            ("vosotros / vosotras", "sois"),
            ("ellos / ellas", "son"),
        ],
        "estar": [
            ("yo", "estoy"),
            ("tú", "estás"),
            ("él / ella", "está"),
            ("nosotros / nosotras", "estamos"),
            ("vosotros / vosotras", "estáis"),
            ("ellos / ellas", "están"),
        ],
    }
    tables = assignment["referenceTables"]
    assert [table["verb"] for table in tables] == ["ser", "estar"]
    for table in tables:
        assert [
            (row["person"], row["form"])
            for row in table["rows"]
        ] == expected_tables[table["verb"]]

    study_words = assignment["studyWords"]
    words = {_study_key(word["word"]): word for word in study_words}
    assert len(words) == len(study_words)
    for word in study_words:
        assert word["role"] == "answer"
        for field in ("id", "word", "gloss", "english"):
            assert isinstance(word.get(field), str) and word[field].strip()
        assert isinstance(word.get("answers"), list) and word["answers"]

    _, translate, choice = assignment["sections"]
    required_feedback_words = {
        _study_key(item["canonicalAnswer"])
        for item in translate["items"]
    } | {
        _study_key(answer)
        for item in choice["items"]
        for answer in item["answers"]
    }
    assert required_feedback_words <= set(words)

    assert words["casa"]["gloss"] == "房子；家"
    assert words["casa"]["english"] == "house; home"
    assert words["está"]["english"] == "is (estar)"
    assert {"他在", "她在", "它在", "您在"} <= set(words["está"]["answers"])


def test_practica_ser_estar_embeds_exact_original_pdf():
    pdf_bytes = SER_ESTAR_VOCAB_PDF.read_bytes()
    assert len(pdf_bytes) == SER_ESTAR_VOCAB_PDF_SIZE
    assert (
        hashlib.sha256(pdf_bytes).hexdigest()
        == SER_ESTAR_VOCAB_PDF_SHA256
    )
    assert len(re.findall(rb"/Type\s*/Page\b", pdf_bytes)) == 3

    assignment = _assignment_by_id(
        build.payload(Project(MI_ESPANOL))["homeworks"],
        "practica-ser-estar-vocabulario-a0",
    )
    source = assignment["source"]
    expected_data_url = (
        "data:application/pdf;base64,"
        + base64.b64encode(pdf_bytes).decode("ascii")
    )

    assert source["filename"] == "Practica_Ser_Estar___vocabulario.pdf"
    assert source["sha256"] == SER_ESTAR_VOCAB_PDF_SHA256
    assert source["size"] == SER_ESTAR_VOCAB_PDF_SIZE
    assert source["pageCount"] == 3
    assert source["dataUrl"] == expected_data_url
    assert "file" not in source


def test_empty_projects_and_reader_have_no_homeworks(tmp_path):
    project = Project(tmp_path / "empty-project")
    project.init()

    assert project.homeworks == []
    assert build.payload(project)["homeworks"] == []

    reader_path, _ = build.build_reader(tmp_path / "reader.html")
    reader = _reader_payload(reader_path.read_text(encoding="utf-8"))
    assert reader["homeworks"] == []


def test_homework_source_checksum_mismatch_is_rejected(tmp_path):
    project_root = tmp_path / "project"
    project = Project(project_root)
    project.init()
    materials = project_root / "materials"
    materials.mkdir()
    (materials / "source.pdf").write_bytes(b"%PDF-1.7\nnot the expected file\n")
    _write_homework(
        project_root,
        "materials/source.pdf",
        "0" * 64,
    )

    with pytest.raises(ValueError, match="homework source checksum mismatch"):
        build.payload(project)


def test_homework_source_path_escape_is_rejected(tmp_path):
    project_root = tmp_path / "project"
    project = Project(project_root)
    project.init()
    (tmp_path / "outside.pdf").write_bytes(b"%PDF-1.7\noutside project\n")
    _write_homework(
        project_root,
        "../outside.pdf",
        hashlib.sha256((tmp_path / "outside.pdf").read_bytes()).hexdigest(),
    )

    with pytest.raises(ValueError, match="homework source must stay inside project"):
        build.payload(project)


def test_homework_type_track_is_block_level():
    # The track is a <span> inside a non-flex button; without display:block its
    # height collapses and the inner accent bar paints as a broken orange blob.
    template = (REPO / "fabulita" / "template.html").read_text(encoding="utf-8")
    match = re.search(r"\.homework-type-track \{[^}]*\}", template)
    assert match, "expected a .homework-type-track CSS rule"
    assert "display: block" in match.group(0)


def test_answer_sentence_words_have_gloss_coverage():
    # Every content word in a resolved answer sentence must be known to
    # studyWords, sentenceLexicon, or vocab.csv, or the learner page cannot
    # underline it (the "biblioteca" bug).
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "collect_lexicon", REPO / "scripts" / "collect_lexicon.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    vocab_rows = mod.load_vocab_rows(MI_ESPANOL)
    for assignment in Project(MI_ESPANOL).homeworks:
        missing = mod.uncovered_words(assignment, vocab_rows)
        assert not missing, f"{assignment['id']} uncovered: {sorted(missing)}"


def _verbatim_fingerprints():
    # Fingerprints of the private worksheet content are derived at test time
    # from the gitignored homework.local.json so that neither the teacher's
    # name nor any verbatim sentence is ever committed in this file. Returns
    # None when the local file is absent (fresh clones). Each sentence becomes
    # an order-preserving regex over the pieces around the "_______" blank with
    # a bounded gap, so both the raw-blank form and an answer-filled copy are
    # caught, while rewritten public items that legitimately share half a
    # sentence are not flagged.
    local = MI_ESPANOL / "homework.local.json"
    if not local.exists():
        return None
    data = json.loads(local.read_text(encoding="utf-8"))
    teacher = ""
    patterns = {}
    for assignment in data.get("assignments", []):
        teacher = (assignment.get("teacher") or "").strip() or teacher
        for section in assignment.get("sections", []):
            for item in section.get("items", []):
                prompt = str(item.get("prompt") or "")
                sentence = re.sub(r"\s*\([^)]*\)\s*$", "", prompt).strip()
                pieces = [p.strip() for p in sentence.split("_______")]
                pieces = [p for p in pieces if len(p) >= 4]
                if not pieces or sum(len(p) for p in pieces) < 12:
                    continue
                label = item.get("id") or sentence
                patterns[label] = re.compile(
                    r".{0,24}".join(re.escape(p) for p in pieces)
                )
    assert teacher, "local worksheet file must carry the teacher field"
    assert patterns, "local worksheet file yielded no sentence fingerprints"
    # Also match the name without its honorific (e.g. a bare surname leak).
    bare = re.sub(
        r"^(profesora?|prof\.?|sra?\.)\s+", "", teacher, flags=re.IGNORECASE
    ).strip()
    name = bare if len(bare) >= 4 else teacher
    patterns["teacher"] = re.compile(re.escape(name))
    return {"teacher": name, "patterns": patterns}


def test_verbatim_worksheet_content_never_ships():
    # The verbatim transcriptions live only in gitignored homework.local.json /
    # docs/*.local.html. None of their fingerprints may appear in ANY
    # git-tracked file (data, docs, plans, specs, tests, NOTICE, ...).
    derived = _verbatim_fingerprints()
    if derived is None:
        pytest.skip("homework.local.json not present")
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=REPO, capture_output=True, text=True,
        check=True,
    ).stdout.splitlines()
    assert tracked, "git ls-files returned nothing"
    for rel in tracked:
        path = REPO / rel
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError):
            continue  # binary or deleted-from-worktree file
        for label, pattern in derived["patterns"].items():
            assert not pattern.search(text), (
                f"verbatim fingerprint {label!r} leaked into {rel}"
            )


def test_local_homework_file_is_gitignored():
    result = subprocess.run(
        ["git", "check-ignore", "examples/mi-espanol/homework.local.json",
         "docs/mi-espanol.local.html"],
        cwd=REPO, capture_output=True, text=True,
    )
    assert result.returncode == 0, "local homework artifacts must be gitignored"
