"""Conservative Zoom Linux GUI name verification/renaming (experimental).

Only click on menu items positively identified by OCR. Never infer that the
undocumented zoommtg uname URI argument was applied. Requires an active meeting,
Xvfb, xdotool, xclip and tesseract on the isolated desktop.
"""
from __future__ import annotations
import io
import re
import subprocess
import time
from PIL import Image
import pytesseract
try:
    from .display_name import check_display_name, name_visible_on_self_row
except ImportError:  # standalone agent image
    from display_name import check_display_name, name_visible_on_self_row

SELF = re.compile(r'\(\s*(me|ich|you|du|moi)\s*\)', re.I)


def _run(*args, timeout=5, input=None):
    return subprocess.run(list(args), check=True, input=input, capture_output=True, timeout=timeout)


def _image(snapshot_fn):
    return Image.open(io.BytesIO(snapshot_fn())).convert('RGB')


def _lines(image):
    """Grouped OCR words and their screen-coordinate bounding boxes."""
    data = pytesseract.image_to_data(image, lang='eng+deu', output_type=pytesseract.Output.DICT)
    groups = {}
    for i, value in enumerate(data['text']):
        if not value.strip():
            continue
        key = (data['block_num'][i], data['par_num'][i], data['line_num'][i])
        groups.setdefault(key, []).append((value, data['left'][i], data['top'][i], data['width'][i], data['height'][i]))
    result=[]
    for words in groups.values():
        left=min(w[1] for w in words)
        top=min(w[2] for w in words)
        right=max(w[1]+w[3] for w in words)
        bottom=max(w[2]+w[4] for w in words)
        result.append({'text': ' '.join(w[0] for w in words), 'x': (left+right)//2,
                       'y': (top+bottom)//2, 'left': left, 'right': right})
    return result


def _self_line(lines):
    for line in lines:
        if SELF.search(line['text']):
            return line
    return None


def _find(lines, pattern):
    matcher=re.compile(pattern, re.I)
    return next((line for line in lines if matcher.search(line['text'])), None)


def _focus_meeting():
    # Zoom window titles can differ; do not activate an arbitrary other window.
    result=subprocess.run(['xdotool','search','--onlyvisible','--name','Zoom Meeting'],
                          capture_output=True, text=True, timeout=3)
    if result.returncode:
        return False
    ids=[s for s in result.stdout.splitlines() if s.strip().isdigit()]
    if not ids:
        return False
    _run('xdotool', 'windowactivate', '--sync', ids[-1])
    return True


def _click(line):
    _run('xdotool','mousemove','--sync',str(line['x']),str(line['y']))
    _run('xdotool','click','--clearmodifiers','1')


def inspect_self_name(snapshot_fn, requested_name, open_panel=True):
    """Returns verified only if the requested name is in Zoom's own row."""
    requested_name=check_display_name(requested_name)
    image=_image(snapshot_fn)
    if name_visible_on_self_row(pytesseract.image_to_string(image, lang='eng+deu'), requested_name):
        return {'status':'verified','method':'participant_panel_ocr'}
    if open_panel and _focus_meeting():
        # Linux Zoom documents Alt+U as the participants-panel shortcut.
        _run('xdotool','key','--clearmodifiers','alt+u')
        time.sleep(0.8)
        image=_image(snapshot_fn)
        if name_visible_on_self_row(pytesseract.image_to_string(image,lang='eng+deu'),requested_name):
            return {'status':'verified','method':'participant_panel_ocr'}
    return {'status':'unverified','method':'participant_panel_ocr',
            'note':'Exact display name on the self row could not be verified. Inspect the participant list over private VNC.'}


def try_rename_self(snapshot_fn, requested_name):
    """Best-effort rename via explicitly recognized menu items.

    A failed/ambiguous screenshot results in manual_required; no blind clicking.
    For non-Latin text the clipboard is used rather than keyboard keycodes.
    """
    requested_name=check_display_name(requested_name)
    if not _focus_meeting():
        return {'status':'manual_required','note':'Meeting window unavailable; check Zoom using private VNC'}
    image=_image(snapshot_fn)
    rows=_lines(image)
    self_row=_self_line(rows)
    if not self_row:
        _run('xdotool','key','--clearmodifiers','alt+u')
        time.sleep(0.8)
        rows=_lines(_image(snapshot_fn))
        self_row=_self_line(rows)
    if not self_row:
        return {'status':'manual_required','note':'Self participant row not found; rename manually through Zoom participants panel'}
    # Only operate on the self row, and only click an OCR-confirmed More control.
    _run('xdotool','mousemove','--sync',str(self_row['right']+55),str(self_row['y']))
    time.sleep(1)
    controls=_lines(_image(snapshot_fn))
    more=next((line for line in controls if re.search(r'\b(more|mehr)\b',line['text'],re.I)
               and abs(line['y']-self_row['y'])<65 and line['x']>self_row['right']),None)
    if not more:
        return {'status':'manual_required','note':'Zoom More button cannot be located safely by OCR'}
    _click(more)
    time.sleep(0.6)
    rename=_find(_lines(_image(snapshot_fn)),r'\b(rename|umbenennen)\b')
    if not rename:
        return {'status':'manual_required','note':'Zoom has not provided the Rename option'}
    _click(rename)
    time.sleep(0.5)
    dialog_lines=_lines(_image(snapshot_fn))
    if not _find(dialog_lines,r'\b(rename|umbenennen)\b') or not _find(dialog_lines,r'\b(change|speichern|ändern|rename)\b'):
        return {'status':'manual_required','note':'Rename dialog could not be positively identified'}
    # The Zoom rename dialog focuses the text box by default on supported builds.
    # If it does not, verification below fails closed rather than claiming success.
    _run('xclip','-selection','clipboard',input=requested_name.encode('utf-8'))
    _run('xdotool','key','--clearmodifiers','ctrl+a')
    _run('xdotool','key','--clearmodifiers','ctrl+v')
    _run('xdotool','key','--clearmodifiers','Return')
    time.sleep(1)
    verified=inspect_self_name(snapshot_fn,requested_name,open_panel=False)
    if verified['status']=='verified':
        return {**verified,'method':'zoom_gui_rename_and_ocr'}
    return {'status':'manual_required','note':'Rename attempted but current participant name is not verified; inspect using VNC'}
