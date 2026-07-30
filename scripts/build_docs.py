#!/usr/bin/env python
"""Rebuild every generated file under docs/ from examples/ and fabulita/.

Usage: uv run python scripts/build_docs.py
       uv run python scripts/build_docs.py --local
"""
import argparse
from pathlib import Path

from fabulita import build, vocab
from fabulita.project import Project

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
DEMOS = {"es": "es-a1", "en": "en-a1", "ja": "ja-n5"}
VOCAB_APPS = {
    "mi-espanol": "mi-espanol.html",
    "my-english": "my-english.html",
}


def main(local=False):
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

    for project_name, output_name in VOCAB_APPS.items():
        project_root = ROOT / "examples" / project_name
        if not (project_root / "fabulita.json").exists():
            print("skipping optional app " + project_name + " (source not present)")
            continue
        vocab_project = Project(project_root)
        # Rich learning dashboards treat vocab.csv as the source of truth.
        # Rebuild the ignored cache from scratch so removed rows cannot linger.
        vocab_project.save_vocab([])
        vocab.import_file(vocab_project, vocab_project.root / "vocab.csv")
        page, psize, n, clips = build.build(
            vocab_project,
            out=DOCS / output_name,
            include_candidates=False,
            home="index.html",
        )
        print("wrote " + str(page) + " (" + str(psize // 1024) + " KB, " + str(n) + " stories)")

        local_source = project_root / "homework.local.json"
        if local and local_source.exists():
            local_name = output_name.replace(".html", ".local.html")
            page, psize, n, clips = build.build(
                vocab_project,
                out=DOCS / local_name,
                include_candidates=False,
                home="index.html",
                include_local_homework=True,
            )
            print("wrote " + str(page) + " (local, " + str(psize // 1024) + " KB)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--local", action="store_true",
                        help="additionally build docs/*.local.html with homework.local.json appended")
    main(local=parser.parse_args().local)
