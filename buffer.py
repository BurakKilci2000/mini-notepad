"""Metnin bellekte tutulduğu veri yapısı.

SEÇİLEN VERİ YAPISI: "Satır listesi" -> her satır da bir "karakter listesi".

    lines = [ ['M','e','r','h','a','b','a'],      # 1. satır
              ['D','ü','n','y','a'] ]             # 2. satır

Neden bu yapı?
  * Her karakter ayrı bir eleman olarak tutulur (proje şartı).
  * Python listesi dinamik dizidir: boyutu ihtiyaca göre büyür/küçülür (dinamik yönetim).
  * (satır, sütun) ile bir karaktere O(1) sürede erişilir -> imleç hareketi ve ekrana
    çizim çok hızlıdır.
  * Ekleme/silme sadece ilgili satırı etkiler: maliyet O(satır uzunluğu). Tek dev bir dizi
    kullansaydık her eklemede dosyanın geri kalanının tamamı kayardı.
  * Satır ekleme/silme, satır numaralarını otomatik günceller: satır numarası = liste indeksi + 1.
"""


class TextBuffer:
    def __init__(self, text=""):
        self.lines = [[]]
        self.set_text(text)

    # ------------------------------------------------------------------ #
    # Tüm metni yükleme / alma
    # ------------------------------------------------------------------ #
    def set_text(self, text):
        """Metni satırlara, satırları karakterlere böler."""
        text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\t", "    ")
        self.lines = [list(line) for line in text.split("\n")]

    def get_text(self):
        """Tüm metni tek bir string olarak döndürür (kaydetmek için)."""
        return "\n".join("".join(line) for line in self.lines)

    # ------------------------------------------------------------------ #
    # Basit sorgular
    # ------------------------------------------------------------------ #
    def line_count(self):
        return len(self.lines)

    def line_length(self, row):
        return len(self.lines[row])

    def line_str(self, row):
        return "".join(self.lines[row])

    # ------------------------------------------------------------------ #
    # Temel düzenleme işlemleri (bütün değişiklikler bu iki fonksiyondan geçer)
    # ------------------------------------------------------------------ #
    def insert_text(self, row, col, text):
        """text'i (row, col) konumuna ekler. Eklenen metnin BİTTİĞİ konumu döndürür.
        text içinde '\n' varsa satır bölünür ve yeni satırlar oluşur."""
        parts = text.split("\n")
        line = self.lines[row]
        tail = line[col:]            # imlecin sağında kalan karakterler
        del line[col:]
        line.extend(parts[0])

        if len(parts) == 1:          # tek satırlık ekleme
            line.extend(tail)
            return row, col + len(parts[0])

        # Çok satırlı ekleme: araya yeni satırlar girer
        new_lines = [list(p) for p in parts[1:]]
        end_row = row + len(parts) - 1
        end_col = len(new_lines[-1])
        new_lines[-1].extend(tail)   # kesilen kuyruk son satırın sonuna eklenir
        self.lines[row + 1:row + 1] = new_lines
        return end_row, end_col

    def delete_range(self, start, end):
        """start=(r1,c1) ile end=(r2,c2) arasındaki metni siler ve silinen metni döndürür.
        (Silinen metin, geri alma işlemi için saklanır.)"""
        deleted = self.get_range(start, end)
        (r1, c1), (r2, c2) = start, end
        if r1 == r2:
            del self.lines[r1][c1:c2]
        else:
            tail = self.lines[r2][c2:]
            del self.lines[r1][c1:]
            self.lines[r1].extend(tail)
            del self.lines[r1 + 1:r2 + 1]   # aradaki satırlar silinir -> numaralar azalır
        return deleted

    def get_range(self, start, end):
        """İki konum arasındaki metni string olarak döndürür."""
        (r1, c1), (r2, c2) = start, end
        if r1 == r2:
            return "".join(self.lines[r1][c1:c2])
        parts = ["".join(self.lines[r1][c1:])]
        for r in range(r1 + 1, r2):
            parts.append(self.line_str(r))
        parts.append("".join(self.lines[r2][:c2]))
        return "\n".join(parts)

    # ------------------------------------------------------------------ #
    # (satır, sütun) <-> doğrusal indeks dönüşümü
    # Seçim, proje şartı gereği başlangıç/bitiş İNDEKSLERİ ile tutulur.
    # Her satır sonundaki '\n' de 1 karakter sayılır.
    # ------------------------------------------------------------------ #
    def to_index(self, row, col):
        index = 0
        for r in range(row):
            index += len(self.lines[r]) + 1
        return index + col

    def from_index(self, index):
        for r, line in enumerate(self.lines):
            if index <= len(line):
                return r, index
            index -= len(line) + 1
        return len(self.lines) - 1, len(self.lines[-1])

    @staticmethod
    def end_of(start, text):
        """start konumuna text eklenseydi, metnin biteceği konum."""
        parts = text.split("\n")
        if len(parts) == 1:
            return start[0], start[1] + len(text)
        return start[0] + len(parts) - 1, len(parts[-1])
