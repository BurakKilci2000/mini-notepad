"""Mini Notepad++ - Konsol Tabanlı Metin Editörü
Programlama Laboratuvarı-II, Proje 1

Çalıştırma:   python main.py        (geliştirirken)
              main.exe              (PyInstaller ile derledikten sonra)
Başlangıçta doğrudan yeni, boş bir dosya açılır.
"""
import sys
import traceback


def main():
    if sys.platform != "win32":
        print("Bu uygulama Windows konsolu için yazılmıştır.")
        return

    from console import WindowsConsole
    from editor import Editor

    console = WindowsConsole()
    editor = Editor(console)
    try:
        editor.run()
    except Exception:
        console.stop()            # konsolu normal haline döndür, sonra hatayı göster
        traceback.print_exc()
        input("Beklenmeyen bir hata oluştu. Kapatmak için Enter'a basın...")


if __name__ == "__main__":
    main()
