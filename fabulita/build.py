"""Assemble the single-file page: template + JSON payload + base64 audio."""

import base64
import json
from pathlib import Path

from .tts import clip_path
from .ui import UI_LANGS, UI_STRINGS

TEMPLATE = Path(__file__).parent / "template.html"
STUDIO = Path(__file__).parent / "studio.html"


def payload(project, include_candidates=True, home=None):
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
            "home": home or cfg.get("home") or "",
        },
        "ui": UI_STRINGS,
        "uiLangs": UI_LANGS,
        "vocab": project.vocab,
        "glossary": project.glossary,
        "stories": stories,
        "audio": audio,
    }


def build(project, out=None, include_candidates=True, home=None):
    data = payload(project, include_candidates=include_candidates, home=home)
    blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    html = TEMPLATE.read_text(encoding="utf-8")
    html = html.replace("__TITLE__", data["config"]["name"])
    html = html.replace("/*__PAYLOAD__*/null", blob, 1)
    out = Path(out) if out else project.root / "dist" / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return out, len(html), len(data["stories"]), sum(len(v) for v in data["audio"].values())


def build_studio(out="studio.html"):
    """Emit the Studio web app with the reader template embedded (for client-side export)."""
    tpl_b64 = base64.b64encode(TEMPLATE.read_bytes()).decode()
    ui = json.dumps({"ui": UI_STRINGS, "uiLangs": UI_LANGS}, ensure_ascii=False).replace("</", "<\\/")
    html = STUDIO.read_text(encoding="utf-8")
    html = html.replace('/*__READER_TPL_B64__*/""', json.dumps(tpl_b64), 1)
    html = html.replace("/*__READER_UI__*/null", ui, 1)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return out, len(html)


def unpack(bundle_path, dest="."):
    """Explode a Studio bundle.json into a CLI project directory."""
    from .project import CONFIG_FILE, Project

    with open(bundle_path, encoding="utf-8") as f:
        bundle = json.load(f)
    if not bundle.get("fabulita_bundle") or "config" not in bundle:
        raise ValueError(f"{bundle_path} is not a fabulita bundle")
    dest = Path(dest)
    if (dest / CONFIG_FILE).exists():
        raise ValueError(f"{dest} already contains a fabulita project")
    proj = Project(dest)
    cfg = dict(bundle["config"])
    cfg.setdefault("ui_default", "en")
    proj._write(CONFIG_FILE, {"name": "Fabulita", **cfg})
    vocab_list = []
    for v in bundle.get("vocab", []):
        if not isinstance(v, dict) or not (v.get("w") or v.get("word")):
            raise ValueError(f"bad vocab entry (need 'w' and 'gloss' keys): {v!r}")
        entry = {"w": v.get("w") or v["word"], "gloss": v.get("gloss", "")}
        if v.get("note"):
            entry["note"] = v["note"]
        vocab_list.append(entry)
    proj.save_vocab(vocab_list)
    proj._write("glossary.json", bundle.get("glossary", {}))
    for story in bundle.get("stories", []):
        proj.save_story(story)
    return dest, len(bundle.get("vocab", [])), len(bundle.get("stories", []))
