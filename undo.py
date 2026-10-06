"""Geri alma (Undo) mekanizması.

Proje şartı: "Undo işlemi için ek bir stack yapısı tasarlanmalıdır."

Tasarım: Metnin her halini (kopyasını) saklamak yerine yalnızca YAPILAN İŞLEMİ saklıyoruz.
  * INSERT (ekleme)  : nereye, hangi metin eklendi      -> geri alırken o metni sileriz
  * DELETE (silme)   : nereden, hangi metin silindi     -> geri alırken o metni geri ekleriz
  * BATCH  (toplu)   : birden fazla işlem (örn. Ctrl+H ile "tümünü değiştir")
                       -> tek Ctrl+Z ile hepsi tersten geri alınır
Bu yaklaşım bellek açısından çok verimlidir: 1 karakter yazınca sadece 1 karakter saklanır.
"""

INSERT = "insert"
DELETE = "delete"
BATCH = "batch"


class Stack:
    """Liste tabanlı LIFO (son giren ilk çıkar) yığın. push/pop/peek işlemleri O(1)."""

    def __init__(self, max_size=1000):
        self._items = []
        self.max_size = max_size

    def push(self, item):
        self._items.append(item)
        if len(self._items) > self.max_size:   # bellek sınırı: en eski kaydı at
            self._items.pop(0)

    def pop(self):
        if self.is_empty():
            return None
        return self._items.pop()

    def peek(self):
        """En üstteki elemanı çıkarmadan döndürür."""
        if self.is_empty():
            return None
        return self._items[-1]

    def is_empty(self):
        return len(self._items) == 0

    def size(self):
        return len(self._items)


class Action:
    """Yığına konulan tek bir düzenleme kaydı."""
    _next_id = 1   # her kayda benzersiz numara (dosyanın kaydedilip kaydedilmediğini anlamak için)

    def __init__(self, kind, pos=None, text="", cursor_before=(0, 0), children=None):
        self.kind = kind                    # INSERT / DELETE / BATCH
        self.pos = pos                      # işlemin yapıldığı (satır, sütun)
        self.text = text                    # eklenen ya da silinen metin
        self.cursor_before = cursor_before  # geri alınca imlecin döneceği yer
        self.children = children or []     # BATCH için alt işlemler
        self.id = Action._next_id
        Action._next_id += 1
