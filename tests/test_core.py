#!/usr/bin/env python3
"""Kiểm thử lõi Spotless Mac trên HOME giả. Chạy: HOME=/tmp/fh python3 tests/test_core.py"""
import importlib.util, json, os, sys, threading, time, urllib.request, urllib.error
SRC = os.path.join(os.path.dirname(__file__), "..", "src", "don_mac.py")
spec = importlib.util.spec_from_file_location("d", SRC); d = importlib.util.module_from_spec(spec); spec.loader.exec_module(d)
H = d.HOME
ok = 0
def check(cond, msg):
    global ok
    if not cond:
        print("❌", msg); sys.exit(1)
    ok += 1; print("✓", msg)

# --- deletable (R6 / FR-013)
check(not d.deletable(H), "home không xóa được")
check(not d.deletable(H + "/Documents"), "Documents không xóa được")
check(not d.deletable(H + "/Library/Keychains"), "~/Library/Keychains không xóa được")
check(not d.deletable(H + "/Library/Keychains/login.keychain-db"), "file trong Keychains không xóa được")
check(not d.deletable(H + "/.ssh/id_ed25519"), "khóa SSH không xóa được")
check(d.deletable(H + "/Library/Caches/BigApp"), "cache trong Library xóa được")
check(d.deletable(H + "/Documents/Project"), "thư mục dự án xóa được")
check(not d.deletable(H + "/Library/Application Support"), "gốc Application Support không xóa được")
check(not d.deletable("/etc/hosts"), "file ngoài home không xóa được")
import tempfile
_out = tempfile.mkdtemp(); os.makedirs(_out + "/avd/Pixel_4.avd")
os.symlink(_out, H + "/.android_link")
_r = d.unsafe_reason(H + "/.android_link/avd/Pixel_4.avd")
check(_r and "ngoài thư mục nhà" in _r and ".android_link" in _r, "liên kết ra ngoài home: báo rõ lý do + tên liên kết")
check(d.unsafe_reason(H + "/Documents/Project") is None, "unsafe_reason None cho mục an toàn")

# --- thư mục treo giữa chừng (lỗi thật trên máy người dùng: OneDrive Errno 60) không được làm hỏng cả lượt quét
os.makedirs(H + "/Library/CloudStorage/OneDrive-Test/.Trash", exist_ok=True)
os.makedirs(H + "/Documents/SlowNet/a", exist_ok=True)
_real_scandir = d.os.scandir
class _Hang:
    def __init__(self, p): self.inner = _real_scandir(p)
    def __enter__(self): return self
    def __exit__(self, *a): self.inner.close()
    def __iter__(self): return self
    def __next__(self): raise OSError(60, "Operation timed out")
def _fake_scandir(p):
    return _Hang(p) if str(p).endswith("SlowNet") or "CloudStorage" in str(p) else _real_scandir(p)
d.os.scandir = _fake_scandir

# --- quét (US1, US3)
d.start_scan()
while d.STATE["running"]: time.sleep(0.2)
d.os.scandir = _real_scandir
check(any("SlowNet" in w for w in d.STATE["warnings"]) and not any("Errno 60" in w and "Đang quét" in w for w in d.STATE["warnings"]),
      "thư mục treo bị bỏ qua kèm cảnh báo nhẹ, không làm hỏng lượt quét")
check(not any("CloudStorage" in w for w in d.STATE["warnings"]), "ổ đám mây không bị quét")
big = {e["name"]: e for e in d.TABS["big"]}
check("pycharm-2026.2.3-aarch64.dmg" in big and "clip.mp4" in big, "Tệp lớn có .dmg 60 MB và video 55 MB")
check(all(e["size"] >= 10 * 1024 ** 2 for e in d.TABS["big"]), "Tệp lớn chỉ gồm file ≥ 10 MB (giao diện lọc tiếp)")
check(big["pycharm-2026.2.3-aarch64.dmg"]["kind"] == "Ảnh Đĩa", "Loại .dmg = Ảnh Đĩa")
check(big["clip.mp4"]["preview"] == "video", "mp4 xem trước dạng video")
dl = {e["name"]: e for e in d.TABS["downloads"]}
check(dl["IMG_6091.jpg"]["group"] == "old1y", "ảnh 400 ngày → Cũ hơn 1 năm")
check(dl["Mẫu báo cáo.docx"]["group"] == "old3m", "docx 150 ngày → Cũ hơn 3 tháng")
check(dl["pycharm-2026.2.3-aarch64.dmg"]["group"] == "recent", "dmg 3 ngày → Gần đây")
check(dl["Old folder"]["is_dir"] and dl["Old folder"]["size"] >= 3 * 1024 ** 2, "thư mục trong Tải về có dung lượng")
check(not any(i["cat"] == "large" for i in d.STATE["items"]), "Đề xuất không còn nhóm File lớn cũ")

