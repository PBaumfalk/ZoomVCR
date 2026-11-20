"""Real FFmpeg capture/merge/probe and computer-vision slide extraction."""
import json
import math
import os
import subprocess
import time
from pathlib import Path
import cv2
import numpy as np
from PIL import Image
from .config import settings

class MediaError(RuntimeError):
    pass

def recording_dir(recording_id: str) -> Path:
    import uuid
    # User-supplied IDs never turn into filesystem paths.
    uuid.UUID(recording_id)
    root = settings().storage_root.resolve()
    result = (root / recording_id).resolve()
    if not result.is_relative_to(root):
        raise ValueError("invalid recording path")
    result.mkdir(parents=True, exist_ok=True)
    return result

def ffprobe(path: Path) -> dict:
    proc = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration,size:stream=codec_type,codec_name", "-of", "json", str(path)], capture_output=True, text=True, timeout=30)
    if proc.returncode:
        raise MediaError("ffprobe failed: " + proc.stderr[-1000:])
    return json.loads(proc.stdout)

def verify_media(path: Path) -> dict:
    if not path.is_file() or path.stat().st_size < 500:
        raise MediaError(f"Media file missing/empty: {path.name}")
    metadata = ffprobe(path)
    streams = metadata.get("streams", [])
    if not any(x.get("codec_type") == "video" for x in streams):
        raise MediaError("Video stream missing")
    if not any(x.get("codec_type") == "audio" for x in streams):
        raise MediaError("Audio stream missing")
    duration = float(metadata.get("format", {}).get("duration") or 0)
    if duration <= 0:
        raise MediaError("Invalid media duration")
    return {"duration_seconds": round(duration, 3), "size_bytes": path.stat().st_size, "streams": streams}

def _safe_concat_name(value: Path) -> str:
    return "file '" + str(value.resolve()).replace("'", "'\\''") + "'\n"

def merge_segments(directory: Path) -> dict:
    segments = sorted((directory / "segments").glob("*.mkv"))
    if not segments:
        raise MediaError("No video segments found")
    for part in segments:
        verify_media(part)
    entries = directory / "segments.ffconcat"
    entries.write_text("ffconcat version 1.0\n" + "".join(_safe_concat_name(p) for p in segments), encoding="utf-8")
    temp = directory / "recording.partial.mp4"
    final = directory / "recording.mp4"
    proc = subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", "-y", "-loglevel", "error", "-safe", "0", "-f", "concat", "-i", str(entries), "-c", "copy", "-movflags", "+faststart", str(temp)], capture_output=True, text=True, timeout=5400)
    if proc.returncode:
        raise MediaError("FFmpeg concat error: " + proc.stderr[-1000:])
    details = verify_media(temp)
    os.replace(temp, final)
    return details

def _synthetic_command(duration: float, segments_dir: Path) -> list[str]:
    # A real 3-slide demonstration, not a pre-recorded placeholder.
    # Individual sources have static slides so slide detection has distinct signals.
    each = max(0.4, duration / 3)
    colors = ("0x122138", "0x185B50", "0x69452D")
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "warning", "-y"]
    for col in colors:
        cmd += ["-f", "lavfi", "-i", f"color=c={col}:size=1280x720:rate=12:duration={each}"]
    cmd += ["-f", "lavfi", "-i", f"sine=frequency=440:sample_rate=48000:duration={duration}"]
    font = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    filters = []
    for idx in range(3):
        name = ("ARBEITSRECHT", "RECHTSPRECHUNG", "PRAXISHINWEISE")[idx]
        filters.append(f"[{idx}:v]drawtext=fontfile={font}:text='FOLIE {idx+1} - {name}':fontcolor=white:fontsize=46:x=(w-text_w)/2:y=(h-text_h)/2,format=yuv420p[v{idx}]")
    filters.append("[v0][v1][v2]concat=n=3:v=1:a=0[v]")
    cmd += ["-filter_complex", ";".join(filters), "-map", "[v]", "-map", "3:a:0", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "27", "-c:a", "aac", "-b:a", "96k", "-pix_fmt", "yuv420p", "-force_key_frames", f"expr:gte(t,n_forced*{settings().record_segment_seconds})", "-shortest", "-f", "segment", "-segment_time", str(settings().record_segment_seconds), "-reset_timestamps", "1", "-segment_format", "matroska", str(segments_dir / "segment_%05d.mkv")]
    return cmd

