"""Uçtan uca otomatik testler.

Editör, gerçek konsol yerine tuşları sırayla veren sahte bir konsolla (FakeConsole) çalıştırılır.
Her senaryodan sonra metin, imleç, pano, diske yazılan dosya veya ekran karesi kontrol edilir.
Çalıştırma (proje kök klasöründen):  python tests/test_editor.py
"""
import sys, os, re, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from keys import Key
from editor import Editor
from search import kmp_search, build_lps

class FakeConsole:
    def __init__(self, keys, size=(80, 24)):
        self.keys = list(keys); self._size = size; self.frame = ""; self.clip = None
    def start(self): pass
    def stop(self): pass
    def write(self, s): self.frame = s
    def size(self): return self._size
    def has_input(self): return bool(self.keys)
    def read_key(self):
        if not self.keys: raise SystemExit("keys exhausted")
        return self.keys.pop(0)
    def set_clipboard(self, t): self.clip = t
    def get_clipboard(self): return self.clip

def screen(frame, cols=80, rows=24):
    grid = [[" "]*cols for _ in range(rows)]
    r=c=0; i=0
    while i < len(frame):
        if frame[i]=="\x1b":
            m = re.match(r"\x1b\[(\d+);(\d+)H", frame[i:])
            if m: r=int(m.group(1))-1; c=int(m.group(2))-1; i+=m.end(); continue
            m = re.match(r"\x1b\[[0-9;?]*[A-Za-z]", frame[i:])
            if m:
                if m.group(0)=="\x1b[K":
                    for k in range(c,cols): grid[r][k]=" "
                i+=m.end(); continue
            i+=1; continue
        if r<rows and c<cols: grid[r][c]=frame[i]
        c+=1; i+=1
    return "\n".join("".join(x).rstrip() for x in grid)

def T(s): return [Key("ENTER") if ch=="\n" else Key("CHAR", char=ch) for ch in s]
def C(letter, shift=False): return Key(letter, ctrl=True, shift=shift)
def K(name, ctrl=False, shift=False): return Key(name, ctrl=ctrl, shift=shift)

def run(keys, size=(80,24)):
    con = FakeConsole(keys, size); ed = Editor(con)
    try: ed.run()
    except SystemExit: pass
    return ed, con

ok = True
def check(name, cond):
    global ok
    print(("PASS " if cond else "FAIL ") + name); ok &= bool(cond)

# KMP
check("lps", build_lps("ABAB")==[0,0,1,2] and build_lps("AABAACAABAA")==[0,1,0,1,2,0,1,2,3,4,5])
check("kmp", kmp_search("ababcabab","abab")==[0,5] and kmp_search(list("aaaa"),"aa")==[0,1,2])

# Typing Turkish + lines
ed,_ = run(T("Merhaba dünya\nŞişli ığdır çöğüş\nüç"))
check("typing", ed.buf.get_text()=="Merhaba dünya\nŞişli ığdır çöğüş\nüç" and (ed.row,ed.col)==(2,2))

# Backspace & ctrl+backspace & line join
ed,_ = run(T("abc def ghi") + [K("BACKSPACE",ctrl=True)] + [K("BACKSPACE")])
check("ctrl+backspace", ed.buf.get_text()=="abc def")
ed,_ = run(T("ab\ncd") + [K("HOME"), K("BACKSPACE")])
check("line join", ed.buf.get_text()=="abcd" and ed.buf.line_count()==1)

# Selection char + copy + paste
ed,con = run(T("merhaba dünya") + [K("HOME")] + [K("RIGHT",ctrl=True)]*7 + [C("C"), K("END")] + T(" ") + [C("V")])
check("char select copy paste", ed.buf.get_text()=="merhaba dünya merhaba" and con.clip=="merhaba")

# Word selection + cut
ed,con = run(T("bir iki üç") + [K("HOME"), K("RIGHT",ctrl=True,shift=True), K("RIGHT",ctrl=True,shift=True), C("X")])
check("word select cut", ed.buf.get_text()=="üç" and con.clip=="bir iki ")

# Word select leftwards
ed,con = run(T("bir iki üç") + [K("LEFT",ctrl=True,shift=True)]*2 + [C("C")])
check("word select left", con.clip=="iki üç")

# typing replaces selection
ed,_ = run(T("hello world") + [K("LEFT",ctrl=True,shift=True)] + T("dünya"))
check("type over selection", ed.buf.get_text()=="hello dünya")

# Undo merge granularity
ed,_ = run(T("bir iki") + [C("Z")])
check("undo word", ed.buf.get_text()=="bir ")
ed,_ = run(T("bir iki") + [C("Z")]*10)
check("undo all", ed.buf.get_text()=="" and not ed.modified)
ed,_ = run(T("abc\ndef") + [K("UP"), K("END"), K("DELETE"), C("Z")])
check("undo delete join", ed.buf.get_text()=="abc\ndef")

# Replace all + undo
keys = T("kedi ve kedi ile kedicik") + [C("H")] + T("kedi") + [K("ENTER")] + T("köpek") + [K("ENTER")]
ed,_ = run(keys)
check("replace", ed.buf.get_text()=="köpek ve köpek ile köpekcik")
ed,_ = run(keys + [C("Z")])
check("replace undo one step", ed.buf.get_text()=="kedi ve kedi ile kedicik")
ed,_ = run(T("kedi kedi") + [C("H")] + T("kedi") + [K("ESC")])
check("replace esc cancel", ed.buf.get_text()=="kedi kedi")
ed,_ = run(T("kedi kedi") + [C("H")] + T("kedi") + [K("ENTER"), K("ESC")])
check("replace esc at 2nd", ed.buf.get_text()=="kedi kedi")

