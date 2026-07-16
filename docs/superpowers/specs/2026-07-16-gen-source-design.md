# Generation word-source selection (decouple upload from generate)

Date: 2026-07-16
Status: approved (design confirmed in conversation)
Scope: `docs/index.html` only.

## Problem

Confirming an upload immediately starts generating from the whole project's
uncovered vocabulary. The user wants upload to be its own step (batch lands
in the word list), and generation to take an explicit word source: the whole
pool, one named upload batch, or a handful of hand-picked words.

## Design

### 1. Confirm = save only

Both confirm paths (new project / append) stop auto-starting generation —
they save and `render()` the project view. The confirm button copy changes
to "✓ 确认，存入词表" (all four locales).

### 2. Word-source selector in the project view

In the loop view's idle area (above the batch chips), a single
`<select id="gen-src">`:
- **全部未覆盖** (default — current behavior)
- one option per upload batch (label: `name · 覆盖 x/n`), value = upload id
- **手动选词**

Held in `state.genSrc = {type: "all"|"batch"|"manual", batchId, words: []}`
(session-only, reset when switching projects via open-proj and after
confirm).

### 3. Batch computation

`nextBatch(p)` becomes source-aware:
- `all`: uncovered words, first 20 (unchanged).
- `batch`: uncovered ∩ batch.words, first 20.
- `manual`: exactly the selected words (covered ones allowed — explicit
  user choice is respected), capped at 20.

The standing fresh-words criterion (new stories avoid words already used by
existing stories) holds for `all`/`batch` by construction; `manual` is the
deliberate exception.

### 4. Manual picking UI

When source = 手动选词, the chips area renders ALL project vocab as
clickable chips (`data-act="pick-word"`): selected chips highlighted,
covered chips keep their dimmed style but stay clickable. A hint shows
"已选 {n}/20". Generate requires ≥1 selected word. Picks live in
`state.genSrc.words` (norm keys).

### 5. Exhaustion & keep behavior

- Batch source with all its words covered → message "这批词已全部覆盖"
  plus the source selector (switch batch / back to 全部) — NOT the
  project-complete 🎉 message (that still requires the whole vocab covered).
- After ✓ keeping a story: `all`/`batch` sources keep the current
  auto-continue loop; `manual` resets to `all` and does not auto-start
  (a hand-picked selection is for that one story).

## Out of scope

- Persisting genSrc to localStorage; multi-batch selection; per-story
  source metadata.

## Testing

Agent-driven browser QA: confirm no longer auto-generates; batch source
restricts chips to that batch's uncovered words; manual pick of 3 words
generates a story using them (covered pick allowed); batch-exhausted
message; standing acceptance criteria (middle-schooler usability,
fresh-word batches for non-manual sources).
