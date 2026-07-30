# Homework UX, scoring, lexicon coverage, verbatim-local assignments — design

Date: 2026-07-29
Target app: `fabulita/template.html` (single source; `uv run python scripts/build_docs.py`
regenerates `docs/mi-espanol.html` and `docs/my-english.html`). Data: `examples/mi-espanol/homework.json`.

## Background

User feedback on the mi-espanol homework flow surfaced five product issues plus two
data issues found while auditing the source PDFs (`Ejercicio_SER_y_ESTAR_1/2.pdf`):

- The question-type progress card renders a broken orange blob.
- Words in completed answer sentences (e.g. "biblioteca") are not underlined/clickable
  because three assignments ship no `sentenceLexicon` and there is no coverage check.
- Results page counts retry-until-correct as 正确 (20/20 despite first-try mistakes).
- No wrong-answer review (错题本).
- No chat entry point for sending requests/feedback (future LLM channel).
- Data audit: the JSON adaptations are correct (56/56 answer keys verified) but each
  PDF lost one item when a two-blank item was split in two (PDF2 #19, the possession
  question about shoes; PDF1 #30, the sadness item), and se01-05 accidentally
  reproduced PDF1 #27 (the open-windows item) verbatim.
- User additionally wants a **verbatim** copy of both worksheets for personal use.
  Open-source red line (NOTICE + `.gitignore` + guard test): verbatim classroom
  material must never enter the committed repo or published pages.

## 1. Progress card UI fix

Root cause: `.homework-type-track` (a `<span>`) lacks `display:block`; inside the
non-flex `button.homework-type-card` it stays inline, so its height collapses and the
inner accent bar escapes as a blob (template CSS around the `.homework-type-*` rules).

Fix: give the track `display:block` (keep `<span>` markup); tidy spacing/active state
of `.homework-type-card` minimally. No redesign.

## 2. Lexicon collector (生成期词语收录器)

New `scripts/collect_lexicon.py`:

- Loads a homework JSON plus the project's `vocab.csv` (source of the page's built-in
  core vocab) for a given example project (default `examples/mi-espanol`).
- For every item, resolves each answer into the prompt (same rule as the app's
  `homeworkResolvedSentence`: replace the `_______` blank per answer) and tokenizes.
- Mirrors the app's matching rules: case/accent-preserving lookup over
  `studyWords` answers/word, `sentenceLexicon` word+forms, core vocab words, with
  leading-article stripping (el/la/los/las/un/una/unos/unas) and `a/b` alternative
  splitting, longest-match not required — word-level coverage is enough.
- Output: per-assignment list of uncovered words (deduped, with the sentences they
  appear in). `--check` exits non-zero when anything is uncovered (for tests/CI).

Backfill (this change): add `sentenceLexicon` entries (id, word, forms, gloss zh,
english) for every uncovered word in `ser-estar-conjugation-a1`,
`ser-estar-practice-a1-01`, `ser-estar-present-a1-02`. Glosses hand-written.

Test: `tests/test_homework_data.py` gains a coverage assertion reusing the collector
module, so future assignments that skip lexicon authoring fail CI.

## 3. First-attempt scoring (firstStatus)

- `commitHomeworkAnswer` writes `firstStatus` + `firstCheckedAt` into
  `progress.responses[itemId]` only when `firstStatus` is absent; never overwritten
  afterwards. `saveHomeworkAnswer` / `retryHomeworkAnswers` keep clearing `status`
  only. Full assignment reset (`deleteHomeworkProgress`) clears everything.
- `homeworkStats` gains first-attempt tallies; the results page (本次作业结果) tiles
  count by `firstStatus` (fallback to `status` for legacy records without it).
  Current/corrected state still drives per-item feedback and retry flow. If every
  first attempt was correct the copy stays as-is; otherwise the tile subtitle notes
  订正后 status where helpful (small copy tweak, not a second tile row).
- Type-switcher "已检查" counts remain based on `status` (checked = has status).

## 4. 错题本 (mistake review)

