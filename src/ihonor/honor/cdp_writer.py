"""HONOR Notes WRITE через управление HonorWorkStation по Chrome DevTools Protocol.

Прорыв Phase 0: внешний headless-write в облако HONOR заблокирован (device-enrollment +
token-binding + DB-integrity tamper-detection). Но можно ДРАЙВИТЬ сам app — он пишет
заметку родным путём (своя крипта SM2/AES-GCM + upload), синк в облако/телефон легитимен.

Доказано: клик `.newNoteButton` + ввод заголовка (textarea `.noteTitleText`) + тела
(contenteditable `.app-note-editor-01`) через CDP `Input.insertText` → заметка создаётся
и синкается на телефон.

Требования: HonorWorkStation запущен с `--remote-debugging-port=<port>` и залогинен.
Запуск: `open -a HonorWorkStation --args --remote-debugging-port=9222`.

NB: websocket подключение требует suppress_origin=True (Electron отвергает Origin).
"""
from __future__ import annotations

import json
import time

import requests
from websocket import create_connection

NEW_NOTE_BTN = ".newNoteButton"
TITLE_SEL = ".noteTitleText"
BODY_SEL = ".app-note-editor-01,[contenteditable=true]"


class HonorCdpWriter:
    def __init__(self, port: int = 9222):
        self._port = port
        self._ws = None
        self._id = 0

    def connect(self) -> None:
        targets = requests.get(f"http://localhost:{self._port}/json", timeout=10).json()
        pages = [t for t in targets if t.get("type") == "page" and "webSocketDebuggerUrl" in t]
        if not pages:
            raise RuntimeError("HonorWorkStation CDP page не найдена (запущен с --remote-debugging-port?)")
        self._ws = create_connection(pages[0]["webSocketDebuggerUrl"], suppress_origin=True, max_size=None)

    def _cmd(self, method: str, params: dict | None = None) -> dict:
        self._id += 1
        self._ws.send(json.dumps({"id": self._id, "method": method, "params": params or {}}))
        while True:
            msg = json.loads(self._ws.recv())
            if msg.get("id") == self._id:
                return msg.get("result", {})

    def _eval(self, expr: str):
        r = self._cmd("Runtime.evaluate", {"expression": expr, "returnByValue": True, "awaitPromise": True})
        return r.get("result", {}).get("value")

    def create_note(self, title: str, body: str = "", settle: float = 2.0) -> None:
        """Создать заметку через UI app (родной путь записи+синка)."""
        if self._eval(f"(()=>{{const b=document.querySelector('{NEW_NOTE_BTN}');if(!b)return false;b.click();return true;}})()") is not True:
            raise RuntimeError("newNoteButton не найдена")
        time.sleep(1.5)
        self._eval(f"(()=>{{const t=document.querySelector('{TITLE_SEL}');if(t)t.focus();return!!t;}})()")
        self._cmd("Input.insertText", {"text": title})
        time.sleep(0.4)
        if body:
            self._eval(
                f"(()=>{{const e=document.querySelector('{BODY_SEL}');if(!e)return false;e.focus();"
                "const r=document.createRange();r.selectNodeContents(e);r.collapse(false);"
                "const s=getSelection();s.removeAllRanges();s.addRange(r);return true;}})()"
            )
            time.sleep(0.3)
            self._cmd("Input.insertText", {"text": body})
        time.sleep(settle)  # автосейв + синк

    def close(self) -> None:
        if self._ws:
            self._ws.close()
