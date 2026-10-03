# Homework UX / Scoring / Lexicon / Verbatim-Local Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the homework progress-card rendering bug, make first-attempt mistakes count and reviewable (错题本), guarantee answer-sentence lexicon coverage via a generator-side collector, add a bottom-right chat box, and add verbatim (local-only, never-committed) transcriptions of the two ser/estar PDFs.

**Architecture:** All app changes go into `fabulita/template.html` (single-file ES5 IIFE, no framework; `uv run python scripts/build_docs.py` regenerates `docs/mi-espanol.html` + `docs/my-english.html` from it). Data changes go into `examples/mi-espanol/homework.json` (public, rewritten content only) and a new gitignored `examples/mi-espanol/homework.local.json` (verbatim content). Runtime behavior is tested by Python tests that build the page into tmp and drive it with `node -e` + `vm` (copy the harness pattern from `tests/test_homework_type_navigation_runtime.py`).

**Tech Stack:** Python 3 + pytest (uv), Node for runtime tests, vanilla ES5 JS in the template.

**Spec:** `docs/superpowers/specs/2026-07-29-homework-ux-scoring-lexicon-design.md`

## Global Constraints

- Template JS is **ES5**: `var` + `function` only — no `let`/`const`/arrow functions/template literals inside `fabulita/template.html`.
- Homework blanks are exactly seven underscores: `_______` (one per item prompt).
- UI copy is Simplified Chinese, matching existing tone (e.g. 暂时不对, 已检查).
- **Open-source red line:** verbatim worksheet content — the original teacher's name (kept only in the gitignored local file) and the original sentences — must NEVER enter `examples/mi-espanol/homework.json`, any committed `docs/*.html`, or any committed file. It lives only in gitignored `homework.local.json` / `docs/*.local.html`.
- `docs/mi-espanol.html` and `docs/my-english.html` are generated — never hand-edit them; regenerate via `uv run python scripts/build_docs.py` (done once, in the final task).
- Run tests with `uv run pytest <file> -v` from the repo root `<repo-root>`.
- Work on the current branch `agent/publish-my-english-v0`.
- All localStorage stores follow the scoped-root shape `{version:1, scopes:{[scopeKey]:{...}}}` with `scopeKey = homeworkScopeKey` (`"book:<project>:<lang>"`).

---

### Task 0: Commit the leftover baseline

The working tree carries finished-but-uncommitted work from the previous session (ser/estar assignments + guard tests + NOTICE/.gitignore updates). Commit it as-is so this plan's commits are isolated.

**Files:**
- Modify: nothing (commit only)

- [ ] **Step 1: Verify the leftover changes are green**

Run: `uv run pytest tests/test_homework_data.py tests/test_homework_type_navigation_runtime.py tests/test_fabulita.py -q`
Expected: PASS (if anything fails, STOP and report — do not fix pre-existing failures silently)

- [ ] **Step 2: Commit**

```bash
git add .gitignore NOTICE docs/mi-espanol.html examples/mi-espanol/homework.json tests/test_fabulita.py tests/test_homework_data.py tests/test_homework_type_navigation_runtime.py
git commit -m "Add rewritten ser/estar assignments with privacy guards (baseline from prior session)"
```

---

### Task 1: Fix the homework type-progress track CSS

**Files:**
- Modify: `fabulita/template.html` (CSS, `.homework-type-track` rule ~line 619)
- Test: `tests/test_homework_data.py`

**Interfaces:**
- Produces: `.homework-type-track` renders as a block-level 0.45rem progress bar (the orange blob bug fix).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_homework_data.py`:

```python
def test_homework_type_track_is_block_level():
    # The track is a <span> inside a non-flex button; without display:block its
    # height collapses and the inner accent bar paints as a broken orange blob.
    template = (REPO / "fabulita" / "template.html").read_text(encoding="utf-8")
    match = re.search(r"\.homework-type-track \{[^}]*\}", template)
    assert match, "expected a .homework-type-track CSS rule"
    assert "display: block" in match.group(0)
```

(`REPO` and `re` already exist in that file; add imports only if missing.)

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_homework_data.py::test_homework_type_track_is_block_level -v`
Expected: FAIL on the `display: block` assertion

- [ ] **Step 3: Fix the CSS**

In `fabulita/template.html`, change:

```css
  .homework-type-track {
    height: 0.45rem; margin-top: 0.55rem; overflow: hidden; border-radius: 99px; background: #ebe8e3;
  }
```

to:

```css
  .homework-type-track {
    display: block; height: 0.45rem; margin-top: 0.55rem; overflow: hidden; border-radius: 99px; background: #ebe8e3;
  }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_homework_data.py::test_homework_type_track_is_block_level -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add fabulita/template.html tests/test_homework_data.py
git commit -m "Fix homework type progress track collapsing into a blob"
```

---

### Task 2: Public-data corrections (recover 2 dropped items, fix a verbatim collision)

Background: the rewritten assignments each lost one PDF item when a two-blank item was split in two, and se01-05 accidentally reproduces PDF1 #27 word-for-word.

**Files:**
- Modify: `examples/mi-espanol/homework.json`
- Modify: `tests/test_homework_data.py` (`test_rewritten_ser_estar_assignments_are_complete_and_private`, ~line 327)
- Modify: `tests/test_homework_type_navigation_runtime.py` (count assertions)

**Interfaces:**
- Produces: `ser-estar-practice-a1-01` has 21 items (new `se01-21`), `ser-estar-present-a1-02` has 31 items (new `se02-31`), `se01-05` has a non-colliding sentence. Later tasks (lexicon, runtime) build on these counts.

- [ ] **Step 1: Update the data test expectations (failing first)**

In `tests/test_homework_data.py::test_rewritten_ser_estar_assignments_are_complete_and_private`:
- Append `"son"` to the `ser-estar-practice-a1-01` answers list (now 21 entries).
- Append `"estoy"` to the `ser-estar-present-a1-02` answers list (now 31 entries).

