"""Assemble the single-file page: template + JSON payload + base64 audio."""

import base64
import hashlib
import json
from pathlib import Path

from .tts import clip_path
from .ui import UI_LANGS, UI_STRINGS

TEMPLATE = Path(__file__).parent / "template.html"
STUDIO = Path(__file__).parent / "studio.html"


def _homework_image_media_type(path, content):
    suffix = path.suffix.lower()
    if suffix in (".jpg", ".jpeg") and content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if suffix == ".png" and content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if (suffix == ".webp" and len(content) >= 12 and
            content[:4] == b"RIFF" and content[8:12] == b"WEBP"):
        return "image/webp"
    raise ValueError(f"unsupported or invalid homework image: {path.name}")


def _embed_homework_images(project, root, assignment, asset_dir=None, asset_url=""):
    """Resolve homework images: base64-embed by default, or copy ``deliver: "file"``
    images into ``asset_dir`` and reference them by a page-relative ``src``."""
    if "images" not in assignment:
        return
    raw_images = assignment.get("images") or {}
    if not isinstance(raw_images, dict):
        raise ValueError("homework images must be an object keyed by image id")
    images = {}
    for image_id, raw in raw_images.items():
        if not isinstance(image_id, str) or not image_id or not isinstance(raw, dict):
            raise ValueError("homework images need nonempty string ids and object values")
        image = dict(raw)
        image_file = image.pop("file", "")
        if image_file:
            image_path = (project.root / image_file).resolve()
            try:
                image_path.relative_to(root)
            except ValueError as exc:
                raise ValueError(
                    f"homework image must stay inside project: {image_file}"
                ) from exc
            if not image_path.is_file():
                raise ValueError(f"homework image not found: {image_file}")
            content = image_path.read_bytes()
            digest = hashlib.sha256(content).hexdigest()
            expected = image.get("sha256")
            if expected and expected != digest:
                raise ValueError(f"homework image checksum mismatch: {image_file}")
            media_type = _homework_image_media_type(image_path, content)
            deliver = image.pop("deliver", "embed")
            image.update({
                "filename": image.get("filename") or image_path.name,
                "sha256": digest,
                "size": len(content),
                "mediaType": media_type,
            })
            if deliver == "file" and asset_dir is not None:
                asset_dir = Path(asset_dir)
                asset_dir.mkdir(parents=True, exist_ok=True)
                target = asset_dir / image_path.name
                if not target.exists() or target.read_bytes() != content:
                    target.write_bytes(content)
                image["src"] = (asset_url.rstrip("/") + "/" if asset_url else "") + image_path.name
            else:
                image["dataUrl"] = f"data:{media_type};base64," + base64.b64encode(content).decode()
        images[image_id] = image
    assignment["images"] = images


def _homework_payload(project, include_local=False, asset_dir=None, asset_url=""):
    """Load homework data and embed its local PDF/image sources in the page."""
    root = project.root.resolve()
    assignments = []
    raw_assignments = list(project.homeworks) + (
        list(project.local_homeworks) if include_local else []
    )
    for raw in raw_assignments:
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
        _embed_homework_images(project, root, assignment, asset_dir=asset_dir, asset_url=asset_url)
        assignments.append(assignment)
    return assignments


def payload(project, include_candidates=True, home=None, include_local_homework=False,
            asset_dir=None, asset_url=""):
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
        "homeworks": _homework_payload(project, include_local=include_local_homework,
                                       asset_dir=asset_dir, asset_url=asset_url),
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


def build(project, out=None, include_candidates=True, home=None, include_local_homework=False,
          asset_dir=None, asset_url=""):
    data = payload(project, include_candidates=include_candidates, home=home,
                    include_local_homework=include_local_homework,
                    asset_dir=asset_dir, asset_url=asset_url)
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
