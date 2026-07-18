# Storybook Merge + Single Lists View + Generation Modal — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Demo stories become the default content of per-language storybooks (deletable/restorable), the widget becomes a single checkbox-driven lists view, and story generation moves from a tab into a modal.

**Architecture:** The Python build pipeline additionally emits `docs/demo-data-<lang>.js` (stories+audio per demo language) and a tiny `docs/demo-manifest.js` (counts+ids). `reader.html` (built from `fabulita/template.html`) merges built-in demo stories with localStorage stories per `#lang`, with built-in deletes recorded as a hidden-id set. `docs/index.html` drops its two tabs: the widget body is the lists view (language selector + checkbox rows + gated buttons) and generation opens in a modal overlay reusing the existing loop state and draft cache.

**Tech Stack:** Python 3 (stdlib only) + pytest for the pipeline; vanilla ES5 JS in single-file HTML for the front end (no JS test harness — frontend verification is browser QA, matching repo convention).

**Spec:** `docs/superpowers/specs/2026-07-18-storybook-merge-lists-modal-design.md`

## Global Constraints

- Frontend JS is ES5-style (var, function, no arrow functions, no template literals) — match the existing files exactly.
- All user-facing strings must exist in ALL UI languages: `fabulita/ui.py` UI_STRINGS (zh/en/es/ja — enforced by `test_ui_strings_complete`), and the inline `L` dict in `docs/index.html` (zh/en/es/ja).
- localStorage keys in use: `fabulita.studio.projects`, `fabulita.uiLang`, `fabulita.gen`, `fabulita.draft`. New keys introduced here: `fabulita.hiddenDemo`, `fabulita.listLang`. Do not touch other keys.
- JSON embedded in JS/HTML must escape `</` as `<\/` (follow `build.py`'s `.replace("</", "<\\/")`).
- `docs/reader.html` is a build artifact of `fabulita/template.html` — never hand-edit it; regenerate with `fabulita reader -o docs/reader.html`.
- Demo languages are es/en/ja from `examples/{es-a1,en-a1,ja-n5}`. Other languages (fr/de/ko/…) have no demo files and must work without them.
- Run tests with: `uv run pytest tests/ -q` (repo uses uv; `.venv` exists).

---

### Task 1: build.py — demo-data and manifest emitters (TDD)

**Files:**
- Modify: `fabulita/build.py`
- Test: `tests/test_fabulita.py` (append)

**Interfaces:**
- Produces: `build.demo_data_js(project) -> str`, `build.build_demo_data(project, out) -> (Path, int)`, `build.demo_manifest_js(projects) -> str`.
- Emitted JS shapes consumed by Tasks 2–4:
  - `demo-data-<lang>.js`: `window.FABULITA_DEMO=window.FABULITA_DEMO||{};window.FABULITA_DEMO["<lang>"]={"lang":…,"gloss_lang":…,"vocab":[…],"glossary":{…},"stories":[…],"audio":{…}};`
  - `demo-manifest.js`: `window.FABULITA_DEMO_COUNTS={"es":{"n":5,"ids":["…"]},…};`
- Accepted stories only (demos ship curated content; candidates excluded).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_fabulita.py` (reuse the existing `proj` fixture and story-building helpers already in the file — look at `test_build_single_file` for the pattern of getting a project with an accepted story):

```python
def test_demo_data_js(proj, tmp_path):
    _setup_story(proj, tmp_path)          # same helper usage as test_build_single_file
    js = build.demo_data_js(proj)
    assert js.startswith("window.FABULITA_DEMO=window.FABULITA_DEMO||{};")
    payload = js.split("=", 3)[3].rstrip(";\n")
    data = json.loads(payload.replace("<\\/", "</"))
    assert data["lang"] == proj.config["lang"]
    assert all(s["status"] == "accepted" for s in data["stories"])
    out, size = build.build_demo_data(proj, tmp_path / "demo-data-es.js")
    assert out.exists() and size == len(js)


def test_demo_manifest_js(proj, tmp_path):
    _setup_story(proj, tmp_path)
    js = build.demo_manifest_js([proj])
    assert js.startswith("window.FABULITA_DEMO_COUNTS=")
    data = json.loads(js.split("=", 1)[1].rstrip(";\n").replace("<\\/", "</"))
    lang = proj.config["lang"]
    assert data[lang]["n"] == len(data[lang]["ids"]) == 1
```

Note: if `tests/test_fabulita.py` has no `_setup_story` helper, inline whatever `test_build_single_file` does to reach "project with 1 accepted story" — copy those lines rather than inventing new fixtures. The split index in `js.split("=", 3)[3]` accounts for the three `=` in `window.FABULITA_DEMO=window.FABULITA_DEMO||{};window.FABULITA_DEMO["es"]=…` — verify against the actual emitted prefix and adjust if you change the prefix format.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_fabulita.py -q -k "demo_data or demo_manifest"`
Expected: FAIL — `AttributeError: module 'fabulita.build' has no attribute 'demo_data_js'`

- [ ] **Step 3: Implement in `fabulita/build.py`**

Add after `payload()`:

```python
def demo_data_js(project):
    """JS snippet defining window.FABULITA_DEMO[<lang>] for the self-serve reader."""
    data = payload(project, include_candidates=False)
    demo = {
        "lang": data["config"]["lang"],
        "gloss_lang": data["config"]["gloss_lang"],
        "vocab": data["vocab"],
        "glossary": data["glossary"],
        "stories": data["stories"],
        "audio": data["audio"],
    }
    blob = json.dumps(demo, ensure_ascii=False).replace("</", "<\\/")
    return ("window.FABULITA_DEMO=window.FABULITA_DEMO||{};"
            "window.FABULITA_DEMO[" + json.dumps(demo["lang"]) + "]=" + blob + ";\n")


def build_demo_data(project, out):
    js = demo_data_js(project)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(js, encoding="utf-8")
    return out, len(js)


def demo_manifest_js(projects):
    """Tiny per-language {n, ids} manifest so index.html can show counts cheaply."""
    counts = {}
    for p in projects:
        stories = [s for s in p.stories() if s.get("status") == "accepted"]
        counts[p.config["lang"]] = {"n": len(stories), "ids": [s["id"] for s in stories]}
    blob = json.dumps(counts, ensure_ascii=False).replace("</", "<\\/")
    return "window.FABULITA_DEMO_COUNTS=" + blob + ";\n"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/ -q`
Expected: all PASS (including the two new tests)

- [ ] **Step 5: Commit**

```bash
git add fabulita/build.py tests/test_fabulita.py
git commit -m "build: emit demo-data JS and demo manifest for the merged storybook"
```

---

### Task 2: scripts/build_docs.py — one-command docs rebuild

**Files:**
- Create: `scripts/build_docs.py`
- Modify: `README.md` (development section — add one line documenting the script)

**Interfaces:**
- Consumes: `build.build_demo_data`, `build.demo_manifest_js` (Task 1); existing `build.build`, `build.build_reader`, `build.build_studio`.
- Produces: `docs/demo-data-{es,en,ja}.js`, `docs/demo-manifest.js`, refreshed `docs/demo-*.html`, `docs/reader.html`, `docs/studio.html`. Tasks 3–4 rely on these files existing in `docs/`.

- [ ] **Step 1: Write the script**

```python
#!/usr/bin/env python
"""Rebuild every generated file under docs/ from examples/ and fabulita/.

Usage: uv run python scripts/build_docs.py
"""
from pathlib import Path

from fabulita import build
from fabulita.project import Project

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
DEMOS = {"es": "es-a1", "en": "en-a1", "ja": "ja-n5"}


def main():
    projects = []
    for lang, name in DEMOS.items():
        proj = Project(ROOT / "examples" / name)
        proj.require()
        projects.append(proj)
        out, size = build.build_demo_data(proj, DOCS / ("demo-data-" + lang + ".js"))
        print("wrote " + str(out) + " (" + str(size // 1024) + " KB)")
        page, psize, n, clips = build.build(
            proj, out=DOCS / ("demo-" + lang + ".html"),
            include_candidates=False, home="index.html")
        print("wrote " + str(page) + " (" + str(n) + " stories, " + str(clips) + " clips)")
    (DOCS / "demo-manifest.js").write_text(build.demo_manifest_js(projects), encoding="utf-8")
    print("wrote " + str(DOCS / "demo-manifest.js"))
    build.build_reader(DOCS / "reader.html")
    build.build_studio(DOCS / "studio.html")
    print("wrote reader.html + studio.html")


if __name__ == "__main__":
    main()
```

Before finalizing, diff a freshly rebuilt `docs/demo-es.html` against the committed one (`git diff --stat docs/demo-es.html`). If the committed demos were built WITH candidates or a different `--home`, match the original flags instead of the ones above so the rebuild is not a regression — check `git log` for the build command or compare story counts.

- [ ] **Step 2: Run it and verify output**

Run: `uv run python scripts/build_docs.py`
Expected: prints one `wrote …` line per artifact; `ls docs/demo-data-*.js docs/demo-manifest.js` shows 4 new files; `head -c 120 docs/demo-manifest.js` starts with `window.FABULITA_DEMO_COUNTS={`.

- [ ] **Step 3: Sanity-check manifest vs data**

Run: `node -e "global.window={};require('/dev/stdin')" < docs/demo-manifest.js && echo OK` (or open in a scratch HTML — the point: each file parses as JS).
Also verify counts: manifest `n` for `es` equals the number of stories in `docs/demo-data-es.js`.

- [ ] **Step 4: README**

Add to the development/contributing section of `README.md`:

```markdown
Regenerate everything under `docs/` (demo pages, demo data, reader, studio):

    uv run python scripts/build_docs.py
```

- [ ] **Step 5: Commit**

```bash
git add scripts/build_docs.py docs/demo-data-*.js docs/demo-manifest.js docs/demo-*.html README.md
git commit -m "docs build: script to regenerate docs/ artifacts; emit demo data + manifest"
```

---

### Task 3: template.html — merged storybook (built-ins + delete/restore)

**Files:**
- Modify: `fabulita/template.html`
- Modify: `fabulita/ui.py` (add `restoreDemo` string to all 4 UI langs)
- Regenerate: `docs/reader.html`

**Interfaces:**
- Consumes: `window.FABULITA_DEMO[<lang>]` (Task 1 shape).
- Produces: localStorage `fabulita.hiddenDemo` = `{"<lang>": ["storyId", …]}` — Task 4's index counts subtract these ids. Built-in stories carry `_builtin: true` (in-memory only, never persisted).

- [ ] **Step 1: ui.py strings**

In `fabulita/ui.py`, next to each `delStory` entry add:

```python
        "restoreDemo": "恢复内置故事",            # zh block (line ~28)
        "restoreDemo": "Restore built-in stories", # en block
        "restoreDemo": "Restaurar historias integradas",  # es block
        "restoreDemo": "内蔵ストーリーを復元",     # ja block
```

Run: `uv run pytest tests/test_fabulita.py::test_ui_strings_complete -q` → PASS.

- [ ] **Step 2: demo-data loader script**

In `fabulita/template.html`, between the payload script (`<script>var P = /*__PAYLOAD__*/null;</script>`, line ~219) and the main IIFE, insert a parser-blocking loader (document.write guarantees the demo-data script executes before the main IIFE):

```html
<script>
(function () {
  if (!(P && P.self)) return;
  var m = (location.hash || "").match(/lang=([a-z]{2})/i);
  if (!m) return;
  document.write('<script src="demo-data-' + m[1].toLowerCase() + '.js"><\/script>');
})();
</script>
```

A missing file (non-demo language) 404s silently and `window.FABULITA_DEMO` stays undefined — every consumer below must tolerate that.

- [ ] **Step 3: merge built-ins in the self-mode boot**

In the self-mode IIFE (template line ~224), after the `Object.keys(all).forEach(…)` loop that fills `stories`/`vocab`/`glossary`, insert:

```javascript
        var hd = {};
        try { hd = JSON.parse(localStorage.getItem("fabulita.hiddenDemo")) || {}; } catch (e) {}
        var hiddenIds = hd[langSel] || [];
        var demo = (window.FABULITA_DEMO || {})[langSel];
        var demoStories = [];
        if (demo) {
          (demo.stories || []).forEach(function (s) {
            if (hiddenIds.indexOf(s.id) !== -1) return;
            s._builtin = true;
            demoStories.push(s);
          });
          (demo.vocab || []).forEach(function (v) {
            if (!v || typeof v.w !== "string") return;
            var k = v.w.normalize("NFC").toLowerCase();
            if (k && !seenW[k]) { seenW[k] = true; vocab.push(v); }
          });
          var dg = demo.glossary || {};
          Object.keys(dg).forEach(function (k) { if (!(k in glossary)) glossary[k] = dg[k]; });
          if (!glossLang) glossLang = demo.gloss_lang || "";
        }
```

Then change the assignments below (currently `P.stories = stories; … P.audio = {};`) to:

```javascript
        P.stories = demoStories.concat(stories);
        P.vocab = vocab;
        P.glossary = glossary;
        P.audio = (demo && demo.audio) || {};
```

(User-kept stories have no ids in `P.audio`, so they keep falling back to speechSynthesis exactly as today.)

- [ ] **Step 4: delete button on built-ins + restore button**

In `storyHtml` (template line ~365) extend the self-mode delete button with a builtin marker:

```javascript
    if (P.self) {
      var delLabel = (delArmed === s.id) ? t("delConfirm") : t("delStory");
      h += '<button class="ctl del-story" data-del="' + esc(s.id) + '" data-pid="' + esc(s._pid || "") + '"' +
        (s._builtin ? ' data-builtin="1"' : "") + '>' + esc(delLabel) + "</button>";
    }
```

In `render()` (line ~424), after the `<div class="controls">…</div></header>` chunk, add a restore control shown only when built-ins are hidden:

```javascript
    if (P.self && P.config.lang) {
      var hd0 = {};
      try { hd0 = JSON.parse(localStorage.getItem("fabulita.hiddenDemo")) || {}; } catch (e) {}
      if ((hd0[P.config.lang] || []).length) {
        h += '<div class="controls"><button class="ctl" id="restore-demo">' + esc(t("restoreDemo")) + "</button></div>";
      }
    }
```

(Insert BEFORE the closing `</header>` so it sits with the other controls; adjust the string concatenation accordingly.)

In the delegated click handler (line ~592), branch the armed-confirm delete:

```javascript
    if (P.self && (el = e.target.closest(".del-story"))) {
      var sid = el.dataset.del, pid = el.dataset.pid;
      if (delArmed !== sid) {
        /* …existing arming code unchanged… */
        return;
      }
      delArmed = null;
      if (el.dataset.builtin) {
        try {
          var hdd = JSON.parse(localStorage.getItem("fabulita.hiddenDemo")) || {};
          var lg = P.config.lang;
          if ((hdd[lg] || []).indexOf(sid) === -1) hdd[lg] = (hdd[lg] || []).concat([sid]);
          localStorage.setItem("fabulita.hiddenDemo", JSON.stringify(hdd));
        } catch (err) {}
        location.reload();
        return;
      }
      /* …existing localStorage projects delete unchanged… */
    }
```

And add the restore handler alongside the other `closest(…)` branches:

```javascript
    if (P.self && (el = e.target.closest("#restore-demo"))) {
      try {
        var hdr = JSON.parse(localStorage.getItem("fabulita.hiddenDemo")) || {};
        delete hdr[P.config.lang];
        localStorage.setItem("fabulita.hiddenDemo", JSON.stringify(hdr));
      } catch (err) {}
      location.reload();
      return;
    }
```

- [ ] **Step 5: regenerate reader + tests**

```bash
uv run fabulita reader -o docs/reader.html
uv run pytest tests/ -q
```
Expected: tests PASS; `grep -c FABULITA_DEMO docs/reader.html` ≥ 2.

- [ ] **Step 6: Browser QA (serve docs/, e.g. `python3 -m http.server -d docs 8000`)**

- `reader.html#lang=es` → demo stories appear with audio playback; word popovers work on demo sentences.
- Delete a demo story (two clicks) → gone after reload; restore button appears; restore → back.
- Keep one own Spanish story (via index) → it appears after the demo stories, delete on it still真删.
- `reader.html#lang=fr` (no demo file) → no console-breaking error, page renders (empty or own stories only).

- [ ] **Step 7: Commit**

```bash
git add fabulita/template.html fabulita/ui.py docs/reader.html
git commit -m "reader: merge built-in demo stories per language with hide/restore delete"
```

---

### Task 4: index.html — storybook rows replace demo links

**Files:**
- Modify: `docs/index.html`

**Interfaces:**
- Consumes: `window.FABULITA_DEMO_COUNTS` (Task 1 shape), `fabulita.hiddenDemo` (Task 3 shape).
- Produces: books section links only to `reader.html#lang=<lang>`; `BOOKS` constant and `demo-*.html` links removed.

- [ ] **Step 1: load the manifest**

Immediately before the main `<script>` of `docs/index.html` add:

```html
<script src="demo-manifest.js"></script>
```

- [ ] **Step 2: replace the books section in `render()`**

Delete the `BOOKS` constant (line ~418) and, inside `render()` (lines ~1254–1281), replace both the `BOOKS.forEach(…)` block and the `byLang`-rows block with a single per-language loop (keep the existing `byLang` computation):

```javascript
  var manifest = window.FABULITA_DEMO_COUNTS || {};
  var hd = {};
  try { hd = JSON.parse(localStorage.getItem("fabulita.hiddenDemo")) || {}; } catch (e) {}
  var shown = {};
  var rowLangs = [];
  LANG_CHOICES.forEach(function (c) {
    if (manifest[c[0]] || byLang[c[0]]) { rowLangs.push(c[0]); shown[c[0]] = true; }
  });
  Object.keys(byLang).forEach(function (lg) { if (!shown[lg]) rowLangs.push(lg); });
  rowLangs.forEach(function (lg) {
    var disp = null;
    LANG_CHOICES.forEach(function (c) { if (c[0] === lg) disp = c[1]; });
    var mf = manifest[lg], hiddenN = 0;
    if (mf) (hd[lg] || []).forEach(function (id) { if (mf.ids.indexOf(id) !== -1) hiddenN++; });
    var n = (mf ? Math.max(0, mf.n - hiddenN) : 0) + (byLang[lg] || 0);
    var bname = (disp || lg.toUpperCase());
    h += '<a class="book" href="reader.html#lang=' + esc(lg) + '"><span class="bname">' + esc(bname) + "</span>" +
      '<span class="bmeta">' + esc(fmt(t("myBookMeta"), { n: n })) + "</span>" +
      '<span class="bopen">' + esc(t("open")) + "</span></a>";
  });
```

Update the widget head copy: the `choose` string in all 4 `L` blocks becomes the storybook heading (zh `我的故事书`, en `My storybooks`, es `Mis libros de cuentos`, ja `わたしのストーリーブック`), and the muted subtitle under it (currently `BOOKS.map(names)`) becomes the demo language names from `LANG_CHOICES` filtered to `manifest` keys. Remove now-unused strings (`meta` per-demo descriptions, `projName` if unreferenced after this change — grep before deleting).

- [ ] **Step 3: Browser QA**

- Fresh profile (or cleared localStorage): three rows Español/English/日本語 with demo counts; clicking opens the merged reader.
- Hide one demo story in the reader → index count drops by 1.
- Keep a French story → a Français row appears with count 1.

- [ ] **Step 4: Commit**

```bash
git add docs/index.html
git commit -m "index: per-language storybook rows (manifest counts) replace demo links"
```

---

### Task 5: index.html — single lists view with language selector + checkbox gating

**Files:**
- Modify: `docs/index.html`

**Interfaces:**
- Consumes: existing `listsOf(lang)`, `state.genSel`, `gsel` action, draft-clearing reset used by `gsel` (lines ~1492–1510).
- Produces: `state.listLang` (persisted as `fabulita.listLang`), checkbox rows in the lists table, and three gated buttons; `data-act="gen-open"` for Task 6. Tabs removed.

- [ ] **Step 1: state + constants**

Near the other `LS*` constants add `var LSLL = "fabulita.listLang";`. In `state` (line ~530): drop `tab: "lists"`, add:

```javascript
  listLang: (function () { try { var v = localStorage.getItem(LSLL); if (v) return v; } catch (e) {} return "es"; })(),
  genOpen: false,
```

- [ ] **Step 2: rewrite `listTableHtml()` (line ~1172)**

```javascript
function listTableHtml() {
  var h = "<label>" + esc(t("targetLang")) + '</label><select id="ll">';
  LANG_CHOICES.forEach(function (c) {
    h += '<option value="' + c[0] + '"' + (c[0] === state.listLang ? " selected" : "") + ">" + c[1] + "</option>";
  });
  h += "</select>";
  var lists = listsOf(state.listLang);
  if (!lists.length) {
    h += '<p class="muted" style="margin-top:0.8rem">' + esc(t("noLists")) + "</p>";
  } else {
    h += '<div class="plist">';
    var covd = langCovered(state.listLang);
    lists.forEach(function (p) {
      var c = 0, vocab = p.vocab || [];
      vocab.forEach(function (v) { if (covd[norm(v.w)]) c++; });
      var checked = state.genSel.indexOf(p.id) !== -1;
      h += '<div class="lrow"><input type="checkbox" data-act="gsel" data-id="' + esc(p.id) + '"' + (checked ? " checked" : "") +
        ' style="margin-right:0.5rem">' +
        '<div data-act="open-list" data-id="' + esc(p.id) + '" style="flex:1;cursor:pointer"><span class="pname">' + esc(p.config.name) +
        '</span> <span class="muted">· ' + vocab.length + " " + esc(t("words")) + " · " + c + "/" + vocab.length + "</span></div><span>→</span></div>";
    });
    h += "</div>";
  }
  var nSel = state.genSel.length;
  h += '<div class="row"><button class="btn" data-act="new-list">' + esc(t("newList")) + "</button>" +
    '<button class="btn" data-act="upload-words"' + (nSel > 1 ? " disabled" : "") + ">" + esc(t("uploadWords")) + "</button>" +
    '<button class="btn btn-primary" data-act="gen-open"' + (nSel < 1 ? " disabled" : "") + ">" + esc(t("generate")) + "</button></div>";
  if (state.newListOpen) {
    h += "<label>" + esc(t("newListName")) + '</label><input type="text" id="nl-name" value="">';
    h += '<div class="row"><button class="btn btn-primary" data-act="new-list-save">' + esc(t("newListSave")) + "</button>" +
      '<button class="btn" data-act="new-list">' + esc(t("cancel")) + "</button></div>";
  }
  return h;
}
```

Notes: the checkbox itself carries `data-act="gsel"` (clickable), the name div opens detail — the old whole-row `gsel` is gone. The new-list inline form loses its own language select — `new-list-save` (line ~1450) now reads `var nlLang = state.listLang;` (delete the `#wl` lookup there). The language row display (`disp`) is dropped since all rows share `state.listLang`.

- [ ] **Step 3: language switch + upload gating handlers**

In the `change` listener add:

```javascript
  if (e.target.id === "ll") {
    state.listLang = e.target.value;
    try { localStorage.setItem(LSLL, state.listLang); } catch (err) {}
    state.targetLang = state.listLang;
    state.genSel = [];
    state.genSrc.words = [];
    var lp2 = state.loop;
    lp2.runId = (lp2.runId || 0) + 1;
    lp2.phase = "idle"; lp2.story = null; lp2.warnings = []; lp2.missing = []; lp2.error = null; lp2.targetId = null;
    clearDraft();
    render();
    return;
  }
```

Change the `upload-words` action (line ~1448) to respect the selection:

```javascript
  else if (act === "upload-words") {
    if (state.aiBusy || state.genSel.length > 1) return;
    if (state.genSel.length === 1) {
      var upList = loadAll()[state.genSel[0]];
      state.uploadTarget = upList ? upList.id : "__new";
      if (upList) state.targetLang = upList.config.lang;
    } else {
      state.uploadTarget = "__new";
      state.targetLang = state.listLang;
    }
    state.step = "input";
    render();
  }
```

In `uploadInputHtml()` the `#wl` default already tracks `state.targetLang` — no change needed there.

- [ ] **Step 4: retire the tabs**

Delete `tabsHtml()` (lines ~1007–1011), the `tab-lists`/`tab-gen` actions (lines ~1446–1447), and change `widgetBody()` to:

```javascript
function widgetBody() { return listsBody(); }
```

(`genBody` is dealt with in Task 6 — for this commit, `gen-open` may temporarily render nothing; that's fine, Tasks 5+6 land together in QA but commit separately for reviewability. If you prefer a green intermediate state, make `gen-open` a no-op `return;` action here.)

- [ ] **Step 5: Browser QA (with Task 6 if landing together, else smoke-only)**

- Language selector persists across reload; switching clears checks.
- 0 checked → 生成故事 disabled, upload targets 新建; 1 checked → upload preselects that list; 2 checked → upload disabled.
- New list uses the selector's language, appears as 0/0 row.
- List detail (click name), add-words, export, two-step delete all still work.

- [ ] **Step 6: Commit**

```bash
git add docs/index.html
git commit -m "index: single lists view — language selector, checkbox rows, gated actions"
```

---

### Task 6: index.html — generation modal

**Files:**
- Modify: `docs/index.html`

**Interfaces:**
- Consumes: `state.genOpen` + `data-act="gen-open"` (Task 5), existing `state.loop`, `saveDraft`/`clearDraft`, `genLists()/genBatch()/genUnion()`.
- Produces: `genLoopHtml()` (genBody minus the selection rows), `modalHtml()`, `gen-close` action; boot-restore opens the modal.

- [ ] **Step 1: CSS**

Add to the stylesheet:

```css
.modal-backdrop { position: fixed; inset: 0; background: rgba(20,18,14,0.45); z-index: 40; display: flex; align-items: flex-start; justify-content: center; padding: 4vh 1rem; overflow-y: auto; }
.modal { background: var(--bg, #fff); border-radius: 10px; max-width: 42rem; width: 100%; padding: 1.2rem 1.4rem; position: relative; }
.modal-x { position: absolute; top: 0.6rem; right: 0.8rem; font-size: 1.1rem; background: none; border: none; cursor: pointer; color: var(--muted); }
```

(Reuse the page's existing background/border variables — check `:root` and match; do not invent a new palette.)

- [ ] **Step 2: genBody → genLoopHtml**

Rename `genBody()` (line ~1013) to `genLoopHtml()` and delete its list-selection block — remove the `if (!allLists.length) …` guard and the whole `allLists.forEach` `.plist` block (lines ~1015–1031). The function now starts at `var lists = genLists(), lp = state.loop;` and keeps everything else (coverage bar, source select, chips, preview, keep/reroll/stop, settings, manualHtml).

- [ ] **Step 3: modal render**

```javascript
function modalHtml() {
  return '<div class="modal-backdrop" data-act="gen-close"><div class="modal" data-modal-body>' +
    '<button class="modal-x" data-act="gen-close" aria-label="close">✕</button>' +
    "<h2 style='margin-top:0'>" + esc(t("tabGen")) + "</h2>" + genLoopHtml() + "</div></div>";
}
```

In `render()` append after the footer line:

```javascript
  if (state.genOpen) h += modalHtml();
```

Clicks inside the modal body must not close it — the backdrop carries `data-act="gen-close"`, so in the click handler resolve `gen-close` ONLY when the click did not land inside `[data-modal-body]` (except the ✕ button):

```javascript
  else if (act === "gen-close") {
    if (e.target.closest("[data-modal-body]") && !e.target.closest(".modal-x")) return;
    state.genOpen = false; render();
  }
  else if (act === "gen-open") {
    if (!state.genSel.length) return;
    state.genOpen = true; state.loop.error = null; render();
  }
```

Add Escape handling to the existing keydown listener:

```javascript
  if (e.key === "Escape" && state.genOpen) { state.genOpen = false; render(); return; }
```

Draft/keep semantics need NO change: closing does not touch `state.loop` or the draft; an in-flight `startGenerate` keeps running (run-token) and `saveDraft()` fires on arrival, so reopening (or reloading) restores the preview.

- [ ] **Step 4: boot restore opens the modal**

In the boot IIFE (line ~1647), replace `state.tab = "gen";` with:

```javascript
    state.genOpen = true;
    var bootList = loadAll()[d.targetId];
    if (bootList) {
      state.listLang = bootList.config.lang;
      try { localStorage.setItem(LSLL, state.listLang); } catch (e2) {}
    }
```

- [ ] **Step 5: strings sweep**

`tabGen` becomes the modal title (keep the key, all 4 langs already have it). Grep for now-dead keys (`tabLists` if unused after Task 5) and remove from all 4 `L` blocks together. Every remaining `t("…")` call must resolve in all 4 blocks.

- [ ] **Step 6: Browser QA (full flow)**

- Check 1 list → 生成故事 opens modal; source select/manual chips/AI-pick hint render; generate → spinner → preview with 朗读 and word popovers.
- 收下 → modal stays open back at source selection, coverage bar updated; story appears in the right storybook.
- Close modal mid-generation → reopen shows preview when done; reload mid-preview → modal reopens with preview (draft restore).
- Esc and backdrop close; clicks inside do not close; ✕ closes.
- Multi-list selection: union coverage shown, keep targets the first checked list.

- [ ] **Step 7: Commit**

```bash
git add docs/index.html
git commit -m "index: generation moves into a modal; draft restore opens it"
```

---

### Task 7: final rebuild, full test pass, review

**Files:**
- Regenerate: `docs/` artifacts via `scripts/build_docs.py`
- Modify: `README.md` if any user-facing flow description mentions the tabs/demos

- [ ] **Step 1:** `uv run python scripts/build_docs.py` then `git status` — commit any drifted artifacts.
- [ ] **Step 2:** `uv run pytest tests/ -q` → all PASS.
- [ ] **Step 3:** Grep README/PRODUCT.md for stale UI descriptions (`生成故事` tab, demo links) and update.
- [ ] **Step 4:** Full browser QA pass across the checklist items of Tasks 3–6 in one session, including a fresh-profile first-run.
- [ ] **Step 5:** Commit, then request code review (superpowers:requesting-code-review).

```bash
git add -A && git commit -m "docs: rebuild artifacts; README copy for merged storybook UI"
```
