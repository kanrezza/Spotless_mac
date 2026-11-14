#!/usr/bin/env python3
"""Kiểm thử feature 005 (Pin & tối ưu, theo dõi nền, khởi động, lịch sử). Chạy: HOME=/tmp/fho python3 tests/test_optim.py"""
import importlib.util, json, os, plistlib, shutil, subprocess, sys, time
HOME = os.environ.get("HOME", "/tmp/fho")
assert HOME.startswith("/tmp/"), "Chạy với HOME giả, ví dụ HOME=/tmp/fho"
shutil.rmtree(HOME, ignore_errors=True); os.makedirs(HOME)
SRC = os.path.join(os.path.dirname(__file__), "..", "src", "don_mac.py")
spec = importlib.util.spec_from_file_location("d", SRC); d = importlib.util.module_from_spec(spec); spec.loader.exec_module(d)
n = 0
def check(c, m):
    global n
    if not c: print("❌", m); sys.exit(1)
    n += 1; print("✓", m)

def ioreg(**kw):
    b = {"CurrentCapacity": 64, "MaxCapacity": 100, "Voltage": 12500, "InstantAmperage": 2 ** 64 - 400, "ExternalConnected": True,
         "IsCharging": True, "FullyCharged": False, "AdapterDetails": {"Watts": 30, "Name": "30W USB-C Power Adapter"},
         "PowerTelemetryData": {"SystemLoad": 33000, "SystemPowerIn": 28000}, "Temperature": 3150, "CycleCount": 399,
         "DesignCapacity": 4382, "NominalChargeCapacity": 3780}
    b.update(kw)
    return plistlib.dumps([b]).decode()

b = d.battery_info(ioreg(), "")
check(b["pct"] == 64 and b["batt_w"] == -5.0 and b["sys_w"] == 33.0 and b["adapter_w"] == 30, "đọc ioreg: %, công suất pin âm, máy dùng 33W, củ 30W")
check(b["lv"] == "bad" and "TỤT" in b["verdict"] and "30W" in b["verdict"], "pin tụt dù cắm sạc → cảnh báo đỏ nêu củ 30W")
check(b["health"] == 86 and b["temp"] == 31.5 and b["cycles"] == 399, "sức khỏe pin 86%, nhiệt độ, số lần sạc")
b2 = d.battery_info(ioreg(InstantAmperage=3000, PowerTelemetryData={"SystemLoad": 8000}), "")
check(b2["lv"] == "ok" and "sạc tốt" in b2["verdict"], "sạc tốt khi +37W vào pin")
b3 = d.battery_info(ioreg(InstantAmperage=200, CurrentCapacity=40, PowerTelemetryData={"SystemLoad": 26000}), "")
check(b3["lv"] == "warn" and "Sạc chậm" in b3["verdict"], "sạc chậm khi chỉ +2,5W vào pin")
b4 = d.battery_info(ioreg(InstantAmperage=0, IsCharging=False, CurrentCapacity=80), "")
check(b4["lv"] == "ok" and "80%" in b4["verdict"], "giữ ở 80% → giải thích sạc tối ưu")
b5 = d.battery_info(ioreg(InstantAmperage=0, IsCharging=False, CurrentCapacity=50, Temperature=3800), "")
check("nóng" in b5["verdict"], "tạm dừng sạc vì pin nóng")
b6 = d.battery_info(ioreg(ExternalConnected=False, InstantAmperage=2 ** 64 - 800, PowerTelemetryData={}, AvgTimeToEmpty=250), "")
check(b6["lv"] == "info" and "4 giờ 10 phút" in b6["verdict"] and b6["sys_w"] == 10.0, "chạy pin: máy dùng 10W, còn 4 giờ 10 phút")
check(d.battery_info("", "") is None, "máy không có pin → None")
check("yếu hơn" in d.charger_advice({"name": "MacBook Air"}, 20)[1] and "đủ dùng" in d.charger_advice({"name": "MacBook Air"}, 30)[1]
      and "yếu hơn" in d.charger_advice({"name": "MacBook Pro"}, 30)[1], "lời khuyên củ sạc theo Air/Pro")
