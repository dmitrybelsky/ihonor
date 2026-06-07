"""HONOR delete через AppleScript AX (System Events).

CDP-синтетика не триггерит delete (trusted-gesture). Решение: открыть заметку через CDP,
затем нативный AXPress на AXStaticText "Delete" (доказано: удаляет). Требует Accessibility-доступ
+ Electron AXManualAccessibility (выставляется здесь). Заметка должна быть ОТКРЫТА (CDP) до вызова.
"""
import subprocess

APP_NAME = "HonorWorkStation"  # имя приложения для activate
AX_PROCESS = "Hihonornote"      # AX-имя процесса (бинарь) для System Events

_DELETE_OSA = f'''
tell application "{APP_NAME}" to activate
delay 0.4
tell application "System Events" to tell process "{AX_PROCESS}"
  try
    set value of attribute "AXManualAccessibility" to true
  end try
  delay 0.4
  set ec to entire contents of window 1
  repeat with el in ec
    try
      if (name of el) is "Delete" then
        set tgt to el
        repeat 4 times
          try
            perform action "AXPress" of tgt
            return "ok"
          end try
          set tgt to (value of attribute "AXParent" of tgt)
        end repeat
      end if
    end try
  end repeat
  return "notfound"
end tell
'''


def ax_press_delete() -> bool:
    """AXPress по элементу 'Delete' открытой заметки. True если нажато."""
    out = subprocess.run(["osascript", "-e", _DELETE_OSA], capture_output=True, text=True).stdout.strip()
    return out == "ok"
