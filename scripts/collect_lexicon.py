#!/usr/bin/env python
"""Scan homework answer sentences for words no lexicon source covers.

The learner page underlines a word in a completed answer sentence only when
one of three sources knows it: the assignment's studyWords, its
sentenceLexicon, or the project's core vocab.csv. This tool finds content
words none of them cover, so every generated assignment ships clickable
glosses.

Usage: uv run python scripts/collect_lexicon.py examples/mi-espanol [--check]
"""
import argparse
import csv
import json
import re
import sys
import unicodedata
from pathlib import Path

ARTICLES = {"el", "la", "los", "las", "un", "una", "unos", "unas"}
# Function words and ser/estar conjugations (the graded answers themselves)
# are exempt from coverage; everything else must have a gloss source.
STOPWORDS = ARTICLES | {
    "soy", "eres", "es", "somos", "sois", "son",
    "estoy", "estás", "está", "estamos", "estáis", "están",
    "ser", "estar",
    "de", "del", "al", "a", "en", "y", "e", "o", "u", "que", "qué",
    "con", "sin", "para", "por", "como", "pero", "porque", "si", "no", "ni",
    "se", "me", "te", "le", "les", "nos", "os", "lo",
    "mi", "mis", "tu", "tus", "su", "sus", "nuestro", "nuestra", "nuestros", "nuestras",
    "yo", "tú", "él", "ella", "usted", "ustedes", "nosotros", "nosotras",
    "vosotros", "vosotras", "ellos", "ellas",
    "este", "esta", "estos", "estas", "ese", "esa", "esos", "esas",
    "muy", "más", "menos", "también", "ya", "aquí", "ahí", "dónde", "quién",
    "cuál", "cómo", "cuándo", "verdad", "mío", "mía", "algo",
}
WORD_RE = re.compile(r"[a-záéíóúüñ]+", re.IGNORECASE)
BLANK = "_______"


def norm(text):
    return unicodedata.normalize("NFKC", str(text)).lower().strip()


def surface_forms(word):
    forms = set()
    for alt in re.split(r"\s*/\s*", norm(word)):
        if not alt:
            continue
        forms.add(alt)
        parts = alt.split()
        if len(parts) > 1 and parts[0] in ARTICLES:
            forms.add(" ".join(parts[1:]))
    return forms


def _entry_forms(entry):
    values = [entry.get("word") or ""]
    values += [v for v in (entry.get("forms") or []) if v]
    values += [v for v in (entry.get("answers") or []) if v]
    out = set()
    for value in values:
        out |= surface_forms(value)
    return out


def covered_tokens(assignment, vocab_rows):
    forms = set()
    for entry in assignment.get("studyWords") or []:
        forms |= _entry_forms(entry)
    for entry in assignment.get("sentenceLexicon") or []:
        forms |= _entry_forms(entry)
    for row in vocab_rows:
        if norm(row.get("kind") or "") == "grammar":
            continue
        if row.get("word"):
            forms |= surface_forms(row["word"])
    tokens = set()
    for form in forms:
        tokens.add(form)
        tokens |= set(form.split())
    return tokens


def answer_sentences(item):
    prompt = re.sub(r"\s*\([^)]*\)\s*$", "", str(item.get("prompt") or "")).strip()
    if BLANK not in prompt:
        return []
    return [prompt.replace(BLANK, answer) for answer in item.get("answers") or []]


def uncovered_words(assignment, vocab_rows):
    covered = covered_tokens(assignment, vocab_rows)
    missing = {}
    for section in assignment.get("sections") or []:
        for item in section.get("items") or []:
            for sentence in answer_sentences(item):
                for token in WORD_RE.findall(norm(sentence)):
                    if token in STOPWORDS or token in covered:
                        continue
                    ids = missing.setdefault(token, [])
                    if item.get("id") not in ids:
                        ids.append(item.get("id"))
    return missing


def load_vocab_rows(project_root):
    path = Path(project_root) / "vocab.csv"
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", help="project directory, e.g. examples/mi-espanol")
    parser.add_argument("--check", action="store_true",
                        help="exit 1 if any word is uncovered")
    args = parser.parse_args()
    root = Path(args.project)
    data = json.loads((root / "homework.json").read_text(encoding="utf-8"))
    vocab_rows = load_vocab_rows(root)
    gaps = 0
    for assignment in data.get("assignments") or []:
        missing = uncovered_words(assignment, vocab_rows)
        if not missing:
            continue
        gaps += len(missing)
        print(f"{assignment.get('id')}: {len(missing)} uncovered words")
        for token in sorted(missing):
            print(f"  {token}  ({', '.join(missing[token])})")
    if not gaps:
        print("all answer-sentence words are covered")
    if args.check and gaps:
        sys.exit(1)


if __name__ == "__main__":
    main()
