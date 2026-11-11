#!/usr/bin/env python3
"""Kiểm thử feature 003 (công cụ mở rộng). Chạy: python3 tests/make_fake_home.py /tmp/fh && HOME=/tmp/fh python3 tests/test_tools.py"""
import importlib.util, json, os, plistlib, sys, threading, time, urllib.request, urllib.error
SRC = os.path.join(os.path.dirname(__file__), "..", "src", "don_mac.py")
spec = importlib.util.spec_from_file_location("d", SRC); d = importlib.util.module_from_spec(spec); spec.loader.exec_module(d)
H = d.HOME; n = 0
def check(c, m):
    global n
    if not c: print("❌", m); sys.exit(1)
    n += 1; print("✓", m)
def W(rel, data=b"x", mt=None):
    p = os.path.join(H, rel); os.makedirs(os.path.dirname(p), exist_ok=True); open(p, "wb").write(data)
    if mt: os.utime(p, (mt, mt))
    return p
d.APP_DIRS = [H + "/Applications"]
noop = lambda m: None
MB = 1024 * 1024

# ---------------------------------------------------------------- US1: file trùng lặp
blob = os.urandom(2 * MB)
a = W("Documents/Trip/video-final.bin", blob, time.time() - 400 * 86400)
b = W("Downloads/video-final (1).bin", blob)
c = W("Pictures/copy-of-video.bin", blob)
other = W("Documents/other.bin", os.urandom(2 * MB))         # cùng dung lượng, khác nội dung
small = W("Documents/tiny1.txt", b"hello"); W("Documents/tiny2.txt", b"hello")  # dưới 1 MB: bỏ qua
os.link(other, H + "/Documents/other-link.bin")             # hard link: không phải bản trùng
W("Documents/Project/node_modules/pkg/same.bin", blob)      # bị bỏ qua
W(".hidden/same.bin", blob)                                  # thư mục ẩn: bị bỏ qua
r = d.scan_dupes(noop)
gs = [g for g in r["groups"] if len(g["files"]) >= 2 and any(f["name"].startswith("video") for f in g["files"])]
check(len(gs) == 1, "tìm đúng 1 nhóm trùng")
g = gs[0]; paths = {f["path"] for f in g["files"]}
check(paths == {a, b, c}, "nhóm gồm đúng 3 bản (bỏ hard link, node_modules, thư mục ẩn, file khác nội dung)")
check(not any(other in {f["path"] for f in x["files"]} or H + "/Documents/other-link.bin" in {f["path"] for f in x["files"]} for x in r["groups"]), "file cùng dung lượng khác nội dung và hard link không bị gộp")
check(g["wasted"] == 2 * MB * 2 and r["wasted"] >= g["wasted"], "dung lượng thu hồi = size × (số bản − 1)")
keep = next(f for f in g["files"] if f["id"] == g["keep"])
check(keep["path"] == a, "đề xuất giữ bản không nằm trong Tải về/Desktop và cũ nhất")
ids = [f["id"] for f in g["files"]]
res = d.do_delete(ids, "trash")
okc = [x for x in res if x["ok"]]; bad = [x for x in res if not x["ok"]]
check(len(okc) == 2 and len(bad) == 1 and "ít nhất một bản" in bad[0]["msg"], "xóa cả nhóm: bản cuối bị chặn")
check(os.path.exists(keep["path"]), "bản được giữ vẫn còn trên đĩa")
check(d.do_delete([keep["id"]], "trash")[0]["ok"] is False, "bản duy nhất còn lại cũng không xóa được")
check(not any(g2["gid"] == g["gid"] for g2 in (d.TOOLS["dupes"]["data"] or {"groups": []})["groups"]), "nhóm không còn trong kết quả sau khi chỉ còn 1 bản")

