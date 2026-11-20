"""Isolated Zoom desktop agent (runs inside a graphical Docker container).

This uses the normal Linux Zoom client. It intentionally does not impersonate
attendance or certify meeting attendance. It acknowledges Zoom's informational
notices (e.g. "This meeting is being recorded ... OK") and keeps the client joined
to computer audio, because a covered audio dialog silently ruins a recording.
The operator must confirm authorization in the main application.
"""
import hmac
from contextlib import asynccontextmanager
import os
import re
import shutil
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator
try:
    from .display_name import check_display_name, name_visible_on_self_row
    from .zoom_name_gui import inspect_self_name, try_rename_self
except ImportError:  # standalone desktop image
    from display_name import check_display_name, name_visible_on_self_row
    from zoom_name_gui import inspect_self_name, try_rename_self

AGENT_TOKEN = os.environ.get('ZOOMVCR_API_TOKEN', '')
RECORDINGS = Path(os.environ.get('ZOOMVCR_STORAGE_ROOT', '/data/recordings'))
DISPLAY = os.environ.get('DISPLAY', ':99')
PULSE_MONITOR = os.environ.get('ZOOMVCR_PULSE_MONITOR', 'ZoomVCR.monitor')
SEGMENT = int(os.environ.get('ZOOMVCR_RECORD_SEGMENT_SECONDS', '60'))
WIDTH = int(os.environ.get('ZOOMVCR_DESKTOP_WIDTH', '1920'))
HEIGHT = int(os.environ.get('ZOOMVCR_DESKTOP_HEIGHT', '1080'))
FPS = int(os.environ.get('ZOOMVCR_DESKTOP_FPS', '15'))
@asynccontextmanager
async def lifespan(app):
    threading.Thread(target=_watchdog_loop, name='capture-watchdog', daemon=True).start()
    yield

app = FastAPI(title='ZoomVCR Desktop Agent', docs_url=None, redoc_url=None, lifespan=lifespan)
_lock = threading.RLock()
_zoom_process = None
_ffmpeg_process = None
_current_id = None
_join_at = None
_started_at = None
_last_error = None
_lease_at = None
_capture_deadline = None
_requested_name = None
_name_status = "not_requested"
_name_error = None
_name_rename_attempted = False

class JoinRequest(BaseModel):
    meeting_url: str = Field(min_length=15, max_length=1200)
    participant_name: str = Field(min_length=1, max_length=80)

    @field_validator('participant_name')
    @classmethod
    def valid_name(cls, value):
        return check_display_name(value)

class CaptureRequest(BaseModel):
    recording_id: str = Field(pattern=r'^[0-9a-fA-F-]{36}$')
    ends_at: datetime



def validate_zoom_meeting_url(value: str, participant_name: str | None = None) -> str:
    """Accept only official HTTPS zoom.us join links and turn them into a Zoom URI.

    Never fetch or browse user-supplied URLs (SSRF mitigation). Zoom encrypted
    join passcodes (`pwd`) from the invite link are retained as URL parameters.
    """
    parsed = urlparse(value)
    host = (parsed.hostname or '').lower()
    if (parsed.scheme != 'https' or parsed.username or parsed.password or parsed.port or
            not (host == 'zoom.us' or host.endswith('.zoom.us'))):
        raise ValueError('Expected an HTTPS zoom.us meeting URL')
    match = re.fullmatch(r'/(?:j|w)/([0-9]{9,13})/?', parsed.path)
    if not match:
        raise ValueError('Zoom link must use /j/<meeting-id> or /w/<meeting-id>')
    params = parse_qs(parsed.query)
    query = {'action': 'join', 'confno': match.group(1)}
    if params.get('pwd'):
        query['pwd'] = params['pwd'][0]
    if participant_name is not None:
        # Zoom's uname URI argument is experimental and may be ignored while signed in.
        # Recording must not assume success until actual participant name is checked.
        query['uname'] = check_display_name(participant_name)
    return 'zoommtg://zoom.us/join?' + urlencode(query)


def authorized(request: Request):
    token = request.headers.get('authorization', '').removeprefix('Bearer ')
    if len(AGENT_TOKEN) < 24 or not hmac.compare_digest(token, AGENT_TOKEN):
        raise HTTPException(401, 'Agent authentication required')


