# fabulita

**Vocabulary list in → LLM-generated graded-reader stories → a single interactive HTML file out.**

fabulita compiles a vocabulary list into a self-contained reading page for language learners:

- 📖 **Micro-stories from your vocab** — each story uses ≤20 words from your list; keep generating until the whole list is covered (coverage bar included)
- 👆 **Tap any word** for its gloss and grammar note (inflected forms glossed back to the infinitive)
- 🔊 **Per-sentence neural TTS**, pre-generated and embedded as data URIs — the page works **offline, with zero infrastructure**: no server, no account, no app
- 🐢 Slow playback for shadowing (pitch preserved)
- 🌐 UI in **中文 / English / Español / 日本語**, light & dark theme
- 🤖 **Bring your own LLM** — fabulita never calls a model API; it writes the prompt, you paste it into Claude/ChatGPT/a local model and save the JSON reply

No database, no framework. A "project" is a folder of JSON files you can keep in git.

## Quickstart

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

Try the bundled demo:

```sh
fabulita -C examples/es-a1 import examples/es-a1/vocab.csv
fabulita -C examples/es-a1 tts        # optional, needs network
fabulita -C examples/es-a1 build
open examples/es-a1/dist/index.html
```

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

## Non-goals

- Not an SRS / flashcard app (export to Anki instead; FSRS integration is on the roadmap)
- Not a reader for arbitrary imported texts — that's [LUTE](https://github.com/LuteOrg/lute-v3)'s job. fabulita generates content *for your vocabulary*, not the other way around.
- No model API calls, ever. Your prompt, your model, your data.

## 中文速览

fabulita 把「生词表」编译成「分级阅读故事书」：导入词表 → `fabulita next` 产出给 LLM 的写作 prompt（每篇 ≤20 个未覆盖词）→ 把 LLM 返回的 JSON `add` 进备选池 → 读过满意后 `accept` → `tts` 预生成逐句朗读 → `build` 出一个可离线使用的单 HTML 文件：点词查义、逐句神经语音朗读、慢速跟读、覆盖率进度条。界面支持中/英/西/日。

## License

MIT