In `tests/test_homework_type_navigation_runtime.py` update:
- `bilingualItems.length === 20` → `=== 21` (and its message "twenty" → "twenty-one")
- `presentItems.length === 30` → `=== 31` (message "thirty" → "thirty-one")
- `rewrittenListHtml.includes("20 道填空题")` → `"21 道填空题"`
- `rewrittenListHtml.includes("30 道填空题")` → `"31 道填空题"`

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_homework_data.py::test_rewritten_ser_estar_assignments_are_complete_and_private tests/test_homework_type_navigation_runtime.py -v`
Expected: FAIL (answer-count mismatch / item-count mismatch)

- [ ] **Step 3: Edit `examples/mi-espanol/homework.json`**

(a) Replace item `se01-05`'s content (keep id/number) with:

```json
{
  "id": "se01-05",
  "number": 5,
  "prompt": "Las cortinas _______ abiertas para dejar entrar la luz. (The curtains are open to let the light in.)",
  "answers": ["están"],
  "canonicalAnswer": "están",
  "sentenceTranslations": { "están": "窗帘拉开着，好让光线进来。" }
}
```

(b) Append to the `se01-context` items array:

```json
{
  "id": "se01-21",
  "number": 21,
  "prompt": "¿De quién _______ estas gafas? (Whose glasses are these?)",
  "answers": ["son"],
  "canonicalAnswer": "son",
  "sentenceTranslations": { "son": "这副眼镜是谁的？" }
}
```

(c) Append to the `se02-context` items array:

```json
{
  "id": "se02-31",
  "number": 31,
  "prompt": "Esta mañana yo _______ un poco nerviosa antes de la clase.",
  "answers": ["estoy"],
  "canonicalAnswer": "estoy",
  "sentenceTranslations": { "estoy": "今天早上上课前我有点紧张。" }
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_homework_data.py tests/test_homework_type_navigation_runtime.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add examples/mi-espanol/homework.json tests/test_homework_data.py tests/test_homework_type_navigation_runtime.py
git commit -m "Restore the two items dropped by two-blank splits; fix se01-05 verbatim collision"
```

---

### Task 3: Lexicon collector script

**Files:**
- Create: `scripts/collect_lexicon.py`
- Test: `tests/test_collect_lexicon.py` (new)

**Interfaces:**
- Produces (imported by tests and Task 4): module functions
  - `surface_forms(word: str) -> set[str]`
  - `covered_tokens(assignment: dict, vocab_rows: list[dict]) -> set[str]`
  - `answer_sentences(item: dict) -> list[str]`
  - `uncovered_words(assignment: dict, vocab_rows: list[dict]) -> dict[str, list[str]]` (token → item ids)
  - `load_vocab_rows(project_root: Path) -> list[dict]` (reads `vocab.csv` with `csv.DictReader`)
  - CLI: `uv run python scripts/collect_lexicon.py examples/mi-espanol [--check]` — prints per-assignment gaps; `--check` exits 1 when any gap exists.

- [ ] **Step 1: Write failing unit tests**

Create `tests/test_collect_lexicon.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_collect_lexicon.py -v`
Expected: FAIL (file not found / attribute errors)

- [ ] **Step 3: Implement `scripts/collect_lexicon.py`**

```python
#!/usr/bin/env python
"""Scan homework answer sentences for words no lexicon source covers.

The learner page underlines a word in a completed answer sentence only when
one of three sources knows it: the assignment's studyWords, its
sentenceLexicon, or the project's core vocab.csv. This tool finds content
words none of them cover, so every generated assignment ships clickable
glosses.

Usage: uv run python scripts/collect_lexicon.py examples/mi-espanol [--check]
"""
import argparse
import csv
import json
import re
import sys
import unicodedata
from pathlib import Path

ARTICLES = {"el", "la", "los", "las", "un", "una", "unos", "unas"}
# Function words and ser/estar conjugations (the graded answers themselves)
# are exempt from coverage; everything else must have a gloss source.
STOPWORDS = ARTICLES | {
    "soy", "eres", "es", "somos", "sois", "son",
    "estoy", "estás", "está", "estamos", "estáis", "están",
    "ser", "estar",
    "de", "del", "al", "a", "en", "y", "e", "o", "u", "que", "qué",
    "con", "sin", "para", "por", "como", "pero", "porque", "si", "no", "ni",
    "se", "me", "te", "le", "les", "nos", "os", "lo",
    "mi", "mis", "tu", "tus", "su", "sus", "nuestro", "nuestra", "nuestros", "nuestras",
    "yo", "tú", "él", "ella", "usted", "ustedes", "nosotros", "nosotras",
    "vosotros", "vosotras", "ellos", "ellas",
    "este", "esta", "estos", "estas", "ese", "esa", "esos", "esas",
    "muy", "más", "menos", "también", "ya", "aquí", "ahí", "dónde", "quién",
    "cuál", "cómo", "cuándo", "verdad", "mío", "mía", "algo",
}
WORD_RE = re.compile(r"[a-záéíóúüñ]+", re.IGNORECASE)
BLANK = "_______"


def norm(text):
    return unicodedata.normalize("NFKC", str(text)).lower().strip()


def surface_forms(word):
    forms = set()
    for alt in re.split(r"\s*/\s*", norm(word)):
        if not alt:
            continue
        forms.add(alt)
        parts = alt.split()
        if len(parts) > 1 and parts[0] in ARTICLES:
            forms.add(" ".join(parts[1:]))
    return forms


def _entry_forms(entry):
    values = [entry.get("word") or ""]
    values += [v for v in (entry.get("forms") or []) if v]
    values += [v for v in (entry.get("answers") or []) if v]
    out = set()
    for value in values:
        out |= surface_forms(value)
    return out


def covered_tokens(assignment, vocab_rows):
    forms = set()
    for entry in assignment.get("studyWords") or []:
        forms |= _entry_forms(entry)
    for entry in assignment.get("sentenceLexicon") or []:
        forms |= _entry_forms(entry)
    for row in vocab_rows:
        if norm(row.get("kind") or "") == "grammar":
            continue
        if row.get("word"):
            forms |= surface_forms(row["word"])
    tokens = set()
    for form in forms:
        tokens.add(form)
        tokens |= set(form.split())
    return tokens


def answer_sentences(item):
    prompt = re.sub(r"\s*\([^)]*\)\s*$", "", str(item.get("prompt") or "")).strip()
    if BLANK not in prompt:
        return []
    return [prompt.replace(BLANK, answer) for answer in item.get("answers") or []]


def uncovered_words(assignment, vocab_rows):
    covered = covered_tokens(assignment, vocab_rows)
    missing = {}
    for section in assignment.get("sections") or []:
        for item in section.get("items") or []:
            for sentence in answer_sentences(item):
                for token in WORD_RE.findall(norm(sentence)):
                    if token in STOPWORDS or token in covered:
                        continue
                    ids = missing.setdefault(token, [])
                    if item.get("id") not in ids:
                        ids.append(item.get("id"))
    return missing


def load_vocab_rows(project_root):
    path = Path(project_root) / "vocab.csv"
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", help="project directory, e.g. examples/mi-espanol")
    parser.add_argument("--check", action="store_true",
                        help="exit 1 if any word is uncovered")
    args = parser.parse_args()
    root = Path(args.project)
    data = json.loads((root / "homework.json").read_text(encoding="utf-8"))
    vocab_rows = load_vocab_rows(root)
    gaps = 0
    for assignment in data.get("assignments") or []:
        missing = uncovered_words(assignment, vocab_rows)
        if not missing:
            continue
        gaps += len(missing)
        print(f"{assignment.get('id')}: {len(missing)} uncovered words")
        for token in sorted(missing):
            print(f"  {token}  ({', '.join(missing[token])})")
    if not gaps:
        print("all answer-sentence words are covered")
    if args.check and gaps:
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_collect_lexicon.py -v`
Expected: PASS

- [ ] **Step 5: Run the CLI to see the real gaps (no assertion, informational)**

Run: `uv run python scripts/collect_lexicon.py examples/mi-espanol`
Expected: prints uncovered word lists for the three ser/estar assignments (biblioteca etc.); exit 0 without `--check`.

- [ ] **Step 6: Commit**

```bash
git add scripts/collect_lexicon.py tests/test_collect_lexicon.py
git commit -m "Add lexicon collector: flag answer-sentence words without gloss coverage"
```

---

### Task 4: Backfill sentenceLexicon until coverage is clean; add the standing test

**Files:**
- Modify: `examples/mi-espanol/homework.json` (add `sentenceLexicon` arrays to `ser-estar-conjugation-a1`, `ser-estar-practice-a1-01`, `ser-estar-present-a1-02`)
- Test: `tests/test_homework_data.py`

**Interfaces:**
- Consumes: `collect_lexicon.uncovered_words` / `load_vocab_rows` from Task 3.
- Produces: zero uncovered words across all mi-espanol assignments; a permanent regression test.

- [ ] **Step 1: Add the standing coverage test (failing first)**

Append to `tests/test_homework_data.py`:

```python
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
```

(`MI_ESPANOL` and `Project` already exist in the file.)

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_homework_data.py::test_answer_sentence_words_have_gloss_coverage -v`
Expected: FAIL listing the uncovered words

- [ ] **Step 3: Author the missing sentenceLexicon entries**

For each word printed by `uv run python scripts/collect_lexicon.py examples/mi-espanol`, add an entry to the owning assignment's top-level `sentenceLexicon` array (create the array after `referenceTables` if absent), following the existing schema used by `ejercicios-vocabulario-a1-1`:

```json
{ "id": "se01-lx-biblioteca", "word": "biblioteca", "forms": ["la biblioteca"], "gloss": "图书馆", "english": "library" }
```

Conventions:
- id prefix per assignment: `se01-lx-*`, `se02-lx-*`, `conj-lx-*`; ids unique within the assignment.
- `word` is the dictionary form as it appears in the sentence (keep accents); put plural/feminine surface variants seen in sentences into `forms` (e.g. `"word": "abierto", "forms": ["abierta", "abiertos", "abiertas"]` — only variants that actually occur are required).
- `gloss` is the Chinese meaning, `english` the English one; both required (the app drops entries missing either).
- Write real glosses (the implementer writes them; they are ordinary A1 words). Do not machine-mangle accents.

Iterate: run the collector, add entries, repeat until it prints "all answer-sentence words are covered".

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_homework_data.py tests/test_homework_type_navigation_runtime.py -v`
Expected: PASS (including the new coverage test)

- [ ] **Step 5: Runtime spot-check that biblioteca is now clickable**

Append to the end of `NODE_RUNTIME_TEST` in `tests/test_homework_type_navigation_runtime.py` (before the closing `"""`):

```js
runtime.openHomework(bilingualSerEstar);
runtime.state.homeworkIndex = 2;
runtime.saveHomeworkAnswer("estamos");
runtime.checkHomeworkAnswer();
var sentenceHtml = runtime.dashboardHomeworkQuestionHtml(bilingualSerEstar);
assert(sentenceHtml.indexOf('homework-sentence-term" type="button" data-homework-sentence-word=') !== -1 &&
    sentenceHtml.indexOf("biblioteca<") !== -1,
  "biblioteca should render as a clickable sentence term after the lexicon backfill");
// note: the matched segment may include the article ("la biblioteca"), so match "biblioteca<" not ">biblioteca<"
```

Run: `uv run pytest tests/test_homework_type_navigation_runtime.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add examples/mi-espanol/homework.json tests/test_homework_data.py tests/test_homework_type_navigation_runtime.py
git commit -m "Backfill sentenceLexicon for ser/estar assignments; enforce coverage in CI"
```

---

### Task 5: First-attempt scoring (firstStatus)

**Files:**
- Modify: `fabulita/template.html`:
  - `homeworkProgress` sanitizer (~line 2652)
  - `saveHomeworkAnswer` (~line 3430)
  - `commitHomeworkAnswer` (~line 3461)
  - `homeworkStats` (~line 3165)
  - `dashboardHomeworkSummaryHtml` (~line 4440)
- Test: `tests/test_homework_first_attempt_runtime.py` (new)

**Interfaces:**
- Produces: `progress.responses[id].firstStatus` / `.firstCheckedAt` (write-once), `.mistakeResolvedAt` (used by Task 6); `homeworkStats` gains `firstCorrect`, `firstNear`, `firstIncorrect`; summary tiles count by first attempt.

- [ ] **Step 1: Write the failing runtime test**

Create `tests/test_homework_first_attempt_runtime.py` by copying the harness structure of `tests/test_homework_type_navigation_runtime.py` (same imports, same `bootPage` JS, same pytest driver building `examples/mi-espanol` into tmp). Set the injected export object to:

```js
    window.__homeworkFirstAttemptRuntimeTest = {
      state,
      homeworkAssignments,
      homeworkItems,
      homeworkProgress,
      homeworkStats,
      openHomework,
      saveHomeworkAnswer,
      checkHomeworkAnswer,
      retryHomeworkAnswers,
      dashboardHomeworkSummaryHtml
    };
```

Test body (replaces the assertions section; keep `bootPage`):

```js
const page = bootPage(process.argv[1]);
const runtime = page.runtime;
const assignment = runtime.homeworkAssignments.find(
  (candidate) => candidate.id === "ser-estar-practice-a1-01"
);
assert(assignment, "expected the bilingual ser/estar assignment");

runtime.openHomework(assignment);

// Item 0 (correct answer "está"): answer wrong first, then correct.
runtime.state.homeworkIndex = 0;
runtime.saveHomeworkAnswer("es");
assert(runtime.checkHomeworkAnswer() === true, "wrong answer should still grade");
let progress = runtime.homeworkProgress(assignment);
const itemId = runtime.homeworkItems(assignment)[0].item.id;
assert(progress.responses[itemId].status === "incorrect",
  "the wrong first answer should grade incorrect");
assert(progress.responses[itemId].firstStatus === "incorrect",
  "the first verdict should be recorded");

runtime.saveHomeworkAnswer("está");
runtime.checkHomeworkAnswer();
progress = runtime.homeworkProgress(assignment);
assert(progress.responses[itemId].status === "correct",
  "the corrected answer should grade correct");
assert(progress.responses[itemId].firstStatus === "incorrect",
  "firstStatus must never be overwritten by later attempts");

// Item 1 (correct answer "es"): correct on the first try.
runtime.state.homeworkIndex = 1;
runtime.saveHomeworkAnswer("es");
runtime.checkHomeworkAnswer();
progress = runtime.homeworkProgress(assignment);
const stats = runtime.homeworkStats(assignment, progress);
assert(stats.correct === 2, "current-state correct should count both items");
assert(stats.firstCorrect === 1 && stats.firstIncorrect === 1,
  "first-attempt stats should keep the initial mistake");

const summary = runtime.dashboardHomeworkSummaryHtml(assignment);
assert(summary.indexOf("<strong>1</strong><span>正确</span>") !== -1,
  "the summary tile should count first-attempt correct answers");
assert(summary.indexOf("订正后已答对 2 题") !== -1,
  "the summary should mention the corrected total");

// retry flow must not erase firstStatus
runtime.retryHomeworkAnswers(assignment);
progress = runtime.homeworkProgress(assignment);
assert(progress.responses[itemId] === undefined ||
    progress.responses[itemId].firstStatus === "incorrect",
  "retry reset must keep the first verdict");
```

Note: after the two answers above, item 0's status is correct so `retryHomeworkAnswers` only resets other (unanswered) items — the assertion tolerates both shapes.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_homework_first_attempt_runtime.py -v`
Expected: FAIL at "the first verdict should be recorded"

- [ ] **Step 3: Implement in `fabulita/template.html`**

(a) `homeworkProgress` sanitizer — after the `originalVerdict` line (~3666), add:

```js
      if (["correct", "near_miss", "incorrect"].indexOf(response.firstStatus) !== -1) {
        item.firstStatus = response.firstStatus;
      }
      if (isFinite(+response.firstCheckedAt) && +response.firstCheckedAt > 0) {
        item.firstCheckedAt = +response.firstCheckedAt;
      }
      if (isFinite(+response.mistakeResolvedAt) && +response.mistakeResolvedAt > 0) {
        item.mistakeResolvedAt = +response.mistakeResolvedAt;
      }
```

(b) `saveHomeworkAnswer` — the rebuilt response drops unknown fields; carry the first-attempt fields forward. After:

```js
    progress.responses[entry.item.id] = {
      answer: nextAnswer,
      updatedAt: Date.now()
    };
```

add:

```js
    if (previous.firstStatus) {
      progress.responses[entry.item.id].firstStatus = previous.firstStatus;
      if (previous.firstCheckedAt) progress.responses[entry.item.id].firstCheckedAt = previous.firstCheckedAt;
      if (previous.mistakeResolvedAt) progress.responses[entry.item.id].mistakeResolvedAt = previous.mistakeResolvedAt;
    }
```

(c) `commitHomeworkAnswer` — before `progress.responses[entry.item.id] = response;` add:

```js
    var previousResponse = progress.responses[entry.item.id] || {};
    if (previousResponse.firstStatus) {
      response.firstStatus = previousResponse.firstStatus;
      if (previousResponse.firstCheckedAt) response.firstCheckedAt = previousResponse.firstCheckedAt;
      if (previousResponse.mistakeResolvedAt) response.mistakeResolvedAt = previousResponse.mistakeResolvedAt;
    } else {
      response.firstStatus = grade.status;
      response.firstCheckedAt = response.checkedAt;
    }
```

Also add `firstVerdict: response.firstStatus,` to the `recordLearningEvent` payload (next to `verdict`).

(d) `homeworkStats` — extend to:

```js
  function homeworkStats(assignment, progress) {
    var stats = { total: 0, checked: 0, correct: 0, near: 0, incorrect: 0,
      firstCorrect: 0, firstNear: 0, firstIncorrect: 0 };
    homeworkItems(assignment).forEach(function (entry) {
      stats.total += 1;
      var response = progress.responses[entry.item.id];
      if (!response || !response.status) {
        if (response && response.firstStatus) {
          if (response.firstStatus === "correct") stats.firstCorrect += 1;
          else if (response.firstStatus === "near_miss") stats.firstNear += 1;
          else stats.firstIncorrect += 1;
        }
        return;
      }
      stats.checked += 1;
      if (response.status === "correct") stats.correct += 1;
      else if (response.status === "near_miss") stats.near += 1;
      else stats.incorrect += 1;
      var first = response.firstStatus || response.status;
      if (first === "correct") stats.firstCorrect += 1;
      else if (first === "near_miss") stats.firstNear += 1;
      else stats.firstIncorrect += 1;
    });
    return stats;
  }
```

(Counting `firstStatus` even when `status` was cleared by a retry keeps the
mistake visible in the summary; legacy records without `firstStatus` fall back
to `status`.)

(e) `dashboardHomeworkSummaryHtml` — switch the mark and the three verdict
tiles to first-attempt numbers and add the corrected-note. Replace the
`stats.correct` mark with `stats.firstCorrect`, the tiles block with:

```js
      '</p><div class="homework-summary-stats"><div class="homework-summary-stat"><strong>' + stats.total +
      '</strong><span>总题数</span></div><div class="homework-summary-stat"><strong>' + stats.firstCorrect +
      '</strong><span>正确</span></div><div class="homework-summary-stat"><strong>' + stats.firstNear +
      '</strong><span>' + (homeworkIsScenario(assignment) ? "意思正确，可优化" : "重音 / 拼写接近") +
      '</span></div><div class="homework-summary-stat"><strong>' + stats.firstIncorrect +
      '</strong><span>暂时不对</span></div></div>' +
```

and insert right before that block (after the 全部题目都已检查 paragraph):

```js
      (stats.correct > stats.firstCorrect ?
        '<p class="homework-summary-note">按第一次作答统计；订正后已答对 ' + stats.correct + ' 题。</p>' : '') +
```

Add CSS next to `.homework-summary-mark` (~line 901):

```css
  .homework-summary-note { margin: 0.2rem 0 0; color: var(--v-muted); font-size: 0.72rem; }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_homework_first_attempt_runtime.py tests/test_homework_runtime.py tests/test_homework_type_navigation_runtime.py -v`
Expected: PASS (if `tests/test_homework_runtime.py` asserts old summary numbers, update its expectations to first-attempt semantics — inspect before changing)

- [ ] **Step 5: Commit**

```bash
git add fabulita/template.html tests/test_homework_first_attempt_runtime.py tests/test_homework_runtime.py
git commit -m "Count homework results by first attempt; keep retry flow for correction"
```

---

### Task 6: 错题本 (mistake review) in the review column

**Files:**
- Modify: `fabulita/template.html`:
  - new functions near the homework helpers (`homeworkMistakeEntries`, `homeworkMistakeKey`, `resolveHomeworkMistake`, `homeworkMistakesHtml`)
  - `dashboardReviewHtml` (~line 4986) — render the block
  - `state` object (~line 1431) — add `mistakeOpenKey: ""`, `mistakeNotice: ""`, `mistakeShowResolved: false`
  - module scope near `homeworkRetryDrafts` (~line 2594) — add `var homeworkMistakeDrafts = Object.create(null);`
  - `document.addEventListener("click", ...)` (~line 5814) — new `data-mistake-*` branches
  - `document.addEventListener("input", ...)` (~line 6367) — mistake input branch
  - CSS — new `.homework-mistakes*` rules
- Test: `tests/test_homework_mistakes_runtime.py` (new)

**Interfaces:**
- Consumes: `firstStatus` / `mistakeResolvedAt` from Task 5.
- Produces: `homeworkMistakeEntries() -> [{assignment, entry, response, key, resolved}]`, `resolveHomeworkMistake(key, value) -> "correct"|"near_miss"|"incorrect"|""`, `homeworkMistakesHtml() -> string`.

- [ ] **Step 1: Write the failing runtime test**

Create `tests/test_homework_mistakes_runtime.py` (same harness pattern). Exports:

```js
    window.__homeworkMistakesRuntimeTest = {
      state,
      homeworkAssignments,
      homeworkItems,
      homeworkProgress,
      openHomework,
      saveHomeworkAnswer,
      checkHomeworkAnswer,
      homeworkMistakeEntries,
      resolveHomeworkMistake,
      homeworkMistakesHtml,
      dashboardReviewHtml
    };
```

Test body:

```js
const page = bootPage(process.argv[1]);
const runtime = page.runtime;
const assignment = runtime.homeworkAssignments.find(
  (candidate) => candidate.id === "ser-estar-practice-a1-01"
);
assert(assignment, "expected the bilingual ser/estar assignment");

assert(runtime.homeworkMistakeEntries().length === 0,
  "a fresh profile should have no mistakes");
assert(runtime.homeworkMistakesHtml().indexOf("还没有错题") !== -1,
  "the empty state should render");

runtime.openHomework(assignment);
runtime.state.homeworkIndex = 0;               // correct answer "está"
runtime.saveHomeworkAnswer("es");
runtime.checkHomeworkAnswer();                  // wrong on first attempt
runtime.saveHomeworkAnswer("está");
runtime.checkHomeworkAnswer();                  // corrected in the assignment

const entries = runtime.homeworkMistakeEntries();
assert(entries.length === 1, "the first-attempt mistake should be collected");
assert(entries[0].resolved === false, "the mistake starts unresolved");
const key = entries[0].key;

const listHtml = runtime.homeworkMistakesHtml();
assert(listHtml.indexOf("错题") !== -1 && listHtml.indexOf("data-mistake-open") !== -1,
  "the mistake block should render an openable entry");
assert(runtime.dashboardReviewHtml().indexOf("错题") !== -1,
  "the review column should include the mistake block");

assert(runtime.resolveHomeworkMistake(key, "es") === "incorrect",
  "a wrong redo should not resolve the mistake");
assert(runtime.homeworkMistakeEntries()[0].resolved === false,
  "an incorrect redo keeps the entry unresolved");

assert(runtime.resolveHomeworkMistake(key, "está") === "correct",
  "the correct redo should be graded");
const after = runtime.homeworkMistakeEntries();
assert(after.length === 1 && after[0].resolved === true,
  "the entry should be marked resolved");
const progress = runtime.homeworkProgress(assignment);
const itemId = runtime.homeworkItems(assignment)[0].item.id;
assert(progress.responses[itemId].firstStatus === "incorrect" &&
    progress.responses[itemId].status === "correct" &&
    progress.responses[itemId].mistakeResolvedAt > 0,
  "resolving must only stamp mistakeResolvedAt");
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_homework_mistakes_runtime.py -v`
Expected: FAIL (`homeworkMistakeEntries` undefined)

- [ ] **Step 3: Implement in `fabulita/template.html`**

(a) Helpers (place after `retryHomeworkAnswers`):

```js
  function homeworkMistakeKey(assignment, item) {
    return String(assignment.id) + "\n" + String(item.id);
  }
  function homeworkMistakeEntries() {
    var out = [];
    homeworkAssignments.forEach(function (assignment) {
      var progress = homeworkProgress(assignment);
      homeworkItems(assignment).forEach(function (entry) {
        var response = progress.responses[entry.item.id];
        if (!response || !response.firstStatus || response.firstStatus === "correct") return;
        out.push({
          assignment: assignment,
          entry: entry,
          response: response,
          key: homeworkMistakeKey(assignment, entry.item),
          resolved: !!response.mistakeResolvedAt
        });
      });
    });
    return out;
  }
  function resolveHomeworkMistake(key, value) {
    var found = homeworkMistakeEntries().filter(function (candidate) {
      return candidate.key === key;
    })[0];
    if (!found) return "";
    var verdict = homeworkVerdict(found.entry.item, value);
    if (verdict === "correct") {
      var progress = homeworkProgress(found.assignment);
      var response = progress.responses[found.entry.item.id];
      if (response) {
        response.mistakeResolvedAt = Date.now();
        saveHomeworkProgress(found.assignment, progress);
      }
      state.mistakeNotice = "已订正，做对了。";
      state.mistakeOpenKey = "";
      delete homeworkMistakeDrafts[key];
    } else {
      state.mistakeNotice = verdict === "near_miss" ? "意思接近了，再注意拼写或重音。" : "还不对，再想想。";
    }
    return verdict;
  }
```

(b) `homeworkMistakesHtml` (place next to `dashboardReviewHtml`):

```js
  function homeworkMistakesHtml() {
    var entries = homeworkMistakeEntries();
    var open = entries.filter(function (entry) { return !entry.resolved; });
    var resolved = entries.filter(function (entry) { return entry.resolved; });
    var h = '<section class="homework-mistakes" aria-label="错题复习"><div class="homework-mistakes-head"><h2>错题</h2><span>' +
      open.length + ' 待订正</span></div>';
    if (!entries.length) {
      return h + '<p class="homework-mistakes-empty">还没有错题。第一次没答对的题会出现在这里。</p></section>';
    }
    if (state.mistakeNotice) {
      h += '<p class="homework-mistakes-notice" role="status">' + esc(state.mistakeNotice) + "</p>";
    }
    h += '<ol class="homework-mistakes-list">';
    open.forEach(function (candidate) {
      var isOpen = state.mistakeOpenKey === candidate.key;
      h += '<li class="homework-mistake' + (isOpen ? " is-open" : "") + '">' +
        '<button class="homework-mistake-summary" data-mistake-open="' + esc(candidate.key) + '">' +
        '<span class="homework-mistake-title">' + esc(candidate.assignment.title || candidate.assignment.id) + " · 第 " +
        (candidate.entry.item.number || "?") + ' 题</span><span class="homework-mistake-prompt">' +
        esc(candidate.entry.item.prompt) + "</span></button>";
      if (isOpen) {
        if (candidate.entry.type === "single_choice") {
          h += '<div class="homework-mistake-options">';
          (candidate.entry.item.options || []).forEach(function (option) {
            h += '<button class="homework-mistake-option" data-mistake-option="' + esc(candidate.key) +
              '" data-mistake-value="' + esc(option) + '">' + esc(option) + "</button>";
          });
          h += "</div>";
        } else {
          h += '<div class="homework-mistake-redo"><input class="homework-mistake-input" data-mistake-input="' +
            esc(candidate.key) + '" value="' + esc(homeworkMistakeDrafts[candidate.key] || "") +
            '" autocomplete="off" lang="' + esc(P.config.lang || "") + '">' +
            '<button class="homework-mistake-check" data-mistake-check="' + esc(candidate.key) + '">检查</button></div>';
        }
      }
      h += "</li>";
    });
    h += "</ol>";
    if (resolved.length) {
      h += '<button class="homework-mistakes-toggle" data-mistake-toggle-resolved>已订正 ' + resolved.length +
        ' 题 ' + (state.mistakeShowResolved ? "收起" : "展开") + "</button>";
      if (state.mistakeShowResolved) {
        h += '<ol class="homework-mistakes-list is-resolved">';
        resolved.forEach(function (candidate) {
          h += '<li class="homework-mistake is-resolved"><span class="homework-mistake-prompt">' +
            esc(candidate.entry.item.prompt) + "</span></li>";
        });
        h += "</ol>";
      }
    }
    return h + "</section>";
  }
```

(c) Render inside the review column — in `dashboardReviewHtml`, change the tail:

```js
      reviewCardHtml() + '<div class="vocab-review-foot">回车检查答案 · 可直接看答案 · 1 没想起 · 2 其他 · 3 想起来了</div>' +
      homeworkMistakesHtml() + '</aside>';
```

(d) State + drafts: add to the `state` literal `mistakeOpenKey: "", mistakeNotice: "", mistakeShowResolved: false,` and near `homeworkRetryDrafts`:

```js
  var homeworkMistakeDrafts = Object.create(null);
```

(e) Click handler — inside the big `document.addEventListener("click", ...)`, before the final fallthrough, add:

```js
    if ((el = e.target.closest("[data-mistake-open]"))) {
      var mistakeKey = el.getAttribute("data-mistake-open");
      state.mistakeOpenKey = state.mistakeOpenKey === mistakeKey ? "" : mistakeKey;
      state.mistakeNotice = "";
      render();
      return;
    }
    if ((el = e.target.closest("[data-mistake-check]"))) {
      var checkKey = el.getAttribute("data-mistake-check");
      resolveHomeworkMistake(checkKey, homeworkMistakeDrafts[checkKey] || "");
      render();
      return;
    }
    if ((el = e.target.closest("[data-mistake-option]"))) {
      resolveHomeworkMistake(el.getAttribute("data-mistake-option"),
        el.getAttribute("data-mistake-value") || "");
      render();
      return;
    }
    if (e.target.closest("[data-mistake-toggle-resolved]")) {
      state.mistakeShowResolved = !state.mistakeShowResolved;
      render();
      return;
    }
```

(f) Input handler — inside `document.addEventListener("input", ...)`:

```js
    if (e.target && e.target.hasAttribute && e.target.hasAttribute("data-mistake-input")) {
      homeworkMistakeDrafts[e.target.getAttribute("data-mistake-input")] = e.target.value;
      return;
    }
```

(g) CSS (append near the `.vocab-review-*` rules):

```css
  .homework-mistakes { margin-top: 1rem; padding-top: 0.9rem; border-top: 1px solid var(--v-line); }
  .homework-mistakes-head { display: flex; align-items: baseline; justify-content: space-between; }
  .homework-mistakes-head h2 { margin: 0; font-size: 0.9rem; }
  .homework-mistakes-head span { color: var(--v-muted); font-size: 0.68rem; font-weight: 750; }
  .homework-mistakes-empty, .homework-mistakes-notice { margin: 0.6rem 0 0; color: var(--v-muted); font-size: 0.72rem; }
  .homework-mistakes-list { margin: 0.6rem 0 0; padding: 0; list-style: none; display: grid; gap: 0.5rem; }
  .homework-mistake { border: 1px solid var(--v-line); border-radius: 10px; background: rgba(255,255,255,0.72); }
  .homework-mistake-summary { display: block; width: 100%; padding: 0.6rem 0.7rem; border: 0; background: none; text-align: left; cursor: pointer; font: inherit; }
  .homework-mistake-title { display: block; color: var(--v-muted); font-size: 0.62rem; font-weight: 750; }
  .homework-mistake-prompt { display: block; margin-top: 0.2rem; font-size: 0.74rem; }
  .homework-mistake.is-resolved .homework-mistake-prompt { color: var(--v-muted); }
  .homework-mistake-redo { display: flex; gap: 0.45rem; padding: 0 0.7rem 0.65rem; }
  .homework-mistake-input { flex: 1; min-width: 0; padding: 0.4rem 0.55rem; border: 1px solid var(--v-line); border-radius: 8px; font: inherit; }
  .homework-mistake-check, .homework-mistakes-toggle { padding: 0.4rem 0.7rem; border: 1px solid var(--v-line); border-radius: 8px; background: #fff; cursor: pointer; font: inherit; font-size: 0.7rem; }
  .homework-mistakes-toggle { margin-top: 0.6rem; }
  .homework-mistake-options { display: flex; flex-wrap: wrap; gap: 0.45rem; padding: 0 0.7rem 0.65rem; }
  .homework-mistake-option { padding: 0.4rem 0.7rem; border: 1px solid var(--v-line); border-radius: 8px; background: #fff; cursor: pointer; font: inherit; font-size: 0.72rem; }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_homework_mistakes_runtime.py tests/test_homework_first_attempt_runtime.py tests/test_review_issue_runtime.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add fabulita/template.html tests/test_homework_mistakes_runtime.py
git commit -m "Add 错题本: first-attempt mistakes reviewable from the review column"
```

---

### Task 7: Bottom-right chat box

**Files:**
- Modify: `fabulita/template.html`:
  - constants + store functions near `HOMEWORK_LS` (~line 2589)
  - `chatWidgetHtml()` near `dashboardHtml`
  - `render()` (~line 5492) dashboard branch
  - `state` literal — add `chatOpen: false, chatDraft: ""`
  - click / input / keydown handlers
  - CSS
- Test: `tests/test_chat_widget_runtime.py` (new)

**Interfaces:**
- Produces: localStorage key `fabulita.chat.v1`; functions `chatMessages() -> [{id, role, text, at}]`, `sendChatMessage(text) -> boolean`, `chatWidgetHtml() -> string`. Reply text isolated in `chatAutoReply()` — the future LLM transport seam (`window.fabulitaLearningServices.chat`).

- [ ] **Step 1: Write the failing runtime test**

Create `tests/test_chat_widget_runtime.py` (same harness). Exports:

```js
    window.__chatWidgetRuntimeTest = {
      state,
      chatMessages,
      sendChatMessage,
      chatWidgetHtml
    };
```

Test body:

```js
const page = bootPage(process.argv[1]);
const runtime = page.runtime;

assert(runtime.chatMessages().length === 0, "chat history should start empty");
assert(runtime.chatWidgetHtml().indexOf("data-chat-toggle") !== -1,
  "the floating chat button should render");

runtime.state.chatOpen = true;
runtime.state.chatDraft = "帮我把这份作业换成新版本";
assert(runtime.sendChatMessage(runtime.state.chatDraft) === true,
  "sending a message should succeed");

const messages = runtime.chatMessages();
assert(messages.length === 2, "a send should store the message and the reply");
assert(messages[0].role === "user" &&
    messages[0].text === "帮我把这份作业换成新版本",
  "the user message should be stored verbatim");
assert(messages[1].role === "assistant" && messages[1].text === "收到",
  "the auto reply should be 收到");
assert(messages[0].at > 0 && messages[0].id, "messages carry id and timestamp");
assert(runtime.state.chatDraft === "", "the draft should clear after sending");

const stored = JSON.parse(page.localStorage.getItem("fabulita.chat.v1"));
assert(stored && stored.version === 1 && stored.scopes,
  "the chat store should persist under fabulita.chat.v1");

const html = runtime.chatWidgetHtml();
assert(html.indexOf("帮我把这份作业换成新版本") !== -1 && html.indexOf("收到") !== -1,
  "the open panel should render the conversation");

assert(runtime.sendChatMessage("   ") === false,
  "blank messages should be rejected");
assert(runtime.chatMessages().length === 2, "blank sends must not store anything");
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_chat_widget_runtime.py -v`
Expected: FAIL (`chatMessages` undefined)

- [ ] **Step 3: Implement in `fabulita/template.html`**

(a) Store (after the homework store functions, ~line 2634):

```js
  var CHAT_LS = "fabulita.chat.v1";
  var CHAT_MAX_MESSAGE = 2000;
  var CHAT_MAX_HISTORY = 200;
  function loadChatRoot() {
    var root = learningPersistence.loadSnapshot(CHAT_LS, null);
    if (root && root.version === 1 && root.scopes && typeof root.scopes === "object" && !Array.isArray(root.scopes)) {
      return root;
    }
    return { version: 1, scopes: {} };
  }
  function chatMessages() {
    var root = loadChatRoot();
    var scope = root.scopes[homeworkScopeKey];
    var list = scope && Array.isArray(scope.messages) ? scope.messages : [];
    return list.filter(function (message) {
      return message && (message.role === "user" || message.role === "assistant") &&
        typeof message.text === "string" && message.text;
    });
  }
  function appendChatMessage(role, text) {
    try {
      var root = loadChatRoot();
      var scope = root.scopes[homeworkScopeKey];
      if (!scope || typeof scope !== "object" || Array.isArray(scope)) scope = { messages: [] };
      if (!Array.isArray(scope.messages)) scope.messages = [];
      scope.messages.push({
        id: reviewEventNewId("chat"),
        role: role,
        text: String(text).slice(0, CHAT_MAX_MESSAGE),
        at: Date.now()
      });
      if (scope.messages.length > CHAT_MAX_HISTORY) {
        scope.messages = scope.messages.slice(-CHAT_MAX_HISTORY);
      }
      scope.updatedAt = Date.now();
      root.scopes[homeworkScopeKey] = scope;
      return learningPersistence.saveSnapshot(CHAT_LS, root);
    } catch (e) {
      return false;
    }
  }
  function chatAutoReply() {
    // Seam for a future LLM transport (window.fabulitaLearningServices.chat).
    return "收到";
  }
  function sendChatMessage(text) {
    var trimmed = String(text == null ? "" : text).trim();
    if (!trimmed) return false;
    if (!appendChatMessage("user", trimmed)) return false;
    appendChatMessage("assistant", chatAutoReply());
    state.chatDraft = "";
    return true;
  }
```

(b) `chatWidgetHtml` (place after `dashboardReviewHtml`):

```js
  function chatWidgetHtml() {
    var h = '<div class="chat-widget">';
    if (state.chatOpen) {
      var messages = chatMessages();
      h += '<section class="chat-panel" aria-label="需求对话"><header class="chat-panel-head"><h2>需求与反馈</h2>' +
        '<button class="chat-close" data-chat-toggle aria-label="收起对话框">×</button></header>' +
        '<div class="chat-log" role="log" aria-live="polite">';
      if (!messages.length) {
        h += '<p class="chat-empty">想调整作业、报告问题或提需求，直接发在这里。</p>';
      }
      messages.forEach(function (message) {
        h += '<p class="chat-message is-' + message.role + '">' + esc(message.text) + "</p>";
      });
      h += '</div><form class="chat-compose" id="chat-form"><input class="chat-input" id="chat-input" ' +
        'autocomplete="off" maxlength="' + CHAT_MAX_MESSAGE + '" placeholder="输入消息…" value="' + esc(state.chatDraft) + '">' +
        '<button class="chat-send" type="submit" data-chat-send>发送</button></form>' +
        '<p class="chat-note">消息仅保存在这个浏览器中；稍后会接入智能助手处理。</p></section>';
    }
    h += '<button class="chat-fab" data-chat-toggle aria-expanded="' + state.chatOpen + '" aria-label="打开需求对话框">💬</button></div>';
    return h;
  }
```

(c) `render()` dashboard branch:

```js
    if (VOCAB_DASHBOARD) {
      app.className = "wrap vocab-dashboard-wrap";
      app.innerHTML = dashboardHtml() + chatWidgetHtml();
      return;
    }
```

(d) `state` literal: add `chatOpen: false, chatDraft: "",`

(e) Click handler additions (same delegated listener):

```js
    if (e.target.closest("[data-chat-send]")) {
      e.preventDefault();
      var chatInput = document.getElementById("chat-input");
      if (chatInput) state.chatDraft = chatInput.value;
      sendChatMessage(state.chatDraft);
      render();
      return;
    }
    if (e.target.closest("[data-chat-toggle]")) {
      state.chatOpen = !state.chatOpen;
      render();
      return;
    }
```

(`data-chat-send` must be matched before `data-chat-toggle` — the send button sits inside the panel, the toggle test would not match it, but keep this order anyway for clarity.)

Also add a submit guard so Enter in the input sends instead of reloading: in the keydown listener add

```js
    if (e.key === "Enter" && e.target && e.target.id === "chat-input") {
      e.preventDefault();
      state.chatDraft = e.target.value;
      sendChatMessage(state.chatDraft);
      render();
      return;
    }
```

(f) Input handler:

```js
    if (e.target && e.target.id === "chat-input") {
      state.chatDraft = e.target.value;
      return;
    }
```

(g) CSS (append near the end of the stylesheet):

```css
  .chat-widget { position: fixed; right: 1.1rem; bottom: 1.1rem; z-index: 60; display: flex; flex-direction: column; align-items: flex-end; gap: 0.6rem; }
  .chat-fab {
    width: 3rem; height: 3rem; border: 0; border-radius: 50%; background: var(--v-accent); color: #fff;
    font-size: 1.25rem; cursor: pointer; box-shadow: 0 6px 18px rgba(0,0,0,0.18);
  }
  .chat-panel {
    width: min(20rem, calc(100vw - 2.2rem)); max-height: 24rem; display: flex; flex-direction: column;
    border: 1px solid var(--v-line); border-radius: 14px; background: #fff; box-shadow: 0 10px 30px rgba(0,0,0,0.16); overflow: hidden;
  }
  .chat-panel-head { display: flex; align-items: center; justify-content: space-between; padding: 0.6rem 0.8rem; border-bottom: 1px solid var(--v-line); }
  .chat-panel-head h2 { margin: 0; font-size: 0.8rem; }
  .chat-close { border: 0; background: none; font-size: 1rem; cursor: pointer; color: var(--v-muted); }
  .chat-log { flex: 1; min-height: 6rem; overflow-y: auto; padding: 0.7rem 0.8rem; display: flex; flex-direction: column; gap: 0.45rem; }
  .chat-empty, .chat-note { margin: 0; color: var(--v-muted); font-size: 0.68rem; }
  .chat-note { padding: 0 0.8rem 0.6rem; }
  .chat-message { margin: 0; max-width: 85%; padding: 0.42rem 0.6rem; border-radius: 10px; font-size: 0.74rem; white-space: pre-wrap; }
  .chat-message.is-user { align-self: flex-end; background: var(--v-accent-soft); }
  .chat-message.is-assistant { align-self: flex-start; background: #f1efe9; }
  .chat-compose { display: flex; gap: 0.45rem; padding: 0.55rem 0.8rem; border-top: 1px solid var(--v-line); }
  .chat-input { flex: 1; min-width: 0; padding: 0.45rem 0.6rem; border: 1px solid var(--v-line); border-radius: 9px; font: inherit; font-size: 0.74rem; }
  .chat-send { padding: 0.45rem 0.8rem; border: 0; border-radius: 9px; background: var(--v-accent); color: #fff; cursor: pointer; font: inherit; font-size: 0.72rem; }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_chat_widget_runtime.py tests/test_learning_persistence_runtime.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add fabulita/template.html tests/test_chat_widget_runtime.py
git commit -m "Add bottom-right chat box storing conversations locally with 收到 auto-reply"
```

---

### Task 8: Verbatim local assignments + `--local` build + guard hardening

**Files:**
- Create: `examples/mi-espanol/homework.local.json` (gitignored — verify with `git status` after creating)
- Modify: `.gitignore`, `fabulita/project.py`, `fabulita/build.py`, `scripts/build_docs.py`
- Test: `tests/test_homework_data.py` (guard hardening), `tests/test_fabulita.py` (local-build behavior)

**Interfaces:**
- Consumes: `Project._read`, `build.payload/_homework_payload/build`.
- Produces: `Project.local_homeworks` property; `build.payload(..., include_local_homework=False)` and `build.build(..., include_local_homework=False)`; `scripts/build_docs.py --local` emitting `docs/mi-espanol.local.html`.

- [ ] **Step 1: gitignore first (before the content file exists)**

Append to `.gitignore` under the "Third-party classroom material" block:

```
examples/*/homework.local.json
docs/*.local.html
```

Run: `git check-ignore examples/mi-espanol/homework.local.json docs/mi-espanol.local.html`
Expected: both paths print (ignored)

- [ ] **Step 2: Write failing build tests**

Append to `tests/test_fabulita.py` (it already imports `build` and `Project`; mirror its tmp-project fixtures):

```python
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
```

(If `Project(root)` requires more config keys, copy the minimal config dict other tests in `test_fabulita.py` use.)

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_fabulita.py::test_local_homework_appends_only_when_requested -v`
Expected: FAIL (unexpected keyword `include_local_homework`)

- [ ] **Step 4: Implement**

`fabulita/project.py` — next to `HOMEWORK_FILE = "homework.json"` add `LOCAL_HOMEWORK_FILE = "homework.local.json"`, and after the `homeworks` property:

```python
    @property
    def local_homeworks(self):
        """Private verbatim assignments; never shipped in committed builds."""
        data = self._read(LOCAL_HOMEWORK_FILE, {"assignments": []})
        assignments = data.get("assignments", []) if isinstance(data, dict) else []
        return assignments if isinstance(assignments, list) else []
```

`fabulita/build.py`:
- `_homework_payload(project, include_local=False)`: iterate `list(project.homeworks) + (list(project.local_homeworks) if include_local else [])` instead of `project.homeworks`.
- `payload(project, include_candidates=True, home=None, include_local_homework=False)`: pass through to `_homework_payload`.
- `build(project, out=None, include_candidates=True, home=None, include_local_homework=False)`: pass through to `payload`.

`scripts/build_docs.py`:

```python
import argparse
```

In `main()`, accept the flag and build the extra page after the public one inside the `VOCAB_APPS` loop:

```python
def main(local=False):
    ...
    for project_name, output_name in VOCAB_APPS.items():
        ...existing public build...
        local_source = project_root / "homework.local.json"
        if local and local_source.exists():
            local_name = output_name.replace(".html", ".local.html")
            page, psize, n, clips = build.build(
                vocab_project,
                out=DOCS / local_name,
                include_candidates=False,
                home="index.html",
                include_local_homework=True,
            )
            print("wrote " + str(page) + " (local, " + str(psize // 1024) + " KB)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--local", action="store_true",
                        help="additionally build docs/*.local.html with homework.local.json appended")
    main(local=parser.parse_args().local)
```

- [ ] **Step 5: Run the build test**

Run: `uv run pytest tests/test_fabulita.py -v`
Expected: PASS

- [ ] **Step 6: Author `examples/mi-espanol/homework.local.json`**

Top-level shape: `{"version": 1, "assignments": [<pdf1>, <pdf2>]}`. Both assignments: `"teacher"` set to the original teacher's name (kept only in the gitignored local file), `"level": "A1"`, `"badge": "原样 · 本地"`, `"contentOrigin": "verbatim_private"`, `"answerKeyBasis": "inferred_from_context"`, `"source": {}`, one `text_input` section each, and copy the two `referenceTables` blocks verbatim from `ser-estar-practice-a1-01` (ids prefixed `v1-`/`v2-`).

Assignment 1 — `"id": "ser-estar-verbatim-01"`, `"title": "Ser y Estar 原样练习 1（现在时填空）"`, `"sourceTitle": "Ejercicio de conjugación: SER y ESTAR en presente"`, section `{"id": "v1-items", "title": "Completa las oraciones", "type": "text_input"}` with the PDF's own instruction line as `instructions`. Items `v1-01` … `v1-30` (two-blank #22 split into `v1-22a`/`v1-22b`, numbers 22 and 23, all later numbers shifted +1 so numbers stay sequential 1..31; 31 items total). Item prompts are the PDF sentences verbatim with the blank as `_______`.

> **Note:** The verbatim item tables (prompts, answers, 中文 translations) are intentionally NOT in this committed plan. They live in the gitignored `examples/mi-espanol/homework.local.json` (already authored); the structure is: assignment 1 = 31 items `v1-01`…`v1-30` with the `v1-22a`/`v1-22b` split, assignment 2 = 21 items `v2-01`…`v2-20` with the `v2-15a`/`v2-15b` split; dual-answer items `v1-10`/`v1-14`/`v1-23`/`v2-12` carry an `ambiguityNote` (mirroring the `se02-10` wording) with both answers in `answers` (canonical first) and both `sentenceTranslations` keys.

Assignment 2 — `"id": "ser-estar-verbatim-02"`, `"title": "Ser y Estar 原样练习 2（双语练习）"`, `"sourceTitle": "SER / ESTAR – Practice"`, section `{"id": "v2-items", "title": "Práctica", "type": "text_input"}` with the PDF's own instruction line as `instructions`. Prompts keep the PDF's English parenthetical verbatim. Items `v2-01` … `v2-20` (two-blank #15 split into `v2-15a`/`v2-15b`; numbers sequential 1..21):

(Item table intentionally omitted — see the note under Assignment 1.)

Each item gets `number` (sequential), `canonicalAnswer` (first answer), and `sentenceTranslations` keyed by every accepted answer (dual-answer items use the two-key form like `se01-12` in homework.json).

- [ ] **Step 7: Harden the worksheet guard test**

Append to `tests/test_homework_data.py` two tests (no verbatim string or the teacher's name may be committed in the test file itself):

- `test_verbatim_worksheet_content_never_ships` — derives its fingerprints at test time from the gitignored `homework.local.json` via a `_verbatim_fingerprints()` helper (the teacher field plus, per item prompt, the sentence pieces around the `_______` blank compiled into an order-preserving bounded-gap regex, so both the raw-blank and answer-filled forms are caught while rewritten public items that legitimately share half a sentence are not). Skips when the local file is absent. Scans EVERY git-tracked file (`git ls-files`), skipping only undecodable binaries, and asserts no fingerprint matches anywhere.
- `test_local_homework_file_is_gitignored` — `git check-ignore examples/mi-espanol/homework.local.json docs/mi-espanol.local.html` must exit 0.

(Add `import subprocess` to the file if missing.)

- [ ] **Step 8: Build the local page and run everything**

Run: `uv run python scripts/build_docs.py --local`
Expected: normal outputs plus `wrote docs/mi-espanol.local.html (local, ...)`; `git status --short docs/` shows only the regular generated pages, no `.local.html`.

Run: `uv run pytest tests/test_homework_data.py tests/test_fabulita.py -v`
Expected: PASS

Sanity: `uv run python - <<'EOF'` … load `docs/mi-espanol.local.html`, assert `"ser-estar-verbatim-01"` and a distinctive verbatim fragment (pick one from the gitignored `homework.local.json` at run time — do not write it into any committed file) are present; load `docs/mi-espanol.html`, assert both absent. `EOF` (or do the equivalent check with grep, again taking the fragment from the local file only).

- [ ] **Step 9: Commit (verify staging excludes the local file)**

```bash
git status --short   # homework.local.json and *.local.html must NOT appear
git add .gitignore fabulita/project.py fabulita/build.py scripts/build_docs.py tests/test_fabulita.py tests/test_homework_data.py
git commit -m "Support gitignored verbatim homework.local.json via build_docs --local"
```

---

### Task 9: Rebuild docs, full suite, memory, wrap-up

**Files:**
- Modify: `docs/mi-espanol.html`, `docs/my-english.html` (regenerated)
- Create: `<memory-dir>/pdf-homework-origin-declaration.md`
- Modify: `<memory-dir>/MEMORY.md`

- [ ] **Step 1: Regenerate all docs pages (public + local)**

Run: `uv run python scripts/build_docs.py --local`
Expected: all pages written; `git status` shows changes only to committed generated pages (mi-espanol.html, my-english.html, possibly demo pages), never `*.local.html`.

- [ ] **Step 2: Full test suite**

Run: `uv run pytest -q`
Expected: PASS. If a runtime test still asserts pre-firstStatus summary markup, fix the expectation (the behavior change is intentional and spec'd).

- [ ] **Step 3: Write the process-rule memory**

Create `pdf-homework-origin-declaration.md` in the memory directory:

```markdown
---
name: pdf-homework-origin-declaration
description: 从 PDF 生成作业前必须先问用户要改写版还是原样版；原样只进 homework.local.json
metadata:
  type: feedback
---

从课堂 PDF 生成作业时，先让用户声明要哪种形态，不要默认改写。

**Why:** 2026-07 用户发现 ser/estar 作业与原 PDF 不一致（supermercado→biblioteca 等），
以为是扫描错误；实际是上一轮为规避版权做的静默差异化改写，且拆分双空题时还丢了两道题。
用户明确表示："下次应该让用户声明是差异化改写还是要原样的"。

**How to apply:** 生成前问一次：改写版（可开源，进 examples/*/homework.json，逐题保留语法考点、
换专名）还是原样版（仅本地，进 gitignored examples/*/homework.local.json，
用 `scripts/build_docs.py --local` 构建 docs/*.local.html）。原样内容绝不进公开产物，
守护测试：tests/test_homework_data.py::test_verbatim_worksheet_content_never_ships。
改写版必须跑 `scripts/collect_lexicon.py --check` 保证答案句词表覆盖。见 [[project-fabulita]]、
[[my-english-vps-ops]]。
```

Append to `MEMORY.md`:

```markdown
- [PDF→作业需先声明改写/原样](pdf-homework-origin-declaration.md) — 原样只进 homework.local.json，绝不入库
```

- [ ] **Step 4: Final commit**

```bash
git status --short   # confirm no *.local.* files staged
git add docs/
git commit -m "Rebuild docs pages with progress fix, first-attempt scoring, 错题本, chat box"
```

- [ ] **Step 5: Report**

Summarize for the user: what shipped, where the local verbatim page lives (`docs/mi-espanol.local.html`, open directly in a browser), and that `uv run python scripts/build_docs.py --local` regenerates it.

---

## Self-Review Notes

- Spec §1→Task 1, §2→Tasks 3+4, §3→Task 5, §4→Task 6, §5→Task 7, §6→Task 2, §7→Task 8 (+memory in Task 9). Testing section→per-task tests + Task 9 full suite.
- Deviation from spec, intentional: the chat auto-reply is synchronous (no artificial delay) to keep the runtime deterministic; the LLM seam (`chatAutoReply`) is where async replaces it later.
- Spec's "verbatim 30/20 items" counts become 31/21 stored items because the app grades one blank per item; no content is lost (each split half shows the full original sentence).
- Line numbers cited are as of commit fa2a335; locate by function name if drifted.