TOP = "Processes: 1\nPID    POWER COMMAND\n1 0.0 launchd\n\nPID    POWER COMMAND\n900   184.5 crashpad_handler\n41896* 12,3 Brave Browser\n"
check(d.parse_top_power(TOP) == {900: 184.5, 41896: 12.3}, "đọc top power (mẫu thứ hai, dấu phẩy, PID có *)")
me = d.me_user()
PS = f"""900 1 {me} 12000 171.2 2-04:00:00 440:49.03 /Applications/Claude.app/Contents/Frameworks/Electron Framework.framework/Helpers/chrome_crashpad_handler
41896 1 {me} 300000 2.3 01:00:00 34.35 /Applications/Brave Browser.app/Contents/MacOS/Brave Browser
"""
g = d.proc_snapshot(PS, "", None)
ea = d.energy_apps(g, "PID POWER COMMAND\nPID POWER COMMAND\n900 184.5 x\n41896 12.3 y\n")
check(ea[0]["label"] == "Claude" and ea[0]["stuck"] and "tab" in ea[1]["tip"].lower(), "app tốn điện: Claude (kẹt) đứng đầu, Brave có mẹo về tab")
ms = d.mini_status(g, None, b)
check(ms["title"].startswith("⚠︎") and "⚡︎" in ms["title"] and ms["actions"][0]["arg"] == "kill:900:chrome_crashpad_handler",
      "thanh menu: ⚠︎ khi kẹt, ⚡︎ khi pin tụt, có nút buộc dừng")

