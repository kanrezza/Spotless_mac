#!/usr/bin/env python3
"""Kiểm thử feature 002 (lời khuyên + quét đầy đủ). Chạy: HOME=/tmp/fh python3 tests/test_advice.py"""
import importlib.util, os, sys, time
SRC = os.path.join(os.path.dirname(__file__), "..", "src", "don_mac.py")
spec = importlib.util.spec_from_file_location("d", SRC); d = importlib.util.module_from_spec(spec); spec.loader.exec_module(d)
H = d.HOME; n = 0
def check(c, m):
    global n
    if not c: print("❌", m); sys.exit(1)
    n += 1; print("✓", m)
FULL = ("what", "ok", "keep", "when")

# --- quy tắc advise_path (FR-003)
r, a = d.advise_path(H + "/Downloads/pycharm-2026.2.3-aarch64.dmg", False)
check(r == "safe" and "PyCharm" in a["what"], "dmg của app đã cài → An toàn, nêu tên PyCharm")
open(H + "/Downloads/unknownapp-1.0.dmg", "wb").write(b"x")
r, a = d.advise_path(H + "/Downloads/unknownapp-1.0.dmg", False)
check(r == "review", "dmg chưa cài → Xem lại")
r, a = d.advise_path(H + "/Downloads/project.zip", False)
check(r == "safe" and "giải nén" in a["what"], "zip đã giải nén → An toàn")
r, a = d.advise_path(H + "/Downloads/Mẫu báo cáo.docx", False, used=time.time() - 10 * 86400)
check(r == "careful", "tài liệu mới → Cẩn thận")
r, a = d.advise_path(H + "/Downloads/IMG_6091.jpg", False, used=time.time() - 400 * 86400)
check(r == "review" and "hơn 1 năm" in a["tip"], "ảnh trong Tải về > 1 năm → Xem lại + ghi chú tuổi")
r, a = d.advise_path(H + "/Pictures/Ảnh kỷ niệm.png", False)
check(r == "careful" and "không tạo lại được" in a["keep"], "ảnh cá nhân → Cẩn thận")
r, a = d.advise_path(H + "/OrbStack/data.img", False)
check(r == "careful" and "OrbStack" in a["what"] and "docker" in a["tip"].lower(), "ổ ảo OrbStack → Cẩn thận + cách dọn")
r, a = d.advise_path(H + "/Library/Application Support/Zalo/files/big.db", False)
check(r == "careful" and "Zalo" in a["what"] and "Zalo" in a["tip"], "dữ liệu Zalo → Cẩn thận + hướng dẫn trong Zalo")
r, a = d.advise_path(H + "/Library/Application Support/Slack/Cache/data_1", False)
check(r == "safe", "cache Slack trong Application Support → An toàn")
r, a = d.advise_path(H + "/Library/Caches/BigApp", True)
check(r == "safe", "~/Library/Caches → An toàn")
r, a = d.advise_path(H + "/.gradle/caches/modules/dep.jar", False)
check(r == "safe", "cache Gradle → An toàn")
r, a = d.advise_path(H + "/Library/Keychains", True)
check(r == "careful" and "Keychain" in a["keep"], "Keychains → Cẩn thận, được bảo vệ")

# --- quét đầy đủ (US2) + nhóm mới (US3)
d.start_scan()
while d.STATE["running"]: time.sleep(0.2)
bigp = {e["path"]: e for e in d.TABS["big"]}
for rel in ["Library/Application Support/Zalo/files/big.db", "OrbStack/data.img", ".gradle/caches/modules/dep.jar",
            "Library/Application Support/Slack/Cache/data_1"]:
    check(os.path.join(H, rel) in bigp, f"Tệp lớn có {rel}")
check(all(e.get("advice") and all(e["advice"].get(k) for k in FULL) for e in d.TABS["big"]), "mọi Tệp lớn có lời khuyên đủ phần")
check(min(e["size"] for e in d.TABS["big"]) >= 10 * 1024 ** 2, "Tệp lớn gom từ 10 MB")
items = d.STATE["items"]
ac = [i for i in items if i["cat"] == "appcache"]
check(any("Slack" in i["label"] for i in ac) and any("com.example.notes" in i["label"] for i in ac),
      "nhóm Cache trong dữ liệu app có Slack + Containers")
ad = [i for i in items if i["cat"] == "appdata"]
check(any(i["label"] == "Dữ liệu Zalo" and i["risk"] == "careful" for i in ad), "nhóm Dữ liệu app lớn có Zalo (Cẩn thận)")
bad = [i["label"] for i in items if i["risk"] in ("review", "careful") and not (i.get("advice") and all(i["advice"].get(k) for k in FULL))]
check(not bad, f"mọi mục Xem lại/Cẩn thận ở Đề xuất có lời khuyên đủ phần {bad}")
check(all(i.get("advice") for i in items), "mọi mục Đề xuất có lời khuyên")
inst = [i for i in items if i["cat"] == "installers" and i["label"].startswith("pycharm")]
check(inst and inst[0]["risk"] == "safe", "Đề xuất: dmg PyCharm đã cài → An toàn")
print(f"\nALL ADVICE TESTS PASSED ({n} kiểm tra)")
