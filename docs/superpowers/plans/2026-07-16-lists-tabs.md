# Two-Tab IA (Word-List Database + Generation) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The widget becomes two tabs — 词表 (a database of named word lists with upload-into-existing / create-new) and 生成故事 (multi-select lists, word source incl. LLM-pick) — with per-language storybooks unchanged.

**Architecture:** `docs/index.html` only. 词表 = project (existing schema; `uploads[]` retired from UI). One-time guarded, backed-up migration splits legacy upload batches into standalone lists. Coverage goes language-wide (`langCovered`). The generation loop is rewired from "one project" to "selected lists" (union vocab; story kept into the first selected list). New LLM-pick source hands the model the whole uncovered pool (cap 120) and lets it choose 10-20 words that fit one scene.

**Tech Stack:** Vanilla ES5 JS.

**Spec:** `docs/superpowers/specs/2026-07-16-lists-tabs-design.md`

## Global Constraints

- ES5 (`var`, `function`, no arrows/template literals); ONLY ASCII `"` as string delimiters (a curly-quote delimiter previously broke the whole page — verify with node --check EVERY task).
- Single file `docs/index.html`; all four locales (zh/en/es/ja) for every new string; every dynamic string through `esc()`.
- Storage schema unchanged (`fabulita.studio.projects` project shape); migration MUST first copy the raw JSON to `fabulita.studio.projects.backupV1` and never overwrite that key if it exists.
- Standing product criteria: middle-schooler usability; all/llm sources use only uncovered words (language-wide), manual respects explicit picks (cap 20).
- Keep working untouched: provider settings block, manual copy-prompt mode, PDF/AI parse pipeline, export helpers, my-storybook cards, reader.html, studio links.
- Verification per task: extract script → `node --check`; greps as specified; report ANY deviation from this plan explicitly.

---

### Task 1: Data layer — migration, language-wide coverage, generation helpers, prompt modes

**Files:**
- Modify: `docs/index.html` (after the storage helpers ~`loadAll`; `coverage`/`nextBatch` region; `promptFor`; `glossMap`)

**Interfaces (Tasks 2-3 rely on these EXACT names):**
- `langCovered(lang) -> {normKey: true}` — union of vocab_used across all projects of that lang.
- `listsOf(lang) -> [project]` (all lists when lang falsy), sorted by name.
- `genLists() -> [project]` — projects for `state.genSel` ids (order preserved, missing ids skipped).
- `genUnion(lists) -> [vocabEntry]` — concat vocab deduped by `norm(w)` (first occurrence wins).
- `genBatch() -> [vocabEntry]` — source-aware batch from the selection (see Step 3).
- `promptFor(p, batch, attempt, pickMode)` — 4th arg optional; truthy = LLM-pick wording.
- `glossMap(vocabArr, glossaryObj, story)` — CHANGED signature (was `(p, story)`); update its two existing call sites.
- Migration side effect: `fabulita.lists.v2` guard key; `fabulita.studio.projects.backupV1` backup.
- `state` additions: `tab: "lists"`, `listView: null`, `uploadTarget: "__new"`, `genSel: []`; `genSrc` loses `batchId` (types now `"all"|"manual"|"llm"`).

- [ ] **Step 1: Migration (IIFE right after the `#cfg=` bootstrap IIFE)**

```js
(function () {
  try {
    if (localStorage.getItem("fabulita.lists.v2")) return;
    var raw = localStorage.getItem(LSP);
    if (raw) {
      if (!localStorage.getItem(LSP + ".backupV1")) localStorage.setItem(LSP + ".backupV1", raw);
      var all = JSON.parse(raw) || {};
      var out = {};
      Object.keys(all).forEach(function (id) {
        var p = all[id];
        if (!p || !p.config) return;
        var ups = p.uploads || [];
        if (!ups.length) { out[id] = p; return; }
        var used = {};
        ups.forEach(function (u) {
          var wset = {};
          (u.words || []).forEach(function (w) { wset[w] = true; });
          var words = (p.vocab || []).filter(function (v) { return v && wset[(v.w || "").normalize("NFC").toLowerCase()]; });
          words.forEach(function (v) { used[(v.w || "").normalize("NFC").toLowerCase()] = true; });
          var nid = "p" + Math.random().toString(36).slice(2, 9);
          out[nid] = { id: nid, config: { name: u.name || "list", lang: p.config.lang, gloss_lang: p.config.gloss_lang, ui_default: p.config.ui_default }, vocab: words, glossary: {}, stories: [] };
        });
        var rest = (p.vocab || []).filter(function (v) { return v && !used[(v.w || "").normalize("NFC").toLowerCase()]; });
        out[id] = { id: id, config: p.config, vocab: rest, glossary: p.glossary || {}, stories: p.stories || [] };
      });
      localStorage.setItem(LSP, JSON.stringify(out));
    }
    localStorage.setItem("fabulita.lists.v2", "1");
  } catch (e) {}
})();
```

