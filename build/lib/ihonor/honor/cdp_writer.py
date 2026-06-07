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
import subprocess
import time

import requests
from websocket import create_connection

NEW_NOTE_BTN = ".newNoteButton"
TITLE_SEL = "textarea.noteTitleText"  # именно textarea (.noteTitleText матчит и div-контейнер)
BODY_SEL = ".app-note-editor-01"  # конкретный класс (comma-fallback ломал selectNodeContents)


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
        """Установить значение React-контролируемого textarea/input + триггер onChange.

        Значения вставляются как JS-safe литералы (json.dumps), НЕ через %r — title/body
        приходят из заметок (внешний контент, синк iCloud) → защита от JS-инъекции/поломки.
        """
        sel = json.dumps(selector)
        val = json.dumps(text)
        js = (
            f"(()=>{{const t=document.querySelector({sel});if(!t)return false;t.focus();"
            "const proto=t.tagName==='TEXTAREA'?window.HTMLTextAreaElement.prototype:window.HTMLInputElement.prototype;"
            "const setter=Object.getOwnPropertyDescriptor(proto,'value').set;"
            f"setter.call(t,{val});t.dispatchEvent(new Event('input',{{bubbles:true}}));return true;}})()"
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

    def open_note_by_title(self, title: str) -> bool:
        """Открыть/выделить заметку в списке по точному заголовку (клик по карточке).

        title вставляется как JS-safe литерал (json.dumps), не через %r (внешний контент).
        """
        jt = json.dumps(title)
        box = self._eval(
            "(()=>{const c=[...document.querySelectorAll('.noteCardItem')]"
            f".find(e=>(e.innerText||'').split('\\n')[0].trim()==={jt});"
            "if(!c)return null;const r=c.getBoundingClientRect();"
            "return JSON.stringify({x:r.left+r.width/2,y:r.top+18});})()"
        )
        if not box:
            return False
        c = json.loads(box)
        for ev_type in ("mousePressed", "mouseReleased"):
            self._cmd("Input.dispatchMouseEvent", {
                "type": ev_type, "x": c["x"], "y": c["y"], "button": "left", "clickCount": 1,
            })
        time.sleep(0.8)
        return True

    def update_note(self, title: str, new_body: str, settle: float = 2.5) -> None:
        """Открыть заметку, выделить ВЕСЬ body (DOM Selection) и заменить реальным insertText.

        Slate заменяет выделенное только через реальное input-событие (CDP Input.insertText)
        на корректно выставленном DOM-выделении. Подтверждаем непустое выделение перед вводом
        (иначе insertText добавляет в каретку → append).
        """
        if not self.open_note_by_title(title):
            raise RuntimeError(f"заметка не найдена в списке: {title}")
        time.sleep(0.7)  # дать редактору отрисовать контент открытой заметки
        if not self._click_center(BODY_SEL):
            raise RuntimeError("body editor не найден")
        time.sleep(0.4)
        sel = "(()=>{const e=document.querySelector('%s');if(!e)return '';e.focus();" \
              "const r=document.createRange();r.selectNodeContents(e);" \
              "const s=getSelection();s.removeAllRanges();s.addRange(r);" \
              "return getSelection().toString();})()" % BODY_SEL
        selected = self._eval(sel)
        if not selected:  # выделение пустое — повтор после паузы
            time.sleep(0.5)
            selected = self._eval(sel)
        self._cmd("Input.insertText", {"text": new_body})
        time.sleep(0.4)
        self._eval(
            f"(()=>{{const e=document.querySelector('{BODY_SEL}');if(e){{"
            "e.dispatchEvent(new Event('blur',{bubbles:true}));"
            "e.dispatchEvent(new Event('focusout',{bubbles:true}));}return true;})()"
        )
        time.sleep(settle)

    def _screen_geom(self) -> dict:
        return json.loads(self._eval("JSON.stringify({sx:window.screenX,sy:window.screenY})"))

    def _card_vp(self, title: str):
        jt = json.dumps(title)
        box = self._eval(
            "(()=>{const c=[...document.querySelectorAll('.noteCardItem')]"
            f".find(e=>(e.innerText||'').split('\\n')[0].trim()==={jt});"
            "if(!c)return null;const r=c.getBoundingClientRect();"
            "return JSON.stringify({vx:r.left+r.width/2,vy:r.top+r.height/2});})()"
        )
        return json.loads(box) if box else None

    def _visible_delete_vp(self):
        d = self._eval(
            "(()=>{const e=[...document.querySelectorAll('*')].find(x=>x.offsetParent!==null"
            "&&x.children.length===0&&/^(Delete|Удалить)$/i.test((x.innerText||'').trim()));"
            "if(!e)return null;const r=e.getBoundingClientRect();"
            "return JSON.stringify({vx:r.left+r.width/2,vy:r.top+r.height/2});})()"
        )
        return json.loads(d) if d else None

    def delete_note(self, title: str, settle: float = 2.0) -> None:
        """Удалить заметку реальными OS-кликами (cliclick): синтетика/CDP-клик delete не триггерит.

        Рецепт (доказан): activate → real right-click карточки (контекст-меню) →
        cliclick по пункту Delete → cliclick по confirm-Delete (диалог) → удалено+синк.
        Требует cliclick (brew install cliclick) + frameless-окно (viewport origin = screenX/Y).
        """
        subprocess.run(
            ["osascript", "-e",
             'tell application "System Events" to set frontmost of '
             '(first process whose name is "Hihonornote") to true'],
            capture_output=True,
        )
        time.sleep(0.4)
        g = self._screen_geom()
        card = self._card_vp(title)
        if not card:
            raise RuntimeError(f"карточка не найдена: {title}")

        def real_click(vp, button="left"):
            x = round(g["sx"] + vp["vx"]); y = round(g["sy"] + vp["vy"])
            flag = "rc" if button == "right" else "c"
            subprocess.run(["cliclick", f"{flag}:{x},{y}"], capture_output=True)

        real_click(card, "right")           # контекст-меню
        time.sleep(0.6)
        d = self._visible_delete_vp()
        if not d:
            raise RuntimeError("пункт Delete в меню не найден")
        real_click(d)                        # клик Delete
        time.sleep(0.9)
        conf = self._visible_delete_vp()     # confirm-диалог (тоже 'Delete')
        if conf:
            real_click(conf)
        time.sleep(settle)

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
