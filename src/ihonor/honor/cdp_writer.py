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
TITLE_SEL = "textarea.noteTitleText"  # именно textarea (.noteTitleText матчит и div-контейнер)
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

    def _set_react_value(self, selector: str, text: str) -> bool:
        """Установить значение React-контролируемого textarea/input + триггер onChange."""
        js = (
            "(()=>{const t=document.querySelector(%r);if(!t)return false;t.focus();"
            "const proto=t.tagName==='TEXTAREA'?window.HTMLTextAreaElement.prototype:window.HTMLInputElement.prototype;"
            "const setter=Object.getOwnPropertyDescriptor(proto,'value').set;"
            "setter.call(t,%r);t.dispatchEvent(new Event('input',{bubbles:true}));return true;})()"
            % (selector, text)
        )
        return self._eval(js) is True

    def create_note(self, title: str, body: str = "", settle: float = 2.5) -> None:
        """Создать заметку через UI app (родной путь записи+синка).

        Надёжно (проверено: TABTEST1 чистый title): click newNote → React-set title
        (native setter + input event; Input.insertText не триггерит React onChange надёжно).
        Body — best-effort через Tab→insertText; CDP body-ввод хрупок к фокусу/app-state
        (см. spec риски, hardening TODO).
        """
        if self._eval(f"(()=>{{const b=document.querySelector('{NEW_NOTE_BTN}');if(!b)return false;b.click();return true;}})()") is not True:
            raise RuntimeError("newNoteButton не найдена")
        time.sleep(1.5)
        if not self._set_react_value(TITLE_SEL, title):
            raise RuntimeError("title textarea не найдена")
        time.sleep(0.4)
        if body:
            # реальный mouse-click в ЦЕНТР body-редактора (центр, не угол — угол бьёт в тулбар)
            if not self._click_center(BODY_SEL):
                raise RuntimeError("body editor не найден")
            time.sleep(0.3)
            self._cmd("Input.insertText", {"text": body})
            time.sleep(0.4)
        # blur/focusout body -> app коммитит и сохраняет (иначе title+body не пишутся в БД)
        self._eval(
            f"(()=>{{const e=document.querySelector('{BODY_SEL}');if(e){{"
            "e.dispatchEvent(new Event('blur',{bubbles:true}));"
            "e.dispatchEvent(new Event('focusout',{bubbles:true}));}return true;})()"
        )
        time.sleep(settle)  # автосейв + синк

    def _click_center(self, selector: str) -> bool:
        import json as _json
        box = self._eval(
            "(()=>{const e=document.querySelector(%r);if(!e)return null;"
            "const r=e.getBoundingClientRect();"
            "return JSON.stringify({x:r.left+r.width/2,y:r.top+r.height/2});})()" % selector
        )
        if not box:
            return False
        c = _json.loads(box)
        for ev_type in ("mousePressed", "mouseReleased"):
            self._cmd("Input.dispatchMouseEvent", {
                "type": ev_type, "x": c["x"], "y": c["y"], "button": "left", "clickCount": 1,
            })
        return True

    def close(self) -> None:
        if self._ws:
            self._ws.close()
