# My storybook (per-language reader) + named upload records

Date: 2026-07-16
Status: approved (design confirmed in conversation)
Scope: `fabulita/template.html`, `fabulita/build.py`, `fabulita/cli.py`, new artifact `docs/reader.html`, `docs/index.html`.

## Problem

1. Accepted stories pile up inside a project (localStorage) but there is no
   reading experience for them — the demo books (demo-es.html) are static
   builds. The user wants: press keep/add on a story → it lands in "the
   storybook of that language", readable like the demos.
2. Uploaded vocabulary vanishes into a flat project list. The user wants a
   vocabulary view with upload history: each upload batch gets a name (e.g.
   "第X单元"), date, and per-word coverage status.

## Design

### A. Per-language "my storybook" (`reader.html`)

- **Reader reuse, not rewrite.** `fabulita/template.html` (the demo-book
  reader; already renders multi-story `P.stories`) gains a *self-serve*
  mode: when the injected payload has `P.self === true`, a hydration block
  (top of the main IIFE, before `var UI = P.ui;`) reads
  `location.hash` (`#lang=es`), loads
  `localStorage["fabulita.studio.projects"]`, and merges every project with
  `config.lang === <lang>`: accepted stories concatenated, `vocab` deduped
  by `norm(w)`, `glossary` object-merged, `gloss_lang` from the first
  matching project, `P.audio = {}`. `P.config.name` = the single project's
  name, or `first + " +N"` when several. Demo/exported pages inject a full
  payload (`self` absent) → zero behavior change.
- **New build artifact `docs/reader.html`**: `build.py` gains
  `build_reader(out)` — injects `{self: true, ui: UI_STRINGS, uiLangs:
  UI_LANGS, config: {…, home: "index.html"}, stories: [], vocab: [],
  glossary: {}, audio: {}}` into the template (same two `.replace` calls as
  `build()`), CLI subcommand `fabulita reader [--out]` (project-less, like
  `studio`). The artifact is committed under docs/ like studio.html.
- **Landing page cards**: `docs/index.html` — below the demo BOOKS row,
  one card per language that has ≥1 accepted story across all localStorage
  projects: "我的西语故事书 · N 篇故事" (name via existing `projName[lang]`
  i18n, generic fallback for fr/de/ko) → `reader.html#lang=es`. Cards
  re-render on every `render()` so a freshly kept story shows up on return.

### B. Named upload records + vocabulary view

- **Data**: project gains `uploads: [{id, name, date: "YYYY-MM-DD",
  words: [norm(w)…]}]` (append-only, v1: no batch delete). Backward
  compatible: missing `uploads` treated as `[]`; words in `vocab` but in no
  batch are displayed as one implicit "早期词表" group.
- **Capture**: the file-input handler records `state.lastFileName`
  (cleared on paste/AI-parse of pasted text). The confirm step gains a
  batch-name input, defaulting to the file name sans extension, else
  "粘贴 · <local date>". On confirm (both new-project and append paths) an
  upload record is created from the final `state.pending`.
- **View**: the project loop view gains a collapsible "📚 词表" section:
  one row per upload (newest first): name · date · word count · covered
  x/n; expanding shows the words as chips, covered chips dimmed. Legacy
  group shown last when non-empty.
- i18n: all four locales (zh/en/es/ja) for the new strings.

## Out of scope

- Batch delete / rename (future).
- Audio in the self-serve reader (TTS speech synthesis still works — only
  pre-baked audio clips are absent).
- Studio changes; CLI project format changes (uploads is additive JSON).

## Error handling

| Case | Behavior |
| --- | --- |
| reader.html opened with no/unknown `#lang` | empty-book state: header + "0 stories" (template renders what it gets); home link back |
| No projects in localStorage | same empty-book state |
| Legacy project without `uploads` | vocab view shows single 早期词表 group |
| Several projects, conflicting gloss_lang | first project wins (documented) |

## Testing

- pytest: `build_reader` writes a file whose payload parses as JSON with
  `self: true` and empty stories; existing build/studio tests unaffected.
- Agent-driven browser QA (user directive): naive-user walk — keep a story
  → landing card appears → reader renders the story with tap-glosses; new
  upload batch named + visible in 词表 with coverage; acceptance criteria
  from 2026-07-16 (middle-schooler usability, fresh-word batches) re-checked.
