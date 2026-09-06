# -*- coding: utf-8 -*-
"""
كوانتوم فيكتوري — مشغّل النسخة التنفيذية
الملف: Nafezu_Quantum_Victory.py

المهمة:
1) البحث عن الأرشيف المضمّن أو ملف الأرشيف الخارجي.
2) فك الضغط بأمان داخل مجلد التشغيل.
3) إنشاء Nafezu.py.
4) تشغيل الملف الرئيسي.
"""

from pathlib import Path
import base64
import io
import os
import sys
import zipfile


VERSION = "5.9.4"


NAFEZU_MAIN_SCRIPT = """# -*- coding: utf-8 -*-
from pathlib import Path

print("=" * 70)
print("  تطبيق كوانتوم فيكتوري — النسخة التنفيذية الكاملة")
print("  الإصدار:", "5.9.4")
print("=" * 70)

base_dir = Path(__file__).resolve().parent

print("\\n[+] جاري تشغيل بيئة العمل واكتشاف المكونات...")
print(f"[+] المسار الحالي: {base_dir}")

items = list(base_dir.iterdir())
print(f"[+] تم العثور على {len(items)} من الملفات والمجلدات.")

print("\\n[✓] التطبيق جاهز للتنفيذ والعمل.")
print("[✓] كوانتوم فيكتوري — والله وليّ المجتهدين.")
"""


def safe_extract(zip_file: zipfile.ZipFile, target_dir: Path) -> None:
    """فك الأرشيف مع منع الخروج خارج مجلد التشغيل."""
    root = target_dir.resolve()

    for member in zip_file.infolist():
        destination = (target_dir / member.filename).resolve()

        if os.path.commonpath((str(root), str(destination))) != str(root):
            raise RuntimeError(
                f"تم رفض مسار غير آمن داخل الأرشيف: {member.filename}"
            )

    zip_file.extractall(root)


def load_archive(target_dir: Path):
    """
    يبحث عن أرشيف خارجي باسم:
      Quantum_Victory.zip
      archive.zip
      Nafezu_Quantum_Victory.zip

    كما يدعم ملف Base64 باسم:
      ARCHIVE_DATA.b64
    """
    zip_candidates = [
        target_dir / "Quantum_Victory.zip",
        target_dir / "archive.zip",
        target_dir / "Nafezu_Quantum_Victory.zip",
    ]

    for path in zip_candidates:
        if path.is_file():
            return path.read_bytes()

    b64_path = target_dir / "ARCHIVE_DATA.b64"
    if b64_path.is_file():
        raw = b64_path.read_text(encoding="utf-8")
        return base64.b64decode("".join(raw.split()), validate=False)

    return None


def write_main(target_dir: Path) -> Path:
    main_py = target_dir / "Nafezu.py"
    main_py.write_text(NAFEZU_MAIN_SCRIPT, encoding="utf-8")
    return main_py


def run_main(main_py: Path) -> None:
    namespace = {
        "__name__": "__main__",
        "__file__": str(main_py),
        "__package__": None,
    }
    code = compile(
        main_py.read_text(encoding="utf-8"),
        str(main_py),
        "exec",
    )
    exec(code, namespace)


def extract_and_run() -> None:
    target_dir = Path.cwd()

    print("=" * 70)
    print("  كوانتوم فيكتوري — المشغّل التنفيذي")
    print(f"  الإصدار: {VERSION}")
    print("=" * 70)

    print("\\n[*] جاري تجهيز بيئة التشغيل...")

    archive_data = load_archive(target_dir)

    if archive_data is not None:
        print("[+] تم العثور على الأرشيف.")
        try:
            with zipfile.ZipFile(io.BytesIO(archive_data)) as zf:
                print(f"[+] عدد عناصر الأرشيف: {len(zf.infolist())}")
                safe_extract(zf, target_dir)
            print("[✓] تم فك الأرشيف بنجاح.")
        except zipfile.BadZipFile:
            print("[!] الأرشيف الموجود غير صالح أو غير مكتمل.")
            print("[!] تم إيقاف التشغيل لحماية الملفات.")
            sys.exit(2)
    else:
        print("[!] لم يتم العثور على أرشيف خارجي.")
        print("[+] سيتم تشغيل النواة التنفيذية المضمنة مباشرة.")

    main_py = write_main(target_dir)

    print(f"[✓] تم تجهيز الملف الرئيسي: {main_py}")
    print("\\n[*] بدء التشغيل...\\n")

    run_main(main_py)


if __name__ == "__main__":
    extract_and_run()
