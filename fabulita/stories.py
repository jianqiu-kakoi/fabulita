"""Story validation and lifecycle (candidate -> accepted)."""

import json
import re

from .project import WORD_RE, ProjectError, norm

REQUIRED = ("id", "title", "sentences")
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def _appears(word, tokens, fulltext):
    """True if the vocab word plausibly appears in the text.

    Exact token match; prefix match with the last character dropped so
    dictionary forms match simple inflections (manzana -> manzanas,
    negro -> negros/negra); or plain substring for languages without word
    spacing (Japanese, Chinese). Deliberately loose: this guards against
    the LLM listing words it never used, not against morphology.
    """
    w = norm(word)
    if w in tokens:
        return True
    stem = w[:-1]
    if len(stem) >= 3:
        for t in tokens:
            if t.startswith(stem):
                return True
    return w in fulltext


def validate(project, story):
    """Returns (errors, warnings). Errors block `add`; warnings are printed."""
    errors, warnings = [], []
    for k in REQUIRED:
        if not story.get(k):
            errors.append(f"missing field: {k}")
    if errors:
        return errors, warnings

    if not ID_RE.match(story["id"]):
        errors.append(f"id {story['id']!r}: use lowercase letters, digits, hyphens")

    for i, s in enumerate(story["sentences"]):
        if not isinstance(s, dict) or "text" not in s:
            errors.append(f"sentence {i}: need an object with at least 'text'")
    if errors:
        return errors, warnings

    tokens = set()
    fulltext = norm(" ".join(s["text"] for s in story["sentences"]))
    for s in story["sentences"]:
        tokens |= {norm(t) for t in WORD_RE.findall(s["text"])}
    for w in story.get("vocab_used", []):
        if not _appears(w, tokens, fulltext):
            warnings.append(f"vocab_used word {w!r} does not seem to appear in the text")

    vocab_set = {norm(w["w"]) for w in project.vocab}
    for w in story.get("vocab_used", []):
        if vocab_set and norm(w) not in vocab_set:
            warnings.append(f"vocab_used word {w!r} is not in vocab.json")

    return errors, warnings


def add(project, path, accept=False, log=print):
    with open(path, encoding="utf-8") as f:
        story = json.load(f)
    story.setdefault("status", "accepted" if accept else "candidate")
    story.setdefault("vocab_used", [])
    story.setdefault("glossary", {})
    story.setdefault("grammar", [])
    errors, warnings = validate(project, story)
    for w in warnings:
        log(f"warning: {w}")
    if errors:
        raise ProjectError("invalid story:\n  " + "\n  ".join(errors))
    if project.story_path(story["id"]).exists():
        raise ProjectError(
            f"story {story['id']!r} already exists (delete it or change the id)"
        )
    project.save_story(story)
    return story


def set_status(project, story_id, status):
    p = project.story_path(story_id)
    if not p.exists():
        raise ProjectError(f"no story {story_id!r}")
    with open(p, encoding="utf-8") as f:
        story = json.load(f)
    story["status"] = status
    project.save_story(story)
    return story
