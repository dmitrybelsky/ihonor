"""Деривация пароля локальной БД HONOR Notes (HonorWorkStation, macOS).

Без хардкода секретов: enkey читается с диска в рантайме, пароль вычисляется
вызовом нативной AEAD-функции из бандла приложения (их же крипто).

Цепочка (вскрыто из app.asar, EncryService.getDBSecretKey):
  enkey (32 hex) хранится в macOS preference Note/Userkey и в config.xml
  -> honorcloud_aead_decrypt(nid=895, enkey, aesKey, keyMata) -> пароль (utf8)
  -> better-sqlite3-multiple-ciphers default cipher = ChaCha20, PRAGMA key=пароль.
"""
import ctypes
import os
import plistlib
import subprocess

APP = "/Applications/HonorWorkStation.app/Contents"
DYLIB = f"{APP}/Frameworks/libSecurityKitNodejs.dylib"
CONTAINER = os.path.expanduser("~/Library/Containers/com.hihonor.hihonornote/Data")
CONFIG_XML = f"{CONTAINER}/.config/hihonornote/config/config.xml"
PREF_PLIST = f"{CONTAINER}/Library/Preferences/com.hihonor.hihonornote.plist"

# Статические константы из EncryService (app.asar)
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
    except Exception:
        pass
    # fallback: config.xml = deviceIdPrefix + 32-hex enkey
    out = subprocess.check_output(["cat", CONFIG_XML], text=True)
    inner = out.split("<enkey>")[1].split("</enkey>")[0].strip()
    return inner[-32:]  # последние 32 символа = сам enkey


def derive_db_password() -> str:
    enkey_hex = read_enkey()
    os.environ.setdefault(
        "DYLD_LIBRARY_PATH", f"{APP}/Frameworks:{APP}/OfficeCenter"
    )
    lib = ctypes.CDLL(DYLIB)
    fn = lib.honorcloud_aead_decrypt
    fn.restype = ctypes.c_int
    fn.argtypes = [
        ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_int,
        ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p,
    ]
    enkey = bytes.fromhex(enkey_hex)
    out = ctypes.create_string_buffer(len(enkey))
    fn(NID, enkey, len(enkey), None, 0, b"\x00" * 16, AES_KEY, KEY_MATA, 16, out)
    # ret=-1 — лишь debug-лог в их коде (GCM tag-mismatch), plaintext валиден
    return out.raw.rstrip(b"\x00").decode("utf-8")


if __name__ == "__main__":
    print(derive_db_password())