(Uses inline normalize because `norm()` is defined later. The original project keeps its stories and any un-batched words; batch projects start with empty stories.)

- [ ] **Step 2: Helpers (next to `coverage`)**

```js
function langCovered(lang) {
  var covd = {}, all = loadAll();
  Object.keys(all).forEach(function (id) {
    var p = all[id];
    if (!p || !p.config || p.config.lang !== lang) return;
    (p.stories || []).forEach(function (s) {
      (s && s.vocab_used || []).forEach(function (w) { covd[norm(w)] = true; });
    });
  });
  return covd;
}
function listsOf(lang) {
  var all = loadAll(), out = [];
  Object.keys(all).forEach(function (id) {
    var p = all[id];
    if (!p || !p.config) return;
    if (!lang || p.config.lang === lang) out.push(p);
  });
  out.sort(function (a, b) { return a.config.name < b.config.name ? -1 : 1; });
  return out;
}
function genLists() {
  var all = loadAll(), out = [];
  (state.genSel || []).forEach(function (id) { if (all[id]) out.push(all[id]); });
  return out;
}
function genUnion(lists) {
  var seen = {}, out = [];
  lists.forEach(function (p) {
    (p.vocab || []).forEach(function (v) {
      var k = norm(v.w);
      if (!seen[k]) { seen[k] = true; out.push(v); }
    });
  });
  return out;
}
function genBatch() {
  var lists = genLists();
  if (!lists.length) return [];
  var union = genUnion(lists);
  var src = state.genSrc || { type: "all" };
  if (src.type === "manual") {
    var sel = {};
    (src.words || []).forEach(function (w) { sel[w] = true; });
    return union.filter(function (v) { return sel[norm(v.w)]; }).slice(0, 20);
  }
  var covd = langCovered(lists[0].config.lang);
  var un = union.filter(function (v) { return !covd[norm(v.w)]; });
  return un.slice(0, src.type === "llm" ? 120 : 20);
}
```

Keep the old `coverage(p)`/`nextBatch(p)` functions for now — Task 3 removes `nextBatch` when the loop is rewired (the copy-prompt path switches to `genBatch`), and `coverage` stays for the storybook cards/词表 counts if still referenced.

- [ ] **Step 3: `promptFor` pick mode**

Change signature to `function promptFor(p, batch, attempt, pickMode)`. Inside, where the "You MUST use" clause is composed, branch:

```js
  var useLine = pickMode
    ? "From the vocabulary list below, CHOOSE 10 to 20 words that naturally belong\ntogether in ONE coherent everyday scene - prefer words that combine well and\nare easy to weave into the same short story. Then write the story using your\nchosen words (you may ignore the rest of the list):"
    : "Write ONE short story (5-8 short sentences, simple present tense, one scene,\nconcrete everyday situation). You MUST use " + useClause(batch.length) + "\nof these vocabulary words (their glosses are in " + (GLOSS_NAMES[p.config.gloss_lang] || p.config.gloss_lang) + "):";
```

and for pickMode ALSO prepend the story-shape sentence (keep the resulting prompt containing both the story-shape instruction and the pick instruction — adapt the existing string concatenation minimally; the JSON contract, rules lines and glossary requirements stay identical).

- [ ] **Step 4: `glossMap` generalization**

Change `function glossMap(p, story)` to `function glossMap(vocabArr, glossaryObj, story)` — internally replace `p.vocab` → `vocabArr`, `p.glossary` → `glossaryObj || {}`. Update BOTH existing call sites (`widgetBody` preview and the `.w` click handler) to `glossMap(p.vocab, p.glossary, s)` for now (Task 3 changes them to union-based).

- [ ] **Step 5: state literal**

