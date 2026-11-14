#!/usr/bin/env python3
"""Kiểm thử feature 006 (hoàn tác, dọn sâu cho dev, nhiệt độ, mạng, quyền riêng tư).
Chạy: HOME=/tmp/fhd python3 tests/test_deep.py"""
import importlib.util, json, os, plistlib, shutil, sqlite3, sys, time
HOME = os.environ.get("HOME", "/tmp/fhd")
assert HOME.startswith("/tmp/"), "Chạy với HOME giả, ví dụ HOME=/tmp/fhd"
shutil.rmtree(HOME, ignore_errors=True); os.makedirs(HOME)
SRC = os.path.join(os.path.dirname(__file__), "..", "src", "don_mac.py")
spec = importlib.util.spec_from_file_location("d", SRC); d = importlib.util.module_from_spec(spec); spec.loader.exec_module(d)
n = 0
def check(c, m):
    global n
    if not c: print("❌", m); sys.exit(1)
    n += 1; print("✓", m)

def mk(path, mb=1, name="f.bin"):
    os.makedirs(path, exist_ok=True)
    with open(os.path.join(path, name), "wb") as f:
        f.write(b"\0" * int(mb * 1024 * 1024))
    return path

# ---------- hoàn tác
proj = mk(os.path.join(HOME, "code/app/node_modules"), 1)
orig = os.path.join(proj, "f.bin")
IT = {"id": "id1", "cat": "envs", "label": "node_modules", "size": 1048576, "path": proj, "kind": "path", "risk": "safe"}
d.ITEMS["id1"] = dict(IT)
d.STATE["items"] = [d.ITEMS["id1"]]
res = d.do_delete(["id1"], "trash")
check(res[0]["ok"] and not os.path.exists(proj), "xóa vào Thùng rác")
rows = d.read_history(10)
check(rows[0].get("batch") and rows[0].get("moved") and rows[0]["moved"][0][0] == proj, "lịch sử ghi lại batch + đường dẫn gốc")
batch = rows[0]["batch"]
b = d.undo_list()[0]
check(b["batch"] == batch and b["can"] == 1 and not b["undone"], "danh sách hoàn tác: 1 mục khôi phục được")
r = d.undo_batch(batch)
check(r["ok"] and r["done"] == 1 and os.path.exists(orig), "hoàn tác: file về đúng chỗ cũ")
check(d.undo_list()[0]["undone"] or any(x["batch"] == batch and x["undone"] for x in d.undo_list()), "lần dọn được đánh dấu đã hoàn tác")
check(not d.undo_batch(batch)["ok"], "hoàn tác lần nữa: không còn gì để khôi phục")
check(not d.undo_batch("khongcothat")["ok"], "batch không tồn tại → báo lỗi rõ ràng")
# chỗ cũ đã có tệp khác thì không ghi đè
d.ITEMS["id2"] = dict(IT, id="id2")
d.STATE["items"] = [d.ITEMS["id2"]]
res = d.do_delete(["id2"], "trash")
b2 = d.read_history(1)[0]["batch"]
mk(proj, 1)
with open(orig, "wb") as f: f.write(b"moi")
r2 = d.undo_batch(b2)
check(not r2["ok"] and "đã có tệp khác" in " ".join(r2["skipped"]), "không ghi đè tệp mới ở chỗ cũ")
# xóa vĩnh viễn thì không hoàn tác được
d.ITEMS["id3"] = dict(IT, id="id3")
d.STATE["items"] = [d.ITEMS["id3"]]
d.do_delete(["id3"], "permanent")
check(not (d.read_history(1)[0].get("moved")), "xóa vĩnh viễn: không ghi đường dẫn hoàn tác")

# ---------- dọn sâu cho dev
G = os.path.join(HOME, ".gradle")
mk(os.path.join(G, "caches/modules-2"), 30)
mk(os.path.join(G, "caches/build-cache-1"), 25)
mk(os.path.join(G, "caches/transforms-3"), 22)
for v in ("8.0", "8.5"):
    mk(os.path.join(G, "caches", v), 30)
for v in ("gradle-7.6-bin", "gradle-8.5-bin"):
    mk(os.path.join(G, "wrapper/dists", v), 30)
SDK = os.path.join(HOME, "Library/Android/sdk")
mk(os.path.join(SDK, "system-images/android-30/google_apis/arm64-v8a"), 40)
mk(os.path.join(SDK, "ndk/26.1.1"), 35)
for v in ("33.0.0", "34.0.0", "35.0.0"):
    mk(os.path.join(SDK, "build-tools", v), 25)
mk(os.path.join(HOME, ".android/avd/Pixel.avd/snapshots/default"), 40)
mk(os.path.join(HOME, ".npm/_cacache"), 30)
mk(os.path.join(HOME, "Library/Caches/pip"), 30)
mk(os.path.join(HOME, ".pyenv/versions/3.9.0"), 30)
d.STATE["items"] = [{"cat": "envs", "label": "node_modules", "size": 500 * 1024 * 1024,
                     "path": os.path.join(HOME, "old/node_modules"), "mtime": time.time() - 200 * 86400}]
data = d.scan_dev_deep(lambda m: None)
rows = {r["label"]: r for r in data["rows"]}
g = lambda kw: next((k for k in rows if kw in k), None)
check(g("modules-2") and g("Build cache") and g("transforms"), "Gradle: thư viện, build cache, transforms")
check("gradle-8.5-bin" in rows[g("Bản Gradle đã tải")]["note"] and rows[g("Bản Gradle đã tải")]["size"] >= 30 * 1024 * 1024,
      "Gradle wrapper: giữ bản mới nhất, chỉ tính bản cũ")
