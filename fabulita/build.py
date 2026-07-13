"""Assemble the single-file page: template + JSON payload + base64 audio."""

import base64
import json
from pathlib import Path

from .tts import clip_path
from .ui import UI_LANGS, UI_STRINGS

TEMPLATE = Path(__file__).parent / "template.html"


def payload(project, include_candidates=True):
    cfg = project.config
    stories = [
        s for s in project.stories()
        if s.get("status") == "accepted" or (include_candidates and s.get("status") == "candidate")
    ]
    audio = {}
    for s in stories:
        clips = {}
        for i in range(len(s["sentences"])):
            p = clip_path(project, s["id"], i)
            if p.exists():
                clips[str(i)] = "data:audio/mpeg;base64," + base64.b64encode(p.read_bytes()).decode()
        if clips:
            audio[s["id"]] = clips
    return {
        "config": {
            "name": cfg["name"],
            "lang": cfg["lang"],
            "gloss_lang": cfg["gloss_lang"],
            "ui_default": cfg["ui_default"],
        },
        "ui": UI_STRINGS,
        "uiLangs": UI_LANGS,
        "vocab": project.vocab,
        "glossary": project.glossary,
        "stories": stories,
        "audio": audio,
    }


def build(project, out=None, include_candidates=True):
    data = payload(project, include_candidates=include_candidates)
    blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    html = TEMPLATE.read_text(encoding="utf-8")
    html = html.replace("__TITLE__", data["config"]["name"])
    html = html.replace("/*__PAYLOAD__*/null", blob, 1)
    out = Path(out) if out else project.root / "dist" / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return out, len(html), len(data["stories"]), sum(len(v) for v in data["audio"].values())
