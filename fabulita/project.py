"""Project layout: a fabulita project is a directory of plain JSON files.

    fabulita.json    config (language, gloss language, UI default, TTS)
    vocab.json       master vocabulary list driving coverage
    glossary.json    shared glossary (function words etc.), merged into every story
    stories/*.json   one story per file, status: candidate | accepted
    audio/<id>/<n>.mp3   TTS cache, keyed by story id + sentence index
    dist/index.html  build output
"""

import json
import re
import unicodedata
from pathlib import Path

CONFIG_FILE = "fabulita.json"
VOCAB_FILE = "vocab.json"
GLOSSARY_FILE = "glossary.json"
STORIES_DIR = "stories"
AUDIO_DIR = "audio"

DEFAULT_CONFIG = {
    "name": "Fabulita",
    "lang": "es",
    "gloss_lang": "zh",
    "ui_default": "en",
    "tts": {"backend": "edge", "voice": ""},
    "max_words_per_story": 20,
}

DEFAULT_VOICES = {
    "es": "es-ES-ElviraNeural",
    "en": "en-US-JennyNeural",
    "ja": "ja-JP-NanamiNeural",
    "zh": "zh-CN-XiaoxiaoNeural",
    "fr": "fr-FR-DeniseNeural",
    "de": "de-DE-KatjaNeural",
    "it": "it-IT-ElsaNeural",
    "pt": "pt-BR-FranciscaNeural",
    "ko": "ko-KR-SunHiNeural",
}

WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)


class ProjectError(Exception):
    pass


def norm(word):
    """Case-fold for matching; keeps accents (hablo != habló)."""
    return unicodedata.normalize("NFC", word).lower()


class Project:
    def __init__(self, root="."):
        self.root = Path(root)

    # ---------- io ----------

    def _read(self, name, default):
        p = self.root / name
        if not p.exists():
            return default
        with open(p, encoding="utf-8") as f:
            return json.load(f)

    def _write(self, name, data):
        p = self.root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")

    @property
    def exists(self):
        return (self.root / CONFIG_FILE).exists()

    def require(self):
        if not self.exists:
            raise ProjectError(
                f"no {CONFIG_FILE} in {self.root.resolve()} — run `fabulita init` first"
            )

    # ---------- config / vocab / glossary ----------

    @property
    def config(self):
        cfg = dict(DEFAULT_CONFIG)
        cfg.update(self._read(CONFIG_FILE, {}))
        return cfg

    def init(self, **overrides):
        if self.exists:
            raise ProjectError(f"{CONFIG_FILE} already exists here")
        cfg = dict(DEFAULT_CONFIG)
        cfg.update({k: v for k, v in overrides.items() if v is not None})
        if not cfg["tts"]["voice"]:
            cfg["tts"]["voice"] = DEFAULT_VOICES.get(cfg["lang"], "")
        self._write(CONFIG_FILE, cfg)
        self._write(VOCAB_FILE, {"words": []})
        self._write(GLOSSARY_FILE, {})
        (self.root / STORIES_DIR).mkdir(exist_ok=True)
        return cfg

    @property
    def vocab(self):
        return self._read(VOCAB_FILE, {"words": []})["words"]

    def save_vocab(self, words):
        self._write(VOCAB_FILE, {"words": words})

    @property
    def glossary(self):
        return self._read(GLOSSARY_FILE, {})

    # ---------- stories ----------

    def stories(self):
        out = []
        d = self.root / STORIES_DIR
        if d.exists():
            for p in sorted(d.glob("*.json")):
                with open(p, encoding="utf-8") as f:
                    out.append(json.load(f))
        return out

    def story_path(self, story_id):
        return self.root / STORIES_DIR / f"{story_id}.json"

    def save_story(self, story):
        self._write(f"{STORIES_DIR}/{story['id']}.json", story)

    # ---------- coverage ----------

    def coverage(self, include_candidates=False):
        vocab_set = {norm(w["w"]) for w in self.vocab}
        covered = set()
        for s in self.stories():
            if s.get("status") == "accepted" or include_candidates:
                covered |= {norm(w) for w in s.get("vocab_used", [])}
        covered &= vocab_set
        uncovered = [w for w in self.vocab if norm(w["w"]) not in covered]
        return covered, uncovered