check(g("phiên bản Gradle cũ") and "8.5" in rows[g("phiên bản Gradle cũ")]["note"], "Cache theo phiên bản Gradle: giữ bản mới nhất")
check(g("System image") and g("NDK") , "Android SDK: system image và NDK")
check(g("Build-tools") and "35.0.0" in rows[g("Build-tools")]["note"], "Build-tools: chỉ bản cũ, giữ bản mới nhất")
check(g("Snapshot") and rows[g("Snapshot")]["risk"] == "safe", "Snapshot máy ảo Android")
check(g("npm cache") and g("pip cache") and g("pyenv"), "npm, pip, pyenv")
check(g("bỏ quên") or g("quá 4 tháng"), "gom node_modules/venv lâu không dùng")
check(all(r["advice"] and r["advice"].get("when") for r in data["rows"]), "mọi mục dọn sâu đều có giải thích + “nên xóa khi nào”")
check(all(r.get("group") for r in data["rows"]), "mọi mục có nhóm")
check(data["total"] > 0 and d.TOOL_FUNCS["dev2"] is d.scan_dev_deep, "đăng ký công cụ dev2")

# ---------- nhiệt độ
t = d.thermal([], "CPU_Scheduler_Limit \t= 100\nCPU_Available_CPUs \t= 8\nCPU_Speed_Limit \t= 100", {"temp": 30})
check(t["state"] == "ok" and t["lv"] == "ok", "không bị hạ xung → mát")
t2 = d.thermal([{"label": "kernel_task", "cpu": 180.0, "key": "k", "procs": [], "system": True}],
               "CPU_Speed_Limit = 62\nCPU_Available_CPUs = 1", {"temp": 41})
check(t2["state"] == "throttle" and "62%" in t2["msg"] and "1/" in t2["msg"] and any("kernel_task" in x for x in t2["tips"]),
      "hạ xung 62%, khóa bớt nhân, giải thích kernel_task")
t3 = d.thermal([{"label": "Brave", "cpu": 150.0, "key": "b", "procs": [], "system": False}], "", {"temp": 39})
check(t3["state"] == "hot" and t3["hot"][0]["label"] == "Brave", "ấm + chỉ ra app đốt CPU")
check(d.thermal([], "", None)["state"] in ("ok", "unknown"), "máy không đọc được nhiệt → không báo động giả")

# ---------- mạng
NT = """time,name,bytes_in,bytes_out
00:00:01,Brave.41896,1000,200
00:00:01,Claude.70583,500,100
time,name,bytes_in,bytes_out
00:00:02,Brave.41896,2000000,500
00:00:02,Claude.70583,700,100
"""
sm = d.parse_nettop(NT)
check(len(sm) == 2 and sm[1][41896] == (2000000, 500), "đọc nettop 2 mẫu")
me = d.me_user()
PS = f"""41896 1 {me} 300000 2.3 01:00:00 34.35 /Applications/Brave Browser.app/Contents/MacOS/Brave Browser
70583 1 {me} 400000 2.7 01:00:00 22.54 /Applications/Claude.app/Contents/MacOS/Claude
"""
gr = d.proc_snapshot(PS, "", None)
na = d.net_apps(gr, NT)
check(na["apps"][0]["label"] == "Brave Browser" and na["apps"][0]["in_s"] > 1e6, "xếp Brave đầu theo tốc độ tải")
check("tab" in na["apps"][0]["tip"].lower(), "mẹo riêng cho trình duyệt")
check(d.net_apps(gr, "")["error"], "không có nettop → báo rõ")

# ---------- quyền riêng tư
db = os.path.join(HOME, "Library/Application Support/com.apple.TCC")
os.makedirs(db)
con = sqlite3.connect(os.path.join(db, "TCC.db"))
con.execute("CREATE TABLE access (service TEXT, client TEXT, client_type INT, auth_value INT, last_modified INT)")
con.executemany("INSERT INTO access VALUES (?,?,?,?,?)", [
    ("kTCCServiceCamera", "com.hangx.ghost", 0, 2, 1700000000),
    ("kTCCServiceCamera", "com.apple.Safari", 0, 0, 1700000000),
    ("kTCCServiceScreenCapture", "com.obsproject.obs-studio", 0, 2, 1700000000),
    ("kTCCServiceAccessibility", "com.hangx.ghost", 0, 2, 1700000000),
    ("kTCCServicePhotos", "com.x.y", 0, 2, 1700000000)])
con.commit(); con.close()
p = d.privacy()
svc = {g["service"]: g for g in p["groups"]}
check(not p["error"] and "kTCCServiceCamera" in svc, "đọc được danh sách quyền")
check([a["id"] for a in svc["kTCCServiceCamera"]["apps"]] == ["com.hangx.ghost"], "chỉ liệt kê app ĐƯỢC cấp (bỏ app bị từ chối)")
check(svc["kTCCServiceAccessibility"]["risky"] and p["groups"][0]["risky"], "quyền mạnh xếp lên đầu và được đánh dấu")
check(svc["kTCCServiceCamera"]["missing"] == 1, "nhận ra app đã gỡ nhưng còn quyền")
check(svc["kTCCServiceCamera"]["url"].endswith("Privacy_Camera"), "có liên kết mở đúng trang cài đặt")
shutil.rmtree(db)
check(d.privacy()["groups"] == [] , "không có TCC.db → không lỗi")
print(f"\nALL DEEP TESTS PASSED ({n} kiểm tra)")