# ---------------------------------------------------------------- US4: Luôn giữ
keepme = W("Documents/Precious/thesis.docx", b"x" * 5000)
e = d.make_entry(keepme)
check(e["deletable"] and not e["kept"], "trước khi giữ: xóa được")
check(d.keep_set([os.path.dirname(keepme)]) == 1, "thêm vào danh sách giữ")
check(os.path.exists(d.cfg_path()) and json.load(open(d.cfg_path()))["keep"] == [H + "/Documents/Precious"], "danh sách giữ lưu vào config.json")
e = d.make_entry(keepme)
check(e["kept"] and not e["deletable"], "file trong thư mục được giữ: kept, không xóa được")
res = d.do_delete([e["id"]], "trash")
check(not res[0]["ok"] and "Luôn giữ" in res[0]["msg"], "do_delete từ chối mục được giữ")
check(d.keep_conflict(H + "/Documents") == H + "/Documents/Precious", "thư mục cha chứa mục được giữ cũng vướng")
it = {"kind": "path", "path": H + "/Documents", "label": "Documents", "size": 1}
check(d.delete_one(it, "trash")[0] is False, "không xóa được thư mục cha của mục được giữ")
d.ITEMS["zz"] = {"id": "zz", "path": keepme, "kind": "path", "label": "t", "size": 1, "cat": "caches", "risk": "safe"}
d.STATE["items"] = [d.ITEMS["zz"]]
d.keep_set([keepme])
check("zz" not in d.ITEMS and not d.STATE["items"], "giữ một mục thì gỡ khỏi Đề xuất")
d.keep_set([H + "/Documents/Precious", keepme], keep=False)
check(d.make_entry(keepme)["deletable"] and d.kept_paths() == [], "bỏ giữ: xóa được trở lại")
check(d.keep_set(["/etc/hosts"]) == 0, "chỉ nhận đường dẫn trong thư mục nhà")

# ---------------------------------------------------------------- US5: lịch sử
hist = d.read_history()
check(len(hist) >= 2 and hist[0]["src"] == "manual" and all(k in hist[0] for k in ("t", "label", "size", "mode")), "xóa thành công được ghi vào lịch sử")
check(all(h["label"] for h in hist) and len({h["label"] for h in hist}) >= 1, "lịch sử có tên mục")
d.log_history([{"t": 1, "label": "x", "size": 1, "mode": "trash", "src": "auto"}])
check(d.read_history()[0]["src"] == "auto", "lịch sử mới nhất ở đầu")
d.clear_history()
check(d.read_history() == [], "xóa lịch sử")

# ---------------------------------------------------------------- US2: gỡ app sạch
def mkapp(name, bid, size=3000):
    p = f"{H}/Applications/{name}.app"; os.makedirs(p + "/Contents/MacOS", exist_ok=True)
    plistlib.dump({"CFBundleIdentifier": bid, "CFBundleName": name, "CFBundleShortVersionString": "1.2"}, open(p + "/Contents/Info.plist", "wb"))
    open(p + "/Contents/MacOS/bin", "wb").write(b"x" * size)
    return p
fooapp = mkapp("Foo", "com.test.foo"); mkapp("Safari", "com.apple.Safari"); mkapp("Notes", "com.apple.Notes")
W("Library/Application Support/com.test.foo/data.db", b"x" * 400000)
W("Library/Caches/com.test.foo/c.bin", b"x" * 200000)
r = d.scan_uninstall(noop)
rows = {x["label"]: x for x in r["rows"]}
check("Foo" in rows and "Safari" not in rows and "Notes" not in rows, "liệt kê Foo; bỏ app hệ thống Apple")
f = rows["Foo"]
check(f["left_size"] >= 500000 and len(f["leftovers"]) == 2 and f["size"] == f["app_size"] + f["left_size"], "dung lượng gồm dữ liệu đi kèm")
check(f["advice"] and all(f["advice"].get(k) for k in ("what", "ok", "keep", "tip", "when")), "app có lời khuyên đủ phần")
res = d.do_delete([f["id"]], "trash")
check(res[0]["ok"], "gỡ app thành công")
tr = os.listdir(d.TRASH)
check(not os.path.exists(fooapp) and "Foo.app" in tr and "com.test.foo" in tr, "app và dữ liệu đi kèm vào Thùng rác")
check(not any(x["label"] == "Foo" for x in d.TOOLS["apps"]["data"]["rows"]) if d.TOOLS["apps"]["data"] else True, "app đã gỡ biến khỏi kết quả")

