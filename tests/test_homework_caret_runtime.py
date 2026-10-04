from pathlib import Path

TEMPLATE = Path(__file__).resolve().parent.parent / "fabulita" / "template.html"


def test_editing_a_checked_text_answer_keeps_the_caret_position():
    # Editing an already-checked answer clears its feedback and re-renders the
    # sheet. The caret must return to where the learner was typing, not jump to
    # the end of the input.
    template = TEMPLATE.read_text(encoding="utf-8")
    start = template.index('if (e.target.id === "homework-answer-input" ||')
    handler = template[start:template.index('if (e.target.id === "qa-question-input")', start)]
    assert "var homeworkCaret = restoreTextFocus ? e.target.selectionStart : null;" in handler
    assert handler.index("homeworkCaret = restoreTextFocus") < handler.index("render();")
    assert "setSelectionRange(homeworkCaret, homeworkCaret)" in handler
    assert "setSelectionRange(restoredHomeworkInput.value.length" not in handler