- Review tab (复习) gains a 错题 block listing every item across assignments whose
  `firstStatus` is not `correct` and which has no `mistakeResolvedAt`.
- Each entry re-renders the original question (prompt, text input or options) and
  grades with the existing verdict pipeline. On a correct answer the app stamps
  `responses[itemId].mistakeResolvedAt` (progress store `fabulita.homework.v1`);
  the entry moves to a collapsed 已订正 list.
- Redoing an item in the 错题本 never mutates `firstStatus` or the assignment's
  current `status`/answer record beyond `mistakeResolvedAt`.

## 5. Chat box (右下角对话框)

- Floating button bottom-right on all dashboard views; opens a panel with message
  history + input.
- Storage: new key `fabulita.chat.v1`, same scope layout as other stores
  (`{version:1, scopes:{[scope]:{messages:[{id, role: "user"|"assistant", text, at}]}}}`).
- On send: append user message, then append assistant reply "收到" (fixed string,
  small delay). Reply generation isolated in one function so a future
  `window.fabulitaLearningServices.chat` transport can replace it.

## 6. Public-data corrections (rewritten assignments stay public)

- `ser-estar-practice-a1-01`: append item 21 = rewritten equivalent of PDF2 #19
  (the possession question about shoes: plural possession → "son"); replace
  se01-05's sentence with a rewrite that no longer collides verbatim with PDF1 #27.
- `ser-estar-present-a1-02`: append item 31 = rewritten equivalent of PDF1 #30
  (the sadness item: mood → "estoy").
- New items follow the existing rewrite convention (swap nouns/proper names, keep
  the grammar point, Chinese sentence translations, pseudonymized names) and get
  sentenceLexicon coverage per §2.

## 7. Verbatim assignments — local only (追加, not shipped)

- New gitignored file `examples/mi-espanol/homework.local.json`: verbatim
  transcription of both PDFs as two additional assignments (PDF1 → 30 items,
  PDF2 → 20 items; the app grades one blank per item, so the two two-blank items
  become two sub-items 22a/22b and 15a/15b, each showing the full original
  sentence with the other blank filled; the original teacher's name is kept
  only in the gitignored local file), marked `contentOrigin: "verbatim_private"`, badge
  原样 · 本地. Dual-accept answers (flores bonitas, hotel caro, comida deliciosa,
  gazpacho frío…) mirrored from the audited answer key.
- Build: `scripts/build_docs.py --local` (default off). When the flag is set and
  `homework.local.json` exists, build an extra page `docs/mi-espanol.local.html`
  whose assignment list = public assignments + verbatim assignments (append).
  Public outputs are byte-identical with or without the local file present.
- `.gitignore`: add `examples/*/homework.local.json` and `docs/*.local.html`.
- Guard test hardening: extend
  `test_mi_espanol_does_not_ship_the_classroom_worksheet` with verbatim
  fingerprints (the teacher's name plus per-sentence fragments, derived at test
  time from the gitignored `homework.local.json` so none of them is ever
  committed) that must never appear in any git-tracked file (the `.local.html`
  file is not committed and not scanned).
- Process rule → project memory: future pdf→homework generation must ask the user
  up front: 差异化改写 (publishable) vs 原样 (local-only file). Recorded as a
  `feedback` memory.

## Testing

- Runtime tests (Node-driven, following `test_homework_type_navigation_runtime.py`
  patterns): firstStatus write-once + stats-by-first-attempt; 错题本 listing and
  resolution; chat store append + auto-reply; progress-track regression can be a
  simple CSS presence assertion.
- Data tests: lexicon coverage (§2), guard-test hardening (§7), existing
  `test_homework_data.py` invariants for the new/changed items.
- Rebuild `docs/` via `uv run python scripts/build_docs.py` and run the full
  pytest suite.

## Out of scope

- A real pdf→homework generation pipeline (with per-item fidelity diffing) — future
  project; the declaration rule in §7 is its seed.
- LLM chat backend; visual redesign beyond the progress card fix; reviewBridge
  spaced-repetition integration for mistakes.
