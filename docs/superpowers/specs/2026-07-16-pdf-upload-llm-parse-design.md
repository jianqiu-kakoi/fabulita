# PDF upload + LLM smart parse → normalized vocab list

Date: 2026-07-16
Status: approved (design), pending implementation
Scope: `docs/index.html` (landing page add-vocab widget) only.

## Problem

The add-vocab widget accepts csv/tsv/txt/md and parses with regex heuristics
(`parseVocab`). Real-world vocab sources are often PDFs — e.g.
`Vocabulario_A1_1_Tabla.pdf`: a 150-row table `Español | Inglés | Escribe aquí`.
PDFs can't be ingested at all today, and heuristics can't clean table debris
(headers, empty practice columns) even if the text were extracted. The user
also wants the normalized word list (`hola → hello` pairs) to be viewable and
exportable, not locked inside localStorage.

## Design

### 1. PDF ingestion

- Add `.pdf` to the file input's `accept` and detect by extension/MIME.
- On first PDF selection, lazy-load pdf.js from CDN (`pdfjs-dist` + worker).
  This is the only feature that requires network once; everything else stays
  offline. Pin an exact version.
- Extract the text layer of every page (`getTextContent`), join items with
  spaces and pages with newlines. Result is messy text with table residue —
  that's fine, the LLM cleans it.

### 2. LLM normalization ("smart parse" — generic, not PDF-only)

- New parse path: send the messy text to the currently configured provider
  (local Ollama/Qwen, Anthropic, Qwen cloud, custom — reuse the existing
  provider plumbing in `generateOpenAI`/`generateAnthropic`).
- Prompt contract — return ONLY a JSON array, no fence, no commentary:

  ```json
  [{"w": "hola", "gloss": "hello"}]
  ```

  Rules stated in the prompt: drop table headers and non-vocabulary noise
  (e.g. "Escribe aquí", page numbers, titles); one entry per word; join
  multiple meanings with "; "; keep glosses in their source language
  (no translation); deduplicate.
- Trigger policy:
  - PDF upload → always goes through the LLM (heuristics never see it).
  - Plain text/csv/etc. → existing regex `parseVocab` runs first; if it
    skipped ≥ 1 line or produced 0 entries, show a "Parse with AI"
    fallback button (only when a provider is configured).
  - If no provider is configured (`genReady()` false), PDF path shows the
    existing provider-setup nudge instead of failing cryptically.
- LLM output feeds the existing confirm table (reviewable, ✕ to drop rows)
  — never straight into the project. Human review stays the last gate.
- JSON robustness: reuse the existing tolerant extraction approach
  (strip `<think>`, slice first `[` … last `]`, `JSON.parse`), validate each
  item has non-empty `w`/`gloss` strings, dedupe by `norm(w)`.

### 3. Normalized list is accessible

- Confirm-table step gains an Export control: copy to clipboard as
  `word → gloss` lines, and download as `.tsv`.
- The same export control is added to an existing project's vocab view, so
  the standardized list can be taken out at any time.

## Out of scope (explicitly)

- Re-glossing/translating glosses into the project's gloss language
  (separate future feature).
- Scanned/image-only PDFs (no text layer) → detect (empty extraction) and
  show "scanned PDFs not supported yet".
- Studio (`fabulita/studio.html`) and the Python CLI — landing page only.

## Error handling

| Failure | Behavior |
| --- | --- |
| pdf.js CDN load fails (offline) | Message: PDF parsing needs network once to load the library |
| PDF has no text layer | Message: scanned PDFs not supported |
| LLM returns unparseable output | Tolerant JSON slice; if still bad, show existing `errParse` with raw-output hint |
| LLM returns empty list | Same skipped/empty messaging as regex path |
| No provider configured | Existing setup nudge |

## Testing

- Manual: upload `Vocabulario_A1_1_Tabla.pdf` with local Qwen via Ollama →
  expect ~150 clean pairs in the confirm table, headers/empty column dropped.
- Manual: messy pasted text → regex path unchanged; AI fallback appears when
  lines are skipped.
- Manual: export buttons produce `hola → hello` lines / valid TSV.
- Offline check: non-PDF flows untouched with network disabled.

All four UI locales (zh/en/es/ja) get the new strings.
