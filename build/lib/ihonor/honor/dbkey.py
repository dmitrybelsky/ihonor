"""Деривация пароля локальной БД HONOR Notes (ChaCha20).

Без хардкода секретов: enkey читается с диска, пароль вычисляется нативной AEAD
из бандла HonorWorkStation (их же крипто). Вскрыто Phase 0 (EncryService.getDBSecretKey).
"""
import contextlib
import ctypes
import os
import plistlib
import re
import sys


@contextlib.contextmanager
def _suppress_c_stdout():
    """Глушит stdout на уровне fd 1 (C printf): нативный dylib HONOR печатает
    'Library initialized.' при загрузке — это ломает машинный JSON-вывод runner'а.
    Python-level redirect не ловит C-printf, нужен dup2 на /dev/null.
    """
    sys.stdout.flush()
    saved = os.dup(1)
    try:
        devnull = os.open(os.devnull, os.O_WRONLY)
        try:
            os.dup2(devnull, 1)
        finally:
            os.close(devnull)
        yield
    finally:
        os.dup2(saved, 1)  # всегда восстанавливаем fd 1
        os.close(saved)

APP = "/Applications/HonorWorkStation.app/Contents"
DYLIB = f"{APP}/Frameworks/libSecurityKitNodejs.dylib"
CONTAINER = os.path.expanduser("~/Library/Containers/com.hihonor.hihonornote/Data")
CONFIG_XML = f"{CONTAINER}/.config/hihonornote/config/config.xml"
PREF_PLIST = f"{CONTAINER}/Library/Preferences/com.hihonor.hihonornote.plist"

AES_KEY = b"0a68afdc$c84b$4f"
KEY_MATA = b"dcb36b2f$5d18$4d"
NID = 895


def read_enkey() -> str:
    """32-hex enkey из preference Note/Userkey (приоритет) или config.xml."""
    try:
        with open(PREF_PLIST, "rb") as f:
            pref = plistlib.load(f)
        uk = (pref.get("Note") or {}).get("Userkey")
        if uk and len(uk) == 32:
            return uk
    except (FileNotFoundError, KeyError, plistlib.InvalidFileException):
        pass  # нет/битый plist → фоллбэк на config.xml (ожидаемо)
    with open(CONFIG_XML, encoding="utf-8") as f:
        out = f.read()
    if "<enkey>" not in out:
        raise ValueError(f"<enkey> не найден в {CONFIG_XML}")
    inner = out.split("<enkey>", 1)[1].split("</enkey>", 1)[0].strip()[-32:]
    if not re.fullmatch(r"[0-9a-fA-F]{32}", inner):
        raise ValueError("enkey не 32-hex")
    return inner


_FN = None  # кэш сконфигурированной нативной функции (dlopen один раз на процесс)


def _aead_fn():
    global _FN
    if _FN is None:
        os.environ.setdefault("DYLD_LIBRARY_PATH", f"{APP}/Frameworks:{APP}/OfficeCenter")
        with _suppress_c_stdout():  # dylib печатает 'Library initialized.' при загрузке
            lib = ctypes.CDLL(DYLIB)
        fn = lib.honorcloud_aead_decrypt
        fn.restype = ctypes.c_int
        fn.argtypes = [
            ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_int,
            ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p,
        ]
        _FN = fn
    return _FN


def derive_db_password() -> str:
    enkey_hex = read_enkey()
    enkey = bytes.fromhex(enkey_hex)
    out = ctypes.create_string_buffer(len(enkey))
    rc = _aead_fn()(NID, enkey, len(enkey), None, 0, b"\x00" * 16, AES_KEY, KEY_MATA, 16, out)
    # rc-конвенция нативной функции недокументирована → не гейтим на rc, валидируем ВЫХОД:
    # пустой/недекодируемый буфер = провал деривации (иначе вернётся мусор-ключ, всплывёт
    # позже как opaque apsw 'file is not a database').
    raw = out.raw.rstrip(b"\x00")
    if not raw:
        raise RuntimeError(f"honorcloud_aead_decrypt: пустой ключ (rc={rc}), деривация не удалась")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as e:
        raise RuntimeError(f"honorcloud_aead_decrypt: ключ не UTF-8 (rc={rc}), деривация не удалась") from e


if __name__ == "__main__":
    print(derive_db_password())
