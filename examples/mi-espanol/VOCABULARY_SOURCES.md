# Mi Español vocabulary sources

## Vocabulario A0 - Principiante - Cuaderno visual

- Author: the learner's Spanish tutor (name withheld; pseudonymized as "Profesor de ejemplo" in this repository).
- Imported: 2026-08-28
- Source supplied by the user as a local PDF.
- Scope: 287 numbered Spanish-English entries across 10 A0 topics.
- Integration: 282 unique Spanish entries were found in the PDF. Five repeated
  entries were merged, four entries already existed in `vocab.csv`, and 278 new
  entries were added.
- Adaptation: the Spanish headwords and English meanings were transcribed; the
  Chinese meanings were added for Mi Español. The PDF illustrations were not
  copied into this repository.

The source PDF does not state a reuse license. Its layout, illustrations, and
original compilation are not covered by this repository's Apache-2.0 license.

## Private lesson attachments (tutor name withheld)

- Imported: 2026-10-03, read from the user's own lesson conversation
  attachments. No PDF or image from the conversation was copied into this
  repository.
- Sources: `Vocabulario_A1_1_Tabla` ("150 Sustantivos A1"),
  `Vocabulario_A1_Tiempo_Contexto`, the infinitives used in
  `ejercicio_verbos_regulares_A1_A2`, and the whiteboard notes of a
  lesson (question words, `tener`, `salir`, regular -ar/-er/-ir
  model verbs).
- Integration: 248 new rows were appended to `vocab.csv`; headwords already
  present were skipped.
- Adaptation: only Spanish headwords and English meanings were transcribed.
  Definite articles, Chinese meanings, categories and the two conjugation rows
  were added for Mi Español. Worksheet sentences and example sentences from
  the tutor's material were not copied.

The source files do not state a reuse license. Their layout and original
compilation are not covered by this repository's Apache-2.0 license.

## A1 topic picture homework (2026-10-03)

- 106 of the A1 words have a picture, recorded in
  `assets/vocab-images/a1-topics.json` with files in `assets/vocab-images/a1/`.
  They are grouped into nine topics; each topic becomes its own assignment
  (`vocabulario-a1-<topic>`), so the homework list is organised by category.
- 98 illustrations are from [Icons8](https://icons8.com/), used under its
  [free license with link attribution](https://icons8.com/license); the learning
  page shows the Icons8 credit. They are not CC0 or Apache-2.0 assets.
- The eight colour swatches were generated for this project and are CC0-1.0.
- Every picture was visually checked by the assistant; its SHA-256, source URL,
  landing page and license are recorded per entry.
- Run `python scripts/build_mi_espanol_topic_visual_homework.py` to regenerate
  the assignments, and `python scripts/build_mi_espanol_conjugation_homework.py`
  for the present-tense conjugation assignment (`presente-verbos-a1`, standard
  conjugations, not taken from any worksheet).

## Homework lexicon words (2026-10-03)

- 121 rows were added to `vocab.csv` for words that the public homework
  assignments already glossed in their own `studyWords` / `sentenceLexicon`
  but that were missing from the main list, plus common function words
  (`al`, `del`, `por`, `para`, `me`, `se`, ...). Personal names, city names and
  conjugated forms of `ser` / `estar` were left out.

## Class notes: question words and ser / estar (2026-10-03)

- 25 rows were appended to `vocab.csv` from the learner's own class notes:
  example questions for each question word (`¿qué estudias?`,
  `¿cómo te llamas?`, `¿dónde está el baño?`, `¿cuántos perros tienes?`, ...),
  `¿cuántos? / ¿cuántas?`, and grammar notes (`ser vs estar`, the present-tense
  conjugations of `ser` and `estar`, `¿por qué?` vs `porque`, `¿por qué?` vs
  `¿para qué?`, `¿cómo es…?` vs `¿cómo está…?`, `¿cómo?` vs `como`). Example
  sentences are standard textbook Spanish written for this list. Existing rows
  were not changed.

- The homework `interrogativos-ser-estar-a1` (built by
  `scripts/build_mi_espanol_interrogativos_homework.py`) practises the same
  class notes: question words, por qué / porque / para qué, ser vs estar,
  ser / estar conjugation and short translations. Standard grammar answer key.

## A0 visual vocabulary photos (public, CC0 / public domain)

- Directory: `assets/vocab-images/` (`manifest.json` + `images/`).
- Provider: [Openverse](https://openverse.org/) search API, restricted to the
  `cc0` and `pdm` (Public Domain Mark) licenses. This automatic search pipeline
  keeps only those licenses; the reviewed replacements below are separate.
- Pipeline: `scripts/fetch_mi_espanol_cc0_images.py` (plan / search / download),
  `scripts/review_vocab_images.py` (local review page that writes the chosen
  candidate back into the manifest), then
  `scripts/build_mi_espanol_public_visual_homework.py` to upsert the public
  `vocabulario-a0-visual` assignment into `homework.json`.
- Provenance: every candidate in the manifest records its source URL, landing
  page, creator, license and provider. The chosen image's provenance is copied
  into the assignment's image registry (`sourceUrl`, `landing`, `creator`,
  `license`). CC0 / PDM works do not require attribution; it is kept anyway.
- Images are downscaled to 480px JPEG and delivered as separate files
  (`deliver: "file"`), copied to `docs/assets/mi-espanol/vocab/` at build time.
- Days of the week and months are intentionally left without pictures.
- The illustrations of the tutor's cuaderno are NOT used here; they
  remain local-only under the ignored `materials/vocabulario-a0-visual/`.

## Reviewed library replacements (2026-09-24)

- All 262 illustrated words use replacements recorded in
  `assets/vocab-images/curated.json`, with files in `curated/`.
- 258 illustrations are from [Icons8](https://icons8.com/), used under its
  [free license with link attribution](https://icons8.com/license).
  The learning page includes a visible Icons8 credit. These files are not CC0
  or Apache-2.0 assets. Contributor names and individual source pages are
  retained per image. PNGs are displayed without enlarging their native size.
- Four scene photographs (cycling, rain, beach, lifeguard) are from
  [Pexels](https://www.pexels.com/) under the
  [Pexels License](https://www.pexels.com/license/). The photographers are
  Netto Fps, Deva Darshan, one second before sunset, and Bruno Curly.
- The user selected the proposed illustration/photo direction; the expanded
  set was visually checked by the assistant. Ambiguous library search results
  were replaced with specific asset IDs. The exact downloaded bytes, SHA-256,
  creator, license, source URL, and landing page are recorded in `curated.json`.
- Run `python scripts/build_mi_espanol_public_visual_homework.py` to apply the
  replacements, then `python scripts/build_docs.py` to rebuild the learning
  page. The builder automatically loads `curated.json` beside the original
  manifest. The original manifest and photos remain available for rollback;
  rerunning the Openverse downloader cannot overwrite curated assets.
- Assignment IDs, question IDs, answers, choices, and image IDs are preserved
  so existing browser learning records continue to match the same exercises.
