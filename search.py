"""Metin arama: KMP (Knuth-Morris-Pratt) string eşleşme algoritması.

Neden KMP?
  Basit (naif) aramada bir uyuşmazlıkta metinde geri dönülür: en kötü durum O(n*m).
  KMP, aranan kelimenin kendi içindeki tekrarları önceden "LPS tablosu"nda hesaplar;
  uyuşmazlıkta metinde hiç geri gitmez. Toplam süre O(n + m).
    n = metin uzunluğu, m = aranan kelime uzunluğu
"""


def build_lps(pattern):
    """LPS (Longest Prefix which is also Suffix) tablosu.
    lps[i] = pattern[0..i] içinde, hem önek hem sonek olan en uzun parçanın uzunluğu.
    Örnek: "ABAB" -> [0, 0, 1, 2]
    """
    lps = [0] * len(pattern)
    length = 0          # şu ana kadarki en uzun önek-sonek uzunluğu
    i = 1
    while i < len(pattern):
        if pattern[i] == pattern[length]:
            length += 1
            lps[i] = length
            i += 1
        elif length != 0:
            length = lps[length - 1]   # daha kısa bir önek dene (i artmaz)
        else:
            lps[i] = 0
            i += 1
    return lps


def kmp_search(text, pattern):
    """text içinde pattern'in geçtiği TÜM başlangıç indekslerini döndürür.
    text bir string ya da karakter listesi olabilir."""
    if not pattern:
        return []
    lps = build_lps(pattern)
    result = []
    i = j = 0           # i: metindeki konum, j: kelimedeki konum
    while i < len(text):
        if text[i] == pattern[j]:
            i += 1
            j += 1
            if j == len(pattern):          # tam eşleşme bulundu
                result.append(i - j)
                j = lps[j - 1]             # aramaya devam
        elif j != 0:
            j = lps[j - 1]                 # metinde geri gitmeden kelimede kaydır
        else:
            i += 1
    return result


def find_all(buffer, pattern):
    """Tüm satırlarda arama yapar, eşleşmeleri [(satır, sütun), ...] listesi olarak döndürür.
    Çakışan eşleşmeler elenir (örn. "aaa" içinde "aa" -> sadece 0. konum),
    böylece değiştirme işlemi tutarlı olur."""
    matches = []
    if not pattern or "\n" in pattern:
        return matches
    for row, line in enumerate(buffer.lines):
        last_end = -1
        for col in kmp_search(line, pattern):
            if col >= last_end:
                matches.append((row, col))
                last_end = col + len(pattern)
    return matches
