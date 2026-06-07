"""iCloud-сторона через Apple Notes.app (AppleScript). Apple авто-синкает в облако.

Доказано Phase 0: list/create/update/delete работают через osascript. body=HTML,
canon body_text=strip-HTML, ext_id=note id (x-coredata://.../ICNote/pNNN).
"""
import html
import re
import subprocess

from ihonor.note import Note

US = "\x1f"  # field sep
RS = "\x1e"  # record sep


def _osa(script: str) -> str:
    return subprocess.run(
        ["osascript", "-e", script], capture_output=True, text=True, check=True
    ).stdout


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _strip_html(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", s)
    return html.unescape(re.sub(r"\s+", " ", s)).strip()


class ICloudAdapter:
    """NoteAdapter поверх Apple Notes.app."""

    def list(self) -> list[Note]:
        script = (
            'tell application "Notes"\n'
            f'set AppleScript\'s text item delimiters to "{US}"\n'
            'set out to ""\n'
            'repeat with n in notes\n'
            f'set out to out & (id of n) & "{US}" & (name of n) & "{US}" & (body of n) & "{RS}"\n'
            'end repeat\n'
            'return out\n'
            'end tell'
        )
        raw = _osa(script)
        notes = []
        for rec in raw.split(RS):
            if US not in rec:
                continue
            parts = rec.split(US)
            if len(parts) < 3:
                continue
            nid, name, body = parts[0], parts[1], US.join(parts[2:])
            notes.append(Note(nid.strip(), name, _strip_html(body), 0, False))
        return notes

    def get(self, ext_id: str) -> Note | None:
        for n in self.list():
            if n.ext_id == ext_id:
                return n
        return None

    def _body_html(self, note: Note) -> str:
        return (
            f"<div><b>{html.escape(note.title)}</b></div>"
            f"<div>{html.escape(note.body_text)}</div>"
        )

    def create(self, note: Note) -> str:
        script = (
            'tell application "Notes"\n'
            f'set n to make new note with properties {{name:"{_esc(note.title)}", '
            f'body:"{_esc(self._body_html(note))}"}}\n'
            'return id of n\n'
            'end tell'
        )
        return _osa(script).strip()

    def update(self, ext_id: str, note: Note) -> None:
        script = (
            'tell application "Notes"\n'
            f'set body of note id "{_esc(ext_id)}" to "{_esc(self._body_html(note))}"\n'
            'end tell'
        )
        _osa(script)

    def delete(self, ext_id: str) -> None:
        _osa(f'tell application "Notes" to delete (notes whose id is "{_esc(ext_id)}")')