Add `tab: "lists", listView: null, uploadTarget: "__new", genSel: [],` and change `genSrc` init to `{ type: "all", words: [] }`.

- [ ] **Step 6: Verify + commit**

node --check clean; greps: `langCovered` ≥3 (def + 2 uses come later — at this task ≥1 def), `genBatch` ≥1, `fabulita.lists.v2` ×2, `backupV1` ×2. `git add docs/index.html && git commit -m "Data layer: batch->list migration with backup, language-wide coverage, generation helpers, LLM-pick prompt mode"`

---

### Task 2: 词表 tab (tab bar, list table + detail, create list, upload-into-target)

**Files:**
- Modify: `docs/index.html` (widgetBody restructure; confirm-step target selector; confirm click handler; new click branches; CSS `.tabs`; i18n ×4; remove the 继续我的项目 pcard section from `render()`)

**Interfaces:**
- Tab bar: `data-act="tab-lists"` / `data-act="tab-gen"`; `widgetBody()` dispatches on `state.tab` to `listsBody()` / `genBody()` (Task 3 provides `genBody`; until then render a placeholder `<p class="muted">…</p>` for the gen tab).
- Lists tab states: table view (default) / `state.listView` = expanded list id / `state.step` `"input"`&`"confirm"` reuse the existing upload panel INSIDE the lists tab.
- Confirm-step target: `<select id="up-target">` — option `__new` (新建词表, shows the existing `#upname` input) + one option per `listsOf(state.targetLang)` entry; bound to `state.uploadTarget`; change-handler syncs it.
- Confirm click branch rewritten: `__new` → create a fresh project/list from `state.pending` (no generation start); a list id → merge `state.pending` into that list's vocab (dedupe by `norm`, gloss overwrite) — the old `appendMode` flag and `uploads[]` writes are REMOVED.
- New-list mini-form: `data-act="new-list"` toggles `state.newListOpen`; inputs `#nl-name` + reuse the `#wl` language select markup; `data-act="new-list-save"` creates an empty list.
- List row/detail: `data-act="open-list" data-id` sets `state.listView`; detail shows word chips (covered via `langCovered(list.config.lang)`), export buttons (existing export actions work on the open list), and `data-act="add-to-list"` (jumps to the upload panel with `state.uploadTarget` preset to this list and `state.targetLang` set to its lang).

Required behavior details:
1. The 上传/粘贴 input panel is the EXISTING one (textarea, `#wl`, upload button incl. PDF, parse, AI fallback, busy/error states) — relocated into the lists tab flow, not duplicated.
2. `state.appendMode`, `state.pid`-dependent loop entry, and the old `open-proj`/`add-more` click branches are removed together with the pcard section (grep for `pcard`, `open-proj`, `add-more`, `appendMode` — all gone by end of task; the storybook cards row in the books widget STAYS).
3. i18n keys (×4): `tabLists` (词表), `tabGen` (生成故事), `newList` (＋ 新建词表), `newListName` (词表名字), `newListSave` (创建), `uploadWords` (上传 / 粘贴生词), `upTarget` (加到哪张词表), `upTargetNew` (新建词表), `addToList` (＋ 加词到这张表), `backToLists` (← 返回词表), `noLists` (还没有词表——先建一张或直接上传), plus adjust `confirm` copy if needed (it already reads "存入词表"). English/Spanish/Japanese equivalents written by the implementer in the same register as existing strings.
4. CSS: `.tabs { display:flex; gap:0.4rem; margin-bottom:0.8rem; }` `.tab { ...pill button matching .btn styling... }` `.tab.on { ...primary-colored... }` — mirror existing `.btn`/`.btn-primary` declarations.

- [ ] Step 1: implement per the interface block above.
- [ ] Step 2: verify — node --check clean; greps: `tab-lists` ×2 (render + click branch), `up-target` ≥3, `pcard` ×0, `appendMode` ×0, `open-proj` ×0, `add-more` ×0, `tabLists` ×5; manually trace that PDF upload → confirm → 加进已有词表 merges (no duplicate norm keys).
- [ ] Step 3: commit `git add docs/index.html && git commit -m "Lists tab: word-list database UI (create / upload-into / detail), retire project cards"`

---

### Task 3: 生成故事 tab (multi-select lists, sources incl. LLM-pick, loop rewiring)