# --- theo dõi nền: tiến trình kẹt 5 phút → tự buộc dừng (tiến trình thật tên crashpad)
tmpd = os.path.join(HOME, "bin"); os.makedirs(tmpd)
exe = os.path.join(tmpd, "crashpad"); shutil.copy("/bin/sleep", exe)
victim = subprocess.Popen([exe, "600"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
cfg = d.load_cfg(); cfg["watch"] = {"enabled": True, "auto_kill": True, "minutes": 5}; d.save_cfg(cfg)
t0 = 1_800_000_000
ev = []
for i in range(7):
    line = f"{victim.pid} 1 {me} 1000 99.0 01:00:00 {i}:00.00 {exe}\n"
    ev += d.watch_once(now=t0 + i * 60, ps_main=line, batt={"connected": False, "batt_w": 0}, level="1")
time.sleep(0.5)
alive = victim.poll() is None
if alive: victim.kill()
check(any(k == "kill" for k, _ in ev) and not alive, "crashpad ăn 100% CPU 5 phút → tự buộc dừng + ghi nhật ký")
check(any(x["kind"] == "kill" for x in d.read_jsonl("watch.jsonl")), "nhật ký theo dõi có sự kiện")
cfg["watch"] = {"enabled": True, "auto_kill": False, "minutes": 2}; d.save_cfg(cfg)
os.remove(d.wpath("watch_state.json"))
ev2 = []
for i in range(4):
    ev2 += d.watch_once(now=t0 + 1000 + i * 60, ps_main=f"777 1 {me} 1000 50.0 01:00:00 {i * 2}:00.00 /usr/local/bin/node\n",
                        batt={"connected": True, "batt_w": -3.0, "sys_w": 35, "adapter_w": 30}, level="2")
kinds = [k for k, _ in ev2]
check("stuck" in kinds and "battery" in kinds and "pressure" in kinds, "node 200% CPU 2 phút + pin tụt + thiếu RAM → 3 thông báo")
check(kinds.count("stuck") == 1, "không báo lặp lại liên tục (mỗi 30 phút tối đa 1 lần)")

# --- lịch sử
os.makedirs(d.DATA_DIR, exist_ok=True)
with open(d.wpath("metrics.jsonl"), "w") as f:
    now = time.time()
    for i in range(10):
        f.write(json.dumps({"t": now - (9 - i) * 86400 * 0.7, "free": 80e9 - i * 2e9, "total": 245e9, "mem_used": 12e9, "mem_total": 17e9, "swap": 2e9, "batt": 50}) + "\n")
d.record_scan([{"cat": "caches", "size": 1e9}, {"cat": "downloads", "size": 2e9}])
d.record_scan([{"cat": "caches", "size": 4e9}, {"cat": "downloads", "size": 2e9}])
d.log_history([{"t": now - 3600, "label": "x", "size": 5e8, "mode": "trash"}])
tr = d.trends(30)
check(tr["proj"] and tr["proj"]["per_day"] < 0 and 15 < tr["proj"]["days_left"] < 40, "dự báo ổ đầy theo xu hướng 7 ngày")
check(tr["growth"] and tr["growth"][0]["cat"] == "caches" and tr["growth"][0]["delta"] == 3e9, "ổ đầy lên vì đâu: Bộ nhớ đệm +3 GB")
check(tr["freed"] and tr["freed"][-1]["size"] == 5e8, "đã dọn theo tuần")
check(d.record_metric(mem=None, batt=None, force=True) and not d.record_metric(), "ghi mẫu lịch sử tối đa mỗi 30 phút")

# --- khởi động cùng máy
la = os.path.join(HOME, "Library/LaunchAgents"); os.makedirs(la)
with open(os.path.join(la, "com.google.keystone.agent.plist"), "wb") as f:
    plistlib.dump({"Label": "com.google.keystone.agent", "ProgramArguments": ["/nonexistent/GoogleSoftwareUpdateAgent"], "RunAtLoad": True}, f)
st = d.startup_manage()
a = next(x for x in st["agents"] if x["label"] == "com.google.keystone.agent")
check(a["can_toggle"] and a["enabled"] and "Google" in a["name"] and a["broken"], "nhận diện trình cập nhật Google, cho tắt")
check(d.agent_toggle("com.google.keystone.agent.plist", False)["ok"] and not os.path.exists(os.path.join(la, "com.google.keystone.agent.plist")),
      "tắt: chuyển plist vào kho sao lưu")
a2 = next(x for x in d.startup_manage()["agents"] if x["label"] == "com.google.keystone.agent")
check(not a2["enabled"] and d.agent_toggle("com.google.keystone.agent.plist", True)["ok"]
      and os.path.exists(os.path.join(la, "com.google.keystone.agent.plist")), "bật lại: trả plist về chỗ cũ")
check(not d.agent_toggle("../evil.plist", False)["ok"] and not d.agent_toggle("local.donmac.watch.plist", False)["ok"], "chặn tên lạ và mục của Spotless Mac")

# --- kiểm tra cài đặt
br = os.path.join(HOME, "Library/Application Support/BraveSoftware/Brave-Browser")
os.makedirs(br)
json.dump({"performance_tuning": {"high_efficiency_mode": {"state": 0}}, "hardware_acceleration_mode": {"enabled": False},
           "background_mode": {"enabled": True}}, open(os.path.join(br, "Local State"), "w"))
for eid, name in (("aaa", "uBlock Origin"), ("bbb", "__MSG_appName__"), ("ccc", "Dark Reader")):
    v = os.path.join(br, "Default/Extensions", eid, "1.0"); os.makedirs(v)
    json.dump({"name": name, "default_locale": "en"}, open(os.path.join(v, "manifest.json"), "w"))
    if name.startswith("__MSG"):
        os.makedirs(os.path.join(v, "_locales/en"))
        json.dump({"appName": {"message": "Grammarly"}}, open(os.path.join(v, "_locales/en/messages.json"), "w"))
bc = {c["id"]: c for c in d.browser_checks()}
check(bc["brave-memsaver"]["lv"] == "warn" and bc["brave-hw"]["lv"] == "bad" and bc["brave-bg"]["lv"] == "warn", "Brave: phát hiện tắt Tiết kiệm bộ nhớ, tắt tăng tốc phần cứng, chạy nền")
check("Grammarly" in bc["brave-ext"]["text"] and "uBlock Origin" in bc["brave-ext"]["text"] and "thừa" in bc["brave-ext"]["text"],
      "tiện ích: đọc tên __MSG__, cảnh báo Grammarly/Dark Reader và chặn quảng cáo thừa với Brave")
os.makedirs(os.path.join(HOME, "Downloads/Visual Studio Code.app/Contents"))
oc = d.opt_checks([])
check(any(c["id"] == "dlapp-Visual Studio Code.app" and c["action"]["kind"] == "move_app" for c in oc), "app nằm trong Tải về → gợi ý chuyển vào Ứng dụng")
gtr = [{"bundle": "/private/var/folders/x/T/AppTranslocation/ABC/d/Visual Studio Code.app", "label": "Visual Studio Code"}]
oc2 = d.opt_checks(gtr)
check(any(c["id"].startswith("transloc-") and c["action"] and c["action"]["src"].endswith("Downloads/Visual Studio Code.app") for c in oc2),
      "app chạy dạng bản sao tạm (Translocation) → tìm bản gốc trong Tải về")
check(not d.move_app("/etc/passwd")["ok"] and not d.move_app(HOME + "/Documents/X.app")["ok"], "chỉ cho chuyển app từ Tải về/Màn hình nền")
check("NSStatusBar" in d.MENU_SWIFT and "--mini" in d.MENU_SWIFT, "mã Swift thanh menu có sẵn")
print(f"\nALL OPTIM TESTS PASSED ({n} kiểm tra)")
