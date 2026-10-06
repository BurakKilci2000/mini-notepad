"""Seçili metnin takibi.

Proje şartı: "Seçili metin başlangıç ve bitiş indeksleri ile takip edilmelidir."
  start -> seçimin başladığı (sabit kalan) doğrusal indeks
  end   -> imlecin o an bulunduğu (hareket eden) doğrusal indeks
Kullanıcı sola doğru seçerse end < start olabilir; ordered() bunları sıraya koyar.
"""


class Selection:
    def __init__(self):
        self.start = None
        self.end = None

    def begin(self, index):
        """Seçim yoksa, imlecin şu anki konumundan yeni seçim başlatır."""
        if self.start is None:
            self.start = index
            self.end = index

    def update(self, index):
        """İmleç hareket ettikçe seçimin bitişini günceller."""
        self.end = index

    def clear(self):
        self.start = None
        self.end = None

    def is_active(self):
        """Gerçekten seçili en az bir karakter var mı?"""
        return self.start is not None and self.start != self.end

    def ordered(self):
        """(küçük indeks, büyük indeks) olarak döndürür."""
        return min(self.start, self.end), max(self.start, self.end)

    def length(self):
        a, b = self.ordered()
        return b - a