**Files:**
- Modify: `docs/index.html` (`genBody()` replacing the placeholder; `startGenerate`; `generateStory`; `keep`/`gen`/`reroll`/`resume`/`stop`/`copy`/`preview-paste` click branches; `gen-src` change branch; `pick-word` branch reuse; i18n ×4)

**Interfaces:**
- `genBody()` renders: (a) list checkbox rows — `data-act="gsel" data-id`, checked when in `state.genSel`; toggling a list whose lang differs from the current selection REPLACES the selection with just that list; row shows name · lang · covered x/n (via `langCovered`); `noLists` empty-state; (b) selection coverage line + `.cov-bar` for the union; (c) source `<select id="gen-src">` with options `all`/`manual`/`llm` (labels `srcAll`/`srcManual`/`srcLLM`); (d) chips area: all → `genBatch()` chips (batchInfo line), manual → the existing picker over `genUnion(genLists())` (covered via langCovered, cap 20, `pick-word` branch unchanged), llm → `<p class="muted">` hint `llmHint` with `{n}` = uncovered pool size; (e) the existing generating/preview/idle blocks and provider settings/manual mode — moved here intact, with `p` replaced by `genLists()[0]` where a project is needed.
- `startGenerate()` uses `genBatch()` and `genLists()[0]` (guard: no lists or empty batch → idle+render, reuse existing guard).
- `generateStory(p, batch, attempt)` passes `state.genSrc.type === "llm"` as `promptFor`'s 4th arg.
- Preview gloss popups: `glossMap(genUnion(genLists()), genLists()[0].glossary, s)` in both call sites.
- `keep`: story pushed into `genLists()[0]` (`saveProj`); manual source resets to `{type:"all",words:[]}` + no auto-continue; all/llm auto-continue while `genBatch().length && genReady()`.
- `copy` (manual prompt) uses `genBatch()` + `genLists()[0]` + pick-mode flag; `preview-paste` normalizes/validates against `genLists()[0]` with union-based glossMap.
- Empty-selection guards: `gen`/`copy` with 0 lists → `lp.error = t("selListFirst")`.
- Old `nextBatch`, the loop-step renderer inside `widgetBody`, and the `srcDone` batch messaging are REMOVED (superseded); the fully-covered selection shows `srcDone`-equivalent message `selDone` when `genBatch()` is empty and source is `all`/`llm`.
- i18n (×4): `srcLLM` (AI 挑词), `llmHint` (AI 会从 {n} 个未覆盖的词里挑 10-20 个适合同一个故事的词), `selListFirst` (先选至少一张词表), `selDone` (所选词表已全部覆盖 🎉 换一张或手动选词), `genPick` reuse existing keys where possible.
- After keep, coverage/storybook cards refresh naturally via `render()`.

- [ ] Step 1: implement per the interface block.
- [ ] Step 2: verify — node --check; greps: `gsel` ≥2, `srcLLM` ×5, `llmHint` ×5, `selListFirst` ×5, `nextBatch` ×0, `genBatch` ≥5; trace: `validateStory` untouched; `API_SCHEMA` untouched.
- [ ] Step 3: commit `git add docs/index.html && git commit -m "Generation tab: multi-list selection, all/manual/LLM-pick sources, loop rewired to list union"`

---

### Task 4: Agent-driven browser QA

- [ ] **Step 1: Migration check first** (before touching UI): via javascript_tool inspect localStorage — `fabulita.studio.projects.backupV1` exists and parses; batches 测试单元一/二 became standalone lists with correct words; original project retains stories + leftover words; reader.html#lang=es still renders all stories.
- [ ] **Step 2: 词表 tab**: table shows migrated lists with language-wide coverage; create a new empty list; upload/paste INTO an existing list (target selector) → merged without duplicates; PDF upload path still reachable and labeled; detail view chips + export work.
- [ ] **Step 3: 生成 tab**: multi-select two es lists → union chips; source all → generate via codex bridge → keep → story in reader; source llm → hint shows pool size → generate → verify the story's vocab_used ⊆ uncovered pool and coherent (~10-20 words); manual picker unchanged; empty-selection guard; cross-language select replaces selection.
- [ ] **Step 4: Standing criteria** (middle-schooler walk; fresh words for all/llm) + console clean + UI language 中文 + friction list → report to `.superpowers/sdd/task-4-qa-browser2.md`.
- [ ] **Step 5: fix anything found; commit.**
