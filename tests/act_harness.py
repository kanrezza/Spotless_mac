#!/usr/bin/env python3
"""Chạy Spotless Mac với dữ liệu tiến trình/tab giả để kiểm thử tab Hoạt động trên máy không phải macOS.
Dùng bởi tests/ui_activity.js: HOME=/tmp/fha python3 tests/act_harness.py --native"""
import importlib.util, os, subprocess, sys
SRC = os.path.join(os.path.dirname(__file__), "..", "src", "don_mac.py")
spec = importlib.util.spec_from_file_location("d", SRC); d = importlib.util.module_from_spec(spec); spec.loader.exec_module(d)
me = d.me_user()
victim = subprocess.Popen(["sleep", "600"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # tiến trình thật để thử Buộc dừng
os.environ["ACT_VICTIM"] = str(victim.pid)
CH = "/Applications/Claude.app/Contents/Frameworks/Electron Framework.framework/Helpers/chrome_crashpad_handler"
BR = "/Applications/Brave Browser.app/Contents/Frameworks/Brave Browser Framework.framework/Versions/1/Helpers/Brave Browser Helper (Renderer).app/Contents/MacOS/Brave Browser Helper (Renderer)"
MAIN = f"""{victim.pid} 1 {me} 12000 171.2 2-04:00:00 440:49.03 {CH}
70583 1 {me} 400000 2.7 3-00:00:00 22:54.65 /Applications/Claude.app/Contents/MacOS/Claude
70629 70583 {me} 900000 25.3 3-00:00:00 19:33.74 /Applications/Claude.app/Contents/Frameworks/Claude Helper (Renderer).app/Contents/MacOS/Claude Helper (Renderer)
41896 1 {me} 300000 2.3 01:00:00 34.35 /Applications/Brave Browser.app/Contents/MacOS/Brave Browser
41983 41896 {me} 800000 4.4 01:00:00 35.05 {BR}
41924 41896 {me} 200000 1.3 01:00:00 14.05 {BR}
401 1 _windowserver 500000 12.7 9-00:00:00 1535:07.60 /System/Library/PrivateFrameworks/SkyLight.framework/Resources/WindowServer
0 0 root 0 8.9 9-00:00:00 1352:03.10 kernel_task
5000 1 {me} 150000 0.5 00:10:00 0:03.00 /opt/homebrew/bin/node
7000 1 {me} 5000000 0.0 05:00:00 1:00.00 /Users/x/Library/Android/sdk/emulator/qemu/darwin-aarch64/qemu-system-aarch64
7100 1 {me} 860000 0.0 05:00:00 1:00.00 /Applications/Google Chrome.app/Contents/MacOS/Google Chrome
"""
ARGS = "41983 x --type=renderer\n41924 x --type=renderer --extension-process\n"
VM = """Mach Virtual Memory Statistics: (page size of 16384 bytes)
Pages wired down:                        100000.
Pages purgeable:                          10000.
File-backed pages:                        150000.
Anonymous pages:                         400000.
Pages occupied by compressor:            150000.
"""
_orig_mem = d.mem_summary
d.mem_summary = lambda *a: _orig_mem(VM, "17179869184", "total = 2048.00M  used = 1500.00M  free = 548.00M", "2")


def fake_ps(fields):
    alive = True
    try:
        os.kill(victim.pid, 0)
        alive = victim.poll() is None
    except OSError:
        alive = False
    main = MAIN if alive else "\n".join(l for l in MAIN.splitlines() if not l.startswith(str(victim.pid)))
    return ARGS if fields.startswith("pid=,args=") else main


d.ps_text = fake_ps
TABOUT = (d.RS.join(d.US.join(r) for r in [
    ["1", "11", "1", "false", "false", "", "Video hay - YouTube", "https://www.youtube.com/watch?v=1"],
    ["1", "12", "2", "true", "false", "", "Hộp thư - Gmail", "https://mail.google.com/mail/u/0/"],
    ["1", "13", "3", "false", "false", "", "Figma file", "https://www.figma.com/design/abc"],
    ["1", "14", "4", "false", "false", "", "Video hay - YouTube", "https://www.youtube.com/watch?v=1"],
    ["1", "15", "5", "false", "false", "", "Sign in to GitHub · GitHub", "https://github.com/login"],
    ["1", "16", "6", "false", "false", "", "Dâu Tây Ngọt Ngào (2026) - ONFLIX", "https://onflix.lat/phim/dau-tay"],
    ["1", "17", "7", "false", "false", "", "Week 0 Functions - CS50", "https://cs50.harvard.edu/python/weeks/0/"]]) + d.RS)
CLOSED = []


def fake_tabs(bid, measure=False, groups=None):
    rows = [r for r in d.parse_tab_rows(TABOUT) if r["id"] not in CLOSED]
    if measure:
        for r in rows:
            v = {"11": 300, "12": 120, "13": 90, "14": 280}.get(r["id"])
            r["heap"] = v * d.MB if v else None
    g = next(x for x in d.proc_snapshot() if x["bid"] == bid)
    m = d.rank_tabs(rows, 800 * 1024 * 1024)
    return {"ok": True, "browser": "Brave", "bid": bid, "tabs": rows, "count": len(rows), "measured": m, "js_off": False,
            "can_measure": True, "renderers": [800 * 1024 * 1024], "n_renderers": 1, "ext_mem": 200 * 1024 * 1024, "gpu_mem": 0,
            "total": g["mem"], "render_total": 800 * 1024 * 1024, "sites": d.site_groups(rows),
            "n_close": sum(1 for t in rows if t["close"]), "close_mem": sum(t["est"] for t in rows if t["close"])}


def fake_act(bid, win, tid, idx, url, action):
    if action == "close":
        CLOSED.append(tid)
    return {"ok": True}


def fake_many(bid, items):
    for x in items:
        CLOSED.append(str(x["id"]))
    return {"ok": True, "done": len(items), "fail": 0}


# --- 005: pin, app tốn điện, khởi động, kiểm tra, lịch sử (dữ liệu giả)
import json as _j, plistlib as _p, time as _t
_IO = _p.dumps([{"CurrentCapacity": 64, "MaxCapacity": 100, "Voltage": 12500, "InstantAmperage": 2 ** 64 - 400, "ExternalConnected": True,
                 "IsCharging": True, "AdapterDetails": {"Watts": 30, "Name": "30W USB-C Power Adapter"},
                 "PowerTelemetryData": {"SystemLoad": 33000, "SystemPowerIn": 28000}, "Temperature": 3150, "CycleCount": 399,
                 "DesignCapacity": 4382, "NominalChargeCapacity": 3780}]).decode()
_orig_bi = d.battery_info
d.battery_info = lambda *a, **k: _orig_bi(_IO, "")
d.hw_model = lambda: {"name": "MacBook Air", "model": "Mac14,2", "chip": "Apple M2"}
_orig_ea = d.energy_apps
d.energy_apps = lambda groups=None, top_text=None: _orig_ea(groups, f"PID POWER COMMAND\nPID POWER COMMAND\n{victim.pid} 150.2 c\n41983 22.5 b\n7000 9.1 q\n")
H = os.environ["HOME"]
la = os.path.join(H, "Library/LaunchAgents"); os.makedirs(la, exist_ok=True)
with open(os.path.join(la, "com.google.keystone.agent.plist"), "wb") as f:
    _p.dump({"Label": "com.google.keystone.agent", "ProgramArguments": ["/x/GoogleSoftwareUpdateAgent"], "RunAtLoad": True}, f)
br = os.path.join(H, "Library/Application Support/BraveSoftware/Brave-Browser"); os.makedirs(br, exist_ok=True)
_j.dump({"performance_tuning": {"high_efficiency_mode": {"state": 0}}, "background_mode": {"enabled": True}}, open(os.path.join(br, "Local State"), "w"))
os.makedirs(d.DATA_DIR, exist_ok=True)
with open(os.path.join(d.DATA_DIR, "metrics.jsonl"), "w") as f:
    for i in range(30):
        f.write(_j.dumps({"t": _t.time() - (29 - i) * 6 * 3600, "free": 80e9 - i * 6e8, "total": 245e9, "mem_used": 11e9 + (i % 5) * 1e9,
                          "mem_total": 17.2e9, "swap": 1e9 + i * 1e8, "batt": 40 + (i * 7) % 60}) + "\n")
d.record_scan([{"cat": "caches", "size": 1e9}])
d.record_scan([{"cat": "caches", "size": 4e9}])
d.log_history([{"t": _t.time() - 86400 * 8, "label": "a", "size": 2e9, "mode": "trash"}, {"t": _t.time() - 3600, "label": "b", "size": 7e8, "mode": "trash"}])
# --- 006: nhiệt độ, mạng, quyền riêng tư, dọn sâu, hoàn tác (dữ liệu giả)
_orig_therm = d.thermal
d.thermal = lambda groups=None, therm_text=None, batt=None: _orig_therm(
    groups, "CPU_Scheduler_Limit = 100\nCPU_Available_CPUs = 1\nCPU_Speed_Limit = 68", None)
_NT = """time,name,bytes_in,bytes_out
00:00:01,Brave Browser.41896,1000,200
00:00:01,Claude.70583,500,100
time,name,bytes_in,bytes_out
00:00:02,Brave Browser.41896,8000000,900
00:00:02,Claude.70583,900,100
"""
_orig_net = d.net_apps
d.net_apps = lambda groups=None, text=None, secs=1.0: _orig_net(groups, _NT, 1.0)
import sqlite3 as _sq
_tcc = os.path.join(H, "Library/Application Support/com.apple.TCC"); os.makedirs(_tcc, exist_ok=True)
_c = _sq.connect(os.path.join(_tcc, "TCC.db"))
_c.execute("CREATE TABLE IF NOT EXISTS access (service TEXT, client TEXT, client_type INT, auth_value INT, last_modified INT)")
_c.executemany("INSERT INTO access VALUES (?,?,?,?,?)", [
    ("kTCCServiceScreenCapture", "com.hangx.ghost", 0, 2, 1700000000),
    ("kTCCServiceAccessibility", "com.raycast.macos", 0, 2, 1700000000),
    ("kTCCServiceMicrophone", "us.zoom.xos", 0, 2, 1700000000)])
_c.commit(); _c.close()
for _r, _mb in (("Library/Android/sdk/ndk/26.1.1", 40), ("Library/Android/sdk/system-images/android-30", 45),
                (".gradle/caches/modules-2", 35), (".gradle/caches/build-cache-1", 30),
                (".android/avd/Pixel.avd/snapshots/default", 50), (".npm/_cacache", 25)):
    _dir = os.path.join(H, _r); os.makedirs(_dir, exist_ok=True)
    with open(os.path.join(_dir, "f.bin"), "wb") as _f:
        _f.write(b"\0" * (_mb * 1024 * 1024))
_old = os.path.join(H, "Projects/khac/node_modules"); os.makedirs(_old, exist_ok=True)
d.STATE["items"] = [{"cat": "envs", "label": "node_modules", "size": 900 * 1024 * 1024, "path": _old,
                     "mtime": _t.time() - 200 * 86400}]
d.log_history([{"t": int(_t.time()) - 600, "label": "node_modules (dự án cũ)", "size": 900 * 1024 * 1024,
                "path": "~/Projects/cu/node_modules", "mode": "trash", "kind": "path", "src": "manual",
                "batch": "demo1234", "moved": [[os.path.join(H, "Projects/cu/node_modules"), os.path.join(d.TRASH, "node_modules")]]}])
os.makedirs(d.TRASH, exist_ok=True); os.makedirs(os.path.join(d.TRASH, "node_modules"), exist_ok=True)
d.browser_tabs = fake_tabs
d.tabs_close_many = fake_many
d.tab_action = fake_act
try:
    d.main()
finally:
    victim.kill()
