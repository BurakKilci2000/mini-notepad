"""Klavyeden okunan tuşları temsil eden sınıf (platformdan bağımsız)."""


class Key:
    """Tek bir tuş olayı.

    name alanı şunlardan biridir:
      'CHAR'      -> yazılabilir bir karakter (char alanında tutulur, örn. 'ğ')
      'UP', 'DOWN', 'LEFT', 'RIGHT', 'HOME', 'END', 'PGUP', 'PGDN'
      'ENTER', 'TAB', 'BACKSPACE', 'DELETE', 'ESC'
      'RESIZE'    -> konsol penceresinin boyutu değişti
      'A'..'Z'    -> Ctrl ile birlikte basılmış bir harf (örn. Ctrl+F -> name='F', ctrl=True)
    """

    def __init__(self, name, char="", ctrl=False, shift=False, alt=False):
        self.name = name
        self.char = char
        self.ctrl = ctrl
        self.shift = shift
        self.alt = alt

    def __repr__(self):
        mods = ("Ctrl+" if self.ctrl else "") + ("Shift+" if self.shift else "") + ("Alt+" if self.alt else "")
        return f"Key({mods}{self.name}{' ' + repr(self.char) if self.char else ''})"