def record_synthetic(recording_id: str, duration: float, stop_requested=lambda: False, on_tick=lambda: None) -> None:
    if duration < 1:
        raise MediaError("Synthetic recording duration must be >= 1 second")
    directory = recording_dir(recording_id)
    segments = directory / "segments"
    segments.mkdir(exist_ok=True)
    if any(segments.glob("segment_*.mkv")):
        raise MediaError("Segments already exist; refused to overwrite")
    usage = __import__("shutil").disk_usage(directory)
    if usage.free < 200 * 1024 * 1024:
        raise MediaError("Less than 200 MB free disk space")
    proc = subprocess.Popen(_synthetic_command(duration, segments), stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=(directory / "ffmpeg.log").open("ab"))
    try:
        while proc.poll() is None:
            if stop_requested():
                proc.stdin.write(b"q\n")
                proc.stdin.flush()
                break
            on_tick()
            time.sleep(.5)
        try:
            returncode = proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            proc.terminate()
            proc.wait(timeout=10)
            raise MediaError("FFmpeg stopped responding")
        if returncode != 0:
            raise MediaError(f"FFmpeg exited with code {returncode}; see ffmpeg.log")
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()

def dhash(frame: np.ndarray) -> int:
    gray = cv2.cvtColor(cv2.resize(frame, (9, 8)), cv2.COLOR_BGR2GRAY)
    bits = gray[:, 1:] > gray[:, :-1]
    value = 0
    for bit in bits.flatten():
        value = (value << 1) | int(bit)
    return value

def slide_candidates(video_file: Path, out_dir: Path, sample_seconds: float = 2, max_slides: int = 800) -> list[dict]:
    """Find changed, visually distinct slides. OCR runs separately."""
    out_dir.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(str(video_file))
    if not cap.isOpened():
        raise MediaError("OpenCV could not open recorded video")
    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps <= 0:
        cap.release()
        raise MediaError("Video FPS could not be read")
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    step = max(1, round(fps * sample_seconds))
    prev_frame = None
    hashes = []
    result = []
    try:
        for frame_no in range(0, total, step):
            if len(result) >= max_slides:
                break
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_no)
            success, frame = cap.read()
            if not success:
                continue
            small = cv2.resize(frame, (320, 180))
            if prev_frame is not None:
                difference = float(np.mean(cv2.absdiff(prev_frame, small)))
                if difference < 15.0:
                    continue
            prev_frame = small
            fingerprint = dhash(frame)
            mean_color = np.mean(small, axis=(0, 1))
            # dHash ignores uniform background colors; avoid conflating distinct slides.
            if any((fingerprint ^ prev_hash).bit_count() <= 6 and
                   float(np.linalg.norm(mean_color - prev_color)) < 22
                   for prev_hash, prev_color in hashes):
                continue
            hashes.append((fingerprint, mean_color))
            filename = f"slide_{len(result)+1:04d}.jpg"
            output = out_dir / filename
            if not cv2.imwrite(str(output), frame, [cv2.IMWRITE_JPEG_QUALITY, 93]):
                raise MediaError("Failed to save slide")
            result.append({"time_seconds": round(frame_no / fps, 2), "image_name": filename, "ocr_text": ""})
    finally:
        cap.release()
    return result

def run_ocr(slides: list[dict], out_dir: Path) -> list[dict]:
    import pytesseract
    for slide in slides:
        try:
            with Image.open(out_dir / slide["image_name"]) as image:
                slide["ocr_text"] = pytesseract.image_to_string(image, lang=settings().ocr_lang).strip()
        except Exception as e:
            slide["ocr_text"] = ""
            slide["ocr_error"] = str(e)[:150]
    return slides

def video_health(video_file: Path) -> dict:
    cap = cv2.VideoCapture(str(video_file))
    duration = float(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0) / max(cap.get(cv2.CAP_PROP_FPS), 1)
    dark, still, samples = 0, 0, 0
    previous = None
    try:
        for sec in range(0, int(duration), 10):
            cap.set(cv2.CAP_PROP_POS_MSEC, 1000 * sec)
            ok, frame = cap.read()
            if not ok:
                continue
            gray = cv2.cvtColor(cv2.resize(frame, (160, 90)), cv2.COLOR_BGR2GRAY)
            samples += 1
            dark += int(float(gray.mean()) < 8)
            if previous is not None and float(np.mean(cv2.absdiff(previous, gray))) < 1.0:
                still += 1
            previous = gray
    finally:
        cap.release()
    return {"samples": samples, "black_sample_ratio": round(dark / max(samples, 1), 3), "unchanged_sample_ratio": round(still / max(samples-1, 1), 3), "warning": "No visible motion in samples (may be static lecture slides)" if samples > 3 and still / max(samples-1, 1) > .95 else None}


# --- automatic cut of silent start, end and pauses -------------------------------------------------

def silence_intervals(path: Path, noise_db: float, min_seconds: float) -> list[tuple[float, float]]:
    """Silent stretches (audio below noise_db for at least min_seconds) as (start, end) in seconds."""
    proc = subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", "-i", str(path), "-vn", "-af",
                           f"silencedetect=noise={noise_db}dB:d={min_seconds}", "-f", "null", "-"],
                          capture_output=True, text=True, timeout=7200)
    if proc.returncode:
        raise MediaError("silencedetect failed: " + proc.stderr[-500:])
    intervals, start = [], None
    for line in proc.stderr.splitlines():
        if "silence_start:" in line:
            start = float(line.split("silence_start:")[1].split()[0])
        elif "silence_end:" in line and start is not None:
            end = float(line.split("silence_end:")[1].split()[0])
            intervals.append((max(0.0, start), end))
            start = None
    if start is not None:   # silence lasting until the end of the file
        intervals.append((max(0.0, start), float("inf")))
    return intervals


