"""TTS cache: audio/<story_id>/<sentence_index>.mp3

Backends:
  edge  — Microsoft Edge neural voices via the edge-tts package (default;
          free, network required, unofficial endpoint)
  none  — skip; the built page falls back to the browser's speechSynthesis

Pluggable: add a synth_<name>(text, voice, out_path) coroutine and list it
in BACKENDS.
"""

import asyncio

from .project import AUDIO_DIR, ProjectError


def clip_path(project, story_id, idx):
    return project.root / AUDIO_DIR / story_id / f"{idx}.mp3"


def speech_text(sentence):
    return sentence["text"].replace("«", "").replace("»", "").strip()


async def _synth_edge(text, voice, out_path):
    import edge_tts

    comm = edge_tts.Communicate(text, voice)
    buf = b""
    async for chunk in comm.stream():
        if chunk["type"] == "audio":
            buf += chunk["data"]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(buf)
    return len(buf)


BACKENDS = {"edge": _synth_edge}


def synth_missing(project, include_candidates=False, force=False, voice=None,
                  backend=None, concurrency=6, log=print):
    cfg = project.config
    backend = backend or cfg["tts"].get("backend", "edge")
    if backend == "none":
        log("tts backend is 'none' — skipping (page will use browser speechSynthesis)")
        return 0
    if backend not in BACKENDS:
        raise ProjectError(f"unknown tts backend {backend!r} (have: {', '.join(BACKENDS)}, none)")
    if backend == "edge":
        try:
            import edge_tts  # noqa: F401
        except ImportError:
            raise ProjectError("edge-tts not installed — pip install 'fabulita[tts]'")
    voice = voice or cfg["tts"].get("voice")
    if not voice:
        raise ProjectError("no voice configured — set tts.voice in fabulita.json")

    jobs = []
    for story in project.stories():
        if story.get("status") != "accepted" and not include_candidates:
            continue
        for i, sent in enumerate(story["sentences"]):
            out = clip_path(project, story["id"], i)
            if force or not out.exists():
                jobs.append((story["id"], i, speech_text(sent), out))
    if not jobs:
        log("audio cache is up to date")
        return 0

    synth = BACKENDS[backend]

    async def run():
        sem = asyncio.Semaphore(concurrency)

        async def one(story_id, i, text, out):
            async with sem:
                n = await synth(text, voice, out)
                log(f"  {story_id}/{i}: {n} bytes")

        await asyncio.gather(*(one(*j) for j in jobs))

    log(f"synthesizing {len(jobs)} clips with {backend} voice {voice} ...")
    asyncio.run(run())
    return len(jobs)
