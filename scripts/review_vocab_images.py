#!/usr/bin/env python3
"""Local review page for the CC0 vocabulary photos.

  uv run python scripts/review_vocab_images.py            # serves http://127.0.0.1:8770/
  uv run python scripts/review_vocab_images.py --write docs/vocab-image-review.local.html

Each word shows its Openverse candidates; clicking one selects it and the
choice is written straight back into ``assets/vocab-images/manifest.json``.
"无图" clears the selection so the word is left out of the picture quiz.
After reviewing, run ``fetch_mi_espanol_cc0_images.py download`` again to fetch
any changed selections.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "examples" / "mi-espanol" / "assets" / "vocab-images" / "manifest.json"
WIKIMEDIA_RE = re.compile(r"^(https://upload\.wikimedia\.org/wikipedia/commons)/([0-9a-f])/([0-9a-f]{2})/([^/]+)$")


def preview_url(candidate: dict) -> str:
    url = candidate.get("url") or ""
    match = WIKIMEDIA_RE.match(url)
    if match:
        base, first, second, name = match.groups()
        return f"{base}/thumb/{first}/{second}/{name}/480px-{name}"
    return url


def apply_choice(manifest: dict, spanish: str, candidate_id: str | None) -> bool:
    for entry in manifest.get("entries", []):
        if entry.get("spanish") != spanish:
            continue
        if candidate_id is not None and not any(c.get("id") == candidate_id for c in entry.get("candidates", [])):
            return False
        if entry.get("selected") != candidate_id:
            entry["selected"] = candidate_id
            entry["image"] = None
        entry["reviewed"] = True
        return True
    return False


def review_page_html(manifest: dict) -> str:
    esc = html.escape
    rows = []
    for entry in manifest.get("entries", []):
        candidates = entry.get("candidates") or []
        cards = []
        for candidate in candidates:
            selected = candidate.get("id") == entry.get("selected")
            cards.append(
                f'<label class="card{" is-selected" if selected else ""}" data-candidate="{esc(candidate["id"])}">'
                f'<img loading="lazy" src="{esc(preview_url(candidate))}" alt="">'
                f'<span class="meta">{esc(candidate.get("license", ""))} · {esc(candidate.get("source", ""))}'
                f'<br>{esc((candidate.get("title") or "")[:40])}'
                f'<br><a href="{esc(candidate.get("landing") or candidate.get("url") or "#")}" target="_blank" rel="noopener">出处</a></span>'
                "</label>"
            )
        none_selected = entry.get("selected") is None
        cards.append(
            f'<label class="card is-none{" is-selected" if none_selected else ""}" data-candidate="">'
            "<span class=\"meta\">无图<br>（不出图题）</span></label>"
        )
        body = "".join(cards) if candidates else '<p class="empty">没有可用图片（Openverse 无 CC0 结果）</p>' + cards[-1]
        rows.append(
            f'<section class="word" data-spanish="{esc(entry["spanish"])}">'
            f'<h2>{esc(entry["spanish"])} <small>{esc(entry.get("english", ""))} · {esc(entry.get("category", ""))}'
            f' · 检索词「{esc(entry.get("query", ""))}」</small></h2>'
            f'<div class="cards">{body}</div></section>'
        )
    entries_count = len(manifest.get("entries", []))
    return f"""<!doctype html><html lang="zh"><meta charset="utf-8"><title>词汇图片审核</title>
<style>
body{{font-family:system-ui;margin:0;padding:1rem 1.5rem;background:#f6f4ee;color:#2a2620}}
header{{position:sticky;top:0;background:#f6f4ee;padding:.5rem 0;border-bottom:1px solid #ddd;z-index:2}}
.word{{margin:1.5rem 0;padding:1rem;background:#fff;border-radius:10px}}
h2{{margin:0 0 .6rem;font-size:1.1rem}} h2 small{{font-weight:400;color:#6f695e;font-size:.85rem}}
.cards{{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:.6rem}}
.card{{display:flex;flex-direction:column;border:3px solid #ddd;border-radius:8px;overflow:hidden;cursor:pointer;background:#fafafa}}
.card img{{width:100%;aspect-ratio:4/3;object-fit:cover;background:#eee}}
.card .meta{{font-size:.72rem;padding:.3rem .4rem;color:#555}}
.card.is-selected{{border-color:#d9532b;background:#fff1ea}}
.card.is-none{{justify-content:center;align-items:center;min-height:120px}}
.empty{{color:#a33;margin:.2rem 0}}
#status{{color:#6f695e;font-size:.9rem}}
</style>
<header><strong>词汇图片审核</strong> · {entries_count} 词 · 点一张图即选中并保存 · <span id="status">就绪</span></header>
{''.join(rows)}
<script>
var status = document.getElementById("status");
document.addEventListener("click", function (e) {{
  var card = e.target.closest(".card"); if (!card || e.target.tagName === "A") return;
  var word = card.closest(".word"); var spanish = word.dataset.spanish; var id = card.dataset.candidate || null;
  fetch("/save", {{method: "POST", headers: {{"Content-Type": "application/json"}},
    body: JSON.stringify({{spanish: spanish, candidate: id}})}})
    .then(function (r) {{ return r.json(); }})
    .then(function (r) {{
      if (!r.ok) {{ status.textContent = "保存失败：" + spanish; return; }}
      word.querySelectorAll(".card").forEach(function (c) {{ c.classList.toggle("is-selected", c === card); }});
      status.textContent = "已保存：" + spanish + (id ? "" : "（无图）");
    }}).catch(function () {{ status.textContent = "保存失败（服务未运行？）"; }});
}});
</script></html>"""


class _Handler(BaseHTTPRequestHandler):
    manifest_path = MANIFEST

    def _manifest(self) -> dict:
        return json.loads(self.manifest_path.read_text(encoding="utf-8"))

    def do_GET(self):  # noqa: N802
        body = review_page_html(self._manifest()).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            manifest = self._manifest()
            ok = apply_choice(manifest, str(payload.get("spanish", "")), payload.get("candidate"))
            if ok:
                self.manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        except (ValueError, OSError):
            ok = False
        body = json.dumps({"ok": ok}).encode("utf-8")
        self.send_response(200 if ok else 400)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):  # quiet
        return


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    parser.add_argument("--port", type=int, default=8770)
    parser.add_argument("--write", type=Path, help="write a static copy of the page and exit")
    args = parser.parse_args(argv)
    if args.write:
        args.write.write_text(review_page_html(json.loads(args.manifest.read_text(encoding="utf-8"))), encoding="utf-8")
        print(f"wrote {args.write}")
        return 0
    _Handler.manifest_path = args.manifest
    server = ThreadingHTTPServer(("127.0.0.1", args.port), _Handler)
    print(f"review page: http://127.0.0.1:{args.port}/  (Ctrl-C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
