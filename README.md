# fabulita

**Vocabulary list in → LLM-generated graded-reader stories → a single interactive HTML file out.**

fabulita compiles a vocabulary list into a self-contained reading page for language learners:

- 📖 **Micro-stories from your vocab** — each story uses ≤20 words from your list; keep generating until the whole list is covered (coverage bar included)
- 👆 **Tap any word** for its gloss and grammar note (inflected forms glossed back to the infinitive)
- 🔊 **Per-sentence neural TTS**, pre-generated and embedded as data URIs — the page works **offline, with zero infrastructure**: no server, no account, no app
- 🐢 Slow playback for shadowing (pitch preserved)
- 🧠 **Built-in recall review** — imported vocabulary becomes local flashcards with a lightweight 1 / 3 / 7 / 14 / 30-day schedule; accepted stories add example context when available
- 📝 **Optional interactive homework** — turn a worksheet into structured choice/text questions with local progress, checking, retry, and the original PDF kept as source material
- 🌐 UI in **中文 / English / Español / 日本語**, light & dark theme
- 🤖 **Bring your own LLM** — the core static generator does not call a model API; it writes the prompt, you paste it into Claude/ChatGPT/a local model and save the JSON reply

No database, no framework. A "project" is a folder of JSON files (plus optional source materials such as a PDF) you can keep in git.

**Two ways to use it:**

- **Studio (web, no install)** — upload/paste a vocab list, copy the story prompt into your LLM, paste its JSON back, preview, accept, then read and review it. Everything stays in your browser (localStorage) — no backend, no account. Try it: `docs/studio.html`, or `fabulita studio -o studio.html` to generate your own copy.
- **CLI (below)** — same JSON format, plus git-friendly project folders and neural TTS. A Studio project exports as `bundle.json`; `fabulita unpack bundle.json` turns it into a CLI project.

`deploy/my-english-cloudbase/` is an optional hosted reference app. It adds
authenticated cloud progress and server-side LLM answer scoring without changing
the offline-first core. It ships unconfigured: deployment credentials, environment
IDs, model keys, privacy details, and production security settings stay outside git.

## Quickstart (CLI)

```sh
pip install 'fabulita[tts]'      # [tts] pulls in edge-tts for audio

mkdir spanish && cd spanish
fabulita init --lang es --gloss-lang zh --name "Español A1"
fabulita import vocab.csv        # rows: word,gloss[,note]

fabulita next                    # prints a prompt for your LLM
# paste it into your LLM, save the JSON reply as story.json
fabulita add story.json          # validated, enters the candidate pool
fabulita accept <story-id>       # promote after you've read it

fabulita tts                     # synthesize per-sentence audio (cached)
fabulita build                   # -> dist/index.html  (open it, done)
```

Try the bundled demos (Spanish, English, Japanese):

```sh
fabulita -C examples/es-a1 import examples/es-a1/vocab.csv
fabulita -C examples/es-a1 tts        # optional, needs network
fabulita -C examples/es-a1 build
open examples/es-a1/dist/index.html   # also: examples/en-a1, examples/ja-n5
```

Japanese (and Chinese) target text has no word spacing — the reader segments it
by greedy longest-match against the glossary, which is plenty for N5/A1-length
sentences. `examples/ja-n5` shows the pattern, including readings in the vocab
`note` column (`学生,学生,がくせい`).

## The loop

```
vocab.csv ──import──▶ vocab.json
                         │
        fabulita next ───┴──▶ LLM prompt (≤20 uncovered words)
                                   │  (your LLM writes a story JSON)
        fabulita add ◀─────────────┘
             │ candidate pool ──accept──▶ accepted
             ▼
        fabulita status   ▸ coverage: 54/64 (84%) — uncovered: perro, gato, …
             │
        fabulita tts      ▸ audio/<story>/<n>.mp3   (edge | none, pluggable)
             ▼
        fabulita build    ▸ dist/index.html — stories, glosses, audio, coverage
```

Repeat `next → add → accept` until coverage hits 100%.

## Story format

`fabulita next` embeds this schema in the prompt; any LLM that can emit JSON works.

```jsonc
{
  "id": "en-el-mercado",
  "title": "En el mercado",
  "title_note": "在市场",
  "sentences": [
    { "text": "Carlos va al mercado.", "trans": "卡洛斯去市场。" }
  ],
  "vocab_used": ["mercado"],            // dictionary forms from your list
  "glossary": { "va": ["他/她去", "← ir（去）"] },
  "grammar": [["al", "= a + el 的缩合形式。"]]
}
```

Glosses live in three layers, later wins: `vocab.json` → project `glossary.json`
(function words, shared across stories) → per-story `glossary`.

## TTS backends

| backend | quality | cost | notes |
|---|---|---|---|
| `edge` (default) | neural, near-human | free | Microsoft Edge voices via [edge-tts](https://github.com/rany2/edge-tts); unofficial endpoint, network needed at build time only |
| `none` | — | — | page falls back to the browser's `speechSynthesis` |

Backends are pluggable (`fabulita/tts.py`); a [Piper](https://github.com/rhasspy/piper) backend (fully local/offline) is on the roadmap.

## Development

Regenerate everything under `docs/` (demo pages, demo data, reader, studio):

    uv run python scripts/build_docs.py

## Non-goals

- Not a full Anki replacement: review is intentionally lightweight and local-only; FSRS, sync, and advanced card types remain outside this V0
- Not a reader for arbitrary imported texts — that's [LUTE](https://github.com/LuteOrg/lute-v3)'s job. fabulita generates content *for your vocabulary*, not the other way around.
- The core/static build does not call model APIs. Optional hosted integrations under `deploy/` have their own explicit server-side configuration and privacy boundary.

## 中文速览

fabulita 把「生词表」编译成「分级阅读故事书」：导入词表 → `fabulita next` 产出给 LLM 的写作 prompt（每篇 ≤20 个未覆盖词）→ 把 LLM 返回的 JSON `add` 进备选池 → 读过满意后 `accept` → `tts` 预生成逐句朗读 → `build` 出一个可离线使用的单 HTML 文件：点词查义、逐句神经语音朗读、慢速跟读、覆盖率进度条、保存在本机的轻量复习卡，以及可选的交互作业。界面支持中/英/西/日。

## License

[Apache-2.0](LICENSE) · © 2026 Jianqiu Ye

Third-party learning material and adaptations have their own terms and
attribution. See [CONTENT_LICENSE.md](CONTENT_LICENSE.md) and [NOTICE](NOTICE).