def zoom_running() -> bool:
    if _zoom_process is not None and _zoom_process.poll() is None:
        return True
    # Ignore zombie (<defunct>) processes: a crashed Zoom client must not count as running.
    for stat in Path('/proc').glob('[0-9]*/stat'):
        try:
            text = stat.read_text()
        except OSError:
            continue
        name = text[text.find('(') + 1:text.rfind(')')]
        state = text[text.rfind(')') + 2:text.rfind(')') + 3]
        if name == 'zoom' and state not in ('Z', 'X'):
            return True
    return False


def _command() -> list[str]:
    return ['ffmpeg', '-hide_banner', '-loglevel', 'warning', '-y',
            '-thread_queue_size', '1024', '-f', 'x11grab', '-framerate', str(FPS),
            '-video_size', f'{WIDTH}x{HEIGHT}', '-i', DISPLAY + '.0',
            '-thread_queue_size', '1024', '-f', 'pulse', '-i', PULSE_MONITOR,
            '-map', '0:v:0', '-map', '1:a:0', '-c:v', 'libx264', '-preset', 'veryfast',
            '-crf', '24', '-pix_fmt', 'yuv420p', '-g', str(FPS * 2),
            '-c:a', 'aac', '-b:a', '128k', '-ar', '48000', '-ac', '2',
            '-force_key_frames', f'expr:gte(t,n_forced*{SEGMENT})',
            '-f', 'segment', '-segment_time', str(SEGMENT),
            '-reset_timestamps', '1', '-segment_format', 'matroska']


def _is_recording():
    return _ffmpeg_process is not None and _ffmpeg_process.poll() is None


@app.get('/health')
def health(request: Request):
    authorized(request)
    return {'status': 'ok', 'display_socket': Path('/tmp/.X11-unix/X99').exists(),
            'ffmpeg_installed': shutil.which('ffmpeg') is not None,
            'zoom_installed': shutil.which('zoom') is not None,
            'zoom_running': zoom_running()}


AUDIO_DIALOG_TITLE = 'audio conference options'
_audio_join_status = 'not_started'


def _visible_windows(title: str) -> list[str]:
    try:
        out = subprocess.run(['xdotool', 'search', '--onlyvisible', '--name', title], capture_output=True,
                             text=True, timeout=5, env={**os.environ, 'DISPLAY': DISPLAY}).stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    return [line.strip() for line in out.splitlines() if line.strip()]


