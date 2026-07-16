# Two-tab IA: word-list database + story generation

Date: 2026-07-16
Status: approved (design confirmed in conversation; multi-select + LLM-pick
explicitly requested; list-per-language, per-language storybooks and
auto-migration adopted from the confirmed draft)
Scope: `docs/index.html` only (studio/reader/CLI untouched; they keep working
through the mapping below).

## Problem

The add-vocab widget conflates uploading words with generating stories, and
"project" hides the user's real mental model: a database of word lists
(tables, like CSVs) plus a separate generation flow that draws on them.

## Design

### Data mapping (no new storage schema)

**词表 (list) = one project** in `fabulita.studio.projects`
(`{id, config:{name, lang, gloss_lang, ui_default}, vocab, glossary, stories}`).
This keeps studio, reader.html aggregation, export and `unpack` working
unchanged. The `uploads[]` batch concept is retired from the UI (lists ARE
the tables now); the field stays in storage for old data but is no longer
written.

- Coverage becomes **language-wide**: a list's covered words = its words ∩
  union(vocab_used) across ALL projects with the same `config.lang`.
  New helper `langCovered(lang)` returns that set; per-list coverage and
  generation-uncovered both use it.
- Stories still physically live inside some project; users see them only
  through the per-language storybook (reader.html) — which project holds a
  story is an implementation detail. A kept story is stored in the FIRST
  selected list of the generation.

### One-time migration (guarded, lossless)

On load, if `localStorage["fabulita.lists.v2"]` is absent:
1. Back up the raw projects JSON to
   `fabulita.studio.projects.backupV1` (never overwritten afterwards).
2. For every existing project that has `uploads[]` batches: split each
   batch into its own project/list (name = batch name, lang/gloss_lang
   inherited; words = the batch's words with their glosses). Words not in
   any batch stay in the original project, which is renamed only if it
   would otherwise be empty-named. Stories remain in the original project
   (coverage is language-wide, so nothing is lost).
3. Set the guard key. Projects without uploads migrate as-is (they are
   already single lists).

### Widget IA: two tabs

Tab bar at the top of the widget body: **词表** | **生成故事**
(`state.tab`), replacing the current input/loop entry flow. The separate
"继续我的项目" card section is removed (superseded by the 词表 tab).

**Tab 1 词表 (default)**
- Table of lists: name · language · word count · covered x/n; click a row
  to expand a detail view: word chips with covered styling, export
  (copy/TSV — existing helpers), and "加词到这张表".
- 「＋ 新建词表」: name + learning-language select → creates an empty list
  (gloss_lang from UI language, as today).
- 「上传 / 粘贴」flow (existing parse pipeline incl. PDF + AI parse stays):
  the confirm step gains a TARGET selector — "加进已有词表" (dropdown of
  lists matching the chosen learning language) or "新建词表" (name input,
  prefilled from filename). No generation is started on confirm.

**Tab 2 生成故事**
- Multi-select the source lists (checkbox rows; must share one language —
  selecting a list of another language deselects the others or is disabled).
- Word source within the selection:
  - **全部未覆盖**(default): uncovered union, first 20.
  - **手动选词**: clickable chips from the union (covered picks allowed,
    cap 20) — existing picker behavior.
  - **LLM 挑词**(new): the prompt receives ALL uncovered words of the
    selection (cap 120 by list order) and instructs the model to CHOOSE
    10-20 words that naturally fit one coherent scene — favoring words that
    combine well — and write the story with them. Same JSON contract;
    `vocab_used` reports what it chose; validation unchanged.
- Generate/preview/keep/reroll loop reuses the existing machinery
  (provider plumbing, timeouts, manual mode paste). Kept story → first
  selected list's project → appears in the language storybook.
- Coverage bar shows the selection's coverage (language-wide covered set).

### Kept behaviors

Provider settings block, manual copy-prompt mode, my-storybook cards,
reader.html, export helpers, all i18n locales (every new string ×4).

## Out of scope

- List rename/delete; cross-language selection; de-duplicating words shared
  by two lists (they count for both lists' coverage; generation unions and
  dedupes by norm(w)); studio UI changes.

## Error handling

| Case | Behavior |
| --- | --- |
| Upload confirm with "加进已有词表" but none exists for that language | target selector shows only 新建词表 option |
| Generate with 0 lists selected | inline hint, no request |
| LLM-pick returns words outside the pool | existing validateStory warnings (keep allowed) |
| Migration runs on corrupted project entries | skip the bad entry, keep backup intact |

## Testing

Agent-driven browser QA (standing criteria: middle-schooler usability;
fresh words for non-manual sources): migration correctness against the
existing real data (backup key present, batches became lists, stories
readable in reader), both tabs' flows end-to-end incl. LLM-pick via the
codex bridge, multi-select union behavior, target-selector upload into an
existing list.
