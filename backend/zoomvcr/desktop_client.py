"""Authenticated client + conservative optical state detection for Zoom GUI."""
import io
import re
import time
import httpx
from PIL import Image
import pytesseract
from .config import settings

WAITING = re.compile(r'waiting room|please wait|host.*let you in|warteraum|bitte warten|gastgeber.*zulassen|meeting has not started|meeting.*noch nicht', re.I)
PREJOIN = re.compile(r"join meeting|join with computer audio|mit computeraudio teilnehmen|an meeting teilnehmen|meeting beitreten|passcode|kenncode|meeting id|sign in|anmelden", re.I)
IN_MEETING = re.compile(r'participants|teilnehmer|share screen|bildschirm freigeben|reaktionen|reactions|leave meeting|meeting verlassen|unmute|mute|stummschalten', re.I)


def classify_desktop_image(image_bytes: bytes) -> str:
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            image.thumbnail((1500, 900))
            content = pytesseract.image_to_string(image, lang='eng+deu')
    except Exception:
        return 'unknown'
    if WAITING.search(content):
        return 'waiting_room'
    if PREJOIN.search(content):
        return 'unknown'
    if IN_MEETING.search(content):
        return 'in_meeting_possible'
    return 'unknown'

class DesktopClient:
    def __init__(self):
        self.base_url = settings().desktop_agent_url.rstrip('/')
        self.token = settings().api_token

    def _request(self, method, path, data=None, timeout=15):
        try:
            with httpx.Client(timeout=timeout) as client:
                r = client.request(method, self.base_url + path,
                        headers={'Authorization': 'Bearer ' + self.token}, json=data)
                r.raise_for_status()
                if path == '/snapshot':
                    return r.content
                return r.json()
        except httpx.HTTPError as exc:
            raise RuntimeError('Desktop agent unavailable or rejected request: ' + str(exc)[:250]) from exc

    def health(self):
        return self._request('GET', '/health')

    def join(self, meeting_url, participant_name):
        return self._request('POST', '/join', {'meeting_url': meeting_url, 'participant_name': participant_name}, timeout=120)

    def ensure_name(self):
        return self._request('POST', '/display-name/ensure', timeout=35)

    def status(self):
        return self._request('GET', '/status')

    def frame(self):
        return self._request('GET', '/snapshot', timeout=10)

    def start(self, recording_id, ends_at):
        return self._request('POST', '/capture/start', {'recording_id': recording_id, 'ends_at': ends_at.isoformat()})

    def heartbeat(self):
        return self._request('POST', '/capture/heartbeat')

    def stop(self):
        return self._request('POST', '/capture/stop', timeout=40)

    def leave(self):
        return self._request('POST', '/leave', timeout=45)
