"""Recording-specific display names and conservative Zoom GUI verification.

Zoom's undocumented zoommtg `uname` URI field may be ignored (especially while
signed in). A requested name is never treated as verified merely because it was
supplied in a link. OCR verification requires Zoom's own *self* row.
"""
import re
import unicodedata

DEFAULT_NAME = 'Kanzlei – Aufzeichnung'
SELF_SUFFIX = re.compile(r'\(\s*(?:me|ich|you|du|moi)\s*\)', re.I)
ROLE_SUFFIX = re.compile(r'\(\s*(?:host|co-host|gastgeber|moderator|organizer)\s*\)', re.I)


def check_display_name(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError('Ein Zoom-Teilnehmername ist erforderlich')
    if any(unicodedata.category(char) in {'Cc', 'Cf', 'Cs', 'Zl', 'Zp'} for char in value):
        raise ValueError('Der Zoom-Teilnehmername enthält unzulässige Steuerzeichen')
    result = value.strip()
    if not 1 <= len(result) <= 80:
        raise ValueError('Der Zoom-Teilnehmername muss 1 bis 80 Zeichen enthalten')
    if any(unicodedata.category(char) in {'Cc', 'Cf', 'Cs', 'Zl', 'Zp'} for char in result):
        raise ValueError('Der Zoom-Teilnehmername enthält unzulässige Steuerzeichen')
    if len(result.split()) == 0:
        raise ValueError('Ein Zoom-Teilnehmername ist erforderlich')
    return result


def _normalize(text: str) -> str:
    text = unicodedata.normalize('NFKD', text)
    text = ''.join(ch for ch in text if not unicodedata.combining(ch))
    return ''.join(ch for ch in text.casefold() if ch.isalnum())


def name_visible_on_self_row(ocr_text: str, expected: str) -> bool:
    """Require self indicator on same row as requested name, not a random attendee.

    This is a *positive* check only; OCR negatives are unverified, never proof
    that the participant has the wrong name.
    """
    expected = _normalize(check_display_name(expected))
    for line in ocr_text.splitlines():
        marker = SELF_SUFFIX.search(line)
        own_name = ROLE_SUFFIX.sub('', SELF_SUFFIX.sub('', line))
        if marker and expected == _normalize(own_name):
            return True
    return False
