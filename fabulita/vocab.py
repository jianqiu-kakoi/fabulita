"""Vocabulary import.

CSV/TSV columns are::

    word,gloss[,note,category,kind,example,example_trans,answers,review_mode]

Only ``word`` and ``gloss`` are required.  The optional learning metadata is
kept on each vocabulary entry so richer readers can group cards and show an
example without changing the compact two-column workflow.
"""

import csv

from .project import ProjectError, norm


def import_file(project, path):
    delim = "\t" if str(path).endswith((".tsv", ".txt")) else ","
    rows = []
    with open(path, encoding="utf-8-sig") as f:
        for lineno, row in enumerate(csv.reader(f, delimiter=delim), start=1):
            row = [c.strip() for c in row]
            while row and not row[-1]:
                row.pop()
            if not row or not any(row):
                continue
            if len(row) < 2 or not row[0] or not row[1]:
                raise ProjectError(
                    f"{path}, line {lineno}: needs at least 2 columns "
                    f"(word,gloss — gloss in your language), got: {row!r}"
                )
            rows.append(row)
    # skip a header row like "word,gloss"
    if rows and rows[0][0].lower() in ("word", "palabra", "词", "単語"):
        rows = rows[1:]

    words = project.vocab
    known = {norm(w["w"]): w for w in words}
    added = updated = 0
    for row in rows:
        entry = {"w": row[0], "gloss": row[1]}
        optional_fields = ("note", "category", "kind", "example", "example_trans", "answers",
                           "review_mode")
        for index, field in enumerate(optional_fields, start=2):
            if len(row) > index and row[index]:
                entry[field] = row[index]
        key = norm(row[0])
        if key in known:
            if known[key] != entry:
                known[key].update(entry)
                updated += 1
        else:
            words.append(entry)
            known[key] = entry
            added += 1
    project.save_vocab(words)
    return added, updated, len(words)
