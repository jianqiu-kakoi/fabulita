# Generation Word-Source Selection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upload is decoupled from generation: confirm saves the batch only; the project view gains a word-source selector (all uncovered / one upload batch / hand-picked words) that drives story generation.

**Architecture:** All in `docs/index.html`. New session state `state.genSrc`; `nextBatch(p)` becomes source-aware; a `<select id="gen-src">` in the loop view; manual mode turns the chips area into a clickable picker; confirm paths stop auto-starting generation.

**Tech Stack:** Vanilla ES5 JS.

**Spec:** `docs/superpowers/specs/2026-07-16-gen-source-design.md`

## Global Constraints

- ES5 style (`var`, `function`, no arrows/template literals, double quotes); single file `docs/index.html`.
- All four locales (zh/en/es/ja) get every new/changed string.
- Fresh-words criterion holds for all/batch sources (uncovered-only); manual respects explicit picks including covered words, capped at 20.
- Project-complete 🎉 message still requires the WHOLE vocab covered; a merely exhausted batch source shows its own message.
- Every dynamic string through `esc()`.

---

### Task 1: Source-aware generation (state, nextBatch, UI, handlers, i18n)

**Files:**
- Modify: `docs/index.html` (state literal; `nextBatch` ~line 528; loop-step renderer ~lines 925-995; click handler branches `confirm`/`keep`/`gen`/`open-proj` + new `pick-word`; change handler; CSS near `.chip`; i18n ×4)

**Interfaces:**
- Produces: `state.genSrc = {type: "all"|"batch"|"manual", batchId: string|null, words: [normKey]}`; `<select id="gen-src">`; click action `pick-word`; i18n keys `srcLabel, srcAll, srcManual, srcDone, pickHint, pickNone` + changed `confirm`.

- [ ] **Step 1: State**

In the state literal, after the `expMsg`/`expText` entries add:

```js
  genSrc: { type: "all", batchId: null, words: [] },
```

- [ ] **Step 2: Source-aware `nextBatch`**

Replace `function nextBatch(p) { return coverage(p).uncovered.slice(0, 20); }` with:

```js
function nextBatch(p) {
  var src = state.genSrc || { type: "all" };
  if (src.type === "manual") {
    var sel = {};
    (src.words || []).forEach(function (w) { sel[w] = true; });
    return p.vocab.filter(function (v) { return sel[norm(v.w)]; }).slice(0, 20);
  }
  var un = coverage(p).uncovered;
  if (src.type === "batch") {
    var up = null;
    (p.uploads || []).forEach(function (u) { if (u.id === src.batchId) up = u; });
    if (up) {
      var inSet = {};
      (up.words || []).forEach(function (w) { inSet[w] = true; });
      un = un.filter(function (v) { return inSet[norm(v.w)]; });
    }
  }
  return un.slice(0, 20);
}
```

- [ ] **Step 3: Confirm paths save only**

In the `confirm` click branch, BOTH occurrences of

```js
      if (genReady()) startGenerate(); else render();
```

become

```js
      state.genSrc = { type: "all", batchId: null, words: [] };
      render();
```

