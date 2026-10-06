"""Windows konsolu ile alt seviye iletişim (sadece standart kütüphane: ctypes).

Neden gerekli?
  input() gibi fonksiyonlar Enter'a basılana kadar bekler ve Ctrl+Shift+Yön gibi
  kombinasyonları ayırt edemez. Bu yüzden Windows API'sindeki ReadConsoleInputW
  fonksiyonunu kullanıyoruz: her tuş basışını; tuş kodu, karakter ve Ctrl/Shift/Alt
  durumuyla birlikte ham olarak verir.

Bu modülün yaptıkları:
  1. Konsolu "ham moda" alır (satır tamponu, yankı, Ctrl+C sinyali, fare, hızlı düzenleme kapalı).
  2. VT (ANSI) işlemeyi açar -> renkler ve imleç şekli çalışır.
  3. Alternatif ekran tamponuna geçer (çıkınca eski konsol içeriği geri gelir).
  4. İmleci YANIP SÖNEN DİKEY ÇİZGİ yapar ve rengini beyaz ayarlar.
  5. Tuşları Key nesnelerine çevirir.
  6. Windows panosuna (clipboard) okuma/yazma yapar.
"""
import ctypes
import shutil
from ctypes import wintypes

from keys import Key

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
user32 = ctypes.WinDLL("user32", use_last_error=True)

# --- Sabitler ------------------------------------------------------------- #
STD_INPUT_HANDLE = -10
STD_OUTPUT_HANDLE = -11

KEY_EVENT = 0x0001
WINDOW_BUFFER_SIZE_EVENT = 0x0004

# Giriş modu bayrakları
ENABLE_WINDOW_INPUT = 0x0008       # pencere boyutu değişince olay gelsin
ENABLE_EXTENDED_FLAGS = 0x0080     # hızlı düzenleme (fare ile seçme) kapatılabilsin
# Çıkış modu bayrakları
ENABLE_PROCESSED_OUTPUT = 0x0001
ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004   # ANSI kaçış dizileri
DISABLE_NEWLINE_AUTO_RETURN = 0x0008

# Ctrl / Alt / Shift durum bayrakları
RIGHT_ALT_PRESSED = 0x0001
LEFT_ALT_PRESSED = 0x0002
RIGHT_CTRL_PRESSED = 0x0004
LEFT_CTRL_PRESSED = 0x0008
SHIFT_PRESSED = 0x0010

# Sanal tuş kodları (Virtual Key) -> bizim isimlerimiz
VK_NAMES = {
    0x08: "BACKSPACE", 0x09: "TAB", 0x0D: "ENTER", 0x1B: "ESC",
    0x21: "PGUP", 0x22: "PGDN", 0x23: "END", 0x24: "HOME",
    0x25: "LEFT", 0x26: "UP", 0x27: "RIGHT", 0x28: "DOWN",
    0x2E: "DELETE",
}

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002


# --- Windows yapıları (struct) --------------------------------------------- #
class KEY_EVENT_RECORD(ctypes.Structure):
    _fields_ = [
        ("bKeyDown", wintypes.BOOL),
        ("wRepeatCount", wintypes.WORD),
        ("wVirtualKeyCode", wintypes.WORD),
        ("wVirtualScanCode", wintypes.WORD),
        ("uChar", wintypes.WCHAR),
        ("dwControlKeyState", wintypes.DWORD),
    ]


class _EVENT_UNION(ctypes.Union):
    _fields_ = [("KeyEvent", KEY_EVENT_RECORD), ("_padding", ctypes.c_byte * 16)]


class INPUT_RECORD(ctypes.Structure):
    _fields_ = [("EventType", wintypes.WORD), ("Event", _EVENT_UNION)]


