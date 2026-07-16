"""fabulita CLI.

Workflow:
    fabulita init --lang es --gloss-lang zh
    fabulita import vocab.csv
    fabulita next            # -> prompt for your LLM; save its JSON reply
    fabulita add story.json  # enters the candidate pool
    fabulita accept <id>
    fabulita tts             # fill the audio cache (edge-tts)
    fabulita build           # -> dist/index.html, single file, offline
"""

import argparse
import sys

from . import __version__, build, prompts, stories, tts, vocab
from .project import Project, ProjectError


def main(argv=None):
    ap = argparse.ArgumentParser(prog="fabulita", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", action="version", version=f"fabulita {__version__}")
    ap.add_argument("-C", "--project", default=".", help="project directory (default: .)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init", help="create a new project here")
    p.add_argument("--name", help="page title")
    p.add_argument("--lang", help="target language code, e.g. es (default: es)")
    p.add_argument("--gloss-lang", dest="gloss_lang", help="language of glosses/translations (default: zh)")
    p.add_argument("--ui", dest="ui_default", choices=["zh", "en", "es", "ja"], help="default UI language")

    p = sub.add_parser("import", help="import vocabulary CSV/TSV (word,gloss[,note])")
    p.add_argument("file")

    p = sub.add_parser("next", help="print the LLM prompt for the next story")
    p.add_argument("--words", type=int, help="max vocabulary words for this story")
    p.add_argument("--all-uncovered", action="store_true",
                   help="also count candidate stories as covered (default) — use to disable",
                   default=True)

    p = sub.add_parser("add", help="validate a story JSON and add it as a candidate")
    p.add_argument("file")
    p.add_argument("--accept", action="store_true", help="add directly as accepted")

    p = sub.add_parser("accept", help="promote a candidate story")
    p.add_argument("id")

    p = sub.add_parser("reject", help="demote a story back to candidate")
    p.add_argument("id")

    sub.add_parser("status", help="coverage and story list")

    p = sub.add_parser("tts", help="synthesize missing sentence audio into the cache")
    p.add_argument("--candidates", action="store_true", help="include candidate stories")
    p.add_argument("--force", action="store_true", help="regenerate existing clips")
    p.add_argument("--voice", help="override configured voice")
    p.add_argument("--backend", help="edge | none")

    p = sub.add_parser("build", help="build the single-file page")
    p.add_argument("-o", "--out", help="output path (default: dist/index.html)")
    p.add_argument("--accepted-only", action="store_true", help="exclude candidate stories")
    p.add_argument("--home", help="URL for a Home link in the page header (e.g. ./index.html)")

    p = sub.add_parser("studio", help="write the Studio web app (single HTML, no project needed)")
    p.add_argument("-o", "--out", default="studio.html", help="output path (default: studio.html)")

    p = sub.add_parser("reader", help="write the self-serve reader page (my storybook, reads localStorage)")
    p.add_argument("-o", "--out", default="reader.html")

    p = sub.add_parser("unpack", help="unpack a Studio bundle.json into a project directory")
    p.add_argument("file")

    p = sub.add_parser("bridge", help="local OpenAI-compatible server backed by the Codex CLI (codex exec)")
    p.add_argument("--port", type=int, default=8130)
    p.add_argument("--model", default=None, help="codex model (-m); default: codex config default")

    args = ap.parse_args(argv)
    proj = Project(args.project)

    try:
        if args.cmd == "bridge":
            from . import bridge
            return bridge.main(args)

        if args.cmd == "studio":
            out, size = build.build_studio(args.out)
            print(f"wrote {out} ({size / 1024:.0f} KB) — open it in a browser")
            return 0

        if args.cmd == "reader":
            out, size = build.build_reader(args.out)
            print(f"wrote {out} ({size / 1024:.0f} KB) — serve it next to index.html")
            return 0

        if args.cmd == "unpack":
            try:
                dest, n_vocab, n_stories = build.unpack(args.file, args.project)
            except ValueError as e:
                raise ProjectError(str(e))
            print(f"unpacked into {dest}: {n_vocab} vocab words, {n_stories} stories")
            return 0

        if args.cmd == "init":
            cfg = proj.init(name=args.name, lang=args.lang,
                            gloss_lang=args.gloss_lang, ui_default=args.ui_default)
            print(f"initialized fabulita project: lang={cfg['lang']} gloss={cfg['gloss_lang']} "
                  f"voice={cfg['tts']['voice'] or '(none)'}")
            return 0

        proj.require()

        if args.cmd == "import":
            added, updated, total = vocab.import_file(proj, args.file)
            print(f"vocab: +{added} added, {updated} updated, {total} total")

        elif args.cmd == "next":
            prompt, batch = prompts.next_prompt(proj, max_words=args.words)
            if prompt is None:
                print("vocabulary fully covered — nothing to generate 🎉", file=sys.stderr)
                return 1
            print(prompt)
            print(f"[{len(batch)} uncovered words in this batch]", file=sys.stderr)

        elif args.cmd == "add":
            story = stories.add(proj, args.file, accept=args.accept)
            print(f"added {story['id']!r} as {story['status']} "
                  f"({len(story['sentences'])} sentences, {len(story['vocab_used'])} vocab words)")

        elif args.cmd == "accept":
            stories.set_status(proj, args.id, "accepted")
            print(f"accepted {args.id!r}")

        elif args.cmd == "reject":
            stories.set_status(proj, args.id, "candidate")
            print(f"{args.id!r} is a candidate again")

        elif args.cmd == "status":
            cov_acc, _ = proj.coverage(include_candidates=False)
            covered, uncovered = proj.coverage(include_candidates=True)
            total = len(proj.vocab)
            pct = round(100 * len(covered) / total) if total else 0
            line = f"vocabulary: {len(covered)}/{total} covered ({pct}%)"
            if len(covered) != len(cov_acc):
                line += f" — accepted stories only: {len(cov_acc)}/{total}"
            print(line)
            if uncovered:
                print("uncovered: " + ", ".join(w["w"] for w in uncovered))
            print("stories:")
            for s in proj.stories():
                mark = "✓" if s.get("status") == "accepted" else "?"
                print(f"  {mark} {s['id']}  ({len(s.get('vocab_used', []))} vocab words)")

        elif args.cmd == "tts":
            tts.synth_missing(proj, include_candidates=args.candidates,
                              force=args.force, voice=args.voice, backend=args.backend)

        elif args.cmd == "build":
            out, size, n_stories, n_clips = build.build(
                proj, out=args.out, include_candidates=not args.accepted_only, home=args.home)
            print(f"built {out} ({size / 1024:.0f} KB, {n_stories} stories, {n_clips} audio clips)")

    except ProjectError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
