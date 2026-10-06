"""Deneysel sonuçlar için performans ölçümleri. Çalıştırma: python bench.py
(Konsol gerektirmez; ekran çizimi sahte bir konsol nesnesiyle ölçülür.)"""
import platform
import random
import sys
import time

from buffer import TextBuffer
from editor import Editor
from keys import Key
from search import find_all, kmp_search
from undo import Action, INSERT

random.seed(42)


def naive_search(text, pattern):
    res, n, m = [], len(text), len(pattern)
    for i in range(n - m + 1):
        j = 0
        while j < m and text[i + j] == pattern[j]:
            j += 1
        if j == m:
            res.append(i)
    return res


def timeit(fn, repeat=3):
    best = float("inf")
    for _ in range(repeat):
        t = time.perf_counter()
        fn()
        best = min(best, time.perf_counter() - t)
    return best


class FakeConsole:
    def __init__(self, cols=120, rows=30):
        self._size = (cols, rows)
        self.bytes = 0
    def write(self, s): self.bytes = len(s)
    def size(self): return self._size
    def set_clipboard(self, t): pass
    def get_clipboard(self): return None


WORDS = "kocaeli üniversitesi bilgisayar mühendisliği metin editörü arama değiştir geri al çğışöü".split()


def make_text(lines, words_per_line=10):
    return "\n".join(" ".join(random.choice(WORDS) for _ in range(words_per_line)) for _ in range(lines))


print(f"Python {platform.python_version()} | {platform.system()} {platform.release()} | {platform.processor() or platform.machine()}")

# 1) KMP vs naif arama (en kötü durum: "aaaa...a" içinde "aaa...ab")
print("\n[1] KMP vs naif arama (en kötü durum, m=50)")
for n in (10_000, 50_000, 100_000):
    text, pat = "a" * n, "a" * 49 + "b"
    tk = timeit(lambda: kmp_search(text, pat))
    tn = timeit(lambda: naive_search(text, pat), repeat=1)
    print(f"  n={n:>7}: KMP {tk*1000:8.2f} ms | naif {tn*1000:9.2f} ms | hızlanma x{tn/tk:.1f}")

# 2) find_all: gerçekçi metinde arama
print("\n[2] find_all (her satır ~10 kelime)")
for lines in (1_000, 10_000, 50_000):
    buf = TextBuffer(make_text(lines))
    chars = len(buf.get_text())
    t = timeit(lambda: find_all(buf, "editörü"))
    print(f"  {lines:>6} satır ({chars/1e6:.2f} M karakter): {t*1000:8.2f} ms, {len(find_all(buf,'editörü'))} eşleşme")

# 3) Ekleme maliyeti: satır listesi vs tek parça string
print("\n[3] 1000 karakter ekleme, dosyanın ortasına")
for lines in (1_000, 10_000, 50_000):
    text = make_text(lines)
    buf = TextBuffer(text)
    mid = lines // 2
    def ins_buf():
        for i in range(1000):
            buf.insert_text(mid, 5, "x")
    s = [text]
    pos = len(text) // 2
    def ins_str():
        for i in range(1000):
            s[0] = s[0][:pos] + "x" + s[0][pos:]
    tb, ts = timeit(ins_buf, 1), timeit(ins_str, 1)
    print(f"  {lines:>6} satır: satır-listesi {tb*1e6/1000:7.2f} µs/işlem | tek string {ts*1e6/1000:8.2f} µs/işlem")

# 4) Undo bellek: işlem kaydı vs anlık görüntü (snapshot)
print("\n[4] Undo bellek kullanımı (1000 düzenleme)")
for lines in (100, 1_000, 5_000):
    text = make_text(lines)
    action_bytes = sum(sys.getsizeof(Action(INSERT, (0, i), "x")) + sys.getsizeof("x") for i in range(1000))
    snapshot_bytes = 1000 * sys.getsizeof(text)
    print(f"  {len(text)/1e3:7.1f} KB dosya: işlem kaydı {action_bytes/1e3:8.1f} KB | snapshot {snapshot_bytes/1e6:8.2f} MB")

# 5) Değiştir (Ctrl+H) + geri alma
print("\n[5] Tümünü değiştir + tek adımda geri al")
for lines in (1_000, 10_000):
    ed = Editor(FakeConsole())
    ed.buf.set_text(make_text(lines))
    original = ed.buf.get_text()
    n = len(find_all(ed.buf, "arama"))
    tr = timeit(lambda: ed.replace_all("arama", "ARAMA"), 1)
    tu = timeit(ed.undo, 1)
    print(f"  {lines:>6} satır, {n} eşleşme: değiştir {tr*1000:7.1f} ms | geri al {tu*1000:7.1f} ms | geri dönüş doğru: {ed.buf.get_text()==original}")

# 6) Ekran çizimi
print("\n[6] Bir ekran karesi çizimi (120x30)")
for lines in (100, 10_000, 50_000):
    ed = Editor(FakeConsole())
    ed.buf.set_text(make_text(lines))
    ed.set_cursor(lines // 2, 0)
    t = timeit(lambda: [ed.render() for _ in range(50)]) / 50
    ed.set_search("editörü")
    ts = timeit(lambda: [ed.render() for _ in range(50)]) / 50
    print(f"  {lines:>6} satır: {t*1000:6.2f} ms/kare | arama vurgulu {ts*1000:6.2f} ms/kare | kare {ed.con.bytes} karakter")