def plan_cut(duration: float, silences: list[tuple[float, float]], edge: float, pause: float,
             pad: float) -> list[tuple[float, float]] | None:
    """Parts to keep. None = nothing worth cutting. [] = (almost) everything is silent."""
    removed: list[tuple[float, float]] = []
    for start, end in silences:
        end = min(end, duration)
        length = end - start
        at_start, at_end = start <= 1.0, end >= duration - 1.0
        if at_start and at_end:
            return []
        if at_start and length >= edge:
            removed.append((0.0, end - pad))
        elif at_end and length >= edge:
            removed.append((start + pad, duration))
        elif length >= pause:
            removed.append((start + pad, end - pad))
    if not removed:
        return None
    keep, cursor = [], 0.0
    for start, end in sorted(removed):
        if start > cursor:
            keep.append((round(cursor, 3), round(start, 3)))
        cursor = max(cursor, end)
    if cursor < duration:
        keep.append((round(cursor, 3), round(duration, 3)))
    return [(a, b) for a, b in keep if b - a >= 1.0]


def apply_cut(source: Path, target: Path, keep: list[tuple[float, float]], workdir: Path) -> None:
    """Stream-copy the kept parts (cuts snap to keyframes, every 2 s in our recordings) and concatenate."""
    workdir.mkdir(parents=True, exist_ok=True)
    parts = []
    try:
        for i, (start, end) in enumerate(keep):
            part = workdir / f"part_{i:03d}.mp4"
            proc = subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", "-y", "-loglevel", "error",
                                   "-ss", f"{start:.3f}", "-to", f"{end:.3f}", "-i", str(source),
                                   "-c", "copy", "-avoid_negative_ts", "make_zero", str(part)],
                                  capture_output=True, text=True, timeout=3600)
            if proc.returncode or not part.is_file():
                raise MediaError("cut failed: " + proc.stderr[-500:])
            parts.append(part)
        listing = workdir / "parts.ffconcat"
        listing.write_text("ffconcat version 1.0\n" + "".join(_safe_concat_name(p) for p in parts), encoding="utf-8")
        temp = target.with_suffix(".partial.mp4")
        proc = subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", "-y", "-loglevel", "error", "-safe", "0",
                               "-f", "concat", "-i", str(listing), "-c", "copy", "-movflags", "+faststart", str(temp)],
                              capture_output=True, text=True, timeout=5400)
        if proc.returncode:
            temp.unlink(missing_ok=True)
            raise MediaError("cut concat failed: " + proc.stderr[-500:])
        verify_media(temp)
        temp.replace(target)
    finally:
        for part in parts:
            part.unlink(missing_ok=True)
        (workdir / "parts.ffconcat").unlink(missing_ok=True)
        try:
            workdir.rmdir()
        except OSError:
            pass


def auto_cut(directory: Path) -> dict:
    """Cut silent start, end and long pauses. original.mp4 keeps the uncut recording; recording.mp4 becomes
    the cut version. Re-processing starts again from original.mp4. Returns a summary for metadata/notes."""
    cfg = settings()
    final, original = directory / "recording.mp4", directory / "original.mp4"
    if not cfg.cut_enabled:
        return {"status": "disabled"}
    source = original if original.is_file() else final
    duration = verify_media(source)["duration_seconds"]
    silences = silence_intervals(source, cfg.cut_silence_db, min(cfg.cut_edge_seconds, cfg.cut_pause_seconds))
    keep = plan_cut(duration, silences, cfg.cut_edge_seconds, cfg.cut_pause_seconds, cfg.cut_pad_seconds)
    kept = sum(b - a for a, b in keep) if keep else 0.0
    if keep is not None and (kept < 60 or kept < 0.05 * duration):
        if original.is_file():   # keep the full recording visible
            original.replace(final)
        return {"status": "mostly_silent", "original_seconds": round(duration, 1),
                "audible_seconds": round(kept, 1)}
    if keep is None:
        if original.is_file():
            original.replace(final)
        return {"status": "nothing_to_cut", "original_seconds": round(duration, 1)}
    if not original.is_file():
        final.replace(original)
    apply_cut(original, final, keep, directory / "cut-parts")
    removed = duration - verify_media(final)["duration_seconds"]
    return {"status": "cut", "original_seconds": round(duration, 1), "removed_seconds": round(removed, 1),
            "cuts": len([1 for a, b in zip([(0, 0)] + keep, keep + [(duration, duration)]) if b[0] - a[1] > 0.5]),
            "kept": keep}
