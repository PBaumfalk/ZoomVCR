import uuid
import os
import subprocess
from pathlib import Path
from zoomvcr.config import settings
from zoomvcr.media import record_synthetic, merge_segments, verify_media, slide_candidates, run_ocr


def test_synthetic_three_slides_with_audio(tmp_path, monkeypatch):
    monkeypatch.setenv('ZOOMVCR_STORAGE_ROOT', str(tmp_path))
    monkeypatch.setenv('ZOOMVCR_RECORD_SEGMENT_SECONDS', '3')
    settings.cache_clear()
    rid = str(uuid.uuid4())
    record_synthetic(rid, 9)
    directory = tmp_path / rid
    metadata = merge_segments(directory)
    assert metadata['duration_seconds'] >= 8
    assert {s['codec_type'] for s in metadata['streams']} == {'video', 'audio'}
    slides = slide_candidates(directory/'recording.mp4', directory/'slides', sample_seconds=1)
    assert len(slides) >= 3, slides
    slides = run_ocr(slides, directory/'slides')
    assert any('FOLIE' in s['ocr_text'] for s in slides)
    settings.cache_clear()
