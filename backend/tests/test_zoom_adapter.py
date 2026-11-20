from pathlib import Path
import sys
import io
import os
from PIL import Image
import pytest

# Standalone desktop agent is copied into the isolated GUI image.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'zoomvcr'))
from zoomvcr.desktop_agent import validate_zoom_meeting_url, _command
from zoomvcr.desktop_client import classify_desktop_image
from zoomvcr.schemas import CreateRecording


def test_official_zoom_join_url():
    assert validate_zoom_meeting_url('https://us06web.zoom.us/j/12345678901?pwd=A%2BB') == 'zoommtg://zoom.us/join?action=join&confno=12345678901&pwd=A%2BB'


@pytest.mark.parametrize('url', [
    'http://zoom.us/j/12345678901',
    'https://evil-zoom.us/j/12345678901',
    'https://zoom.us.evil.com/j/12345678901',
    'https://zoom.us/j/12345678901@other.com',
    'https://zoom.us/j/hello',
    'https://zoom.us/admin',
    'https://zoom.us:444/j/12345678901',
])
def test_reject_malicious_join_urls(url):
    with pytest.raises(ValueError):
        validate_zoom_meeting_url(url)


def test_zoom_permission_requires_basis_and_both_confirmations():
    from datetime import datetime, timezone, timedelta
    future = datetime.now(timezone.utc) + timedelta(hours=2)
    core = dict(title='Arbeitsrecht', source='desktop_manual', participant_name='Kanzlei Muster – Aufzeichnungsdienst', meeting_url='https://zoom.us/j/12345678901',
                scheduled_at=future, duration_minutes=180)
    with pytest.raises(ValueError):
        CreateRecording(**core)
    with pytest.raises(ValueError):
        CreateRecording(**core, authorization_basis='written_consent',
                        permission_confirmed=True, disclosure_acknowledged=True)
    obj = CreateRecording(**core, authorization_basis='written_consent',
                          authorization_reference='Freigabe E-Mail 05.11.2026',
                          permission_confirmed=True, disclosure_acknowledged=True)
    assert obj.authorization_reference.startswith('Freigabe')
    assert CreateRecording(**core, authorization_basis='host', permission_confirmed=True,
                           disclosure_acknowledged=True).duration_minutes == 180


def test_ffmpeg_capture_configuration():
    args = _command()
    assert 'x11grab' in args and 'pulse' in args
    assert 'libx264' in args and 'aac' in args
    assert '-segment_time' in args
    assert '-nostdin' not in args  # required so STOP can send q


def test_ambiguous_screenshot_must_not_count_as_admission():
    image = Image.new('RGB', (800, 400), 'white')
    output = io.BytesIO()
    image.save(output, format='JPEG')
    assert classify_desktop_image(output.getvalue()) == 'unknown'


def test_audio_dialog_button_found_by_colour():
    """Blue filled button is found; blue link text below (short runs) is ignored."""
    from PIL import Image, ImageDraw
    from zoomvcr.desktop_agent import find_blue_button
    img = Image.new('RGB', (1280, 720), (255, 255, 255))
    d = ImageDraw.Draw(img)
    d.rectangle([524, 298, 755, 327], fill=(14, 113, 235))      # button
    for x in range(560, 720, 6):                                  # dotted link text
        d.rectangle([x, 340, x + 3, 350], fill=(14, 113, 235))
    x, y = find_blue_button(img, 355, 120, 925, 548)
    assert 524 <= x <= 755 and 298 <= y <= 327
    assert find_blue_button(Image.new('RGB', (1280, 720), 'white'), 0, 0, 1280, 720) is None


def test_blue_buttons_found_despite_white_label():
    """Label text splits the blue rows; the button box must still cover the full height (OCR crop)."""
    from PIL import Image, ImageDraw
    from zoomvcr.desktop_agent import find_blue_buttons
    img = Image.new('RGB', (1280, 720), (40, 40, 40))
    d = ImageDraw.Draw(img)
    d.rectangle([851, 397, 907, 428], fill=(14, 113, 235))       # small 'OK' notice button
    d.rectangle([868, 405, 880, 420], fill=(255, 255, 255))      # 'O'
    d.rectangle([884, 405, 892, 420], fill=(255, 255, 255))      # 'K'
    d.rectangle([524, 298, 755, 327], fill=(14, 113, 235))       # wide audio button
    for x in range(560, 720, 6):                                   # blue link text: too low to count
        d.rectangle([x, 340, x + 3, 350], fill=(14, 113, 235))
    found = sorted(find_blue_buttons(img), key=lambda b: b[2])
    assert len(found) == 2
    (ox, oy, ow, oh), (jx, jy, jw, jh) = found
    assert 851 <= ox <= 907 and oh >= 30 and ow == 57
    assert 524 <= jx <= 755 and jw == 232


def test_button_labels_and_repair_order():
    from PIL import Image
    from zoomvcr import desktop_agent as da
    assert da.classify_button('a OK -') == 'notice'
    assert da.classify_button('0K') == 'notice'
    assert da.classify_button('Join with Computer Audio') == 'join_audio'
    assert da.classify_button('Unmute') is None and da.classify_button('Leave') is None
    img = Image.new('RGB', (100, 100))
    clicks = []
    da_click, da_find = da._click, da.find_blue_buttons
    try:
        da._click = lambda env, x, y: clicks.append((x, y))
        da.find_blue_buttons = lambda img: [(640, 312, 232, 30), (879, 413, 57, 32), (300, 300, 80, 30)]
        labels = {232: 'Join with Computer Audio', 57: 'OK', 80: 'Unmute'}
        read = lambda img, cx, cy, bw, bh: labels[bw]
        # a notice covering the dialog is acknowledged first, unknown buttons are never clicked
        assert da.repair_audio(img, True, False, env={}, read_text=read) == 'notice_acknowledged'
        assert clicks == [(879, 413)]
        labels[57] = 'Leave'
        assert da.repair_audio(img, True, False, env={}, read_text=read) == 'computer_audio_clicked'
        assert clicks[-1] == (640, 312)
    finally:
        da._click, da.find_blue_buttons = da_click, da_find


def test_voice_engine_detection():
    from zoomvcr.desktop_agent import voice_engine_active
    joined = 'Sink Input #2\n\tProperties:\n\t\tapplication.name = "ZOOM VoiceEngine"\n'
    assert voice_engine_active(joined) is True
    assert voice_engine_active('') is False
