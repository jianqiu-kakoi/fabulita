# Draft cache + no auto-continue after keep

Date: 2026-07-17
Status: approved (user request verbatim)
Scope: `docs/index.html` only.

## Problem

1. A generated story preview lives only in memory: navigating away (reader,
   reload) loses it — "白生成了".
2. After ✓ keeping a story, the next generation auto-starts; the user wants
   to land back on the word-source selection instead.

## Design

1. **Draft cache** (`localStorage["fabulita.draft"]`): when a preview
   arrives, persist `{story, warnings, missing, targetId, genSel, genSrc,
   ts}`. On page load (after migration), if a draft exists AND its
   `targetId` project still exists: open the widget on the 生成故事 tab
   with selection/source restored and the preview showing. Cleared on:
   keep, reroll (start), stop/discard, gsel selection change. Corrupted
   draft → silently dropped. In-app tab/view switches already preserve the
   in-memory preview; the cache adds reload/navigation survival.
2. **No auto-continue**: `keep` saves the story, resets the loop to idle and
   re-renders the gen tab (selection + updated coverage). All sources
   behave alike (manual already did). The idle 停 button and `lp.stopped`
   machinery become vestigial and are removed (the preview row keeps its
   ■ button as "discard this preview"); the `gen-save` auto-start gate
   drops its `stopped` check and its auto-start entirely (saving provider
   settings never launches a generation by itself now).

## Testing

Agent browser QA: generate → preview → reload page → preview restored with
correct selection/source; keep → back to selection view, no auto request
(watch network); draft cleared after keep (reload shows no preview);
discard clears draft; standing criteria unaffected.