def find_blue_button(img, left: int, top: int, right: int, bottom: int, min_run: int = 120):
    """Centre of the tallest band of rows with a long run of Zoom-primary-blue pixels inside the box
    (= the filled 'Join with Computer Audio' button; the blue link text below never reaches min_run)."""
    rgb = img.convert('RGB')
    w, h = rgb.size
    left, top, right, bottom = max(0, left), max(0, top), min(w, right), min(h, bottom)
    px = rgb.load()
    rows = []
    for y in range(top, bottom):
        xs = [x for x in range(left, right)
              if px[x, y][2] > 190 and px[x, y][0] < 80 and 80 < px[x, y][1] < 160]
        if len(xs) >= min_run:
            rows.append((y, xs))
    if not rows:
        return None
    bands, cur = [], [rows[0]]
    for row in rows[1:]:
        if row[0] == cur[-1][0] + 1:
            cur.append(row)
        else:
            bands.append(cur)
            cur = [row]
    bands.append(cur)
    band = max(bands, key=len)
    xs = [x for row in band for x in row[1]]
    return (sum(xs) // len(xs), (band[0][0] + band[-1][0]) // 2)


VOICE_ENGINE = 'ZOOM VoiceEngine'   # PulseAudio stream Zoom opens only while joined to computer audio
NOTICE_LABELS = ('ok', 'okay', 'got it', 'continue', 'close', 'dismiss')
_guard_generation = 0
_audio_missing_since = None


def voice_engine_active(pactl_output: str | None = None) -> bool:
    """True while Zoom plays meeting audio into PulseAudio (= joined with computer audio)."""
    if pactl_output is None:
        try:
            pactl_output = subprocess.run(['pactl', 'list', 'sink-inputs'], capture_output=True, text=True,
                                          timeout=5).stdout
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
    return VOICE_ENGINE in pactl_output


def _is_zoom_blue(p) -> bool:
    return p[2] > 190 and p[0] < 80 and 80 < p[1] < 160


def find_blue_buttons(img, box=None, min_width: int = 30, min_height: int = 18, max_height: int = 60,
                      gap: int = 24) -> list[tuple[int, int, int, int]]:
    """All filled Zoom-blue buttons as (centre_x, centre_y, width, height). Runs of blue pixels in a row are
    merged across small gaps (white label text), rows are joined into boxes by horizontal overlap."""
    rgb = img.convert('RGB')
    w, h = rgb.size
    left, top, right, bottom = box or (0, 0, w, h)
    left, top, right, bottom = max(0, left), max(0, top), min(w, right), min(h, bottom)
    px = rgb.load()
    comps, active = [], []
    for y in range(top, bottom):
        runs, start, last = [], None, None
        for x in range(left, right):
            if _is_zoom_blue(px[x, y]):
                if start is None:
                    start = x
                elif x - last > gap:
                    runs.append((start, last))
                    start = x
                last = x
        if start is not None:
            runs.append((start, last))
        next_active = []
        for a, b in runs:
            if b - a + 1 < min_width:
                continue
            for comp in active:
                if comp[3] == y - 1 and a <= comp[1] and b >= comp[0]:
                    comp[0], comp[1], comp[3] = min(comp[0], a), max(comp[1], b), y
                    break
            else:
                comp = [a, b, y, y]
                comps.append(comp)
            next_active.append(comp)
        active = next_active
    return [((c[0] + c[1]) // 2, (c[2] + c[3]) // 2, c[1] - c[0] + 1, c[3] - c[2] + 1)
            for c in comps if min_height <= c[3] - c[2] + 1 <= max_height]


def classify_button(text: str) -> str | None:
    t = re.sub(r'[^a-z0-9 ]', ' ', text.lower().replace('0', 'o'))
    t = ' '.join(w for w in t.split() if len(w) > 1)   # drop stray glyphs from rounded corners
    if 'computer audio' in t or t.startswith('join with'):
        return 'join_audio'
    if t in NOTICE_LABELS:
        return 'notice'
    return None


def _button_text(img, cx: int, cy: int, bw: int, bh: int) -> str:
    import pytesseract
    # inset by the corner radius so the rounded corners do not turn into glyphs
    crop = img.convert('L').crop((cx - bw // 2 + 6, cy - bh // 2 + 4, cx + bw // 2 - 5, cy + bh // 2 - 3))
    crop = crop.point(lambda v: 0 if v > 180 else 255)   # white label on blue -> black on white
    crop = crop.resize((crop.width * 3, crop.height * 3))
    return pytesseract.image_to_string(crop, lang='eng', config='--psm 7')


def _toolbar_join_audio(env) -> tuple[int, int] | None:
    """Reveal Zoom's auto-hiding toolbar and locate its 'Join Audio' label (bottom left)."""
    import io
    import pytesseract
    from PIL import Image
    subprocess.run(['xdotool', 'mousemove', str(WIDTH // 2), str(HEIGHT - 120)], timeout=5, env=env)
    subprocess.run(['xdotool', 'mousemove', str(WIDTH // 2), str(HEIGHT - 50)], timeout=5, env=env)
    time.sleep(1.0)
    img = Image.open(io.BytesIO(_desktop_snapshot())).convert('L')
    top = HEIGHT - 110
    crop = img.crop((0, top, WIDTH // 3, HEIGHT))
    data = pytesseract.image_to_data(crop, lang='eng', output_type=pytesseract.Output.DICT)
    words = [(str(t).strip().lower(), data['left'][i], data['top'][i], data['width'][i], data['height'][i])
             for i, t in enumerate(data['text']) if str(t).strip()]
    for prev, cur in zip(words, words[1:]):
        if prev[0] == 'join' and cur[0].startswith('audio'):
            x0, x1 = prev[1], cur[1] + cur[3]
            return ((x0 + x1) // 2, top + cur[2] + cur[4] // 2)
    return None


def _click(env, x: int, y: int) -> None:
    subprocess.run(['xdotool', 'mousemove', str(x), str(y), 'click', '1'], timeout=5, env=env)


def repair_audio(img, dialog_open: bool, allow_toolbar: bool, env=None, read_text=None) -> str | None:
    """One repair step while Zoom is not joined to computer audio. Notices with an OK-type button may cover the
    audio dialog (07./08.11.2026: 'This meeting is being recorded ... OK'), so they are acknowledged first.
    Only buttons whose label is recognised are clicked."""
    env = env or {**os.environ, 'DISPLAY': DISPLAY}
    read_text = read_text or _button_text
    candidates = [b for b in find_blue_buttons(img) if b[2] <= 420][:10]
    labelled = [(classify_button(read_text(img, *b)), b) for b in candidates]
    for wanted, result in (('notice', 'notice_acknowledged'), ('join_audio', 'computer_audio_clicked')):
        for kind, b in labelled:
            if kind == wanted:
                _click(env, b[0], b[1])
                return result
    if not dialog_open and allow_toolbar:
        pos = _toolbar_join_audio(env)
        if pos:
            _click(env, *pos)
            return 'toolbar_join_audio_clicked'
    return None


def _audio_guard(generation: int, grace: float = 20.0) -> None:
    """Runs for the whole meeting: keeps Zoom joined to computer audio. Zoom asks for 'Join with Computer
    Audio' on every join, info notices can cover that dialog, and audio can drop mid-meeting. The PulseAudio
    stream of Zoom's voice engine is the ground truth; without it the recording is silent."""
    global _audio_join_status, _audio_missing_since
    import io
    from PIL import Image
    env = {**os.environ, 'DISPLAY': DISPLAY}
    started = time.monotonic()
    _audio_join_status, _audio_missing_since = 'waiting_for_audio', None
    while generation == _guard_generation and zoom_running():
        try:
            dialog = bool(_visible_windows(AUDIO_DIALOG_TITLE))
            if voice_engine_active() and not dialog:
                _audio_join_status, _audio_missing_since = 'computer_audio_joined', None
                time.sleep(5)
                continue
            if not dialog and not meeting_window_open():
                time.sleep(5)   # preview, waiting room or idle client: nothing to repair
                continue
            if _audio_missing_since is None:
                _audio_missing_since = time.monotonic()
            img = Image.open(io.BytesIO(_desktop_snapshot()))
            action = repair_audio(img, dialog, time.monotonic() - started > grace, env)
            _audio_join_status = action or 'audio_missing'
            print(f'audio guard: {_audio_join_status}', flush=True)
            time.sleep(3)
        except Exception as exc:  # the guard must never die during a recording
            _audio_join_status = 'guard_error'
            print(f'audio guard error: {type(exc).__name__}: {exc}', flush=True)
            time.sleep(5)


def _start_audio_guard() -> None:
    global _guard_generation
    _guard_generation += 1
    threading.Thread(target=_audio_guard, args=(_guard_generation,), name='audio-guard', daemon=True).start()


@app.post('/join')
def join(payload: JoinRequest, request: Request):
    authorized(request)
    global _zoom_process, _join_at, _last_error, _requested_name, _name_status, _name_error, _name_rename_attempted
    try:
        uri = validate_zoom_meeting_url(payload.meeting_url, payload.participant_name)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    with _lock:
        if _is_recording():
            raise HTTPException(409, 'Desktop is busy recording another meeting')
        if not shutil.which('zoom'):
            raise HTTPException(503, 'Official Zoom Linux client is not installed')
        # A meeting left over from an earlier recording would make Zoom ask "leave and join new?".
        if zoom_running() and meeting_window_open():
            _stop_zoom()
        # Zoom runs only for recordings (idle client costs about one CPU core): start it on demand.
        if not zoom_running():
            try:
                _launch_zoom()
            except OSError as exc:
                _last_error = str(exc)
                raise HTTPException(503, f'Cannot launch Zoom desktop: {exc}') from exc
        # Zoom desktop links are handed to its own URI handler; no browser automation.
        env = {**os.environ, 'DISPLAY': DISPLAY}
        try:
            _zoom_process = subprocess.Popen(['zoom', uri], env=env,
                                             stdin=subprocess.DEVNULL,
                                             stdout=subprocess.DEVNULL,
                                             stderr=subprocess.DEVNULL,
                                             start_new_session=True)
        except OSError as exc:
            _last_error = str(exc)
            raise HTTPException(503, f'Cannot launch Zoom desktop: {exc}') from exc
        _join_at = datetime.now(timezone.utc).isoformat()
        _last_error = None
        _start_audio_guard()
        _requested_name = payload.participant_name
        _name_status = "unverified"
        _name_error = "Zoom may ignore a requested display name; actual name not verified yet"
        _name_rename_attempted = False
        return {'status': 'launch_requested', 'zoom_running': zoom_running(),
                'requested_participant_name': _requested_name, 'participant_name_status': _name_status,
                'note': 'Zoom launch requested; membership and waiting-room admission cannot be confirmed from this response.'}


@app.get('/status')
def status(request: Request):
    authorized(request)
    with _lock:
        files = list((RECORDINGS / _current_id / 'segments').glob('*.mkv')) if _current_id else []
        return {'recording': _is_recording(), 'recording_id': _current_id,
                'ffmpeg_exit_code': _ffmpeg_process.poll() if _ffmpeg_process else None,
                'zoom_running': zoom_running(), 'join_requested_at': _join_at, 'audio_join': _audio_join_status,
                'audio_missing_seconds': round(time.monotonic() - _audio_missing_since) if _audio_missing_since else 0,
                'capture_started_at': _started_at, 'segment_count': len(files),
                'last_error': _last_error, 'connection_verified': False, 'watchdog_enabled': True,
                'requested_participant_name': _requested_name,
                'participant_name_status': _name_status, 'participant_name_note': _name_error}


@app.post('/capture/start')
def capture_start(payload: CaptureRequest, request: Request):
    authorized(request)
    global _ffmpeg_process, _current_id, _started_at, _last_error, _lease_at, _capture_deadline
    with _lock:
        if _is_recording():
            raise HTTPException(409, 'Capture is already running')
        if not zoom_running():
            raise HTTPException(409, 'Zoom client is not running')
        if not Path('/tmp/.X11-unix/X99').exists():
            raise HTTPException(503, 'Xvfb virtual display is unavailable')
        directory = RECORDINGS / payload.recording_id
        folder = directory / 'segments'
        folder.mkdir(parents=True, exist_ok=True)
        existing = sorted(folder.glob('segment_*.mkv'))
        if existing:
            raise HTTPException(409, 'Existing segments: will not overwrite previous recording')
        if shutil.disk_usage(folder).free < 1024 * 1024 * 1024:
            raise HTTPException(507, 'Less than 1 GiB free disk space')
        log_file = (directory / 'ffmpeg.log').open('ab')
        cmd = _command() + [str(folder / 'segment_%05d.mkv')]
        try:
            _ffmpeg_process = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                                               stdout=subprocess.DEVNULL, stderr=log_file,
                                               start_new_session=True)
        except OSError as exc:
            _last_error = str(exc)
            raise HTTPException(503, str(exc)) from exc
        finally:
            log_file.close()
        _current_id = payload.recording_id
        _started_at = datetime.now(timezone.utc).isoformat()
        _last_error = None
        _lease_at = time.monotonic()
        _capture_deadline = payload.ends_at.timestamp()
        if _capture_deadline <= time.time():
            _ffmpeg_process.terminate()
            raise HTTPException(409, 'Recording end must be in the future')
        time.sleep(0.8)
        if not _is_recording():
            _last_error = f'FFmpeg exited immediately with code {_ffmpeg_process.poll()}'
            raise HTTPException(503, _last_error + '; inspect ffmpeg.log')
        return {'status': 'recording', 'recording_id': _current_id}


@app.post('/capture/stop')
def capture_stop(request: Request):
    authorized(request)
    global _ffmpeg_process
    with _lock:
        if _ffmpeg_process is not None and _ffmpeg_process.poll() is None:
            try:
                _ffmpeg_process.stdin.write(b'q\n')
                _ffmpeg_process.stdin.flush()
                _ffmpeg_process.wait(timeout=20)
            except (OSError, subprocess.TimeoutExpired):
                _ffmpeg_process.terminate()
                try:
                    _ffmpeg_process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    _ffmpeg_process.kill()
                    _ffmpeg_process.wait()
        return {'status': 'stopped', 'exit_code': _ffmpeg_process.poll() if _ffmpeg_process else None}


MEETING_WINDOW_TITLES = ('^Meeting$', 'Zoom Meeting')   # Zoom 7.x: "Meeting"; older clients: "Zoom Meeting"


def meeting_window_open() -> bool:
    return any(_visible_windows(title) for title in MEETING_WINDOW_TITLES)


ZOOM_MAIN_WINDOW = 'Zoom Workplace'


def _launch_zoom(wait: float = 60.0) -> None:
    """Start the Zoom client and wait until its main window is up (the sign-in persists in the profile)."""
    global _zoom_process
    env = {**os.environ, 'DISPLAY': DISPLAY}
    _zoom_process = subprocess.Popen(['zoom'], env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL, start_new_session=True)
    end = time.monotonic() + wait
    while time.monotonic() < end:
        if _visible_windows(ZOOM_MAIN_WINDOW):
            time.sleep(3)   # let the client finish loading before it receives the join link
            return
        if not zoom_running():
            raise OSError('Zoom exited right after start')
        time.sleep(1)


def _stop_zoom() -> None:
    """Leave any meeting by ending the client. Alt+F4 asks hosts 'end or leave?' and the window title differs
    between Zoom versions; ending the process is deterministic. Zoom is started again for the next recording."""
    global _zoom_process, _guard_generation, _audio_missing_since
    _guard_generation += 1   # stops the audio guard of the previous meeting
    _audio_missing_since = None
    # Zoom opens survey/'restore session' pages in Firefox after meetings; they would pile up on the desktop.
    subprocess.run(['pkill', '-x', 'firefox'], timeout=5, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(['pkill', '-x', 'zoom'], timeout=5, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(20):
        if not zoom_running():
            break
        time.sleep(0.5)
    else:
        subprocess.run(['pkill', '-9', '-x', 'zoom'], timeout=5, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1)
    if _zoom_process is not None:
        try:
            _zoom_process.wait(timeout=2)   # reap: a zombie would count as running
        except subprocess.TimeoutExpired:
            pass
    _zoom_process = None


@app.post('/leave')
def leave(request: Request):
    authorized(request)
    if _is_recording():
        raise HTTPException(409, 'Stop the recording before leaving')
    with _lock:
        try:
            _stop_zoom()
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {'status': 'leave_manual', 'note': f'Leave the meeting from the private VNC desktop ({exc}).'}
    return {'status': 'left', 'meeting_window_open': meeting_window_open()}


def _desktop_snapshot() -> bytes:
    try:
        frame = subprocess.run(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error',
                                '-f', 'x11grab', '-video_size', f'{WIDTH}x{HEIGHT}',
                                '-i', DISPLAY + '.0', '-frames:v', '1', '-f', 'image2pipe',
                                '-vcodec', 'mjpeg', '-'], capture_output=True, timeout=8)
    except (OSError, subprocess.TimeoutExpired):
        raise HTTPException(503, 'Desktop screenshot unavailable')
    if frame.returncode != 0:
        raise HTTPException(503, 'Virtual display is unavailable')
    return frame.stdout


@app.get('/snapshot')
def snapshot(request: Request):
    authorized(request)
    return Response(_desktop_snapshot(), media_type='image/jpeg', headers={'Cache-Control': 'no-store'})



@app.post('/display-name/ensure')
def ensure_display_name(request: Request):
    authorized(request)
    global _name_status, _name_error, _name_rename_attempted
    with _lock:
        if not _requested_name:
            raise HTTPException(409, 'No display name has been requested for this session')
        if not zoom_running():
            raise HTTPException(409, 'Zoom is not running')
        try:
            outcome = inspect_self_name(_desktop_snapshot, _requested_name)
            if outcome['status'] != 'verified' and not _name_rename_attempted:
                _name_rename_attempted = True
                outcome = try_rename_self(_desktop_snapshot, _requested_name)
            _name_status = outcome['status']
            _name_error = outcome.get('note')
            return {'requested_participant_name':_requested_name, **outcome}
        except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
            _name_status = 'manual_required'
            _name_error = 'GUI verification not available: ' + str(exc)[:180]
            return {'requested_participant_name': _requested_name,
                    'status': 'manual_required', 'note':_name_error}

@app.post('/capture/heartbeat')
def capture_heartbeat(request: Request):
    authorized(request)
    global _lease_at
    with _lock:
        if not _is_recording():
            raise HTTPException(409, 'Capture is no longer running')
        _lease_at = time.monotonic()
        return {'status': 'lease_renewed'}


def _watchdog_loop():
    global _last_error
    while True:
        time.sleep(5)
        with _lock:
            if not _is_recording():
                continue
            overdue = _capture_deadline is not None and time.time() >= _capture_deadline
            lease_lost = _lease_at is not None and (time.monotonic() - _lease_at) > 35
            if overdue or lease_lost:
                _last_error = 'Scheduled end reached' if overdue else 'Capture worker heartbeat lost'
                # A fresh FFmpeg segment is playable only after a graceful close.
                try:
                    _ffmpeg_process.stdin.write(b'q\n')
                    _ffmpeg_process.stdin.flush()
                    _ffmpeg_process.wait(timeout=12)
                except (OSError, subprocess.TimeoutExpired):
                    _ffmpeg_process.terminate()

