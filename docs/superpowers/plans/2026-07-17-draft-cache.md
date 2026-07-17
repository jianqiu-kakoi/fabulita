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

---

### Task 3: Self-serve reader — proper title + per-story delete

**Files:** Modify `fabulita/ui.py` (4 new keys ×4 langs), `fabulita/template.html`; regenerate `docs/reader.html` + `docs/studio.html`; extend `tests/test_fabulita.py` if trivial.

**Requirements:**
1. `ui.py` UI_STRINGS gains per-lang keys: `myBook` (zh 我的故事书 / en My storybook / es Mi libro de cuentos / ja わたしのストーリーブック), `delStory` (zh 删除这篇 / en Delete this story / es Eliminar esta historia / ja この話を削除), `delConfirm` (zh 再点一次确认删除 / en Click again to confirm / es Pulsa otra vez para confirmar / ja もう一度押して確認).
2. Template hydration (`P.self` block): stop using the "first name +N" title. Resolve UI language early (localStorage `fabulita.uiLang`, fallback `P.config.ui_default`, fallback "en") and set `P.config.name = (P.ui[ul] && P.ui[ul].myBook) || "My storybook"`; keep `document.title` assignment. ALSO attach `_pid: <project id>` to every aggregated story object during hydration.
3. Story delete (self-serve ONLY — gate every bit on `P.self`): each story header (in `storyHtml` or the render loop) gains a small muted delete button carrying `data-del="<story id>" data-pid="<_pid>"`. Two-step inline confirm WITHOUT native confirm(): first click sets an in-memory armed flag and re-labels that button to `delConfirm`; second click removes the story (match by id) from that project in `localStorage["fabulita.studio.projects"]`, saves, and `location.reload()`. Clicking anywhere else disarms. All strings via the template's `t()`; esc() everything.
4. Regenerate artifacts (`fabulita reader --out docs/reader.html`, `fabulita studio --out docs/studio.html`); node --check both script blocks of reader.html; `uv run --extra dev pytest -q` green.
5. Commit: `Reader: localized my-storybook title + per-story delete (self-serve only)`

### Task 4: 词表 delete (index.html)

**Requirements:**
1. In `listDetailHtml()`: a `data-act="del-list" data-id` button (muted/danger style). Two-step inline confirm via `state.delArm` (holds the armed list id, cleared on any other click/render action): first click arms and re-labels to the confirm string — if the list has stories, use `delListConfirmN` with `{n}` = story count (its stories disappear from the storybook), else `delListConfirm`. Second click: delete the project from storage, clear from `state.genSel`, clear `state.listView`, clear the draft if `fabulita.draft`'s targetId is the deleted id, render back to the table.
2. i18n ×4: `delList` (删除这张词表), `delListConfirm` (再点一次确认删除), `delListConfirmN` (再点一次确认删除（含 {n} 篇故事）).
3. node --check; greps: `del-list` ×2, `delArm` ≥4, `delListConfirmN` ×5.
4. Commit: `Lists tab: delete a word list (two-step inline confirm, draft/selection cleanup)`

### Task 5: Agent browser QA (draft cache + title + deletes)

Covers plan Task 2's checklist PLUS: reader title shows 我的故事书 (not 测试单元一 +3); story delete two-step works and survives reload (story gone, coverage updated); list delete two-step works incl. genSel/draft cleanup; deleting the stories-holding list removes those stories from the reader; standing criteria; console clean; findings → `.superpowers/sdd/task-5-qa-draft.md`; fix anything found.
