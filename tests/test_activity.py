#!/usr/bin/env python3
"""Kiểm thử feature 004 (tab Hoạt động). Chạy: python3 tests/test_activity.py"""
import importlib.util, os, sys
SRC = os.path.join(os.path.dirname(__file__), "..", "src", "don_mac.py")
spec = importlib.util.spec_from_file_location("d", SRC); d = importlib.util.module_from_spec(spec); spec.loader.exec_module(d)
n = 0
def check(c, m):
    global n
    if not c: print("❌", m); sys.exit(1)
    n += 1; print("✓", m)
me = d.me_user()
check(d._dur("2-04:00:00") == 2 * 86400 + 4 * 3600 and abs(d._dur("440:49.03") - 26449.03) < 0.01 and d._dur("7:20:49,03") > 26000,
      "đọc thời gian ps (ngày, phút:giây, dấu phẩy)")
rows = d.parse_ps(f"  12 1 {me} 100 171,2 01:00 1:00.00 /Applications/A B.app/Contents/MacOS/A B\nrác\n")
check(len(rows) == 1 and rows[0]["cpu"] == 171.2 and rows[0]["path"].endswith("A B"), "parse_ps: đường dẫn có dấu cách, CPU dấu phẩy")
check(d.parse_args("5 x --type=renderer --extension-process\n6 y --type=utility --utility-sub-type=network.mojom.NetworkService\n")
      == {5: "extension", 6: "network"}, "nhận loại tiến trình Chromium")
check(d.outer_bundle("/Applications/Brave Browser.app/Contents/Frameworks/X.framework/Helpers/H (Renderer).app/Contents/MacOS/H")
      == "/Applications/Brave Browser.app", "gom helper vào app ngoài cùng")
check(d.is_sys_path("/System/Library/CoreServices/Finder.app/Contents/MacOS/Finder") and not d.is_sys_path("/opt/homebrew/bin/node")
      and not d.is_sys_path("/System/Volumes/Preboot/Cryptexes/App/System/Applications/Safari.app/Contents/MacOS/Safari"),
      "phân biệt đường dẫn hệ thống / Safari / Homebrew")
PS = f"""900 1 {me} 12000 171.2 2-04:00:00 440:49.03 /Applications/Claude.app/Contents/Frameworks/Electron Framework.framework/Helpers/chrome_crashpad_handler
901 1 {me} 400000 2.7 3-00:00:00 22:54.65 /Applications/Claude.app/Contents/MacOS/Claude
401 1 _windowserver 500000 12.7 9-00:00:00 1535:07.60 /System/Library/PrivateFrameworks/SkyLight.framework/Resources/WindowServer
950 1 {me} 300000 2.3 01:00:00 34.35 /Applications/Brave Browser.app/Contents/MacOS/Brave Browser
"""
VM = "page size of 16384 bytes\nPages wired down: 100000.\nAnonymous pages: 400000.\nPages purgeable: 10000.\nPages occupied by compressor: 150000.\nFile-backed pages: 1.\n"
mem = d.mem_summary(VM, "17179869184", "total = 2048.00M  used = 1500.00M", "1")
check(mem and mem["pressure"] == "normal" and mem["used"] == (390000 + 100000 + 150000) * 16384, "tính RAM đã dùng như Giám sát hoạt động")
check(d.mem_summary(VM, "17179869184", "", "4")["pressure"] == "critical", "áp lực đỏ khi macOS báo 4")
g = {x["label"]: x for x in d.proc_snapshot(PS, "", mem)}
cl = g["Claude"]
check(cl["n"] == 2 and cl["can_quit"] and any(f["lv"] == "bad" for f in cl["flags"]), "Claude: gom 2 tiến trình, crashpad bị đánh dấu kẹt")
cp = next(p for p in cl["procs"] if "crashpad" in p["name"])
check(cp["killable"] and "Buộc dừng an toàn" in cp["info"]["act"], "crashpad được buộc dừng và có giải thích")
ws = g["WindowServer"]
check(ws["system"] and not ws["procs"][0]["killable"] and not ws["can_quit"] and ws["info"]["what"], "WindowServer: hệ thống, không cho dừng")
check(g["Brave Browser"]["browser"] == "chromium" and "tab" in g["Brave Browser"]["info"]["act"], "Brave nhận là trình duyệt Chromium")
check(all(x["info"].get("when") for x in g.values()), "mọi nhóm có “Nên đóng khi nào”")
sug = d.activity_suggest(list(g.values()), mem)
check(sug and sug[0]["act"]["kind"] == "kill" and sug[0]["act"]["pid"] == 900, "gợi ý đầu tiên: buộc dừng crashpad kẹt")
r = d.proc_kill(os.getpid(), os.path.basename(sys.executable))
check(not r["ok"], "không cho buộc dừng chính Spotless Mac")
check(not d.app_quit("/System/Library/CoreServices/Finder.app")["ok"], "không cho thoát Finder")
check(d.tab_weight("https://www.youtube.com/watch?v=x")[1] >= 700 and d.tab_weight("brave://newtab")[1] < 100
      and d.tab_weight("http://localhost:5173/")[0] == 150, "ước tính tab theo loại trang")
