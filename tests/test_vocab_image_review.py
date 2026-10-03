"""Pure-logic tests for the local vocab image review tool."""

import json

from scripts.review_vocab_images import apply_choice, preview_url, review_page_html


def test_preview_url_uses_wikimedia_thumbnails_and_source_urls_otherwise():
    wiki = {"url": "https://upload.wikimedia.org/wikipedia/commons/a/ab/Toaster.jpg", "thumbnail": "t"}
    assert preview_url(wiki) == "https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/Toaster.jpg/480px-Toaster.jpg"
    flickr = {"url": "https://live.staticflickr.com/1/2_b.jpg", "thumbnail": "t"}
    assert preview_url(flickr) == "https://live.staticflickr.com/1/2_b.jpg"


def test_apply_choice_updates_selection_and_invalidates_stale_download():
    manifest = {"entries": [{
        "spanish": "la tortuga", "selected": "a", "candidates": [{"id": "a"}, {"id": "b"}],
        "image": {"file": "images/001-turtle.jpg", "candidateId": "a"},
    }]}
    assert apply_choice(manifest, "la tortuga", "b") is True
    entry = manifest["entries"][0]
    assert entry["selected"] == "b" and entry["image"] is None
    assert entry["reviewed"] is True
    assert apply_choice(manifest, "la tortuga", None) is True
    assert entry["selected"] is None and entry["image"] is None
    assert apply_choice(manifest, "la tortuga", "zzz") is False
    assert apply_choice(manifest, "nope", "a") is False


def test_review_page_lists_every_entry_with_its_candidates():
    manifest = {"entries": [
        {"spanish": "la tortuga", "english": "turtle", "category": "Animales", "numbers": [1],
         "query": "turtle", "selected": "a",
         "candidates": [{"id": "a", "url": "https://x/a.jpg", "thumbnail": "", "title": "T", "creator": "C",
                         "license": "cc0", "landing": "https://x/a", "source": "flickr"}],
         "image": None},
        {"spanish": "la niebla", "english": "fog", "category": "El tiempo", "numbers": [179],
         "query": "fog", "selected": None, "candidates": [], "image": None},
    ]}
    html = review_page_html(manifest)
    assert "la tortuga" in html and "la niebla" in html
    assert 'data-spanish="la tortuga"' in html
    assert 'data-candidate="a"' in html
    assert "https://x/a.jpg" in html
    assert "没有可用图片" in html
    assert json.dumps("la tortuga") in html or "la tortuga" in html
