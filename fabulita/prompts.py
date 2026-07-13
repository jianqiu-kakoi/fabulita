"""Generate the LLM prompt for the next story (bring your own LLM).

fabulita deliberately does not call any model API: paste the prompt into
Claude/ChatGPT/a local model, save the JSON it returns, `fabulita add` it.
"""

import json

LANG_NAMES = {
    "es": "Spanish", "en": "English", "ja": "Japanese", "zh": "Chinese",
    "fr": "French", "de": "German", "it": "Italian", "pt": "Portuguese",
    "ko": "Korean",
}

TEMPLATE = """\
You are writing a graded-reader micro-story for a beginner (CEFR A1) learner of {lang_name}.

Write ONE short story (5-8 short sentences, simple present tense, one scene,
concrete everyday situation). You MUST use at least {min_use} and at most {max_words}
of these vocabulary words (their glosses are in {gloss_lang}):

{word_list}

Rules:
- Only A1-level grammar and high-frequency function words besides the list above.
- Natural, coherent story — not a word-salad that name-drops vocabulary.
- Glosses and translations must be written in {gloss_lang}.
- "glossary" must cover EVERY word form that appears in the text and is not a proper
  name — including inflected verb forms (gloss them like: "打开", "← abrir（打开）").
- "vocab_used" lists exactly the words from the vocabulary list above that appear
  in the story (dictionary form as given in the list).

Return ONLY a JSON object in this exact shape (no markdown fence, no commentary):

{schema}
"""

SCHEMA = {
    "id": "kebab-case-slug",
    "title": "Story title in the target language",
    "title_note": "title translated",
    "sentences": [
        {"text": "First sentence.", "trans": "translation of the sentence"}
    ],
    "vocab_used": ["word1", "word2"],
    "glossary": {"word-form-in-text": ["gloss", "optional note e.g. ← infinitive"]},
    "grammar": [["pattern", "short explanation"]],
}

GLOSS_LANG_NAMES = {"zh": "Chinese (中文)", "en": "English", "ja": "Japanese", "es": "Spanish"}


def next_prompt(project, max_words=None, include_candidates=True):
    cfg = project.config
    max_words = max_words or cfg.get("max_words_per_story", 20)
    _, uncovered = project.coverage(include_candidates=include_candidates)
    if not uncovered:
        return None, []
    batch = uncovered[:max_words]
    word_list = "\n".join(
        f"- {w['w']} — {w['gloss']}" + (f" ({w['note']})" if w.get("note") else "")
        for w in batch
    )
    prompt = TEMPLATE.format(
        lang_name=LANG_NAMES.get(cfg["lang"], cfg["lang"]),
        gloss_lang=GLOSS_LANG_NAMES.get(cfg["gloss_lang"], cfg["gloss_lang"]),
        min_use=min(10, len(batch)),
        max_words=max_words,
        word_list=word_list,
        schema=json.dumps(SCHEMA, ensure_ascii=False, indent=2),
    )
    return prompt, batch
