# Codex CLI bridge: story/vocab generation via `codex exec`

Date: 2026-07-16
Status: approved (design confirmed in conversation)
Scope: new `fabulita/bridge.py` + CLI wiring + provider preset in `docs/index.html`.

## Problem

The landing page generates stories/parses vocab browser-side against an
OpenAI-compatible endpoint. Local Ollama (qwen3:8b) is too slow on this
machine (3-10 min per request, measured 2026-07-16). The user has a Codex
CLI subscription (`codex exec`, codex-cli 0.144.3 verified) and wants story
generation to run through it for now. A browser page cannot spawn a CLI, so
a small local bridge is needed.

## Design

### 1. `fabulita bridge` subcommand (`fabulita/bridge.py`, stdlib only)

- `ThreadingHTTPServer` on `--port` (default 8130), loopback only
  (bind 127.0.0.1).
- `POST /v1/chat/completions`: parse `{model, messages}`; prompt = the
  string contents of all messages joined with `\n\n`; run:
  `codex exec --ephemeral --skip-git-repo-check -s read-only --color never
  --output-last-message <tmp>/last.txt -C <tmp> [-m <model>] -`
  with the prompt piped via stdin (`-` = read prompt from stdin), 600 s
  subprocess timeout, cwd-isolated in a TemporaryDirectory. Response:
  `{"id":"bridge","object":"chat.completion","choices":[{"index":0,
  "message":{"role":"assistant","content":<last.txt>},"finish_reason":"stop"}]}`.
- `model` resolution: request `model` field if non-empty, else `--model`
  CLI flag if given, else omit `-m` (codex config default).
- CORS: `Access-Control-Allow-Origin: *`, allow `content-type,
  authorization` headers and `POST, OPTIONS` methods on every response;
  `OPTIONS` → 204 (page origin is localhost:8901, so preflights happen).
- Errors: codex non-zero exit / timeout / bad JSON → 4xx/5xx with
  OpenAI-style body `{"error":{"message":...}}` (the page's `httpError`
  reads `error.message`). Unknown path → 404.
- `request_format`/`response_format` fields in the request are ignored —
  the page's prompts already demand raw JSON and parse tolerantly.
- Quiet request logging (one line per request: path, status, duration).

### 2. Page: "Codex CLI" provider preset (`docs/index.html`)

- `PROV.codex = { base: "http://localhost:8130/v1", model: "", needKey: false }`.
- Dropdown option after Ollama; `provCodex` i18n key in all four locales
  (zh: "Codex CLI（本地桥 · fabulita bridge）", en/es/ja equivalents).
- `genReady()`: `codex` is ready unconditionally (like ollama).
- `settingsHtml()`: no API-key field for codex (like ollama); base shown as
  muted preset text.
- `provLabel()` names map gains `codex`.
- Everything downstream (stories, PDF/AI vocab parse) works unchanged —
  same OpenAI-compatible pipeline, 600 s timeouts already in place.

## Out of scope

- Streaming, multi-turn sessions, `--output-schema` structured output.
- Generic "any CLI as provider" bridge (build when a second CLI shows up).
- Auth on the bridge (loopback only).

## Error handling

| Failure | Behavior |
| --- | --- |
| codex binary missing | 500 `{"error":{"message":"codex CLI not found..."}}` |
| codex non-zero exit | 500 with stderr tail in error.message |
| codex hangs | 600 s subprocess timeout → 504-style 500 error |
| bad request JSON / no messages | 400 with error.message |
| CORS preflight | 204 with CORS headers |

## Testing

- pytest (TDD): `build_cmd()` model inclusion/omission; end-to-end handler
  tests against a fake `codex` executable on PATH (writes canned output to
  the `--output-last-message` path; variants: success, non-zero exit);
  CORS headers on OPTIONS and POST.
- Browser QA is executed by a subagent controlling Chrome (user directive
  2026-07-16): real `codex exec` end-to-end — configure Codex CLI provider,
  generate one story on the existing project; verify PDF-upload entry
  discoverability; restore UI state (uiLang) after testing.
