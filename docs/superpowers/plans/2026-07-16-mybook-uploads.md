# My Storybook + Upload Records Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Accepted stories become readable per-language "my storybook" pages (reader.html, aggregated from localStorage), and every vocabulary upload is recorded as a named batch viewable with coverage in the project view.

**Architecture:** `fabulita/template.html` gains a self-serve hydration block (active only when the injected payload has `self:true`); `build.py` gains `build_reader()`; CLI gains `fabulita reader`; `docs/reader.html` becomes a committed artifact. `docs/index.html` gains per-language storybook cards, a batch-name input on the confirm step, `uploads[]` records on confirm, and a 📚 词表 section in the loop view.

**Tech Stack:** Python 3 stdlib + pytest; vanilla ES5 JS in both HTML files.

**Spec:** `docs/superpowers/specs/2026-07-16-mybook-uploads-design.md`

## Global Constraints

- ES5 style in ALL page JS (`var`, `function`, no arrows, no template literals, double quotes). Match each file's existing idiom.
- `fabulita` package stays stdlib-only.
- Demo/exported pages must be byte-for-byte unaffected in behavior: the template's new code runs ONLY when `P.self` is truthy.
- localStorage schema stays backward compatible: `uploads` missing → `[]`; no existing field changes.
- All four locales (zh ~181 / en ~240 / es ~299 / ja ~358 in docs/index.html) get every new string.
- Python tests: `uv run --extra dev pytest -q` from repo root (25 currently green).
- Browser QA runs via a subagent controlling Chrome (user directive 2026-07-16); acceptance criteria: middle-schooler usability + fresh-word batches (no overlap with existing stories' vocab_used).

---

### Task 1: Self-serve reader (template hydration + build_reader + CLI + artifact)

**Files:**
- Modify: `fabulita/template.html:217-222` (hydration block at top of main IIFE)
- Modify: `fabulita/build.py` (add `build_reader` after `build_studio`, ~line 70)
- Modify: `fabulita/cli.py` (add `reader` subparser next to `studio` ~line 65; dispatch block next to the `studio` block ~line 74)
- Create (artifact): `docs/reader.html`
- Test: `tests/test_bridge.py` untouched; add to `tests/test_fabulita.py` (or a new `tests/test_reader.py`)

**Interfaces:**
- Produces: `build.build_reader(out) -> (Path, int)`; CLI `fabulita reader [--out PATH]`; template self-serve contract: payload `{self: true, ui, uiLangs, config: {name, lang, gloss_lang, ui_default, home}, vocab: [], glossary: {}, stories: [], audio: {}}` + URL hash `#lang=<code>` → aggregated book. Task 2 links to `reader.html#lang=<code>`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_fabulita.py` (new test at the end; reuse its existing imports style — check the file first):

```python
def test_build_reader(tmp_path):
    from fabulita import build
    out, size = build.build_reader(tmp_path / "reader.html")
    html = out.read_text(encoding="utf-8")
    assert size == len(html)
    assert "/*__PAYLOAD__*/null" not in html
    import json as _json, re
    m = re.search(r"<script>var P = (\{.*?\});</script>", html, re.S)
    assert m, "payload script tag not found"
    data = _json.loads(m.group(1))
    assert data["self"] is True
    assert data["stories"] == [] and data["vocab"] == []
    assert data["config"]["home"] == "index.html"
    assert "ui" in data and "uiLangs" in data
```

- [ ] **Step 2: Run it — expect FAIL** (`AttributeError: module 'fabulita.build' has no attribute 'build_reader'`):
`uv run --extra dev pytest tests/test_fabulita.py::test_build_reader -q`

- [ ] **Step 3: `build.py` — add `build_reader`**

After `build_studio` (build.py ~line 70):

```python
def build_reader(out="reader.html"):
    """Emit the self-serve reader: aggregates 'my storybook' from localStorage at runtime."""
    data = {
        "self": True,
        "ui": UI_STRINGS,
        "uiLangs": UI_LANGS,
        "config": {"name": "fabulita", "lang": "", "gloss_lang": "en",
                   "ui_default": "en", "home": "index.html"},
        "vocab": [], "glossary": {}, "stories": [], "audio": {},
    }
    blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    html = TEMPLATE.read_text(encoding="utf-8")
    html = html.replace("__TITLE__", "fabulita")
    html = html.replace("/*__PAYLOAD__*/null", blob, 1)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return out, len(html)
```

- [ ] **Step 4: CLI wiring**

Next to the `studio` parser (cli.py ~line 65):

```python
    p = sub.add_parser("reader", help="write the self-serve reader page (my storybook, reads localStorage)")
    p.add_argument("--out", default="reader.html")
```

Dispatch, right after the `studio` block (project-less, before `proj.require()`):

```python
        if args.cmd == "reader":
            out, size = build.build_reader(args.out)
            print(f"wrote {out} ({size / 1024:.0f} KB) — serve it next to index.html")
            return 0
```

- [ ] **Step 5: template hydration block**

`fabulita/template.html` — the main IIFE currently opens (lines 218-221):

```js
<script>
(function () {
  "use strict";
  var UI = P.ui;
```

Insert BETWEEN `"use strict";` and `var UI = P.ui;`:

```js
  if (P && P.self) {
    (function () {
      var m = (location.hash || "").match(/lang=([a-z]{2})/i);
      var langSel = m ? m[1].toLowerCase() : "";
      var all = {};
      try { all = JSON.parse(localStorage.getItem("fabulita.studio.projects")) || {}; } catch (e) {}
      var stories = [], vocab = [], glossary = {}, seenW = {}, glossLang = "", names = [];
      Object.keys(all).forEach(function (id) {
        var pr = all[id];
        if (!pr || !pr.config || pr.config.lang !== langSel) return;
        (pr.stories || []).forEach(function (s) { if (s && s.status !== "candidate") stories.push(s); });
        (pr.vocab || []).forEach(function (v) {
          var k = (v.w || "").normalize("NFC").toLowerCase();
          if (k && !seenW[k]) { seenW[k] = true; vocab.push(v); }
        });
        var g = pr.glossary || {};
        Object.keys(g).forEach(function (k) { glossary[k] = g[k]; });
        if (!glossLang) glossLang = pr.config.gloss_lang || "";
        names.push(pr.config.name || "");
      });
      P.config.lang = langSel;
      if (glossLang) P.config.gloss_lang = glossLang;
      if (names.length) P.config.name = names.length === 1 ? names[0] : names[0] + " +" + (names.length - 1);
      P.stories = stories;
      P.vocab = vocab;
      P.glossary = glossary;
      P.audio = {};
      document.title = P.config.name;
    })();
  }
```

- [ ] **Step 6: Regenerate artifacts and test**

```bash
uv run --extra dev pytest -q                       # all green (25 + 1 new)
uv run fabulita reader --out docs/reader.html      # artifact
uv run fabulita studio --out docs/studio.html      # studio embeds the template → regenerate so its export carries the new hydration block
python3 -c "import re,sys; h=open('docs/reader.html').read(); m=re.findall(r'<script>(.*?)</script>', h, re.S); [open('/tmp/rd%d.js'%i,'w').write(s) for i,s in enumerate(m)]"
node --check /tmp/rd0.js && node --check /tmp/rd1.js   # both script blocks parse
```

Note: `docs/demo-*.html` are NOT regenerated (they need project dirs/audio; behavior unaffected since `P.self` is absent there).

- [ ] **Step 7: Commit**

```bash
git add fabulita/template.html fabulita/build.py fabulita/cli.py tests/test_fabulita.py docs/reader.html docs/studio.html
git commit -m "Self-serve reader: my-storybook page aggregating localStorage by language"
```

---

### Task 2: Landing page — per-language storybook cards

**Files:**
- Modify: `docs/index.html` (render() BOOKS section ~line 966; i18n ×4)

**Interfaces:**
- Consumes: `loadAll()`, `LANG_CHOICES`, `t("projName")`, `esc`, `fmt`; `reader.html#lang=<code>` (Task 1).
- Produces: cards inside the books widget listing each language with ≥1 accepted story.

- [ ] **Step 1: Aggregate + render cards**

In `render()`, the books widget currently ends with (search for it):

```js
  h += "</div></div></div>";
```

immediately after the `BOOKS.forEach(...)` loop. Insert BETWEEN the forEach and that closing line:

```js
  var byLang = {};
  (function () {
    var all0 = loadAll();
    Object.keys(all0).forEach(function (id) {
      var pr = all0[id];
      if (!pr || !pr.config) return;
      var n = (pr.stories || []).filter(function (s) { return s && s.status !== "candidate"; }).length;
      if (n) byLang[pr.config.lang] = (byLang[pr.config.lang] || 0) + n;
    });
  })();
  Object.keys(byLang).forEach(function (lg) {
    var disp = null;
    LANG_CHOICES.forEach(function (c) { if (c[0] === lg) disp = c[1]; });
    var bname = (t("projName")[lg]) || (t("myBookGeneric") + " · " + (disp || lg.toUpperCase()));
    h += '<a class="book" href="reader.html#lang=' + esc(lg) + '"><span class="bname">' + esc(bname) + "</span>" +
      '<span class="bmeta">' + esc(fmt(t("myBookMeta"), { n: byLang[lg] })) + "</span>" +
      '<span class="bopen">' + esc(t("open")) + "</span></a>";
  });
```

- [ ] **Step 2: i18n (all four locales)**

```js
    myBookGeneric: "我的故事书", myBookMeta: "你收下的 {n} 篇故事",                    // zh
    myBookGeneric: "My storybook", myBookMeta: "{n} stories you kept",               // en
    myBookGeneric: "Mi libro de cuentos", myBookMeta: "{n} historias que guardaste", // es
    myBookGeneric: "わたしのストーリーブック", myBookMeta: "採用した {n} 話",          // ja
```

- [ ] **Step 3: Verify**

`node --check` on the extracted script (same one-liner as before) — clean. `grep -c "myBookGeneric" docs/index.html` → 5 (4 defs + 1 use); `grep -c "myBookMeta"` → 5.

- [ ] **Step 4: Commit**

```bash
git add docs/index.html
git commit -m "Landing: per-language my-storybook cards linking to reader.html"
```

---

### Task 3: Upload records + 词表 view

**Files:**
- Modify: `docs/index.html`: state literal (~line 772 area, `lastRaw` line), `wf` change handler, `runAiParse`, confirm-step render, `confirm` click branch (both paths), loop-view render (after the export-buttons row), CSS block, i18n ×4

**Interfaces:**
- Consumes: `state.pending`, `norm(w)`, `proj()/saveProj`, existing confirm/loop renderers.
- Produces: `project.uploads: [{id, name, date, words}]`; `state.lastFileName`; confirm-step input `#upname`; loop-view 词表 section.

- [ ] **Step 1: State + filename capture**

State literal: extend the line with `lastRaw: "",` to also include `lastFileName: "",`.

`wf` change handler — after `state.targetLang = ...` add `state.lastFileName = f.name.replace(/\.[a-z0-9]+$/i, "");` (before the PDF branch so both routes get it).

`parse` click branch (textarea path) — after its `state.aiBusy` guard add `state.lastFileName = "";`. Same line in the `ai-parse` branch.

- [ ] **Step 2: Confirm-step name input**

In the confirm-step renderer, right BEFORE the button row (`<div class="row"><button ... data-act="confirm">`), insert:

```js
    h += "<label>" + esc(t("uploadNameLabel")) + '</label><input type="text" id="upname" value="' +
      esc(state.lastFileName || fmt(t("uploadNameDefault"), { d: new Date().toLocaleDateString() })) + '">';
```

- [ ] **Step 3: Record the batch on confirm (both paths)**

At the TOP of the `confirm` click branch (before the appendMode check):

```js
    var upEl = document.getElementById("upname");
    var upRec = {
      id: "u" + Math.random().toString(36).slice(2, 9),
      name: ((upEl && upEl.value) || "").trim() || fmt(t("uploadNameDefault"), { d: new Date().toLocaleDateString() }),
      date: new Date().toISOString().slice(0, 10),
      words: state.pending.map(function (e) { return norm(e.w); })
    };
```

In the appendMode path, after `saveProj(pp)` is prepared (before it), add `pp.uploads = (pp.uploads || []).concat([upRec]);` — concretely: insert `pp.uploads = (pp.uploads || []).concat([upRec]);` on the line before `saveProj(pp);`.

In the new-project path, add `uploads: [upRec],` to the `saveProj({ id: id, config: {...}, vocab: state.pending, glossary: {}, stories: [] })` object (after `vocab:`).

Also reset `state.lastFileName = "";` in both paths alongside the existing `state.inputBuf = "";` resets, and in the `cancel` branch.

- [ ] **Step 4: 词表 section in the loop view**

In the loop-step renderer, right AFTER the export-buttons row + its `expMsg/expText` lines (search `data-act="export-tsv"` inside the loop step), insert:

```js
    (function () {
      var covSet = {};
      cov.covered.forEach(function (v) { covSet[norm(v.w)] = true; });
      var ups = (p.uploads || []).slice().reverse();
      var inBatch = {};
      (p.uploads || []).forEach(function (u) { (u.words || []).forEach(function (w) { inBatch[w] = true; }); });
      var legacy = p.vocab.filter(function (v) { return !inBatch[norm(v.w)]; });
      if (!ups.length && !legacy.length) return;
      var glossByW = {}, dispByW = {};
      p.vocab.forEach(function (v) { glossByW[norm(v.w)] = v.gloss; dispByW[norm(v.w)] = v.w; });
      h += '<details class="keyrow"><summary>' + esc(t("vocabSection")) + " · " + p.vocab.length + " " + esc(t("words")) + "</summary>";
      function batchHtml(name, date, words) {
        var c = 0;
        words.forEach(function (w) { if (covSet[w]) c++; });
        var hh = '<details class="upbatch"><summary>' + esc(name) + (date ? ' <span class="muted">· ' + esc(date) + "</span>" : "") +
          ' <span class="muted">· ' + words.length + " " + esc(t("words")) + " · " + c + "/" + words.length + " " + esc(t("coverage")) + '</span></summary><div class="chips">';
        words.forEach(function (w) {
          hh += '<span class="chip' + (covSet[w] ? " chip-cov" : "") + '" title="' + esc(glossByW[w] || "") + '">' + esc(dispByW[w] || w) + "</span>";
        });
        return hh + "</div></details>";
      }
      ups.forEach(function (u) { h += batchHtml(u.name, u.date, u.words || []); });
      if (legacy.length) h += batchHtml(t("legacyBatch"), "", legacy.map(function (v) { return norm(v.w); }));
      h += "</details>";
    })();
```

- [ ] **Step 5: CSS + i18n**

CSS (next to the existing `.chip` rules — search `.chip`):

```css
  .chip-cov { opacity: 0.45; text-decoration: line-through; }
  .upbatch { margin: 0.4rem 0 0; }
  .upbatch summary { cursor: pointer; font-size: 0.85rem; }
```

i18n (all four locales):

```js
    uploadNameLabel: "这批词的名字（会记录在词表里）", uploadNameDefault: "粘贴 · {d}", vocabSection: "📚 词表（按上传批次）", legacyBatch: "早期词表",                       // zh
    uploadNameLabel: "Name this batch (kept in your word list)", uploadNameDefault: "Pasted · {d}", vocabSection: "📚 Word list (by upload)", legacyBatch: "Earlier words",   // en
    uploadNameLabel: "Nombre de este lote (se guarda en tu lista)", uploadNameDefault: "Pegado · {d}", vocabSection: "📚 Lista de palabras (por subida)", legacyBatch: "Palabras anteriores", // es
    uploadNameLabel: "このリストの名前（語彙リストに記録）", uploadNameDefault: "貼り付け · {d}", vocabSection: "📚 語彙リスト（アップロード別）", legacyBatch: "以前の単語",       // ja
```

- [ ] **Step 6: Verify**

`node --check` on the extracted script — clean. Greps: `uploadNameLabel` ×5, `vocabSection` ×5, `legacyBatch` ×5 (wait — legacyBatch: 4 defs + 1 use = 5 ✓), `lastFileName` ≥5 (state init + wf set + 2 clears in parse/ai-parse + confirm resets), `uploads` ≥4.

- [ ] **Step 7: Commit**

```bash
git add docs/index.html
git commit -m "Upload records: named batches + vocabulary view with coverage in project view"
```

---

### Task 4: Agent-driven browser QA

**Files:** none (fixes only if found)

- [ ] **Step 1: Dispatch a browser-QA subagent** with the standing acceptance criteria (middle-schooler usability; fresh-word batches) plus, specifically:
  1. Landing shows a 「我的西语故事书 · N 篇」card (project has ≥1 story); click → reader.html renders the story book: title, story sentences, tap-word gloss popup works, story count in footer, ⌂ home link back to index.
  2. reader.html with `#lang=xx` (no projects) shows an empty book, no JS errors.
  3. Upload/paste a new small batch into the existing project (加更多词 → paste → confirm): the confirm step shows the name input (default "粘贴 · 日期"), set a custom name "测试单元"; after confirm, 📚 词表 section lists the batch with correct count and coverage; the earlier PDF words appear under 早期词表.
  4. Fresh-batch rule still holds after the new upload (next-batch chips ∩ existing stories' vocab_used = ∅).
  5. Console clean on index.html and reader.html; restore UI language to 中文; report friction points.
- [ ] **Step 2: Fix anything found; commit** (`git add -A && git commit -m "QA fixes: my-storybook + uploads round 1"`). Skip if clean.
