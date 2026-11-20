"""OpenAI-compatible HTTP calls: model listing, chunked audio transcription, chat completions.

Nothing here logs or returns the API key. Error messages are reduced to status code and the
provider's error message, with any occurrence of the key masked.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

from .ai_settings import AIConfig

RETRY_STATUS = {408, 409, 429, 500, 502, 503, 504}
# whisper-1 returns segment timestamps (verbose_json). Other transcription models (gpt-4o-*)
# return plain text only, so short chunks provide the timestamps needed for slide correlation.
SEGMENT_MODELS = ("whisper",)
CHUNK_SECONDS_SEGMENTS = 600
CHUNK_SECONDS_TEXT = 30
PROMPT = "Deutschsprachige juristische Fortbildung mit Paragraphen, Gerichten und Aktenzeichen."
# Chunks quieter than this are not uploaded at all (waiting time before a lecture, pauses):
# saves cost and avoids the typical ASR hallucinations on silence.
SILENCE_MAX_DB = -50.0
# Whisper marks segments it considers non-speech; together with known phantom phrases they are dropped.
NO_SPEECH_LIMIT = 0.6
HALLUCINATIONS = ("amara.org", "untertitel im auftrag des zdf", "untertitelung im auftrag des zdf",
                  "untertitel von stephanie geiges", "copyright wdr")


class ProviderError(RuntimeError):
    pass


def _clean(message: str, cfg: AIConfig) -> str:
    if cfg.api_key:
        message = message.replace(cfg.api_key, "***")
    return message[:300]


def _error(response: httpx.Response, cfg: AIConfig) -> ProviderError:
    try:
        detail = response.json().get("error", {})
        detail = detail.get("message") if isinstance(detail, dict) else str(detail)
    except Exception:
        detail = response.text[:200]
    return ProviderError(_clean(f"HTTP {response.status_code}: {detail or 'ohne Angabe'}", cfg))


def _request(cfg: AIConfig, method: str, path: str, *, attempts: int = 4, timeout: float = 120, **kwargs) -> httpx.Response:
    url = cfg.base_url.rstrip("/") + path
    headers = {"Authorization": "Bearer " + cfg.api_key}
    delay = 2.0
    for attempt in range(1, attempts + 1):
        try:
            with httpx.Client(timeout=timeout, follow_redirects=False) as client:
                response = client.request(method, url, headers=headers, **kwargs)
        except httpx.HTTPError as exc:
            if attempt == attempts:
                raise ProviderError(_clean(f"Verbindung fehlgeschlagen: {type(exc).__name__}", cfg)) from None
        else:
            if response.status_code < 400:
                return response
            if response.status_code not in RETRY_STATUS or attempt == attempts:
                raise _error(response, cfg)
            retry_after = response.headers.get("retry-after", "")
            if retry_after.replace(".", "", 1).isdigit():
                delay = max(delay, min(float(retry_after), 60.0))
        time.sleep(delay)
        delay = min(delay * 2, 60.0)
    raise ProviderError("unreachable")


def list_models(cfg: AIConfig) -> list[str]:
    response = _request(cfg, "GET", "/models", attempts=2, timeout=20)
    try:
        return sorted(str(item["id"]) for item in response.json().get("data", []))
    except Exception:
        return []


def media_duration(path: Path) -> float:
    proc = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
                          capture_output=True, text=True, timeout=120)
    if proc.returncode:
        raise ProviderError("ffprobe failed: " + proc.stderr[-200:])
    return float(json.loads(proc.stdout)["format"]["duration"])


def chunk_plan(duration: float, chunk_seconds: int) -> list[tuple[float, float]]:
    plan, offset = [], 0.0
    while offset < duration - 0.25:
        length = min(float(chunk_seconds), duration - offset)
        plan.append((round(offset, 3), round(length, 3)))
        offset += chunk_seconds
    return plan


def _extract_chunk(video: Path, target: Path, offset: float, length: float) -> None:
    # Mono 16 kHz MP3 at 48 kbit/s: 10 minutes ≈ 3.6 MB, well below the 25 MB upload limit.
    proc = subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                           "-ss", f"{offset:.3f}", "-t", f"{length:.3f}", "-i", str(video), "-vn",
                           "-ac", "1", "-ar", "16000", "-c:a", "libmp3lame", "-b:a", "48k", str(target)],
                          capture_output=True, text=True, timeout=900)
    if proc.returncode or not target.is_file():
        raise ProviderError("Audio chunk extraction failed: " + proc.stderr[-200:])


def _is_phantom(text: str) -> bool:
    low = text.lower()
    return any(marker in low for marker in HALLUCINATIONS)


def parse_transcription(payload: dict, offset: float, length: float) -> list[dict]:
    segments = payload.get("segments")
    if isinstance(segments, list) and segments:
        lines = []
        for seg in segments:
            text = str(seg.get("text", "")).strip()
            if not text or _is_phantom(text) or float(seg.get("no_speech_prob", 0) or 0) > NO_SPEECH_LIMIT:
                continue
            lines.append({"start": round(offset + float(seg.get("start", 0)), 2),
                          "end": round(offset + float(seg.get("end", 0)), 2), "text": text})
        return lines
    text = str(payload.get("text", "")).strip()
    if not text or _is_phantom(text):
        return []
    return [{"start": round(offset, 2), "end": round(offset + length, 2), "text": text}]


def chunk_is_silent(path: Path) -> bool:
    proc = subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"],
                          capture_output=True, text=True, timeout=300)
    for line in proc.stderr.splitlines():
        if "max_volume:" in line:
            try:
                return float(line.split("max_volume:")[1].split("dB")[0]) < SILENCE_MAX_DB
            except ValueError:
                return False
    return False


def _transcribe_chunk(cfg: AIConfig, video: Path, workdir: Path, index: int, offset: float, length: float) -> list[dict]:
    target = workdir / f"chunk_{index:05d}.mp3"
    _extract_chunk(video, target, offset, length)
    if chunk_is_silent(target):
        target.unlink(missing_ok=True)
        return []
    segment_mode = cfg.transcription_model.startswith(SEGMENT_MODELS)
    data = {"model": cfg.transcription_model, "language": "de", "prompt": PROMPT,
            "response_format": "verbose_json" if segment_mode else "json"}
    if segment_mode:
        data["timestamp_granularities[]"] = "segment"
    try:
        response = _request(cfg, "POST", "/audio/transcriptions", data=data, timeout=300,
                            files={"file": (target.name, target.read_bytes(), "audio/mpeg")})
        return parse_transcription(response.json(), offset, length)
    finally:
        target.unlink(missing_ok=True)


def transcribe_video(cfg: AIConfig, video: Path, directory: Path, workers: int = 4) -> list[dict]:
    if not cfg.has_key:
        raise ProviderError("Kein API-Key hinterlegt (Verwaltung → KI und Benachrichtigung)")
    chunk_seconds = CHUNK_SECONDS_SEGMENTS if cfg.transcription_model.startswith(SEGMENT_MODELS) else CHUNK_SECONDS_TEXT
    plan = chunk_plan(media_duration(video), chunk_seconds)
    workdir = directory / "asr-chunks"
    workdir.mkdir(parents=True, exist_ok=True)
    try:
        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            parts = list(pool.map(lambda item: _transcribe_chunk(cfg, video, workdir, item[0], *item[1]),
                                  enumerate(plan)))
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    return [line for part in parts for line in part]


def chat_json(cfg: AIConfig, system: str, user: str) -> dict:
    response = _request(cfg, "POST", "/chat/completions", timeout=300, json={
        "model": cfg.summary_model, "response_format": {"type": "json_object"},
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]})
    try:
        return json.loads(response.json()["choices"][0]["message"]["content"])
    except Exception as exc:
        raise ProviderError("Antwort des KI-Dienstes war kein gültiges JSON") from exc