(The appendMode occurrence keeps its `return;` after; the new-project occurrence is the branch's last statement.)

- [ ] **Step 4: Reset source on project switch**

In the `open-proj` click branch, alongside its other state resets add:

```js
    state.genSrc = { type: "all", batchId: null, words: [] };
```

- [ ] **Step 5: Loop-view selector + restructured conditions + manual picker**

In the loop step of `widgetBody()`: right after the line `if (state.expText) h += '<textarea readonly ...' (the loop-step one, before the 词表 `(function () {` IIFE), insert the covered-set hoist and the selector:

```js
    var covSetL = {};
    cov.covered.forEach(function (v) { covSetL[norm(v.w)] = true; });
    var src = state.genSrc || { type: "all", batchId: null, words: [] };
    h += "<label>" + esc(t("srcLabel")) + '</label><select id="gen-src">' +
      '<option value="all"' + (src.type === "all" ? " selected" : "") + ">" + esc(t("srcAll")) + "</option>";
    (p.uploads || []).slice().reverse().forEach(function (u) {
      var c = 0;
      (u.words || []).forEach(function (w) { if (covSetL[w]) c++; });
      h += '<option value="' + esc(u.id) + '"' + (src.type === "batch" && src.batchId === u.id ? " selected" : "") + ">" +
        esc(u.name) + " · " + c + "/" + (u.words || []).length + "</option>";
    });
    h += '<option value="manual"' + (src.type === "manual" ? " selected" : "") + ">" + esc(t("srcManual")) + "</option></select>";
```

Then restructure the condition chain. Current shape:

```js
    if (!batch.length) {            // doneAll
    } else if (lp.stopped) {        // stopped
    } else {                        // chips + phases
```

New shape:

```js
    if (!cov.uncovered.length) {
      // unchanged doneAll block
    } else if (lp.stopped) {
      // unchanged stopped block
    } else if (!batch.length && src.type === "batch") {
      h += '<div class="msg ok">' + esc(t("srcDone")) + "</div>";
    } else {
      // chips area:
      if (src.type === "manual") {
        h += '<p class="muted" style="margin-top:0.7rem">' + esc(fmt(t("pickHint"), { n: batch.length })) + '</p><div class="chips">';
        p.vocab.forEach(function (v) {
          var k = norm(v.w);
          h += '<span class="chip' + (src.words.indexOf(k) !== -1 ? " chip-sel" : "") + (covSetL[k] ? " chip-cov" : "") +
            '" data-act="pick-word" data-w="' + esc(k) + '" title="' + esc(v.gloss) + '">' + esc(v.w) + "</span>";
        });
        h += "</div>";
      } else {
        // unchanged: batchInfo line + batch chips
      }
      // unchanged: lp.phase generating/preview/idle blocks
    }
```

(Everything inside the final `else` after the chips area — the `generating`/`preview`/idle-buttons blocks — stays byte-identical.)

- [ ] **Step 6: Handlers**

a) Change handler — add before the `wf` branch:

```js
  if (e.target.id === "gen-src") {
    var sv = e.target.value;
    if (sv === "all") state.genSrc = { type: "all", batchId: null, words: [] };
    else if (sv === "manual") state.genSrc = { type: "manual", batchId: null, words: state.genSrc && state.genSrc.type === "manual" ? state.genSrc.words : [] };
    else state.genSrc = { type: "batch", batchId: sv, words: [] };
    render();
    return;
  }
```

b) Click handler — new branch after `gen`:

```js
  else if (act === "pick-word") {
    var gs = state.genSrc;
    if (!gs || gs.type !== "manual") return;
    var kw = el.dataset.w, ki = gs.words.indexOf(kw);
    if (ki !== -1) gs.words.splice(ki, 1);
    else if (gs.words.length < 20) gs.words.push(kw);
    render();
  }
```

c) `gen` branch gains an empty-selection guard — change `else if (act === "gen") { lp.attempt = 0; startGenerate(); }` to:

```js
  else if (act === "gen") {
    if (!nextBatch(p).length) { lp.error = t("pickNone"); render(); return; }
    lp.attempt = 0; startGenerate();
  }
```

d) `keep` branch — manual resets and does not auto-continue. Change its tail

```js
    if (nextBatch(p).length && genReady()) startGenerate(); else render();
```

to

```js
    if (state.genSrc && state.genSrc.type === "manual") {
      state.genSrc = { type: "all", batchId: null, words: [] };
      render();
    } else if (nextBatch(p).length && genReady()) startGenerate();
    else render();
```

- [ ] **Step 7: CSS + i18n**

CSS next to the existing `.chip` rules:

```css
  .chip[data-act] { cursor: pointer; }
  .chip-sel { background: var(--accent); border-color: var(--accent); color: #fff; }
```

(If the stylesheet has no `--accent` variable, reuse the exact background/border declaration of `.btn-primary` — check first.)

i18n — CHANGE `confirm` in all four locales:

```js
    confirm: "✓ 确认，存入词表",                       // zh
    confirm: "✓ Confirm — save to my word list",       // en
    confirm: "✓ Confirmar y guardar en mi lista",      // es
    confirm: "✓ 確認してリストに保存",                  // ja
```

ADD in all four locales:

```js
    srcLabel: "用哪些词生成", srcAll: "全部未覆盖的词", srcManual: "手动选词", srcDone: "这批词已全部覆盖 🎉 换个词源继续。", pickHint: "点选要用的单词（最多 20 个）· 已选 {n}", pickNone: "先选至少 1 个词",                                                                        // zh
    srcLabel: "Generate from", srcAll: "All uncovered words", srcManual: "Pick words myself", srcDone: "Every word in this batch is covered 🎉 — pick another source.", pickHint: "Tap the words to use (max 20) · {n} selected", pickNone: "Pick at least one word first",         // en
    srcLabel: "Generar con", srcAll: "Todas las palabras sin cubrir", srcManual: "Elegir palabras yo mismo", srcDone: "Todas las palabras de este lote están cubiertas 🎉 — elige otra fuente.", pickHint: "Toca las palabras a usar (máx. 20) · {n} seleccionadas", pickNone: "Elige al menos una palabra",  // es
    srcLabel: "どの単語から生成", srcAll: "未カバーの全単語", srcManual: "自分で単語を選ぶ", srcDone: "このリストの単語はすべてカバー済み 🎉 別のソースを選んでください。", pickHint: "使う単語をタップ（最大 20）· {n} 選択中", pickNone: "先に 1 語以上選んでください",           // ja
```

- [ ] **Step 8: Verify**

1. `python3 -c "import re; h=open('docs/index.html').read(); m=re.findall(r'<script>(.*?)</script>', h, re.S); open('/tmp/fab-src.js','w').write(m[-1])" && node --check /tmp/fab-src.js` — clean.
2. Greps: `srcLabel` ×5 (4 defs + 1 use), `pickHint` ×5, `pickNone` ×5 (4 defs + 1 use in the gen guard), `gen-src` ×2 (select render + change handler), `pick-word` ×2 (chip + click branch), `genSrc` ≥12.
3. `grep -c "startGenerate(); else render();" docs/index.html` — the confirm paths no longer contain it (only the keep branch's else-if retains a variant).

- [ ] **Step 9: Commit**

```bash
git add docs/index.html
git commit -m "Generation word-source selector: all / upload batch / hand-picked words; confirm saves only"
```

---

### Task 2: Agent-driven browser QA

**Files:** none (fixes only if found)

- [ ] **Step 1: Dispatch a browser-QA subagent** with the standing acceptance criteria (middle-schooler usability; fresh-word batches for all/batch sources) plus:
  1. Paste a 3-word batch into the existing project (加更多词) → confirm ("确认，存入词表") → verify NO generation auto-starts; the batch appears in 📚 词表 and in the gen-src dropdown with its coverage.
  2. Select the new batch as source → chips show only its (uncovered) words → generate one story via the Codex provider → chips words ⊆ batch words; keep it; auto-continue stays within the batch or shows the srcDone message when exhausted.
  3. 手动选词: pick 3 words (incl. one covered/dimmed chip) → 已选 3 hint → generate → story preview uses the picked words → keep → source resets to 全部未覆盖 and no auto-generation fires.
  4. gen with manual + 0 words → pickNone error, no request sent.
  5. Console clean; UI language 中文 restored; report friction points.
- [ ] **Step 2: Fix anything found; commit** (`git add -A && git commit -m "QA fixes: gen-source round 1"`). Skip if clean.