# ---------------------------------------------------------------- US3: dữ liệu mồ côi
mkapp("Bar", "com.test.bar")
for rel, sz in [("Library/Application Support/com.test.bar", 300000), ("Library/Application Support/com.test.bar.helper", 150000),
                ("Library/Caches/com.gone.app", 250000), ("Library/Application Support/com.gone.app/store.db", 400000),
                ("Library/Preferences/com.gone.app.plist", 150000), ("Library/Application Support/com.apple.sharedfilelist/x", 300000),
                ("Library/Application Support/Zalo/x.bin", 300000), ("Library/Caches/com.tiny.leftover/x", 100)]:
    W(rel + ("" if rel.endswith(".plist") or "/" in rel.split("Library/", 1)[1].split("/", 1)[1] else "/f.bin"), b"x" * sz)
r = d.scan_orphans(noop)
rows = {x["label"]: x for x in r["rows"]}
check("com.gone.app" in rows, "tìm thấy dữ liệu mồ côi com.gone.app")
check(len(rows["com.gone.app"]["locations"]) == 3, "gom 3 vị trí (Caches, Application Support, Preferences) vào một mục")
check("com.test.bar" not in rows and "com.test.bar.helper" not in rows, "app đang cài (kể cả helper) không bị coi là mồ côi")
check(not any(k.startswith("com.apple") for k in rows) and "Zalo" not in rows and "com.tiny.leftover" not in rows, "bỏ com.apple.*, tên không phải mã gói, mục quá nhỏ")
check(rows["com.gone.app"]["risk"] == "review" and all(rows["com.gone.app"]["advice"].get(k) for k in ("what", "ok", "keep", "tip", "when")), "mồ côi: Xem lại + giải thích đủ phần")
res = d.do_delete([rows["com.gone.app"]["id"]], "trash")
check(res[0]["ok"] and not os.path.exists(H + "/Library/Caches/com.gone.app") and not os.path.exists(H + "/Library/Preferences/com.gone.app.plist"), "xóa mồ côi chuyển mọi vị trí vào Thùng rác")
check(d.bundle_id_of("ABCDE12345.group.com.foo.bar") == "com.foo.bar" and d.bundle_id_of("Google") is None and d.bundle_id_of("a.b") is None, "bundle_id_of")

