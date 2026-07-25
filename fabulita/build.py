"""Assemble the single-file page: template + JSON payload + base64 audio."""

import base64
import hashlib
import json
from pathlib import Path

from .tts import clip_path
from .ui import UI_LANGS, UI_STRINGS

TEMPLATE = Path(__file__).parent / "template.html"
STUDIO = Path(__file__).parent / "studio.html"


def _homework_payload(project):
    """Load optional homework data and embed its local PDF source in the single-file page."""
    root = project.root.resolve()
    assignments = []
    for raw in project.homeworks:
        if not isinstance(raw, dict):
            continue
        assignment = dict(raw)
        source = dict(assignment.get("source") or {})
        source_file = source.pop("file", "")
        if source_file:
            source_path = (project.root / source_file).resolve()
            try:
                source_path.relative_to(root)
            except ValueError as exc:
                raise ValueError(f"homework source must stay inside project: {source_file}") from exc
            if not source_path.is_file():
                raise ValueError(f"homework source not found: {source_file}")
            content = source_path.read_bytes()
            digest = hashlib.sha256(content).hexdigest()
            expected = source.get("sha256")
            if expected and expected != digest:
                raise ValueError(f"homework source checksum mismatch: {source_file}")
            source.update({
                "filename": source.get("filename") or source_path.name,
                "sha256": digest,
                "size": len(content),
                "dataUrl": "data:application/pdf;base64," + base64.b64encode(content).decode(),
            })
        assignment["source"] = source
        assignments.append(assignment)
    return assignments


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
            "review_id": cfg.get("review_id") or project.root.name,
            "qa_id": cfg.get("qa_id") or project.root.name,
            "history_id": cfg.get("history_id") or project.root.name,
            "homework_id": cfg.get("homework_id") or project.root.name,
            "layout": cfg.get("layout") or "reader",
        },
        "ui": UI_STRINGS,
        "uiLangs": UI_LANGS,
        "vocab": project.vocab,
        "glossary": project.glossary,
        "stories": stories,
        "audio": audio,
        "homeworks": _homework_payload(project),
    }


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
    """Write demo data JS to a file and return (path, size)."""
    js = demo_data_js(project)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(js, encoding="utf-8")
    return out, len(js)


def demo_manifest_js(projects):
    """Tiny per-language {n, ids} manifest so index.html can show counts cheaply."""
    counts = {}
    for p in projects:
        stories_list = [s for s in p.stories() if s.get("status") == "accepted"]
        counts[p.config["lang"]] = {"n": len(stories_list), "ids": [s["id"] for s in stories_list]}
    blob = json.dumps(counts, ensure_ascii=False).replace("</", "<\\/")
    return "window.FABULITA_DEMO_COUNTS=" + blob + ";\n"


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


def build_reader(out="reader.html"):
    """Emit the self-serve reader: aggregates 'my storybook' from localStorage at runtime."""
    data = {
        "self": True,
        "ui": UI_STRINGS,
        "uiLangs": UI_LANGS,
        "config": {"name": "fabulita", "lang": "", "gloss_lang": "en",
                   "ui_default": "en", "home": "index.html", "review_id": "self",
                   "qa_id": "self", "history_id": "self", "homework_id": "self", "layout": "reader"},
        "vocab": [], "glossary": {}, "stories": [], "audio": {}, "homeworks": [],
    }
    blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    html = TEMPLATE.read_text(encoding="utf-8")
    html = html.replace("__TITLE__", "fabulita")
    html = html.replace("/*__PAYLOAD__*/null", blob, 1)
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
        for field in ("note", "category", "kind", "example", "example_trans", "answers", "review_mode",
                      "display", "english"):
            if v.get(field):
                entry[field] = v[field]
        vocab_list.append(entry)
    proj.save_vocab(vocab_list)
    proj._write("glossary.json", bundle.get("glossary", {}))
    for story in bundle.get("stories", []):
        proj.save_story(story)
    return dest, len(bundle.get("vocab", [])), len(bundle.get("stories", []))