# --- browse (US4)
r = d.browse(None)
names = {c["name"]: c for c in r["children"]}
check("Documents" in names and r["crumbs"][0]["name"] == "Thư mục nhà", "browse home có Documents + crumb gốc")
check(not names["Library"]["deletable"] and not names["Documents"]["deletable"], "Library/Documents bị khóa xóa")
r2 = d.browse(names["Documents"]["id"])
kids = {c["name"]: c for c in r2["children"]}
check([c["name"] for c in r2["crumbs"]] == ["Thư mục nhà", "Documents"], "crumbs Documents đúng")
for _ in range(50):
    if not d.DIR_PENDING: break
    time.sleep(0.1)
r2 = d.browse(names["Documents"]["id"]); kids = {c["name"]: c for c in r2["children"]}
check(r2["pending"] == 0 and kids["Project"]["size"] > 0, "dung lượng thư mục con tính xong nền")
check(kids["Báo cáo thực tập.pdf"]["preview"] == "pdf", "PDF xem trước dạng pdf")
check(d.browse(kids["ghi chú.txt"]["id"]) is None, "browse một file → None")

# --- server endpoints (US2)
srv = d.ThreadingHTTPServer(("127.0.0.1", 0), d.Handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{srv.server_address[1]}"
def req(path, body=None, headers=None, token=True):
    h = dict(headers or {})
    if token: h["X-Token"] = d.TOKEN
    data = json.dumps(body).encode() if body is not None else None
    if data: h["Content-Type"] = "application/json"
    try:
        with urllib.request.urlopen(urllib.request.Request(base + path, data=data, headers=h)) as resp:
            return resp.status, resp.read(), dict(resp.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), dict(e.headers)
txt = kids["ghi chú.txt"]
st, body, _ = req("/api/text", {"id": txt["id"]})
check(st == 200 and "Xin chào Spotless Mac" in json.loads(body)["text"], "/api/text đọc tiếng Việt")
pdf = kids["Báo cáo thực tập.pdf"]; real = open(pdf["path"], "rb").read()
st, body, hd = req(f"/api/file?id={pdf['id']}&t={d.TOKEN}", token=False)
check(st == 200 and body == real and hd["Content-Type"] == "application/pdf", "/api/file trả đúng PDF")
st, body, hd = req(f"/api/file?id={pdf['id']}&t={d.TOKEN}", headers={"Range": "bytes=0-9"}, token=False)
check(st == 206 and body == real[:10] and hd["Content-Range"].startswith("bytes 0-9/"), "/api/file hỗ trợ Range 206")
st, *_ = req(f"/api/file?id={pdf['id']}&t=sai", token=False)
check(st == 403, "/api/file sai token → 403")
st, *_ = req(f"/api/file?id=khongco&t={d.TOKEN}", token=False)
check(st == 404, "/api/file id lạ → 404")
st, *_ = req(f"/api/file?id={names['Documents']['id']}&t={d.TOKEN}", token=False)
check(st == 404, "/api/file thư mục → 404")
st, body, _ = req("/api/tab?name=big")
check(st == 200 and {"clip.mp4", "pycharm-2026.2.3-aarch64.dmg"} <= {e["name"] for e in json.loads(body)["entries"]}, "/api/tab big trả các tệp lớn")
st, *_ = req("/api/tab?name=big", token=False)
check(st == 403, "/api/tab thiếu token → 403")
st, body, _ = req("/api/browse", {"id": "khongco"})
check(st == 404, "/api/browse id lạ → 404")

# --- xóa (FR-008, FR-012, FR-013)
st, body, _ = req("/api/delete", {"ids": [names["Library"]["id"]], "mode": "trash"})
check(not json.loads(body)["results"][0]["ok"] and os.path.isdir(H + "/Library"), "xóa Library bị từ chối")
dmg = big["pycharm-2026.2.3-aarch64.dmg"]
st, body, _ = req("/api/delete", {"ids": [dmg["id"]], "mode": "trash"})
check(json.loads(body)["results"][0]["ok"] and os.path.exists(H + "/.Trash/pycharm-2026.2.3-aarch64.dmg"), "xóa dmg → vào Thùng rác")
check(all(e["path"] != dmg["path"] for e in d.TABS["big"] + d.TABS["downloads"]), "dmg biến khỏi Tệp lớn và Bản tải về")
proj = kids["Project"]
st, body, _ = req("/api/delete", {"ids": [proj["id"]], "mode": "trash"})
check(json.loads(body)["results"][0]["ok"] and os.path.isdir(H + "/.Trash/Project"), "xóa thư mục từ Trình duyệt tệp → Thùng rác")
check(not any(e["path"].startswith(proj["path"] + "/") for e in d.ENTRIES.values()), "mục con của thư mục đã xóa bị gỡ khỏi sổ")
st, body, _ = req("/api/delete", {"ids": [txt["id"]], "mode": "permanent"})
check(json.loads(body)["results"][0]["ok"] and not os.path.exists(txt["path"]), "xóa vĩnh viễn khi chọn rõ")
srv.shutdown()
print(f"\nALL CORE TESTS PASSED ({ok} kiểm tra)")