out = d.US.join(["1", "7", "1", "false", "false", "ERR:off", "A", "https://x.com/"]) + d.RS
t = d.parse_tab_rows(out)
check(t[0]["js_err"] == "off" and t[0]["heap"] is None and t[0]["id"] == "7", "đọc dòng tab + lỗi JS")
check(d.aq('a"b\\c') == '"a\\"b\\\\c"', "thoát chuỗi AppleScript")
check(d.browser_tabs("com.evil.app").get("error"), "từ chối trình duyệt không hỗ trợ")
check(not d.tab_action("com.brave.Browser", "1", "2", "x", "", "close")["ok"], "từ chối tab không hợp lệ")
PS2 = PS + f"""7000 1 {me} 5000000 0.0 05:00:00 1:00.00 /Users/x/Library/Android/sdk/emulator/qemu/darwin-aarch64/qemu-system-aarch64
7100 1 {me} 200000 0.0 05:00:00 1:00.00 /Applications/Google Chrome.app/Contents/MacOS/Google Chrome
7200 1 {me} 50000 0.0 05:00:00 1:00.00 /Applications/AltTab.app/Contents/MacOS/AltTab
"""
g2 = {x["label"]: x for x in d.proc_snapshot(PS2, "", mem)}
check(g2["qemu-system-aarch64"]["verdict"]["v"] == "close", "máy ảo rảnh 5 GB → Nên đóng")
check(g2["Google Chrome"]["verdict"]["v"] in ("close", "maybe") and "Brave" in g2["Google Chrome"]["verdict"]["t"], "2 trình duyệt → gợi ý đóng cái nhỏ hơn")
check(g2["WindowServer"]["verdict"]["v"] == "sys" and g2["AltTab"]["verdict"]["v"] == "keep", "hệ thống → Hệ thống; app nhẹ → cứ để")
check(g2["Claude"]["verdict"]["v"] == "fix", "app có tiến trình kẹt → chỉ cần buộc dừng tiến trình đó")
check(all(x["verdict"]["t"] for x in g2.values()), "mọi nhóm có lời giải thích có nên đóng")
s2 = d.activity_suggest(list(g2.values()), mem)
check(any("Nên đóng" in x["t"] and "qemu" in x["t"] for x in s2), "gợi ý tổng: Nên đóng qemu")
check(d.verdict({"label": "X", "bid": "", "mem": 2 * d.GB, "cpu": 0.0, "idle": True, "flags": [], "system": False,
                  "browser": "", "self": False}, dict(mem, pressure="warn"))["v"] == "close", "app rảnh 2 GB khi thiếu RAM → Nên đóng")
print(f"\nALL ACTIVITY TESTS PASSED ({n} kiểm tra)")
