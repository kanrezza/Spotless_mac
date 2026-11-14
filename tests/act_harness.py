#!/usr/bin/env python3
"""Chạy Spotless Mac với dữ liệu tiến trình/tab giả để kiểm thử tab Hoạt động trên máy không phải macOS.
Dùng bởi tests/ui_activity.js: HOME=/tmp/fha python3 tests/act_harness.py --native"""
import importlib.util, os, subprocess, sys
SRC = os.path.join(os.path.dirname(__file__), "..", "src", "don_mac.py")
spec = importlib.util.spec_from_file_location("d", SRC); d = importlib.util.module_from_spec(spec); spec.loader.exec_module(d)
me = d.me_user()
victim = subprocess.Popen(["sleep", "600"])  # tiến trình thật để thử Buộc dừng
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


d.browser_tabs = fake_tabs
d.tabs_close_many = fake_many
d.tab_action = fake_act
try:
    d.main()
finally:
    victim.kill()
