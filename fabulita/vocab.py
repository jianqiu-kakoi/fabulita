"""Vocabulary import: CSV/TSV with columns  word,gloss[,note]  (no header needed)."""

import csv

from .project import ProjectError, norm


def import_file(project, path):
    delim = "\t" if str(path).endswith((".tsv", ".txt")) else ","
    rows = []
    with open(path, encoding="utf-8-sig") as f:
        for lineno, row in enumerate(csv.reader(f, delimiter=delim), start=1):
            row = [c.strip() for c in row if c.strip()]
            if not row:
                continue
            if len(row) == 1:
                raise ProjectError(
                    f"{path}, line {lineno}: needs at least 2 columns "
                    f"(word,gloss — gloss in your language), got: {row[0]!r}"
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
        if len(row) > 2:
            entry["note"] = row[2]
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
