#!/usr/bin/env python3
"""Tạo HOME giả để kiểm thử Spotless Mac: python3 tests/make_fake_home.py /tmp/fh"""
import os, sys, time, shutil, zipfile
root = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "/tmp/fh")
shutil.rmtree(root, ignore_errors=True)
J = lambda *p: os.path.join(root, *p)
for d in ["Desktop", "Documents/Project/src", "Downloads/Old folder", "Pictures", ".Trash", "Library/Caches/BigApp",
          "Library/Keychains", "Library/Logs", ".ssh", "Movies"]:
    os.makedirs(J(d), exist_ok=True)
try:
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (800, 500), (30, 120, 220)); d = ImageDraw.Draw(im)
    d.ellipse((250, 100, 550, 400), fill=(255, 200, 40)); d.text((20, 20), "Anh test Don Mac", fill="white")
    im.save(J("Pictures", "Ảnh kỷ niệm.png"))
    im.save(J("Downloads", "IMG_6091.jpg"), quality=80)
    pdf = Image.new("RGB", (595, 842), "white"); ImageDraw.Draw(pdf).text((60, 80), "Bao cao thuc tap - trang 1", fill="black")
    pdf.save(J("Documents", "Báo cáo thực tập.pdf"))
except ImportError:
    open(J("Pictures", "Ảnh kỷ niệm.png"), "wb").write(b"\x89PNG\r\n\x1a\n")
    open(J("Downloads", "IMG_6091.jpg"), "wb").write(b"\xff\xd8\xff")
    open(J("Documents", "Báo cáo thực tập.pdf"), "wb").write(b"%PDF-1.4\n%%EOF\n")
open(J("Documents/Project/src", "main.py"), "w").write("\n".join(f"print('dòng {i}')" for i in range(300)))
open(J("Documents", "ghi chú.txt"), "w").write("Xin chào Spotless Mac\nDòng 2\n")
with zipfile.ZipFile(J("Downloads", "Mẫu báo cáo.docx"), "w") as z:
    z.writestr("word/document.xml", "<w:document/>")
with open(J("Downloads", "pycharm-2026.2.3-aarch64.dmg"), "wb") as f:
    f.write(os.urandom(60 * 1024 * 1024))
with open(J("Movies", "clip.mp4"), "wb") as f:
    f.write(os.urandom(55 * 1024 * 1024))
open(J("Downloads/Old folder", "a.bin"), "wb").write(os.urandom(3 * 1024 * 1024))
open(J("Library/Caches/BigApp", "c"), "wb").write(os.urandom(2 * 1024 * 1024))
open(J("Library/Keychains", "login.keychain-db"), "wb").write(b"secret")
open(J(".ssh", "id_ed25519"), "w").write("KEY")
# --- feature 002: dữ liệu app, OrbStack, cache ẩn, app đã cài, zip đã giải nén
for d in ["Library/Application Support/Zalo/files", "Library/Application Support/Slack/Cache",
          "Library/Application Support/Slack/Code Cache", "OrbStack", ".gradle/caches/modules", "Applications/PyCharm.app/Contents",
          "Downloads/project", "Library/Containers/com.example.notes/Data/Library/Caches"]:
    os.makedirs(J(d), exist_ok=True)
def blob(rel, mb):
    with open(J(rel), "wb") as f: f.write(os.urandom(mb * 1024 * 1024))
blob("Library/Application Support/Zalo/files/big.db", 330)
blob("Library/Application Support/Slack/Cache/data_1", 25)
blob("OrbStack/data.img", 80)
blob(".gradle/caches/modules/dep.jar", 15)
blob("Library/Containers/com.example.notes/Data/Library/Caches/c.bin", 22)
with zipfile.ZipFile(J("Downloads", "project.zip"), "w") as z:
    z.writestr("a.txt", "x" * 2_000_000)
open(J("Downloads", "project.zip"), "ab").write(os.urandom(1_200_000))
now = time.time()
for name, days in [("IMG_6091.jpg", 400), ("Mẫu báo cáo.docx", 150), ("pycharm-2026.2.3-aarch64.dmg", 3), ("Old folder", 800)]:
    os.utime(J("Downloads", name), (now - days * 86400, now - days * 86400))
print(root)
