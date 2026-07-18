#!/usr/bin/env python
"""Rebuild every generated file under docs/ from examples/ and fabulita/.

Usage: uv run python scripts/build_docs.py
"""
from pathlib import Path

from fabulita import build
from fabulita.project import Project

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
DEMOS = {"es": "es-a1", "en": "en-a1", "ja": "ja-n5"}


def main():
    projects = []
    for lang, name in DEMOS.items():
        proj = Project(ROOT / "examples" / name)
        proj.require()
        projects.append(proj)
        out, size = build.build_demo_data(proj, DOCS / ("demo-data-" + lang + ".js"))
        print("wrote " + str(out) + " (" + str(size // 1024) + " KB)")
        # include_candidates=True matches the originally-committed docs/demo-*.html
        # (docs/demo-es.html ships its 1 candidate story alongside its 5 accepted
        # ones); flipping this to False would silently drop that story.
        page, psize, n, clips = build.build(
            proj, out=DOCS / ("demo-" + lang + ".html"),
            include_candidates=True, home="index.html")
        print("wrote " + str(page) + " (" + str(n) + " stories, " + str(clips) + " clips)")
    # Policy split, intentional: demo-manifest.js (and demo-data-*.js, via
    # build_demo_data) are accepted-only — they drive the curated "storybook"
    # surface — while the demo-*.html pages above keep include_candidates=True
    # to match the originally shipped demo pages. So the manifest's per-language
    # `n` may be lower than that language's demo-*.html story count (e.g. es:
    # manifest n=5 vs demo-es.html's 6, which includes 1 candidate story).
    (DOCS / "demo-manifest.js").write_text(build.demo_manifest_js(projects), encoding="utf-8")
    print("wrote " + str(DOCS / "demo-manifest.js"))
    build.build_reader(DOCS / "reader.html")
    build.build_studio(DOCS / "studio.html")
    print("wrote reader.html + studio.html")


if __name__ == "__main__":
    main()