# ---------------------------------------------------------------- US8: ảnh giống nhau
def bmp(rows_topdown):  # rows_topdown: danh sách hàng, mỗi hàng là list mức xám; BMP 24-bit, bottom-up
    h, w = len(rows_topdown), len(rows_topdown[0]); bpr = ((w * 24 + 31) // 32) * 4
    body = b""
    for row in reversed(rows_topdown):
        line = b"".join(bytes([v, v, v]) for v in row); body += line + b"\0" * (bpr - len(line))
    hdr = b"BM" + (54 + len(body)).to_bytes(4, "little") + b"\0\0\0\0" + (54).to_bytes(4, "little")
    dib = (40).to_bytes(4, "little") + w.to_bytes(4, "little") + h.to_bytes(4, "little") + (1).to_bytes(2, "little") + (24).to_bytes(2, "little") + b"\0" * 24
    return hdr + dib + body
dec = bmp([[250 - 25 * x for x in range(9)] for _ in range(9)])   # sáng → tối: mỗi cặp lớn hơn → toàn bit 1
inc = bmp([[10 + 25 * x for x in range(9)] for _ in range(9)])
check(d.bmp_dhash(dec) == (1 << 64) - 1 and d.bmp_dhash(inc) == 0, "bmp_dhash đọc đúng hướng gradient (bottom-up)")
check(d.bmp_dhash(b"not a bmp") is None and d.bmp_dhash(dec[:60]) is None, "bmp_dhash an toàn với dữ liệu hỏng")
h1 = 0x0F0F0F0F0F0F0F0F; h2 = h1 ^ 0b101; h3 = 0xF0F0_1234_ABCD_9876
cl = d.cluster_hashes({"a": h1, "b": h2, "c": h3})
check(len(cl) == 1 and set(cl[0]) == {"a", "b"}, "cluster_hashes gom ảnh gần nhau (≤5 bit), tách ảnh khác")
far = h1 ^ ((1 << 8) - 1)
check(d.cluster_hashes({"a": h1, "b": far}) == [], "khoảng cách 8 bit không bị gom")
d.SIPS = "/usr/bin/sips"
fake = {}
orig = d.image_hash
d.image_hash = lambda p: fake.get(os.path.basename(p))
p1 = W("Pictures/IMG_1.jpg", b"1" * 30000); p2 = W("Pictures/IMG_1 copy.jpg", b"2" * 40000); p3 = W("Pictures/IMG_9.jpg", b"3" * 50000)
fake.update({"IMG_1.jpg": h1, "IMG_1 copy.jpg": h2, "IMG_9.jpg": h3})
r = d.scan_similar(noop)
check(len(r["groups"]) == 1 and {f["name"] for f in r["groups"][0]["files"]} == {"IMG_1.jpg", "IMG_1 copy.jpg"}, "scan_similar: 1 nhóm ảnh giống")
check(r["groups"][0]["files"][0]["name"] == "IMG_1 copy.jpg", "ảnh lớn nhất ở đầu nhóm")
d.image_hash = orig; d.SIPS = None
check("unavailable" in d.scan_similar(noop), "không có sips → báo không khả dụng")

# ---------------------------------------------------------------- US7: thư mục build
for rel in ["proj/Cargo.toml", "proj/target/debug/app", "web/package.json", "web/.next/cache/x", "mobile/pubspec.yaml",
            "mobile/build/out.bin", "mobile/.dart_tool/x", "ios/Podfile", "ios/Pods/Lib/a", "plain/target/x", "plain/build/y"]:
    W(rel, b"x" * 8000)
items = []; d.walk_home(items, noop)
labels = {i["label"]: i for i in items if i["cat"] == "envs"}
for lb in ["proj/target", "web/.next", "mobile/build", "mobile/.dart_tool", "ios/Pods"]:
    check(lb in labels and labels[lb]["risk"] == "review" and labels[lb]["advice"], f"nhận ra thư mục build {lb}")
check("plain/target" not in labels and "plain/build" not in labels, "target/build không có file anh em thì không đụng vào")

# ---------------------------------------------------------------- US9: máy, bảo mật, khởi động
m = d.machine_info()
check("cores" in m and isinstance(m["procs"], list), "machine_info trả cấu trúc hợp lệ")
sec = d.security_info()
check({"filevault", "firewall", "sip", "gatekeeper", "xprotect"} == {x["key"] for x in sec} and all(x["state"] in ("ok", "warn", "unknown") for x in sec), "security_info đủ 5 mục")
W("Library/LaunchAgents/com.gone.helper.plist", b"")
plistlib.dump({"Label": "com.gone.helper", "ProgramArguments": ["/Applications/Gone.app/Contents/MacOS/helper"], "RunAtLoad": True}, open(H + "/Library/LaunchAgents/com.gone.helper.plist", "wb"))
st = d.startup_items()
check(any(x["label"] == "com.gone.helper" and x["broken"] for x in st), "mục khởi động trỏ tới chương trình đã mất được đánh dấu")
check(all(not x["label"].startswith("com.apple.") for x in st), "bỏ mục của Apple")

# ---------------------------------------------------------------- US6: dọn tự động
W("Library/Caches/AutoApp/c.bin", b"x" * (25 * MB))
W("Documents/Precious2/keepme.txt", b"x")
d.keep_set([H + "/Library/Caches/AutoApp"])
before = set(os.listdir(H + "/Library/Caches"))
lines = []
d.auto_clean(True, 1, out=lines.append)
check(os.listdir(H + "/Library/Caches") and set(os.listdir(H + "/Library/Caches")) == before, "--dry-run không thay đổi file nào")
check(any("xem thử" in l for l in lines), "--dry-run báo rõ")
check(not any("AutoApp" in l for l in lines), "mục trong danh sách giữ không nằm trong danh sách tự dọn")
d.keep_set([H + "/Library/Caches/AutoApp"], keep=False)
lines = []; d.auto_clean(True, 1, out=lines.append)
check(any("AutoApp" in l for l in lines), "bỏ giữ rồi thì mục xuất hiện lại trong danh sách tự dọn")
lines = []; d.auto_clean(True, 100000, out=lines.append)
check(any("Chưa đạt ngưỡng" in l for l in lines), "dưới ngưỡng thì không dọn")
d.run_scan()
cands = d.auto_candidates(d.STATE["items"])
check(cands and all(i["risk"] == "safe" and i["cat"] in d.AUTO_CATS and i["kind"] in ("path", "clear_dir") for i in cands), "ứng viên tự dọn chỉ gồm mục An toàn thuộc nhóm cho phép")
check(not any(i["cat"] in ("apps", "docker", "trash", "backups", "sims", "appdata") for i in cands), "không bao giờ tự dọn app/Docker/Thùng rác/sao lưu/dữ liệu app")
lines = []; d.auto_clean(False, 1, out=lines.append)
check(any(h["src"] == "auto" for h in d.read_history()), "tự dọn ghi lịch sử với nguồn 'auto'")
check(not os.path.exists(H + "/Library/Caches/AutoApp"), "mục An toàn đã được dọn (vào Thùng rác)")
pl = d.schedule_plist(300, 0, 10)
check(pl["ProgramArguments"][2:] == ["--auto-clean", "--min-mb", "300"] and pl["StartCalendarInterval"]["Hour"] == 10, "plist lịch có đúng tham số")
s = d.schedule_set(True, 300, 2, 9)
check(s["enabled"] and s["min_mb"] == 300 and s["weekday"] == 2 and s["hour"] == 9, "lưu lịch vào config")
check(d.schedule_set(True, 1, 99, 99)["min_mb"] == 10 and d.schedule_get()["hour"] == 99 % 24, "giá trị lịch được chặn trong khoảng hợp lệ")
d.schedule_set(False)
check(not d.schedule_get()["enabled"], "tắt lịch")

# ---------------------------------------------------------------- Dấu vết AI (Claude, Codex, ChatGPT)
DAY = 86400; old_t = time.time() - 90 * DAY
def WO(rel, size, mt):  # file có kích thước và tuổi xác định
    return W(rel, b"x" * size, mt)
for v in ("2.1.300", "2.1.310", "2.1.322"):
    WO(f".local/share/claude/versions/{v}", 300000, old_t)
os.makedirs(H + "/.local/bin", exist_ok=True)
os.symlink(H + "/.local/share/claude/versions/2.1.310", H + "/.local/bin/claude")   # bản đang dùng: 2.1.310
WO(".claude/projects/-proj-a/old-session.jsonl", 200000, old_t)
WO(".claude/projects/-proj-a/new-session.jsonl", 200000, time.time() - DAY)
WO(".claude/projects/-proj-a/memory/MEMORY.md", 5000, old_t)                      # ghi nhớ: không được đụng
WO(".claude/projects/-proj-a/subagents/agent.jsonl", 150000, old_t)
WO(".claude/file-history/abc/v1", 120000, old_t); WO(".claude/file-history/abc/v2", 120000, time.time() - DAY)
WO(".claude/settings.json", 500, old_t); WO(".claude/CLAUDE.md", 500, old_t)
WO(".claude/debug/log.txt", 100000, old_t)
WO(".codex/sessions/2026/01/rollout-1.jsonl", 250000, old_t); WO(".codex/sessions/2026/11/rollout-2.jsonl", 250000, time.time() - DAY)
WO(".codex/generated_images/pic.png", 100000, old_t); WO(".codex/auth.json", 300, old_t); WO(".codex/config.toml", 300, old_t)
WO(".codex/logs_1.sqlite", 150000, time.time()); WO(".codex/logs_1.sqlite-wal", 120000, time.time())
for v in ("0.100.0", "0.120.0"):
    WO(f".codex/packages/standalone/releases/{v}-aarch64/codex", 200000, old_t)
WO("Library/Application Support/Claude/vm_bundles/claudevm.bundle/rootfs.img", 400000, old_t)
WO("Library/Application Support/Claude/Cache/Cache_Data/f1", 70 * 1024 * 1024, old_t)
WO("Library/Caches/com.openai.chat/blob", 60 * 1024 * 1024, old_t)
r = d.scan_ai(noop)
rows = r["rows"]; by = {x["label"]: x for x in rows}
def find(sub): return next((x for x in rows if sub in x["label"]), None)
v = find("phiên bản cũ")
check(v and v["group"] == "Claude Code" and len(v.get("extra", [])) + 1 == 1 and "2.1.300" in v["path"], "Claude Code: chỉ liệt kê bản cũ, giữ bản mới nhất 2.1.322")
check(all("2.1.322" not in x for x in [v["path"]] + v.get("extra", [])) and all("2.1.310" not in x for x in [v["path"]] + v.get("extra", [])), "không bao giờ chọn bản mới nhất hoặc bản đang dùng (symlink)")
pj = find("Transcript phiên làm việc"); pj = next(x for x in rows if x["kind"] == "prune_old" and x["path"].endswith(".claude/projects"))
check(pj["days"] == 30 and 350000 <= pj["size"] < 370000 and "2 file" in pj["label"], "transcript cũ: chỉ tính .jsonl cũ (không tính file mới, memory/*.md)")
check(all(x["advice"] and all(x["advice"].get(k) for k in ("what", "ok", "keep", "when")) for x in rows), "mọi dòng AI có lời giải thích")
ea = d.electron_advice("CertificateRevocation")
check(ea and ea[0] == "safe" and "CRLSet" in ea[1]["what"] and ea[1]["when"], "CertificateRevocation được nhận diện cụ thể, có “khi nào”")
check(d.electron_advice("TenLaHoanToan") is None, "tên lạ → chưa nhận diện")
check(all(v[4] for v in d.ELECTRON_DIRS.values()), "mọi thư mục Electron đã biết có mục “khi nào”")

cdx = [x for x in rows if x["group"] == "Codex"]
check(any("sessions" in x["path"] for x in cdx) and any("generated_images" in x["path"] for x in cdx) and any(x["label"].startswith("Codex: 1 phiên") for x in cdx), "Codex: sessions, ảnh tạo ra, bản phát hành cũ")
check(any(x["label"].startswith("Cơ sở dữ liệu nhật ký (2 file)") for x in cdx), "Codex: gom logs*.sqlite và -wal")
check(any("vm_bundles" in x["path"] and x["risk"] == "careful" for x in rows), "Cowork vm_bundles: Cẩn thận")
check(any("openai" in x["path"] and x["group"] == "ChatGPT" and x["risk"] == "safe" for x in rows), "ChatGPT: cache an toàn")
check(any(x["group"] == "Claude Desktop" and x["path"].endswith("Claude/Cache") and x["risk"] == "safe" for x in rows), "Claude Desktop: Cache an toàn")
check(not any(".claude/settings.json" in x["path"] or "auth.json" in x["path"] for x in rows), "không liệt kê file cấu hình/đăng nhập")
# xóa
res = d.do_delete([pj["id"]], "trash")
check(res[0]["ok"] and "2 file" in res[0]["msg"], "prune_old: báo số file đã xóa")
check(not os.path.exists(H + "/.claude/projects/-proj-a/old-session.jsonl") and not os.path.exists(H + "/.claude/projects/-proj-a/subagents/agent.jsonl"), "transcript cũ (kể cả subagent) bị xóa")
check(os.path.exists(H + "/.claude/projects/-proj-a/new-session.jsonl") and os.path.exists(H + "/.claude/projects/-proj-a/memory/MEMORY.md"), "transcript mới và memory/MEMORY.md còn nguyên")
fh = next(x for x in rows if x["path"].endswith("file-history"))
check(d.do_delete([fh["id"]], "trash")[0]["ok"] and not os.path.exists(H + "/.claude/file-history/abc/v1") and os.path.exists(H + "/.claude/file-history/abc/v2"), "file-history: chỉ xóa bản cũ")
d.keep_set([H + "/.codex/sessions/2026/01/rollout-1.jsonl"])
cs = next(x for x in rows if x["path"].endswith(".codex/sessions"))
d.do_delete([cs["id"]], "trash")
check(os.path.exists(H + "/.codex/sessions/2026/01/rollout-1.jsonl"), "prune_old tôn trọng danh sách Luôn giữ")
d.keep_set([H + "/.codex/sessions/2026/01/rollout-1.jsonl"], keep=False)
check(os.path.exists(H + "/.claude/settings.json") and os.path.exists(H + "/.claude/CLAUDE.md") and os.path.exists(H + "/.codex/auth.json"), "file cấu hình/đăng nhập không bị đụng")
bad = dict(cs, id="evil", path=H + "/Documents", kind="prune_old", days=1); d.TOOL_ITEMS["evil"] = bad
check(not d.do_delete(["evil"], "trash")[0]["ok"] and os.path.exists(H + "/Documents"), "prune_old chỉ chạy trên thư mục trong danh sách cho phép")
vd = d.do_delete([v["id"]], "trash")
check(vd[0]["ok"] and os.path.exists(H + "/.local/share/claude/versions/2.1.322") and not os.path.exists(H + "/.local/share/claude/versions/2.1.300"), "xóa bản cũ: bản mới nhất còn nguyên")
check(d.old_versions(H + "/.local/share/claude/versions", d.live_binaries("claude")) == [], "sau khi dọn không còn bản cũ")
check(d.vkey("2.1.322") > d.vkey("2.1.99") and d.vkey("0.120.0-aarch64") > d.vkey("0.100.0-aarch64"), "vkey so sánh số phiên bản đúng")

# ---------------------------------------------------------------- API
srv = d.ThreadingHTTPServer(("127.0.0.1", 0), d.Handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{srv.server_address[1]}"
def call(path, body=None, tok=True):
    h = {"Content-Type": "application/json"}
    if tok: h["X-Token"] = d.TOKEN
    try:
        with urllib.request.urlopen(urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode(), headers=h)) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, {}
check(call("/api/settings", tok=False)[0] == 403 and call("/api/machine", tok=False)[0] == 403 and call("/api/toolres?name=apps", tok=False)[0] == 403, "API mới yêu cầu mã bí mật")
check(call("/api/toolres?name=hack")[0] == 404 and call("/api/tool", {"name": "hack"})[1] == {"ok": False}, "tên công cụ lạ bị từ chối")
call("/api/tool", {"name": "dupes"})
for _ in range(100):
    s, r = call("/api/toolres?name=dupes")
    if not r["running"]: break
    time.sleep(0.1)
check(s == 200 and r["done"] and r["error"] is None and "groups" in r["data"], "/api/tool + /api/toolres chạy được tới khi xong")
W("Documents/ToKeep/a.txt", b"x" * 3000); e = d.make_entry(H + "/Documents/ToKeep/a.txt")
check(call("/api/keep", {"ids": [e["id"]]})[1]["n"] == 1, "/api/keep thêm mục")
s, r = call("/api/settings")
check(any(k["path"].endswith("ToKeep/a.txt") for k in r["kept"]) and "schedule" in r and "history" in r, "/api/settings trả danh sách giữ, lịch, lịch sử")
check(call("/api/unkeep", {"paths": ["/etc/passwd", H + "/Documents/ToKeep/a.txt"]})[1]["n"] == 1, "/api/unkeep chỉ gỡ đường dẫn đã có trong danh sách")
s, r = call("/api/machine")
check(s == 200 and "machine" in r and "security" in r and "startup" in r, "/api/machine")
check(call("/api/history_clear", {})[1]["ok"] and call("/api/settings")[1]["history"] == [], "/api/history_clear")
print(f"\nALL TOOLS TESTS PASSED ({n} kiểm tra)")
