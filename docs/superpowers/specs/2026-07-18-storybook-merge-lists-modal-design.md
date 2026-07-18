# Storybook merge + single lists view + generation modal

Date: 2026-07-18
Status: approved
Scope: `docs/index.html`, `docs/reader.html`, build pipeline (demo-data
emit). `docs/studio.html`, CLI core, list-detail interactions unchanged.

## Problem

1. Español / English / 日本語 are static demo pages disconnected from the
   user's own storybook; the user wants one storybook per language with the
   demo stories as default content, every story deletable.
2. 生成故事 is a sibling tab of 词表; the user wants generation to be a
   click-to-open modal launched from the lists view.
3. The lists view has no language filter and no checkbox selection; the
   user wants: language selector on top → that language's lists with
   checkboxes → add-new-list (0/0) → upload-into / generate driven by the
   checked state.

## Design

### 1. Demo data as build artifact

The pipeline additionally emits `docs/demo-data-<lang>.js` for each demo
language (es, en, ja), containing
`window.FABULITA_DEMO = window.FABULITA_DEMO || {}; FABULITA_DEMO.<lang> = {stories: [...], glossary: ..., audio: ...}` —
the same story/audio payload currently baked into `demo-<lang>.html`.
`reader.html` injects `<script src="demo-data-<lang>.js">` based on
`#lang=xx` (missing file → no built-ins, non-demo languages just work).
Audio stays in the static file; localStorage quota untouched.
The build also emits a tiny `docs/demo-manifest.js`
(`window.FABULITA_DEMO_COUNTS = {es: n, en: n, ja: n}` + story ids) so the
index can show counts and languages without loading megabytes of story
data. `demo-<lang>.html` files remain in the repo as single-file showcase
artifacts but are no longer linked from the index.

### 2. Index: "我的故事书" section

Replaces the "选一本书" demo rows. One row per language: demo languages
(es/en/ja) always shown; other languages (fr/de/ko/…) appear once they have
≥1 kept story. Row = localized storybook name + story count (built-ins
not hidden + kept, from `demo-manifest.js` and localStorage). Click →
`reader.html#lang=<lang>`.

### 3. Reader: merged storybook with per-story delete

For `#lang=xx`: built-in demo stories (minus ids in
`localStorage["fabulita.hiddenDemo"]`, a per-language id set) first, then
kept stories from all lists of that language in kept order. Delete on a
kept story = existing real delete. Delete on a built-in story = add id to
hiddenDemo. When any id is hidden, show a "恢复内置故事" button that
clears the language's hidden set.

### 4. Lists view: single view, checkbox-driven

The widget drops both tabs; its body is the lists view (upload/confirm
steps and list detail still overlay it as today). Layout top-down:

- 学习语言 selector (persisted, `localStorage["fabulita.listLang"]`;
  default = last used, else UI-appropriate default).
- Rows for that language's lists: checkbox + name + word count +
  coverage x/n. Clicking the name opens the existing detail view.
  Checked ids live in state (persisted with the draft as today's
  `genSel`).
- Buttons, enabled by checked count:
  - ＋ 新建词表 — always; creates 0/0 in the selected language.
  - 上传/粘贴生词 — 0 checked → target defaults to 新建词表; exactly 1
    checked → that list preselected as target (confirm screen still lets
    the user switch); >1 checked → disabled.
  - ✨ 生成故事 — ≥1 checked; opens the generation modal.

Switching the language selector clears checks (lists are per-language).

### 5. Generation modal

A modal overlay hosting the existing generation loop UI unchanged:
source (全部未覆盖 / 手动选词 / AI 挑词) → generate → preview with 朗读 +
点词查义 → 收下 / 换一篇 → back to source selection. Reuses
`state.loop`, run tokens, and the draft cache as-is.

- Close (✕ / Esc / backdrop): draft persists; an in-flight request keeps
  running (existing run-token logic) and its preview is saved to the
  draft on arrival; reopening restores.
- On boot, a restorable draft opens the modal directly (replaces today's
  "open on gen tab" restore).
- Keep saves to the first checked list (existing behavior) and returns to
  source selection inside the modal.

## Out of scope

- studio.html, CLI generation/validation logic, list-detail view.
- Deleting or redesigning `demo-<lang>.html` artifacts.
- Any server/back-end (still fully static + localStorage).

## Testing

CLI: extend build tests for the demo-data emit (file exists, valid JS,
stories match source JSON). Frontend: manual QA checklist in the plan —
demo merge (view/delete/restore built-ins, counts on index), checkbox
gating of the three buttons, language switch clears checks, modal
open/close/draft-restore across reload, keep lands story in the right
list and storybook, non-demo language storybook works without a
demo-data file.
