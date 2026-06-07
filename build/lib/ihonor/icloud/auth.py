import os
import sys
from pathlib import Path

from pyicloud import PyiCloudService


def login(apple_id: str, password: str, session_dir: str = ".icloud-session") -> PyiCloudService:
    """Авторизация в iCloud с персистом сессии.

    pyicloud используем ТОЛЬКО для auth/сессии — его notes-поддержка мертва.
    Cookies/сессия оседают в session_dir, чтобы 2FA не спрашивался каждый раз.

    2FA-код берётся из env ICLOUD_2FA_CODE (для неинтерактивного запуска),
    иначе спрашивается через input() в TTY.
    """
    Path(session_dir).mkdir(exist_ok=True)
    api = PyiCloudService(apple_id, password, cookie_directory=session_dir)

    if api.requires_2fa:
        code = os.environ.get("ICLOUD_2FA_CODE")
        if not code:
            if sys.stdin.isatty():
                code = input("2FA code: ").strip()
            else:
                raise RuntimeError(
                    "Требуется 2FA. Запусти с переменной: "
                    "ICLOUD_2FA_CODE=123456 uv run ..."
                )
        code = code.strip()
        if not api.validate_2fa_code(code):
            raise RuntimeError("iCloud 2FA validation failed (код неверный или истёк)")
        if not api.is_trusted_session:
            api.trust_session()

    return api
