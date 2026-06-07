"""Деривация пароля локальной БД HONOR Notes (ChaCha20).

Без хардкода секретов: enkey читается с диска, пароль вычисляется нативной AEAD
из бандла HonorWorkStation (их же крипто). Вскрыто Phase 0 (EncryService.getDBSecretKey).
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
    out = subprocess.check_output(["cat", CONFIG_XML], text=True)
    inner = out.split("<enkey>")[1].split("</enkey>")[0].strip()
    return inner[-32:]


def derive_db_password() -> str:
    enkey_hex = read_enkey()
    os.environ.setdefault("DYLD_LIBRARY_PATH", f"{APP}/Frameworks:{APP}/OfficeCenter")
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
    return out.raw.rstrip(b"\x00").decode("utf-8")


if __name__ == "__main__":
    print(derive_db_password())