# --- Fonksiyon imzaları ---------------------------------------------------- #
kernel32.GetStdHandle.restype = wintypes.HANDLE
kernel32.GetStdHandle.argtypes = [wintypes.DWORD]
kernel32.GetConsoleMode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
kernel32.SetConsoleMode.argtypes = [wintypes.HANDLE, wintypes.DWORD]
kernel32.ReadConsoleInputW.argtypes = [wintypes.HANDLE, ctypes.POINTER(INPUT_RECORD),
                                       wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
kernel32.PeekConsoleInputW.argtypes = [wintypes.HANDLE, ctypes.POINTER(INPUT_RECORD),
                                       wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
kernel32.GetNumberOfConsoleInputEvents.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
kernel32.WriteConsoleW.argtypes = [wintypes.HANDLE, wintypes.LPCWSTR, wintypes.DWORD,
                                   ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID]
kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalLock.restype = wintypes.LPVOID
kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
user32.OpenClipboard.argtypes = [wintypes.HWND]
user32.GetClipboardData.argtypes = [wintypes.UINT]
user32.GetClipboardData.restype = wintypes.HANDLE
user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
user32.SetClipboardData.restype = wintypes.HANDLE


class WindowsConsole:
    def __init__(self):
        self.h_in = kernel32.GetStdHandle(STD_INPUT_HANDLE)
        self.h_out = kernel32.GetStdHandle(STD_OUTPUT_HANDLE)
        self._old_in_mode = wintypes.DWORD()
        self._old_out_mode = wintypes.DWORD()
        self._pending = []     # tuş basılı tutulunca gelen tekrarlar
        self._started = False

    # ------------------------------------------------------------------ #
    # Başlat / Kapat
    # ------------------------------------------------------------------ #
    def start(self):
        kernel32.GetConsoleMode(self.h_in, ctypes.byref(self._old_in_mode))
        kernel32.GetConsoleMode(self.h_out, ctypes.byref(self._old_out_mode))
        self._old_cp = kernel32.GetConsoleOutputCP()
        self._old_icp = kernel32.GetConsoleCP()
        kernel32.SetConsoleOutputCP(65001)    # UTF-8 -> Türkçe karakterler
        kernel32.SetConsoleCP(65001)

        # Ham giriş: satır tamponu, yankı, Ctrl+C sinyali, fare, hızlı düzenleme KAPALI
        kernel32.SetConsoleMode(self.h_in, ENABLE_WINDOW_INPUT | ENABLE_EXTENDED_FLAGS)
        out_mode = (ENABLE_PROCESSED_OUTPUT | ENABLE_VIRTUAL_TERMINAL_PROCESSING
                    | DISABLE_NEWLINE_AUTO_RETURN)
        if not kernel32.SetConsoleMode(self.h_out, out_mode):
            raise RuntimeError("Konsol ANSI renklerini desteklemiyor (Windows 10 veya üstü gerekir).")
        self._started = True
        self.write(
            "\x1b[?1049h"          # alternatif ekran tamponu
            "\x1b[?7l"             # satır sonunda otomatik kaydırmayı kapat
            "\x1b[5 q"             # imleç: yanıp sönen dikey çizgi
            "\x1b]12;#ffffff\x07"  # imleç rengi: beyaz
            "\x1b[2J"
        )

    def stop(self):
        if not self._started:
            return
        self._started = False
        self.write("\x1b[0m\x1b[0 q\x1b]112\x07\x1b[?7h\x1b[?25h\x1b[?1049l")
        kernel32.SetConsoleMode(self.h_in, self._old_in_mode.value)
        kernel32.SetConsoleMode(self.h_out, self._old_out_mode.value)
        kernel32.SetConsoleOutputCP(self._old_cp)
        kernel32.SetConsoleCP(self._old_icp)

    # ------------------------------------------------------------------ #
    # Çıkış
    # ------------------------------------------------------------------ #
    def write(self, text):
        """Metni konsola Unicode olarak yazar (Türkçe karakterler bozulmaz)."""
        written = wintypes.DWORD()
        chunk = 8000
        for i in range(0, len(text), chunk):
            part = text[i:i + chunk]
            n = len(part.encode("utf-16-le")) // 2
            kernel32.WriteConsoleW(self.h_out, part, n, ctypes.byref(written), None)

    def size(self):
        """(sütun, satır) olarak pencere boyutu."""
        s = shutil.get_terminal_size((100, 30))
        return s.columns, s.lines

    # ------------------------------------------------------------------ #
    # Giriş
    # ------------------------------------------------------------------ #
    def _decode(self, ev):
        """Windows tuş olayını Key nesnesine çevirir. Anlamsız olaylar için None."""
        vk = ev.wVirtualKeyCode
        state = ev.dwControlKeyState
        ch = ev.uChar
        ctrl = bool(state & (LEFT_CTRL_PRESSED | RIGHT_CTRL_PRESSED))
        alt = bool(state & (LEFT_ALT_PRESSED | RIGHT_ALT_PRESSED))
        shift = bool(state & SHIFT_PRESSED)

        # Ctrl+H düzeltmesi: ASCII'de Ctrl+H = 8 = Backspace karakteridir. Bu yüzden bazı
        # terminaller (Windows Terminal vb.) Ctrl+H'yi Backspace tuşu (VK_BACK) olarak iletir.
        #   - H tuşunun donanım tarama kodu 0x23, Backspace'inki 0x0E'dir.
        #   - Klasik konsolda gerçek Ctrl+Backspace '\x7f' üretir; '\x08' + Ctrl ise Ctrl+H demektir.
        if vk == 0x08 and (ev.wVirtualScanCode == 0x23 or (ctrl and ch == "\x08")):
            return Key("H", ctrl=True, shift=shift, alt=alt)

        if vk in VK_NAMES:
            return Key(VK_NAMES[vk], ctrl=ctrl, shift=shift, alt=alt)

        # Yazılabilir karakter. NOT: Türkçe klavyede @ # $ { [ ] } \ | ~ gibi karakterler
        # AltGr ile yazılır ve Windows AltGr'yi "Ctrl+Alt" olarak bildirir.
        # Bu yüzden Ctrl+Alt birlikteyse karakteri normal karakter sayıyoruz.
        if ch and ch >= " " and ch != "\x7f" and (not ctrl or alt):
            return Key("CHAR", char=ch)

        if ctrl and 0x41 <= vk <= 0x5A:       # Ctrl + A..Z
            return Key(chr(vk), ctrl=True, shift=shift, alt=alt)

        # Terminale yapıştırılan metinlerde tuş kodu 0 gelebilir
        if vk == 0 and ch == "\r":
            return Key("ENTER")
        if vk == 0 and ch == "\t":
            return Key("TAB")
        return None

    def read_key(self):
        """Bir tuş basılana kadar bekler ve Key döndürür."""
        if self._pending:
            return self._pending.pop(0)
        record = INPUT_RECORD()
        count = wintypes.DWORD()
        while True:
            kernel32.ReadConsoleInputW(self.h_in, ctypes.byref(record), 1, ctypes.byref(count))
            if record.EventType == WINDOW_BUFFER_SIZE_EVENT:
                return Key("RESIZE")
            if record.EventType != KEY_EVENT:
                continue
            ev = record.Event.KeyEvent
            if not ev.bKeyDown:           # tuş bırakma olaylarını yok say
                continue
            key = self._decode(ev)
            if key is None:               # sadece Ctrl/Shift'e basıldı vb.
                continue
            for _ in range(max(1, ev.wRepeatCount) - 1):
                self._pending.append(key)
            return key

    def has_input(self):
        """Kuyrukta işlenecek tuş var mı? (Varsa ekranı çizmeyi erteleriz -> titreme olmaz,
        uzun bir yapıştırma tek seferde çizilir.)"""
        if self._pending:
            return True
        total = wintypes.DWORD()
        kernel32.GetNumberOfConsoleInputEvents(self.h_in, ctypes.byref(total))
        if total.value == 0:
            return False
        n = min(total.value, 64)
        records = (INPUT_RECORD * n)()
        got = wintypes.DWORD()
        kernel32.PeekConsoleInputW(self.h_in, records, n, ctypes.byref(got))
        for i in range(got.value):
            rec = records[i]
            if rec.EventType == WINDOW_BUFFER_SIZE_EVENT:
                return True
            if rec.EventType == KEY_EVENT and rec.Event.KeyEvent.bKeyDown:
                if self._decode(rec.Event.KeyEvent) is not None:
                    return True
        return False

    # ------------------------------------------------------------------ #
    # Windows Panosu (Clipboard)
    # ------------------------------------------------------------------ #
    def set_clipboard(self, text):
        try:
            data = ctypes.create_unicode_buffer(text.replace("\n", "\r\n"))
            size = ctypes.sizeof(data)
            if not user32.OpenClipboard(None):
                return False
            try:
                user32.EmptyClipboard()
                handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, size)
                if not handle:
                    return False
                ptr = kernel32.GlobalLock(handle)
                ctypes.memmove(ptr, data, size)
                kernel32.GlobalUnlock(handle)
                if not user32.SetClipboardData(CF_UNICODETEXT, handle):
                    kernel32.GlobalFree(handle)
                    return False
                return True
            finally:
                user32.CloseClipboard()
        except Exception:
            return False

    def get_clipboard(self):
        try:
            if not user32.OpenClipboard(None):
                return None
            try:
                handle = user32.GetClipboardData(CF_UNICODETEXT)
                if not handle:
                    return None
                ptr = kernel32.GlobalLock(handle)
                if not ptr:
                    return None
                try:
                    return ctypes.wstring_at(ptr)
                finally:
                    kernel32.GlobalUnlock(handle)
            finally:
                user32.CloseClipboard()
        except Exception:
            return None
