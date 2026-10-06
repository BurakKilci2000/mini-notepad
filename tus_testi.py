"""Tanı aracı: basılan her tuşun Windows'a nasıl ulaştığını gösterir. Çıkış: ESC."""
import ctypes
from console import WindowsConsole, INPUT_RECORD, KEY_EVENT, kernel32
from ctypes import wintypes

con = WindowsConsole()
kernel32.SetConsoleMode(con.h_in, 0x0080)
print("Tuşlara basın (Ctrl+H, Backspace, Ctrl+Backspace). Çıkmak için ESC.")
rec, n = INPUT_RECORD(), wintypes.DWORD()
while True:
    kernel32.ReadConsoleInputW(con.h_in, ctypes.byref(rec), 1, ctypes.byref(n))
    if rec.EventType != KEY_EVENT or not rec.Event.KeyEvent.bKeyDown:
        continue
    e = rec.Event.KeyEvent
    print(f"vk=0x{e.wVirtualKeyCode:02X}  scan=0x{e.wVirtualScanCode:02X}  "
          f"char={e.uChar!r}  durum=0x{e.dwControlKeyState:X}  ->  {con._decode(e)}")
    if e.wVirtualKeyCode == 0x1B:
        break
