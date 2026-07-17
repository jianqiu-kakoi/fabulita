# Draft Cache + No Auto-Continue Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Story previews survive reload/navigation via a localStorage draft; keeping a story returns to the source-selection view instead of auto-generating.

**Architecture:** `docs/index.html` only. `fabulita.draft` written on preview arrival, restored on boot, cleared on keep/reroll/discard/selection-change. `keep` loses its auto-continue; `lp.stopped` + idle-stop button removed.

**Spec:** `docs/superpowers/specs/2026-07-17-draft-cache-design.md`

## Global Constraints

- ES5, ASCII `"` delimiters only (node --check every commit); single file; esc() everywhere; i18n ×4 for any new string (none expected).

---

### Task 1: Implement draft cache + keep behavior

**Files:** Modify `docs/index.html`

- [ ] **Step 1: Draft helpers** (next to the storage helpers):

```js
var LSD = "fabulita.draft";
function saveDraft() {
  var lp = state.loop;
  try {
    localStorage.setItem(LSD, JSON.stringify({
      story: lp.story, warnings: lp.warnings, missing: lp.missing,
      targetId: lp.targetId, genSel: state.genSel, genSrc: state.genSrc, ts: Date.now()
    }));
  } catch (e) {}
}
function clearDraft() { try { localStorage.removeItem(LSD); } catch (e) {} }
```

- [ ] **Step 2: Write on preview arrival** — in `startGenerate`'s success callback, after `lp.phase = "preview";` add `saveDraft();`. Also in the `preview-paste` success path after the preview state is set, add `saveDraft();`.

- [ ] **Step 3: Restore on boot** — right BEFORE the final `render();` call at the bottom of the IIFE:

```js
(function () {
  try {
    var d = JSON.parse(localStorage.getItem(LSD));
    if (!d || !d.story || !d.targetId) return;
    if (!loadAll()[d.targetId]) { localStorage.removeItem(LSD); return; }
    state.open = true;
    state.tab = "gen";
    state.genSel = d.genSel || [d.targetId];
    state.genSrc = d.genSrc || { type: "all", words: [] };
    state.loop.story = d.story;
    state.loop.warnings = d.warnings || [];
    state.loop.missing = d.missing || [];
    state.loop.targetId = d.targetId;
    state.loop.phase = "preview";
  } catch (e) {}
})();
```

- [ ] **Step 4: Clear sites** — add `clearDraft();` in: `keep` (after saveProj), the `reroll` branch (at its start), the preview-row `stop` branch, and the `gsel` branch (alongside its existing loop invalidation).

- [ ] **Step 5: keep = no auto-continue** — replace the keep branch's tail (the manual-reset / auto-continue conditional) with an unconditional:

```js
    lp.targetId = null;
    if (state.genSrc && state.genSrc.type === "manual") state.genSrc = { type: "all", words: [] };
    render();
```

(keep the existing story-push/saveProj/loop-reset lines above it.)

- [ ] **Step 6: Remove `lp.stopped` machinery** — delete the idle-row stop button IF it still renders in the idle (non-preview) state; keep the preview-row ■ button (it discards the preview: verify its handler resets phase/story AND now calls clearDraft). Remove `stopped:` from the two loop-reset literals and the `!lp.stopped` check in the `gen-save` branch — and remove that branch's auto-start entirely (saving settings just renders).

- [ ] **Step 7: Verify** — node --check; greps: `fabulita.draft` ≥3 (const + restore + …), `saveDraft` ×3 (def + 2 calls), `clearDraft` ≥5 (def + 4 sites), `stopped` ×0, `startGenerate` NOT called from `gen-save`; trace reload-restore path manually (state.open/tab/genSel/preview).

- [ ] **Step 8: Commit** — `git add docs/index.html && git commit -m "Draft cache: previews survive reload; keep returns to selection (no auto-continue)"`

---

### Task 2: Agent browser QA

- [ ] Generate (any source) → preview → hard reload (cache-bust) → widget opens on 生成 tab with same selection/source and the preview restored → 收下 → story saved to the right list, view returns to selection (idle), NO new request fired (check network/no spinner) → reload again → no preview (draft cleared).
- [ ] 换一篇 regenerates (old draft replaced on next preview); ■ discards + clears draft (reload → no preview).
- [ ] Selection change with a restored preview → preview invalidated + draft cleared.
- [ ] Console clean; UI 中文; friction notes → `.superpowers/sdd/task-2-qa-draft.md`; fix anything found.
