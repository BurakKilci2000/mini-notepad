"""ANSI (VT100) kaçış dizileri: renkler, imleç konumlandırma ve metin hizalama yardımcıları.

Windows 10 ve sonrası konsollar, VT işleme modu açıldığında bu dizileri anlar.
Böylece harici bir GUI kütüphanesi kullanmadan renkli arka plan çizebiliyoruz.
"""

ESC = "\x1b"
RESET = ESC + "[0m"
HIDE_CURSOR = ESC + "[?25l"
SHOW_CURSOR = ESC + "[?25h"
CLEAR_EOL = ESC + "[K"            # imleçten satır sonuna kadar temizle
CLEAR_SCREEN = ESC + "[2J"

# Renk şablonları (ön plan;arka plan)
TOOLBAR = ESC + "[97;100m"        # şerit: beyaz yazı, gri arka plan
TOOL_TITLE = ESC + "[93;100;1m"   # şerit başlığı: sarı, kalın
TOOL_KEY = ESC + "[96;100m"       # kısayol: açık mavi (cyan)
GUTTER = ESC + "[90m"             # satır numaraları: koyu gri
SEPARATOR = ESC + "[90m"
SELECT = ESC + "[30;103m"         # SEÇİM: siyah yazı, SARI arka plan
MATCH = ESC + "[97;44m"           # ARAMA EŞLEŞMESİ: beyaz yazı, MAVİ arka plan
CURRENT_MATCH = ESC + "[97;104;1m"  # Ctrl+G ile üzerinde durulan eşleşme: açık mavi
STATUS = ESC + "[30;47m"          # durum çubuğu: siyah yazı, açık gri arka plan
MESSAGE = ESC + "[93m"            # bilgi mesajı: sarı
PROMPT_TEXT = ESC + "[97m"
LIST_SELECTED = ESC + "[30;46m"   # dosya yöneticisinde seçili satır
DIR_COLOR = ESC + "[96m"          # klasör isimleri
TITLE_BAR = ESC + "[97;44;1m"


def goto(row, col):
    """İmleci (satır, sütun) konumuna taşır. ANSI'de konumlar 1'den başlar."""
    return f"{ESC}[{row};{col}H"


def fit(text, width):
    """Metni tam olarak 'width' karakter genişliğe getirir (fazlasını keser, eksiğini boşlukla doldurur)."""
    if width <= 0:
        return ""
    text = text[:width]
    return text + " " * (width - len(text))


def fit_tail(text, width):
    """Uzun metinlerin SONUNU gösterir (uzun dosya yolları için kullanışlı)."""
    if width <= 0:
        return ""
    if len(text) > width:
        text = "…" + text[-(width - 1):]
    return fit(text, width)
