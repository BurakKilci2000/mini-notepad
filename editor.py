"""Editörün beyni: tuşları yorumlar, metni düzenler ve ekranı çizer.

Ekran düzeni:
  ┌──────────────────────────────────────────────┐
  │ Toolbox şeridi (komutlar + kısayollar)       │  <- sığmazsa alt satıra taşar
  │──────────────────────────────────────────────│
  │  1 │ metin...                                │
  │  2 │ metin...                                │  <- metin alanı (satır numaralı)
  │ ...                                          │
  │ Durum çubuğu: dosya adı, satır, sütun        │
  │ Mesaj / soru satırı (Ctrl+F vb. burada)      │
  └──────────────────────────────────────────────┘
"""
import os
from bisect import bisect_left

import ansi
from buffer import TextBuffer
from filemanager import FileManager
from search import find_all
from selection import Selection
from undo import BATCH, DELETE, INSERT, Action, Stack

TAB_SPACES = "    "

# Toolbox şeridi: (grup başlığı, [(komut, kısayol), ...])
TOOLBOX = [
    ("Dosya İşlemleri", [("Dosya Aç", "Ctrl+O"), ("Dosya Kaydet", "Ctrl+S"),
                         ("Dosya Farklı Kaydet", "Ctrl+Shift+S")]),
    ("Arama", [("Ara", "Ctrl+F"), ("Bul ve Gez", "Ctrl+G"), ("Değiştir", "Ctrl+H")]),
    ("Düzen", [("Kopyala", "Ctrl+C"), ("Kes", "Ctrl+X"), ("Yapıştır", "Ctrl+V"),
               ("Geri Al", "Ctrl+Z"), ("Karakter Seç", "Ctrl+Yön"),
               ("Kelime Seç", "Ctrl+Shift+Yön"), ("Karakter Sil", "Backspace"),
               ("Kelime Sil", "Ctrl+Backspace"), ("Çıkış", "ESC")]),
]


def is_word_char(ch):
    """Kelime karakteri mi? (Türkçe harfler de isalnum() ile True döner.)"""
    return ch.isalnum() or ch == "_"


