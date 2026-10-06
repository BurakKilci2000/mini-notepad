"""Konsol içinde çalışan dosya yöneticisi (Dosya Aç / Kaydet / Farklı Kaydet için).

Kullanım:
  ↑ ↓          : listede gezin
  → (İleri)    : seçili klasörün içine gir
  ← (Geri)     : üst dizine çık
  Harfler      : dosya adını yaz,  Backspace: dosya adından sil
  Enter        : işlemi tamamla
  ESC          : iptal
"""
import os

import ansi


def human_size(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


class FileManager:
    def __init__(self, console, start_dir):
        self.con = console
        self.cwd = os.path.abspath(start_dir)
        self.entries = []      # [(isim, klasör_mü), ...]
        self.sel = 0           # seçili satırın indeksi
        self.scroll = 0        # listenin ekranda görünen ilk satırı
        self.name = ""         # kullanıcının yazdığı dosya adı
        self.message = ""
        self.mode = "open"
        self.question = None   # (y/n) sorusu varsa

    # ------------------------------------------------------------------ #
    # Klasör içeriği
    # ------------------------------------------------------------------ #
    def load(self, select_name=None):
        try:
            names = os.listdir(self.cwd)
        except OSError as e:
            self.message = f"Klasör okunamadı: {e.strerror}"
            names = []
        dirs, files = [], []
        for n in names:
            (dirs if os.path.isdir(os.path.join(self.cwd, n)) else files).append(n)
        dirs.sort(key=str.casefold)
        files.sort(key=str.casefold)
        # Önce ".." (üst dizin), sonra klasörler, sonra dosyalar
        self.entries = [("..", True)] + [(d, True) for d in dirs] + [(f, False) for f in files]
        self.sel = 0
        self.scroll = 0
        if select_name is not None:
            for i, (n, _) in enumerate(self.entries):
                if n == select_name:
                    self.sel = i
                    break

    def go_forward(self):
        """İLERİ: seçili klasöre gir."""
        name, is_dir = self.entries[self.sel]
        if not is_dir:
            self.message = "Seçili öğe bir klasör değil."
            return
        if name == "..":
            self.go_back()
            return
        target = os.path.join(self.cwd, name)
        try:
            os.listdir(target)        # erişim izni var mı?
        except OSError as e:
            self.message = f"Klasöre girilemedi: {e.strerror}"
            return
        self.cwd = os.path.abspath(target)
        self.load()

    def go_back(self):
        """GERİ: üst dizine çık."""
        parent = os.path.dirname(self.cwd)
        if parent == self.cwd:
            self.message = "Zaten en üst dizindesiniz."
            return
        child = os.path.basename(self.cwd)
        self.cwd = parent
        self.load(select_name=child)

    # ------------------------------------------------------------------ #
    # Ana döngü
    # ------------------------------------------------------------------ #
    def run(self, mode, initial_name=""):
        """mode: 'open' veya 'save'. Seçilen tam dosya yolunu, iptal edilirse None döndürür."""
        self.mode = mode
        self.name = initial_name
        self.load()
        while True:
            if not self.con.has_input():
                self.render()
            key = self.con.read_key()
            if key.name != "RESIZE":
                self.message = ""
            n = key.name

            if n == "ESC":
                return None
            elif n in ("UP", "DOWN", "PGUP", "PGDN"):
                step = {"UP": -1, "DOWN": 1, "PGUP": -10, "PGDN": 10}[n]
                self.sel = max(0, min(len(self.entries) - 1, self.sel + step))
                entry_name, is_dir = self.entries[self.sel]
                if self.mode == "open" and not is_dir:
                    self.name = entry_name     # açarken seçilen dosyanın adını kutuya yaz
            elif n == "RIGHT":
                self.go_forward()
            elif n == "LEFT":
                self.go_back()
            elif n == "BACKSPACE":
                self.name = self.name[:-1]
            elif n == "CHAR":
                self.name += key.char
            elif n == "ENTER":
                result = self.confirm()
                if result:
                    return result

    def confirm(self):
        """Enter'a basıldığında: yazılan dosya adıyla işlemi tamamlar."""
        name = self.name.strip()
        if not name:
            entry_name, is_dir = self.entries[self.sel]
            if is_dir:
                self.go_forward()
                return None
            name = entry_name

        path = os.path.abspath(os.path.join(self.cwd, name))
        if os.path.isdir(path):           # klasör adı yazıldıysa içine gir
            self.cwd = path
            self.name = ""
            self.load()
            return None

        if self.mode == "open":
            if not os.path.isfile(path):
                self.message = f"Dosya bulunamadı: {name}"
                return None
            return path

        # Kaydetme modu
        if os.path.exists(path):
            answer = self.ask(f"'{name}' zaten var. Üzerine yazılsın mı? (y/n) ")
            if answer is not True:
                self.message = "Kaydetme iptal edildi, başka bir ad yazabilirsiniz."
                return None
        return path

    def ask(self, question):
        self.question = question
        try:
            while True:
                self.render()
                key = self.con.read_key()
                if key.name == "CHAR" and key.char in "yY":
                    return True
                if key.name == "CHAR" and key.char in "nN":
                    return False
                if key.name == "ESC":
                    return None
        finally:
            self.question = None

    # ------------------------------------------------------------------ #
    # Çizim
    # ------------------------------------------------------------------ #
    def render(self):
        cols, rows = self.con.size()
        title = "DOSYA AÇ" if self.mode == "open" else "DOSYA KAYDET"
        list_h = max(1, rows - 7)

        if self.sel < self.scroll:
            self.scroll = self.sel
        if self.sel >= self.scroll + list_h:
            self.scroll = self.sel - list_h + 1

        out = [ansi.HIDE_CURSOR]
        out.append(ansi.goto(1, 1) + ansi.TITLE_BAR + ansi.fit(f" {title} — Dosya Yöneticisi", cols) + ansi.RESET)
        out.append(ansi.goto(2, 1) + ansi.fit_tail(f" Konum: {self.cwd}", cols) + ansi.CLEAR_EOL)
        out.append(ansi.goto(3, 1) + ansi.SEPARATOR + "─" * cols + ansi.RESET)

        for i in range(list_h):
            y = 4 + i
            idx = self.scroll + i
            line = ""
            style = ""
            if idx < len(self.entries):
                name, is_dir = self.entries[idx]
                if name == "..":
                    text = " <DIR>  ..  (üst dizin)"
                elif is_dir:
                    text = f" <DIR>  {name}"
                else:
                    try:
                        size = human_size(os.path.getsize(os.path.join(self.cwd, name)))
                    except OSError:
                        size = ""
                    text = f"        {name}"
                    if len(text) + len(size) + 2 < cols:
                        text = text + " " * (cols - len(text) - len(size) - 1) + size
                if idx == self.sel:
                    style = ansi.LIST_SELECTED
                elif is_dir:
                    style = ansi.DIR_COLOR
                line = style + ansi.fit(text, cols) + ansi.RESET
            out.append(ansi.goto(y, 1) + line + ansi.CLEAR_EOL)

        y = 4 + list_h
        out.append(ansi.goto(y, 1) + ansi.SEPARATOR + "─" * cols + ansi.RESET)
        help_text = " ↑↓ Seç   → İleri (klasöre gir)   ← Geri (üst dizin)   Enter Tamam   ESC İptal"
        out.append(ansi.goto(y + 1, 1) + ansi.fit(help_text, cols) + ansi.CLEAR_EOL)
        out.append(ansi.goto(y + 2, 1) + ansi.MESSAGE + ansi.fit(self.question or self.message, cols)
                   + ansi.RESET + ansi.CLEAR_EOL)

        label = " Dosya adı: "
        field_w = max(1, cols - len(label) - 1)
        shown = self.name[-field_w:]
        out.append(ansi.goto(y + 3, 1) + ansi.MESSAGE + label + ansi.PROMPT_TEXT + shown
                   + ansi.RESET + ansi.CLEAR_EOL)
        if self.question:
            cursor_x = len(self.question) + 1
            out.append(ansi.goto(y + 2, min(cols, cursor_x)))
        else:
            out.append(ansi.goto(y + 3, min(cols, len(label) + len(shown) + 1)))
        out.append(ansi.SHOW_CURSOR)
        self.con.write("".join(out))
