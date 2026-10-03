"""Homework images delivered as separate files (public CC0 assets) instead of base64."""

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from fabulita import build
from fabulita.project import Project


REPO = Path(__file__).parent.parent
PIXEL_JPEG = bytes.fromhex(
    "ffd8ffe000104a46494600010100000100010000ffdb004300080606070605080707070909080a0c140d0c0b0b0c1912130f14"
    "1d1a1f1e1d1a1c1c20242e2720222c231c1c2837292c30313434341f27393d38323c2e333432ffc0000b080001000101011100"
    "ffc40014000100000000000000000000000000000009ffc40014100100000000000000000000000000000000ffda0008010100"
    "003f00d2cf20ffd9"
)


def _project(tmp_path, deliver):
    root = tmp_path / "proj"
    root.mkdir()
    (root / "fabulita.json").write_text(json.dumps({
        "name": "T", "lang": "es", "gloss_lang": "zh", "ui_default": "zh", "layout": "vocab"
    }), encoding="utf-8")
    (root / "vocab.csv").write_text("word,gloss\nla tortuga,乌龟\n", encoding="utf-8")
    image_dir = root / "assets" / "vocab-images" / "images"
    image_dir.mkdir(parents=True)
    (image_dir / "001-turtle.jpg").write_bytes(PIXEL_JPEG)
    image = {"file": "assets/vocab-images/images/001-turtle.jpg",
             "sha256": hashlib.sha256(PIXEL_JPEG).hexdigest()}
    if deliver:
        image["deliver"] = deliver
    (root / "homework.json").write_text(json.dumps({"version": 1, "assignments": [{
        "id": "img", "title": "img", "source": {}, "images": {"vocab-001": image},
        "sections": [{"id": "s", "title": "s", "type": "single_choice", "items": [{
            "id": "q1", "prompt": "?", "imageId": "vocab-001", "options": ["a", "b"], "answers": ["a"]
        }]}]
    }]}), encoding="utf-8")
    return Project(root)


def test_file_delivery_copies_asset_and_references_relative_src(tmp_path):
    project = _project(tmp_path, "file")
    asset_dir = tmp_path / "docs" / "assets" / "proj" / "vocab"
    data = build.payload(project, include_candidates=False, asset_dir=asset_dir, asset_url="assets/proj/vocab")
    image = data["homeworks"][0]["images"]["vocab-001"]
    assert image["src"] == "assets/proj/vocab/001-turtle.jpg"
    assert "dataUrl" not in image and "file" not in image
    assert image["sha256"] == hashlib.sha256(PIXEL_JPEG).hexdigest()
    assert (asset_dir / "001-turtle.jpg").read_bytes() == PIXEL_JPEG


def test_file_delivery_falls_back_to_embedding_without_asset_dir(tmp_path):
    project = _project(tmp_path, "file")
    data = build.payload(project, include_candidates=False)
    image = data["homeworks"][0]["images"]["vocab-001"]
    assert image["dataUrl"].startswith("data:image/jpeg;base64,")
    assert "src" not in image


def test_embedded_images_ignore_asset_dir(tmp_path):
    project = _project(tmp_path, None)
    asset_dir = tmp_path / "docs" / "assets" / "proj" / "vocab"
    data = build.payload(project, include_candidates=False, asset_dir=asset_dir, asset_url="assets/proj/vocab")
    image = data["homeworks"][0]["images"]["vocab-001"]
    assert image["dataUrl"].startswith("data:image/jpeg;base64,")
    assert not asset_dir.exists()


NODE_SRC_TEST = r"""
const fs = require("fs");
const vm = require("vm");
const html = fs.readFileSync(process.argv[1], "utf8");
const scripts = [...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)].map((m) => m[1]);
const P = JSON.parse(scripts[0].match(/^var P = ([\s\S]*);$/)[1]);
let app = scripts[scripts.length - 1];
const close = app.lastIndexOf("})();");
app = app.slice(0, close) + "window.__t = { safeHomeworkImageUrl };" + app.slice(close);
const noop = () => {};
const classList = { add: noop, remove: noop, toggle: noop, contains: () => false };
const document = {
  body: { classList, appendChild: noop }, documentElement: { lang: "" }, activeElement: null, title: "",
  addEventListener: noop,
  getElementById(id) { return id === "app" ? { className: "", innerHTML: "" } :
    (id === "pop" ? { classList, style: { setProperty: noop }, offsetWidth: 0, offsetHeight: 0 } : null); },
  querySelector() { return null; }, querySelectorAll() { return []; },
  createElement() { return { style: {}, click: noop, remove: noop }; }
};
const storage = new Map();
const context = {
  P, console, document, location: { hash: "", reload: noop }, navigator: {}, setTimeout, clearTimeout,
  Intl, Date, Math, JSON, Blob: class {}, URL: { createObjectURL: () => "", revokeObjectURL: noop },
  crypto: { randomUUID: () => "u" }, addEventListener: noop, scrollY: 0, scrollX: 0, innerWidth: 1200,
  innerHeight: 800, speechSynthesis: { cancel: noop, getVoices: () => [], speak: noop },
  SpeechSynthesisUtterance: class {}, Audio: class { pause() {} play() { return Promise.resolve(); } addEventListener() {} },
  localStorage: { getItem: (k) => storage.has(k) ? storage.get(k) : null, setItem: (k, v) => storage.set(k, String(v)), removeItem: (k) => storage.delete(k) }
};
context.window = context;
vm.createContext(context);
vm.runInContext(app, context);
const f = context.__t.safeHomeworkImageUrl;
const ok = f({ images: { a: { src: "assets/proj/vocab/001-turtle.jpg" } } }, "a");
if (ok !== "assets/proj/vocab/001-turtle.jpg") throw new Error("relative asset src should be accepted, got " + JSON.stringify(ok));
for (const bad of ["https://evil.example/x.jpg", "../secret.jpg", "assets/../x.jpg", "javascript:alert(1)", "assets/x.svg", "/assets/x.jpg"]) {
  const got = f({ images: { a: { src: bad } } }, "a");
  if (got !== "") throw new Error("should reject " + bad + ", got " + JSON.stringify(got));
}
const data = f({ images: { a: { dataUrl: "data:image/jpeg;base64,AAAA" } } }, "a");
if (data !== "data:image/jpeg;base64,AAAA") throw new Error("data urls should still work");
console.log("ok");
"""


def test_runtime_accepts_relative_asset_src_only(tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js required")
    project = _project(tmp_path, "file")
    from fabulita import vocab
    vocab.import_file(project, project.root / "vocab.csv")
    page, _, _, _ = build.build(project, out=tmp_path / "p.html", include_candidates=False, home="index.html")
    result = subprocess.run([node, "-e", NODE_SRC_TEST, str(page)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