class Editor:
    def __init__(self, console, path=None):
        self.con = console
        self.buf = TextBuffer()
        self.row = 0                # imlecin satırı (0 tabanlı)
        self.col = 0                # imlecin sütunu (0 tabanlı)
        self.want_col = 0           # yukarı/aşağı giderken korunacak sütun
        self.top = 0                # ekranda görünen ilk satır (dikey kaydırma)
        self.left = 0               # ekranda görünen ilk sütun (yatay kaydırma)
        self.page_h = 20
        self.filepath = None        # None -> dosya hiç kaydedilmedi
        self.selection = Selection()
        self.clipboard = ""
        self.undo_stack = Stack()
        self.saved_id = None        # kaydedildiği andaki en üst undo kaydının numarası
        self.can_merge = False      # art arda yazılan harfler tek undo kaydında birleşsin mi
        self._batch = None
        self._batch_cursor = (0, 0)
        self.search_text = ""
        self.matches = []           # [(satır, sütun), ...]
        self.current_match = -1     # Ctrl+G ile üzerinde durulan eşleşme
        self.message = "Yeni dosya oluşturuldu. Tüm komutlar üstteki şeritte."
        self.prompt_label = None    # alt satırda bir giriş isteniyorsa etiketi
        self.prompt_text = ""
        self.running = True
        if path:
            self.load_file(path)

    # ================================================================== #
    # Durum bilgileri
    # ================================================================== #
    @property
    def modified(self):
        """Dosya son kayıttan beri değişti mi? Undo yığınının tepesine bakarak anlarız.
        (Geri alarak kayıtlı hale dönülürse 'değişmedi' sayılır.)"""
        top = self.undo_stack.peek()
        return (top.id if top else None) != self.saved_id

    def cursor_index(self):
        return self.buf.to_index(self.row, self.col)

    def set_cursor(self, row, col, keep_want=False):
        row = max(0, min(row, self.buf.line_count() - 1))
        col = max(0, min(col, self.buf.line_length(row)))
        self.row, self.col = row, col
        if not keep_want:
            self.want_col = col

    def sel_range(self):
        """Seçimin (başlangıç, bitiş) konumlarını (satır, sütun) olarak verir."""
        a, b = self.selection.ordered()
        return self.buf.from_index(a), self.buf.from_index(b)

    # ================================================================== #
    # Düzenleme ilkelleri: TÜM değişiklikler buradan geçer ve undo yığınına kaydedilir
    # ================================================================== #
    def _record(self, action):
        if self._batch is not None:
            self._batch.append(action)
        else:
            self.undo_stack.push(action)

    def edit_insert(self, pos, text, mergeable=False):
        top = self.undo_stack.peek()
        if (mergeable and self.can_merge and self._batch is None and top is not None
                and top.kind == INSERT and TextBuffer.end_of(top.pos, top.text) == pos):
            top.text += text        # aynı kelimeyi yazmaya devam: önceki kayda ekle
        else:
            self._record(Action(INSERT, pos, text, (self.row, self.col)))
        end = self.buf.insert_text(pos[0], pos[1], text)
        self.can_merge = mergeable
        self.clear_search()
        return end

    def edit_delete(self, start, end):
        if start == end:
            return ""
        before = (self.row, self.col)
        text = self.buf.delete_range(start, end)
        self._record(Action(DELETE, start, text, before))
        self.can_merge = False
        self.clear_search()
        return text

    def begin_batch(self):
        self._batch = []
        self._batch_cursor = (self.row, self.col)

    def end_batch(self):
        children, self._batch = self._batch, None
        if children:
            self.undo_stack.push(Action(BATCH, cursor_before=self._batch_cursor, children=children))

    def _revert(self, action):
        """Bir işlemin tersini uygular."""
        if action.kind == INSERT:
            self.buf.delete_range(action.pos, TextBuffer.end_of(action.pos, action.text))
        elif action.kind == DELETE:
            self.buf.insert_text(action.pos[0], action.pos[1], action.text)
        elif action.kind == BATCH:
            for child in reversed(action.children):   # sondan başa doğru geri al
                self._revert(child)

    # ================================================================== #
    # Komutlar: yazma ve silme
    # ================================================================== #
    def delete_selection(self):
        if not self.selection.is_active():
            self.selection.clear()
            return False
        start, end = self.sel_range()
        self.edit_delete(start, end)
        self.set_cursor(*start)
        self.selection.clear()
        return True

    def type_char(self, ch):
        self.delete_selection()     # seçili metin varsa, yazılan karakter onun yerine geçer
        end = self.edit_insert((self.row, self.col), ch, mergeable=(ch != " "))
        self.set_cursor(*end)

    def insert_at_cursor(self, text):
        self.delete_selection()
        end = self.edit_insert((self.row, self.col), text)
        self.set_cursor(*end)

    def backspace(self, word=False):
        """Normal Backspace: bir karakter siler. Ctrl+Backspace: bir kelime siler."""
        if self.delete_selection():
            return
        r, c = self.row, self.col
        if word:
            start = self.word_left(r, c)
        elif c > 0:
            start = (r, c - 1)
        elif r > 0:                                   # satır başında: üst satırla birleştir
            start = (r - 1, self.buf.line_length(r - 1))
        else:
            return
        if start == (r, c):
            return
        self.edit_delete(start, (r, c))
        self.set_cursor(*start)

    def delete_forward(self):
        if self.delete_selection():
            return
        r, c = self.row, self.col
        if c < self.buf.line_length(r):
            self.edit_delete((r, c), (r, c + 1))
        elif r < self.buf.line_count() - 1:
            self.edit_delete((r, c), (r + 1, 0))

    def undo(self):
        action = self.undo_stack.pop()
        if action is None:
            self.message = "Geri alınacak işlem yok."
            return
        self._revert(action)
        self.selection.clear()
        self.clear_search()
        self.can_merge = False
        self.set_cursor(*action.cursor_before)
        self.message = "Geri alındı."

    # ================================================================== #
    # Komutlar: kopyala / kes / yapıştır
    # ================================================================== #
    def copy(self, cut=False):
        if not self.selection.is_active():
            self.message = "Önce metin seçin (Ctrl+Yön veya Ctrl+Shift+Yön)."
            return
        start, end = self.sel_range()
        text = self.buf.get_range(start, end)
        self.clipboard = text
        self.con.set_clipboard(text)       # Windows panosuna da yaz
        if cut:
            self.delete_selection()
            self.message = f"Kesildi ({len(text)} karakter)."
        else:
            self.message = f"Kopyalandı ({len(text)} karakter)."

    def paste(self):
        text = self.con.get_clipboard() or self.clipboard
        if not text:
            self.message = "Pano boş."
            return
        text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\t", TAB_SPACES)
        self.insert_at_cursor(text)
        self.message = f"Yapıştırıldı ({len(text)} karakter)."

    # ================================================================== #
    # İmleç hareketi ve seçim
    # ================================================================== #
    def word_left(self, r, c):
        """Bir önceki kelimenin başı."""
        if c == 0:
            return (r - 1, self.buf.line_length(r - 1)) if r > 0 else (r, c)
        line = self.buf.lines[r]
        while c > 0 and line[c - 1].isspace():
            c -= 1
        if c > 0 and is_word_char(line[c - 1]):
            while c > 0 and is_word_char(line[c - 1]):
                c -= 1
        else:
            while c > 0 and not is_word_char(line[c - 1]) and not line[c - 1].isspace():
                c -= 1
        return r, c

    def word_right(self, r, c):
        """Bir sonraki kelimenin başı."""
        line = self.buf.lines[r]
        if c >= len(line):
            return (r + 1, 0) if r + 1 < self.buf.line_count() else (r, c)
        if is_word_char(line[c]):
            while c < len(line) and is_word_char(line[c]):
                c += 1
        else:
            while c < len(line) and not is_word_char(line[c]) and not line[c].isspace():
                c += 1
        while c < len(line) and line[c].isspace():
            c += 1
        return r, c

    def move_cursor(self, key):
        """Yön tuşları.
        Yön             -> sadece hareket (seçimi kaldırır)
        Ctrl+Yön        -> karakter karakter SEÇİM
        Ctrl+Shift+Yön  -> kelime kelime SEÇİM
        """
        name = key.name
        selecting = key.ctrl
        by_word = key.ctrl and key.shift
        if selecting:
            self.selection.begin(self.cursor_index())
        else:
            self.selection.clear()

        r, c = self.row, self.col
        if name == "LEFT":
            if by_word:
                r, c = self.word_left(r, c)
            elif c > 0:
                c -= 1
            elif r > 0:
                r, c = r - 1, self.buf.line_length(r - 1)
            self.set_cursor(r, c)
        elif name == "RIGHT":
            if by_word:
                r, c = self.word_right(r, c)
            elif c < self.buf.line_length(r):
                c += 1
            elif r < self.buf.line_count() - 1:
                r, c = r + 1, 0
            self.set_cursor(r, c)
        elif name == "UP":
            if r > 0:
                self.set_cursor(r - 1, self.want_col, keep_want=True)
        elif name == "DOWN":
            if r < self.buf.line_count() - 1:
                self.set_cursor(r + 1, self.want_col, keep_want=True)
        elif name == "HOME":
            self.set_cursor(r, 0)
        elif name == "END":
            self.set_cursor(r, self.buf.line_length(r))
        elif name == "PGUP":
            self.set_cursor(r - self.page_h, self.want_col, keep_want=True)
        elif name == "PGDN":
            self.set_cursor(r + self.page_h, self.want_col, keep_want=True)

        if selecting:
            self.selection.update(self.cursor_index())
        self.can_merge = False

    # ================================================================== #
    # Arama (Ctrl+F), Bul ve Gez (Ctrl+G), Değiştir (Ctrl+H)
    # ================================================================== #
    def set_search(self, text):
        self.search_text = text
        self.matches = find_all(self.buf, text) if text else []
        self.current_match = -1

    def clear_search(self):
        self.search_text = ""
        self.matches = []
        self.current_match = -1

    def first_match_from_cursor(self):
        for i, pos in enumerate(self.matches):
            if pos >= (self.row, self.col):
                return i
        return 0

    def cmd_find(self):
        """Ctrl+F: Yazdıkça eşleşmeler MAVİ arka planla gösterilir."""
        self.selection.clear()
        query = self.prompt("Ara (Enter: onayla, ESC: iptal): ", on_change=self.set_search)
        if not query:
            self.clear_search()
            self.message = "Arama iptal edildi."
            return
        self.set_search(query)
        if not self.matches:
            self.clear_search()
            self.message = f"'{query}' bulunamadı."
            return
        r, c = self.matches[self.first_match_from_cursor()]
        self.set_cursor(r, c)
        self.message = f"'{query}': {len(self.matches)} eşleşme mavi ile gösteriliyor. (ESC: vurguyu kaldır)"

    def cmd_goto_matches(self):
        """Ctrl+G: Tüm eşleşmeler bulunur, ← → (veya ↑ ↓) ile aralarında gezilir."""
        self.selection.clear()
        query = self.prompt("Bul ve gez - kelime (Enter: bul, ESC: iptal): ", on_change=self.set_search)
        if not query:
            self.clear_search()
            self.message = "İptal edildi."
            return
        self.set_search(query)
        if not self.matches:
            self.clear_search()
            self.message = f"'{query}' bulunamadı."
            return

        index = self.first_match_from_cursor()
        total = len(self.matches)
        while True:
            self.current_match = index
            self.set_cursor(*self.matches[index])
            self.message = (f"Eşleşme {index + 1}/{total}   → ↓ : sonraki   ← ↑ : önceki   "
                            f"Enter/ESC : bitir")
            self.render()
            key = self.con.read_key()
            if key.name in ("RIGHT", "DOWN"):
                index = (index + 1) % total           # sondan sonra başa döner
            elif key.name in ("LEFT", "UP"):
                index = (index - 1) % total           # baştan önce sona döner
            elif key.name in ("ENTER", "ESC"):
                break
        self.clear_search()
        self.message = f"İmleç {index + 1}. eşleşmede bırakıldı."

    def cmd_replace(self):
        """Ctrl+H: önce aranan kelime, sonra yeni kelime girilir; tüm eşleşmeler değişir."""
        self.selection.clear()
        old = self.prompt("Değiştir - aranacak kelime (ESC: iptal): ", on_change=self.set_search)
        if not old:
            self.clear_search()
            self.message = "Değiştirme iptal edildi."
            return
        self.set_search(old)
        if not self.matches:
            self.clear_search()
            self.message = f"'{old}' bulunamadı."
            return
        new = self.prompt(f"'{old}' ({len(self.matches)} eşleşme) yerine yeni kelime (ESC: iptal): ")
        if new is None:
            self.clear_search()
            self.message = "Değiştirme iptal edildi."
            return
        count = self.replace_all(old, new)
        self.message = f"{count} eşleşme '{old}' → '{new}' olarak değiştirildi. (Ctrl+Z ile geri alınabilir)"

    def replace_all(self, old, new):
        matches = find_all(self.buf, old)
        self.begin_batch()
        # Sondan başa doğru değiştiriyoruz: böylece öndeki eşleşmelerin konumu kaymaz.
        for r, c in reversed(matches):
            self.edit_delete((r, c), (r, c + len(old)))
            if new:
                self.edit_insert((r, c), new)
        self.end_batch()
        self.clear_search()
        self.set_cursor(self.row, self.col)
        return len(matches)

    # ================================================================== #
    # Alt satırda kullanıcıdan metin alma / evet-hayır sorusu
    # ================================================================== #
    def prompt(self, label, on_change=None):
        """Mesaj satırında bir metin ister. Enter -> metni döndürür, ESC -> None."""
        self.prompt_label = label
        self.prompt_text = ""
        try:
            while True:
                if not self.con.has_input():
                    self.render()
                key = self.con.read_key()
                if key.name == "ESC":
                    return None
                if key.name == "ENTER":
                    return self.prompt_text
                if key.name == "BACKSPACE":
                    self.prompt_text = self.prompt_text[:-1]
                elif key.name == "CHAR":
                    self.prompt_text += key.char
                else:
                    continue
                if on_change:
                    on_change(self.prompt_text)
        finally:
            self.prompt_label = None

    def ask_yes_no(self, question):
        """y -> True, n -> False, ESC -> None"""
        self.prompt_label = question
        self.prompt_text = ""
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
            self.prompt_label = None

    # ================================================================== #
    # Dosya işlemleri
    # ================================================================== #
    def start_dir(self):
        if self.filepath:
            return os.path.dirname(os.path.abspath(self.filepath))
        return os.getcwd()

    def load_file(self, path):
        try:
            with open(path, "rb") as f:
                raw = f.read()
        except OSError as e:
            self.message = f"Dosya açılamadı: {e.strerror}"
            return False
        text = None
        for encoding in ("utf-8-sig", "cp1254"):    # önce UTF-8, olmazsa Türkçe Windows kodlaması
            try:
                text = raw.decode(encoding)
                break
            except UnicodeDecodeError:
                pass
        if text is None:
            text = raw.decode("latin-1")
        self.buf.set_text(text)
        self.filepath = os.path.abspath(path)
        self.undo_stack = Stack()
        self.saved_id = None
        self.can_merge = False
        self.selection.clear()
        self.clear_search()
        self.top = self.left = 0
        self.set_cursor(0, 0)
        self.message = f"Açıldı: {self.filepath}"
        return True

    def write_file(self, path):
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.buf.get_text())
        except OSError as e:
            self.message = f"Kaydedilemedi: {e.strerror}"
            return False
        self.filepath = os.path.abspath(path)
        top = self.undo_stack.peek()
        self.saved_id = top.id if top else None
        self.can_merge = False
        self.message = f"Kaydedildi: {self.filepath}"
        return True

    def cmd_save(self, save_as=False):
        """Dosya Kaydet: dosya önceden kaydedildiyse dosya yöneticisi AÇILMAZ.
        Farklı Kaydet: her zaman dosya yöneticisi açılır."""
        if self.filepath and not save_as:
            return self.write_file(self.filepath)
        initial = os.path.basename(self.filepath) if self.filepath else "yeni_dosya.txt"
        path = FileManager(self.con, self.start_dir()).run("save", initial)
        if path is None:
            self.message = "Kaydetme iptal edildi."
            return False
        return self.write_file(path)

    def cmd_open(self):
        if self.modified:
            answer = self.ask_yes_no("Kaydedilmemiş değişiklikler var. Kaydetmek istiyor musunuz? (y/n) ")
            if answer is None:
                self.message = "Dosya açma iptal edildi."
                return
            if answer and not self.cmd_save():
                return
        path = FileManager(self.con, self.start_dir()).run("open")
        if path is None:
            self.message = "Dosya açma iptal edildi."
            return
        self.load_file(path)

    def cmd_exit(self):
        """ESC: Kaydedilmemişse 'Kaydetmek istiyor musunuz? (y/n)' sorulur."""
        if not self.modified:
            self.running = False
            return
        answer = self.ask_yes_no("Kaydetmek istiyor musunuz? (y/n) ")
        if answer is None:
            self.message = "Çıkış iptal edildi."
            return
        if answer and not self.cmd_save():
            return                 # kaydetme iptal edildiyse çıkma
        self.running = False

    def on_escape(self):
        if self.matches:           # önce arama vurgusu varsa onu kaldır
            self.clear_search()
            self.message = "Arama vurgusu kaldırıldı. Çıkmak için tekrar ESC."
        else:
            self.cmd_exit()

    # ================================================================== #
    # Tuş yönlendirme
    # ================================================================== #
    def handle_key(self, key):
        n = key.name
        if n == "RESIZE":
            return
        if n == "CHAR":
            self.type_char(key.char)
            return

        self.can_merge = False

        if key.ctrl and len(n) == 1:           # Ctrl + harf kısayolları
            if n == "O":
                self.cmd_open()
            elif n == "S":
                self.cmd_save(save_as=key.shift)   # Ctrl+Shift+S -> Farklı Kaydet
            elif n == "F":
                self.cmd_find()
            elif n == "G":
                self.cmd_goto_matches()
            elif n == "H":
                self.cmd_replace()
            elif n == "C":
                self.copy()
            elif n == "X":
                self.copy(cut=True)
            elif n == "V":
                self.paste()
            elif n == "Z":
                self.undo()
            return

        if n in ("LEFT", "RIGHT", "UP", "DOWN", "HOME", "END", "PGUP", "PGDN"):
            self.move_cursor(key)
        elif n == "ENTER":
            self.insert_at_cursor("\n")        # yeni satır -> satır numarası artar
        elif n == "TAB":
            self.insert_at_cursor(TAB_SPACES)
        elif n == "BACKSPACE":
            self.backspace(word=key.ctrl)
        elif n == "DELETE":
            self.delete_forward()
        elif n == "ESC":
            self.on_escape()

    def run(self):
        self.con.start()
        try:
            while self.running:
                if not self.con.has_input():   # bekleyen tuş yoksa ekranı çiz
                    self.render()
                key = self.con.read_key()
                if key.name != "RESIZE":
                    self.message = ""
                self.handle_key(key)
        finally:
            self.con.stop()

    # ================================================================== #
    # Ekrana çizim
    # ================================================================== #
    def build_toolbox(self, width):
        """Komutları yan yana dizer; satıra sığmayan bir sonraki satıra geçer."""
        tokens = []        # her token: [(stil, metin), ...]
        for title, items in TOOLBOX:
            tokens.append([(ansi.TOOL_TITLE, f"[{title}]")])
            for name, shortcut in items:
                tokens.append([(ansi.TOOLBAR, name + " "), (ansi.TOOL_KEY, f"({shortcut})")])

        lines, current, used = [], [], 0
        for token in tokens:
            length = sum(len(t) for _, t in token)
            sep = 2 if current else 1
            if current and used + sep + length > width:   # sığmadı -> yeni satır
                lines.append((current, used))
                current, used, sep = [], 0, 1
            current.append((ansi.TOOLBAR, " " * sep))
            current.extend(token)
            used += sep + length
        lines.append((current, used))

        result = []
        for segments, _ in lines:
            out, count = [], 0
            for style, text in segments:
                text = text[:max(0, width - count)]     # çok dar pencerede kes
                out.append(style + text)
                count += len(text)
            out.append(ansi.TOOLBAR + " " * (width - count) + ansi.RESET)
            result.append("".join(out))
        return result

    def scroll_to_cursor(self, text_h, text_w):
        if self.row < self.top:
            self.top = self.row
        if self.row >= self.top + text_h:
            self.top = self.row - text_h + 1
        if self.col < self.left:
            self.left = self.col
        if self.col >= self.left + text_w:
            self.left = self.col - text_w + 1

    def render_line(self, r, text_w, sel, match_map, match_len):
        """Bir satırı, seçim (sarı) ve eşleşme (mavi) renkleriyle çizer."""
        line = self.buf.lines[r]
        n = len(line)
        styles = [None] * (n + 1)          # +1: satır sonu karakteri (seçiliyse gösterilir)
        for c, is_current in match_map.get(r, []):
            style = ansi.CURRENT_MATCH if is_current else ansi.MATCH
            for k in range(c, min(c + match_len, n)):
                styles[k] = style
        if sel:                             # seçim, arama renginin üstüne yazar
            (r1, c1), (r2, c2) = sel
            if r1 <= r <= r2:
                a = c1 if r == r1 else 0
                b = c2 if r == r2 else n + 1
                for k in range(a, b):
                    styles[k] = ansi.SELECT

        chars = line + [" "]
        out, prev = [], None
        for k in range(self.left, min(n + 1, self.left + text_w)):
            if k == n and styles[k] is None:
                break
            if styles[k] != prev:
                out.append(ansi.RESET + (styles[k] or ""))
                prev = styles[k]
            out.append(chars[k])
        out.append(ansi.RESET)
        return "".join(out)

    def render(self):
        cols, rows = self.con.size()
        toolbox = self.build_toolbox(cols)
        text_top = len(toolbox) + 2                # metin alanının ilk ekran satırı (1 tabanlı)
        text_h = max(1, rows - len(toolbox) - 3)   # şerit + ayraç + durum + mesaj
        self.page_h = max(1, text_h - 1)
        num_w = max(3, len(str(self.buf.line_count())))
        gutter_w = num_w + 4                       # " 123 │ "
        text_w = max(1, cols - gutter_w)
        self.scroll_to_cursor(text_h, text_w)

        sel = self.sel_range() if self.selection.is_active() else None
        # Sadece ekranda görünen satırlardaki eşleşmeleri al. Eşleşme listesi (satır, sütun)
        # sırasına göre sıralı olduğundan ikili arama (bisect) ile O(log k) sürede bulunur.
        match_map = {}
        first = bisect_left(self.matches, (self.top, 0))
        last = bisect_left(self.matches, (self.top + text_h, 0))
        for i in range(first, last):
            r, c = self.matches[i]
            match_map.setdefault(r, []).append((c, i == self.current_match))

        out = [ansi.HIDE_CURSOR]
        for i, line in enumerate(toolbox):
            out.append(ansi.goto(i + 1, 1) + line)
        out.append(ansi.goto(len(toolbox) + 1, 1) + ansi.SEPARATOR + "─" * cols + ansi.RESET)

        for i in range(text_h):
            r = self.top + i
            out.append(ansi.goto(text_top + i, 1))
            if r < self.buf.line_count():
                out.append(ansi.GUTTER + f" {r + 1:>{num_w}} │ " + ansi.RESET)
                out.append(self.render_line(r, text_w, sel, match_map, len(self.search_text)))
            out.append(ansi.CLEAR_EOL)

        # Durum çubuğu
        name = self.filepath or "Yeni Dosya (kaydedilmedi)"
        flag = "  [değiştirildi]" if self.modified else ""
        right = f"   Satır {self.row + 1}/{self.buf.line_count()}  Sütun {self.col + 1}  UTF-8 "
        if self.selection.is_active():
            right = f"   Seçim: {self.selection.length()} karakter" + right
        left_w = max(0, cols - len(right))
        status = ansi.fit_tail(f" {name}{flag}", left_w) + right
        out.append(ansi.goto(rows - 1, 1) + ansi.STATUS + ansi.fit(status, cols) + ansi.RESET)

        # Mesaj / giriş satırı
        if self.prompt_label is not None:
            visible = self.prompt_text[-max(1, cols - len(self.prompt_label) - 1):]
            out.append(ansi.goto(rows, 1) + ansi.MESSAGE + self.prompt_label[:cols]
                       + ansi.PROMPT_TEXT + visible + ansi.RESET + ansi.CLEAR_EOL)
            cursor = (rows, min(cols, len(self.prompt_label) + len(visible) + 1))
        else:
            out.append(ansi.goto(rows, 1) + ansi.MESSAGE + ansi.fit(self.message, cols)
                       + ansi.RESET + ansi.CLEAR_EOL)
            cursor = (text_top + self.row - self.top, gutter_w + self.col - self.left + 1)

        out.append(ansi.goto(*cursor) + ansi.SHOW_CURSOR)
        self.con.write("".join(out))
