import importlib.util
from pathlib import Path

REPO = Path(__file__).parent.parent
_spec = importlib.util.spec_from_file_location(
    "collect_lexicon", REPO / "scripts" / "collect_lexicon.py"
)
collect_lexicon = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(collect_lexicon)


def test_surface_forms_strip_articles_and_split_alternatives():
    assert collect_lexicon.surface_forms("la casa") == {"la casa", "casa"}
    assert collect_lexicon.surface_forms("el árbol / los árboles") == {
        "el árbol", "árbol", "los árboles", "árboles",
    }


def test_answer_sentences_resolve_blanks_and_drop_english_gloss():
    item = {
        "prompt": "Nosotros _______ en la biblioteca ahora. (We are in the library now.)",
        "answers": ["estamos"],
    }
    assert collect_lexicon.answer_sentences(item) == [
        "Nosotros estamos en la biblioteca ahora."
    ]


def test_uncovered_words_flags_content_words_only():
    assignment = {
        "studyWords": [],
        "sentenceLexicon": [
            {"id": "x", "word": "ahora", "forms": [], "gloss": "现在", "english": "now"}
        ],
        "sections": [{
            "items": [{
                "id": "i1",
                "prompt": "Nosotros _______ en la biblioteca ahora.",
                "answers": ["estamos"],
            }],
        }],
    }
    missing = collect_lexicon.uncovered_words(assignment, [])
    # estamos (ser/estar form), nosotros, en (stopwords) must not be flagged;
    # biblioteca must be.
    assert set(missing) == {"biblioteca"}
    assert missing["biblioteca"] == ["i1"]


def test_uncovered_words_accepts_core_vocab_rows():
    assignment = {
        "sections": [{
            "items": [{"id": "i1", "prompt": "La comida _______ lista.", "answers": ["está"]}],
        }],
    }
    rows = [
        {"word": "la comida", "kind": "word"},
        {"word": "listo / lista", "kind": "word"},
    ]
    assert collect_lexicon.uncovered_words(assignment, rows) == {}
