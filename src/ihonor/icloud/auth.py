from pathlib import Path

from pyicloud import PyiCloudService


def login(apple_id: str, password: str, session_dir: str = ".icloud-session") -> PyiCloudService:
    """Авторизация в iCloud с персистом сессии.

    pyicloud используем ТОЛЬКО для auth/сессии — его notes-поддержка мертва.
    Cookies/сессия оседают в session_dir, чтобы 2FA не спрашивался каждый раз.
    """
    Path(session_dir).mkdir(exist_ok=True)
    api = PyiCloudService(apple_id, password, cookie_directory=session_dir)

    if api.requires_2fa:
        code = input("2FA code: ").strip()
        if not api.validate_2fa_code(code):
            raise RuntimeError("iCloud 2FA validation failed")
        if not api.is_trusted_session:
            api.trust_session()

    return api