# Find highlights
ed,con = run(T("ali veli ali\nali") + [C("F")] + T("ali") + [K("ENTER")])
check("find matches", ed.matches==[(0,0),(0,9),(1,0)] and "\x1b[97;44m" in con.frame)
# ESC clears highlight first, doesn't exit
ed,con = run(T("ali") + [C("F")] + T("ali") + [K("ENTER"), K("ESC")])
check("esc clears search", ed.matches==[] and ed.running)

# Ctrl+G navigation
ed,_ = run(T("a x a x a") + [K("HOME"), C("G")] + T("a") + [K("ENTER"), K("RIGHT"), K("RIGHT"), K("ENTER")])
check("ctrl+g next", (ed.row,ed.col)==(0,8))
ed,_ = run(T("a x a x a") + [K("HOME"), C("G")] + T("a") + [K("ENTER"), K("LEFT"), K("ENTER")])
check("ctrl+g wrap prev", (ed.row,ed.col)==(0,8))

# Line numbers render & dynamic
ed,con = run(T("a\nb\nc"))
s = screen(con.frame)
check("line numbers 3", "  3 │ c" in s)
ed,con = run(T("a\nb\nc") + [K("HOME"), K("BACKSPACE")])
s = screen(con.frame)
check("line numbers decrease", "  3 │" not in s and "  2 │ bc" in s)

# Toolbox wrap
ed,con = run(T("x"), size=(80,24))
s = screen(con.frame).split("\n")
check("toolbox shows shortcuts", "Dosya Aç (Ctrl+O)" in s[0] and any("(ESC)" in l for l in s[:8]))

# Save as via filemanager, then exit
tmp = tempfile.mkdtemp(); os.chdir(tmp); os.mkdir("alt klasör")
ed,con = run(T("İçerik ğüşıöç") + [C("S")] + [K("BACKSPACE")]*20 + T("deneme.txt") + [K("ENTER")])
check("save new", open(os.path.join(tmp,"deneme.txt"),encoding="utf-8").read()=="İçerik ğüşıöç" and not ed.modified)
# Ctrl+S after saved: no file manager
ed2 = ed; ed2.con.keys = T("!") + [C("S")]
try: ed2.run()
except SystemExit: pass
check("save existing no fm", open(os.path.join(tmp,"deneme.txt"),encoding="utf-8").read()=="İçerik ğüşıöç!")
# save-as into subfolder via RIGHT navigation
ed,con = run(T("x") + [C("S",shift=True), K("DOWN"), K("RIGHT")] + [K("BACKSPACE")]*20 + T("a.txt") + [K("ENTER")])
check("save as subfolder", os.path.exists(os.path.join(tmp,"alt klasör","a.txt")))
# go back with LEFT
ed,con = run(T("y") + [C("S",shift=True), K("DOWN"), K("RIGHT"), K("LEFT")] + [K("BACKSPACE")]*20 + T("b.txt") + [K("ENTER")])
check("filemanager back", os.path.exists(os.path.join(tmp,"b.txt")))
# overwrite prompt
ed,con = run(T("zzz") + [C("S")] + [K("BACKSPACE")]*20 + T("b.txt") + [K("ENTER")] + T("y"))
check("overwrite confirm", open(os.path.join(tmp,"b.txt"),encoding="utf-8").read()=="zzz")
# Open file
ed,con = run([C("O")] + [K("DOWN")]*10 + [K("BACKSPACE")]*30 + T("deneme.txt") + [K("ENTER")])
check("open", ed.buf.get_text()=="İçerik ğüşıöç!" and ed.filepath.endswith("deneme.txt"))

# Filemanager render
con = FakeConsole([C("O")]); e = Editor(con)
try: e.run()
except SystemExit: pass

# Exit flows
ed,_ = run([K("ESC")])
check("exit clean", not ed.running)
ed,con = run(T("abc") + [K("ESC")])
check("exit asks", ed.running and "Kaydetmek istiyor musunuz? (y/n)" in screen(con.frame))
ed,_ = run(T("abc") + [K("ESC")] + T("n"))
check("exit no", not ed.running)
ed,_ = run(T("abc") + [K("ESC")] + T("y") + [K("BACKSPACE")]*20 + T("cikis.txt") + [K("ENTER")])
check("exit yes saves", not ed.running and os.path.exists(os.path.join(tmp,"cikis.txt")))

# Selection render yellow
ed,con = run(T("abc def") + [K("LEFT",ctrl=True)]*3)
check("selection yellow", "\x1b[30;103mdef" in con.frame)
# Multi-line selection + copy
ed,con = run(T("ab\ncd") + [K("UP", ctrl=True), C("C")])
check("multiline select", con.clip=="\ncd")
# Scrolling long file
ed,con = run(T("\n".join(str(i) for i in range(100))), size=(60,20))
s = screen(con.frame, 60, 20)
check("scroll", " 100 │ 99" in s)
# narrow window wrap
ed,con = run(T("x"), size=(40,20))
print("TÜM TESTLER GEÇTİ" if ok else "BAZI TESTLER BAŞARISIZ")
sys.exit(0 if ok else 1)
