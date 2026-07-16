# PDF Upload + LLM Smart Parse Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The landing-page add-vocab widget accepts PDF word lists, normalizes them into `{w, gloss}` pairs via the configured LLM provider, and lets the user export the normalized list.

**Architecture:** All changes live in `docs/index.html` (single-file page, ES5-style IIFE, no build step). PDF text is extracted client-side with pdf.js (lazy dynamic `import()` from jsDelivr, pinned `pdfjs-dist@6.1.200`); the messy text goes to the already-configured provider (Ollama/Qwen/Anthropic/custom) with a prompt that returns `{"words":[{"w":"hola","gloss":"hello"}]}`; results feed the existing confirm table. A "Parse with AI" fallback appears for messy plain text. Export buttons (copy `w → gloss` lines / download TSV) are added to the confirm table and the project loop view.

**Tech Stack:** Vanilla JS (ES5 style, matching file), pdf.js 6.1.200 via jsDelivr, existing provider plumbing (`generateAnthropic` / OpenAI-compatible fetch).

**Spec:** `docs/superpowers/specs/2026-07-16-pdf-upload-llm-parse-design.md`

## Global Constraints

- Single file: every change goes into `docs/index.html`. No new files, no build tooling.
- Match the file's existing style: `var`, `function` declarations, no arrow functions, no template literals, double-quoted strings.
- pdf.js pinned exactly: `https://cdn.jsdelivr.net/npm/pdfjs-dist@6.1.200/build/pdf.min.mjs` and `.../pdf.worker.min.mjs` (verified live 2026-07-16).
- All four UI locales (`zh`, `en`, `es`, `ja`) get every new string — the `L` object blocks start at approx lines 133 (zh), 185 (en), 237 (es), 289 (ja).
- Glosses are never translated by the LLM — keep source language.
- LLM output goes to the confirm table, never straight into a project.
- **No JS test harness exists** (repo tests are Python-only, for the `fabulita` package; the page's convention is manual QA rounds — see commit history). Each task therefore ends with concrete browser verification steps instead of unit tests. A local server is assumed at `http://localhost:8901/` serving `docs/` (`cd docs && python3 -m http.server 8901`).
- Test fixture: `~/Downloads/Vocabulario_A1_1_Tabla.pdf` (150-row table `Español | Inglés | Escribe aquí`).

---

### Task 1: Generic LLM completion plumbing + `llmParseVocab` core

**Files:**
- Modify: `docs/index.html:548-606` (provider call functions)
- Modify: `docs/index.html:443` (after `parseVocab`, add vocab-LLM helpers)

**Interfaces:**
- Consumes: existing `genCfg()`, `norm(w)`, `t(k)`, `PROV`, `httpError`, `parseStoryText`.
- Produces (used by Tasks 2–3):
  - `llmParseVocab(text: string): Promise<Array<{w: string, gloss: string}>>` — sends text to the configured provider, returns validated, deduped entries. Rejects with `Error` on network/JSON failure.
  - `openaiChat(g, prompt): Promise<string>` — raw assistant text from an OpenAI-compatible endpoint.
  - `generateAnthropic(g, prompt, schema): Promise<object>` — now takes an explicit JSON schema (story callers pass `API_SCHEMA`).
  - `normalizeVocabList(raw): Array<{w, gloss}>` — validates/dedupes a parsed `{words:[...]}` object or bare array; throws if no list found.

- [ ] **Step 1: Split `generateOpenAI` into `openaiChat` + thin wrapper**

Replace the existing `generateOpenAI` function (lines 574-598) with:

```js
function openaiChat(g, prompt) {
  var base = (g.base || (PROV[g.provider] && PROV[g.provider].base) || "").replace(/\/+$/, "");
  var headers = { "content-type": "application/json" };
  if (g.key) headers["Authorization"] = "Bearer " + g.key;
  var ctrl = new AbortController();
  var timer = setTimeout(function () { ctrl.abort(); }, 180000);
  return fetch(base + "/chat/completions", {
    method: "POST", headers: headers, signal: ctrl.signal,
    body: JSON.stringify({
      model: g.model, stream: false,
      response_format: { type: "json_object" },
      messages: [{ role: "user", content: prompt }]
    })
  }).catch(function (err) {
    if (err && err.name === "AbortError") throw new Error("timeout (180 s)");
    throw new Error(t("errConn") + base);
  }).then(function (res) {
    clearTimeout(timer);
    if (!res.ok) return httpError(res);
    return res.json();
  }).then(function (data) {
    var msg = data.choices && data.choices[0] && data.choices[0].message;
    return (msg && msg.content) || "";
  });
}

function generateOpenAI(g, prompt) {
  return openaiChat(g, prompt).then(parseStoryText);
}
```

- [ ] **Step 2: Parametrize `generateAnthropic` with a schema argument**

In `generateAnthropic` (line 548), change the signature and the `output_config` line:

```js
function generateAnthropic(g, prompt, schema) {
```

```js
      output_config: { format: { type: "json_schema", schema: schema || API_SCHEMA } },
```

(Existing story callsite in `generateStory` line 603 stays `generateAnthropic(g, prompt)` — the default keeps it working.)

- [ ] **Step 3: Add vocab schema, prompt, normalizer, and `llmParseVocab`**

Insert directly after the `parseVocab` function (after line 443):

```js
// ───────────────────────── vocab parsing via LLM ─────────────────────────
var VOCAB_SCHEMA = {
  type: "object", additionalProperties: false, required: ["words"],
  properties: {
    words: {
      type: "array",
      items: {
        type: "object", additionalProperties: false, required: ["w", "gloss"],
        properties: { w: { type: "string" }, gloss: { type: "string" } }
      }
    }
  }
};

function vocabParsePrompt(text) {
  return "Below is raw text extracted from a vocabulary document (often a PDF table — it may contain titles, table headers, page numbers, empty practice columns and other noise).\n\n" +
    "Extract the vocabulary as word/gloss pairs.\n\nRules:\n" +
    "- Drop titles, table headers, column labels (e.g. \"Escribe aquí\"), page numbers and anything that is not a vocabulary entry.\n" +
    "- One entry per word; if a word has several meanings, join them with \"; \".\n" +
    "- Keep glosses EXACTLY in their source language — do NOT translate them.\n" +
    "- Deduplicate words.\n\n" +
    "Return ONLY a JSON object in this exact shape (no markdown fence, no commentary):\n\n" +
    "{\"words\":[{\"w\":\"hola\",\"gloss\":\"hello\"}]}\n\nText:\n\n" + text;
}

function normalizeVocabList(raw) {
  var list = raw && (Array.isArray(raw) ? raw : raw.words);
  if (!Array.isArray(list)) throw new Error("no words[] in model output");
  var entries = [], seen = {};
  list.forEach(function (e) {
    if (!e || typeof e.w !== "string" || typeof e.gloss !== "string") return;
    var w = e.w.trim(), gloss = e.gloss.trim();
    if (!w || !gloss) return;
    var k = norm(w);
    if (seen[k]) return;
    seen[k] = true;
    entries.push({ w: w, gloss: gloss });
  });
  return entries;
}

function parseVocabJSON(text) {
  text = text.replace(/<think>[\s\S]*?<\/think>/gi, "").trim();
  var a = text.indexOf("{"), b = text.lastIndexOf("}");
  if (a === -1 || b < a) throw new Error("no JSON in model output");
  return normalizeVocabList(JSON.parse(text.slice(a, b + 1)));
}

function llmParseVocab(text) {
  var g = genCfg();
  var prompt = vocabParsePrompt(text);
  if (g.provider === "anthropic") return generateAnthropic(g, prompt, VOCAB_SCHEMA).then(normalizeVocabList);
  if (/^qwen3\b/i.test(g.model || "")) prompt += "\n\n/no_think";
  return openaiChat(g, prompt).then(parseVocabJSON);
}
```

- [ ] **Step 4: Verify — no regression**

1. Hard-reload `http://localhost:8901/index.html` (cmd+shift+R); open DevTools console — expect **zero errors** on load.
2. Regression: open the add-vocab widget, paste `hola, hello` + `adiós, goodbye` (two lines), Parse & review → confirm → with a configured provider, generate one story. Expect story preview renders (proves `generateOpenAI`/`generateAnthropic` refactor didn't break the story path).

- [ ] **Step 5: Commit**

```bash
git add docs/index.html
git commit -m "Refactor provider calls; add llmParseVocab core (LLM vocab normalization)"
```

---

### Task 2: PDF upload end-to-end

**Files:**
- Modify: `docs/index.html:354-359` (after `PROV`, add pdf.js constants + loader)
- Modify: `docs/index.html:372-384` (state init: add `aiBusy`, `aiErr`, `lastRaw`)
- Modify: `docs/index.html:726` (file input `accept`)
- Modify: `docs/index.html:721-729` (input-step UI: busy/error messages)
- Modify: `docs/index.html:1006-1020` (change handler: route PDFs)
- Modify: `docs/index.html:849-854` (add `runAiParse` next to `doParse`)
- Modify: i18n blocks (~133/185/237/289): new strings

**Interfaces:**
- Consumes: `llmParseVocab(text)` (Task 1), `genReady()`, `t(k)`, `esc`, `render`, existing state machine (`state.step`, `state.pending`, `state.skipped`).
- Produces (used by Task 3):
  - `runAiParse(getText: () => string|Promise<string>): void` — full AI-parse flow: provider guard → busy spinner → `llmParseVocab` → confirm table or error.
  - `extractPdfText(file: File): Promise<string>`.
  - State fields: `state.aiBusy: boolean`, `state.aiErr: string|null`, `state.lastRaw: string`.

- [ ] **Step 1: Add pdf.js loader constants + `loadPdfjs` + `extractPdfText`**

Insert after the `PROV` block (after line 359):

```js
var PDFJS_URL = "https://cdn.jsdelivr.net/npm/pdfjs-dist@6.1.200/build/pdf.min.mjs";
var PDFJS_WORKER = "https://cdn.jsdelivr.net/npm/pdfjs-dist@6.1.200/build/pdf.worker.min.mjs";
var pdfjsPromise = null;
function loadPdfjs() {
  if (!pdfjsPromise) {
    pdfjsPromise = import(PDFJS_URL).then(function (m) {
      m.GlobalWorkerOptions.workerSrc = PDFJS_WORKER;
      return m;
    });
    pdfjsPromise.catch(function () { pdfjsPromise = null; });
  }
  return pdfjsPromise;
}
function extractPdfText(file) {
  return loadPdfjs().catch(function () { throw new Error(t("errPdfLoad")); })
    .then(function (lib) {
      return file.arrayBuffer().then(function (buf) {
        return lib.getDocument({ data: buf }).promise;
      });
    }).then(function (doc) {
      var chain = Promise.resolve([]);
      for (var i = 1; i <= doc.numPages; i++) {
        (function (n) {
          chain = chain.then(function (acc) {
            return doc.getPage(n).then(function (pg) { return pg.getTextContent(); }).then(function (tc) {
              acc.push(tc.items.map(function (it) { return it.str; }).join(" "));
              return acc;
            });
          });
        })(i);
      }
      return chain.then(function (acc) { return acc.join("\n"); });
    });
}
```

- [ ] **Step 2: Add state fields**

In the `state` literal (line 378, next to `pending: null, skipped: 0,`):

```js
  pending: null, skipped: 0, aiBusy: false, aiErr: null, lastRaw: "",
```

- [ ] **Step 3: Add `runAiParse` next to `doParse`**

Insert after `doParse` (after line 854):

```js
function runAiParse(getText) {
  if (!genReady()) { state.aiErr = t("aiNeedProvider"); state.keyOpen = true; render(); return; }
  state.aiBusy = true; state.aiErr = null; state.step = "input"; render();
  Promise.resolve().then(getText).then(function (text) {
    text = String(text || "");
    if (!text.replace(/\s/g, "")) throw new Error(t("errPdfScan"));
    state.lastRaw = text;
    return llmParseVocab(text);
  }).then(function (entries) {
    state.aiBusy = false;
    if (!entries.length) { state.skipped = -1; state.pending = null; }
    else { state.step = "confirm"; state.pending = entries; state.skipped = 0; }
    render();
  }, function (err) {
    state.aiBusy = false; state.aiErr = err.message; render();
  });
}
```

- [ ] **Step 4: Route PDFs in the change handler**

Replace the `wf` branch (lines 1014-1019) with:

```js
  if (e.target.id === "wf") {
    var f = e.target.files[0];
    if (!f) return;
    state.targetLang = document.getElementById("wl").value;
    if (/\.pdf$/i.test(f.name) || f.type === "application/pdf") { runAiParse(function () { return extractPdfText(f); }); return; }
    f.text().then(doParse);
  }
```

- [ ] **Step 5: Input-step UI — accept `.pdf`, busy spinner, error message**

Line 726: change `accept=".csv,.tsv,.txt,.md"` to `accept=".csv,.tsv,.txt,.md,.pdf"`.

After the `state.skipped === -1` line (line 728), add:

```js
    if (state.aiBusy) h += '<div class="msg ok"><span class="spinner"></span>' + esc(t("aiParsing")) + "</div>";
    if (state.aiErr) h += '<div class="msg err">' + esc(state.aiErr) + "</div>";
    if (state.aiErr && !genReady()) h += settingsHtml();
```

Also, in the `gen-save` click branch (line 988, `state.genDraft = null; ...`), append `state.aiErr = null;` so saving a provider from this inline form clears the "need provider" error. (`gen-save` is already step-guarded — it only auto-starts generation when `state.step === "loop"`, so embedding `settingsHtml()` in the input step is safe.)

- [ ] **Step 6: i18n strings (all four locales)**

In each locale block, update `upload` and add four keys after it:

zh (~146):
```js
    upload: "上传文件（csv / tsv / txt / md / pdf）",
    aiParsing: "AI 正在解析词表…（本地小模型可能要 1-2 分钟）",
    aiNeedProvider: "PDF / AI 解析需要先接入模型服务（本机 Ollama 免 Key）。",
    errPdfLoad: "PDF 解析库加载失败——首次使用需要联网。",
    errPdfScan: "没有找到可提取的文本（扫描版 PDF 暂不支持）。",
```

en (~198):
```js
    upload: "Upload a file (csv / tsv / txt / md / pdf)",
    aiParsing: "AI is parsing the list… (small local models may take 1-2 min)",
    aiNeedProvider: "PDF / AI parsing needs a model provider first (local Ollama works — no key).",
    errPdfLoad: "Could not load the PDF library — first use needs a network connection.",
    errPdfScan: "No extractable text found (scanned PDFs not supported yet).",
```

es (~250):
```js
    upload: "Subir archivo (csv / tsv / txt / md / pdf)",
    aiParsing: "La IA está analizando la lista… (los modelos locales pequeños pueden tardar 1-2 min)",
    aiNeedProvider: "El análisis con IA / PDF necesita primero un proveedor de modelo (Ollama local funciona, sin clave).",
    errPdfLoad: "No se pudo cargar la librería PDF — el primer uso necesita conexión.",
    errPdfScan: "No se encontró texto extraíble (los PDF escaneados aún no se admiten).",
```

ja (~302):
```js
    upload: "ファイルをアップロード（csv / tsv / txt / md / pdf）",
    aiParsing: "AI が語彙リストを解析中…（ローカル小型モデルは 1〜2 分かかることがあります）",
    aiNeedProvider: "PDF / AI 解析にはモデルサービスの接続が必要です（ローカル Ollama は Key 不要）。",
    errPdfLoad: "PDF ライブラリを読み込めません——初回はネット接続が必要です。",
    errPdfScan: "抽出できるテキストがありません（スキャン PDF は未対応）。",
```

- [ ] **Step 7: Verify — real PDF end-to-end**

1. Hard-reload `http://localhost:8901/index.html`; console clean.
2. With a provider configured (local Ollama or any), open the add-vocab widget → Upload → pick `~/Downloads/Vocabulario_A1_1_Tabla.pdf`.
3. Expect: spinner message (`aiParsing`) → confirm table with ~150 rows like `Hola → Hello`; **no** rows for "Español", "Inglés", "Escribe aquí", "150 Sustantivos A1".
4. Clear the provider config (⚙ → Clear), upload the PDF again → expect the `aiNeedProvider` error plus the provider settings form, no crash.
5. DevTools → Network tab: confirm `pdf.min.mjs` is only fetched on first PDF use, not on page load.

- [ ] **Step 8: Commit**

```bash
git add docs/index.html
git commit -m "PDF upload: lazy pdf.js extraction + LLM normalization into confirm table"
```

---

### Task 3: "Parse with AI" fallback for messy plain text

**Files:**
- Modify: `docs/index.html:849-854` (`doParse`: remember raw text)
- Modify: `docs/index.html:728` area (input step: fallback button when nothing parsed)
- Modify: `docs/index.html:730-741` (confirm step: fallback button when lines skipped)
- Modify: `docs/index.html:894-905` (click handler: new `ai-parse` action)
- Modify: i18n blocks: 1 new string

**Interfaces:**
- Consumes: `runAiParse(getText)`, `state.lastRaw` (Task 2), `genReady()`.
- Produces: click action `data-act="ai-parse"`; i18n key `aiParseBtn`.

- [ ] **Step 1: Remember raw text in `doParse`**

At the top of `doParse` (line 849), add one line:

```js
function doParse(text) {
  state.lastRaw = text;
  var r = parseVocab(text);
```

- [ ] **Step 2: Fallback button in the input step (0 entries parsed)**

Change the `state.skipped === -1` line (line 728) to:

```js
    if (state.skipped === -1) {
      h += '<p class="muted">' + esc(t("nothing")) + "</p>";
      if (genReady() && state.lastRaw) h += '<div class="row"><button class="btn" data-act="ai-parse">' + esc(t("aiParseBtn")) + "</button></div>";
    }
```

- [ ] **Step 3: Fallback button in the confirm step (some lines skipped)**

Change the `state.skipped > 0` line (line 732) to:

```js
    if (state.skipped > 0) {
      h += '<p class="muted">⚠ ' + esc(fmt(t("skipped"), { n: state.skipped })) + "</p>";
      if (genReady() && state.lastRaw) h += '<div class="row" style="margin-bottom:0.6rem"><button class="btn" data-act="ai-parse">' + esc(t("aiParseBtn")) + "</button></div>";
    }
```

- [ ] **Step 4: Click handler**

After the `act === "parse"` branch (line 903), add:

```js
  else if (act === "ai-parse") { runAiParse(function () { return state.lastRaw; }); }
```

- [ ] **Step 5: i18n — add `aiParseBtn` to all four locales** (next to `parse`)

```js
    aiParseBtn: "✨ 用 AI 解析",          // zh
    aiParseBtn: "✨ Parse with AI",       // en
    aiParseBtn: "✨ Analizar con IA",     // es
    aiParseBtn: "✨ AI で解析",           // ja
```

- [ ] **Step 6: Verify**

1. Hard-reload; console clean.
2. Paste garbage that regex can't fully handle, e.g.:
   ```
   VOCABULARIO UNIDAD 1
   la casa house
   el perro dog (animal)
   sin separador
   ```
   → Parse & review. Expect confirm table plus "⚠ n lines skipped" and the ✨ AI button.
3. Click the AI button → spinner → confirm table now from the LLM (header line dropped, `sin separador` either dropped or sensibly handled).
4. Paste pure prose (no separators at all) → Parse & review → "nothing parsed" message + AI button appears (provider configured). Without provider config, no AI button.

- [ ] **Step 7: Commit**

```bash
git add docs/index.html
git commit -m "Add Parse-with-AI fallback for messy pasted text"
```

---

### Task 4: Export the normalized word list (copy / TSV)

**Files:**
- Modify: `docs/index.html:443` area (helpers next to vocab code)
- Modify: `docs/index.html:739-740` (confirm-step button row)
- Modify: `docs/index.html:750-752` (loop-step header area)
- Modify: `docs/index.html:894+` (click handler: `export-copy`, `export-tsv`)
- Modify: `docs/index.html:372-384` (state: `expMsg`)
- Modify: i18n blocks: 3 new strings

**Interfaces:**
- Consumes: `state.pending` (confirm step), `proj().vocab` (loop step), `t(k)`.
- Produces: `vocabLines(list)`, `vocabTsv(list)`, `downloadTsv(name, list)`; actions `data-act="export-copy"` / `data-act="export-tsv"`; state `state.expMsg`.

- [ ] **Step 1: Helpers**

Insert after `normalizeVocabList` etc. (the Task 1 block):

```js
function vocabLines(list) { return list.map(function (v) { return v.w + " → " + v.gloss; }).join("\n"); }
function vocabTsv(list) { return list.map(function (v) { return v.w + "\t" + v.gloss; }).join("\n"); }
function downloadTsv(name, list) {
  var blob = new Blob([vocabTsv(list)], { type: "text/tab-separated-values" });
  var a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(function () { URL.revokeObjectURL(a.href); }, 1000);
}
```

- [ ] **Step 2: State field**

In the `state` literal, extend the Task 2 line:

```js
  pending: null, skipped: 0, aiBusy: false, aiErr: null, lastRaw: "", expMsg: null,
```

- [ ] **Step 3: Confirm-step buttons**

Change the confirm-step button row (lines 739-740) to:

```js
    h += '<div class="row"><button class="btn btn-primary" data-act="confirm">' + esc(t("confirm")) + "</button>" +
      '<button class="btn" data-act="cancel">' + esc(t("cancel")) + "</button>" +
      '<button class="btn" data-act="export-copy">' + esc(t("exportCopy")) + "</button>" +
      '<button class="btn" data-act="export-tsv">' + esc(t("exportTsv")) + "</button></div>";
    if (state.expMsg) h += '<div class="msg ok">' + esc(state.expMsg) + "</div>";
```

- [ ] **Step 4: Loop-step buttons (existing project)**

After the coverage bar (line 752, `h += '<div class="cov-bar">...'`), add:

```js
    h += '<div class="row" style="margin-top:0.5rem"><button class="btn" data-act="export-copy">' + esc(t("exportCopy")) + "</button>" +
      '<button class="btn" data-act="export-tsv">' + esc(t("exportTsv")) + "</button></div>";
    if (state.expMsg) h += '<div class="msg ok">' + esc(state.expMsg) + "</div>";
```

- [ ] **Step 5: Click handlers**

Add after the `ai-parse` branch:

```js
  else if (act === "export-copy" || act === "export-tsv") {
    var list = state.step === "confirm" ? state.pending : (p ? p.vocab : null);
    if (!list || !list.length) return;
    if (act === "export-tsv") {
      downloadTsv(((p && p.config.name) || "fabulita") + "-vocab.tsv", list);
      return;
    }
    (navigator.clipboard ? navigator.clipboard.writeText(vocabLines(list)) : Promise.reject()).then(function () {
      state.expMsg = t("exportCopied"); render();
    }, function () {
      state.expMsg = null;
      state.msg = { cls: "ok", html: "<textarea readonly style='min-height:10rem'>" + esc(vocabLines(list)) + "</textarea>" };
      render();
    });
  }
```

Also clear `state.expMsg` when leaving these screens — in the `cancel` branch (line 905) and the `confirm` branch (both project-create and append paths), add `state.expMsg = null;`.

- [ ] **Step 6: i18n — 3 new strings per locale**

```js
    exportCopy: "📋 复制词表", exportTsv: "⬇ 下载 TSV", exportCopied: "已复制。",                 // zh
    exportCopy: "📋 Copy list", exportTsv: "⬇ Download TSV", exportCopied: "Copied.",            // en
    exportCopy: "📋 Copiar lista", exportTsv: "⬇ Descargar TSV", exportCopied: "Copiado.",       // es
    exportCopy: "📋 リストをコピー", exportTsv: "⬇ TSV をダウンロード", exportCopied: "コピーしました。", // ja
```

- [ ] **Step 7: Verify**

1. Hard-reload; console clean.
2. Parse any list → confirm table → 📋 Copy → paste into the textarea of another app/tab: expect `hola → hello` lines. ⬇ TSV → file downloads, open it: tab-separated pairs.
3. Open an existing project card → loop view shows both export buttons above the batch chips; both work on the full project vocab.

- [ ] **Step 8: Commit**

```bash
git add docs/index.html
git commit -m "Export normalized vocab: copy word→gloss lines / download TSV"
```

---

### Task 5: Full QA sweep + plan close-out

**Files:**
- Modify: `docs/index.html` (only if QA finds bugs)

**Interfaces:** none new.

- [ ] **Step 1: Locale sweep**

For each of 中文 / English / Español / 日本語 (top-right switcher): open the add-vocab widget and confirm the new strings render (upload label mentions pdf; trigger the no-provider PDF error once to see `aiNeedProvider`).

- [ ] **Step 2: End-to-end with the real PDF**

Fresh state (DevTools → Application → Local Storage → remove `fabulita.studio.projects` if you want a clean slate, optional): configure local Ollama provider → upload `Vocabulario_A1_1_Tabla.pdf` → review ~150 rows → drop a row with ✕ → export TSV → confirm → story generation starts. Accept one story.

- [ ] **Step 3: Offline regression**

DevTools → Network → Offline: paste a clean two-line list → Parse & review → confirm table appears (regex path untouched, no network). Upload a PDF while offline → expect `errPdfLoad` message, no crash. Set back to Online.

- [ ] **Step 4: Fix anything found, commit**

```bash
git add docs/index.html
git commit -m "QA fixes: PDF upload + AI parse round 1"
```

(Skip the commit if nothing was found.)
