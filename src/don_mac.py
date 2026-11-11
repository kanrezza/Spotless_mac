#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Dọn Mac 2.0: công cụ dọn dung lượng chạy ngay trên máy bạn.

CÀI THÀNH APP (chỉ cần làm 1 lần), trong Terminal:
    python3 ~/Downloads/don_mac.py --install
→ Biên dịch app gốc macOS "Dọn Mac.app" (cửa sổ riêng, icon trên Dock) vào thư mục Ứng dụng.
  Sau đó mở bằng Launchpad / Spotlight (⌘ + Space, gõ "Dọn Mac") như mọi app khác.
  Bật "Toàn quyền truy cập ổ đĩa" cho Dọn Mac MỘT LẦN là không bị hỏi quyền nữa.

Hoặc chạy trực tiếp không cần cài:
    python3 don_mac.py

- Chỉ dùng thư viện chuẩn của Python, không gửi dữ liệu ra ngoài.
- Server chỉ nghe trên 127.0.0.1 và yêu cầu mã bí mật ngẫu nhiên mỗi lần chạy.
- Chỉ xóa được những mục tool vừa quét ra. Mặc định chuyển vào Thùng rác.
- Đóng tab trình duyệt là app tự tắt.

Dòng lệnh: --auto-clean [--dry-run] [--min-mb N]  dọn các mục An toàn (dùng cho lịch tự động).
"""
import base64
import calendar
import mimetypes
import json
import os
import plistlib
import re
import secrets
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

VERSION = "5.0.1"
APP_NAME = "Dọn Mac"
APP_BUNDLE_ID = "local.donmac.app"
NATIVE = "--native" in sys.argv  # chạy bên trong app gốc (cửa sổ Swift)
APP_MODE = "--app" in sys.argv or NATIVE

# ------------------------------------------------------------------ cấu hình
HOME = os.path.realpath(os.path.expanduser("~"))
TRASH = os.path.join(HOME, ".Trash")
DATA_DIR = os.path.join(HOME, "Library/Application Support/DonMac")  # cấu hình, danh sách giữ, lịch sử
BIG_FILE_BYTES = 50 * 1024 ** 2      # tab "Tệp lớn" (như macOS)
MIN_INSTALLER_BYTES = 1 * 1024 ** 2
CACHE_MIN_BYTES = 20 * 1024 ** 2
APP_MIN_BYTES = 50 * 1024 ** 2
TOKEN = secrets.token_urlsafe(24)

for _p in ("/opt/homebrew/bin", "/usr/local/bin", os.path.join(HOME, ".orbstack/bin")):
    if os.path.isdir(_p) and _p not in os.environ.get("PATH", "").split(os.pathsep):
        os.environ["PATH"] = os.environ.get("PATH", "") + os.pathsep + _p

PROTECTED = {HOME} | {
    os.path.join(HOME, d) for d in (
        "Library", "Desktop", "Documents", "Downloads", "Pictures", "Movies", "Music",
        "Applications", "Public", ".Trash", ".ssh", ".config", "Library/Application Support",
        "Library/Caches", "Library/Containers", "Library/Preferences", "Library/Logs",
    )
}
APP_DIRS = ["/Applications", os.path.join(HOME, "Applications")]
SKIP_BUNDLES = {"com.apple.Safari", APP_BUNDLE_ID}
SOUND_LIBS = ["/Library/Application Support/GarageBand", "/Library/Application Support/Logic",
              "/Library/Audio/Apple Loops"]

CATEGORIES = [
    ("system", "Hệ thống", "Snapshot Time Machine cục bộ: phần lớn của “Dữ liệu hệ thống”."),
    ("apps", "Ứng dụng", "Gỡ app cùng dữ liệu đi kèm (cài đặt, cache). App được chuyển vào Thùng rác."),
    ("docker", "Docker / OrbStack", "Image, container, volume và build cache không còn dùng."),
    ("trash", "Thùng rác", "File đã xóa nhưng vẫn chiếm chỗ cho tới khi dọn sạch Thùng rác."),
    ("dev", "Công cụ lập trình", "Cache build và gói đã tải; công cụ sẽ tự tải lại khi cần."),
    ("sims", "Simulator & máy ảo", "Simulator iOS, runtime Xcode, máy ảo và system image Android."),
    ("envs", "node_modules, môi trường ảo & thư mục build", "Cài/build lại được: npm install, pip install, cargo build, pod install, flutter pub get…"),
    ("installers", "File cài đặt & file nén", "File .dmg, .pkg, .zip… thường không cần giữ sau khi đã cài/giải nén."),
    ("caches", "Bộ nhớ đệm ứng dụng", "Ứng dụng sẽ tự tạo lại. Nên đóng ứng dụng đó trước khi xóa."),
    ("appcache", "Cache trong dữ liệu ứng dụng", "Cache của Discord, Slack, VS Code, Zalo, trình duyệt… nằm trong Application Support/Containers."),
    ("appdata", "Dữ liệu ứng dụng lớn", "Dữ liệu chính của app (tin nhắn, file đã nhận…). Bấm “Vì sao?” trước khi xóa."),
    ("backups", "Sao lưu iPhone/iPad", "Chỉ xóa khi đã có bản sao lưu khác (iCloud) hoặc không cần nữa."),
    ("logs", "Nhật ký (Logs)", "File log của ứng dụng, xóa an toàn."),
]

DEV_PATHS = [
    ("Library/Developer/Xcode/DerivedData", "Xcode DerivedData", "safe", "Kết quả build tạm của Xcode."),
    ("Library/Developer/Xcode/iOS DeviceSupport", "Xcode iOS DeviceSupport", "safe", "Tự tạo lại khi cắm thiết bị."),
    ("Library/Developer/Xcode/macOS DeviceSupport", "Xcode macOS DeviceSupport", "safe", ""),
    ("Library/Developer/Xcode/Archives", "Xcode Archives", "careful", "Bản build đã archive; cần nếu muốn đọc crash log cũ."),
    ("Library/Developer/CoreSimulator/Caches", "Simulator caches", "safe", ""),
    (".npm/_cacache", "npm cache", "safe", ""),
    ("Library/pnpm/store", "pnpm store", "safe", ""),
    ("Library/Caches/Yarn", "Yarn cache", "safe", ""),
    (".gradle/caches", "Gradle caches", "safe", ""),
    (".m2/repository", "Maven repository", "safe", ""),
    (".cargo/registry", "Cargo registry", "safe", ""),
    ("go/pkg/mod", "Go module cache", "safe", ""),
    (".nuget/packages", "NuGet packages (.NET)", "safe", "Tự tải lại khi build."),
    (".pub-cache/hosted", "Pub cache (Flutter/Dart)", "safe", "Chạy flutter pub get để tải lại."),
    ("Library/Caches/pip", "pip cache", "safe", ""),
    ("miniconda3/pkgs", "Conda pkgs (miniconda3)", "safe", ""),
    ("anaconda3/pkgs", "Conda pkgs (anaconda3)", "safe", ""),
    ("opt/anaconda3/pkgs", "Conda pkgs (anaconda3)", "safe", ""),
    (".cache/huggingface", "Model Hugging Face", "careful", "Model/dataset đã tải; xóa thì phải tải lại."),
    (".ollama/models", "Model Ollama", "careful", "Model đã tải; xóa thì phải tải lại."),
]

WALK_SKIP_TOP = {"Library", ".Trash", "OrbStack", "Applications"}
WALK_SKIP_SUFFIX = (".app", ".photoslibrary", ".musiclibrary", ".tvlibrary", ".photolibrary", ".fcpbundle")
WALK_SKIP_PATHS = {os.path.join(HOME, p) for p in (
    ".cache", ".npm", ".gradle", ".m2", ".cargo", "go/pkg", ".ollama", ".nuget", ".pub-cache",
    ".rustup", ".android", "Music/Music", "Music/iTunes", "Movies/TV", "Pictures/Photo Booth Library",
    "miniconda3/pkgs", "anaconda3/pkgs", "opt/anaconda3/pkgs", ".orbstack",
)}
INSTALLER_EXT = {".dmg", ".pkg", ".mpkg", ".iso", ".xip"}
ARCHIVE_EXT = {".zip", ".rar", ".7z", ".tar", ".gz", ".tgz", ".bz2", ".xz"}

# ------------------------------------------------------------------ trạng thái
STATE = {"running": False, "step": "", "items": [], "warnings": [], "scanned_at": None, "need_fda": False}
ITEMS = {}
LOCK = threading.Lock()
ENTRIES = {}        # id -> Entry (tab Tệp lớn / Bản tải về / Trình duyệt tệp)
PATH2ID = {}
TABS = {"big": [], "downloads": []}
DIRSIZE = {}
DIR_PENDING = set()
SIZE_POOL = ThreadPoolExecutor(max_workers=4)
THUMB_DIR = tempfile.mkdtemp(prefix="donmac-thumbs-")
QL_PROC = [None]
LAST_PING = [time.time()]
BYE_AT = [0.0]
BUSY = [0]


# ------------------------------------------------------------------ tiện ích
def run(cmd, timeout=60):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except Exception:
        return None


def du(path):
    r = run(["du", "-sk", path], timeout=900)
    try:
        return int(r.stdout.strip().splitlines()[-1].split()[0]) * 1024
    except Exception:
        return 0


def du_many(paths):
    with ThreadPoolExecutor(max_workers=8) as ex:
        return list(ex.map(du, paths))


def listdir(path):
    try:
        return sorted(os.listdir(path))
    except OSError:
        return []


def item_akey(cat, label, kind, risk):
    if cat in ("trash", "logs", "cache", "appcache", "backups"):
        return {"backups": "backup", "cache": "cache", "caches": "cache"}.get(cat, cat)
    if cat == "caches":
        return "cache"
    if cat == "system":
        return "tm_snap"
    if cat == "apps":
        return "sound_lib" if kind == "admin_cmd" else ("app_old" if risk == "safe" else "app_recent")
    if cat == "docker":
        return {"Image": "docker_images", "Container": "docker_containers", "Build": "docker_build",
                "Volume": "docker_volumes"}.get(label.split()[0], "docker_images")
    if cat == "dev":
        for k, v in (("Archives", "dev_archives"), ("Model", "dev_models"), ("Homebrew", "brew"),
                     ("~/.cache", "dotcache"), ("DeviceSupport", "dev_devsupport")):
            if k in label:
                return v
        return "dev_cache"
    if cat == "sims":
        for k, v in (("Simulator không", "sims_bad"), ("Runtime", "sims_runtime"), ("Máy ảo Android", "android_avd"),
                     ("system image", "android_img")):
            if k in label:
                return v
    if cat == "envs":
        return "node_modules" if label.endswith("node_modules") else "venv"
    return None


def add(items, cat, label, size, path=None, cmd=None, kind="path", risk="safe", note="", mtime=None,
        extra=None, shell=None, unknown_ok=False, akey=None, advice=None):
    """size=None nghĩa là không đo được dung lượng (vẫn hiện nếu unknown_ok)."""
    if size is None:
        if not unknown_ok:
            return
    elif size <= 0:
        return
    it = {"id": uuid.uuid4().hex[:12], "cat": cat, "label": label,
          "size": None if size is None else int(size), "path": path, "kind": kind,
          "risk": risk, "note": note, "mtime": mtime}
    for k, v in (("cmd", cmd), ("extra", extra), ("shell", shell)):
        if v:
            it[k] = v
    if advice is None and cat == "installers" and path:
        try:
            r, advice = advise_path(path, False, size, None)
            it["risk"] = r
        except Exception:
            advice = None
    it["advice"] = advice or ADVICE.get(akey or item_akey(cat, label, kind, risk) or "")
    items.append(it)


_SIZE_RE = re.compile(r"([\d.]+)\s*([kKMGT]?B)")
_SIZE_MULT = {"B": 1, "kB": 1e3, "KB": 1e3, "MB": 1e6, "GB": 1e9, "TB": 1e12}


def parse_docker_size(s):
    m = _SIZE_RE.search(s or "")
    return int(float(m.group(1)) * _SIZE_MULT.get(m.group(2), 1)) if m else 0


def mtime_of(path):
    try:
        return os.lstat(path).st_mtime
    except OSError:
        return None


def as_str(s):
    """Thoát chuỗi để nhúng vào AppleScript."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def human(n):
    for u in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.0f} {u}" if u in ("B", "KB") else f"{n:.1f} {u}".replace(".", ",")
        n /= 1024
    return f"{n:.1f} PB"


def has_fda():
    """Có “Toàn quyền truy cập ổ đĩa” chưa: thư mục TCC chỉ đọc được khi đã có quyền."""
    try:
        os.listdir(os.path.join(HOME, "Library/Application Support/com.apple.TCC"))
        return True
    except PermissionError:
        return False
    except OSError:
        return True


def bundle_path():
    for base in ("/Applications", os.path.join(HOME, "Applications")):
        b = os.path.join(base, f"{APP_NAME}.app")
        if os.path.isdir(b):
            return b
    return None


def sys_info():
    info = {}
    r = run(["sysctl", "-n", "kern.boottime"], 5)
    m = re.search(r"sec = (\d+)", r.stdout if r else "")
    if m:
        info["uptime_days"] = (time.time() - int(m.group(1))) / 86400
    r = run(["sysctl", "-n", "vm.swapusage"], 5)
    m = re.search(r"used = ([\d.]+)M", r.stdout if r else "")
    if m:
        info["swap_gb"] = float(m.group(1)) / 1024
    return info


# ------------------------------------------------------------------ Entry (các tab kiểu macOS)
EXT_KIND = {
    ".jpg": "Ảnh JPEG", ".jpeg": "Ảnh JPEG", ".png": "Ảnh PNG", ".gif": "Ảnh GIF", ".heic": "Hình ảnh HEIF",
    ".heif": "Hình ảnh HEIF", ".webp": "Ảnh WebP", ".tiff": "Ảnh TIFF", ".tif": "Ảnh TIFF", ".bmp": "Ảnh BMP",
    ".svg": "Ảnh SVG", ".pdf": "Tài liệu PDF", ".doc": "Microsoft Word", ".docx": "Microsoft Word",
    ".xls": "Microsoft Excel", ".xlsx": "Microsoft Excel", ".ppt": "Microsoft PowerPoint",
    ".pptx": "Microsoft PowerPoint", ".pages": "Tài liệu Pages", ".numbers": "Bảng tính Numbers",
    ".key": "Bài thuyết trình Keynote", ".txt": "Văn bản thuần", ".md": "Markdown", ".csv": "Văn bản CSV",
    ".json": "JSON", ".py": "Mã nguồn Python", ".js": "JavaScript", ".ts": "TypeScript", ".html": "HTML",
    ".mp4": "Video MPEG-4", ".mov": "Phim QuickTime", ".m4v": "Video MPEG-4", ".mkv": "Video Matroska",
    ".avi": "Video AVI", ".webm": "Video WebM", ".mp3": "Âm thanh MP3", ".m4a": "Âm thanh MPEG-4",
    ".wav": "Âm thanh WAV", ".flac": "Âm thanh FLAC", ".aac": "Âm thanh AAC", ".zip": "Tệp lưu trữ ZIP",
    ".rar": "Tệp lưu trữ RAR", ".7z": "Tệp lưu trữ 7z", ".tar": "Tệp lưu trữ tar", ".gz": "Tệp nén gzip",
    ".dmg": "Ảnh Đĩa", ".iso": "Ảnh Đĩa ISO", ".pkg": "Gói cài đặt", ".app": "Ứng dụng",
    ".ipa": "Ứng dụng iOS", ".apk": "Ứng dụng Android", ".psd": "Ảnh Photoshop", ".sketch": "Tệp Sketch",
    ".fig": "Tệp Figma", ".epub": "Sách EPUB", ".log": "Nhật ký", ".sqlite": "Cơ sở dữ liệu SQLite",
}
PV_IMAGE = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".heic", ".heif", ".tif", ".tiff", ".avif", ".ico"}
PV_VIDEO = {".mp4", ".mov", ".m4v", ".webm"}
PV_AUDIO = {".mp3", ".m4a", ".wav", ".aac", ".flac", ".aiff", ".aif", ".ogg"}
PV_TEXT = {".txt", ".md", ".csv", ".tsv", ".json", ".xml", ".yml", ".yaml", ".toml", ".ini", ".cfg", ".log",
           ".py", ".js", ".ts", ".tsx", ".jsx", ".html", ".css", ".scss", ".java", ".kt", ".c", ".h", ".cpp",
           ".hpp", ".cs", ".go", ".rs", ".rb", ".php", ".swift", ".dart", ".sh", ".zsh", ".sql", ".r", ".tex",
           ".env", ".gitignore", ".dockerfile", ".vue", ".svelte", ".lua", ".pl"}
PREVIEW_MAX_INLINE = 50 * 1024 ** 2
LIB = os.path.join(HOME, "Library")
LIB_OK = tuple(os.path.join(LIB, d) + os.sep for d in (
    "Caches", "Logs", "Developer", "Application Support", "Containers", "Group Containers",
    "Saved Application State", "HTTPStorages", "WebKit"))
NO_DELETE_PREFIX = tuple(os.path.join(HOME, d) + os.sep for d in (".ssh", ".gnupg", ".Trash"))


def deletable(path):
    """Có được phép xóa mục này khi duyệt tự do không (research R6)."""
    if not is_safe(path) or keep_conflict(path):
        return False
    full = os.path.join(os.path.realpath(os.path.dirname(path)), os.path.basename(path))
    if (full + os.sep).startswith(LIB + os.sep):
        return full.startswith(LIB_OK)
    return not full.startswith(NO_DELETE_PREFIX)


def preview_kind(path, is_dir, size):
    if is_dir:
        return "dir"
    ext = os.path.splitext(path)[1].lower()
    if ext in PV_IMAGE:
        return "image" if (size or 0) <= PREVIEW_MAX_INLINE and ext not in (".heic", ".heif", ".tif", ".tiff") \
            else "thumb"
    if ext == ".pdf":
        return "pdf"
    if ext in PV_VIDEO:
        return "video"
    if ext in PV_AUDIO:
        return "audio"
    if ext in PV_TEXT or (not ext and (size or 0) < 2 * 1024 ** 2):
        return "text"
    return "thumb"


def kind_of(path, is_dir):
    if is_dir:
        ext = os.path.splitext(path)[1].lower()
        return EXT_KIND.get(ext, "Thư mục") if ext in (".app",) else "Thư mục"
    ext = os.path.splitext(path)[1].lower()
    return EXT_KIND.get(ext) or ((ext[1:].upper() + " tệp") if ext else "Tài liệu")


# ------------------------------------------------------------------ Lời khuyên "Có nên xóa?" (feature 002)
def A(what, ok, keep, tip="", when=""):
    """Lời khuyên 5 phần: Đây là gì, Xóa được gì, Vì sao nên cân nhắc, Nên làm gì, Nên xóa khi nào."""
    return {"what": what, "ok": ok, "keep": keep, "tip": tip, "when": when}


ADVICE = {
    "trash": A("Những gì bạn đã xóa trước đó nhưng vẫn nằm trong Thùng rác và vẫn chiếm ổ đĩa.",
               "Mọi thứ trong Thùng rác, nếu chắc không cần khôi phục.",
               "Sau khi dọn sạch thì không lấy lại được nữa, kể cả các file Dọn Mac vừa chuyển vào.",
               "Mở Thùng rác trong Finder lướt qua một lần trước khi dọn."),
    "tm_snap": A("Bản chụp nhanh Time Machine lưu tạm ngay trên ổ máy, được tạo mỗi giờ khi có bật Time Machine.",
                 "Tất cả: bản sao lưu thật trên ổ Time Machine không bị ảnh hưởng.",
                 "Mất khả năng khôi phục file về vài giờ trước khi chưa cắm ổ sao lưu. macOS cũng tự xóa chúng khi thiếu chỗ.",
                 "Đây thường là phần lớn của “Dữ liệu hệ thống”. Cần nhập mật khẩu máy."),
    "app_old": A("Ứng dụng đã lâu không mở, cùng dữ liệu đi kèm (cài đặt, cache).",
                 "App và dữ liệu đi kèm: tất cả vào Thùng rác, tải lại được từ App Store/trang chủ.",
                 "Dữ liệu đi kèm có thể chứa cài đặt, tài khoản đăng nhập hoặc file nội bộ của app (ví dụ lịch sử chat).",
                 "Nếu cần giữ dữ liệu, gỡ app bằng Finder thay vì Dọn Mac."),
    "app_recent": A("Ứng dụng bạn mới dùng gần đây (hoặc macOS chưa ghi nhận lần mở).",
                    "App bạn chắc chắn không dùng nữa.",
                    "Bạn vẫn đang dùng app này. Gỡ đi sẽ mất cả cài đặt và dữ liệu đi kèm của nó.",
                    "Xem dòng “Mở lần cuối” để quyết định. Thoát app trước khi xóa."),
    "sound_lib": A("Loop, nhạc cụ ảo và mẫu âm thanh của GarageBand/Logic Pro.",
                   "Toàn bộ, nếu bạn không dùng GarageBand (Tạo Nhạc) hay Logic.",
                   "Xóa vĩnh viễn (không vào Thùng rác). Nếu mở lại GarageBand sẽ phải tải lại vài GB.",
                   "Nếu đã gỡ GarageBand ở nhóm Ứng dụng thì nên xóa luôn phần này."),
    "docker_images": A("Image Docker không còn container nào dùng.",
                       "Image cũ, image thử nghiệm, các bản build trung gian.",
                       "Lần sau chạy project cần pull/build lại, có thể mất vài phút và tốn mạng.",
                       "Xem trước bằng lệnh: docker images"),
    "docker_containers": A("Container đã dừng (không chạy).",
                           "Container tạm, container thử nghiệm đã xong việc.",
                           "Dữ liệu ghi bên trong container (không nằm trong volume) sẽ mất.",
                           "Xem trước bằng lệnh: docker ps -a"),
    "docker_build": A("Cache của lệnh docker build.", "Toàn bộ.",
                      "Lần build kế tiếp chậm hơn một chút. Không mất dữ liệu.", ""),
    "docker_volumes": A("Volume Docker không gắn với container nào: thường là dữ liệu database (Postgres, MySQL, Mongo…).",
                        "Volume của project đã bỏ hoặc dữ liệu thử nghiệm.",
                        "Đây là DỮ LIỆU THẬT. Xóa là mất database của project, không có Thùng rác.",
                        "Kiểm tra bằng: docker volume ls. Sao lưu volume quan trọng trước."),
    "dev_cache": A("Cache gói/thư viện của công cụ lập trình.",
                   "Toàn bộ: công cụ sẽ tự tải lại khi cần.",
                   "Lần build/cài đặt tiếp theo tải lại từ mạng, chậm hơn một chút.", ""),
    "dev_devsupport": A("Ký hiệu gỡ lỗi Xcode tải về cho từng phiên bản iOS/macOS bạn từng cắm máy.",
                        "Các phiên bản iOS cũ bạn không còn dùng.",
                        "Cắm lại thiết bị phiên bản đó thì Xcode tải lại (vài phút).", ""),
    "dev_archives": A("Bản build đã Archive trong Xcode (để nộp App Store/TestFlight).",
                      "Archive của bản đã phát hành lâu, app đã bỏ.",
                      "Cần archive (dSYM) để đọc crash log của các bản đang có người dùng.",
                      "Giữ lại archive của bản mới nhất mỗi app."),
    "dev_models": A("Model AI/dataset đã tải về máy.", "Model không còn dùng.",
                    "Muốn dùng lại phải tải lại, thường rất nặng (vài GB).", ""),
    "brew": A("File tải và phiên bản cũ của các gói Homebrew.", "Toàn bộ (chạy brew cleanup).",
              "Không thể quay về phiên bản cũ của gói mà không tải lại.", ""),
    "dotcache": A("Cache của công cụ dòng lệnh trong ~/.cache.",
                  "Phần lớn là cache tải về, tạo lại được.",
                  "Một số công cụ để model hoặc dữ liệu đáng giá ở đây. Xem tên thư mục trước khi xóa.",
                  "Bấm “Hiện trong Finder” để xem bên trong."),
    "sims_bad": A("Simulator của các phiên bản iOS đã gỡ, không mở được nữa.", "Toàn bộ.",
                  "Không có lý do giữ.", ""),
    "sims_runtime": A("Bộ chạy simulator iOS/watchOS/visionOS của Xcode.",
                      "Runtime của phiên bản iOS bạn không còn test.",
                      "Muốn test lại trên phiên bản đó phải tải lại trong Xcode (vài GB).",
                      "Giữ lại runtime mới nhất."),
    "android_avd": A("Máy ảo Android Emulator cùng dữ liệu bên trong.",
                     "Máy ảo cũ không còn dùng.",
                     "Mất app đã cài, dữ liệu, tài khoản đăng nhập trong máy ảo đó. Tắt máy ảo trước khi xóa.",
                     "Cách chuẩn: Android Studio → Device Manager → ⋮ → Delete."),
    "android_img": A("System image Android dùng để tạo máy ảo.",
                     "Phiên bản Android không còn dùng.",
                     "Máy ảo dùng image này sẽ không chạy được cho tới khi tải lại.",
                     "Tải lại trong Android Studio → SDK Manager."),
    "node_modules": A("Thư viện npm cài cho một project.",
                      "node_modules của project cũ/không còn làm.",
                      "Muốn chạy lại project phải npm install (tốn thời gian + mạng). Project đang làm thì giữ.",
                      "Xem ngày “Sửa lần cuối” để biết project còn dùng không."),
    "build_artifact": A("Thư mục sinh ra khi build/chạy dự án (Rust target, CocoaPods Pods, .next, .dart_tool, build…).",
                        "Toàn bộ thư mục: được tạo lại hoàn toàn từ mã nguồn.",
                        "Lần build kế tiếp lâu hơn vì phải biên dịch/tải lại, và cần mạng để tải thư viện. Đừng xóa nếu đang build dở hoặc làm việc offline.",
                        "Xóa ở dự án không còn làm việc là hợp lý nhất."),
    "venv": A("Môi trường ảo Python của một project.",
              "venv của project cũ.",
              "Muốn chạy lại phải tạo venv và pip install lại. Nếu thiếu requirements.txt có thể không biết cài gì.",
              "Kiểm tra project có requirements.txt/pyproject.toml trước."),
    "installer": A("File cài đặt ứng dụng (.dmg, .pkg, .iso).",
                   "File cài đặt của app đã cài xong.",
                   "Nếu app chưa cài, hoặc bản này khó tải lại (bản cũ, bản có license), hãy giữ.", ""),
    "archive": A("File nén (.zip, .rar, .7z…).",
                 "File nén đã giải nén ra rồi.",
                 "Nếu chưa giải nén, đây có thể là bản duy nhất của dữ liệu bên trong.",
                 "Mở xem trước hoặc Quick Look để biết bên trong có gì."),
    "cache": A("Bộ nhớ đệm của ứng dụng trong ~/Library/Caches.",
               "Toàn bộ: app tự tạo lại.",
               "App có thể mở chậm hơn lần đầu, có thể phải tải lại ảnh/thumbnail.",
               "Thoát app đó trước khi xóa."),
    "appcache": A("Thư mục cache bên trong dữ liệu của app (thường là app Electron như Discord, Slack, VS Code, Zalo…).",
                  "Toàn bộ: chỉ là dữ liệu tạm.",
                  "App sẽ tải lại ảnh/nội dung, lần mở đầu chậm hơn.",
                  "Thoát app đó trước khi xóa."),
    "appdata": A("Dữ liệu chính của ứng dụng: tin nhắn, file đã nhận, cài đặt, tài khoản.",
                 "Chỉ khi bạn đã gỡ app hoặc không cần dữ liệu trên máy nữa.",
                 "Xóa nguyên thư mục = mất lịch sử, file đã tải, cài đặt; app có thể bị đăng xuất hoặc lỗi.",
                 "Nên dọn từ bên trong app (mục quản lý bộ nhớ/dung lượng trong Cài đặt của app)."),
    "backup": A("Bản sao lưu iPhone/iPad trên máy.",
                "Bản sao lưu của máy cũ đã bán hoặc đã có bản sao lưu iCloud mới hơn.",
                "Đây có thể là bản sao lưu DUY NHẤT của tin nhắn, ảnh, dữ liệu app trên điện thoại.",
                "Kiểm tra iPhone → Cài đặt → [tên] → iCloud → Sao lưu iCloud trước khi xóa."),
    "logs": A("Nhật ký hoạt động của các ứng dụng.", "Toàn bộ.",
              "Chỉ cần nếu đang gửi báo lỗi cho nhà phát triển.", ""),
}

# "Nên xóa khi nào" cho từng nhóm Đề xuất
WHEN = {
    "trash": "Khi bạn đã lướt qua Thùng rác và chắc chắn không cần khôi phục gì. Làm sau cùng, vì các file Dọn Mac vừa chuyển vào cũng nằm ở đây.",
    "tm_snap": "Khi ổ đĩa sắp đầy và bạn cần chỗ ngay. Không cần làm thường xuyên: macOS tự xóa snapshot khi thiếu chỗ.",
    "app_old": "Khi app đã hơn 6 tháng không mở và bạn không nhớ dùng nó vào việc gì. Cần lại thì tải lại được.",
    "app_recent": "Chỉ khi bạn đã quyết định thôi dùng app này hẳn (ví dụ đã chuyển sang app khác) và đã xuất/sao lưu dữ liệu cần giữ.",
    "sound_lib": "Khi bạn không còn làm nhạc bằng GarageBand/Logic, hoặc đã gỡ các app đó. Còn dùng thì giữ.",
    "docker_images": "Khi xong một đợt làm việc và cần chỗ, sau khi chạy docker images mà không thấy image nào đang cần. Tránh làm đúng lúc sắp deploy hoặc đang không có mạng.",
    "docker_containers": "Khi các container đó đã xong việc (kiểm tra bằng docker ps -a). Đừng xóa container chứa dữ liệu chưa sao lưu.",
    "docker_build": "Bất cứ lúc nào cần chỗ; hợp lý nhất khi ổ gần đầy hoặc sau khi xong dự án.",
    "docker_volumes": "Chỉ khi chắc chắn project dùng volume đó đã bỏ hẳn hoặc dữ liệu đã được sao lưu. Còn do dự thì đừng xóa.",
    "dev_cache": "Khi cần chỗ, hoặc khi build báo lỗi lạ nghi cache hỏng. Nên làm khi có mạng vì lần build sau phải tải lại.",
    "dev_devsupport": "Khi bạn đã nâng iPhone/iPad lên iOS mới và không còn cắm thiết bị chạy bản cũ.",
    "dev_archives": "Khi app đã phát hành hơn 1 năm hoặc đã có archive mới hơn của cùng app. Luôn giữ bản mới nhất của mỗi app.",
    "dev_models": "Khi bạn không còn chạy model/dataset đó (hơn vài tháng) và chấp nhận tải lại nếu cần.",
    "brew": "Làm đều đặn mỗi vài tuần: rất an toàn vì chỉ dọn bản cũ.",
    "dotcache": "Khi cần chỗ và bạn đã xem tên thư mục, biết công cụ nào sinh ra nó. Thư mục chứa model thì để nguyên trừ khi không dùng nữa.",
    "sims_bad": "Ngay bây giờ: simulator này không còn mở được.",
    "sims_runtime": "Khi bạn không còn test trên phiên bản iOS/watchOS đó. Giữ lại runtime mới nhất.",
    "android_avd": "Khi dự án dùng máy ảo đó đã xong và bạn không cần dữ liệu bên trong. Xóa qua Android Studio → Device Manager.",
    "android_img": "Khi bạn không còn tạo máy ảo bằng phiên bản Android đó.",
    "node_modules": "Khi project đã hơn vài tháng không đụng tới. Project đang làm thì giữ để khỏi cài lại.",
    "build_artifact": "Khi dự án đã lâu không build, hoặc khi bạn cần chỗ. Build lại sẽ tạo lại thư mục này.",
    "venv": "Khi project Python đã bỏ, hoặc khi venv bị lỗi và bạn muốn tạo lại cho sạch.",
    "installer": "Ngay sau khi cài xong app. Hoặc khi file nằm trong Tải về hơn vài tuần mà bạn vẫn chưa cài.",
    "archive": "Sau khi đã giải nén và kiểm tra dữ liệu bên trong đầy đủ.",
    "cache": "Khi cần chỗ, hoặc khi app chạy chậm/lỗi lạ (cache hỏng). Thoát app trước.",
    "appcache": "Khi cần chỗ, hoặc khi app lag/lỗi hiển thị. Không cần làm thường xuyên.",
    "appdata": "Chỉ khi bạn đã gỡ app, hoặc dọn từ bên trong app vẫn chưa đủ. App còn dùng hằng ngày thì dọn trong Cài đặt của app thay vì xóa thư mục.",
    "backup": "Khi đã có bản sao lưu iCloud mới hơn, hoặc điện thoại/máy tính bảng đó không còn dùng.",
    "logs": "Bất cứ lúc nào cần chỗ, hoặc sau khi xử lý xong lỗi bạn đang điều tra.",
}
for _k, _w in WHEN.items():
    ADVICE[_k]["when"] = _w
assert all(ADVICE[k].get("when") for k in ADVICE), [k for k in ADVICE if not ADVICE[k].get("when")]


# Thư mục con thường gặp trong dữ liệu của app Electron/Chromium: tên -> (rủi ro, đây là gì, xóa được, cân nhắc, khi nào)
ELECTRON_DIRS = {
    "CertificateRevocation": ("safe", "Danh sách chứng chỉ bị thu hồi (CRLSet) mà lõi Chromium tải về để kiểm tra kết nối an toàn.",
                              "Toàn bộ: tự tải lại khi app mở.", "Không mất dữ liệu nào của bạn. Chỉ tốn vài MB mạng để tải lại.",
                              "Bất cứ lúc nào, thường chỉ vài MB nên không đáng làm riêng. Xóa kèm các cache khác khi dọn app."),
    "Crashpad": ("safe", "Báo cáo sự cố (crash dump) chờ gửi về nhà phát triển.", "Toàn bộ.",
                 "Mất các báo cáo lỗi chưa gửi; không ảnh hưởng dữ liệu của bạn.", "Khi cần chỗ; hoặc sau khi app đã hết crash."),
    "component_crx_cache": ("safe", "Gói thành phần Chromium (CRX) đã tải về.", "Toàn bộ: tự tải lại.", "Chỉ tải lại một lần.", "Khi cần chỗ."),
    "extensions_crx_cache": ("safe", "Bản tải về của các tiện ích mở rộng.", "Toàn bộ: tự tải lại.", "Tiện ích cài lại từ cache nên chậm hơn lần đầu.", "Khi cần chỗ."),
    "GrShaderCache": ("safe", "Cache shader đồ họa.", "Toàn bộ.", "Lần mở đầu vẽ giao diện chậm hơn một chút.", "Khi cần chỗ hoặc khi giao diện app bị lỗi hiển thị."),
    "GraphiteDawnCache": ("safe", "Cache shader đồ họa (Dawn/Graphite).", "Toàn bộ.", "Lần mở đầu vẽ giao diện chậm hơn một chút.", "Khi cần chỗ hoặc khi app lỗi hiển thị."),
    "ShaderCache": ("safe", "Cache shader đồ họa.", "Toàn bộ.", "Lần mở đầu vẽ giao diện chậm hơn một chút.", "Khi cần chỗ hoặc khi app lỗi hiển thị."),
    "Shared Dictionary": ("safe", "Từ điển nén dùng chung do trang web/app tải về để tải nhanh hơn.", "Toàn bộ.", "Lần tải kế tiếp hơi chậm.", "Khi cần chỗ."),
    "blob_storage": ("safe", "Dữ liệu tạm của trang web/app (blob).", "Toàn bộ khi app đã đóng.", "Đóng app trước, kẻo mất dữ liệu đang dùng dở.", "Sau khi thoát hẳn app, khi cần chỗ."),
    "Dictionaries": ("safe", "Từ điển kiểm tra chính tả đã tải về.", "Toàn bộ: tự tải lại.", "Cần mạng để tải lại.", "Khi cần chỗ."),
    "logs": ("safe", "Nhật ký hoạt động của app.", "Toàn bộ.", "Mất thông tin để điều tra lỗi cũ.", "Khi cần chỗ, hoặc sau khi xử lý xong lỗi."),
    "Service Worker": ("review", "Dữ liệu chạy ngầm và bộ nhớ đệm offline của giao diện web trong app.", "Thường xóa được: app tải lại khi mở.",
                       "Một số nội dung chỉ dùng được offline sẽ phải tải lại; chưa đến mức mất dữ liệu cá nhân.", "Khi app lỗi hiển thị lạ hoặc cần chỗ; thoát app trước."),
    "Session Storage": ("review", "Trạng thái các cửa sổ/tab đang mở của app (để khôi phục sau khi mở lại).", "Xóa được.",
                        "App có thể không khôi phục lại các cửa sổ cũ.", "Khi app mở chậm hoặc treo ở màn hình cũ."),
    "Local Storage": ("careful", "Cài đặt và mã đăng nhập (token) mà giao diện web của app lưu trên máy.", "Chỉ khi chấp nhận đăng nhập lại.",
                      "Xóa sẽ bị đăng xuất và mất cài đặt cục bộ của app.", "Khi app không đăng nhập được hoặc bạn muốn đăng xuất sạch khỏi máy này."),
    "IndexedDB": ("careful", "Cơ sở dữ liệu cục bộ của giao diện web trong app (có thể gồm dữ liệu offline, cache hội thoại).", "Chỉ khi chấp nhận app tải lại dữ liệu hoặc đăng nhập lại.",
                  "Dữ liệu chỉ có trên máy (nếu có) sẽ mất; dữ liệu đã đồng bộ lên tài khoản thì lấy lại được.", "Khi app đồng bộ lỗi, hoặc bạn không dùng app nữa."),
    "Cookies": ("careful", "Cookie đăng nhập của app.", "Chỉ khi chấp nhận đăng nhập lại.", "Bị đăng xuất khỏi mọi dịch vụ của app.", "Khi cần đăng xuất sạch hoặc khi đăng nhập bị kẹt."),
    "Network": ("careful", "Cookie và trạng thái mạng của app.", "Chỉ khi chấp nhận đăng nhập lại.", "Bị đăng xuất.", "Khi đăng nhập bị kẹt."),
    "Partitions": ("careful", "Dữ liệu từng phân vùng web của app (đăng nhập, lưu trữ cục bộ).", "Chỉ khi chấp nhận đăng nhập lại.", "Bị đăng xuất, mất cài đặt cục bộ.", "Khi gỡ app hoặc khi đăng nhập bị kẹt."),
    "databases": ("careful", "Cơ sở dữ liệu web cục bộ của app.", "Chỉ khi chấp nhận mất dữ liệu cục bộ.", "Có thể mất dữ liệu chỉ lưu trên máy.", "Khi gỡ app hoặc khi app báo lỗi dữ liệu."),
    "WebStorage": ("careful", "Kho lưu trữ web cục bộ của app.", "Chỉ khi chấp nhận đăng nhập lại.", "Bị đăng xuất, mất cài đặt cục bộ.", "Khi gỡ app hoặc đăng nhập bị kẹt."),
    "vm_bundles": ("careful", "Máy ảo Linux mà Claude Desktop dựng để chạy chế độ Cowork (khoảng 10 GB trở lên).", "Cả thư mục nếu bạn không dùng Cowork.",
                   "Mất lịch sử và gói cài trong Cowork. Mở Cowork lần sau phải tải lại ~10 GB, và có thể phình lại.",
                   "Khi bạn không dùng Cowork nữa, hoặc ổ đĩa đang thiếu chỗ gấp. Thoát Claude trước."),
    "claude-code": ("review", "Các phiên bản Claude Code được Claude Desktop tải về để dùng nhúng.", "Các bản cũ (giữ bản mới nhất).",
                    "Xóa bản đang dùng làm tính năng Code trong Claude Desktop tải lại.", "Sau khi Claude Desktop đã cập nhật lên bản mới."),
    "Claude Extensions": ("careful", "Tiện ích (extension) bạn đã cài cho Claude Desktop.", "Chỉ tiện ích bạn không dùng.",
                          "Mất cấu hình và dữ liệu của tiện ích; phải cài lại.", "Khi bạn không dùng tiện ích đó nữa."),
}
GENERIC_REVIEW_WHEN = "Chỉ khi bạn đã gỡ app, hoặc không dùng nó nữa. Chưa chắc thì cứ để nguyên, hoặc chuyển vào Thùng rác trước và chờ 2–4 tuần."


def electron_advice(name):
    """(risk, advice) cho một thư mục con quen thuộc trong dữ liệu app Electron/Chromium; None nếu chưa nhận diện."""
    e = ELECTRON_DIRS.get(name)
    return (e[0], A(f"Thư mục “{name}”: {e[1]}", e[2], e[3], when=e[4])) if e else None


KNOWN_APPS = [  # (từ khóa trong đường dẫn, tên hiển thị, lời khuyên riêng)
    ("zalo", "Zalo", "Dữ liệu Zalo trên máy gồm tin nhắn, ảnh, video, file đã nhận. Dọn trong Zalo: Cài đặt → mục Dữ liệu/Quản lý dung lượng, xóa file đã tải thay vì xóa thư mục."),
    ("telegram", "Telegram", "Telegram lưu tin trên máy chủ, phần trên máy chủ yếu là cache ảnh/video. Dọn trong Telegram: Cài đặt → Nâng cao → Quản lý bộ nhớ cục bộ."),
    ("keepcoder", "Telegram", "Telegram lưu tin trên máy chủ, phần trên máy chủ yếu là cache ảnh/video. Dọn trong Cài đặt → Dữ liệu và bộ nhớ của Telegram."),
    ("discord", "Discord", "Tin nhắn Discord lưu trên máy chủ; dữ liệu trên máy chủ yếu là cache. Xóa sẽ phải đăng nhập lại."),
    ("slack", "Slack", "Tin nhắn Slack lưu trên máy chủ; xóa sẽ phải đăng nhập lại các workspace."),
    ("google/chrome", "Google Chrome", "Hồ sơ Chrome: lịch sử, cookie, mật khẩu đã lưu, tiện ích. Dọn trong Chrome: Cài đặt → Quyền riêng tư → Xóa dữ liệu duyệt web."),
    ("bravesoftware", "Brave", "Hồ sơ Brave: lịch sử, cookie, mật khẩu, ví. Dọn trong Brave: Cài đặt → Quyền riêng tư → Xóa dữ liệu duyệt web."),
    ("/code/", "VS Code", "Cấu hình và dữ liệu VS Code. Thư mục User/workspaceStorage của project cũ xóa được; giữ User/settings.json."),
    ("cursor", "Cursor", "Cấu hình và dữ liệu Cursor. workspaceStorage của project cũ xóa được."),
    ("jetbrains", "JetBrains", "Cấu hình/cache của các IDE JetBrains. Thư mục của phiên bản IDE cũ (vd PyCharm2024.1) xóa được nếu đã lên bản mới."),
    ("spotify", "Spotify", "Chủ yếu là nhạc tải offline và cache. Dọn trong Spotify: Cài đặt → Bộ nhớ."),
    ("whatsapp", "WhatsApp", "Tin nhắn và file đính kèm WhatsApp. Dọn trong WhatsApp: Cài đặt → Bộ nhớ và dữ liệu."),
    ("messenger", "Messenger", "Dữ liệu Messenger trên máy; tin nhắn vẫn còn trên máy chủ."),
    ("microsoft teams", "Microsoft Teams", "Chủ yếu là cache; tin nhắn lưu trên máy chủ."),
    ("com.microsoft.teams", "Microsoft Teams", "Chủ yếu là cache; tin nhắn lưu trên máy chủ."),
    ("orbstack", "OrbStack", "Ổ đĩa ảo chứa toàn bộ container, image, volume Docker và máy Linux. Không xóa file này; dọn bằng nhóm Docker ở tab Đề xuất hoặc lệnh docker system prune."),
    ("com.docker", "Docker Desktop", "Ổ đĩa ảo Docker Desktop. Không xóa file; dọn bằng docker system prune hoặc Docker Desktop → Troubleshoot."),
    ("adobe", "Adobe", "Dữ liệu/cache của ứng dụng Adobe. Xóa cache media trong Cài đặt của từng app Adobe."),
    ("application support/claude", "Claude", "Dữ liệu Claude Desktop: cache, máy ảo Cowork (vm_bundles, ~10 GB), phiên bản Claude Code nhúng. Dùng tab Công cụ → Dấu vết AI để dọn có chọn lọc. Hội thoại lưu trên tài khoản."),
    ("com.openai.chat", "ChatGPT", "Dữ liệu app ChatGPT trên máy. Hội thoại lưu trên tài khoản OpenAI; xóa sẽ phải đăng nhập lại."),
    ("application support/codex", "Codex", "Dữ liệu app Codex. Transcript phiên làm việc nằm ở ~/.codex/sessions; dùng tab Công cụ → Dấu vết AI để dọn theo tuổi."),
    ("steam", "Steam", "Game đã cài. Gỡ game trong Steam để giải phóng."),
    ("riot", "Riot Games", "Dữ liệu game Riot (Liên Minh, TFT). Gỡ qua Riot Client."),
    ("minecraft", "Minecraft", "Thế giới đã lưu và bản game. Sao lưu thư mục saves trước khi xóa."),
]
APP_CACHE_DIRS = ("Cache", "Code Cache", "GPUCache", "DawnCache", "DawnWebGPUCache", "DawnGraphiteCache",
                  "Service Worker/CacheStorage", "Service Worker/ScriptCache", "CachedData",
                  "CachedExtensionVSIXs", "ShaderCache", "GrShaderCache", "Crashpad/completed", "logs")
PERSONAL_DOC = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".pages", ".numbers", ".key",
                ".psd", ".ai", ".sketch", ".fig", ".epub", ".txt", ".md", ".csv"}
VM_EXT = {".img", ".qcow2", ".vmdk", ".vdi", ".vhd", ".vhdx", ".hdd", ".raw", ".sparseimage", ".sparsebundle", ".utm"}
PKG_SUFFIX = (".photoslibrary", ".musiclibrary", ".tvlibrary", ".photolibrary", ".fcpbundle", ".imovielibrary",
              ".logicx", ".band", ".sparsebundle", ".utm", ".pvm")
_APPS_CACHE = {"t": 0, "names": {}}


def known_app(path):
    low = path.lower()
    for key, name, tip in KNOWN_APPS:
        if key in low:
            return name, tip
    return None, None


def installed_apps():
    if time.time() - _APPS_CACHE["t"] > 120:
        names = {}
        for base in APP_DIRS + ["/System/Applications"]:
            for n in listdir(base):
                if n.endswith(".app"):
                    names[re.sub(r"[^a-z0-9]", "", n[:-4].lower())] = n[:-4]
        _APPS_CACHE.update(t=time.time(), names=names)
    return _APPS_CACHE["names"]


def installed_match(filename):
    m = re.match(r"[A-Za-z]+", filename)
    token = m.group(0).lower() if m else ""
    if len(token) < 3:
        return None
    for norm, disp in installed_apps().items():
        if norm and (norm.startswith(token) or (len(norm) >= 4 and token.startswith(norm))):
            return disp
    return None


def app_folder_name(path):
    for marker in ("/Library/Application Support/", "/Library/Containers/", "/Library/Group Containers/"):
        if marker in path:
            return path.split(marker, 1)[1].split("/", 1)[0]
    return None


def advise_path(path, is_dir, size=None, used=None):
    """Trả (risk, advice) cho một file/thư mục bất kỳ (FR-003)."""
    name = os.path.basename(path)
    low = path.lower()
    ext = os.path.splitext(name)[1].lower()
    lib = LIB + os.sep
    if not deletable(path):
        return "careful", A("Thư mục hệ thống hoặc dữ liệu được Dọn Mac bảo vệ.",
                            "Không xóa trực tiếp trong Dọn Mac.",
                            "Xóa nhầm có thể làm hỏng app, mất mật khẩu (Keychain), khóa SSH hoặc dữ liệu cá nhân.",
                            "Mở vào bên trong để tìm mục con nặng; nhóm Đề xuất đã gom sẵn những phần xóa được.",
                            "Không xóa trong Dọn Mac. Chỉ đụng tới khi bạn hiểu rõ và làm thủ công bằng Finder.")
    if path.startswith(os.path.join(LIB, "Caches") + os.sep):
        return "safe", ADVICE["cache"]
    if "/data/library/caches/" in low or any(f"/{c.lower()}/" in low + "/" for c in APP_CACHE_DIRS if "/" not in c) \
            and "/library/application support/" in low:
        return "safe", ADVICE["appcache"]
    app_name, app_tip = known_app(path)
    if ext in VM_EXT or name.lower() in ("docker.raw", "data.img") or app_name in ("OrbStack", "Docker Desktop"):
        if app_name in ("OrbStack", "Docker Desktop"):
            return "careful", A(f"Ổ đĩa ảo của {app_name}.", "Không nên xóa file này trực tiếp.",
                                "Xóa là mất TOÀN BỘ container, image, volume (database) và máy ảo Linux.", app_tip,
                                "Chỉ khi bạn bỏ hẳn OrbStack/Docker. Còn dùng thì dọn bằng docker prune hoặc nhóm Docker ở tab Đề xuất.")
        return "careful", A("Ổ đĩa/ảnh máy ảo.", "Máy ảo bạn không còn dùng.",
                            "Bên trong là cả một hệ điều hành và dữ liệu của máy ảo đó.",
                            "Xóa máy ảo trong chính app quản lý nó (UTM, Parallels, VMware…).",
                            "Khi máy ảo đó đã bỏ hẳn và bạn đã lấy hết dữ liệu cần giữ ra ngoài.")
    if path.startswith(os.path.join(LIB, "Developer") + os.sep):
        if "deriveddata" in low or "/caches/" in low:
            return "safe", ADVICE["dev_cache"]
        if "devicesupport" in low:
            return "safe", ADVICE["dev_devsupport"]
        if "/archives/" in low:
            return "review", ADVICE["dev_archives"]
        return "review", A("Dữ liệu công cụ lập trình của Apple (Xcode, Simulator).", "Simulator/runtime cũ.",
                           "Simulator chứa app và dữ liệu test của bạn.", "Dùng nhóm Simulator ở tab Đề xuất để dọn an toàn hơn.",
                           "Khi bạn không còn dùng Xcode/Simulator, hoặc khi đã xong dự án dùng chúng.")
    if path.startswith(lib) and app_folder_name(path):
        folder = app_folder_name(path)
        disp = app_name or folder
        sub = path.split("/Library/Application Support/", 1)[1].split("/", 2)[1:2] if "/Library/Application Support/" in path else []
        ea = electron_advice(sub[0]) if sub else None
        if ea:
            return ea
        adv = dict(ADVICE["appdata"]); adv["what"] = f"Dữ liệu của ứng dụng {disp}: tin nhắn, file đã nhận, cài đặt, tài khoản."
        if app_tip:
            adv["tip"] = app_tip
        return "careful", adv
    if "/library/cloudstorage/" in low:
        svc = path.split("/Library/CloudStorage/", 1)[1].split("/", 1)[0] if "/Library/CloudStorage/" in path else "ổ đám mây"
        return "careful", A(f"File trên ổ đám mây ({svc}).", "File bạn không cần trên mọi thiết bị.",
                            "Xóa ở đây là xóa trên đám mây và mọi máy đồng bộ. Dung lượng thường không nằm trên máy này.",
                            "Muốn chỉ giải phóng máy này: chuột phải trong Finder → “Giải phóng dung lượng”/“Free up space”.",
                            "Chỉ khi bạn chắc chắn không cần file đó trên mọi thiết bị. Muốn lấy lại chỗ thì dùng “Giải phóng dung lượng”.")
    if "/library/mobile documents/" in low:
        return "careful", A("File trong iCloud Drive.", "File bạn không cần trên mọi thiết bị.",
                            "Xóa ở đây là xóa trên iCloud và MỌI thiết bị đồng bộ.",
                            "Muốn chỉ giải phóng máy này: chuột phải trong Finder → “Xóa bản tải về”.",
                            "Chỉ khi bạn chắc chắn không cần file đó trên mọi thiết bị. Muốn lấy lại chỗ thì dùng “Xóa bản tải về”.")
    if "/library/mail/" in low or "/library/messages/" in low:
        return "careful", A("Thư/tin nhắn và tệp đính kèm của app Mail/Tin nhắn.", "Tệp đính kèm cũ.",
                            "Xóa thẳng file có thể làm hỏng hộp thư hoặc lịch sử tin nhắn.",
                            "Xóa trong chính app Mail/Tin nhắn (Tin nhắn → Cài đặt → Giữ tin nhắn: 1 năm).",
                            "Khi bạn đã lưu những tệp đính kèm cần thiết ra nơi khác. Luôn xóa trong chính app, đừng xóa thẳng file.")
    if name.endswith(".photoslibrary"):
        return "careful", A("Thư viện app Ảnh (toàn bộ ảnh, video, album).", "Không nên xóa cả thư viện.",
                            "Đây là TOÀN BỘ ảnh của bạn. Xóa là mất hết nếu chưa bật Ảnh iCloud.",
                            "Xóa ảnh/video trong app Ảnh, hoặc bật “Tối ưu hóa dung lượng máy Mac” trong Ảnh → Cài đặt → iCloud.",
                            "Hầu như không bao giờ xóa cả thư viện. Chỉ khi bạn đã chuyển ảnh sang thư viện khác và đã kiểm tra đủ.")
    if name.endswith(PKG_SUFFIX):
        return "careful", A("Thư viện/dự án của một ứng dụng (iMovie, Final Cut, Logic, GarageBand…).",
                            "Dự án đã xuất xong, không cần chỉnh sửa lại.",
                            "Xóa là mất dự án gốc để chỉnh sửa.",
                            "Trong iMovie/Final Cut có thể xóa “tệp kết xuất” để giảm dung lượng mà vẫn giữ dự án.",
                            "Khi dự án đã xuất bản/giao xong và bạn sẽ không chỉnh sửa lại nữa.")
    if "/node_modules" in low:
        return "safe" if not is_dir or name == "node_modules" else "review", ADVICE["node_modules"]
    if "/.git/" in low:
        return "careful", A("Dữ liệu nội bộ của Git (lịch sử commit).", "Không xóa file lẻ trong .git.",
                            "Có thể làm hỏng repo, mất lịch sử chưa push.", "Thu gọn bằng lệnh: git gc --aggressive",
                            "Không bao giờ xóa file lẻ trong .git. Chỉ xóa cả dự án khi đã bỏ hẳn và đã push mọi thứ cần giữ.")
    for d in (".npm", ".gradle", ".m2", ".cargo/registry", ".pub-cache", ".nuget", ".cache/pip", "go/pkg/mod",
              "library/caches/pip"):
        if f"/{d}/" in low:
            return "safe", ADVICE["dev_cache"]
    if "/.cache/" in low:
        return "review", ADVICE["dotcache"]
    old = used and (time.time() - used) > 365 * 86400
    in_dl = path.startswith(os.path.join(HOME, "Downloads") + os.sep)
    age_tip = " File này đã hơn 1 năm không mở." if old else ""
    if not is_dir and ext in INSTALLER_EXT:
        app = installed_match(name)
        if app:
            return "safe", A(f"File cài đặt. Máy đã cài {app}.", "Xóa được: app đã cài xong, file này không còn cần.",
                             "Chỉ giữ nếu bạn cần đúng phiên bản này để cài lại.", "Cần thì tải bản mới từ trang chủ." + age_tip,
                             "Ngay bây giờ: app đã được cài xong.")
        return "review", A("File cài đặt; Dọn Mac không thấy app tương ứng trong Ứng dụng.",
                           "Nếu đã cài vào nơi khác hoặc không định cài nữa.",
                           "Có thể bạn chưa cài app này. Xóa thì phải tải lại.", "Mở file để kiểm tra trước." + age_tip,
                           "Khi bạn xác nhận không còn định cài app đó, hoặc app đã được cài từ nguồn khác (App Store, Homebrew…).")
    if not is_dir and (ext in ARCHIVE_EXT or name.lower().endswith((".tar.gz", ".tar.xz"))):
        stem = re.sub(r"\.(tar\.gz|tar\.xz|tar\.bz2|zip|rar|7z|tar|gz|tgz|bz2|xz)$", "", name, flags=re.I)
        if stem and os.path.isdir(os.path.join(os.path.dirname(path), stem)):
            return "safe", A("File nén, đã có thư mục giải nén cùng tên bên cạnh.", "Xóa được file nén.",
                             "Chỉ giữ nếu cần gửi lại nguyên file nén cho người khác.", "",
                             "Ngay bây giờ nếu bạn đã mở thư mục giải nén và thấy đủ dữ liệu.")
        return "review", dict(ADVICE["archive"], tip=ADVICE["archive"]["tip"] + age_tip,
                              when="Sau khi bạn đã giải nén và kiểm tra đủ dữ liệu bên trong. Chưa mở thử thì đừng xóa: đây có thể là bản duy nhất.")
    if not is_dir and (ext in PV_IMAGE or ext in PV_VIDEO or ext in PV_AUDIO or ext in (".mkv", ".avi")):
        kind = "Ảnh" if ext in PV_IMAGE else "Video" if ext in PV_VIDEO | {".mkv", ".avi"} else "Âm thanh"
        return ("review" if in_dl and old else "careful"), A(
            f"{kind} cá nhân.", "Bản trùng, bản đã có trong app Ảnh/iCloud/Google Photos, hoặc file tải tạm.",
            "Ảnh/video cá nhân không tạo lại được. Chỉ xóa khi chắc đã có bản sao ở nơi khác.",
            "Xem trước ở khung bên phải hoặc nhấn Space để xem toàn màn hình." + age_tip,
            "Khi bạn chắc chắn đã có bản sao ở nơi khác (Ảnh iCloud, ổ ngoài, Google Photos), hoặc là file tải tạm/ảnh chụp màn hình đã dùng xong. "
            "Ảnh/video trong Tải về quá 1 năm là ứng viên tốt.")
    if not is_dir and ext in PERSONAL_DOC:
        return ("review" if in_dl and old else "careful"), A(
            "Tài liệu cá nhân/công việc.", "Bản nháp cũ, bản trùng, tài liệu tải tạm đã dùng xong.",
            "Có thể là bản duy nhất (bài tập, báo cáo, hợp đồng). Xóa nhầm khó lấy lại sau khi dọn Thùng rác.",
            "Xem trước để chắc chắn." + age_tip,
            "Khi tài liệu đã nộp/xong việc và bạn có bản lưu ở nơi khác (email, Drive, USB). Bản duy nhất thì đừng xóa.")
    if is_dir:
        if app_name:
            return "careful", A(f"Thư mục của {app_name}.", "Phần cache/tệp tạm bên trong.",
                                "Có thể chứa dữ liệu chính của app.", app_tip,
                                "Khi bạn đã gỡ app đó, hoặc chỉ xóa phần cache/tệp tạm bên trong.")
        return "review", A("Thư mục của bạn.", "Thư mục project/tải về đã không còn dùng.",
                           "Bên trong có thể có file quan trọng.",
                           "Bấm đúp để mở vào trong và xem từng mục trước khi xóa cả thư mục." + age_tip,
                           "Khi project/thư mục này đã hết dùng và bạn đã mở ra kiểm tra nội dung bên trong.")
    return "review", A("File không rõ mục đích.", "Nếu bạn nhận ra và không cần nữa.",
                       "Dọn Mac không đoán được file này dùng làm gì; có thể là dữ liệu của app hoặc project.",
                       "Mở xem trước, hoặc Hiển thị trong Finder để xem nó nằm cạnh những gì." + age_tip,
                       "Chỉ khi bạn nhận ra file đó và biết chắc không cần nữa. Không nhận ra thì để nguyên.")


def scan_appdata(items, warn):
    """Nhóm mới: cache trong dữ liệu app (an toàn) + dữ liệu app lớn (cẩn thận) — feature 002 US3."""
    fda = has_fda()
    asup = os.path.join(LIB, "Application Support")
    bases = [(asup, n) for n in listdir(asup)]
    if fda:
        for root in ("Containers", "Group Containers"):
            r = os.path.join(LIB, root)
            bases += [(r, n) for n in listdir(r)]
    bases = [(r, n) for r, n in bases if not n.startswith("com.apple.") and not n.startswith("group.com.apple.")
             and n not in ("MobileSync", "CrashReporter", "AddressBook", "CallHistoryDB", "Knowledge", "CloudDocs")
             and os.path.isdir(os.path.join(r, n)) and not os.path.islink(os.path.join(r, n))]
    caches = []
    for r, n in bases:
        p = os.path.join(r, n)
        for c in APP_CACHE_DIRS:
            q = os.path.join(p, c)
            if os.path.isdir(q) and not os.path.islink(q):
                caches.append((n, c, q))
        q = os.path.join(p, "Data/Library/Caches")
        if os.path.isdir(q):
            caches.append((n, "Caches", q))
        # hồ sơ trình duyệt Chromium: <app>/Default/Cache… và <app>/Profile N/Cache…
        for sub in listdir(p):
            if sub == "Default" or sub.startswith("Profile "):
                for c in ("Cache", "Code Cache", "GPUCache", "Service Worker/CacheStorage"):
                    q = os.path.join(p, sub, c)
                    if os.path.isdir(q):
                        caches.append((n, f"{sub}/{c}", q))
    cache_sizes = du_many([q for _, _, q in caches])
    cached_by_app = {}
    for (n, c, q), s in zip(caches, cache_sizes):
        cached_by_app[n] = cached_by_app.get(n, 0) + s
        if s >= CACHE_MIN_BYTES:
            name = known_app(q)[0] or n
            add(items, "appcache", f"{name}: bộ nhớ đệm ({c})", s, path=q, risk="safe", mtime=mtime_of(q),
                note=home_short(q), akey="appcache")
    big = [(r, n) for r, n in bases]
    sizes = du_many([os.path.join(r, n) for r, n in big])
    for (r, n), s in zip(big, sizes):
        if s >= 300 * 1024 ** 2:
            p = os.path.join(r, n)
            risk, adv = advise_path(p, True)
            name = known_app(p)[0] or n
            rest = s - cached_by_app.get(n, 0)
            note = f"Trong đó ~{human(cached_by_app[n])} là cache (đã liệt kê ở nhóm trên)." if cached_by_app.get(n, 0) > CACHE_MIN_BYTES else ""
            add(items, "appdata", f"Dữ liệu {name}", s, path=p, risk="careful", mtime=mtime_of(p),
                note=note, advice=adv)


def home_short(p):
    return "~" + p[len(HOME):] if p.startswith(HOME) else p


def make_entry(path, st=None, size=None, group=None):
    """Tạo/cập nhật Entry cho một đường dẫn; id ổn định theo đường dẫn trong một phiên."""
    try:
        st = st or os.lstat(path)
    except OSError:
        return None
    import stat as _stat
    is_dir = _stat.S_ISDIR(st.st_mode)
    if size is None and not is_dir:
        size = (getattr(st, "st_blocks", 0) * 512) or st.st_size
    eid = PATH2ID.get(path) or uuid.uuid4().hex[:12]
    old = ENTRIES.get(eid, {})
    e = {
        "id": eid, "name": os.path.basename(path) or path, "path": path,
        "kind": old.get("kind") or kind_of(path, is_dir),
        "size": size if size is not None else (DIRSIZE.get(path) if is_dir else None),
        "mtime": st.st_mtime, "is_dir": is_dir,
        # thư mục: atime bị chính lệnh du cập nhật, nên dùng ngày sửa
        "used": old.get("used") or (st.st_mtime if is_dir else st.st_atime),
        "deletable": deletable(path), "preview": preview_kind(path, is_dir, size), "group": group,
        "kept": bool(keep_conflict(path)),
    }
    try:
        e["risk"], e["advice"] = advise_path(path, is_dir, e["size"], e["used"])
    except Exception:
        e["risk"], e["advice"] = "review", None
    ENTRIES[eid] = e
    PATH2ID[path] = eid
    return e


def enrich_mdls(entries):
    """Lấy Loại (đã bản địa hóa) + Lần dùng cuối từ Spotlight theo lô (research R3)."""
    if not entries or not shutil.which("mdls"):
        return
    for i in range(0, len(entries), 200):
        chunk = entries[i:i + 200]
        r = run(["mdls", "-raw", "-name", "kMDItemKind", "-name", "kMDItemLastUsedDate"]
                + [e["path"] for e in chunk], 60)
        if not r or r.returncode != 0:
            continue
        parts = r.stdout.split("\0")
        if len(parts) < 2 * len(chunk):
            continue
        for j, e in enumerate(chunk):
            kind, used = parts[2 * j].strip(), parts[2 * j + 1].strip()
            if kind and kind != "(null)":
                e["kind"] = kind
            if used and used != "(null)":
                try:
                    e["used"] = calendar.timegm(time.strptime(used[:19], "%Y-%m-%d %H:%M:%S"))
                except ValueError:
                    pass
            try:
                e["risk"], e["advice"] = advise_path(e["path"], e["is_dir"], e["size"], e["used"])
            except Exception:
                pass


def forget_path(path):
    """Gỡ một đường dẫn (và mọi thứ bên trong) khỏi mọi danh sách sau khi xóa."""
    pre = path.rstrip(os.sep) + os.sep
    gone = lambda q: q and (q == path or q.startswith(pre))
    with LOCK:
        for k in [k for k, v in ENTRIES.items() if gone(v["path"])]:
            PATH2ID.pop(ENTRIES[k]["path"], None)
            ENTRIES.pop(k, None)
        for name in TABS:
            TABS[name] = [e for e in TABS[name] if not gone(e["path"])]
        for k in [k for k, v in ITEMS.items() if gone(v.get("path"))]:
            ITEMS.pop(k, None)
        STATE["items"] = [x for x in STATE["items"] if not gone(x.get("path"))]
        for q in [q for q in DIRSIZE if gone(q)]:
            DIRSIZE.pop(q, None)
        parent = os.path.dirname(path)
        while parent.startswith(HOME):  # dung lượng thư mục cha không còn đúng
            DIRSIZE.pop(parent, None)
            if parent == HOME:
                break
            parent = os.path.dirname(parent)


def scan_downloads():
    base = os.path.join(HOME, "Downloads")
    now = time.time()
    names = [n for n in listdir(base) if not n.startswith(".")]
    paths = [os.path.join(base, n) for n in names]
    dirs = [p for p in paths if os.path.isdir(p) and not os.path.islink(p)]
    dsz = dict(zip(dirs, du_many(dirs)))
    out = [e for e in (make_entry(p, size=dsz.get(p)) for p in paths) if e]
    enrich_mdls(out)
    for e in out:
        age = (now - (e["used"] or e["mtime"])) / 86400
        e["group"] = "old1y" if age > 365 else "old3m" if age > 90 else "recent"
    out.sort(key=lambda e: -(e["size"] or 0))
    return out


def _dir_size_job(path):
    try:
        size = du(path)
        DIRSIZE[path] = size
        eid = PATH2ID.get(path)
        if eid in ENTRIES:
            ENTRIES[eid]["size"] = size
    finally:
        DIR_PENDING.discard(path)


def in_home(path):
    rp = os.path.realpath(path)
    return rp == HOME or rp.startswith(HOME + os.sep)


def browse(eid):
    if eid:
        e = ENTRIES.get(eid)
        if not e or not e["is_dir"]:
            return None
        path = e["path"]
    else:
        path = HOME
    if not in_home(path) or not os.path.isdir(path):
        return None
    children = []
    it = []
    try:
        with os.scandir(path) as sc:
            for x in sc:
                it.append(x)
    except OSError:
        pass  # lấy được bao nhiêu hiện bấy nhiêu
    for d in it:
        try:
            st = d.stat(follow_symlinks=False)
        except OSError:
            continue
        e = make_entry(d.path, st)
        if not e:
            continue
        cloud = any(seg in d.path for seg in ("/Library/CloudStorage/", "/Library/Mobile Documents/")) \
            or d.path in MEDIA_SKIP
        if e["is_dir"] and not cloud and d.path not in DIRSIZE and d.path not in DIR_PENDING:
            DIR_PENDING.add(d.path)
            SIZE_POOL.submit(_dir_size_job, d.path)
        children.append(e)
    files = [c for c in children if not c["is_dir"]]
    if len(files) <= 400:
        enrich_mdls(files)
    crumbs, cur = [], path
    while True:
        ce = make_entry(cur) if cur != HOME else None
        crumbs.append({"id": ce["id"] if ce else None,
                       "name": "Thư mục nhà" if cur == HOME else os.path.basename(cur)})
        if cur == HOME or not cur.startswith(HOME):
            break
        cur = os.path.dirname(cur)
    crumbs.reverse()
    pending = sum(1 for c in children if c["is_dir"] and c["path"] in DIR_PENDING)
    for c in children:
        if c["is_dir"] and c["path"] in DIRSIZE:
            c["size"] = DIRSIZE[c["path"]]
    return {"dir": {"id": eid, "path": path}, "crumbs": crumbs, "children": children, "pending": pending}


def thumb_for(e, size=1024):
    """Hình thu nhỏ do Quick Look tạo (research R1); None nếu không có."""
    out = os.path.join(THUMB_DIR, f"{e['id']}-{size}.png")
    if os.path.exists(out):
        return out
    if not shutil.which("qlmanage") or not os.path.exists(e["path"]):
        return None
    tmp = tempfile.mkdtemp(dir=THUMB_DIR)
    run(["qlmanage", "-t", "-s", str(size), "-o", tmp, e["path"]], 20)
    made = [os.path.join(tmp, n) for n in listdir(tmp) if n.endswith(".png")]
    if made:
        os.replace(made[0], out)
    shutil.rmtree(tmp, ignore_errors=True)
    return out if os.path.exists(out) else None


def read_text(e, limit=64 * 1024):
    with open(e["path"], "rb") as f:
        data = f.read(limit + 1)
    text = data[:limit].decode("utf-8", errors="replace")
    lines = text.splitlines()
    truncated = len(data) > limit or len(lines) > 200
    return {"text": "\n".join(lines[:200]), "truncated": truncated}


def quicklook(e):
    if not shutil.which("qlmanage") or not os.path.exists(e["path"]):
        return False
    old = QL_PROC[0]
    if old and old.poll() is None:
        old.terminate()
    QL_PROC[0] = subprocess.Popen(["qlmanage", "-p", e["path"]], stdout=subprocess.DEVNULL,
                                  stderr=subprocess.DEVNULL)
    return True


# ------------------------------------------------------------------ các bước quét
def scan_trash(items, warn):
    if not os.path.isdir(TRASH):
        return
    try:
        os.listdir(TRASH)
    except PermissionError:
        warn.append("Chưa đọc được Thùng rác và một phần ~/Library. Hãy bật “Toàn quyền truy cập ổ đĩa” cho "
                    + ("Dọn Mac" if APP_MODE else "Terminal") + ", rồi mở lại tool.")
        return
    add(items, "trash", "Dọn sạch Thùng rác", du(TRASH), path=TRASH, kind="empty_trash", risk="review",
        note="Xóa vĩnh viễn mọi thứ đang nằm trong Thùng rác.")


def scan_system(items, warn):
    r = run(["tmutil", "listlocalsnapshots", "/"], 30)
    if r and r.returncode == 0:
        snaps = [ln for ln in r.stdout.splitlines() if "com.apple" in ln]
        if snaps:
            add(items, "system", f"Snapshot Time Machine cục bộ ({len(snaps)} bản)", None,
                kind="admin_cmd", shell="tmutil deletelocalsnapshots /", risk="review", unknown_ok=True,
                note="macOS không cho biết dung lượng chính xác, thường từ vài đến vài chục GB. "
                     "Bản sao lưu trên ổ Time Machine vẫn giữ nguyên. Cần mật khẩu máy.")


def app_info(path):
    try:
        with open(os.path.join(path, "Contents/Info.plist"), "rb") as f:
            return plistlib.load(f)
    except Exception:
        return {}


def last_used(path):
    r = run(["mdls", "-raw", "-name", "kMDItemLastUsedDate", path], 20)
    s = (r.stdout.strip() if r else "")
    if s and s != "(null)":
        try:
            return calendar.timegm(time.strptime(s[:19], "%Y-%m-%d %H:%M:%S"))
        except ValueError:
            pass
    return None


def app_leftovers(bid, name):
    L = os.path.join(HOME, "Library")
    c = []
    if bid:
        c += [f"{L}/Application Support/{bid}", f"{L}/Caches/{bid}", f"{L}/Preferences/{bid}.plist",
              f"{L}/Containers/{bid}", f"{L}/Saved Application State/{bid}.savedState",
              f"{L}/HTTPStorages/{bid}", f"{L}/WebKit/{bid}", f"{L}/Logs/{bid}"]
    if name and len(name) >= 4:
        c += [f"{L}/Application Support/{name}", f"{L}/Caches/{name}", f"{L}/Logs/{name}"]
    return [p for p in dict.fromkeys(c) if os.path.lexists(p) and p not in PROTECTED]


def scan_apps(items, warn):
    apps = []
    for base in APP_DIRS:
        for n in listdir(base):
            p = os.path.join(base, n)
            if n.endswith(".app") and not os.path.islink(p):
                apps.append(p)

    def one(p):
        info = app_info(p)
        bid = info.get("CFBundleIdentifier", "")
        if bid in SKIP_BUNDLES:
            return None
        name = info.get("CFBundleName") or os.path.basename(p)[:-4]
        extra = app_leftovers(bid, name)
        size = du(p) + sum(du(x) for x in extra)
        return p, bid, extra, size, last_used(p)

    with ThreadPoolExecutor(max_workers=8) as ex:
        res = [r for r in ex.map(one, apps) if r]
    now = time.time()
    for p, bid, extra, size, used in res:
        if size < APP_MIN_BYTES:
            continue
        if used:
            days = (now - used) / 86400
            note = "Mở lần cuối " + time.strftime("%d/%m/%Y", time.localtime(used))
            risk = "safe" if days > 180 else "review"
            if days > 180:
                note += f" (≈{int(days // 30)} tháng trước)"
        else:
            note, risk = "Chưa ghi nhận lần mở nào", "review"
        if extra:
            note += f" · gồm {len(extra)} thư mục dữ liệu đi kèm"
        add(items, "apps", os.path.basename(p)[:-4], size, path=p, kind="app", risk=risk, note=note,
            mtime=used, extra=extra)

    libs = [p for p in SOUND_LIBS if os.path.isdir(p)]
    if libs:
        add(items, "apps", "Thư viện âm thanh GarageBand / Logic", sum(du_many(libs)), kind="admin_cmd",
            shell="rm -rf " + " ".join(shlex.quote(p) for p in libs), risk="review",
            note="Loop và nhạc cụ ảo. Chỉ xóa nếu không dùng GarageBand (Tạo Nhạc). Cần mật khẩu máy, xóa vĩnh viễn.")


def scan_docker(items, warn):
    if not shutil.which("docker"):
        return
    r = run(["docker", "system", "df", "--format", "{{json .}}"], 60)
    if r is None or r.returncode != 0:
        warn.append("Docker/OrbStack chưa chạy nên chưa quét được phần này. Mở OrbStack rồi bấm “Quét lại”.")
        return
    spec = {
        "Images": ("Image không dùng", ["docker", "image", "prune", "-a", "-f"], "review",
                   "Xóa image không có container nào dùng. Lần sau cần pull/build lại."),
        "Containers": ("Container đã dừng", ["docker", "container", "prune", "-f"], "review",
                       "Xóa các container đang ở trạng thái dừng."),
        "Build Cache": ("Build cache", ["docker", "builder", "prune", "-a", "-f"], "safe",
                        "Cache khi build image; lần build sau chậm hơn một chút."),
        "Local Volumes": ("Volume không dùng", ["docker", "volume", "prune", "-a", "-f"], "careful",
                          "Volume chứa dữ liệu (ví dụ database). Chỉ xóa nếu chắc không cần."),
    }
    for line in r.stdout.splitlines():
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if d.get("Type") in spec:
            label, cmd, risk, note = spec[d["Type"]]
            add(items, "docker", label, parse_docker_size(d.get("Reclaimable")), cmd=cmd, kind="cmd",
                risk=risk, note=f"{note} Tổng {d.get('Size', '?')}, {d.get('TotalCount', '?')} mục.")


def scan_dev(items, warn):
    found = [(os.path.join(HOME, rel), label, risk, note) for rel, label, risk, note in DEV_PATHS
             if os.path.isdir(os.path.join(HOME, rel))]
    cache_dir = os.path.join(HOME, ".cache")
    for n in listdir(cache_dir):
        p = os.path.join(cache_dir, n)
        if n != "huggingface" and os.path.isdir(p) and not os.path.islink(p):
            found.append((p, f"~/.cache/{n}", "review", "Cache của công cụ dòng lệnh."))
    for (p, label, risk, note), s in zip(found, du_many([f[0] for f in found])):
        add(items, "dev", label, s, path=p, risk=risk, note=note, mtime=mtime_of(p))

    if shutil.which("brew"):
        r = run(["brew", "--cache"], 30)
        bc = r.stdout.strip() if r else ""
        if bc and os.path.isdir(bc):
            add(items, "dev", "Homebrew: file tải cũ", du(bc), cmd=["brew", "cleanup", "--prune=all", "-s"],
                kind="cmd", risk="safe", note="Chạy “brew cleanup”: xóa bản tải và phiên bản cũ.")


def xcode_ready():
    r = run(["xcode-select", "-p"], 10)
    return bool(r and r.returncode == 0 and ".app/" in r.stdout)


def scan_sims(items, warn):
    devdir = os.path.join(HOME, "Library/Developer/CoreSimulator/Devices")
    if os.path.isdir(devdir) and xcode_ready():
        r = run(["xcrun", "simctl", "list", "devices", "-j"], 60)
        try:
            data = json.loads(r.stdout)["devices"]
            bad = [d["udid"] for devs in data.values() for d in devs if not d.get("isAvailable", True)]
        except Exception:
            bad = []
        if bad:
            add(items, "sims", f"Simulator không còn dùng được ({len(bad)})",
                sum(du_many([os.path.join(devdir, u) for u in bad])),
                cmd=["xcrun", "simctl", "delete", "unavailable"], kind="cmd", risk="safe",
                note="Simulator của các phiên bản iOS đã gỡ.")
        r = run(["xcrun", "simctl", "runtime", "list", "-j"], 60)
        try:
            rts = json.loads(r.stdout)
        except Exception:
            rts = {}
        for rid, info in (rts.items() if isinstance(rts, dict) else []):
            ident = (info.get("runtimeIdentifier") or "").split(".")[-1]
            parts = ident.split("-")
            label = (parts[0] + " " + ".".join(parts[1:])) if len(parts) > 1 else (ident or rid)
            add(items, "sims", f"Runtime {label} (Xcode)", info.get("sizeBytes") or 0,
                cmd=["xcrun", "simctl", "runtime", "delete", rid], kind="cmd", risk="careful",
                note="Runtime simulator; muốn dùng lại phải tải lại trong Xcode.")

    avd = os.path.join(HOME, ".android/avd")
    avds = [os.path.join(avd, n) for n in listdir(avd) if n.endswith(".avd")]
    for p, s in zip(avds, du_many(avds)):
        ini = p[:-4] + ".ini"
        add(items, "sims", f"Máy ảo Android: {os.path.basename(p)[:-4]}", s, path=p, risk="careful",
            note="Máy ảo Android Emulator cùng dữ liệu bên trong.", mtime=mtime_of(p),
            extra=[ini] if os.path.exists(ini) else None)
    si = os.path.join(HOME, "Library/Android/sdk/system-images")
    imgs = [os.path.join(si, a, b) for a in listdir(si) for b in listdir(os.path.join(si, a))
            if os.path.isdir(os.path.join(si, a, b))]
    for p, s in zip(imgs, du_many(imgs)):
        add(items, "sims", f"Android system image: {os.path.relpath(p, si)}", s, path=p, risk="careful",
            note="Tải lại được trong Android Studio → SDK Manager.", mtime=mtime_of(p))


MEDIA_SKIP = {os.path.join(HOME, p) for p in ("Music/Music", "Music/iTunes", "Movies/TV", "Pictures/Photo Booth Library",
                                               # ổ đám mây (OneDrive, Google Drive, Dropbox, iCloud Drive): quét sẽ
                                               # bắt máy tải file về hoặc treo chờ mạng, và xóa ở đây là xóa trên mây
                                               "Library/CloudStorage", "Library/Mobile Documents")}
CLOUD_HINT = ("OneDrive", "Google Drive", "GoogleDrive", "Dropbox", "Box", "iCloud Drive")
ALWAYS_PERMANENT = {"cmd", "admin_cmd", "empty_trash", "clear_dir", "prune_old"}
BIG_SCAN_MIN = 10 * 1024 ** 2   # gom từ 10 MB, giao diện lọc theo ngưỡng người dùng chọn
SCAN_INFO = {"library": False}


# thư mục build của dự án: (file anh em bắt buộc, nhãn loại)
ARTIFACT_RULES = {
    "target": (("Cargo.toml",), "rust_target"),
    "Pods": (("Podfile",), "pods"),
    ".next": (("package.json",), "next"),
    ".nuxt": (("package.json",), "nuxt"),
    ".dart_tool": (("pubspec.yaml",), "dart_tool"),
    "build": (("pubspec.yaml", "build.gradle", "build.gradle.kts"), "build_dir"),
}
ARTIFACT_NOTES = {
    "rust_target": "Thư mục build của Rust. Tạo lại bằng cargo build",
    "pods": "Thư viện CocoaPods. Tạo lại bằng pod install",
    "next": "Cache build của Next.js. Tạo lại khi chạy next dev/build",
    "nuxt": "Cache build của Nuxt. Tạo lại khi chạy",
    "dart_tool": "Cache của Dart/Flutter. Tạo lại bằng flutter pub get",
    "build_dir": "Kết quả build (Flutter/Gradle). Tạo lại khi build",
}


def walk_home(items, step):
    """Một lượt đi qua thư mục người dùng.
    full=True: vùng bình thường (gom file cài đặt, node_modules, venv, file lớn).
    full=False: vùng đã có nhóm riêng (Library, OrbStack, cache ẩn, .git): chỉ gom file lớn cho tab Tệp lớn."""
    home_dev = os.stat(HOME).st_dev
    drop_dirs = (os.path.join(HOME, "Downloads") + os.sep, os.path.join(HOME, "Desktop") + os.sep)
    lib_ok = has_fda()
    SCAN_INFO["library"] = lib_ok
    SCAN_INFO["skipped"] = []
    envs, stack, count, big, pkgs = [], [(HOME, True)], 0, [], []
    while stack:
        d, full = stack.pop()
        try:
            it = os.scandir(d)
        except OSError:
            continue
        with it:
            while True:
                try:
                    e = next(it)
                except StopIteration:
                    break
                except OSError as err:  # thư mục treo/ngắt giữa chừng (ổ mạng, ổ đám mây…): bỏ qua phần còn lại
                    SCAN_INFO.setdefault("skipped", []).append(f"{home_short(d)} ({err.strerror or err})")
                    break
                try:
                    if e.is_symlink():
                        continue
                    if e.is_dir(follow_symlinks=False):
                        if d == HOME and e.name in CLOUD_HINT:
                            continue
                        if (d == HOME and e.name == ".Trash") or e.path in MEDIA_SKIP or e.name.endswith(".app"):
                            continue
                        if e.stat(follow_symlinks=False).st_dev != home_dev:
                            continue
                        if e.name.endswith(PKG_SUFFIX):
                            if lib_ok:
                                pkgs.append(e.path)
                            continue
                        sub_full = full
                        if d == HOME and e.name == "Library":
                            if not lib_ok:
                                continue
                            sub_full = False
                        elif full and ((d == HOME and e.name in WALK_SKIP_TOP) or e.name == ".git"
                                       or e.path in WALK_SKIP_PATHS):
                            sub_full = False
                        if full and e.name == "node_modules":
                            envs.append((e.path, "node_modules"))
                            continue
                        if full and os.path.isfile(os.path.join(e.path, "pyvenv.cfg")):
                            envs.append((e.path, "venv"))
                            continue
                        rule = ARTIFACT_RULES.get(e.name) if full else None
                        if rule and any(os.path.exists(os.path.join(d, sib)) for sib in rule[0]):
                            envs.append((e.path, rule[1]))
                            continue
                        stack.append((e.path, sub_full))
                    elif e.is_file(follow_symlinks=False):
                        count += 1
                        if count % 5000 == 0:
                            step(f"Đang quét thư mục người dùng… {count:,} file".replace(",", "."))
                        st = e.stat(follow_symlinks=False)
                        size = getattr(st, "st_blocks", 0) * 512 or st.st_size
                        if full:
                            ext = os.path.splitext(e.name)[1].lower()
                            in_drop = e.path.startswith(drop_dirs)
                            if size >= MIN_INSTALLER_BYTES and (ext in INSTALLER_EXT or (ext in ARCHIVE_EXT and in_drop)):
                                add(items, "installers", e.name, size, path=e.path,
                                    risk="safe" if ext in INSTALLER_EXT else "review",
                                    note="File cài đặt" if ext in INSTALLER_EXT else "File nén", mtime=st.st_mtime)
                        if size >= BIG_SCAN_MIN:
                            big.append((e.path, st, size))
                except OSError:
                    continue

    step("Đang đọc thông tin tệp lớn…")
    big_entries = [e for e in (make_entry(p, st, sz) for p, st, sz in big) if e]
    for p, sz in zip(pkgs, du_many(pkgs)):
        if sz >= BIG_SCAN_MIN:
            e = make_entry(p, size=sz)
            if e:
                big_entries.append(e)
    enrich_mdls(big_entries)
    big_entries.sort(key=lambda e: -(e["size"] or 0))
    with LOCK:
        TABS["big"] = big_entries

    step("Đang tính dung lượng node_modules và môi trường ảo…")
    for (p, kind), s in zip(envs, du_many([p for p, _ in envs])):
        add(items, "envs", f"{os.path.basename(os.path.dirname(p))}/{os.path.basename(p)}", s, path=p,
            risk="review", mtime=mtime_of(p), akey={"node_modules": "node_modules", "venv": "venv"}.get(kind, "build_artifact"),
            note={"node_modules": "Cài lại bằng npm install", "venv": "Môi trường ảo Python, tạo lại được"}.get(
                kind, ARTIFACT_NOTES.get(kind, "Thư mục build, tạo lại được")))


def scan_caches(items, warn):
    base = os.path.join(HOME, "Library/Caches")
    skip = {"Homebrew", "pip", "Yarn"}
    paths = [os.path.join(base, n) for n in listdir(base) if not n.startswith("com.apple.") and n not in skip]
    paths = [p for p in paths if os.path.isdir(p) and not os.path.islink(p)]
    for p, s in zip(paths, du_many(paths)):
        if s >= CACHE_MIN_BYTES:
            add(items, "caches", os.path.basename(p), s, path=p, risk="safe", mtime=mtime_of(p))


def scan_backups(items, warn):
    base = os.path.join(HOME, "Library/Application Support/MobileSync/Backup")
    paths = [os.path.join(base, n) for n in listdir(base) if os.path.isdir(os.path.join(base, n))]
    for p, s in zip(paths, du_many(paths)):
        name, note = os.path.basename(p), ""
        try:
            with open(os.path.join(p, "Info.plist"), "rb") as f:
                info = plistlib.load(f)
            name = info.get("Device Name") or info.get("Display Name") or name
            if info.get("Last Backup Date"):
                note = "Sao lưu lần cuối " + info["Last Backup Date"].strftime("%d/%m/%Y")
        except Exception:
            pass
        add(items, "backups", name, s, path=p, risk="careful", note=note, mtime=mtime_of(p))


def scan_logs(items, warn):
    p = os.path.join(HOME, "Library/Logs")
    if os.path.isdir(p):
        add(items, "logs", "~/Library/Logs", du(p), path=p, kind="clear_dir", risk="safe",
            note="Xóa nội dung bên trong, giữ lại thư mục.")


def run_scan():
    items, warn = [], []

    def step(msg):
        with LOCK:
            STATE["step"] = msg

    steps = [
        ("Đang kiểm tra Thùng rác…", lambda: scan_trash(items, warn)),
        ("Đang kiểm tra snapshot Time Machine…", lambda: scan_system(items, warn)),
        ("Đang kiểm tra ứng dụng…", lambda: scan_apps(items, warn)),
        ("Đang kiểm tra Docker / OrbStack…", lambda: scan_docker(items, warn)),
        ("Đang kiểm tra công cụ lập trình…", lambda: scan_dev(items, warn)),
        ("Đang kiểm tra simulator & máy ảo…", lambda: scan_sims(items, warn)),
        ("Đang quét thư mục người dùng…", lambda: walk_home(items, step)),
        ("Đang kiểm tra thư mục Tải về…", lambda: TABS.__setitem__("downloads", scan_downloads())),
        ("Đang kiểm tra bộ nhớ đệm…", lambda: scan_caches(items, warn)),
        ("Đang kiểm tra dữ liệu ứng dụng…", lambda: scan_appdata(items, warn)),
        ("Đang kiểm tra bản sao lưu iPhone/iPad…", lambda: scan_backups(items, warn)),
        ("Đang kiểm tra nhật ký…", lambda: scan_logs(items, warn)),
    ]
    for msg, fn in steps:
        step(msg)
        try:
            fn()
        except Exception as e:
            import traceback
            traceback.print_exc(file=sys.stderr)
            warn.append(f"{msg.rstrip('…')}: lỗi {e}")
    if SCAN_INFO.get("skipped"):
        sk = SCAN_INFO["skipped"]
        warn.append(f"Bỏ qua {len(sk)} thư mục không phản hồi kịp: " + "; ".join(sk[:3]) + (" …" if len(sk) > 3 else ""))
    items.sort(key=lambda i: -(i["size"] or 0))
    with LOCK:
        ITEMS.clear()
        ITEMS.update({i["id"]: i for i in items})
        STATE.update(running=False, step="", items=items, warnings=warn, scanned_at=time.time(),
                     need_fda=any("Toàn quyền" in w for w in warn))


def start_scan():
    with LOCK:
        if STATE["running"]:
            return
        STATE.update(running=True, step="Đang bắt đầu…")
    threading.Thread(target=run_scan, daemon=True).start()


# ------------------------------------------------------------------ xóa
def _force(func, path, _exc):
    try:
        os.chmod(os.path.dirname(path), 0o700)
        os.chmod(path, 0o700)
        func(path)
    except Exception:
        pass


def remove_path(p):
    if os.path.islink(p) or not os.path.isdir(p):
        os.unlink(p)
    else:
        shutil.rmtree(p, onerror=_force)
    return not os.path.lexists(p)


def move_to_trash(p):
    """Đổi tên vào ~/.Trash (cùng ổ đĩa, không sao chép)."""
    name = os.path.basename(p.rstrip("/"))
    dest = os.path.join(TRASH, name)
    if os.path.lexists(dest):
        base, ext = os.path.splitext(name)
        stamp = time.strftime("%H.%M.%S")
        dest = os.path.join(TRASH, f"{base} {stamp}{ext}")
        i = 2
        while os.path.lexists(dest):
            dest = os.path.join(TRASH, f"{base} {stamp} {i}{ext}")
            i += 1
    os.makedirs(TRASH, exist_ok=True)
    os.rename(p, dest)


def finder_trash(p):
    r = run(["osascript", "-e", f'tell application "Finder" to delete (POSIX file "{as_str(p)}" as alias)'], 300)
    if r and r.returncode == 0:
        return True, ""
    err = (r.stderr.strip() if r else "hết thời gian chờ")
    if "-128" in err:
        err = "Đã hủy nhập mật khẩu"
    return False, err[-200:]


def run_admin(shell):
    r = run(["osascript", "-e", f'do shell script "{as_str(shell)}" with administrator privileges'], 3600)
    if r and r.returncode == 0:
        return True, ""
    err = (r.stderr.strip() if r else "hết thời gian chờ")
    if "-128" in err:
        err = "Đã hủy nhập mật khẩu"
    return False, err[-300:]


def unsafe_reason(p):
    """Lý do không được xóa (None = an toàn). Nói rõ để người dùng biết vì sao bị bỏ qua."""
    logical = os.path.normpath(p)
    if not logical.startswith(HOME + os.sep):
        return f"nằm ngoài thư mục nhà ({logical})"
    parent = os.path.realpath(os.path.dirname(p))
    full = os.path.join(parent, os.path.basename(p))
    if not full.startswith(HOME + os.sep):
        link = os.path.dirname(p)
        while link.startswith(HOME + os.sep) and not os.path.islink(link):
            link = os.path.dirname(link)
        via = f" qua liên kết {home_short(link)}" if os.path.islink(link) else ""
        return f"thực chất nằm ở {full}{via}, ngoài thư mục nhà, nên Dọn Mac không tự xóa"
    if full in PROTECTED:
        return "là thư mục được bảo vệ"
    return None


def is_safe(p):
    return unsafe_reason(p) is None


def is_safe_app(p):
    parent = os.path.realpath(os.path.dirname(p))
    return parent in [os.path.realpath(d) for d in APP_DIRS] and p.endswith(".app") \
        and app_info(p).get("CFBundleIdentifier") not in SKIP_BUNDLES


def app_running(p):
    r = run(["pgrep", "-f", re.escape(p + "/Contents/MacOS/")], 10)
    return bool(r and r.returncode == 0)


def clear_dir(p):
    errs = 0
    for n in listdir(p):
        try:
            if not remove_path(os.path.join(p, n)):
                errs += 1
        except OSError:
            errs += 1
    return errs


def trash_extras(extra):
    bad = 0
    for x in extra or []:
        if os.path.lexists(x) and is_safe(x):
            try:
                move_to_trash(x)
            except OSError:
                bad += 1
    return bad


def delete_one(it, mode):
    kind = it["kind"]
    if kind == "cmd":
        r = run(it["cmd"], 3600)
        if r and r.returncode == 0:
            out = r.stdout.strip().splitlines()
            return True, out[-1] if out else ""
        return False, ((r.stderr.strip() or r.stdout.strip()) if r else "hết thời gian chờ")[-300:]
    if kind == "admin_cmd":
        return run_admin(it["shell"])
    if kind == "empty_trash":
        errs = clear_dir(TRASH)
        return errs == 0, "" if errs == 0 else f"{errs} mục không xóa được"
    p = it["path"]
    k = keep_conflict(p) or next((keep_conflict(x) for x in it.get("extra") or [] if keep_conflict(x)), None)
    if k:
        return False, "Bỏ qua: nằm trong danh sách “Luôn giữ” (" + home_short(k) + ")"
    if kind == "app":
        if not is_safe_app(p):
            return False, "Không phải ứng dụng hợp lệ, đã bỏ qua"
        if app_running(p):
            return False, "Ứng dụng đang mở, hãy thoát nó rồi thử lại"
        if os.path.lexists(p):
            try:
                move_to_trash(p)
            except OSError:
                ok, msg = finder_trash(p)  # app của root/App Store: Finder sẽ hỏi mật khẩu
                if not ok:
                    return False, msg
        bad = trash_extras(it.get("extra"))
        return True, "Đã chuyển vào Thùng rác" + (f" ({bad} mục dữ liệu không chuyển được)" if bad else "")
    if not is_safe(p):
        return False, "Bỏ qua: " + unsafe_reason(p) + ". Hãy xóa bằng Finder (Hiện trong Finder) hoặc trong app quản lý nó."
    if kind == "prune_old":
        rules = prune_rules()
        if p not in rules:
            return False, "Không phải thư mục được phép dọn theo tuổi"
        days = max(1, min(int(it.get("days") or 30), 3650))
        n, freed = prune_old(p, days, rules[p])
        return True, f"Đã xóa vĩnh viễn {n} file cũ hơn {days} ngày ({human(freed)})"
    if kind == "clear_dir":
        errs = clear_dir(p)
        return errs == 0, "" if errs == 0 else f"{errs} mục không xóa được"
    if not os.path.lexists(p):
        return True, "Đã không còn tồn tại"
    if mode == "permanent":
        ok = remove_path(p)
        for x in it.get("extra") or []:
            if os.path.lexists(x) and is_safe(x):
                remove_path(x)
        return ok, "" if ok else "Chỉ xóa được một phần (thiếu quyền?)"
    move_to_trash(p)
    trash_extras(it.get("extra"))
    return True, "Đã chuyển vào Thùng rác"


def do_delete(ids, mode, src="manual"):
    results, hist = [], []
    blocked = dup_blocked(ids)
    BUSY[0] += 1
    try:
        for i in ids:
            with LOCK:
                it = ITEMS.get(i) or TOOL_ITEMS.get(i)
                ent = ENTRIES.get(i) if not it else None
            if i in blocked:
                nm = (it or ent or {}).get("label") or (ent or {}).get("name") or i
                results.append({"id": i, "ok": False, "msg": "Giữ lại ít nhất một bản trong nhóm file trùng lặp", "label": nm})
                continue
            if ent:
                if not deletable(ent["path"]):
                    why = "Mục nằm trong danh sách “Luôn giữ”" if keep_conflict(ent["path"]) else "Mục được bảo vệ, không xóa"
                    results.append({"id": i, "ok": False, "msg": why, "label": ent["name"]})
                    continue
                it = {"kind": "path", "path": ent["path"], "label": ent["name"], "size": ent["size"]}
            if not it:
                results.append({"id": i, "ok": False, "msg": "Không tìm thấy mục này, hãy quét lại"})
                continue
            try:
                ok, msg = delete_one(it, mode)
            except Exception as e:
                ok, msg = False, str(e)
            if ok:
                with LOCK:
                    ITEMS.pop(i, None)
                    STATE["items"] = [x for x in STATE["items"] if x["id"] != i]
                if it.get("path") and it["kind"] in ("path", "app"):
                    forget_path(it["path"])
                hist.append({"t": int(time.time()), "label": it["label"], "size": it.get("size"),
                             "path": home_short(it["path"]) if it.get("path") else None,
                             "mode": mode if it["kind"] not in ALWAYS_PERMANENT else "permanent",
                             "kind": it["kind"], "src": src})
            results.append({"id": i, "ok": ok, "msg": msg, "label": it["label"], "size": it["size"]})
    finally:
        BUSY[0] -= 1
    log_history(hist)
    prune_tools([r["id"] for r in results if r["ok"]])
    return results


def status():
    d = shutil.disk_usage(HOME)
    with LOCK:
        return {
            "running": STATE["running"], "step": STATE["step"], "items": STATE["items"],
            "warnings": STATE["warnings"], "scanned_at": STATE["scanned_at"], "need_fda": STATE["need_fda"],
            "disk": {"total": d.total, "free": d.free}, "sys": sys_info(), "app_mode": APP_MODE,
            "native": NATIVE, "fda": has_fda(), "library_scanned": SCAN_INFO.get("library", False),
        }


# ------------------------------------------------------------------ 003: cấu hình, danh sách giữ, lịch sử
_KEEP = {"paths": None}
TOOL_ITEMS = {}      # id -> item (kết quả công cụ: gỡ app, mồ côi); không bị run_scan xóa
DUP_GROUPS = {}      # gid -> [entry id]
DUP_KEEP = {}        # gid -> entry id được đề xuất giữ
TOOLS = {n: {"running": False, "step": "", "done": False, "data": None, "error": None, "at": None}
         for n in ("apps", "dupes", "orphans", "similar", "ai")}
LA_LABEL = "local.donmac.auto"


def cfg_path():
    return os.path.join(DATA_DIR, "config.json")


def history_path():
    return os.path.join(DATA_DIR, "history.jsonl")


def load_cfg():
    try:
        with open(cfg_path(), "r", encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        d = {}
    if not isinstance(d, dict):
        d = {}
    if not isinstance(d.get("keep"), list):
        d["keep"] = []
    if not isinstance(d.get("schedule"), dict):
        d["schedule"] = {"enabled": False, "min_mb": 200}
    return d


def save_cfg(d):
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = cfg_path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    os.replace(tmp, cfg_path())
    _KEEP["paths"] = None


def kept_paths():
    if _KEEP["paths"] is None:
        _KEEP["paths"] = [os.path.normpath(p) for p in load_cfg()["keep"] if isinstance(p, str) and p]
    return _KEEP["paths"]


def keep_conflict(path):
    """Trả về đường dẫn trong danh sách giữ mà `path` nằm trong / chứa / trùng; None nếu không vướng."""
    if not path:
        return None
    p = os.path.normpath(path)
    for k in kept_paths():
        if p == k or p.startswith(k + os.sep) or k.startswith(p + os.sep):
            return k
    return None


def refresh_kept_flags():
    """Cập nhật cờ kept/deletable của mọi Entry và gỡ mục bị giữ khỏi danh sách Đề xuất."""
    with LOCK:
        for e in ENTRIES.values():
            e["kept"] = bool(keep_conflict(e["path"]))
            e["deletable"] = deletable(e["path"])
        for k in [k for k, v in ITEMS.items() if v.get("path") and keep_conflict(v["path"])]:
            ITEMS.pop(k, None)
        STATE["items"] = [x for x in STATE["items"] if not (x.get("path") and keep_conflict(x["path"]))]


def keep_set(paths, keep=True):
    """Thêm/bỏ đường dẫn khỏi danh sách giữ. Chỉ nhận đường dẫn trong thư mục nhà."""
    cfg = load_cfg()
    cur = [os.path.normpath(p) for p in cfg["keep"]]
    n = 0
    for p in paths:
        p = os.path.normpath(p)
        if keep:
            if p.startswith(HOME + os.sep) and p not in cur:
                cur.append(p)
                n += 1
        elif p in cur:
            cur.remove(p)
            n += 1
    cfg["keep"] = cur
    save_cfg(cfg)
    refresh_kept_flags()
    return n


def log_history(rows):
    if not rows:
        return
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(history_path(), "a", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    except OSError:
        pass


def read_history(limit=300):
    try:
        with open(history_path(), "r", encoding="utf-8") as f:
            lines = f.readlines()[-limit:]
    except OSError:
        return []
    out = []
    for ln in reversed(lines):
        try:
            out.append(json.loads(ln))
        except ValueError:
            continue
    return out


def clear_history():
    try:
        os.remove(history_path())
    except OSError:
        pass


def item_by_id(i):
    with LOCK:
        return ITEMS.get(i) or TOOL_ITEMS.get(i) or ENTRIES.get(i)


# ------------------------------------------------------------------ 003: công cụ quét theo yêu cầu
def slim(e):
    return {k: e.get(k) for k in ("id", "name", "path", "size", "mtime", "used", "deletable", "kept", "preview", "kind")}


def iter_user_files(step=None, skip_hidden=True):
    """Đi qua file trong thư mục nhà, bỏ Library, thư mục ẩn, gói app, node_modules, đám mây, ổ khác."""
    home_dev = os.stat(HOME).st_dev
    stack, count = [HOME], 0
    while stack:
        d = stack.pop()
        try:
            it = os.scandir(d)
        except OSError:
            continue
        with it:
            while True:
                try:
                    e = next(it)
                except StopIteration:
                    break
                except OSError:
                    break
                try:
                    if e.is_symlink():
                        continue
                    if e.is_dir(follow_symlinks=False):
                        n = e.name
                        if d == HOME and (n in CLOUD_HINT or n in ("Library", ".Trash", "OrbStack", "Applications")):
                            continue
                        if skip_hidden and n.startswith("."):
                            continue
                        if n == "node_modules" or n.endswith(".app") or n.endswith(PKG_SUFFIX) or e.path in MEDIA_SKIP \
                                or e.path in WALK_SKIP_PATHS:
                            continue
                        if e.stat(follow_symlinks=False).st_dev != home_dev:
                            continue
                        stack.append(e.path)
                    elif e.is_file(follow_symlinks=False):
                        count += 1
                        if step and count % 4000 == 0:
                            step(f"Đang đọc danh sách file… {count:,}".replace(",", "."))
                        yield e.path, e.stat(follow_symlinks=False)
                except OSError:
                    continue


# ---- Gỡ app sạch
UNINSTALL_APPLE_OK = {"com.apple.garageband10", "com.apple.iMovieApp", "com.apple.iWork.Keynote",
                      "com.apple.iWork.Numbers", "com.apple.iWork.Pages", "com.apple.dt.Xcode"}


def scan_uninstall(step):
    with LOCK:
        for k in [k for k, v in TOOL_ITEMS.items() if v.get("cat") == "uninstall"]:
            TOOL_ITEMS.pop(k, None)
    apps = []
    for base in APP_DIRS:
        for n in listdir(base):
            p = os.path.join(base, n)
            if n.endswith(".app") and not os.path.islink(p):
                apps.append(p)
    step(f"Đang đo {len(apps)} ứng dụng…")

    def one(p):
        info = app_info(p)
        bid = info.get("CFBundleIdentifier", "")
        if bid in SKIP_BUNDLES or (bid.startswith("com.apple.") and bid not in UNINSTALL_APPLE_OK):
            return None
        name = info.get("CFBundleName") or os.path.basename(p)[:-4]
        extra = app_leftovers(bid, name)
        app_size = du(p)
        left = sum(du(x) for x in extra)
        return p, bid, name, info.get("CFBundleShortVersionString", ""), extra, app_size, left, last_used(p)

    with ThreadPoolExecutor(max_workers=8) as ex:
        res = [r for r in ex.map(one, apps) if r]
    now, items = time.time(), []
    for p, bid, name, ver, extra, app_size, left, used in res:
        days = (now - used) / 86400 if used else None
        risk = "safe" if days is not None and days > 180 else "review"
        if used:
            note = "Mở lần cuối " + time.strftime("%d/%m/%Y", time.localtime(used))
        else:
            note = "Chưa ghi nhận lần mở nào"
        adv = A(f"Ứng dụng {name}" + (f" {ver}" if ver else "") + ", cùng dữ liệu đi kèm trong Library.",
                "Cả ứng dụng và dữ liệu đi kèm (cài đặt, cache) được chuyển vào Thùng rác." if extra
                else "Ứng dụng được chuyển vào Thùng rác.",
                "Mất cài đặt, đăng nhập và dữ liệu cục bộ của app (nếu có). App tải từ App Store hoặc có giấy phép riêng "
                "thì cần mua/đăng nhập lại khi cài lại.",
                "Chưa mở hơn 6 tháng thì thường an toàn." if risk == "safe"
                else "App mới dùng gần đây, hãy chắc chắn bạn không cần nữa. Thoát app trước khi xóa.",
                WHEN["app_old"] if risk == "safe" else WHEN["app_recent"])
        add(items, "uninstall", name, app_size + left, path=p, kind="app", risk=risk, note=note, mtime=used,
            extra=extra, advice=adv)
        it = items[-1]
        it.update(app_size=app_size, left_size=left, bid=bid, version=ver,
                  leftovers=[home_short(x) for x in extra], used=used)
    with LOCK:
        TOOL_ITEMS.update({i["id"]: i for i in items})
    items.sort(key=lambda i: -(i["size"] or 0))
    return {"rows": items}


# ---- File trùng lặp
DUP_MIN = 1024 ** 2
DUP_MAX = 8 * 1024 ** 3


def hash_file(path, limit=None):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        if limit:
            h.update(f.read(limit))
        else:
            while True:
                chunk = f.read(1024 * 1024)
                if not chunk:
                    break
                h.update(chunk)
    return h.digest()


def _safe_hash(path, limit=None):
    try:
        return hash_file(path, limit)
    except OSError:
        return None


def _dup_score(e):
    p = e["path"]
    messy = p.startswith((os.path.join(HOME, "Downloads") + os.sep, os.path.join(HOME, "Desktop") + os.sep))
    return (1 if messy else 0, e["mtime"] or 0, p.count(os.sep))  # ưu tiên: ngoài Tải về/Desktop, cũ nhất, nông nhất


def scan_dupes(step):
    by_size, seen_ino, total = {}, set(), 0
    for path, st in iter_user_files(step):
        if DUP_MIN <= st.st_size <= DUP_MAX:
            key = (st.st_dev, st.st_ino)
            if key in seen_ino:
                continue  # hard link tới cùng dữ liệu: không tiết kiệm được gì
            seen_ino.add(key)
            by_size.setdefault(st.st_size, []).append((path, st))
        total += 1
    cands = [(s, v) for s, v in by_size.items() if len(v) > 1]
    step(f"Đang so sánh nội dung {sum(len(v) for _, v in cands)} file có cùng dung lượng…")
    groups = []
    with ThreadPoolExecutor(max_workers=4) as ex:
        for size, files in cands:
            part = {}
            for (path, st), h in zip(files, ex.map(lambda f: _safe_hash(f[0], 1024 * 1024), files)):
                if h:
                    part.setdefault(h, []).append((path, st))
            for same in part.values():
                if len(same) < 2:
                    continue
                if size <= 1024 * 1024:
                    groups.append((size, same))
                    continue
                full = {}
                for (path, st), h in zip(same, ex.map(lambda f: _safe_hash(f[0]), same)):
                    if h:
                        full.setdefault(h, []).append((path, st))
                groups += [(size, g) for g in full.values() if len(g) > 1]
    groups.sort(key=lambda g: -g[0] * (len(g[1]) - 1))
    with LOCK:
        DUP_GROUPS.clear()
        DUP_KEEP.clear()
    out, wasted, built = [], 0, []
    for size, files in groups[:500]:
        ents = [e for e in (make_entry(p, st, size) for p, st in files) if e]
        if len(ents) >= 2:
            built.append((size, ents))
    enrich_mdls([e for _, ents in built for e in ents])
    for size, ents in built:
        keep = min(ents, key=_dup_score)
        gid = uuid.uuid4().hex[:10]
        with LOCK:
            DUP_GROUPS[gid] = [e["id"] for e in ents]
            DUP_KEEP[gid] = keep["id"]
        wasted += size * (len(ents) - 1)
        out.append({"gid": gid, "size": size, "wasted": size * (len(ents) - 1), "keep": keep["id"],
                    "files": [slim(e) for e in sorted(ents, key=_dup_score)]})
    return {"groups": out, "wasted": wasted, "scanned": total}


def dup_blocked(ids):
    """Id bị chặn vì việc xóa sẽ làm mất mọi bản của một nhóm trùng lặp."""
    idset, blocked = set(ids), set()
    with LOCK:
        groups = {g: list(m) for g, m in DUP_GROUPS.items()}
    for gid, members in groups.items():
        chosen = [m for m in members if m in idset]
        if not chosen:
            continue
        alive = [m for m in members if m in ENTRIES and os.path.lexists(ENTRIES[m]["path"])]
        if len([m for m in alive if m not in idset]) == 0:
            keep = DUP_KEEP.get(gid)
            blocked.add(keep if keep in chosen else chosen[-1])
    return blocked


# ---- Dữ liệu mồ côi
ORPHAN_MIN = 100 * 1024
TLDS = {"com", "org", "net", "io", "app", "me", "co", "de", "fr", "uk", "jp", "cn", "vn", "dev", "ai", "tv", "us", "fm",
        "so", "pro", "ch", "nl", "ru", "it", "es", "se", "no", "dk", "fi", "be", "at", "au", "ca", "kr", "tw", "hk",
        "sg", "in", "br", "info", "xyz", "cc", "ly", "gg", "sh", "to", "is", "pw", "eu", "pl", "cz", "ua"}
ORPHAN_DIRS = (  # (thư mục con của ~/Library, hậu tố cần cắt)
    ("Application Support", ""), ("Caches", ""), ("Containers", ""), ("Group Containers", ""),
    ("Preferences", ".plist"), ("Saved Application State", ".savedState"), ("HTTPStorages", ""),
    ("HTTPStorages", ".binarycookies"), ("WebKit", ""), ("Logs", ""), ("Cookies", ".binarycookies"),
    ("Application Scripts", ""),
)


def bundle_id_of(name):
    """Tách mã gói kiểu com.hang.app từ tên thư mục; None nếu không giống."""
    n = re.sub(r"^[A-Z0-9]{10}\.", "", name)   # tiền tố Team ID của Group Containers
    n = re.sub(r"^group\.", "", n)
    parts = n.split(".")
    if len(parts) < 3 or parts[0].lower() not in TLDS or not all(re.fullmatch(r"[A-Za-z0-9_-]+", x) for x in parts):
        return None
    return n


def installed_bundle_ids():
    ids = set()
    bases = APP_DIRS + ["/System/Applications", "/Applications/Utilities"]
    for base in list(bases):  # thêm một cấp thư mục con, ví dụ /Applications/Adobe/…
        for n in listdir(base):
            p = os.path.join(base, n)
            if os.path.isdir(p) and not n.endswith(".app"):
                bases.append(p)
    for base in bases:
        for n in listdir(base):
            if n.endswith(".app"):
                bid = app_info(os.path.join(base, n)).get("CFBundleIdentifier")
                if bid:
                    ids.add(bid.lower())
    return ids


def orphan_covered(bid, installed):
    b = bid.lower()
    for i in installed:
        if b == i or b.startswith(i + ".") or i.startswith(b + "."):
            return True
    return False


def scan_orphans(step):
    with LOCK:
        for k in [k for k, v in TOOL_ITEMS.items() if v.get("cat") == "orphan"]:
            TOOL_ITEMS.pop(k, None)
    step("Đang đọc danh sách ứng dụng đã cài…")
    installed = installed_bundle_ids()
    found = {}
    for sub, suffix in ORPHAN_DIRS:
        base = os.path.join(LIB, sub)
        for n in listdir(base):
            if suffix and not n.endswith(suffix):
                continue
            core = n[:-len(suffix)] if suffix else n
            bid = bundle_id_of(core)
            if not bid or bid.lower().startswith(("com.apple.", "apple.")) or orphan_covered(bid, installed):
                continue
            p = os.path.join(base, n)
            if p not in PROTECTED and not os.path.islink(p):
                found.setdefault(bid, []).append(p)
    step(f"Đang đo {len(found)} nhóm dữ liệu…")
    flat = [p for ps in found.values() for p in ps]
    sizes = dict(zip(flat, du_many(flat)))
    items = []
    for bid, paths in found.items():
        size = sum(sizes[p] for p in paths)
        if size < ORPHAN_MIN:
            continue
        adv = A(f"Dữ liệu còn sót lại của ứng dụng mang mã {bid}. Không thấy ứng dụng này trong thư mục Ứng dụng.",
                "Xóa được nếu bạn chắc chắn đã gỡ app đó và không định dùng lại.",
                "Có thể app vẫn được cài ở chỗ khác (ổ ngoài, Setapp, bản thử nghiệm) hoặc bạn định cài lại: "
                "xóa sẽ mất cài đặt, tài khoản đăng nhập và dữ liệu cục bộ của nó.",
                "Không nhớ app nào? Cứ chuyển vào Thùng rác trước, vài tuần sau không thấy vấn đề gì thì dọn Thùng rác.",
                "Khi bạn nhớ rõ app đó đã được gỡ từ lâu (hoặc tên mã gói là của app bạn nhận ra là đã bỏ). Không chắc thì chuyển vào Thùng rác và chờ 2–4 tuần.")
        add(items, "orphan", bid, size, path=sorted(paths)[0], kind="path", risk="review", extra=sorted(paths)[1:],
            note=f"{len(paths)} vị trí trong Library", mtime=max((mtime_of(p) or 0) for p in paths) or None, advice=adv)
        items[-1]["locations"] = [home_short(p) for p in sorted(paths)]
    with LOCK:
        TOOL_ITEMS.update({i["id"]: i for i in items})
    items.sort(key=lambda i: -(i["size"] or 0))
    return {"rows": items, "limited": not has_fda(), "installed": len(installed)}


# ---- Ảnh giống nhau
SIM_EXT = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".tif", ".tiff", ".bmp", ".gif", ".webp"}
SIM_MIN = 20 * 1024
SIM_MAX_IMAGES = 4000
SIM_DISTANCE = 5
SIPS = shutil.which("sips")


def bmp_dhash(data):
    """dHash 64-bit từ ảnh BMP 24/32-bit đã thu nhỏ (lấy mẫu 9 cột × 8 hàng). None nếu không đọc được."""
    try:
        if data[:2] != b"BM":
            return None
        off = int.from_bytes(data[10:14], "little")
        w = int.from_bytes(data[18:22], "little", signed=True)
        h = int.from_bytes(data[22:26], "little", signed=True)
        bpp = int.from_bytes(data[28:30], "little")
        if bpp not in (24, 32) or w < 2 or h == 0:
            return None
        top_down, h = h < 0, abs(h)
        bpr, px = ((w * bpp + 31) // 32) * 4, bpp // 8

        def gray(x, y):
            sx, sy = x * (w - 1) // 8, y * (h - 1) // 7
            row = sy if top_down else h - 1 - sy
            o = off + row * bpr + sx * px
            return (299 * data[o + 2] + 587 * data[o + 1] + 114 * data[o]) // 1000

        bits = 0
        for y in range(8):
            for x in range(8):
                bits = (bits << 1) | (1 if gray(x, y) > gray(x + 1, y) else 0)
        return bits
    except (IndexError, ValueError):
        return None


def image_hash(path):
    if not SIPS:
        return None
    tmp = os.path.join(THUMB_DIR, "h_" + uuid.uuid4().hex[:10] + ".bmp")
    try:
        r = run([SIPS, "-z", "9", "9", "-s", "format", "bmp", path, "--out", tmp], 30)
        if not r or r.returncode != 0:
            return None
        with open(tmp, "rb") as f:
            return bmp_dhash(f.read())
    except OSError:
        return None
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


def cluster_hashes(hashes, dist=SIM_DISTANCE):
    """hashes: {key: int64}. Gom các key có khoảng cách Hamming ≤ dist (chia 64 bit thành dist+1 đoạn, bồ câu)."""
    keys = list(hashes)
    parent = {k: k for k in keys}

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    nseg = dist + 1
    cuts = [round(i * 64 / nseg) for i in range(nseg + 1)]
    for s in range(nseg):
        lo, hi = cuts[s], cuts[s + 1]
        mask = (1 << (hi - lo)) - 1
        buckets = {}
        for k in keys:
            buckets.setdefault((hashes[k] >> lo) & mask, []).append(k)
        for b in buckets.values():
            if len(b) < 2 or len(b) > 400:
                continue
            for i in range(len(b)):
                for j in range(i + 1, len(b)):
                    if bin(hashes[b[i]] ^ hashes[b[j]]).count("1") <= dist:
                        parent[find(b[i])] = find(b[j])
    out = {}
    for k in keys:
        out.setdefault(find(k), []).append(k)
    return [v for v in out.values() if len(v) > 1]


def scan_similar(step):
    if not SIPS:
        return {"groups": [], "unavailable": "Máy này không có công cụ sips nên chưa so sánh được ảnh."}
    files = []
    for path, st in iter_user_files(step):
        if os.path.splitext(path)[1].lower() in SIM_EXT and st.st_size >= SIM_MIN:
            files.append((path, st))
    files.sort(key=lambda f: -f[1].st_mtime)
    files = files[:SIM_MAX_IMAGES]
    step(f"Đang tính dấu vân tay của {len(files)} ảnh…")
    hashes, done = {}, 0
    with ThreadPoolExecutor(max_workers=4) as ex:
        for (path, st), h in zip(files, ex.map(lambda f: image_hash(f[0]), files)):
            done += 1
            if done % 100 == 0:
                step(f"Đang tính dấu vân tay ảnh… {done}/{len(files)}")
            if h is not None and 6 <= bin(h).count("1") <= 58:  # bỏ ảnh trơn một màu
                hashes[path] = h
    stat = dict(files)
    out = []
    for g in cluster_hashes(hashes):
        if len(g) > 40:
            continue
        ents = [e for e in (make_entry(p, stat[p]) for p in g) if e]
        if len(ents) < 2:
            continue
        ents.sort(key=lambda e: -(e["size"] or 0))
        out.append({"gid": uuid.uuid4().hex[:10], "size": sum(e["size"] or 0 for e in ents),
                    "files": [slim(e) for e in ents]})
    out.sort(key=lambda g: -g["size"])
    return {"groups": out[:300], "checked": len(hashes)}


# ---- Dấu vết của công cụ AI (Claude, Codex, ChatGPT)
def _p(*parts):
    return os.path.join(HOME, *parts)


# thư mục chỉ được dọn theo tuổi file: {đường dẫn: đuôi file được phép xóa (None = mọi file)}
def prune_rules():
    return {
        _p(".claude/projects"): (".jsonl",),         # chỉ transcript; không đụng memory/*.md
        _p(".claude/file-history"): None,
        _p(".claude/debug"): None,
        _p(".claude/shell-snapshots"): None,
        _p(".claude/image-cache"): None,
        _p(".claude/paste-cache"): None,
        _p(".codex/sessions"): (".jsonl",),
        _p(".codex/archived_sessions"): (".jsonl",),
        _p(".codex/log"): None,
        _p(".codex/generated_images"): None,
        _p(".codex/attachments"): None,
    }


def walk_old(root, days, exts=None):
    """(dung lượng, số file) của file cũ hơn `days` ngày trong root (không đi theo liên kết)."""
    import stat as _st
    cutoff, size, count = time.time() - days * 86400, 0, 0
    for dp, _dn, fn in os.walk(root, followlinks=False):
        for f in fn:
            if exts and not f.lower().endswith(exts):
                continue
            try:
                st = os.lstat(os.path.join(dp, f))
            except OSError:
                continue
            if not _st.S_ISLNK(st.st_mode) and st.st_mtime < cutoff:
                size += getattr(st, "st_blocks", 0) * 512 or st.st_size
                count += 1
    return size, count


def prune_old(root, days, exts=None):
    """Xóa vĩnh viễn file cũ hơn `days` ngày trong root, rồi dọn thư mục rỗng. Trả (số file, byte)."""
    import stat as _st
    cutoff, n, freed = time.time() - days * 86400, 0, 0
    for dp, _dn, fn in os.walk(root, topdown=False, followlinks=False):
        for f in fn:
            if exts and not f.lower().endswith(exts):
                continue
            p = os.path.join(dp, f)
            try:
                st = os.lstat(p)
            except OSError:
                continue
            if _st.S_ISLNK(st.st_mode) or st.st_mtime >= cutoff or keep_conflict(p):
                continue
            try:
                os.unlink(p)
                n += 1
                freed += getattr(st, "st_blocks", 0) * 512 or st.st_size
            except OSError:
                pass
        if dp != root:
            try:
                os.rmdir(dp)
            except OSError:
                pass
    return n, freed


def vkey(name):
    return tuple(int(x) for x in re.findall(r"\d+", name)[:4]) or (0,)


def live_binaries(cmd):
    cands = [shutil.which(cmd), _p(".local/bin", cmd), "/opt/homebrew/bin/" + cmd, "/usr/local/bin/" + cmd]
    return {os.path.realpath(c) for c in cands if c and os.path.exists(c)}


def old_versions(root, live=()):
    """Các bản cài cũ trong root (mỗi mục con là một phiên bản), trừ bản mới nhất và bản đang được dùng."""
    ents = [os.path.join(root, n) for n in listdir(root) if not n.startswith(".")]
    if len(ents) < 2:
        return []
    ents.sort(key=lambda p: vkey(os.path.basename(p)))
    keep = {ents[-1]}
    out = []
    for p in ents:
        rp = os.path.realpath(p)
        if p in keep or any(l == rp or l.startswith(rp + os.sep) for l in live):
            continue
        out.append(p)
    return out


AI_CHROME_CACHE = {"Cache", "Code Cache", "GPUCache", "DawnCache", "Service Worker", "Crashpad", "logs", "Logs", "blob_storage"}
AI_PRECIOUS = {"IndexedDB", "Local Storage", "Session Storage", "databases", "Partitions", "Cookies", "Network", "Local State"}
AI_KEYWORDS = ("claude", "anthropic", "openai", "chatgpt", "codex")


WHEN_VM = ELECTRON_DIRS["vm_bundles"][4]


def scan_ai(step):
    with LOCK:
        for k in [k for k, v in TOOL_ITEMS.items() if v.get("cat") == "ai"]:
            TOOL_ITEMS.pop(k, None)
    items, done = [], set()

    def row(group, label, size, path, kind="path", risk="review", note="", extra=None, advice=None, **kw):
        add(items, "ai", label, size, path=path, kind=kind, risk=risk, note=note, extra=extra, advice=advice,
            mtime=mtime_of(path))
        if items and items[-1]["path"] == path and items[-1]["label"] == label:
            items[-1]["group"] = group
            items[-1].update(kw)
            done.add(path)

    def versions(group, root, what_cmd, label, tool):
        olds = old_versions(root, live_binaries(what_cmd))
        if not olds:
            return
        sizes = du_many(olds)
        row(group, f"{label}: {len(olds)} phiên bản cũ", sum(sizes), olds[0], risk="safe", extra=olds[1:],
            note=f"{home_short(root)} · giữ lại bản mới nhất và bản đang dùng",
            advice=A(f"Mỗi lần {tool} tự cập nhật, các bản chạy cũ vẫn nằm lại trên ổ đĩa (thường vài trăm MB mỗi bản).",
                     "Mọi bản cũ, trừ bản mới nhất và bản đang được lệnh dùng.",
                     f"Phiên {tool} nào còn đang chạy bằng bản cũ có thể lỗi nếu xóa giữa chừng.",
                     f"Thoát các phiên {tool} đang mở trước khi xóa.",
                     f"Sau mỗi vài lần {tool} tự cập nhật, hoặc khi cần chỗ. Làm lúc không có phiên {tool} nào đang chạy."))

    step("Đang kiểm tra Claude Code…")
    versions("Claude Code", _p(".local/share/claude/versions"), "claude", "Claude Code", "Claude Code")
    versions("Claude Desktop", os.path.join(LIB, "Application Support/Claude/claude-code"), "claude",
             "Claude Desktop (Claude Code nhúng)", "Claude")
    rules = prune_rules()

    def pruned(group, rel, days, label, risk, advice, abs_path=None):
        root = abs_path or _p(rel)
        if not os.path.isdir(root):
            return
        size, count = walk_old(root, days, rules.get(root))
        if size > 0:
            row(group, f"{label} cũ hơn {days} ngày ({count} file)", size, root, kind="prune_old", risk=risk,
                note=f"{home_short(root)} · xóa vĩnh viễn, giữ lại file mới hơn {days} ngày", advice=advice, days=days)

    pruned("Claude Code", ".claude/projects", 30, "Transcript phiên làm việc", "review",
           A("Mỗi phiên Claude Code ghi lại toàn bộ hội thoại, lệnh và kết quả công cụ thành file .jsonl; chạy nhiều là phình rất to.",
             "Transcript cũ của các phiên bạn không cần mở lại. Thư mục memory (ghi nhớ của Claude) và CLAUDE.md không bị đụng tới.",
             "Mất khả năng tiếp tục (--resume) và xem lại các phiên cũ đó; đây cũng là bản ghi \"vì sao đổi như thế\".",
             "Giữ 30 ngày gần nhất là mức cân bằng. Cần lâu hơn thì đặt cleanupPeriodDays trong ~/.claude/settings.json.",
             "Khi transcript cũ hơn 30 ngày và bạn không còn định --resume hay tra lại phiên đó. Làm hằng tháng, hoặc ngay khi thư mục vượt vài GB."))
    pruned("Claude Code", ".claude/file-history", 14, "Ảnh chụp file để /rewind", "review",
           A("Trước mỗi lần sửa file, Claude Code lưu một bản sao để có thể hoàn tác (/rewind).",
             "Bản sao của các phiên cũ không cần hoàn tác nữa.",
             "Không còn /rewind được cho các phiên đó. File hiện tại trong dự án của bạn không bị ảnh hưởng.",
             "Có báo cáo file-history phình tới hàng trăm GB, nên đây là chỗ đáng dọn đều đặn.",
             "Khi phiên đó đã xong hơn 2 tuần và bạn không cần /rewind về nó nữa. Nên làm mỗi 2–4 tuần."))
    pruned("Claude Code", ".claude/debug", 7, "Nhật ký gỡ lỗi", "safe",
           A("File log gỡ lỗi của Claude Code.", "Toàn bộ log cũ.", "Mất thông tin để điều tra lỗi cũ.",
             "Chỉ cần khi báo lỗi cho nhà phát triển.",
             "Bất cứ lúc nào, miễn không đang điều tra một lỗi của Claude Code. Làm hằng tuần cũng được."))
    pruned("Claude Code", ".claude/shell-snapshots", 7, "Ảnh chụp môi trường shell", "safe",
           A("Bản chụp môi trường shell mỗi phiên để chạy lệnh nhanh hơn.", "Mọi bản cũ.", "Không có, phiên mới tự tạo lại.", "",
             "Bất cứ lúc nào: phiên mới tự tạo lại. Dọn kèm nhóm log mỗi tuần/tháng."))
    for sub in ("image-cache", "paste-cache"):
        pruned("Claude Code", ".claude/" + sub, 14, "Ảnh/nội dung đã dán vào phiên", "review",
               A("Ảnh hoặc văn bản bạn dán vào Claude Code được lưu lại để gửi kèm.", "Các bản cũ của phiên đã xong.",
                 "Phiên cũ khi mở lại có thể không còn hiện ảnh đã dán.", "Dọn nếu bạn dán nhiều ảnh chụp màn hình.",
                 "Khi phiên đó xong hơn 2 tuần. Nếu bạn dán nhiều ảnh chụp màn hình thì làm mỗi tháng."))
    vm = os.path.join(LIB, "Application Support/Claude/vm_bundles")
    if os.path.isdir(vm):
        row("Claude Desktop", "Máy ảo của Cowork (vm_bundles)", du(vm), vm, risk="careful",
            note=home_short(vm), advice=A(
                "Claude Desktop dựng một máy ảo Linux (khoảng 10 GB trở lên) để chạy chế độ Cowork.",
                "Cả thư mục nếu bạn không dùng Cowork, hoặc muốn lấy lại chỗ tạm thời.",
                "Mất lịch sử/gói cài trong Cowork (sessiondata.img). Mở Cowork lần sau phải tải lại ~10 GB và có thể phình lại.",
                "Thoát Claude trước khi xóa. Nếu chỉ dùng Claude Code (CLI) thì không cần máy ảo này.",
                WHEN_VM))

    step("Đang kiểm tra Codex…")
    versions("Codex", _p(".codex/packages/standalone/releases"), "codex", "Codex", "Codex")
    pruned("Codex", ".codex/sessions", 30, "Transcript phiên làm việc", "review",
           A("Mỗi phiên Codex ghi toàn bộ hội thoại và kết quả công cụ thành file rollout .jsonl.",
             "Transcript cũ của các phiên bạn không cần mở lại.", "Mất khả năng tiếp tục (resume) các phiên cũ đó.",
             "Báo cáo cho thấy thư mục này có thể lên hàng chục GB.",
             "Khi phiên đó cũ hơn 30 ngày và bạn không còn resume lại. Làm hằng tháng, hoặc ngay khi vượt vài GB."))
    pruned("Codex", ".codex/archived_sessions", 30, "Transcript đã lưu trữ", "review",
           A("Phiên Codex đã được lưu trữ (archive).", "Các transcript cũ.", "Không còn mở lại được các phiên đó.", "",
             "Khi bạn chắc chắn không cần đọc lại các phiên đã lưu trữ đó (hơn 30 ngày)."))
    pruned("Codex", ".codex/log", 7, "Nhật ký", "safe", A("Log của Codex CLI.", "Log cũ.", "Mất thông tin điều tra lỗi cũ.", "",
                                    "Bất cứ lúc nào, trừ khi đang điều tra lỗi Codex. Làm hằng tuần."))
    logs = [os.path.join(_p(".codex"), n) for n in listdir(_p(".codex")) if n.startswith("logs") and ".sqlite" in n]
    if logs:
        sz = du_many(logs)
        row("Codex", f"Cơ sở dữ liệu nhật ký ({len(logs)} file)", sum(sz), logs[0], risk="review", extra=logs[1:],
            note=home_short(_p(".codex")), advice=A(
                "Codex ghi nhật ký chi tiết vào các file logs*.sqlite; đã có báo cáo file này phình rất lớn.",
                "Các file nhật ký.", "Mất nhật ký gỡ lỗi. Cần thoát Codex trước khi xóa kẻo nó ghi lại ngay.",
                "Thoát hẳn Codex (cả app và CLI) rồi mới xóa.",
                "Khi file này lên vài trăm MB trở lên. Thoát hẳn Codex rồi mới xóa; làm lúc không đang chạy tác vụ nào."))
    pruned("Codex", ".codex/generated_images", 30, "Ảnh do Codex tạo ra", "review",
           A("Ảnh Codex đã tạo trong các phiên làm việc.", "Ảnh cũ bạn đã lấy dùng hoặc không cần nữa.",
             "Không tạo lại được đúng ảnh đó. Nếu ảnh đã nằm trong dự án của bạn thì bản đó không bị ảnh hưởng.",
             "Xem lại ảnh (tab Ảnh giống/Tệp lớn) trước khi dọn.",
             "Khi bạn đã lấy ảnh cần dùng ra khỏi thư mục này (hoặc ảnh đã nằm trong dự án). Ảnh quá 30 ngày thường là bản nháp."))
    pruned("Codex", ".codex/attachments", 30, "File đính kèm phiên", "review",
           A("File bạn đính kèm vào các phiên Codex.", "Bản đính kèm cũ.", "Phiên cũ có thể không còn hiện file đã đính kèm.", "",
             "Khi phiên đã xong hơn 30 ngày và file gốc vẫn còn ở nơi bạn đã lấy ra."))

    step("Đang kiểm tra ChatGPT và dữ liệu ứng dụng…")
    seen = set()
    for sub in ("Application Support", "Caches", "Containers", "Group Containers", "Logs"):
        base = os.path.join(LIB, sub)
        for n in listdir(base):
            if not any(k in n.lower() for k in AI_KEYWORDS) or n.startswith("com.apple."):
                continue
            top = os.path.join(base, n)
            if not os.path.isdir(top) or os.path.islink(top) or top in done:
                continue
            kids = [os.path.join(top, k) for k in listdir(top)]
            kids = [k for k in kids if os.path.isdir(k) and not os.path.islink(k) and k not in done
                    and not any(d.startswith(k + os.sep) or d == k for d in done)]
            ksz = du_many(kids) if kids else []
            group = "ChatGPT" if any(w in n.lower() for w in ("openai", "chatgpt")) and "codex" not in n.lower() \
                else ("Codex" if "codex" in n.lower() else "Claude Desktop")
            for k, s in zip(kids, ksz):
                if s < 50 * 1024 ** 2 or k in seen:
                    continue
                seen.add(k)
                nm = os.path.basename(k)
                cache = nm in AI_CHROME_CACHE or sub == "Caches"
                precious = nm in AI_PRECIOUS
                ea = electron_advice(nm)
                if ea:
                    risk, adv = ea
                elif cache:
                    risk, adv = "safe", A(f"Thư mục “{nm}” nằm trong vùng bộ nhớ đệm của {n}.", "Toàn bộ: app tự tạo lại khi cần.",
                                          "Chỉ là cache, không mất dữ liệu cá nhân. Lần mở kế tiếp có thể chậm hơn một chút.",
                                          "Thoát app trước khi xóa.", "Khi cần chỗ hoặc khi app chạy chậm/lỗi lạ.")
                elif precious:
                    risk, adv = "careful", A(f"Thư mục “{nm}” trong dữ liệu của {n}: đăng nhập, cài đặt hoặc lưu trữ cục bộ.",
                                             "Chỉ khi chấp nhận đăng nhập lại.",
                                             "Xóa sẽ bị đăng xuất và mất cài đặt cục bộ. Hội thoại lưu trên tài khoản thì không mất.",
                                             "Thoát app trước khi xóa.", ELECTRON_DIRS["Local Storage"][4])
                else:
                    risk, adv = "review", A(
                        f"Thư mục “{nm}” trong dữ liệu của {n} ({human(s)}). Dọn Mac chưa nhận diện tên này nên chưa biết chính xác nó lưu gì.",
                        "Cân nhắc nếu nó phình to bất thường: tên thư mục dạng cache/tmp/log thường dọn được; "
                        "tên dạng data/db/storage/session thường là dữ liệu cục bộ.",
                        "Có thể là dữ liệu cục bộ của app (đăng nhập, bản nháp, lịch sử offline). Xóa có thể phải đăng nhập lại hoặc mất bản nháp chưa đồng bộ.",
                        "Chuyển vào Thùng rác (không xóa vĩnh viễn), mở lại app dùng thử vài ngày; ổn thì dọn Thùng rác. Thoát app trước khi xóa.",
                        GENERIC_REVIEW_WHEN)
                row(group, f"{n}/{nm}", s, k, risk=risk, note=home_short(k), advice=adv)
            if not kids:
                s = du(top)
                if s >= 50 * 1024 ** 2 and top not in seen:
                    seen.add(top)
                    row(group, n, s, top, risk="safe" if sub == "Caches" else "review", note=home_short(top),
                        advice=A(f"Dữ liệu của {n}.", "Cache tự tạo lại." if sub == "Caches" else "Có thể xóa nếu không cần dữ liệu cục bộ.",
                                 "Có thể phải đăng nhập lại.", "Thoát app trước khi xóa.",
                                 GENERIC_REVIEW_WHEN if sub != "Caches" else "Khi cần chỗ hoặc app chạy chậm/lỗi lạ."))
    with LOCK:
        TOOL_ITEMS.update({i["id"]: i for i in items})
    order = {"Claude Code": 0, "Claude Desktop": 1, "Codex": 2, "ChatGPT": 3}
    items.sort(key=lambda i: (order.get(i.get("group"), 9), -(i["size"] or 0)))
    return {"rows": items}


TOOL_FUNCS = {"apps": scan_uninstall, "dupes": scan_dupes, "orphans": scan_orphans, "similar": scan_similar,
              "ai": scan_ai}


def start_tool(name):
    if name not in TOOL_FUNCS:
        return False
    t = TOOLS[name]
    with LOCK:
        if t["running"]:
            return True
        t.update(running=True, step="Đang bắt đầu…", done=False, error=None)

    def step(m):
        with LOCK:
            t["step"] = m

    def job():
        try:
            data = TOOL_FUNCS[name](step)
            with LOCK:
                t.update(data=data, at=time.time())
        except Exception as e:
            import traceback
            traceback.print_exc(file=sys.stderr)
            with LOCK:
                t.update(error=str(e))
        finally:
            with LOCK:
                t.update(running=False, step="", done=True)

    BUSY[0] += 1
    threading.Thread(target=lambda: (job(), BUSY.__setitem__(0, max(0, BUSY[0] - 1))), daemon=True).start()
    return True


def prune_tools(gone_ids):
    """Gỡ các id đã xóa khỏi kết quả của công cụ."""
    gone = set(gone_ids)
    with LOCK:
        for k in gone:
            TOOL_ITEMS.pop(k, None)
        for name in ("apps", "orphans", "ai"):
            d = TOOLS[name]["data"]
            if d:
                d["rows"] = [r for r in d["rows"] if r["id"] not in gone]
        for name in ("dupes", "similar"):
            d = TOOLS[name]["data"]
            if d and d.get("groups"):
                for g in d["groups"]:
                    g["files"] = [f for f in g["files"] if f["id"] not in gone]
                    if name == "dupes":
                        g["wasted"] = g["size"] * max(0, len(g["files"]) - 1)
                d["groups"] = [g for g in d["groups"] if len(g["files"]) > 1]
                if name == "dupes":
                    d["wasted"] = sum(g["wasted"] for g in d["groups"])


# ------------------------------------------------------------------ 003: thông tin máy, bảo mật, khởi động
def sh(cmd, t=10):
    r = run(cmd, t)
    return r.stdout if r and r.returncode == 0 else ""


def machine_info():
    info = {"cores": os.cpu_count()}
    try:
        info["load"] = [round(x, 2) for x in os.getloadavg()]
    except OSError:
        info["load"] = None
    total = sh(["sysctl", "-n", "hw.memsize"]).strip()
    vm = sh(["vm_stat"])
    if total.isdigit() and vm:
        m = re.search(r"page size of (\d+) bytes", vm)
        page = int(m.group(1)) if m else 4096

        def pages(label):
            mm = re.search(label + r":\s+(\d+)\.", vm)
            return int(mm.group(1)) if mm else 0
        avail = (pages("Pages free") + pages("Pages inactive") + pages("Pages speculative")) * page
        info["mem"] = {"total": int(total), "used": max(0, int(total) - avail)}
    m = re.search(r"sec = (\d+)", sh(["sysctl", "-n", "kern.boottime"]))
    info["uptime"] = int(time.time() - int(m.group(1))) if m else None
    batt = sh(["pmset", "-g", "batt"])
    m = re.search(r"(\d+)%;\s*([a-zA-Z ]+)", batt)
    info["battery"] = {"percent": int(m.group(1)), "state": m.group(2).strip()} if m else None
    procs = []
    for ln in sh(["ps", "-Axo", "pid=,pcpu=,rss=,comm=", "-r"]).splitlines()[:8]:
        parts = ln.split(None, 3)
        if len(parts) == 4:
            try:
                procs.append({"pid": int(parts[0]), "cpu": float(parts[1]), "mem": int(parts[2]) * 1024,
                              "name": os.path.basename(parts[3])})
            except ValueError:
                pass
    info["procs"] = procs
    return info


def security_info():
    rows = []

    def row(key, label, out, good, hint):
        low = (out or "").lower()
        state = "unknown" if not low else ("ok" if good(low) else "warn")
        rows.append({"key": key, "label": label, "value": (out or "").strip().splitlines()[0] if out and out.strip()
                     else "Không đọc được", "state": state, "hint": hint})
    row("filevault", "FileVault (mã hóa ổ đĩa)", sh(["fdesetup", "status"]), lambda s: "is on" in s,
        "Bật trong Cài đặt Hệ thống → Quyền riêng tư & Bảo mật → FileVault.")
    row("firewall", "Tường lửa", sh(["/usr/libexec/ApplicationFirewall/socketfilterfw", "--getglobalstate"]),
        lambda s: "enabled" in s, "Bật trong Cài đặt Hệ thống → Mạng → Tường lửa.")
    row("sip", "SIP (bảo vệ toàn vẹn hệ thống)", sh(["csrutil", "status"]), lambda s: "enabled" in s,
        "Chỉ tắt khi bạn cố ý. Bật lại bằng lệnh csrutil enable trong Recovery.")
    row("gatekeeper", "Gatekeeper (chặn app không rõ nguồn)", sh(["spctl", "--status"]), lambda s: "enabled" in s,
        "Bật bằng lệnh sudo spctl --master-enable.")
    ver = None
    for p in ("/Library/Apple/System/Library/CoreServices/XProtect.bundle/Contents/Info.plist",
              "/Library/Apple/System/Library/CoreServices/XProtect.app/Contents/Info.plist"):
        try:
            with open(p, "rb") as f:
                ver = plistlib.load(f).get("CFBundleShortVersionString")
            break
        except Exception:
            continue
    rows.append({"key": "xprotect", "label": "XProtect (chống mã độc tích hợp)",
                 "value": f"Phiên bản {ver}" if ver else "Không đọc được", "state": "ok" if ver else "unknown",
                 "hint": "macOS tự cập nhật. Đây không phải phần mềm diệt virus."})
    return rows


def startup_items():
    out = []
    for d in (os.path.join(HOME, "Library/LaunchAgents"), "/Library/LaunchAgents", "/Library/LaunchDaemons"):
        for n in listdir(d):
            if not n.endswith(".plist") or n.startswith("com.apple."):
                continue
            p = os.path.join(d, n)
            try:
                with open(p, "rb") as f:
                    pl = plistlib.load(f)
            except Exception:
                continue
            prog = pl.get("Program") or (pl.get("ProgramArguments") or [None])[0]
            e = make_entry(p)
            out.append({"id": e["id"] if e else None, "label": pl.get("Label") or n[:-6], "file": n,
                        "where": home_short(d), "program": prog, "run_at_load": bool(pl.get("RunAtLoad")),
                        "broken": bool(prog and isinstance(prog, str) and prog.startswith("/") and not os.path.exists(prog))})
    out.sort(key=lambda x: (not x["broken"], x["label"].lower()))
    return out


# ------------------------------------------------------------------ 003: dọn tự động theo lịch
AUTO_CATS = {"caches", "appcache", "logs", "installers", "dev"}


def auto_candidates(items):
    return [i for i in items if i["cat"] in AUTO_CATS and i["risk"] == "safe" and i["kind"] in ("path", "clear_dir")
            and i.get("path") and not keep_conflict(i["path"])]


def auto_clean(dry_run=False, min_mb=200, out=print):
    with LOCK:
        STATE["running"] = True
    run_scan()
    with LOCK:
        chosen = auto_candidates(STATE["items"])
    total = sum(i["size"] or 0 for i in chosen)
    for i in chosen:
        out(f"  {human(i['size']):>10}  {i['label']}  ({home_short(i['path'])})")
    out(f"Tổng các mục An toàn tự dọn được: {human(total)}")
    if total < min_mb * 1024 ** 2:
        out(f"Chưa đạt ngưỡng {min_mb} MB, không dọn gì.")
        return 0
    if dry_run:
        out("Chế độ xem thử (--dry-run): không xóa gì.")
        return 0
    res = do_delete([i["id"] for i in chosen], "trash", src="auto")
    ok = [r for r in res if r["ok"]]
    out(f"Đã dọn {len(ok)}/{len(res)} mục, ~{human(sum(r.get('size') or 0 for r in ok))}.")
    return 0


def la_path():
    return os.path.join(HOME, "Library/LaunchAgents", LA_LABEL + ".plist")


def schedule_get():
    s = load_cfg()["schedule"]
    return {"enabled": bool(s.get("enabled")), "min_mb": int(s.get("min_mb") or 200), "weekday": int(s.get("weekday", 0)),
            "hour": int(s.get("hour", 10)), "installed": os.path.exists(la_path())}


def schedule_plist(min_mb, weekday, hour):
    script = os.path.join(DATA_DIR, "don_mac.py")
    if not os.path.exists(script):
        script = os.path.realpath(__file__)
    log = os.path.join(HOME, "Library/Logs/DonMac-auto.log")
    return {"Label": LA_LABEL, "ProgramArguments": [sys.executable, script, "--auto-clean", "--min-mb", str(min_mb)],
            "StartCalendarInterval": {"Weekday": weekday, "Hour": hour, "Minute": 17},
            "StandardErrorPath": log, "StandardOutPath": log}


def schedule_set(enabled, min_mb=200, weekday=0, hour=10):
    min_mb = max(10, min(int(min_mb), 100000))
    weekday, hour = int(weekday) % 7, int(hour) % 24
    cfg = load_cfg()
    cfg["schedule"] = {"enabled": bool(enabled), "min_mb": min_mb, "weekday": weekday, "hour": hour}
    save_cfg(cfg)
    if sys.platform == "darwin":
        target = f"gui/{os.getuid()}"
        run(["launchctl", "bootout", f"{target}/{LA_LABEL}"], 20)
        if enabled:
            plist = schedule_plist(min_mb, weekday, hour)
            os.makedirs(os.path.dirname(la_path()), exist_ok=True)
            with open(la_path(), "wb") as f:
                plistlib.dump(plist, f)
            run(["launchctl", "bootstrap", target, la_path()], 20)
        else:
            try:
                os.remove(la_path())
            except OSError:
                pass
    return schedule_get()


# ------------------------------------------------------------------ web
class Handler(BaseHTTPRequestHandler):
    server_version = "DonMac/" + VERSION

    def log_message(self, *args):
        pass

    def _send(self, code, body, ctype):
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False), "application/json; charset=utf-8")

    def _query(self):
        from urllib.parse import parse_qs, urlsplit
        return {k: v[0] for k, v in parse_qs(urlsplit(self.path).query).items()}

    def _send_file(self, fp, ctype):
        try:
            total = os.path.getsize(fp)
            f = open(fp, "rb")
        except OSError:
            return self._json({"error": "not found"}, 404)
        with f:
            start, end, code = 0, total - 1, 200
            m = re.match(r"bytes=(\d*)-(\d*)", self.headers.get("Range", ""))
            if m and total:
                a, b = m.group(1), m.group(2)
                if a:
                    start, end = int(a), (int(b) if b else total - 1)
                elif b:
                    start, end = max(0, total - int(b)), total - 1
                end = min(end, total - 1)
                if start > end:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{total}")
                    self.end_headers()
                    return
                code = 206
            length = max(0, end - start + 1) if total else 0
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(length))
            self.send_header("Cache-Control", "private, max-age=300")
            self.send_header("X-Content-Type-Options", "nosniff")
            if code == 206:
                self.send_header("Content-Range", f"bytes {start}-{end}/{total}")
            self.end_headers()
            f.seek(start)
            left = length
            try:
                while left > 0:
                    chunk = f.read(min(256 * 1024, left))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)
            except (BrokenPipeError, ConnectionResetError):
                pass

    def _authed(self):
        return secrets.compare_digest(self.headers.get("X-Token", ""), TOKEN)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            page = PAGE.replace("__TOKEN__", TOKEN).replace("__VERSION__", VERSION).replace(
                "__CATS__", json.dumps([{"id": c, "title": t, "desc": d} for c, t, d in CATEGORIES], ensure_ascii=False))
            self._send(200, page, "text/html; charset=utf-8")
        elif self.path == "/api/status":
            if not self._authed():
                return self._json({"error": "forbidden"}, 403)
            LAST_PING[0] = time.time()
            self._json(status())
        elif self.path.startswith("/api/tab?"):
            if not self._authed():
                return self._json({"error": "forbidden"}, 403)
            name = self._query().get("name", "")
            if name not in TABS:
                return self._json({"error": "not found"}, 404)
            with LOCK:
                self._json({"running": STATE["running"], "scanned": STATE["scanned_at"] is not None,
                            "entries": TABS[name]})
        elif self.path.startswith("/api/toolres?"):
            if not self._authed():
                return self._json({"error": "forbidden"}, 403)
            name = self._query().get("name", "")
            if name not in TOOLS:
                return self._json({"error": "not found"}, 404)
            with LOCK:
                self._json(dict(TOOLS[name], fda=has_fda()))
        elif self.path == "/api/machine":
            if not self._authed():
                return self._json({"error": "forbidden"}, 403)
            self._json({"machine": machine_info(), "security": security_info(), "startup": startup_items()})
        elif self.path == "/api/settings":
            if not self._authed():
                return self._json({"error": "forbidden"}, 403)
            self._json({"schedule": schedule_get(), "kept": [{"path": p, "short": home_short(p)} for p in kept_paths()],
                        "history": read_history(300), "darwin": sys.platform == "darwin", "version": VERSION})
        elif self.path.startswith("/api/file?") or self.path.startswith("/api/thumb?"):
            q = self._query()
            if not secrets.compare_digest(q.get("t", ""), TOKEN):
                return self._json({"error": "forbidden"}, 403)
            e = ENTRIES.get(q.get("id", ""))
            if not e or e["is_dir"]:
                return self._json({"error": "not found"}, 404)
            if self.path.startswith("/api/thumb?"):
                t = thumb_for(e, 512 if q.get("s") == "512" else 1024)
                if not t:
                    return self._json({"error": "no thumbnail"}, 404)
                return self._send_file(t, "image/png")
            if not os.path.isfile(e["path"]):
                return self._json({"error": "not found"}, 404)
            ext = os.path.splitext(e["path"])[1].lower()
            ctype = {".heic": "image/heic", ".heif": "image/heif", ".m4a": "audio/mp4", ".mov": "video/quicktime",
                     ".flac": "audio/flac", ".webp": "image/webp", ".avif": "image/avif", ".md": "text/plain"}.get(ext) \
                or mimetypes.guess_type(e["path"])[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype in ("image/svg+xml", "text/html", "application/xhtml+xml"):
                ctype = "text/plain; charset=utf-8"  # không để file HTML/SVG chạy script trong app
            self._send_file(e["path"], ctype)
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        path, _, query = self.path.partition("?")
        if path == "/api/bye":  # sendBeacon khi đóng tab: không gửi được header nên dùng query
            if secrets.compare_digest(query, "t=" + TOKEN):
                BYE_AT[0] = time.time()
            return self._json({"ok": True})
        if not self._authed():
            return self._json({"error": "forbidden"}, 403)
        try:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            return self._json({"error": "bad request"}, 400)
        LAST_PING[0] = time.time()
        if path == "/api/ping":
            self._json({"ok": True})
        elif path == "/api/scan":
            start_scan()
            self._json({"ok": True})
        elif path == "/api/delete":
            mode = "permanent" if body.get("mode") == "permanent" else "trash"
            self._json({"results": do_delete(list(body.get("ids", [])), mode)})
        elif path == "/api/reveal":
            it = item_by_id(body.get("id"))
            if it and it.get("path") and os.path.lexists(it["path"]):
                run(["open", "-R", it["path"]], 10)
            self._json({"ok": True})
        elif path == "/api/tool":
            self._json({"ok": start_tool(str(body.get("name", "")))})
        elif path == "/api/keep":
            paths = []
            for i in body.get("ids", []):
                it = item_by_id(i)
                if it and it.get("path"):
                    paths.append(it["path"])
            self._json({"ok": True, "n": keep_set(paths, True)})
        elif path == "/api/unkeep":
            cur = set(kept_paths())
            self._json({"ok": True, "n": keep_set([p for p in body.get("paths", []) if p in cur], False)})
        elif path == "/api/schedule":
            self._json(schedule_set(bool(body.get("enabled")), body.get("min_mb", 200), body.get("weekday", 0),
                                    body.get("hour", 10)))
        elif path == "/api/history_clear":
            clear_history()
            self._json({"ok": True})
        elif path == "/api/browse":
            res = browse(body.get("id"))
            if res is None:
                return self._json({"error": "not found"}, 404)
            self._json(res)
        elif path == "/api/text":
            e = ENTRIES.get(body.get("id"))
            if not e or e["is_dir"] or not os.path.isfile(e["path"]):
                return self._json({"error": "not found"}, 404)
            self._json(read_text(e))
        elif path == "/api/quicklook":
            e = ENTRIES.get(body.get("id"))
            self._json({"ok": bool(e) and quicklook(e)})
        elif path == "/api/open_fda":
            run(["open", "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles"], 10)
            self._json({"ok": True})
        elif path == "/api/reveal_app":
            if bundle_path():
                run(["open", "-R", bundle_path()], 10)
            self._json({"ok": True})
        elif path == "/api/open_orbstack":
            run(["open", "-a", "OrbStack"], 10)
            self._json({"ok": True})
        elif path == "/api/restart":
            run(["osascript", "-e", 'tell application "loginwindow" to «event aevtrrst»'], 30)
            self._json({"ok": True})
        elif path == "/api/quit":
            self._json({"ok": True})
            threading.Thread(target=self.server.shutdown, daemon=True).start()
        else:
            self._json({"error": "not found"}, 404)


def watchdog(server):
    """Ở chế độ app: tự tắt khi tab đóng (hoặc lâu không thấy trình duyệt)."""
    while True:
        time.sleep(2)
        if BUSY[0]:
            continue
        now = time.time()
        closed = BYE_AT[0] and now - BYE_AT[0] > 8 and LAST_PING[0] < BYE_AT[0]
        if closed or now - LAST_PING[0] > 300:
            server.shutdown()
            return


PAGE = r"""<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Dọn Mac</title>
<style>
:root{--bg:#f5f5f7;--card:#fff;--text:#1d1d1f;--muted:#6e6e73;--line:#e5e5ea;--alt:#f7f7f9;--accent:#0a84ff;
--sel:#0a64d6;--seltext:#fff;--danger:#ff3b30;--safe:#1f9d55;--safe-bg:#e3f6ea;--review:#b26a00;--review-bg:#fff2d6;
--careful:#c4271f;--careful-bg:#fde5e3;--seg:#e3e3e8}
@media (prefers-color-scheme:dark){:root{--bg:#1c1c1e;--card:#2c2c2e;--text:#f5f5f7;--muted:#98989d;--line:#3a3a3c;
--alt:#323234;--sel:#0a5fcc;--safe:#4cd47b;--safe-bg:#1d3a28;--review:#ffc15e;--review-bg:#3d3018;--careful:#ff7b72;
--careful-bg:#45201e;--seg:#3a3a3c}}
*{box-sizing:border-box}
html,body{height:100%}
body{margin:0;background:var(--bg);color:var(--text);font:14px/1.45 -apple-system,BlinkMacSystemFont,"SF Pro Text",sans-serif;
display:flex;flex-direction:column;overflow:hidden}
.top{padding:20px 24px 0;max-width:1400px;width:100%;margin:0 auto}
header{display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap}
h1{font-size:24px;margin:0;letter-spacing:-.02em}
h1 small{font-size:12px;color:var(--muted);font-weight:500;margin-left:6px}
.disk{background:var(--card);border-radius:12px;padding:10px 14px;min-width:260px;font-size:13px}
.bar{height:6px;border-radius:3px;background:var(--line);overflow:hidden;margin-top:6px}
.bar>div{height:100%;background:var(--accent)}
.seg{display:flex;background:var(--seg);border-radius:9px;padding:2px;margin:16px 0 14px;width:max-content;max-width:100%;overflow-x:auto}
.seg button{background:none;border-radius:7px;padding:6px 16px;font-weight:500;white-space:nowrap}
.seg button.on{background:var(--accent);color:#fff}
.main{flex:1;min-height:0;max-width:1400px;width:100%;margin:0 auto;padding:0 24px}
.view{height:100%;display:none}.view.on{display:flex;flex-direction:column}
#v-suggest{overflow:auto;padding-bottom:20px}
button{font:inherit;border:0;border-radius:8px;padding:7px 13px;cursor:pointer;background:var(--card);color:var(--text)}
button:hover{filter:brightness(.96)}
button:disabled{opacity:.45;cursor:default;filter:none}
button.primary{background:var(--danger);color:#fff;font-weight:600}
button.link{background:none;color:var(--accent);padding:3px 6px}
button.small{padding:5px 11px;font-size:13px;background:var(--accent);color:#fff;margin-left:8px}
.tools{display:flex;gap:8px;flex-wrap:wrap;margin:0 0 14px}
.warn,.sys{border-radius:12px;padding:10px 14px;margin-bottom:10px}
.warn{background:var(--review-bg);color:var(--review)}
.sys{background:var(--card);color:var(--muted)}.sys.hot{background:var(--review-bg);color:var(--review)}
.progress{background:var(--card);border-radius:14px;padding:22px;text-align:center;color:var(--muted)}
.spin{display:inline-block;width:14px;height:14px;border:2px solid var(--line);border-top-color:var(--accent);
border-radius:50%;animation:s 1s linear infinite;vertical-align:-2px;margin-right:8px}
@keyframes s{to{transform:rotate(360deg)}}
section{background:var(--card);border-radius:14px;margin-bottom:14px;overflow:hidden}
.sh{display:flex;align-items:center;gap:12px;padding:14px 16px;cursor:pointer;user-select:none}
.sh h2{font-size:15px;margin:0}.sh .desc{color:var(--muted);font-size:12.5px}
.sh .total{margin-left:auto;font-weight:600;white-space:nowrap}
.chev{transition:transform .15s;color:var(--muted)}
section.closed .chev{transform:rotate(-90deg)}section.closed .rows{display:none}
.row{display:grid;grid-template-columns:24px 1fr auto auto;gap:12px;align-items:center;padding:10px 16px;border-top:1px solid var(--line)}
.row .name{font-weight:500;word-break:break-word}
.path{color:var(--muted);font-size:12px;word-break:break-all}
.size{font-variant-numeric:tabular-nums;font-weight:600;text-align:right;white-space:nowrap}
.size.unk{color:var(--muted);font-weight:500}
.badge{font-size:11px;font-weight:600;border-radius:6px;padding:2px 7px;white-space:nowrap}
.b-safe{color:var(--safe);background:var(--safe-bg)}.b-review{color:var(--review);background:var(--review-bg)}
.b-careful{color:var(--careful);background:var(--careful-bg)}
input[type=checkbox]{width:16px;height:16px;accent-color:var(--accent);cursor:pointer;margin:0}
button.badge{border:0;cursor:pointer;font:inherit;font-size:11px;font-weight:600;padding:3px 8px}
button.badge:hover{filter:brightness(.95)}
.why{font-size:12px;color:var(--accent);background:none;padding:2px 4px;font-weight:600}
.adv{margin:0 16px 12px 52px;padding:12px 14px;border-radius:10px;background:var(--alt);font-size:13px;border-left:3px solid var(--review)}
.adv.adv-safe{border-left-color:var(--safe)}.adv.adv-careful{border-left-color:var(--careful)}
.adv p{margin:0 0 8px}.adv .g{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:8px}
.adv h4{margin:0 0 3px;font-size:12.5px}.adv .g p{margin:0;color:var(--muted)}
.adv .tip{margin:0;color:var(--text)}
.adv .when{margin:6px 0 0;padding:6px 8px;border-radius:6px;background:rgba(127,127,127,.12)}
.pv .adv{margin:12px 0 0;border-radius:10px}.pv .adv .g{grid-template-columns:1fr}
.pvsec{margin-top:14px;padding-top:12px;border-top:1px solid var(--line)}
.pvsec h4{margin:0 0 6px;font-size:13px;display:flex;gap:8px;align-items:center}
.dot{width:8px;height:8px;border-radius:50%;flex:none;display:inline-block}
.d-safe{background:var(--safe)}.d-review{background:#f5a623}.d-careful{background:var(--careful)}
.tr.sel .dot{box-shadow:0 0 0 1.5px #fff}
.crumbs select{font:inherit;font-size:12.5px;margin-left:10px;padding:2px 4px;border-radius:6px;border:1px solid var(--line);background:var(--card);color:var(--text)}
.crumbs .lnote{color:var(--review);font-size:12px;margin-left:10px}
.legend{display:flex;gap:12px;font-size:12px;color:var(--muted);margin-left:12px}.legend span{display:flex;gap:5px;align-items:center}
@media (max-width:700px){.adv{margin-left:16px}.adv .g{grid-template-columns:1fr}}
.onb{background:var(--card);border-radius:14px;padding:22px 24px}
.onb h2{margin:0 0 8px;font-size:19px}.onb p,.onb li{color:var(--muted)}.onb li{margin:6px 0}.onb b{color:var(--text)}
.onb .btns{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-top:14px}.onb .btns .small{margin-left:0}
.empty{background:var(--card);border-radius:14px;padding:28px;text-align:center;color:var(--muted)}
/* ---- bảng kiểu macOS ---- */
.split{flex:1;min-height:0;display:flex;gap:14px;padding-bottom:14px}
.tablecard{flex:1;min-width:0;background:var(--card);border-radius:12px;display:flex;flex-direction:column;overflow:hidden}
.crumbs{display:flex;flex-wrap:wrap;gap:2px;align-items:center;padding:9px 12px;border-bottom:1px solid var(--line);font-size:13px}
.crumbs button{background:none;padding:2px 6px;border-radius:6px;color:var(--accent)}
.crumbs button:last-child{color:var(--text);font-weight:600}
.crumbs .sep{color:var(--muted)}
.crumbs .stat{margin-left:auto;color:var(--muted);font-size:12px}
.thead,.tr{display:grid;grid-template-columns:30px minmax(160px,1fr) minmax(90px,170px) 128px 92px;align-items:center}
.thead{font-size:12px;font-weight:600;color:var(--muted);border-bottom:1px solid var(--line);user-select:none}
.thead>div{padding:7px 8px;cursor:pointer;white-space:nowrap}.thead>div:first-child{cursor:default}
.thead .r,.tr .r{text-align:right}
.thead .on{color:var(--text)}
.tbody{flex:1;overflow:auto;outline:none}
.tr{font-size:13px;cursor:default;user-select:none}
.tr:nth-child(even){background:var(--alt)}
.tr>div{padding:5px 8px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.tr>div:first-child,.thead>div:first-child{padding:5px 0 5px 10px;overflow:visible;text-overflow:clip}
.tr .nm{display:flex;align-items:center;gap:7px}.tr .nm span{overflow:hidden;text-overflow:ellipsis}
.tr .ic{font-size:15px;width:18px;text-align:center;flex:none}
.tr .go{margin-left:auto;color:var(--muted);flex:none;padding-left:6px}
.tr.sel{background:var(--sel)!important;color:var(--seltext)}.tr.sel .go,.tr.sel .mut{color:var(--seltext)}
.tr.lock{opacity:.62}
.mut{color:var(--muted)}
.grp{padding:12px 10px 5px;font-weight:700;font-size:13px;display:flex;gap:9px;align-items:center;border-bottom:1px solid var(--line)}
.grp .mut{font-weight:500;margin-left:auto}
.more{padding:10px;text-align:center;color:var(--muted);font-size:12px}
.tempty{padding:40px;text-align:center;color:var(--muted)}
/* ---- khung xem trước ---- */
.pv{width:340px;flex:none;background:var(--card);border-radius:12px;display:flex;flex-direction:column;overflow:hidden}
.pv.hide{display:none}
.pvbox{height:300px;flex:none;background:var(--alt);display:flex;align-items:center;justify-content:center;overflow:hidden;position:relative}
.pvbox img{max-width:100%;max-height:100%;object-fit:contain}
.pvbox iframe{width:100%;height:100%;border:0;background:#fff}
.pvbox video{max-width:100%;max-height:100%}
.pvbox audio{width:90%}
.pvbox pre{margin:0;padding:12px;width:100%;height:100%;overflow:auto;font:11.5px/1.45 ui-monospace,Menlo,monospace;white-space:pre-wrap;word-break:break-word;align-self:stretch}
.pvbox .big{font-size:72px}
.pvbox .note{position:absolute;bottom:8px;left:0;right:0;text-align:center;font-size:12px;color:var(--muted)}
.pvinfo{padding:14px 16px;overflow:auto;flex:1}
.pvinfo h3{margin:0 0 4px;font-size:15px;word-break:break-word}
.pvinfo .k{color:var(--muted)}
.pvinfo dl{display:grid;grid-template-columns:auto 1fr;gap:4px 12px;margin:12px 0;font-size:12.5px}
.pvinfo dt{color:var(--muted)}.pvinfo dd{margin:0;word-break:break-all}
.pvbtns{display:flex;gap:8px;flex-wrap:wrap}
.pvbtns button{background:var(--seg)}
/* ---- thanh dưới ---- */
.foot{background:color-mix(in srgb,var(--card) 92%,transparent);backdrop-filter:blur(14px);border-top:1px solid var(--line)}
.foot .in{max-width:1400px;margin:0 auto;padding:10px 24px;display:flex;gap:14px;align-items:center;flex-wrap:wrap}
.sel{font-weight:600}
.mode{display:flex;gap:14px;color:var(--muted);font-size:13px}.mode label{cursor:pointer}
.foot .right{margin-left:auto;display:flex;gap:8px}
.foot .right button:not(.primary){background:var(--seg)}
.toast{position:fixed;top:16px;left:50%;transform:translateX(-50%);background:var(--text);color:var(--bg);
padding:12px 18px;border-radius:12px;max-width:min(640px,92vw);box-shadow:0 8px 30px rgba(0,0,0,.25);display:none;z-index:9}
@media (max-width:860px){.split{flex-direction:column}.pv{width:auto;flex:none;max-height:45%}.pvbox{height:180px}
.thead,.tr{grid-template-columns:30px 1fr 110px 80px}.thead .c-kind,.tr .c-kind{display:none}}
@media (max-width:600px){.row{grid-template-columns:24px 1fr auto}.row .badge{display:none}.thead,.tr{grid-template-columns:30px 1fr 80px}.thead .c-used,.tr .c-used{display:none}}
/* ---- 003: công cụ + máy & cài đặt ---- */
.subseg{display:flex;gap:6px;flex-wrap:wrap;margin:0 0 14px}
.subseg button{background:var(--card);border-radius:18px;padding:5px 14px;font-weight:500}
.subseg button.on{background:var(--accent);color:#fff}
#v-tools,#v-machine{overflow:auto;padding-bottom:24px}
.tinfo{margin-bottom:12px}.tinfo h2{margin:0 0 3px;font-size:17px}.tinfo p{margin:0;color:var(--muted)}
.tbar{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:0 0 12px;background:var(--card);border-radius:12px;padding:10px 12px}
.tbar .sum{font-weight:600;margin:0 6px}.tbar .grow{margin-left:auto;display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.tbar label{color:var(--muted);font-size:13px;cursor:pointer}
.th{width:34px;height:34px;object-fit:cover;border-radius:6px;vertical-align:middle;margin-right:8px;background:var(--alt)}
.row.two{grid-template-columns:24px 1fr auto auto}
.badge.keep{color:var(--safe);background:var(--safe-bg)}
.sgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:10px;padding:12px 16px 16px}
.scard{display:block;background:var(--alt);border-radius:10px;padding:8px;cursor:pointer;position:relative;font-size:12px}
.scard img{width:100%;height:110px;object-fit:cover;border-radius:6px;display:block;background:var(--line);margin-bottom:6px}
.scard input{position:absolute;top:14px;left:14px}
.scard .mut{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.card{background:var(--card);border-radius:14px;padding:14px 16px;margin-bottom:14px}
.card h2{margin:0 0 8px;font-size:15px}.card p.k{color:var(--muted);margin:0 0 8px;font-size:12.5px}
.kv{display:grid;grid-template-columns:auto 1fr;gap:5px 14px;font-size:13px}.kv dt{color:var(--muted)}.kv dd{margin:0}
.mini{width:100%;border-collapse:collapse;font-size:12.5px}.mini td,.mini th{padding:5px 6px;text-align:left;border-top:1px solid var(--line)}
.mini th{color:var(--muted);font-weight:600;border-top:0}.mini .r{text-align:right}
.secrow{display:grid;grid-template-columns:12px 230px 1fr;gap:10px;align-items:start;padding:7px 0;border-top:1px solid var(--line);font-size:13px}
.secrow:first-of-type{border-top:0}.secrow .hint{color:var(--muted);font-size:12px;grid-column:3}
.sched{display:flex;gap:10px;flex-wrap:wrap;align-items:center}.sched select,.sched input[type=number]{font:inherit;padding:3px 6px;border-radius:6px;border:1px solid var(--line);background:var(--card);color:var(--text)}
.sched input[type=number]{width:80px}
.bar.mem{height:8px}
</style>
</head>
<body>
<div class="top">
  <header>
    <div><h1>Dọn Mac<small>v__VERSION__</small></h1></div>
    <div class="disk" id="disk">…</div>
  </header>
  <div class="seg" id="tabs">
    <button data-tab="suggest" class="on">Đề xuất</button>
    <button data-tab="big">Tệp lớn</button>
    <button data-tab="downloads">Bản tải về</button>
    <button data-tab="browse">Trình duyệt tệp</button>
    <button data-tab="tools">Công cụ</button>
    <button data-tab="machine">Máy &amp; cài đặt</button>
  </div>
</div>
<div class="main">
  <div class="view on" id="v-suggest">
    <div class="tools">
      <button id="rescan">↻ Quét lại</button>
      <button id="pickSafe">Chọn tất cả mục “An toàn”</button>
      <button id="clear">Bỏ chọn</button>
      <button id="quit" style="margin-left:auto">Thoát</button>
    </div>
    <div id="sys"></div>
    <div id="warns"></div>
    <div id="list"></div>
  </div>
  <div class="view" id="v-tools">
    <div class="subseg" id="tsub">
      <button data-tool="apps" class="on">Gỡ app</button>
      <button data-tool="dupes">Trùng lặp</button>
      <button data-tool="orphans">Dữ liệu mồ côi</button>
      <button data-tool="similar">Ảnh giống</button>
      <button data-tool="ai">Dấu vết AI</button>
    </div>
    <div id="tool-body"></div>
  </div>
  <div class="view" id="v-machine">
    <div id="m-sched"></div><div id="m-keep"></div><div id="m-hist"></div>
    <div id="m-machine"></div><div id="m-sec"></div><div id="m-start"></div>
  </div>
  <div class="view" id="v-table">
    <div class="split">
      <div class="tablecard">
        <div class="crumbs" id="crumbs"></div>
        <div class="thead" id="thead"></div>
        <div class="tbody" id="tbody" tabindex="0"></div>
      </div>
      <div class="pv" id="pv"></div>
    </div>
  </div>
</div>
<div class="foot"><div class="in">
  <div class="sel" id="sel">Chưa chọn mục nào</div>
  <div class="mode">
    <label><input type="radio" name="mode" value="trash" checked> Chuyển vào Thùng rác</label>
    <label><input type="radio" name="mode" value="permanent"> Xóa vĩnh viễn</label>
  </div>
  <div class="right">
    <button id="tglPv" title="Ẩn/hiện khung xem trước">◧ Xem trước</button>
    <button id="keepBtn" disabled title="Không đề xuất và không cho xóa các mục này nữa">🔒 Luôn giữ</button>
    <button id="reveal" disabled>Hiển thị trong Finder</button>
    <button class="primary" id="go" disabled>Xóa…</button>
  </div>
</div></div>
<div class="toast" id="toast"></div>
<script>
const TOKEN="__TOKEN__", CATS=__CATS__;
const RISK={safe:["An toàn","b-safe"],review:["Xem lại","b-review"],careful:["Cẩn thận","b-careful"]};
const ALWAYS_PERM=new Set(["cmd","admin_cmd","empty_trash","clear_dir"]);
const ICON={dir:"📁",image:"🖼️",pdf:"📕",video:"🎬",audio:"🎵",text:"📝",thumb:"📄",none:"📄"};
const ICON_EXT={dmg:"💿",iso:"💿",pkg:"📦",zip:"🗜️",rar:"🗜️","7z":"🗜️",gz:"🗜️",tar:"🗜️",app:"🧩",docx:"📘",doc:"📘",xlsx:"📗",xls:"📗",pptx:"📙",ppt:"📙"};
const GROUPS=[["old1y","Cũ hơn 1 năm"],["old3m","Cũ hơn 3 tháng"],["recent","Gần đây"]];
const MAX_ROWS=3000;
let tab="suggest", items=[], selected=new Set(), closed=new Set(), openWhy=new Set(), busy=false, dead=false, native=false, scanning=false, fda=true, libScanned=true;
let thr=50e6;try{thr=+localStorage.getItem("donmac.thr")||50e6}catch(e){}
function adviceHTML(a,risk){
  if(!a)return "";
  return `<div class="adv adv-${risk||"review"}">${a.what?`<p><b>Đây là gì:</b> ${esc(a.what)}</p>`:""}
    <div class="g"><div><h4>✅ Xóa được</h4><p>${esc(a.ok)}</p></div><div><h4>⚠️ Vì sao nên cân nhắc</h4><p>${esc(a.keep)}</p></div></div>
    ${a.when?`<p class="when"><b>🕒 Nên xóa khi nào:</b> ${esc(a.when)}</p>`:""}
    ${a.tip?`<p class="tip">💡 ${esc(a.tip)}</p>`:""}</div>`;
}
const T={big:{list:[],sort:["size",-1],sel:new Set(),anchor:null,loaded:false},
  downloads:{list:[],sort:["size",-1],sel:new Set(),anchor:null,loaded:false},
  browse:{list:[],sort:["size",-1],sel:new Set(),anchor:null,loaded:false,dir:null,crumbs:[],pending:0}};
let pvOn=true;try{pvOn=localStorage.getItem("donmac.pv")!=="0"}catch(e){}
const $=id=>document.getElementById(id);
const host=m=>{try{window.webkit.messageHandlers.donmac.postMessage(m);return true}catch(e){return false}};
const esc=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
function human(n){if(n==null)return "Không rõ";const u=["B","KB","MB","GB","TB"];let i=0;n=+n;while(n>=1000&&i<4){n/=1000;i++}
  return (i<2?Math.round(n):n.toFixed(n>=100?0:(n>=10?1:2))).toString().replace(".",",")+" "+u[i]}
const home=p=>p?p.replace(/^\/Users\/[^/]+/,"~"):"";
const date=t=>t?new Date(t*1000).toLocaleDateString("vi-VN"):"";
function macDate(t){if(!t)return "—";const d=new Date(t*1000),p=n=>String(n).padStart(2,"0");
  return `${p(d.getHours())}:${p(d.getMinutes())} ${d.getDate()}/${d.getMonth()+1}/${String(d.getFullYear()).slice(2)}`}
const fileURL=(e,kind="file")=>`/api/${kind}?id=${e.id}&t=${encodeURIComponent(TOKEN)}`;
function icon(e){if(e.is_dir&&!e.name.endsWith(".app"))return ICON.dir;const x=(e.name.split(".").pop()||"").toLowerCase();return ICON_EXT[x]||ICON[e.preview]||"📄"}
function goneScreen(){dead=true;document.body.innerHTML='<div class="top"><h1>Dọn Mac đã tắt</h1><p class="mut">Mở lại app Dọn Mac để dùng tiếp.</p></div>'}
async function api(path,body){
  if(dead)return {};
  try{const r=await fetch(path,{method:body===undefined?"GET":"POST",
    headers:{"X-Token":TOKEN,"Content-Type":"application/json"},body:body===undefined?undefined:JSON.stringify(body)});
    return await r.json();}catch(e){goneScreen();throw e}
}
function toast(html,ms=6000){const t=$("toast");t.innerHTML=html;t.style.display="block";
  clearTimeout(t._h);t._h=setTimeout(()=>t.style.display="none",ms)}

/* ================= Tab Đề xuất (giữ từ v3) ================= */
function renderDisk(d){if(!d)return;const used=d.total-d.free;
  $("disk").innerHTML=`<b>${human(d.free)}</b> còn trống / ${human(d.total)}<div class="bar"><div style="width:${(used/d.total*100).toFixed(1)}%"></div></div>`}
function renderSys(s){
  if(!s||s.uptime_days==null){$("sys").innerHTML="";return}
  const d=s.uptime_days, sw=s.swap_gb||0, hot=d>=3||sw>=2;
  const up=d<1?`${Math.max(1,Math.round(d*24))} giờ`:`${Math.floor(d)} ngày`;
  $("sys").innerHTML=`<div class="sys ${hot?"hot":""}">${hot?"⚠️ ":""}Máy đã chạy liên tục <b>${up}</b> · swap đang dùng <b>${sw.toFixed(1).replace(".",",")} GB</b>.
    ${hot?"Khởi động lại thường giải phóng nhiều GB “Dữ liệu hệ thống”.<button class='small' id='restart'>Khởi động lại…</button>":""}</div>`;
}
function renderOnboard(){
  $("list").innerHTML=`<div class="onb"><h2>🔐 Cấp quyền một lần là xong</h2>
  <p>macOS không cho app nào tự cấp quyền cho chính nó. Bạn chỉ cần bật <b>Toàn quyền truy cập ổ đĩa</b> cho Dọn Mac <b>một lần</b>. Từ đó app quét được mọi thư mục mà không hỏi lại nữa.</p>
  <ol><li>Bấm <b>Mở Cài đặt</b>.</li>
  <li>Bấm nút <b>+</b> ở cuối danh sách, chọn <b>Dọn Mac</b> trong thư mục Ứng dụng, rồi bật công tắc. Cách khác: bấm <b>Hiện Dọn Mac trong Finder</b> rồi kéo icon vào danh sách.</li>
  <li>Khi macOS hỏi <b>Thoát &amp; mở lại</b>, bấm đồng ý (hoặc bấm <b>Mở lại Dọn Mac</b>).</li></ol>
  <div class="btns"><button class="small" data-act="open_fda">Mở Cài đặt</button>
  <button class="small" data-act="reveal_app">Hiện Dọn Mac trong Finder</button>
  <button class="small" id="relaunch">Mở lại Dọn Mac</button>
  <button class="link" id="skip">Bỏ qua, quét luôn (macOS sẽ hỏi từng thư mục)</button></div></div>`;
}
function renderSuggest(){
  const list=$("list");
  if(!items.length){list.innerHTML='<div class="empty">Không còn gì đáng kể để dọn 🎉</div>';renderFoot();return}
  let html="";
  for(const c of CATS){
    const rows=items.filter(i=>i.cat===c.id); if(!rows.length)continue;
    const total=rows.reduce((a,b)=>a+(b.size||0),0), all=rows.every(r=>selected.has(r.id));
    html+=`<section class="${closed.has(c.id)?"closed":""}">
      <div class="sh" data-toggle="${c.id}">
        <input type="checkbox" data-catbox="${c.id}" ${all?"checked":""} title="Chọn cả nhóm">
        <div><h2>${esc(c.title)} <span class="chev">▾</span></h2><div class="desc">${esc(c.desc)}</div></div>
        <div class="total">${total?human(total):""}</div></div><div class="rows">`;
    for(const r of rows){
      const [rl,rc]=RISK[r.risk]||RISK.review;
      const showPath=r.path&&r.kind!=="empty_trash";
      const meta=[r.note, showPath?home(r.path):"", r.mtime&&r.kind!=="app"?"Sửa lần cuối "+date(r.mtime):""].filter(Boolean).join(" · ");
      const op=openWhy.has(r.id);
      html+=`<label class="row"><input type="checkbox" data-id="${r.id}" ${selected.has(r.id)?"checked":""}>
        <div><div class="name">${esc(r.label)}</div><div class="path">${esc(meta)}
        ${r.path&&(r.kind==="path"||r.kind==="app")?` <button class="link" data-reveal="${r.id}">Hiện trong Finder</button>`:""}
        ${r.advice?` <button class="link why" data-why="${r.id}">${op?"Ẩn giải thích ▴":"Vì sao? ▾"}</button>`:""}</div></div>
        <button class="badge ${rc}" data-why="${r.id}" title="Bấm để xem nên xóa hay không">${rl}${r.advice?(op?" ▴":" ▾"):""}</button><span class="size ${r.size==null?"unk":""}">${human(r.size)}</span></label>
        ${op?adviceHTML(r.advice,r.risk):""}`;
    }
    html+="</div></section>";
  }
  list.innerHTML=html; renderFoot();
}
async function refresh(){
  const s=await api("/api/status"); if(!s.disk)return;
  renderDisk(s.disk); renderSys(s.sys); native=s.native; fda=s.fda; libScanned=s.library_scanned;
  $("warns").innerHTML=(s.warnings||[]).map(w=>{
    let b="";
    if(w.includes("Toàn quyền"))b="<button class='small' data-act='open_fda'>Mở cài đặt quyền</button>";
    if(w.includes("OrbStack"))b="<button class='small' data-act='open_orbstack'>Mở OrbStack</button>";
    return `<div class="warn">${esc(w)}${b}</div>`}).join("");
  const wasScanning=scanning; scanning=s.running;
  if(s.native&&!s.fda&&!s.running&&!s.scanned_at){renderOnboard();renderFoot();return}
  if(s.running){
    $("list").innerHTML=`<div class="progress"><span class="spin"></span>${esc(s.step)}<br><small>Lần đầu có thể mất 1–3 phút.</small></div>`;
    if(tab==="big"||tab==="downloads")renderTable();
    renderFoot(); setTimeout(refresh,700); return;
  }
  items=s.items; const ids=new Set(items.map(i=>i.id));
  selected=new Set([...selected].filter(i=>ids.has(i))); renderSuggest();
  if(wasScanning||!T.big.loaded){T.big.loaded=false;T.downloads.loaded=false;if(tab==="big"||tab==="downloads")loadTab(tab)}
}

/* ================= Các tab kiểu macOS ================= */
const COLS=[["name","Tên",""],["kind","Loại","c-kind"],["used","Truy cập sau cùng","c-used"],["size","Kích cỡ","r"]];
const cur=()=>T[tab];
function sorted(list){
  const [k,d]=cur().sort;
  const val=e=>k==="name"?e.name.toLowerCase():k==="kind"?(e.kind||"").toLowerCase():(e[k]??-1);
  return list.slice().sort((a,b)=>{const x=val(a),y=val(b);return (x<y?-1:x>y?1:0)*d||a.name.localeCompare(b.name)});
}
function baseList(){const t=cur();return tab==="big"?t.list.filter(e=>(e.size||0)>=thr):t.list}
function visibleOrder(){
  const t=cur(); if(tab!=="downloads")return sorted(baseList()).slice(0,MAX_ROWS);
  const out=[];for(const [g] of GROUPS)out.push(...sorted(t.list.filter(e=>e.group===g)));return out.slice(0,MAX_ROWS);
}
async function loadTab(name){
  const t=T[name];
  if(name==="browse"){await openDir(t.dir?t.dir.id:null,true);return}
  const r=await api("/api/tab?name="+name); if(!r.entries)return;
  if(r.running||!r.scanned){t.list=[];t.loaded=false;renderTable();return}
  t.list=r.entries; t.loaded=true;
  const ids=new Set(t.list.map(e=>e.id)); t.sel=new Set([...t.sel].filter(i=>ids.has(i)));
  renderTable();
}
async function openDir(id,keepSel){
  const t=T.browse;
  const r=await api("/api/browse",{id}); if(!r.children){toast("Không mở được thư mục này");return}
  const same=t.dir&&r.dir.id===t.dir.id;
  t.dir=r.dir;t.crumbs=r.crumbs;t.list=r.children;t.pending=r.pending;t.loaded=true;
  if(!(same&&keepSel)){t.sel=new Set();t.anchor=null;$("tbody").scrollTop=0}
  else{const ids=new Set(t.list.map(e=>e.id));t.sel=new Set([...t.sel].filter(i=>ids.has(i)))}
  renderTable();
  clearTimeout(t._poll); if(t.pending>0&&tab==="browse")t._poll=setTimeout(()=>openDir(t.dir.id,true),1000);
}
function renderCrumbs(){
  const c=$("crumbs");
  if(tab==="browse"){
    const t=T.browse;
    c.style.display="flex";
    c.innerHTML=t.crumbs.map((x,i)=>`${i?'<span class="sep">›</span>':""}<button data-crumb="${x.id??""}">${esc(x.name)}</button>`).join("")+
      `<span class="stat">${t.pending?`<span class="spin"></span>Đang tính dung lượng ${t.pending} thư mục…`:`${t.list.length} mục`}</span>`;
  }else{
    const t=cur(), L=baseList(), tot=L.reduce((a,b)=>a+(b.size||0),0);
    c.style.display="flex";
    const thrSel=tab==="big"?`<select id="thr" title="Ngưỡng dung lượng">${[[10e6,"≥ 10 MB"],[50e6,"≥ 50 MB"],[100e6,"≥ 100 MB"],[500e6,"≥ 500 MB"],[1e9,"≥ 1 GB"]].map(([v,l])=>`<option value="${v}" ${v==thr?"selected":""}>${l}</option>`).join("")}</select>`:"";
    const lnote=tab==="big"&&!libScanned?`<span class="lnote" title="Bật Toàn quyền truy cập ổ đĩa để quét cả ~/Library (dữ liệu app, Containers)">⚠️ Chưa quét ~/Library (chưa có quyền)</span>`:"";
    c.innerHTML=`<b>${tab==="big"?"Tệp lớn":"Bản tải về"}</b>${thrSel}${lnote}<span class="legend"><span><i class="dot d-safe"></i>An toàn</span><span><i class="dot d-review"></i>Xem lại</span><span><i class="dot d-careful"></i>Cẩn thận</span></span><span class="stat">${t.loaded?`${L.length} mục · ${human(tot)}`:""}</span>`;
  }
}
function renderTable(){
  if(tab==="suggest")return;
  renderCrumbs();
  const t=cur(), [sk,sd]=t.sort;
  $("thead").innerHTML=`<div></div>`+COLS.map(([k,l,cls])=>`<div class="${cls} ${sk===k?"on":""}" data-sort="${k}">${l}${sk===k?(sd<0?" ▾":" ▴"):""}</div>`).join("");
  const body=$("tbody");
  if(!t.loaded){
    body.innerHTML=scanning||tab!=="browse"?`<div class="tempty"><span class="spin"></span>Đang quét… danh sách sẽ hiện khi quét xong.</div>`:`<div class="tempty"><span class="spin"></span>Đang mở…</div>`;
    renderPreview();renderFoot();return;
  }
  if(!t.list.length){body.innerHTML=`<div class="tempty">${tab==="big"?"Không có tệp nào từ 50 MB trở lên 🎉":tab==="downloads"?"Thư mục Tải về trống":"Thư mục trống"}</div>`;renderPreview();renderFoot();return}
  const row=e=>`<div class="tr ${t.sel.has(e.id)?"sel":""} ${e.deletable?"":"lock"}" data-rid="${e.id}" title="${esc(home(e.path))}">
    <div><input type="checkbox" data-ck="${e.id}" ${t.sel.has(e.id)?"checked":""} ${e.deletable?"":"disabled title='Mục được bảo vệ'"}></div>
    <div class="nm"><i class="dot d-${e.risk||"review"}" title="${(RISK[e.risk]||RISK.review)[0]}"></i><span class="ic">${icon(e)}</span><span>${esc(e.name)}</span>${e.is_dir&&tab==="browse"?'<span class="go">›</span>':""}</div>
    <div class="c-kind mut">${esc(e.kind||"")}</div><div class="c-used mut">${macDate(e.used)}</div>
    <div class="r">${e.size==null?(e.is_dir?'<span class="mut">…</span>':"—"):human(e.size)}</div></div>`;
  let html="";
  if(tab==="downloads"){
    let n=0;
    for(const [g,label] of GROUPS){
      const rows=sorted(t.list.filter(e=>e.group===g)); if(!rows.length)continue;
      const all=rows.every(e=>t.sel.has(e.id)||!e.deletable), tot=rows.reduce((a,b)=>a+(b.size||0),0);
      html+=`<div class="grp"><input type="checkbox" data-grp="${g}" ${all?"checked":""}>${label}<span class="mut">${rows.length} mục · ${human(tot)}</span></div>`;
      for(const e of rows){if(n++<MAX_ROWS)html+=row(e)}
    }
  }else{
    const rows=sorted(baseList()); html=rows.slice(0,MAX_ROWS).map(row).join("");
    if(!rows.length)html=`<div class="tempty">Không có tệp nào ≥ ${human(thr)}. Thử hạ ngưỡng ở trên.</div>`;
    if(rows.length>MAX_ROWS)html+=`<div class="more">…và ${rows.length-MAX_ROWS} mục nhỏ hơn</div>`;
  }
  const st=body.scrollTop; body.innerHTML=html; body.scrollTop=st;
  renderPreview(); renderFoot();
}
function paintSel(){
  const t=cur();
  for(const r of document.querySelectorAll("#tbody .tr")){
    const on=t.sel.has(r.dataset.rid); r.classList.toggle("sel",on);
    const c=r.querySelector("input"); if(c)c.checked=on;
  }
  if(tab==="downloads")for(const g of document.querySelectorAll("[data-grp]")){
    const rows=t.list.filter(e=>e.group===g.dataset.grp); g.checked=rows.every(e=>t.sel.has(e.id)||!e.deletable);
  }
  renderPreview(); renderFoot();
}
function selEntries(){const t=cur();return t.list.filter(e=>t.sel.has(e.id))}
let pvFor=null;
function renderPreview(){
  const pv=$("pv"); pv.classList.toggle("hide",!pvOn||tab==="suggest");
  if(!pvOn||tab==="suggest")return;
  const sel=selEntries();
  const key=sel.length===1?sel[0].id+":"+sel[0].size:"n"+sel.length+":"+sel.reduce((a,b)=>a+(b.size||0),0);
  if(key===pvFor)return; pvFor=key;
  if(!sel.length){pv.innerHTML=`<div class="pvbox"><div class="big">🔍</div><div class="note">Chọn một mục để xem trước</div></div><div class="pvinfo"><p class="k">Nhấn <b>Space</b> để mở Quick Look, <b>⌘⌫</b> để xóa, <b>⇧/⌘-click</b> để chọn nhiều.</p></div>`;return}
  if(sel.length>1){const tot=sel.reduce((a,b)=>a+(b.size||0),0);
    pv.innerHTML=`<div class="pvbox"><div class="big">🗂️</div></div><div class="pvinfo"><h3>${sel.length} mục được chọn</h3><p class="k">Tổng dung lượng <b>${human(tot)}</b></p>
    <dl>${sel.slice(0,12).map(e=>`<dt>${icon(e)}</dt><dd>${esc(e.name)} · ${human(e.size)}</dd>`).join("")}${sel.length>12?`<dt></dt><dd class="k">…và ${sel.length-12} mục khác</dd>`:""}</dl></div>`;return}
  const e=sel[0]; let box="";
  switch(e.preview){
    case "image":box=`<img src="${fileURL(e)}" alt="" onerror="this.onerror=pvThumbFail;this.src='${fileURL(e,"thumb")}'">`;break;
    case "pdf":box=`<iframe src="${fileURL(e)}#view=FitH" title="PDF"></iframe>`;break;
    case "video":box=`<video src="${fileURL(e)}" controls preload="metadata"></video>`;break;
    case "audio":box=`<div class="big">🎵</div><audio src="${fileURL(e)}" controls preload="none" style="position:absolute;bottom:14px"></audio>`;break;
    case "text":box=`<pre id="pvtext">Đang tải…</pre>`;break;
    case "dir":box=`<div class="big" style="font-size:48px">📁</div>`;break;
    default:box=`<img src="${fileURL(e,"thumb")}" alt="" onerror="pvThumbFail.call(this)">`;
  }
  pv.innerHTML=`<div class="pvbox" id="pvbox" ${e.preview==="dir"?'style="height:120px"':""}>${box}</div><div class="pvinfo"><h3>${esc(e.name)}</h3><div class="k">${esc(e.kind||"")} · ${e.size==null?"đang tính…":human(e.size)}</div>
    <dl><dt>Vị trí</dt><dd>${esc(home(e.path))}</dd><dt>Sửa đổi</dt><dd>${macDate(e.mtime)}</dd><dt>Truy cập</dt><dd>${macDate(e.used)}</dd>
    ${e.deletable?"":`<dt>Ghi chú</dt><dd>🔒 ${e.kept?"Bạn đã đánh dấu Luôn giữ":"Mục được bảo vệ, không xóa được"}</dd>`}</dl>
    ${e.advice?`<div class="pvsec"><h4>Có nên xóa? <span class="badge ${(RISK[e.risk]||RISK.review)[1]}">${(RISK[e.risk]||RISK.review)[0]}</span></h4>${adviceHTML(e.advice,e.risk)}</div>`:""}
    <div class="pvbtns">${e.is_dir?(tab==="browse"?`<button data-open="${e.id}">Mở thư mục</button>`:""):`<button data-ql="${e.id}">Quick Look ␣</button>`}<button data-reveal2="${e.id}">Hiển thị trong Finder</button></div></div>`;
  if(e.preview==="text")api("/api/text",{id:e.id}).then(r=>{const p=$("pvtext");if(p)p.textContent=r.text!=null?(r.text||"(tệp trống)")+(r.truncated?"\n…":""):"Không đọc được tệp"}).catch(()=>{});
}
function pvThumbFail(){const b=this.parentNode;if(!b)return;const e=selEntries()[0];
  b.style.height="120px";b.innerHTML=`<div class="big" style="font-size:48px">${e?icon(e):"📄"}</div><div class="note">Không có bản xem trước</div>`}
function renderFoot(){
  if(tab==="tools"||tab==="machine")return;
  const tableTab=tab!=="suggest";
  $("reveal").style.display=$("tglPv").style.display=tableTab?"":"none";
  if(!tableTab){
    let n=0,s=0;for(const it of items)if(selected.has(it.id)){n++;s+=it.size||0}
    $("sel").textContent=n?`Đã chọn ${n} mục · ${human(s)}${items.some(i=>selected.has(i.id)&&i.size==null)?" + phần không rõ":""}`:"Chưa chọn mục nào";
    $("go").disabled=!n||busy; $("keepBtn").disabled=!items.some(i=>selected.has(i.id)&&i.path); return;
  }
  const sel=selEntries(), del=sel.filter(e=>e.deletable), s=del.reduce((a,b)=>a+(b.size||0),0);
  $("sel").textContent=sel.length?`Đã chọn ${sel.length} mục · ${human(s)}${del.length<sel.length?` (${sel.length-del.length} mục được bảo vệ)`:""}`:"Chưa chọn mục nào";
  $("go").disabled=!del.length||busy; $("reveal").disabled=sel.length!==1; $("keepBtn").disabled=!sel.length;
}
function selectRow(id,ev){
  const t=cur(), order=visibleOrder().map(e=>e.id);
  if(ev&&ev.shiftKey&&t.anchor&&order.includes(t.anchor)){
    const a=order.indexOf(t.anchor),b=order.indexOf(id);
    if(!(ev.metaKey||ev.ctrlKey))t.sel=new Set();
    for(let i=Math.min(a,b);i<=Math.max(a,b);i++)t.sel.add(order[i]);
  }else if(ev&&(ev.metaKey||ev.ctrlKey)){t.sel.has(id)?t.sel.delete(id):t.sel.add(id);t.anchor=id}
  else{t.sel=new Set([id]);t.anchor=id}
  paintSel();
}
function moveSel(d){
  const t=cur(), order=visibleOrder().map(e=>e.id); if(!order.length)return;
  let i=t.anchor?order.indexOf(t.anchor):-1; i=Math.max(0,Math.min(order.length-1,i+d));
  t.sel=new Set([order[i]]);t.anchor=order[i];paintSel();
  const el=document.querySelector(`[data-rid="${order[i]}"]`); if(el)el.scrollIntoView({block:"nearest"});
}
function setTab(name){
  tab=name; for(const b of document.querySelectorAll("#tabs button"))b.classList.toggle("on",b.dataset.tab===name);
  const isTool=name==="tools",isMach=name==="machine";
  $("v-suggest").classList.toggle("on",name==="suggest"); $("v-table").classList.toggle("on",!isTool&&!isMach&&name!=="suggest");
  $("v-tools").classList.toggle("on",isTool); $("v-machine").classList.toggle("on",isMach);
  document.querySelector(".foot").style.display=(isTool||isMach)?"none":"";
  try{localStorage.setItem("donmac.tab",name)}catch(e){}
  pvFor=null;
  if(isTool){setTool(tool);return}
  if(isMach){loadMachine();return}
  if(name==="suggest"){renderSuggest();renderFoot();return}
  renderTable(); if(!T[name].loaded||name==="browse")loadTab(name);
  $("tbody").focus();
}
async function deleteSelected(){
  const mode=document.querySelector("input[name=mode]:checked").value;
  if(tab==="suggest")return deleteSuggest(mode);
  const del=selEntries().filter(e=>e.deletable); if(!del.length)return;
  const size=del.reduce((a,b)=>a+(b.size||0),0);
  const names=del.slice(0,5).map(e=>"• "+e.name).join("\n")+(del.length>5?`\n…và ${del.length-5} mục khác`:"");
  if(!confirm(`Xóa ${del.length} mục (${human(size)})?\n\n${names}\n\n`+(mode==="permanent"?"⚠️ XÓA VĨNH VIỄN, không khôi phục được.":"Các mục sẽ được chuyển vào Thùng rác.")))return;
  busy=true;renderFoot();$("go").textContent="Đang xóa…";
  let res;try{res=await api("/api/delete",{ids:del.map(e=>e.id),mode})}finally{busy=false;$("go").textContent="Xóa…"}
  const results=res.results||[], ok=results.filter(r=>r.ok), bad=results.filter(r=>!r.ok);
  let msg=`✅ Đã xóa ${ok.length} mục · ${human(ok.reduce((a,b)=>a+(b.size||0),0))}`;
  if(mode==="trash"&&ok.length)msg+="<br><small>Dung lượng được giải phóng sau khi dọn sạch Thùng rác (tab Đề xuất).</small>";
  if(bad.length)msg+="<br>⚠️ Chưa xóa được:<br>"+bad.map(b=>`• ${esc(b.label||b.id)}: ${esc(b.msg)}`).join("<br>");
  toast(msg,bad.length?14000:7000);
  const t=cur(); t.sel=new Set(); pvFor=null;
  for(const k of ["big","downloads"])T[k].loaded=false;
  if(tab==="browse")await openDir(t.dir?t.dir.id:null,false); else await loadTab(tab);
  api("/api/status").then(s=>{if(s.disk){renderDisk(s.disk);items=s.items;renderSuggest()}}).catch(()=>{});
}
async function deleteSuggest(mode){
  const chosen=items.filter(i=>selected.has(i.id));
  const size=chosen.reduce((a,b)=>a+(b.size||0),0);
  const perm=chosen.filter(i=>ALWAYS_PERM.has(i.kind)).length, apps=chosen.filter(i=>i.kind==="app").length, admin=chosen.filter(i=>i.kind==="admin_cmd").length;
  let msg=`Xóa ${chosen.length} mục (${human(size)})?\n\n`+(mode==="permanent"?"⚠️ XÓA VĨNH VIỄN, không khôi phục được.":"Các file/thư mục sẽ được chuyển vào Thùng rác.");
  if(mode==="trash"&&perm)msg+=`\n\nLưu ý: ${perm} mục (Docker, Homebrew, simulator, snapshot, Thùng rác, Logs…) luôn bị xóa vĩnh viễn.`;
  if(apps)msg+=`\n\n${apps} ứng dụng sẽ được chuyển vào Thùng rác. Hãy thoát các app đó trước.`;
  if(admin)msg+=`\n\nmacOS sẽ hỏi mật khẩu máy cho ${admin} mục.`;
  if(!confirm(msg))return;
  busy=true;renderFoot();$("go").textContent="Đang xóa…";
  let res;try{res=await api("/api/delete",{ids:chosen.map(i=>i.id),mode})}finally{busy=false;$("go").textContent="Xóa…"}
  const results=res.results||[], ok=results.filter(r=>r.ok), bad=results.filter(r=>!r.ok);
  for(const r of ok)selected.delete(r.id);
  let t=`✅ Đã xử lý ${ok.length} mục · ${human(ok.reduce((a,b)=>a+(b.size||0),0))}`;
  if(ok.some(r=>(r.msg||"").includes("Thùng rác")))t+="<br><small>Dung lượng được giải phóng sau khi dọn sạch Thùng rác (bấm Quét lại để thấy mục này).</small>";
  if(bad.length)t+="<br>⚠️ Chưa xóa được:<br>"+bad.map(b=>`• ${esc(b.label||b.id)}: ${esc(b.msg)}`).join("<br>");
  toast(t,bad.length?14000:8000); for(const k of ["big","downloads"])T[k].loaded=false; refresh();
}

/* ================= 003: Công cụ ================= */
const TINFO={
  apps:["Gỡ app cùng dữ liệu đi kèm","Liệt kê app đã cài, dung lượng gồm cả dữ liệu trong Library. Xóa sẽ chuyển app và dữ liệu đi kèm vào Thùng rác. Thoát app trước khi xóa."],
  dupes:["File trùng lặp","So sánh nội dung (không chỉ tên) các file từ 1 MB trong thư mục của bạn. Mỗi nhóm giữ lại 1 bản, các bản còn lại được tích sẵn. Quét có thể mất vài phút."],
  orphans:["Dữ liệu mồ côi","Thư mục trong Library mang mã kiểu com.hang.app nhưng không có ứng dụng tương ứng trong Ứng dụng. Mức “Xem lại”: bấm nhãn để đọc giải thích trước khi xóa."],
  ai:["Dấu vết của Claude, Codex, ChatGPT","Các công cụ AI để lại rất nhiều file thừa: phiên bản cũ sau mỗi lần tự cập nhật, transcript và nhật ký của từng phiên, ảnh/file đính kèm, máy ảo Cowork, cache của app. Mỗi mục có nhãn rủi ro và giải thích. Transcript/log cũ bị xóa vĩnh viễn (chỉ file cũ hơn số ngày ghi trên mục)."],
  similar:["Ảnh giống nhau","Tìm ảnh trông giống nhau (cùng ảnh nhưng khác kích cỡ, chỉnh nhẹ…). Chỉ để bạn xem và tự chọn, không tích sẵn gì cả."]};
const TL={};for(const k of ["apps","dupes","orphans","similar","ai"])TL[k]={data:null,sel:new Set(),started:false,running:false,step:"",error:null,at:null,open:new Set()};
let tool="apps", tmode="trash";
const flat=n=>{const d=TL[n].data;if(!d)return[];return d.rows?d.rows:(d.groups||[]).flatMap(g=>g.files)};
function setTool(n){
  tool=n;for(const b of document.querySelectorAll("#tsub button"))b.classList.toggle("on",b.dataset.tool===n);
  try{localStorage.setItem("donmac.tool",n)}catch(e){}
  if(!TL[n].started&&(n==="apps"||n==="orphans"||n==="ai"))startTool(n);else renderTool();
}
async function startTool(n){const t=TL[n];t.started=true;t.running=true;t.step="Đang bắt đầu…";t.error=null;renderTool();
  await api("/api/tool",{name:n});pollTool(n)}
async function pollTool(n){
  const r=await api("/api/toolres?name="+n),t=TL[n];if(!r||r.running===undefined)return;
  t.running=r.running;t.step=r.step||"";t.error=r.error||null;t.fda=r.fda;
  if(r.data){t.data=r.data;
    if(r.at!==t.at){t.at=r.at;t.sel=new Set();if(n==="dupes")for(const g of r.data.groups)for(const f of g.files)if(f.id!==g.keep&&f.deletable)t.sel.add(f.id)}
    const ids=new Set(flat(n).map(x=>x.id));t.sel=new Set([...t.sel].filter(i=>ids.has(i)))}
  if(n===tool)renderTool();
  if(r.running)setTimeout(()=>pollTool(n),800);
}
function toolBar(n,pick){
  const t=TL[n],f=flat(n),m=new Map(f.map(x=>[x.id,x])),sz=[...t.sel].reduce((a,i)=>a+((m.get(i)||{}).size||0),0);
  return `<div class="tbar"><button data-tstart="${n}">↻ Quét lại</button>${pick||""}<button data-tclear="${n}">Bỏ chọn</button>
    <span class="sum">${t.sel.size?`Đã chọn ${t.sel.size} mục · ${human(sz)}`:"Chưa chọn mục nào"}</span>
    <div class="grow"><label><input type="radio" name="tmode" value="trash" ${tmode==="trash"?"checked":""}> Thùng rác</label>
    <label><input type="radio" name="tmode" value="permanent" ${tmode==="permanent"?"checked":""}> Xóa vĩnh viễn</label>
    <button class="primary" data-tdel="${n}" ${t.sel.size?"":"disabled"}>Xóa…</button></div></div>`;
}
function renderTool(){
  if(tab!=="tools")return;
  const n=tool,t=TL[n],b=$("tool-body"),[title,desc]=TINFO[n];
  let h=`<div class="tinfo"><h2>${title}</h2><p>${desc}</p></div>`;
  if(t.running){b.innerHTML=h+`<div class="progress"><span class="spin"></span>${esc(t.step)}</div>`;return}
  if(t.error)h+=`<div class="warn">Lỗi khi quét: ${esc(t.error)}</div>`;
  if(!t.data){b.innerHTML=h+`<div class="tools"><button class="small" data-tstart="${n}" style="margin-left:0">Bắt đầu quét</button></div>`;return}
  h+=(n==="apps"||n==="orphans"||n==="ai")?rowsHTML(n,t.data):groupsHTML(n,t.data);
  b.innerHTML=h;
}
function rowHTML(n,r){
  const t=TL[n],[rl,rc]=RISK[r.risk]||RISK.review,op=t.open.has(r.id);
  let meta=[r.note];
  if(n==="apps"){meta.push(`app ${human(r.app_size)}`);if(r.left_size)meta.push(`dữ liệu đi kèm ${human(r.left_size)} (${r.leftovers.length} thư mục)`);meta.push(home(r.path))}
  let h=`<label class="row"><input type="checkbox" data-tid="${r.id}" ${t.sel.has(r.id)?"checked":""}>
    <div><div class="name">${esc(r.label)}${r.version?` <span class="mut">${esc(r.version)}</span>`:""}</div><div class="path">${esc(meta.filter(Boolean).join(" · "))}
    <button class="link" data-reveal="${r.id}">Hiện trong Finder</button> <button class="link why" data-twhy="${r.id}">${op?"Ẩn giải thích ▴":"Vì sao? ▾"}</button></div></div>
    <button class="badge ${rc}" data-twhy="${r.id}">${rl}${op?" ▴":" ▾"}</button><span class="size">${human(r.size)}</span></label>`;
  if(op){h+=adviceHTML(r.advice,r.risk);
    const L=r.leftovers||r.locations||(r.extra&&r.extra.length?r.extra.map(home):null);
    if(L&&L.length)h+=`<div class="adv" style="margin-top:-6px"><p><b>${n==="apps"?"Dữ liệu đi kèm sẽ được chuyển cùng:":(n==="ai"?"Cùng được xóa:":"Các vị trí:")}</b></p><div class="path">${L.map(esc).join("<br>")}</div></div>`}
  return h;
}
function rowsHTML(n,d){
  const t=TL[n],rows=d.rows;
  let h="";
  if(n==="orphans"&&d.limited)h+=`<div class="warn">Chưa có “Toàn quyền truy cập ổ đĩa” nên chưa thấy hết dữ liệu (Containers, Group Containers…). <button class="small" data-act="open_fda">Mở cài đặt quyền</button></div>`;
  if(!rows.length)return h+`<div class="empty">${n==="apps"?"Không có ứng dụng nào để gỡ.":n==="ai"?"Không thấy dấu vết đáng kể nào của Claude, Codex, ChatGPT 🎉":"Không thấy dữ liệu mồ côi nào 🎉"}</div>`;
  const pick=n==="apps"?`<button data-tpick="${n}">Chọn app lâu không mở</button>`:n==="ai"?`<button data-tpick="ai">Chọn mục “An toàn”</button>`:"";
  h+=toolBar(n,pick);
  const grouped=rows.some(r=>r.group);
  const sets=grouped?[...new Set(rows.map(r=>r.group||"Khác"))].map(g=>[g,rows.filter(r=>(r.group||"Khác")===g)]):[[null,rows]];
  for(const [g,rs] of sets)
    h+="<section>"+(g?`<div class="sh" style="cursor:default"><input type="checkbox" data-tgrp="${esc(g)}" ${rs.every(r=>t.sel.has(r.id))?"checked":""} title="Chọn cả nhóm"><h2>${esc(g)}</h2><div class="total">${human(rs.reduce((a,b)=>a+(b.size||0),0))}</div></div>`:"")+`<div class="rows">`+rs.map(r=>rowHTML(n,r)).join("")+"</div></section>";
  return h;
}
function groupsHTML(n,d){
  const t=TL[n];
  if(d.unavailable)return `<div class="warn">${esc(d.unavailable)}</div>`;
  if(!d.groups.length)return `<div class="empty">${n==="dupes"?"Không thấy file trùng lặp nào 🎉":"Không thấy ảnh nào giống nhau."}</div>`;
  const pick=n==="dupes"?`<button data-tpick="dupes">Chọn lại tự động</button>`:`<button data-tpick="similarAll">Chọn tất cả ảnh</button><button data-tpick="similarRest">Chọn tất cả trừ ảnh lớn nhất mỗi nhóm</button>`;
  let h=`<p class="mut" style="margin:0 0 10px">${n==="dupes"?`${d.groups.length} nhóm · có thể thu hồi ${human(d.wasted)} (đã xét ${d.scanned} file)`:`${d.groups.length} nhóm ảnh giống nhau (đã xét ${d.checked} ảnh)`}</p>`+toolBar(n,pick);
  for(const g of d.groups){
    if(n==="dupes"){
      h+=`<section><div class="sh" style="cursor:default"><input type="checkbox" data-tgid="${g.gid}" ${g.files.filter(f=>f.id!==g.keep&&f.deletable).every(f=>t.sel.has(f.id))?"checked":""} title="Chọn các bản thừa trong nhóm (giữ lại bản đề xuất)"><h2>${g.files.length} bản giống nhau</h2><span class="desc">mỗi bản ${human(g.size)} · tick các bản muốn bỏ, luôn giữ lại ít nhất 1 bản</span><div class="total">${human(g.wasted)}</div></div><div class="rows">`;
      for(const f of g.files){
        const th=f.preview==="image"?`<img class="th" loading="lazy" src="${fileURL(f)}" onerror="this.style.display='none'">`:"";
        h+=`<label class="row"><input type="checkbox" data-tid="${f.id}" ${t.sel.has(f.id)?"checked":""} ${f.deletable?"":"disabled"}>
          <div><div class="name">${th}${esc(f.name)}</div><div class="path">${esc(home(f.path))} · sửa ${esc(macDate(f.mtime))}
          <button class="link" data-reveal="${f.id}">Hiện trong Finder</button>${f.preview!=="none"&&f.preview!=="dir"?` <button class="link" data-ql="${f.id}">Xem nhanh</button>`:""}</div></div>
          <span>${f.id===g.keep?'<span class="badge keep">Đề xuất giữ</span>':(f.kept?"🔒 Luôn giữ":"")}</span><span class="size">${human(f.size)}</span></label>`}
      h+="</div></section>";
    }else{
      h+=`<section><div class="sh" style="cursor:default"><input type="checkbox" data-tgid="${g.gid}" ${g.files.filter(f=>f.deletable).every(f=>t.sel.has(f.id))?"checked":""} title="Chọn tất cả ảnh trong nhóm"><h2>${g.files.length} ảnh giống nhau</h2><span class="desc">ảnh lớn nhất ở đầu · tick các ảnh muốn bỏ</span><div class="total">${human(g.size)}</div></div><div class="sgrid">`;
      for(const f of g.files)h+=`<label class="scard"><input type="checkbox" data-tid="${f.id}" ${t.sel.has(f.id)?"checked":""} ${f.deletable?"":"disabled"}>
        <img loading="lazy" src="${fileURL(f)}" alt="" onerror="this.onerror=null;this.src='${fileURL(f,"thumb")}'" data-ql="${f.id}"><span class="mut">${esc(f.name)}</span><span class="mut">${human(f.size)} · ${esc(macDate(f.mtime))}</span></label>`;
      h+="</div></section>";
    }
  }
  return h;
}
async function toolDelete(n){
  const t=TL[n],m=new Map(flat(n).map(x=>[x.id,x])),ids=[...t.sel].filter(i=>m.has(i));if(!ids.length)return;
  const size=ids.reduce((a,i)=>a+(m.get(i).size||0),0);
  const names=ids.slice(0,5).map(i=>"• "+(m.get(i).label||m.get(i).name)).join("\n")+(ids.length>5?`\n…và ${ids.length-5} mục khác`:"");
  let msg=`Xóa ${ids.length} mục (${human(size)})?\n\n${names}\n\n`+(tmode==="permanent"?"⚠️ XÓA VĨNH VIỄN, không khôi phục được.":"Các mục sẽ được chuyển vào Thùng rác.");
  if(n==="apps")msg+="\n\nHãy thoát các app này trước khi xóa.";
  const pr=ids.filter(i=>m.get(i).kind==="prune_old").length;
  if(pr&&tmode==="trash")msg+=`\n\nLưu ý: ${pr} mục (transcript, nhật ký, ảnh cũ…) luôn bị xóa vĩnh viễn, chỉ các file cũ hơn số ngày ghi trên mục.`;
  if(n==="ai")msg+="\n\nNên thoát Claude, Codex, ChatGPT trước khi xóa.";
  if(!confirm(msg))return;
  let res;try{res=await api("/api/delete",{ids,mode:tmode})}catch(e){return}
  const results=res.results||[],ok=results.filter(r=>r.ok),bad=results.filter(r=>!r.ok);
  let out=`✅ Đã xóa ${ok.length} mục · ${human(ok.reduce((a,b)=>a+(b.size||0),0))}`;
  if(bad.length)out+="<br>⚠️ Chưa xóa được:<br>"+bad.map(b=>`• ${esc(b.label||b.id)}: ${esc(b.msg)}`).join("<br>");
  toast(out,bad.length?14000:7000);
  t.sel=new Set();for(const k of ["big","downloads"])T[k].loaded=false;
  await pollTool(n);api("/api/status").then(s=>{if(s.disk){renderDisk(s.disk);items=s.items;renderSuggest()}}).catch(()=>{});
}

/* ================= 003: Máy & cài đặt ================= */
const dur=s=>{if(s==null)return"—";const d=Math.floor(s/86400),h=Math.floor(s%86400/3600),m=Math.floor(s%3600/60);return (d?d+" ngày ":"")+(h?h+" giờ ":"")+m+" phút"};
const when=t=>t?new Date(t*1000).toLocaleString("vi-VN"):"";
const DAYS=["Chủ nhật","Thứ hai","Thứ ba","Thứ tư","Thứ năm","Thứ sáu","Thứ bảy"];
async function loadMachine(){
  $("m-machine").innerHTML=$("m-sec").innerHTML=$("m-start").innerHTML=`<div class="card"><span class="spin"></span>Đang đọc thông tin máy…</div>`;
  api("/api/settings").then(renderSettings).catch(()=>{});
  api("/api/machine").then(renderMachine).catch(()=>{});
}
function renderSettings(s){
  const c=s.schedule;
  $("m-sched").innerHTML=`<div class="card"><h2>Dọn tự động theo lịch</h2>
    <p class="k">Chạy nền, chỉ dọn mục <b>An toàn</b> (bộ nhớ đệm, nhật ký, file cài đặt đã cài app, cache công cụ), chuyển vào Thùng rác. Bỏ qua mục “Luôn giữ”. Mỗi lần chạy được ghi vào Lịch sử. Tác vụ nền không có quyền Toàn quyền truy cập ổ đĩa nên có thể bỏ qua vài mục trong Library.</p>
    ${s.darwin?`<div class="sched"><label><input type="checkbox" id="schEn" ${c.enabled?"checked":""}> Bật</label> mỗi
      <select id="schDay">${DAYS.map((d,i)=>`<option value="${i}" ${i===c.weekday?"selected":""}>${d}</option>`).join("")}</select> lúc
      <select id="schHour">${[...Array(24).keys()].map(h=>`<option value="${h}" ${h===c.hour?"selected":""}>${h}:17</option>`).join("")}</select>
      khi tổng ≥ <input type="number" id="schMb" min="10" step="50" value="${c.min_mb}"> MB <button class="small" id="schSave">Lưu</button>
      <span class="mut">${c.installed?"✅ Lịch đang chạy":"Chưa cài lịch"}</span></div>`:`<p class="mut">Chỉ dùng được trên macOS.</p>`}</div>`;
  $("m-keep").innerHTML=`<div class="card"><h2>🔒 Luôn giữ (${s.kept.length})</h2>
    <p class="k">Dọn Mac không đề xuất và không cho xóa các mục này. Chọn mục ở tab bất kỳ rồi bấm “Luôn giữ” để thêm.</p>
    ${s.kept.length?`<table class="mini">${s.kept.map(k=>`<tr><td>${esc(k.short)}</td><td class="r"><button class="link" data-unkeep="${esc(k.path)}">Bỏ giữ</button></td></tr>`).join("")}</table>`:`<span class="mut">Chưa có mục nào.</span>`}</div>`;
  const h=s.history,tot=h.filter(x=>x.mode!=="x").reduce((a,b)=>a+(b.size||0),0);
  $("m-hist").innerHTML=`<div class="card"><h2>Lịch sử dọn dẹp</h2>
    ${h.length?`<p class="k">${h.length} mục gần nhất · tổng ${human(tot)}. <button class="link" id="histClear">Xóa lịch sử</button></p>
    <table class="mini"><tr><th>Thời gian</th><th>Mục</th><th>Cách xóa</th><th>Nguồn</th><th class="r">Dung lượng</th></tr>
    ${h.slice(0,100).map(x=>`<tr><td>${esc(when(x.t))}</td><td>${esc(x.label)}<div class="mut">${esc(x.path||"")}</div></td><td>${x.mode==="permanent"?"Vĩnh viễn":"Thùng rác"}</td><td>${x.src==="auto"?"Tự động":"Thủ công"}</td><td class="r">${human(x.size)}</td></tr>`).join("")}</table>`
    :`<span class="mut">Chưa có lần dọn nào được ghi lại.</span>`}</div>`;
}
function renderMachine(r){
  const m=r.machine,mem=m.mem,pct=mem?Math.round(mem.used/mem.total*100):0;
  $("m-machine").innerHTML=`<div class="card"><h2>Trạng thái máy</h2><dl class="kv">
    <dt>CPU</dt><dd>${m.cores||"?"} nhân · tải trung bình ${m.load?m.load.join(" / "):"—"}</dd>
    <dt>RAM</dt><dd>${mem?`${human(mem.used)} / ${human(mem.total)} (${pct}%)<div class="bar mem"><div style="width:${pct}%"></div></div>`:"—"}</dd>
    <dt>Đã chạy</dt><dd>${dur(m.uptime)}</dd><dt>Pin</dt><dd>${m.battery?`${m.battery.percent}% · ${esc(m.battery.state)}`:"Không có / không đọc được"}</dd></dl>
    ${m.procs.length?`<table class="mini" style="margin-top:10px"><tr><th>Tiến trình ngốn nhiều CPU</th><th class="r">CPU</th><th class="r">RAM</th></tr>${m.procs.map(p=>`<tr><td>${esc(p.name)}</td><td class="r">${p.cpu}%</td><td class="r">${human(p.mem)}</td></tr>`).join("")}</table>`:""}</div>`;
  const dot={ok:"d-safe",warn:"d-careful",unknown:"d-review"};
  $("m-sec").innerHTML=`<div class="card"><h2>Bảo mật cơ bản (chỉ xem)</h2><p class="k">Dọn Mac không thay đổi cài đặt hệ thống và không phải phần mềm diệt virus.</p>
    ${r.security.map(x=>`<div class="secrow"><span class="dot ${dot[x.state]}" style="margin-top:6px"></span><b>${esc(x.label)}</b><span>${esc(x.value)}</span>${x.state==="warn"?`<span class="hint">${esc(x.hint)}</span>`:""}</div>`).join("")}</div>`;
  $("m-start").innerHTML=`<div class="card"><h2>Mục tự khởi động (${r.startup.length})</h2><p class="k">Chương trình chạy cùng máy. Mục đánh dấu “không còn chương trình” thường là dấu vết của app đã gỡ. Dọn Mac chỉ liệt kê, hãy xóa bằng Finder nếu chắc chắn.</p>
    ${r.startup.length?`<table class="mini"><tr><th>Mục</th><th>Chương trình</th><th></th></tr>${r.startup.map(x=>`<tr><td>${esc(x.label)}<div class="mut">${esc(x.where)}</div></td><td>${x.broken?`<span class="badge b-review">không còn chương trình</span> `:""}<span class="mut">${esc(x.program||"")}</span></td><td class="r">${x.id?`<button class="link" data-reveal="${x.id}">Hiện trong Finder</button>`:""}</td></tr>`).join("")}</table>`:`<span class="mut">Không có mục nào ngoài của Apple.</span>`}</div>`;
}
async function keepSelected(){
  const ids=tab==="suggest"?items.filter(i=>selected.has(i.id)&&i.path).map(i=>i.id):selEntries().map(e=>e.id);
  if(!ids.length)return;
  if(!confirm(`Luôn giữ ${ids.length} mục?\n\nDọn Mac sẽ không đề xuất và không cho xóa chúng nữa. Bạn bỏ giữ được trong tab “Máy & cài đặt”.`))return;
  await api("/api/keep",{ids});toast("🔒 Đã đánh dấu Luôn giữ");
  selected=new Set();for(const k of ["big","downloads","browse"])T[k].sel=new Set();pvFor=null;
  for(const k of ["big","downloads"])T[k].loaded=false;
  if(tab==="browse")await openDir(T.browse.dir?T.browse.dir.id:null,false);else if(tab!=="suggest")await loadTab(tab);
  refresh();
}
document.addEventListener("click",async e=>{
  const tw=e.target.closest("[data-twhy]");
  if(tw){e.preventDefault();e.stopPropagation();const o=TL[tool].open,id=tw.dataset.twhy;o.has(id)?o.delete(id):o.add(id);renderTool();return}
  const ts=e.target.closest("[data-tool]");if(ts){setTool(ts.dataset.tool);return}
  const st=e.target.closest("[data-tstart]");if(st){TL[st.dataset.tstart].sel=new Set();startTool(st.dataset.tstart);return}
  const tc=e.target.closest("[data-tclear]");if(tc){TL[tc.dataset.tclear].sel=new Set();renderTool();return}
  const td=e.target.closest("[data-tdel]");if(td){toolDelete(td.dataset.tdel);return}
  const tp=e.target.closest("[data-tpick]");
  if(tp){const n=tp.dataset.tpick,t=TL[n==="similarAll"||n==="similarRest"?"similar":n];t.sel=new Set();
    if(n==="apps")for(const r of t.data.rows)if(r.risk==="safe")t.sel.add(r.id);
    if(n==="ai")for(const r of t.data.rows)if(r.risk==="safe")t.sel.add(r.id);
    if(n==="dupes")for(const g of t.data.groups)for(const f of g.files)if(f.id!==g.keep&&f.deletable)t.sel.add(f.id);
    if(n==="similarAll")for(const g of TL.similar.data.groups)for(const f of g.files)if(f.deletable)TL.similar.sel.add(f.id);
    if(n==="similarRest")for(const g of TL.similar.data.groups)g.files.forEach((f,i)=>{if(i>0&&f.deletable)TL.similar.sel.add(f.id)});
    renderTool();return}
  const uk=e.target.closest("[data-unkeep]");if(uk){await api("/api/unkeep",{paths:[uk.dataset.unkeep]});for(const k of ["big","downloads"])T[k].loaded=false;api("/api/settings").then(renderSettings);refresh();return}
  if(e.target.id==="histClear"){if(confirm("Xóa toàn bộ lịch sử dọn dẹp?")){await api("/api/history_clear",{});api("/api/settings").then(renderSettings)}return}
  if(e.target.id==="schSave"){const r=await api("/api/schedule",{enabled:$("schEn").checked,min_mb:+$("schMb").value||200,weekday:+$("schDay").value,hour:+$("schHour").value});
    toast(r.enabled?(r.installed?"✅ Đã bật dọn tự động":"Đã lưu, nhưng chưa cài được lịch"):"Đã tắt dọn tự động");api("/api/settings").then(renderSettings);return}
});
document.addEventListener("change",e=>{
  const t=e.target;
  if(t.name==="tmode"){tmode=t.value;return}
  if(t.dataset.tgid||t.dataset.tgrp){
    const T0=TL[tool],d=T0.data;let fs=[];
    if(t.dataset.tgid){const g=d.groups.find(x=>x.gid===t.dataset.tgid);if(g)fs=g.files.filter(f=>f.deletable&&(tool!=="dupes"||f.id!==g.keep))}
    else fs=d.rows.filter(r=>(r.group||"Khác")===t.dataset.tgrp);
    for(const f of fs)t.checked?T0.sel.add(f.id):T0.sel.delete(f.id);
    renderTool();return}
  if(t.dataset.tid){const s=TL[tool].sel;t.checked?s.add(t.dataset.tid):s.delete(t.dataset.tid);renderTool()}
});

/* ================= Sự kiện ================= */
document.addEventListener("click",async e=>{
  const wy=e.target.closest("[data-why]");
  if(wy){e.preventDefault();e.stopPropagation();const id=wy.dataset.why;openWhy.has(id)?openWhy.delete(id):openWhy.add(id);renderSuggest();return}
  const tb=e.target.closest("#tabs button"); if(tb){setTab(tb.dataset.tab);return}
  const rv=e.target.closest("[data-reveal],[data-reveal2]");
  if(rv){e.preventDefault();e.stopPropagation();api("/api/reveal",{id:rv.dataset.reveal||rv.dataset.reveal2});return}
  const ql=e.target.closest("[data-ql]"); if(ql){api("/api/quicklook",{id:ql.dataset.ql});return}
  const op=e.target.closest("[data-open]"); if(op){openDir(op.dataset.open);return}
  const cr=e.target.closest("[data-crumb]"); if(cr){openDir(cr.dataset.crumb||null);return}
  const so=e.target.closest("[data-sort]");
  if(so){const t=cur(),k=so.dataset.sort;t.sort=t.sort[0]===k?[k,-t.sort[1]]:[k,k==="name"||k==="kind"?1:-1];renderTable();return}
  const ck=e.target.closest("[data-ck]");
  if(ck){const t=cur();ck.checked?t.sel.add(ck.dataset.ck):t.sel.delete(ck.dataset.ck);t.anchor=ck.dataset.ck;paintSel();return}
  const gp=e.target.closest("[data-grp]");
  if(gp){const t=cur();for(const x of t.list)if(x.group===gp.dataset.grp&&x.deletable)gp.checked?t.sel.add(x.id):t.sel.delete(x.id);paintSel();return}
  const tr=e.target.closest(".tr"); if(tr){selectRow(tr.dataset.rid,e);return}
  const act=e.target.closest("[data-act]"); if(act){api("/api/"+act.dataset.act,{});return}
  if(e.target.id==="relaunch"){host("relaunch");return}
  if(e.target.id==="skip"){await api("/api/scan",{});refresh();return}
  if(e.target.id==="restart"){if(confirm("Khởi động lại máy? Hãy lưu công việc đang làm trước."))api("/api/restart",{});return}
  const cb=e.target.closest("[data-catbox]"); if(cb){e.stopPropagation();return}
  const tg=e.target.closest("[data-toggle]");
  if(tg){const c=tg.dataset.toggle;closed.has(c)?closed.delete(c):closed.add(c);renderSuggest()}
});
document.addEventListener("dblclick",e=>{
  const tr=e.target.closest(".tr"); if(!tr)return;
  const x=cur().list.find(v=>v.id===tr.dataset.rid); if(!x)return;
  if(x.is_dir&&tab==="browse")openDir(x.id); else if(!x.is_dir)api("/api/quicklook",{id:x.id});
});
document.addEventListener("change",e=>{
  const t=e.target;
  if(t.id==="thr"){thr=+t.value;try{localStorage.setItem("donmac.thr",String(thr))}catch(_){}const T0=cur();const ok=new Set(baseList().map(x=>x.id));T0.sel=new Set([...T0.sel].filter(i=>ok.has(i)));pvFor=null;renderTable();return}
  if(t.dataset.id){t.checked?selected.add(t.dataset.id):selected.delete(t.dataset.id);renderSuggest()}
  if(t.dataset.catbox){for(const i of items)if(i.cat===t.dataset.catbox)t.checked?selected.add(i.id):selected.delete(i.id);renderSuggest()}
});
document.addEventListener("keydown",e=>{
  if(tab==="suggest"||tab==="tools"||tab==="machine"||e.target.matches("input,textarea,select"))return;
  const meta=e.metaKey||e.ctrlKey, t=cur();
  if(meta&&(e.key==="Backspace"||e.key==="Delete")){e.preventDefault();if(!$("go").disabled)deleteSelected();return}
  if(meta&&e.key.toLowerCase()==="a"){e.preventDefault();t.sel=new Set(visibleOrder().filter(x=>x.deletable).map(x=>x.id));paintSel();return}
  if(e.key===" "&&!e.target.matches("button,video,audio")){e.preventDefault();const s=selEntries();if(s.length===1&&!s[0].is_dir)api("/api/quicklook",{id:s[0].id});return}
  if(e.key==="ArrowDown"){e.preventDefault();moveSel(1);return}
  if(e.key==="ArrowUp"){e.preventDefault();moveSel(-1);return}
  if(tab==="browse"&&e.key==="Enter"){const s=selEntries();if(s.length===1&&s[0].is_dir)openDir(s[0].id);return}
  if(tab==="browse"&&e.key==="Backspace"&&!meta){const c=T.browse.crumbs;if(c.length>1){e.preventDefault();openDir(c[c.length-2].id||null)}}
});
$("rescan").onclick=async()=>{await api("/api/scan",{});for(const k of ["big","downloads"])T[k].loaded=false;refresh()};
$("pickSafe").onclick=()=>{for(const i of items)if(i.risk==="safe")selected.add(i.id);renderSuggest()};
$("clear").onclick=()=>{selected.clear();renderSuggest()};
$("quit").onclick=async()=>{if(!confirm("Tắt Dọn Mac?"))return;if(native&&host("quit"))return;await api("/api/quit",{});goneScreen()};
$("go").onclick=deleteSelected;
$("keepBtn").onclick=keepSelected;
$("reveal").onclick=()=>{const s=selEntries();if(s.length===1)api("/api/reveal",{id:s[0].id})};
$("tglPv").onclick=()=>{pvOn=!pvOn;try{localStorage.setItem("donmac.pv",pvOn?"1":"0")}catch(e){}pvFor=null;renderPreview()};
setInterval(()=>{if(!dead)api("/api/ping",{}).catch(()=>{})},20000);
addEventListener("pagehide",()=>{try{navigator.sendBeacon("/api/bye?t="+TOKEN)}catch(e){}});
addEventListener("pageshow",e=>{if(e.persisted&&!dead)api("/api/ping",{}).catch(()=>{})});
refresh();
try{const sv=localStorage.getItem("donmac.tool");if(sv&&TL[sv])tool=sv;const saved=localStorage.getItem("donmac.tab");if(saved&&saved!=="suggest"&&(T[saved]||saved==="tools"||saved==="machine"))setTab(saved)}catch(e){}
</script>
</body>
</html>
"""


# ------------------------------------------------------------------ cài app
ICON_B64 = "aWNucwAAtAJpYzA4AAA7P4lQTkcNChoKAAAADUlIRFIAAAEAAAABAAgGAAAAXHKoZgAAOv5JREFUeNrtfXmcXFWd7/d3zr231t6XpEM2OntCQiCAAYTAsCOCMyKgOPp8+tTBpyPOc9T3dHTUGfXp8JzRceTNCCM8AUFFFlkExMgStgAJSSckQLpDkk7vW3Vt955z3h/31tKVarJ1VdetPt+P167QnU7Vvee3fX8boKGhoaGhoaGhoaGhoaGhoaGhoaGhoaGhoaGhoaGhoaGhoaGhoaGhoaGhoaGhoaGhoaGhoaGhoaGhoaGhoaGhoaGhoaGhoaGhoaGhoaGhoTEdIH0L9H2qcih9C/TBPpbPrYV+5imDGacsjBko8PSO39+w4dDvx2JaGfgV0ehEod64UWmFUP1Wjt7x9YYNhL5Wtnj+bErWGIz3DqoudAKdALo2prXUVLMHsNLEhha2AAshWhuJh2tVVxwSvX+UecpBTaIAlFYA/hN8AjYQPnAem4tRznsHVdfGnzsAnGK/YMENt86WFGBAPPfUHVt7AH49EIaZE9pwGG9//0P9AIopeY4FG8y5Z5xKwTFHvpHYKgoUQlUqA6peoQfh0s/yucMG2/fc/xH5D33ux/+pse60P5/HwuFVLFS3XNryRBaw5klbcOJ8hRcaqdyvU1oB+Pd4uIKqFMAIEPJNZvJRmU6PkYktIhk7oBLp1+JvvfTGnu9c1ZOvEOau/4DFA2HVtbHTATaqSTwDpRVAZQi+++d169hcs93Y1/2CQldXEgBaVm6ItvzNbWuNSMu7iPFzQOxUEObwoMHBAUhASe9p6gCgutWB6Z4UIoC4+9xlElBC9CvpbIdjPy0Tw8/2bX7gpZ6f3tDr/TVz7voPGPtGIdBxj8zzCHyvCKhqBH/lSt4Waje6Nz+YAiAAGKv+/e1389qmq4iZlzLDWE4BV9hlGlCOhIIUUFDebyDPXjAtJlVNAyhFGa8ACgQiBUaGQcwCwAHlACrt7FfA4zIx8uC++7//2NA93xsBgLZ1V4S7RxyBNx4R1aAIyKfCT9lr5Uo2yzjV7Nn6/5IAxKJvbZwXXnLye5kR+UvixnoecAVephylAAFylX/ODmhouHpBESQUFAGMTIOxjMFIObukcu5Wg313v/ap+a9VkyIgH1t91rbuCrN784NpAM7i726ZG1609FOMm59kAd6qBCATrtATgQGkLbvG0SkEpSQIxC2TkQXIpEgrYf8y1d35zzv/esXmrCJIvOWgo8OXoQH50uov2GBAvEnYty+x+OvPzQ2vPPlTxI1P8ZDRIhOAtB3X0pMWeo0p0QZSSaWIcc4jDCLp2HCcu1I9WUVgta27wuje/KDt+gz+UQLkK8EHaNaai6yerY/FAZgn3T78MRaMfN2IGG0iDkjHcQjgIO3aa5TILZBK5isC5SRvSjzz1D+98aPL+2atuSjSs3W/DRT1BpRWAMcj/IsXc4RPNLD1sfHlP+w4yWpr/yGPBi6QCS34GtOlCBg3ajiccftNMTxw4/b/1vYAgBDmrgf2Pef4wRvgFSj4+cLPADCsW2dh+3aFnrcSq24b/iurefZdzLKWi5jjQEoiIq4JPY0yHlMvvFQQSekw02zmkegHm6/8mxZ64+0nxnc/lGxZuSEU7+uSRYwsaQ/gyIg+BoBaVm4I9HVsHJ/zmd80Nr/7kn/i0fBHRUJBOUIQI64Po0YFOAQSBPAagzmx1PP23p2f2PnFtdtaVm6I9nVsTBd4AhUVElAFx/us6awrAwPP3h9bdNP2leE57bcbNcFTnBHHZfW1u69ReYGBw8OGIVP2sNPf+9GOG+be33TWlTUDz96fhlubUnFKgCpV+BvPuDQ4+MIjo0tuev2c0Lz2+5lp1Iu44xAjQx81jQrOFwhmcE4BQrqn93Mdn5z1I9cT6HSALlGEF1BaAUy8eMvKDWZfx8bYin/v+7BRX/9jIqNOpmxBjGmXX8MfIQEjMIszZ3jou9v/a+PfYe56A7xboasr4wnISlACrIKEn3mWP9DXsTG28qfdnw20Nt9OktfJtCO18GvAPxwhg1Qkk46w2hq+vPLW4f/AvuecphNONoEFvODcT6shpgrwPph3UcO6C0NDmx8fWf4vb30kuPDEn4u4cCAlgy7o0fDvBIK0UW9Yqe6Bn3Z8vPmvGs+4tHbwhUdSngcwWfVg1SuAQ1J9jYvPCA6+8UJs8fe2nhNqX3EfKaqRjoSu5tPwezwAkGBBw0h1771x5w0Lftiw7sK6oc2PJ/OUgJyuUIAqQfhbVq60+jo6ku1feXR55OTznyZu1sm0LbXwa1RLegCMJA8ZPLlnz0d33th+W6UogelSAFnCD21tRtucdcDSdeGm93zpcR4OnSziaU34aVRd7SAzGBSpscSuzZe+8dX1LzUtWxYaeP31VF4oUHYlwKeZ9OMNy9ZbfZsfGZ/317/+mdVce6ETsx1iTKf6NFBtxYNSKMkCZohHms/mAePO3rFUGhhjiMXUTCgFLiT9WEP7uuBQxzMjy/7PG58LnHDCF50xxyHSeX6NqtUBTKaFY9QGZpmtq+f33/yJexqWLQslu7unjQNg0yD8BIC1tKw0h97anFjwPx9ca7Yt/I5MSkFQ2u3XqG4lwMhwxhzHamm6bukPOj42tHnzSOPiM6z88vdyhue8zK5/xvrz+Oz5JoJzMPfab/yCh4OLZdJRxDTppzETPAEFKFI82nC2ecKJv+199fkRRFo4xntkNXoAhaW+rGHdOgtvbR5Z8sU7Pm40RM8RcdvRjT0aM8kPkLaQPGI2161+37fRvTlRN5vM/JoYTCwU8rUHMNH6z5plJEdHZes135pXu/qS2yApBKn0fD4NHOuuLz8eHAIxlZaCRUKralZf9kr3Xf+wvXHxGcHE4H5RzhJho8x1/qyutdUaee21ocbTrr2B15itzqitiT+NYz5cBgMcCd+WB3DOmHXCSV8C8Nig3cM8o6zgdg9SqRUBK6sH0NJijBw8aDd/8JtLeF3Lx2RcKqq8oSQaPoBUAGfAygaCI33qBRBxGXeEURs5q/2bT12Grq5YQ/u6wlCgpIQgK1OREQPA6mbPNtHXF29+98c+xaNmo7TdWl99nDWO9mAJBdRaQFsEsKV/N9wouBuLAies/RsAgSHRX9ZsAC9b7N/SYqRiMdn83i8uqFl92Y8hEHRjf72GW+PoD5YtgdlhwtWLGX7fJWEyf67mIYCptJQ8EpwfOenPXh7+7Q+3NbSvCyaHumU55giycrX51s1eZqKvL9Hwrg9dySNmo7SFtv4ax3Vwkw4QNgBO/l7Qp6AkGYRA20kfBkAineBFsgHkRw4gqwRGRvYCdQtqjLq265XIruPS0Dh2DyACRE2Co3z/ebhMCMVCNRe1XvcPy0f3daTR1MQLQgFfcgAEgBra1xnYuzcx/9M/PZuFI2tEwlYAcaXcZkl96etoLgBIeyFA2ATSwj1ovv1MIBKOEDxsRurO/NDVAJK1s5aYRTwA8oMCoMK6f8diBgARnLfmChZgTCkltR3TOK6DS8C4rdAScslAR1bBHnMBsHDTFairi46O7stwdOTXLEDmd/Ox7l0yvPycZhauu1imFUB6A6/G8aTP3DTg0npCW4RQYwKO8vmueyIuk47i4dBJc6/95zXYty+Fhnbuew+gbsECjpGRVMtlXziFB4MnqpSjSC/q1MDx1wHUBdxj5sjqSCUpJQUPGWZoxTl/BiBdM6vJKMIDUCVXAhbm/kmGWjnQ5ZjzVp3OLE5OWjgEXfmncTyjtwGDgHlR97jNqyFs6VOwWI4j8Gk6gJQAeKhuPQBrbGSECrIByi8hQOb3srHhIQbAMiKNZ3oPR/P/GscFRwE1JrC43j1KyxvdrAAj32cDmLIVYIVPrl33vtno3iXQ2Mj8GAK4XxsbGQ6+IepWX9CqjPDJ0na7IFTBKNRquVCln6uSLoKb/19YC8yvce/5GbPZhEH7vr2ISKYdxQJWa82Z1y8FYCMa5aUcIW6UdOBnNMoxOOjUnHbNPGYZTSrtKFRx/C+US1BpF6d0YMxN+61tYbC8Ota1LQx1poAj/H/vlVSSm5wH5yxbAeDJaLAlGMNe5uk3ytODqtI8gENXfNlBDsAxF56yilumCSlltRamSAVETSDA3NfT3SJb7S3Ap82mrNKdGwUW1AIpB/5PL5FbJMeijWsBMEhBeXJKfmgHziqCSCjIxgFpRBsXgQOKlKIqTUulHGBtC6EvAXSNKgT49AmiyaoiL168AlAAjUHg1FbKZgNMBpw+m2FLv0CUAX42MwRFSgIsEG4HYMXGuottEVKVygFMCAHGx2MAYMGKzIcEqEoLgAnuoVvVxKaViJIKMDmwopF83SH3TsU/MRs4Zw7DghqCVDni7/1LGILc9Qh8f5yEArg5q37F+XUYH5eoq2Ol4gGMEqUA3dexGAEwmRFYoGT1+qdEQFooNIeA9lrCzgGFIJ+GlJQCmHJLZAmq+u41uff04gU56294XYArGgnLGwg7BhXCPDdg35epQEcBxNtQO6sOsdgY6uoyYYAokDFVKR5AofDn4pZolCmlVDUz01IBjBHWthBCZs4KlTsDYUugPkC4op1BqurLsKQF0BwC3n2Cy/5x7/QK6YYB581jiDsuUej7z0skVDDqWv5c5DzlqcDShQB1dYTxXtGw/PJZFAgtUWlZCduIS0ZKMQJqLHIbU6bR9+YeCSmqjAPgDBhNA/9lFUdzyMu45H1PAfjoSoZ5NUDC8XH4Q0RK2JIHgjW1665cBsBGZDbzUzsweXWNBACKgavSzx6c1vjfkW5DysI6wsJagpTTowQyJFnEBELG9GcjpvKQJhxgaQPhE6s5lJpY9JPJwrSGCf/9ZI5xJ+cd+PhgkeKG4eUGqUiWrcIHgqjctB9S7uSjarwIQNpxU1FRE1jakGtNLev7UK4QWFxheSOhIeDVyFfBPeYEDCeBy09kiJq5hHghD6MUcPFChqYAkLC9w+3nzy6EJ0uyZOPBWIkXjZKqzszfBGY6JYGL5nMoAOvbOOZEcz3q5SUigRPrGBoChJRTHVkA7jH/580jfGYtn8D8Fx5kCaAtQvjW2QakqoKioIzlV0VH51GlcgATQoA87YVq3f7OCThnLoHgTqlZ0cSQcKanNj1D/hnM/0kA5g3+CHDgpxeaiHojMugdlIUjgfctZvhvqzm6xwGLV1UyhKZ6VLhRjrXjhdNcqmsoBbCqkbCmhbnpWwLet4jhiS6Z/ezlrP4bTysYDFhUT9i/TyFg+ZMLIG/OX8IGbjrfyBJ/nA5PFgoJfPpkjhcPSrxwUKEh4GZI/GZYvKSf70eCVbX7H3eAv1rLETJySu7KxQxrmglj6cMf2Km2/vNraerLxabBzEEB/QngB+cZ+MBSdkTCn61AY0BDEPjPy0ysaSb0J9w0oQ8bA6gICeizxSBVGgKYDBj0iKn3LnIPqMHcONRkwNfP4tnuNCrjlJwFngLgPr3rmQm/cQf4xlkc1y47cuEvtjfgxxcaOGUWYSiFbPOQH/Wh39eDVxUMj5iaFQa+eTaf0AHIyT18Z85h+Mxajt64qxjKhbRXK7amhblZAB8pAoO5IdVYGvjBBgM3rOVw5LEpM+4pxPY6wi+vMHH6bML+MQWut1CWdTdg1ZEAJnMPaH0QuP1yC/MKatIzoYFQwJfP4BhPK9y8xUFr2P25ksXjyr3PUrnaxuDKHZ2jKn9oPiP3GogDp84ifP40AxctcBXY8SjPzHOosYCfX2binzc7uHWbAMGtkxCyUm9N+cq49Wiuo7AoADCQBObWALdcauGkZirqnpJ3+KQCvvVuA0TA/90iEDWBoOEeyqnWhW5dPGFFE2XLY/3AoRBcb8qWwCUnMvzLBSZqLWRDqqkKKWot4GtnGljZRPj6Mw4Gk27dhsUrWRFUgQKwCybl+CnoYh714gj3kALA1csYvnamgZYQvWNsSt7/SQV882wDZ8xm+NYmG52jbqVegOeUhJoCha88HqDRG5S5solgMMqmBSsmh+W54EICsTSQFMB7FzF8fA3HWXNYtsd/KjmMDCEqJPD+pRxntDE82inxL5sd9MQVoiYhwCemUSuhvFx7AGUWeJU32UcoICXcNt/GEHD+HIZPnsxxzgkst52WjuzASwVcsYjhrBMs3LZd4p7XBQ7EFBKOqwgM5qavCqneYzkEmTkADQECm2bvPyvwec1KtgCSjkJ9gHB6G+G6FRwfWMonfN5SEJiZVeJSuUNEP7Ga44L5DDdvEXhqn0TXqIJUbmhges9DKW/MmNIewBTEp5XrAtieC2h5LmfEACImYWEd4dx5DO9pZ5hbk2tBJTq6Ip9MLNoYJHx+Hccn17g56vvekOjolxhMKozb7u+2JbKcwtEKAkPObc78nlLd94xwF1N2+fc1LVyhJwKaQsDCWsJ7FnG8p51jSQNlj4dU5clcMMoJ9ol1hO+eayBmA88dkLj7dYFXeyQGEsBgQsHkBIu5YULmeVNe2bEqCMH86ALMaA9AeYz+qW2u1Kxqdl3BNS0Ma1oIbVGa8ICFOvZ8coaVdiQQNoEN8xg2zGOwBdA5qvBYp0BKALsGFYZTQNxW6BhQR6RoCK6gtYSAJY3uG2yvJzQH3dDFmGJPILObL+NtZDwmWyhYnLIcSGPIDUWWNhDeNYfhzDkMbRHKNurkC34505ZE7sqdjLsfNYELFzBcuIBhLA28Maywca/AKz0Kbw4rHIwrjKXdz+RIQCoFk1HWawMmKgntAfhsz/y2fgkCsKXPdflDhkC4iAeQidkLrR+OcGAoJ/egxG1M6gFwynEDR3ug8q1o1CKXAJviQoRM92NblNDiVectb2JoDQO1FmFlE6HGIhgMWNFEh3yGjBLMMP98GoUm894yikh5GYNTWgmntOZEoyeusH/MFfr9MYXdQxKjKeD1IYWhpIJB7hi4TOGX0grAXyFA0s5ZBoJLTo2kFDpHFP7QKfEvLwGnzmL45FqOc+bmOIAjFdCMYA4mFW7bJnHPzhwHEPTWW2esiVA5Qu9IZYM8yzQr7HowUrnhTGuY0J+Y2oUZGX2SsBUGvXf44gGJuoBbhLSl1/23DAYsaWBY0kBYWE9or6OslcyERELlMgGYxjFqSrnVg/lKvT+h8MaQwu5Bhd3DCr3jCpx5a8kF8NawynqFmTZsmkq+QBXM/9EeQOktQf6fOQFBbyK7LYAn90o82SXxF8sYvnaWgZYwHZat9lLzYAQ8+KbEt5610TkMRCwgYAAhM39D7EQldCwu+bwaQtBwlUHQyG3MoRLcr5GUGydnz6oCNh1QE1bYSCVgMEKNBZxYTzhrDsPyJsKfLWBoDk0Mr8rtPuc/m8wNerlHYdN+iW39Ei90S/THXWGHUmBEE4a/WHziczKYDgEOy2f4yTXKuIXwSL8ay/3vd++U2HQgjVsvn7wOoPCAfe0pBzd7dQBNYVdYprQoiABHqGz8L7wJLEsaGZzdLgM31Uw2I4Dzie8hah4y3AbKs5I7BhRe6XEAEBbUAufN57hwIcP58xlMlrOkpRaifN6ByLXkj3dKPNYl8GK3QtxWMBgh5CnosJUZRnjosy3m5MJfDoD2AI74YXhPtykE9IwDH7o/jTvea+GklkMrAfMP2VefcvDTVx20hAgKpRnXrTyScVH9xLTmovrSxqSq4A/iHX4gZABhkzz3Grhtm8Dt2x2sbnE9qmMJrY6lIJU87240Ddz0goNf7BAYTbnxfcRy36PKV9BKFwJVPQdwNLCFa+lGUsD1D6TxwNUW5tVOVAIZ4f/OJgc/2eygLUolbUeVEjAZ4cQ6yoYRgJvmMpk7omy6732+t2N63XpQhI4+hY/9zsbpbQw3nOpyLKoEXTAZTy2WBm560cFjnRK7ByVqA4SmoFemLQGnkqxOmWYuaODoi22ipusJfO0pZ0IMnzloz+6X+PHLAq0RKumSDoJbqdgUBhbUsgmFNAtqGZrCqLiVWcobWioUELXc97txr8QH77NxR4fI8ghTFSJlnsmBmMJHHkzjhy862D+m0BDKrReXM7QWmKHsLkB1XLZUaAwpPPSmg/t3i+w0GuYRct942gEjBUJpByISKaSEwom1hLpgjndQCqgLAifWElLC/blKvI9SufenPqgQMRW++KSNa36bxmhKZdOhUyH8d+8UOP+OFDb3SMyOAiZXELLSB6EL7QFUMtzSUcJPXnGQsFW2zv2+3QJbeyVqrNJvqmHkFuCc1kbZVuT8g39aG8EWquIZ6oyXVBcA/rhX4iO/s9EXPz4lkGklvrND4MYnbLcIy8uSKKXPb9k4AOltrKm2my6Ue6Be61XY0qewfo4rZb95XWTXhZX6M7ulyYTT2/iE+D/z9fQ2DiKRzXdXOtkqhUu0vnBA4qpfp/G7D1hoCNJRk4OZVuJ/fdnB3/3JRnOYJiga+GEkmOYA4IvZdUIp/GmvhAJwcFyho18hZJY+rsyUALeGCSd7yzIzQpL5enIroTVMZZ9SfLzeQF0A6BxR+C+/szGcUkfFIWdaie/eKfCdZx00hXLMvoZWAFPOwAc44dE9rtV/dr/EgZgsyzRaRm5Z8fo5lB04QkWWZayfQ4jb/ipUySiBZ/dJfPoRO9tLcaRu/x/3Snz292mEzJmxMr2yFUAVLwZUXtntvlGFWFrh9QEJVa6FHACUVLi0nRftSMv8+dJ2DiWV756F4+0C3NglcVeHmMBxTFoPwYDhpMJ3N9mwGIFPw5KWKeUBtQfgg45CBoymgD3DCp3DKsvCl8P9nxVlOGcem7AsE3kjsgHgnHkMs6LMV2FA1p2XbqrwC0/YeOpt6a7IVZPHzbYA/vpxG5u7FaJWVawL1wrALxmBsXT5FlHku/8tBe5/4c68Fp+GAfkt21IB//aKM2mvRKaxaEuPxMNvSjSH/UP4Vb0CUFV+EQG2Uni5RyJuU7Z0vKQXuX3pk7n/xcIAqVR2RqifLlsBNQFg0z6JF7tltpuw2FSnm18V2ck/1bASXXMAfuABJGARoT+u8OawRIDyym9LtAg07QCt4cnd/2JhQGuYIe34c2EoU+6WoH981oEtJ3oBGev/+z0CD+x2m66ErIKzJXUI4Bs3lTNgW5/Kjgwr+UqytMIl7SzblkyHGXrSEiZc0s4wnla+bFsVCqgNAC/sl9jeV9wLuKtDuJWQ+khqBVDu+D/A3XFe/XFV+sWc5Bb/XL6IH1GKK/P9yxdxEJFvF7YxAlJC4dE9ub2LmU7IgYTCS5r40wpgOg9nLK2QKvFWYPI6EptDhNUtdERTdDPfX91CaA5RdnqNH2suQgbh928JJByVXQQKAI/tkTgYkzC5zvlDbwaaZm1awo/JGTCUAK5ey9EaoSOaoZ8JA1ojhPcsZrjlVceXLLmEO1ego1fh1YMKZ86l7K2+b5fj3v9KWoTgg81AOgsAf7HCCQeYW0v42/VGNgNxNOu2/3a9gbm1hITjz2dDBKSlwovdMjtbYCSp8PqgQsDIzVSsluetQwCNCdY/lgY+vtZAc9jNNLCjeNBSAs1hwsfXGoilJ88cVHqTjMEILxzItcp2DCgcHFNlq8HQHIB2Acp+ZVJ/syOED67i7nDKo3x6zCMnP7iKY3aEfJkSlNId1rq9zyVcAeD5fQIpR7mHudpcPu0BaGSs/1ha4eJ2d6KulMc2PVhKl0C8uJ1hLK185wUouNWWPePu0g4AePmgBGcE3eOvFQCqu+eAcO1K4/gG5nl/79qVBgxGvnSZGQEpR2FHv8sD7BqU2X0IGloBVB0MBvSPA5ct4lh/AjuuPXqZttr1JzBctoijf3xq1nBjGgqDxtPu61janzP5Z85eADkjsoAls3ZjKeCMOQw3XWROSaVhZonnTReZ6B5T2NorES7DABNMYT2AQcDrAzLb4aimaM16JRWXCe0BaBDcfP23zjPRECRMxaq/zOaehiDhW+eZcKT/CoMUgLgD7BqQ6I1DZwC0AqhO1384CVy2mOP0OQxCTt0yTU5uFd3pcxguW8wxnPRfKJBZiaY9y0oOAdJ5ZVz6QR0d0WUD9UHgmxvMoyr6OZpQQMH9/c++LZCyAdMHZJpUQJATdvVL9MXzlp9W0/kq024w7QFUMBIO8L0LLCyoo5KszMqM3F5QR/jeBVa2OtA3oZHu/PPLbsAq2g1WBpgM6IsrfGG9hb9YzrMjrkuBzEKTv1jO0dFn4Kbn0mgJl3aV2VRVBHJvApAtJYKgKjpdqvq2A2vxP/K4fyCpcOZcjq+82yXoSl2sw5mrBL7ybhOb9gk8f0CgIVjalWbHPX+BA/1xhZd73BXkOsLUy0F9D07u1JvmEMNNF1vucFGUnqHPrOUmAm662MJVv0whllYI8srtrWdwS6O7hhUMqlIOQGcBMKNIv7R001n3XB3AsiaW3fNXrn9fKWBZE8M9Vwdgcff9lOvfPxalJZSrABhp46IVAPy9XQhwp/z+4EILq1uZu2i0zMLHPD5gdSvDDy6yEE+rsiqhY+VLNLQC8HWhD5RL+v3oUgt/scIoKel3JByESwoa+NfLAxhLoyQZCP/RZZoD0BxACSyu8Kbd/sP5Fj54kpHdazfdRKQjgWtXuUNHPvtQGlELU7KuWwNHPv5IZwFQ1YRfWri5/h9d5gr/dFr+yZTAdasMQAH//eE0QobLUeihmzoE0DjOuDVuAzUBwm+uDVSc8OcrAaGA604y8JtrA6gJuNuFdNytFYCeCHSMl0Fu/ro+SLjr/QGcO59XpPAXFgqdO5/jrvcHUB90F6AYpJ+lngikcVTxPiOgd1zhmpUGHr4+iDWzWEULf2E4sGYWw8PXB3HNSgO94yr7mTSgSUANTMryGwwYt10h+sZ5Fr5wppltavFLB15m397CesLN7w1gWTPDd5+2YTAgYrqfTVMDOgTQKGy5Va7Vb40QbrkqgC+caUKoyk6tHa55SCjgC2eauOWqAFojhN5xdUT7CTRm6kQgpbLXTCnsMbx59U0hhmvXGfji2RZaI+QLl/9wSgBwLf4VSznOOCGI7z+TxgOvCwwkJOq8HgLdoz8Fi0F0O7D/hMNggCOAA6MKp5/A8dCHg/j+xYHsFh+jSu54JkPQGiF8/+IAHvpwEKefwHFgVMER7vc1P6BDgBlF8MVtoG9coTFM+PvzLdz9gRDaG1jWIlabi8y9/gFHAu0NDHd/IIS/P99CY5jQN64Qt6GJQh0CVC+5R5QZ2qkAEE6ezfDnKwxcs8rd3AP4i+g75nDH4waiFvDFsy187BQTd293cO8OB1sOuo26NQF3qEk1De7UCmAGlgJm2mZtASQdBVsAp7RxfHWDhfNP5FlrJ6S7iWemWL9M63Jm/dgNp5v49Gkmntwj8O2NabzSLWByIGiQu8FX6bLiSmhy0B7AUbj4jnS38wgJtIQJa2dzXL/GxPtXGdnqOOF18XE2M70iznLCzRlwQTvHuQtD+PV2B7/YauN1b44fZ0DEpGx6USuDas4ClK+3YcoHZGSEPi2A+iDhzLkc1602sWEhx9xamjCocqYKfrGwIMN3SOWWDl+32sB1qw3sG1XY2Clw12s2tvR4Qz05EPaUQUZ5aH1QHpmZ8SFAJpanvIUZac+9d6Qr9GfN47h0sYELF3EsbWITFdsMc/WPJzRgzF1tfv0aA9evMbBrQOLxNwUeecPBq90S/eMKBnPDBIvnhpQozEDuQIcAU9Rrn2eVqGAcdobBTjuAI12BD3BCWw1hRQvHhoV8cqH3PARt8Y88NMgM85TKVQZLmxiWNjHccIaZVQYbOwV29El0jymkhKsQDOYqBIPlnmN+nYHMExjtOVSxAqC8FyzvNRXMjM/AFrmZeikBSO/UZDbhmJxQF3QP4uwawmlzON41l2FVK0N9kA4R+gzrr4V+6sIDVUQZDCcVtvdKPL9P4qUDAgfHFLpGJEaSgC2Utyg19zuDBmXPh8mLK31VoCTyFYjSCqDyIaRbeELeLLiko7IWxZG5h23xzKRbQmuEsuWrixoJEctdq728hWFhPWFpM8PCeoY5NXSICy/zynW10JewqpAOvd/1QcLZ8znOns8BuPsQD4wpdA5L7OqX6BxW2NknwZh7Lnb1SzieMukdVxCeFbClZxDURG/N4oDpbUbOFG9pBVDBHIBUQF2AUBNwH3htwBVeqRQaQoQVLQxp4ZJNa9t49u8saSIYjGALhbogHfbfyCzeZNAFLNOVacmGCd7XzH+fW0uYW8vx7vn8kL8bSysQEYRU2D2gskLd0ScxGFcIGcD+MYU9QxIWJ7w9InFgTMFkQFIAA3EF0hxAZX4W8oQzZAKNIbeYxOSuRa8JMC++JJw5h8FgQMoBagLAwnqGlHCtweGEX8PfiFqEsbTLF6ydzdA5LDGWcoebEgE7+iRSAmgKcwgJDCUVGr1y5VhKoW985ir7it8MlIn3Dowp7B3JWesn9zgTmGGT5+K9gEFoClE2dz+nhtAazVXmLW9mWNjAsKzJ/ZoJAfIPQWEIoIGS7/ubEHJhYnhwYEyhc0ji9QGJziGJnf0y+1x6YwoHxlS2pmAgoZByVFEuyD0fLrGovHJmi1ei+S9P8tzwS0bEZBMfVE2AJiX/lAKGkyrrQWxLKDgHcz/wyO4cYVQXJCyoY2irIaybw7F+HseqFob6UI4XKCQBNaZO6DMkYL6iHU4obO+TeO5tgc0HBLqzJKDKCnN+3G4wgslyxiDIgZBBRcnAQ84KZnbnom/qAI72QWXn1inANIB8dZGfBkzZwLYeiVe7FR7Y6cDihDk1Lq9w3okcFy4ysLSZ5dJYBWlAjaPf6SfzhD7zWHb1Szz+poM/7nHTgAfGFNIFacCoSSDr0DRg9mzkcQi+F2qFsrQDG9V80Iq9LiQlOAFh01UQmUKg/rjCY286eHi3g/pgGqe0cVy65B2UAQO0LjhMJWjmPuWlATNC/8hugVe6BYaTuUIgdww5TSgEkoczIroIQCuA4/IsVM57CAQoWwr8zF4HT+5xlcHJszmuW2PgvBMNzK2lrDLw44Sfcrn5+WnUfaMKf9zj4K6tDrYcdIU+UwrcHKasoOv+gKqaCARfdQOqgjgxYhJqrJwy+FOng5YIYVkzx1+uNXD1SeYhzUAzOTzIbwZi5Objf7XNxu2vOni9X6BvPNcM1ORldqRyyToNXQpcsQw1ANRYrmeQsIHn3nbwVKeDf3vBxtfPt3Beu5G1dGIGhgYZV5+z3DzEP77l4O+fTOOVA7l24IZQztJX6gpy7QFoTKoM4E33iVpupmB7r8A1dyVxchvD+1cZuOYkEy0RmlGhQb6r3zeucPc2G7/e7mBLtwRIoSmcGwgitNBrBVAt3IFUrisLAFsPSjz/dgo/ed7GR08xccO7TEQtd0gmr9KwQHlTgg3mVuT95HkbP3/FRueQRMgkRCwAIG3pdRoQVcvSZsKDsOGmqgbjCl97LIU/vOngJ1cG0d7oxgXVNjo783kMAt4alLjh/iSefEugMUxo8Sy+1IKvOYCZxhUYDJhTS3hhn8DF/xnHVcsN/O25AcyK+n8seAaZz9ETU/jff0rhvp0OBuMKc2rdz6gtvvYAZmx6VnlDRaIWYTwN/NsLNh7ZLfDdSwJ473Ij29XoR24gM63HYMADOx18+dEU9gy5+wCiFiGtmXzoseAaE1zkzPacj/wqgR88nQan3JYdXxJ9BPzg6TQ+8qtEdutRhvXX0B5AcZNYFfWZx+b92MKtTwcHvvZYEjt7Bb56fgALG5hvQoLM++wckvj2kyn8YovtjT5XOn9fks1ASnsA1cgPzIoQ7tpq48JbxrGlW2Q37/pB+Ld0C1x4yzju2mpjVoR0tZ4OATSOFrYEmiOEoYTC1XfGsXGP467ZkpUbxhgM2LjHwdV3xjGUUGiOEGxN8mkFcExpQH3BdoCIQRhLAFfeFscdW2zwCvQEMvULd2yxceVtcYwl3PdtO/oZluWSOgtQtXAUYHAgwgif/m0CSgHXrzUrhhPIvI/fdjj41L0J1AS8ASv6YZbP+9IhwMwon41ahL+6L4E7ttgVwQlkhP+OLTY+8Zuc8Ot4X4cAGiVSAjUW4VP3JnDPa9OrBDLCf882G5+6NwGTQQs/dBpQlwKXQQmEDcKNDyaxtJnh5DZe9kaiTBXjlm6BGx9IImy4+X1dzouqLQXWHkAFKQGLu1ON//z2OHb0yuyEonL9+0TAjl6JP789jpTjvh9t+XUIoIHypdxCpttO+7kHkpAyNzizHAM8pAQ+90ASfeMKIVNX9ukQYIZOBJpO2AJoCBKe3uPgm39I4e8vDLhxOZU+1//1x1N4eo877UhX9+kQQGMai4Uaw4SbnkplScFSWeOM8N/zmo2bnkqhMayLfLQHoFnAikDIAG58MIHT53IsaGBTTgpmfl/nkMSNDyYQMnTVRmUtBtEeAGYyKRgwgOG4wlceSR4yC3+qQjMC8JVHkhiOKwQMTfppD2DK/dmyK7WqgSPcTbkP7rDx/F4H75pvQMip2VSc+T3P73Xw4A4b9UGCo+N+zQFoVN45MBjwpYeTGIwrd6vRcR4O5aX8BuMKX3o4CYNp3QydBtSo1FAgahE2dQl85r4EGB2/sCpvGtFn7ktgU5dA1CLt+usQoPQRgMZxtBBH3VDg2S4HZy0wjnnAaObvPdvluv7NUc36awWgkwAVD1IuJ3D7yzbOWnD8j+32l204wv29+rnM3OWgOgSAf6oEawKEh3c66B9XbihwlIKrvLRf/7jCwzsd1ARIV/tpDkDDL5OGLQ4cHJP4+eY0CEefspNe2u/nm9M4OCZh8Rk5plFDhwA+9QKkSwjevCmNj5xqoTlKR1wcJJW7q7AvpnDzpjSiFrljyPQz0WlADf94AUED6BqW+PYTR1cclCn6+fYTSXQNSwQNbf01yqQA9Hi3qbscBdQGCfdut3FwTIKzwwuy8lZ1HxyTuHe7jdogwVH6Xlb6pT0AjaLCbDKgP6bw6gGRJQgPRyACwKsHBPpjCibT1l+jnByAVABT+tRNFQiQSuHBDgeXLjMPu3U48/0HOxzIzDPQj0IvBtEeAPxbHRggPNCRRm9Mgr9DSlB5hT+9MYkHOtKIBnTVn4ZWAFWREuwZU3jyjXcOAzL//ck3BHrGlE79aWgFUDWRAAEP7HCLrSdLBWb++wM77MOGChqaA9AjweCfmoCwRXj6LQe9MYnWKMt2+RVW/vXGJJ5+y0HYy/1rD8Af80D0YhCNw4YBB0Yl/jBJGJD58x/eEDgwqiv/NLQCqL4HSMADHcXDgKz732GXdb+Ahg4BdClwGSAlELEIz7zloGdMYlZNLgzIuP89YxLPvOUgYpG74EM/A/+MBKyObkCDlPY0ShcGeBV+m/eJbIow/+vmfcJt/NHFP/Adw0vE/KsAYjGFUKNhd78wAJHcQ0YAUNr+lOKcCAVs6hIT6nsyXzd1CYgCclCjorW6AjNIpmLjdtdzewCYiCeUH0MABYAw0pVSUiYUMSjSCmDKwwC4ZOCmLscd9OkJOic3U7Cpy3FXfGnv309anSCEFL3bYq6RHhelenxGWSIa4YwcYpo0powHCHDCm30SQwmF5kiuRXgorvBmn0SA6/jfR/G/AhgpJWNQwgZC5LcQIEf3BRsIQFqmhncTYzoEKBEPYHCgf1xiz6DIrvgGgD2DAv3jEoZO//mpz0OREYCyk/vstx4fRDBoYHxcFRmuT5XmARTy/ApJUgBIJYa7vWogHYmWKBWYEgpv9kucPs8NIwHCm/0SKaEQIb3o008eABEBItENwEEoyJEsmkNTlUwCem94SAIwnO6Xt0s7IcrBas7Q5kAICezqm0gE7uoTEHKKTIVGWUcBiVjvVgAOEC5pAr20HAAlJAAzueP+t4NrPjIGM1QPkVYgzUlPeRjAgB29ru/PvaqfHb3SXfqhazD8JP9MOTZk/+uvAzCQTJZ0XohR0uE/8bhEoM5wDjzfJ+z4Lh5uOEPJtATA9ZPGlLYHm5ywZ0AgYSsEDELSVtgzIGBylxTU8u+TFCA3mUqNjia2P/gGABM0JFDCMjpWohGGOSUQrAeSyTji/S+BcU0ElnB9WM+YQlq4nEDSAQ6OetN/9C3ySywnyQxCpsd3OjvvPYBAnYl4XBYp76jIEEB54ajKS1ErpGwBgNsHt77MZ60GlK4KLBUP4EhgLKVQF3S7/rK7A3QI4J8UIBlQ8f6XASQRrIsgNVL4BFUlk4AThR+QngsTSL76n1tkfHgARoB5NLXGFM8J7BuT2NUnvfhfoEfP/vebGmewE8re99zTAAzPeOZkqQSeACvxRHOFREKitsVw3tp4QCUGnyEzBJSn1RkzMR0Y4LnV4jr15ystLmEGmUyM7B1/+n+/AgQCSHY7RdPrPikEktkrxQQAJXo2PwYlAaV0GIDSrA8biLvnw+A6/eczSDKDULGeP2Jw7xBqW9kEGSpRIGeUwPLTIYogNeogEAgl/vCPT/GFF+xjgbq5yo4rkO5Sn8qmoLQDbN0vcOUqE/0xld38o0MAXzxBrpIxkdzxq/sBGEiPOUWEX/mpFDjvjScEAi3M7tveJ4f3PggzmOEJNKb6gXpPdGu3gC10F6BP/H9BVpRkvP+VxJPf3oJAbQDJYecd4n9V6e3A+WSgS2SkxhwAlv3KbQ+q5JgN4joMKAFskesG1PARi8sMOAe3/gZAEoE6lZWbEjdylioLUMgDCKRGHFhNgfgLP94mRt5+lIK1BCU1GTiFN97kwMv7HMBrEdbwC/kXZjJ2sCv12P94CJYVxmifnWc8S2L5S1kKnF8PkO/CCJBjAwGW3nLrf/Bz/+4SgHMoHQlMXeClID3qf8+AACelawAq/rlJRTzAnH3P32r37R5ATXMI6f5i6T/llyxAobYSeV6ADSsaSDz1gy1iuOv3FKxl2gvAlA8IAYDOQekWAulb4gPr3901+tDnfwurJoKxMduTGVGOLAAr0zJgkb3ItoEAS2y59T9ketxW5NopvQ32+C6hgIBJ2NHjkn8hK9cDoK9KvZSCESJ7/4u3YrhzCAELQMopEv8rPw4FVQUfwvMCRm1EI4H00ze9Ig5u/QUF6xmkkPo0HP9FCnAcN/5iei97hWtsISlQx+XQnldjv/rw3bAaIxgbSBex/iUrAirHVOBDPQDAgT2ehlUTjD/xpZ/KWO8+MiMMSpMBU0EmB0xgMKGwu08gYJCuAajUJ8VNpZy0k9x25/eRjqUBWwKw3RkAWVkpSQtwuTkAOSEbAAikUjZgkdP5dG+q49f/CDIIRPqoTsFosIFxhW3dAinH2w+gb00lEn+SQnVcHNj8n8nH/9eziDQEkR5LlTP2L7cHUOgFCKQHUog0RBK/u+H34uArv6RQA4cSmhA8zl6AhA3EUgoBQ1cAViZLKyQF6rkc7OwY/eX7/xVmQwROPOVZ/smsP/zmAUzmBQjvQ7pMpz2egtkQHPnFJd+RQ50dZNVzCM0HHM/FyX2ojtD3ouIuKRV4gGQ6PhZ/+jtfRrwvAbI9jxhOua0/UPrJPFTwOnMxAAQhCIZhIJl0pBN7hS88/3JwMwDpQI8NO7a7LRUglcK2bqm7ASutUIOYIDPE0zt/843kE1/diEhDEMnRRF7sn7lkqdp/y60AChUB5XkeriIQacCsDYp9zxxkdXP2miec+R5IoaCkVgLHsiVIArUhQk9MwZG6F6CCSBpB0UbD6Xr6Z+N3XvVThFtqEB+Ie8KfLggBZLnGuPAyCb8qogRy3oBMKoTrI07Hvbt427oxo3n5uZCOBBTTTa1HZ2Q4Af0xlU0HalREr4+gYCMXB7fcP/azM7+DcEsQ8b6kJ/h2AfsvyxH7T7cHUBgSEOykQrg5Yr96y7NG+wU1fNaKdUiNO+4ocX2UjwZCQt+yyiH9HIo0G3Joz0ujP1n5WZhhjlQiDYhUngIo5vqXJYCbLgVABSSkpwQcINwYSb/0k03W0vedwJraVyAdl4AifaCPLhTQqBDLH2kx5Mi+neMPfeJzcqwnCZCATCYLLL9dpGgO1RICHGkoQIAAbIdgBozUiz9+wlz63gZeO3c1pCM1J6Dhq1hMKUHBRi6H974Q++2HPi/2bOwHtwj2eKHrbxdh/lFtHsBkWYHCSUKuEpBgMGus9Is/epSfcPo4bznpHKUkQdhSTxHSqPTuPoAkizRzu3vrA2P/tuJGNfJ2EmaEYI8nCtx+uyD1V/b1udOpAN65p02mgHBzxH7llpdY84r9rHHJu1ggGoCdECCmh4loVGSRD4wgIyPExNvP/yx2y7u+BzPMwC3hWX77HYRfTYcS4NM0wr7YV3WIgrDjCqGmiP3a/9tCPLCZt560hqItzbDjwuUFdEigUSkuvxQUrOdKpMbs3Q9+c/zO9/wMZjgA27a9mD9d4PqL6XT9p1MBFOMDJh8s4iQkQk1R582H94vOR39vzDuvmdXNWw4lCdLW3oDGNFt9KUEMFG5mcqz7teSfvvH55BNffgqhphqkRpOuK3uI8DsFdf/Ttr5lOi1oYWUg8xSSAcDMuywAFsxwEHacADjh9//yKvPEC/+aQg1NKj6goKDAtCLQKHesD0nBOq7SCSn7tt069stL/wOJsThCTRYSA/E8oT8S4cd0KAA+zQrgSEaLua+lrQCTYAQC9vY7tzh9O/9otq6po0jLUjIjBCclAaU3D2uUQfDdST4UqGEi1r059cq//138tx++B45iMIOEVLa8N51X5WdPR7NPJXsAhTwAy/vKvcv0PAJrglcQrgsiPiIB2KHLfnyesfiKj7DorNNBHMrdpSa9AiKtDDSmrIUXgCIzzMGDkPG+PXL/83eM333VfQBSCNUGkBgtluKzJ+n0k9Mt/KiQerFDS4MnKgGjSFhgwjQtqFAAzmgCgBW6/OazjfZLPsyis04HN6FSY4B03Mn4RDo80Di2mX1QCsQ4WVGAGZDjfXucAy/cmXjo4w8j1jcEwwiDLAd2tqU3XfA1v8qvooQfFVQwWqQoCNxTBEYBN5CvDAyY4QCUMuAkkp4iOIvPP/cyFpl1LgXrwxBpKHsc7vBRAgCmwwSNSQQ+bzwlMZghIiMElRqVMjXykuh59ZHEQx9/ArH+QQAhhGoVEqOpItY+390vrPGvGOFHhVWM0yTkYL4iMApCg4wi4DDrAlDjHI6TBMCsFdcsNE755EW8acm5ZNWspGA9gxJQTtItw1YQ3v0n73+kC2lnyuykjOgpb5Kicg0Dt4iMIMAtqPQ4VHq0U8W6n3W23f1o8rnvdQBI5gQ/kQZsp4ibn5/jFwWWX1WS8KMCW0aoYFhJfkiQnyXIVwITPQSzzoJSHM6o8NywsHna55aYy648ndfNO5kCDcthhmaREXJlXTpQ0gGk7RUi2no2YTXn65nBQAQQB3ELIO6eAycFmRodU6nR3Sp2cKuz76kXUpu+sw3J2DAAA4ZhwgxLT/ALLXy+0DuTDPasOOFHhfaMFesYZEW4gXyiMP+rqwxM04BRayIxQoCTeWAmGpc0Blb/5ULWvKqd1c9fykJNC0C8BUa4CVIQBWoimjKo2oEckKmRFEBpiHQC0n5bpUb75Fj366Jv65vOjnv3iAObejxLzwFYCDUCTtKBHbcLBN4p4uZnXqsCqy9LOdm32hTA4UKCyRSBUfA1d5lhA0bQhG0TnDGZ98AIgAEeqOGzT41AEedLr1gIzjmkdgRQXS2SirMA0m8/uR+xgZgY2y8w2jmYJ7Tu2TFCHGZIwUkK2LbtbVsUkwi6KHJNttEHlbijqdLjXZokXcgKiEJ+BJf3cyZzvYMQAxSDnQCcRH4Ntu2Te6NxbHsrjWwbuhFiME0FGIAjBBAXsG1xyBTrd77kO7j7qlIFHz475MW8gUKPgBUoBFZEAeR/L6/2wCSYmddh5nFF5NN7pTGZ0BEpIO4qexvSm8VfuMOyUKALBV0U+TnlJ6vv10M9+TShQxUBFVEGbJKfYwW/a7IJRhrVoQyKzus9jBIo9udiaT3pF8H3q1UrZpWp6MRhV/DpKASfHUb4tTLwtwfwTkqgmAJQRQS+mLWHX9z9alAAR+oRFFMIhxN8pq3/jPcCJnst8yz8O8X3Cj63qNWgCA6nEOiQWYTF3X+tBKrbGygU4kJXvtjrqhH8ajzgdITeQTFFAR3/z1gvYLLXxb4Hv7r6M0EBHKkymEwBHOmgEg1/KwA6jECrI+APqlJQMAOUwZEoBw1NEKJaBR6a2Z70M2sFMNPrBGaAwOtDr++HxgwTcg0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NjSrA/wc0vimz4k3juQAAAABJRU5ErkJggmljMDkAAHi7iVBORw0KGgoAAAANSUhEUgAAAgAAAAIACAYAAAD0eNT6AAB4eklEQVR42u29eZycVZ3v/znnPE8tXb1m30MgArIvGgIiqyA4DqgIqIjihjOuM+p1RufOde78vHfc7szoOCM4IoqCCAKCgIgQ9p2wE5aEhOyEJL13V9XzPOec3x+nqru6UlVdnfRSVf15v1716q3Sqa5n+X6+O0AIIYQQQgghhBBCCCGEEEIIIYQQQgghhBBCCCGEEEIIIYQQQgghhBBCCCGEEEIIIYQQQgghhBBCCCGEEEIIIYQQQgghhBBCCCGEEEIIIYQQQgghhBBCCCGEEEIIIYQQQgghhBBCCCGEEEIIIYQQQgghhBBCCCGEEEIIIYQQQgghhBBCCCGEEEIIIYQQQgghhBBCCCGEEEIIIYQQQgghhBBCCCGEEEIIIYQQQgghhBBCCCGEEEIIIYQQQgghhBBCCCGEEEIIIaSeEHwLCM8lQuoSy7eA8KZNeC4QQiggCG/6hMebEEJhQGgQeGx5fhBCo05hQHiD57Gs4vmiwgXPc4aQ+jP2YhQjbikGaDRIYx47sZc/5/lBSGNHAGzBtW73wchTEFAAkBo5XqLoc1vm++N5XvBcIqT2w/rVRgDsPogCigEKADKJx6iUwR/N2Iuq/p/ly0d+Pwx5zhBSy/j+sAFet66cMbdVioCxPJ9igAKATNKxqWTURZWGXmD5cmfUtRazDzhHAYAJM7nn7MLuh2/J8JwhpG4jA97MEz7pAYD0ExYAvP5NZvuu582QWFi3zlYpAgq/LhYVFAMUAGSSjf5oBn/k50uX5gz98cqELWL3wz+PAEQFF3JY/B/O/ej35yRakxIDgwCaYKOA5wwhtXwT8WI27UU22eGJjT/4QheAbImnxQEYAJh5wjkJ6S+yQ8JgWBTk7wu2yqhAtWKAQoACgOxlPr6S0S/43nKBpaHArMPlzPgclTP2usjQx5d+68cdmR3SJGVrsnnley+RnoppbYRQnhFaJ0Q8eYkQImaN5dlCSP3cUYyMCWkGoset7z+I7GDcWhOpFimD7Z2P242rHxzo64wHPV3Rjl//jzeLhUFeFOx87RYNpSw2bjRViAA7RjFAIUABwPcf1eX1Rzf+S5cKtB2oZjYvlrsf/nmYu8Dy6j+57Bv/3SoGYvHU2875tEy1GpvNnihTsRUmCy1gfdXqpYQYeXnqwRIVBYSQmsdaQMbcYwgJ6F7AGNMjhFXW2KzJDPzca/OD7JY3n7Q96x4YfPH52Karv7I99y98AGLmCefEAWD3pqcibNliShj4UtGAatMEFAIUAHzfiwx8/uKpLASWLhVz2w5UpqNd7Lzv+rDA4Dcd/B9/TsJbflJyyZIjo97sCSoRW2kCA6/VbxECMIF7iNz/ZnQUQRRcjBZCAIqHi5D6vMtYF+Y3sDZ3zxBWCOELpYbuMKoJgHLCwAI9VoeRDYJfWJje/mfu/GWmc+vgG1d+eWeBIPBmnnCOlxMDFrlUQpHhrxQJoBCgAOD7XcHbLyUACr8v5x5xxh5Gf9HfXjej+a0rT04uXHhk1BueoJriK2xg2rw2CZPJGXuMMPRSAHK4SVDwfCBkeoQHbGGgD4ATBlI5UZACrAF0vx6w1qZtkP2llaanf/2dV73+jx/cDiAAEMuJAbV767MhNm60oxh8W0EoUAhQANDwV/T2Fy2SM5cc4+1++DED7BgAgEXfum5G64ITTozPbj/J6MRHhVJzVQowWWfwYTSstSFEgbGnoSeEVBAGFlYDAlJ53pAg0IANdb/O6MessKuyz93ym1f/zwVb82JgxoqzEn5G6x3P/dnkogK2hLEvlyqgEKAAmDbvcTWFfHlBIOcecYYME0p1Pn5HNuftq0N+seUv4i05o+85o6/7AasjWItQCEiX8XOuPQ8DIWRfBYGQnicTgJA5MZDVj1op7um96+prNl7+idfdP5rdPPOE48Uo9QIUAhQA09bwlzL0e37viDMUtj8jsHNnPwAs/eyV+7WeftFFAjhZJfwzZAzQA4DVkbXWagGh6N0TQiZYERhYWCE9T8ZdkWHYE+4WfvbKsLfngTWXLLoNLq0Qn7HirHjn5mcjbN9uCoz83ggBigAKgLp8T0fr0Rd7PI44QxYYfvXWn299b6y99UQbJS7xW71ZJgBMOrIW0AKg0SeETKkYkJ7nqZRLO+pM+GcL3Nd799VX56ICsRkrzkrshRDAPu4nIBQANeH1l8v1F34uccjJCjvXIGf4Y0de13MGYskvS+GfIePO2zdRFEFACAhW5xNCakYL5B0SmfSEjAFRb9Rl0v2XdT55639t/Y+Lt4xRCIzHGGJCATDlXn85o1/O8PtH/Kbz3SLZ/CUpvDMgBcxAZK2gt08IqYc5xFbDWis931NNQNTnhMDuR2/6ybaffHIzKqcGykUFKAIoAOoy5C/Kfj53roIxYsjw/7rz3SJVbPitFUJKvs2EkHqMCkjPGxYCmZFCAIcc4mPNGl1GBJgxjiAmFABTbvgr9fBL97P5quPYE/2u1ddnANjDruk5QyWTX84bfj0QWdDwE0IaVggMXrb7nht+su0Xn9yC2bNTmH0IsOa+qMj7L5USYG0ABUDdef1DjxnLV/id6x7XAAaWfPO++W2HrfiZ15J4jzWAGaTHTwhpfCEgk4DNRl3Z3dv++qXPLL0egG078ty2nmdvDgpmCNgygkCMUjhIKAAm5T0rfv9k0fdl4edtJ58b67nv5m7MWNF6+A//9Pci1vxXMuF15Cr6jRAs7COETAMhIBBJpXzhAdZGd+mu7n974ZNzbsfsQ5pntDXLznWPBwVG3aDyHAEKAQqAKTX+pav6C73+rh6L3a/0HXJl91lea+Lv/Jb4KWGPhdWRocdPCJmWXYTWQrX4Qg9EBuHgd5774mnfQ9fqnrYT/6Kj58HbskXGP//5WDcTEgqACQ/572H4AaBj/2NjXetX96Dj2LYj/mPV1+E3/b1KeTLqi0Ih4LGqnxAyrXWAsVpIIfwOJcP+4J6oJ/29NZ9ovwMzD2qB7LTYuXO0IkGKAAqAKTf+xQ85Y/ly1bluXe9bL999tj8z9XW/JX5K2KWNNdYKyXA/IYQUBARCr9nz9UBkTDD4nRf+8ZzvY+N9gx37H5vsWr86KDD6Y2kZpAigAJiQkL8okfcXAETH/sfGuhJpjTVrMm/96cYPxGYu+I30PRn1R6GQwufbSggh5aIBELGZnszuGLyz58k7Ltn07+ftbDvy5OaeZ+8L4UYMo0RqQIyhbZBQAIyr8R/62Lb0yFjPxme7MfeM1BE/vOV6lUycrTORsdpaISW9fkIIGS0WYKBV0vNgou70ts2XvvLF/a+vMiXASMAYYPHZ3hf7yaKPqnXl+Ymejc92v/XyN88+4j9vuU01J86OBiMDA0HjTwghVd1+hZDC0+lQQ3jt8dmLf3P4r7r+L1KzPezcqTuOfVes6N5bbsqqoLPLCMB4Gn9ZJJ7c1zNnerAdAp3reg/68esfTM5feJ3wPRH1h5qGnxBC9hJjLKSw/kxPBjvTdz7/kZUfAJ4bbFt6ZFvPxmfzdQGl0gLl6gIYCWAEYEzGXxT18wsAauh7M5b72L07QvM8deivuv5vfNbCa61RIhqIIhp/QgjZFwslBQAR7owCryV55pG/e+y2t17+5lk9G5/tbjv8L+IF9+NyEYFKrdo0eHwLRl3gI0pEANyJtny5h56YwezZOPwfbr8hNqfpzHB3ZGAh2N5HCCEYxwJBo71mX9lQ2/SWjRe88uUDftd6yJkzetfcmS3I/5sqxgmzLoARgDEb/8J5/qJj/2N9rFsXYP5Ce/g3b7vR72g6M9wZBjT+hBAyATdpKVU0EEXWCJtcvPS3B/37+vN719zZ2bb0SL8gKitLtWRXubWVEYBp/B5UM9zHfVx6pI+Nzw4sufSGWS0nvPuq2OzUu8LuMBJSenw7CSFkQpsEjFBCwLMm3L3tIy9duvQmzDwoAbtToLMzLNEVMJalQowA0Pjv6fHnP7YecmYcG5/tPuD7L7+//cy/fMlrSb0r7I40jT8hhExKk4C0kYGNIOJzlvz28GvSv8esgwA1z2DGcr9EFECWuNcLOsHT+4+vVCBSUgS0HnJmvHfNnZ0H/fv68xNLlv7GGqlMlpX+hBAyRdsFjd/mqaBz4M8vfv/978f2rQI6kOhcFxXUBJSKCLA7YBoLAFEhClBaPbqwf/dBP3z9g4lFi35rIwijDVf3EkLIFI8Q9ts8P+ga+POL33v/+/Hcny1mzPDQ2RmVWCJUasXwtC0KVBQAJYtFRoT925Ye6WfRnjno2/e8P75w8bWIIK02VghB408IIVOaEYDS6SiKdSTfMvOYD7zdb55/s8xoZKNdQDpdyriLgu+VaxsEawAaP+9f6sAXFfwt9Xs2PpttWrKoIzZr4VWwSlmtLWj8CSGkVjoEvKg7CBLzUme0nnDe3/U8e3N38+LTEgX3clliBoCY7lHx6aZ4ys30L1nwh479PUjfYNZMHPaPf/qdSjW/S6dDKwQ3+RFCCGosFwAptPRlNr3h5U+9+rVDf9ty8Okz+16+O1tUD2CqmBNgGQGYnsbfPWbMUOhaH2HuPHvoP9xxo9/RfKYeDEDjTwghtblCAMYoq5FKLjvo6gP/9eUL+l6+ezeWHO6XKe7GdE8BCEzfoj9Z1vufMUO1LTxeNR12qprx7s/8Jjar9V1hd8A+f0IIqYs5AVLAg8lsXnfRq//vklva5ECiZ9PzYc77LxUBqDQrgBGABq34LxX6l6lFJyd6nr+tq+2dH/67xILWd0XdQUDjTwghdTInQGsLq1R83rJfNC07oL1n0/NZtC31qqwHmDYRATWNK/5RdDJIALJlwcGx/nUPdh7w3RcvSC5a+m09YAQAj+N9CSGkftIBVmutEjGv7bB3Hblz26rfdWABMuiSyGRKjX23BR+nTZS80Y1apSr/4vY/2bpoZax3y6N9B3zvmdOblx92qw2FslFkISSNPyGEoN4WCFntd/gqu6P3zjWfbPvL1kNWNveueTQoUQxopmNRoGLeP/fo6FCJ+QvRevB+su3kL/5cJuKLdSbUkBz0Qwgh9ZoO0FkT+S3Jt7Qc9b5Xt1/7j4+3LDi4JejbpXP3flvBuDe84ycwvfL+pQb9uND/wW/3+15+ou+Qn3XeFpvT8a6wN9RCsuKfEELqPQwAT2npCfSvffac9X9/zF0tC97e2rftiaCgKLA4AmAwDcYFK0yvvH/Jfv/m+QfG+19/vnP5/3n6w4mly76mB3QkBFj0RwghDRAGsJGxKu55Kta63Lx572+s8kU27AMyGVMsF6aTw9yIEYBKof89PP/WRYf4vVvW9Oz/nafObF5+5C0mskCkFfP+hBDSYPUArb4Kdnb/ec2nO96LJYensOl5XSIKUG53QMNFAeQ0zPsPPzo6pG2eL+Zf+oOO5LwDvyWU9GyoBY0/IYQ02rhgoaJ+Hfkz2s844LvPXAjRm8aCg8c6JEhQANRf9b8o4f2LVMfB8b6X797ddviFfx+bkzou6g8irvYlhJBGDQNoZUKY5KJDLk/ud8wsZKIQbUtVUY1YsRBo2Mi5bHCjX3bVb/P8A+MD6x/p3P/bj/6FP3/+X4XdUcSiP0IIaewwgAlDK+N+YtlHf34FOtdl0ZKScPVwosSQoHKjggUFQG3XMogSff/u67Y2pfy4nv/hH7QnFx76v6SnUlYbAXDYDyGENPiMIGWy2voz28884F+euhBb1gxgwcFekQBAmbQA2AVQX1X/eZEzdIBTC4+J972+f/fCv/rqPycWz/og5/wTQgimU0UgAGW95llnW99cPbj9qQEAEtmsKbIntuBr22hRANngo36LCwEV2paoge5XMol3pBf6HXM+GfUaww1/hBAy3VIBgfFa/ETHiZ/7LDZu7E7NODi+x0r4kTZSNloNgGpgASAL/saCTX9zPezcEr7lfz32a785dajJhhaC0/4IIWRaaQALYSJrvdbUManDz3ruzeevWdOSmJMM+naVavUr1wYoGAGovYl/pSIBsmXBwR62m779//e9Z8Rmtp+pM5Gh8SeEkGm6MCgyVvpeU3Lh4f+AdeuUNZFE5XZAyRqA+mj3GznrH1CxVLsX9K+L5l38H5fLRGyRDiMLISgACCGYmtX1mAYT52t7V4AJjPZS8SWJQ05+audtt77QPH9WMujfXbwUSDTiQD3ZQJX/okIUQDTPP9DrfyPsW/qtu8/yWpuO1+nICsGef0LIFBl/ADEFcOzYVB8HA0hpm5as+BowIgogS8wHAIsAazf0jzIiQLqDulE1LVnxNSGltdZYnvqEkKlACaA/AM5/i8T8JoGsZiBgCoMASqcj67U2Hb/0W3efNbBD9zbPP9ArEVGu1BYoKABqbwiQACCb5x/oDewI+pZ+6+530/snhNQCBoAvnRggU52KMVYMRQE2eiVqAWSFKHPdigDZIN5/qQ6AoZG/7mBuofdPCKmdm69wAoDUUhQgdfzSb9195sCOoK953nK/gvHnKOAaEgSiTK+maJ633M95/2d6rSl6/4SQKb9hZTWwMAV84ACJN9MWHqMANRIFELkowBZlrak0GRCNMCLYa+AOAJf7t0YAW2TTkrd/TUBYa7Rl4T8hZKrRBpiVBFbMEfjjRoOWWK4rgEyRQRFKD4TGb206fun/vPvMjd8+/bbU3P3bBnasNznbkv+oC74W9bwiWDZA5X+plb8y5/17AzvW9y39p/vP8VpSx+t0SO+fEFITN7LQAE0ecNw8gUzEboAa6QiwgLRNy1b8j9aVZ6aEkLZEFECOsiiIAmAKBwANHSQT71AAgvicg06RMWkttOEpTgippZvvYMQ1ZLVjWKQ0GSNkLHasals+v/+NdSFaWsbaDigoACa/718W/E0SLS1ycOMTQcd5Xz/Yb247Tw8YIUDvnxBSG+RLken511YewCCKVHNMzn7vNz6BlednU7OWemNoB2QEYIqEwIhH04yDfRx7bN/Md176Qa8tPtPoMIKgziaEoGaGAJGa3BGgTBrKa571ycTONbMGNryui6IApYoD67IYUNZ55X+pDgABQIj0LovVqxN+atapNnCNHjy1CSFTjZJAf9YNAQKArLYcAlRjTYFWh0amvOa5F/zb24H+gVRyljeKxy/YBTB5Xn/FBUCpufu74r9v3fs+1dZ2cpQODSAUK2wJIbUw/9/YkREAa4cfpAaOkTHWE3E/ecDKr7ccfPp9pmuDzTmYtoIDapkCmPrtf9LGOxRO/rhJzDnwVOHDWmtY/EcIqb1FQKDRr9liwLSBiMWPiR945JKBHesjNDePVgdQd8WAss5z/nsKgJYWMbhpdYS1D86Wyfb3mUErBASzbYSQmrqp5Yv/uBCoRosBbRh5LTHZfsrnzgHQ2zTjIL/MvBmwC2Bq0gB7DAHK5WrSSz/9sxNl0m+3OjIs/iOE1NKNTFs3DRAAzn+LwrwUuBCoFmsBQiivZebpzctP7BCZTjPKToC66wqQdT76d49ogIm3K6w8XyfmvOV0mfQ8a9n7TwipHUIDtMeBlfPcbSvhMQJQo4ZG2qyBjDWdkDhkxaKBNzfoojSAHEOdGgXAOE7+K5n7R3OzTG9+OsSmh2bJphnnmgEL9v4TQmrphhZZoD0BHDePI8lrPAAgjAkj1RpDLg3Qk+x4i1/GCWUb4BTtARh+NM1WALL7XXrtKS78rxn+J4TU3M3Lwk0ALNwMSGo4DdA66/Smd140SwY9xcWA5RzTuogCyDo1+ChViJGMzfUADPodS45WTZ5nrdY8gQkhtWVSgHTB+F/LccA1ngYAhJdYqTc+nhzYsd6WWD0P1OlUQFmHW/9Kf97cLNOdr+nkyvPnqkTr0SZtISwUbO4K44MPPviY4ocAkAmBlXMF4hKIDBCX7utMmLuZ8X2qnQcAayMjY0rPv+SKdwAIkZypShj/SguCLAXAxBYASlgrMbjTmK1PJ0Qs9Q4bCE7/I4TU1g1XAOkQePs8gZhyBYEx5b5Oh0wF1GQKwGitUl7Cb190DICBXKS52ry/YApg/AsC91RbTpUF8z/x8xNkXGqLiNX/hJCaw5MY2kuav6lp475PatLwKJO2UKn2o5Irz5+T7tpQaihQOXtla7kOQNbZ1D+UqwdIxucpAAN++6JjVMpLWKM1CwAJIbV0Qws0MDcFfOggNTQECHBfz025n/OmVYuFgAIilnqH2fp0AoM7DawtrAGQZewSdwFM0Oz/kSmAVEqmu9br5NHvmi1S7UfptAUAxQmbhJBaQsP1/ceLmpPjyn2/LxweOE9QQ2ObIyMSUs/9+H8fv+nbp96K5MwkBgZ0kT2SuUNc2OwhWAMwcbP/h7sBBndp5XvtMp46kdv/CCGowS2AvVngvOUSCc8VAErhPiY89/3erHseqa15ANZERia9hD9r2QkAMsl4myqTAqirWQBeHS8BGv7chWPgtS/1hbVpAC2U0ISQ2nIjnbfS6pduFG/1cx6ZZQig9o6dACJAGKuB2d4oTqkoyv2X+pwRgH0o/htRgJHsOMAD0D/j7K9/VLXEm40OI+b/0RAV0zyIpJHy//NSwHlvUUMRgcKP5+V2ArAOoCZ3AykzaOG1z7uo+cRTlqS3Ph8ilZJFBeko0wLILoBx8vZtqTfaGi0BaBEZAwlB+dwYN8zByC1N4c2QNAIGQNJz4f5SJDz3c7Yv1fBdySAWvvJoNtd6LioUpnMdMMYlaFZRXUkAItO9I0q+ZeVM1Txrpc1aiPodcUxyBzej3bKU9ribnU4I6jz/31eU/y+8mRXWAfSxDqBGCwFDI5KeP/dTvzgBQAbJmbLMauC6EQFeHU8AdJdIU5PE4G4tZ544RyWSJ9jA5p5Hq4F6HpYSASvmSXRnLd5MW3hqeh9Ra1nW2gAlAGiJVW5xaokBlveumswBWBNprykZi8074B0AfpeItzZngLAKz79m6wDqrQvAllFaUmQHIhg7yHgxGmdYih3pKU1nwxFTnBJXzxGtrAb2bwPOP3Bk/r8wQgC4n+/f5p7Pw12TKQAYnR2osAOglJ1iCmAc+v9Lh1mslQCgOhYlrQBX/zbIzXJ+CrjwIInByEJN4zuhEkB/AFxwoML8lKBhqNPwf3cGOGd/5VJaprSLGBmgPe6e151hGqBW1bgQXhKYoQqGAZVaVFeudo0CYB8coeI3WyY69lcA+mae/fcf9loTTUYH7ABoEMPnS2AgpMGzcINiOCq2PtEWaI0DJy2SqDShJP/9kxZJtMbdvyM11gmQNvDb5n+o+biVCzPb1wRoaionAupiHbBXZ33/e77JQ5WYXhyAYPqsMSyeNkDKB46bJ/HHDQatsWl8Q7SuNWywcFscqZuIVmiA+U3AcfPFUI1LudoXwD1vfhPwxiDgs5qptpS4AQAZs1qoUQx/pVx/zdQByDqcAVCyUFBYw+ukQZAS6MkCzb7AyvkCmchO6wI4Y938+OPm8b1AHYb/e7LA2cvUUJi/Up4z//Ozlyn0sBugdktyrXFGf2QrYDXRAEYA9rIewJZYulAQATCWA7QapAMgAE5d4g5rb+Bio9Px2AoAgQFmJYFPHKrwqzXaDYkRriuA1D6RBdpy4X9ZhTcvhLsGTlokceWLGpHlPa0me9PDQVuFvQKLAPe9ALBcGqDgY5uC8mO8Uhph7LZrAVw5Xw7lT6f7zUbljMJAyFbAuhKzuel/bbHRw/+l0gBtMffvGQSovduUN3O/OEYuAQJGHwYkKAD2Xhzs+cY2NYnMGy+FqbevXOi1zf+QSRsICHYCNEAUIBNhqBhQ0OOoyniQ2rtraQN85yQPEi6VI6q40ZnczoDvnORBG/ACqKGlQEYHkdeaaJr57r/7MID+RPsyhdFT1hwFPI6RAbFH+D8SCkIyAtAgYW9thwXAYMhxwNyNgLrsYunKAictEjh9sRyTgMs/7/TFEictEujKYlq3wtZiOwCkFwdgqxgHzBTAOKQCbIU0QMGsNNIIFdMdCeCEBe7wnrBAoCPhvj/d74EUQ/UlYttjwBeP9mD3Io9vc3e0Lx7toT3G416bI4EgbL4YcE+bZKtMY1MAjGEccF2rLYKqeqbbY8AJC2ROAMihGyCm8VTEyAAr5wt0xJ0YIrVd+d+VBS49QuFtcwW0HbsHr4Q75982V+DSI5SLArAYoN50oGQXwMRsBRzx0QZGgHu00SgJb18C6RBoibuPvpy+x1XApUNCDaxcINEedyFh9oejpsOqYQQk1b7HJa11vyeMctaEB33qC3IsMOz5MwUwlYKA3n8Djkx97/4KzXFn+Jrj7uvpOBpVCCeAVs4T8JVriTQMBdd8tKYzA5y1n8BHD1Gui0Pu/fVgAXz0EIWz9hPozHAaZB0trquLbYCyTt/oYpnMeyIaaGTqYglR0AFw0uLpORo13w2xcoEcWo7EE722j1egXcTqK2/zkPL3bQh8flxcyne/z5e5tkCeBPXYuk4BgLH3+ZcqqBCMAjRoAWBuCVC+Zzrv7Rw3X2B+yv1cTMO5CIMhT/R6OH8j4x6/OMvDsXuZ+y9XC3DsXIFfnOUN/R88F1ArQwHFKMXrNS0MZJ2qLLGH588oAOo9/N8XAO9briDzI1GF+yjhvt8XTM9CqEKPj70utSvUAODnZ3k4aZFEZMavdU/lroOTFkn8/Cyv4kIhUhNzaurGSa2XLoDKr9MaXg4NUl/TEtszxCmF+77lXQYxxfehFnv+M5E7R9+5UMLY8ReqSrr6j3culGiJuf+PswGm9G5VTbFfTU8BBGq7C2BMIsHa4Qepz0r3pS3A+QepoRte4cfzD1L42XMaXVnAmyYV8MXnc2vcvQ/feUxjdpPzCsnUR2ey2n3+/ZNdz7+YgIFNomA2wPdP9vDpP0XI5uoNuAZt8q9JYxoj8izryDkU9aCoyN55N70B8LFDFTriI3Oc+dxqR9z9vHcapgHyIoARgNoz/qFx436vPMvDqYvl0DKfCZsEKYBTF0tceZYbExyaifv/yLgXBlIANPobSvZi45123v/Fh4z0/gsFAuB+vrTFPV9MIyMTU6wBqNVpf8YCvzh7OO8/0cZYFtQD/OJsD8ayO4R2a/q0AaJksQULAOsWXwG70s67b4uXrnDORwHaclGAXWn37xr97pHVwIIUcMHBil5/jd00hQAGAuCKdw8b/8nq0c9PhjxpkcQV7/YwEOTWCPPQTGX/f7mRwBQAVFoEZYqndqWBs5YJfPJwVbF4Kl8E9cnDFc5aJrArPT2KoBgBqL3joeFSVu97i8QpiyfX+BeLgFMWS7zvLRK9gXtdTAdMtu1hDQAhe13U1BoDvvo2D01e5aEp+ec3ee75rbF9G7KCOqwBAJwY4E1+anP+kQF+ebaHH5/uuV7/KbqLqtxwqB+f7uGXZ7sZAawJIBQABPUQ+t/aD3zpGIVj54qq+qbz/dDHzhX40jEKW/sbPxVQHOa64GCFBSmXHuB9fnKjVVFBwd/pS3LtflO4olnkXpexwOlLhgsDx3MGAaEAIGR8jb8E3hgALjxI4pLDlLthVXkmqlzo85LDFC48SOKNgdyyoGkCIwBTU3CUjnJT/iax4G9vCwMj414vV6USTIM5AAAHAdSV8X9zwOLc5QqXneFBirGF8kVOBDRJ4LIzPFgb4pZ1GnOaROOtyTV7KnSbbwY3lO+TFfIXcKmqH57mT3rB394UBl55locvrwoxGLpri7MCxtvOUAAQsnfGf9DinOUKl5/pQ8DdmMbqSeX/nQBw+Zk+ADSkCBDA0E2cTL5BDTRgjMV/nxXD8Qskkp4772p1I5+XM/QnL5Z45KI4Htlm8Jk7AkQQiCkOjiJMAZApmpOuBLCjyPjbfahaLowcXH6mj3OWK+wYtC4nKxpkE6B2mwDjRR4cUwATJ7g8CcRya6kjY3Hl2TGctmTY+Nf6ey9zNQFJDzhticSVZ8cQGYvujPu7PMm0AKEAIJi84qlQA72BxfuXK1w2Dsa/lAi47Ewf71+u0BtYhLr+i6CEANLaYuUC573lVyHbXFSAN/HxP08tgF1piy39Fu9cLHD1e2M4KdfmZ+tIeOWvi8i4VdpXvzeGdy4W2NJvsSttYcEiQYLGSgHYggepkRuqBfpDoD0BXHZKDO9aKoc82fG6mcrc/yMAXP5uH3dtVPjqvSG6M65lUIhh41lv5zMADIQj0x5xCRy3QODO1w1alGBudxy8fl+6eRQdCeDrKzwkFPDXR3tD0/48Wb/RDG2B4xdIrFwQw0+ejpDRwM+e0+jMALOSrsaBp9DY7QwFACEVPKneALDW4i8PUPjuyT7a4hPnReWXr1gA71oqcf+H4vi7+0L84TUNIQRaYsOjW1HHq4CNdV0AKxdI3PyaQaug4t2X91UKl+d/s9/i3cskvnC0h3cslCPe73r3lPNtglIAnzva3e6Pmy/x46cj/GmDwcykizCZ3FhjwggAIWO+yeTnog+EgBQWpyyW+MwRPk5e7G6oehJupnkj3xZ3KYEPb1b47+ci3L/FwFiBpOduhKpOowJ5mALY+/MUuZTUYAhktcV+rQJfONrDl451Hn++6l/Jxqm1yKcEdM7bf8dCiRMWxvCj1RGuXqPxeq9FXAkkvNxcDVvf1wehACATPHNZyVyeUQPdAdDsAwkPWDFf4NICw28Lb76TGIEAXDX0yYtjuG+zwU+fi/DcTotsNPx6PZUTDWbP0Hu9RAXI6Odrfox0bwBoY9GREHjnUokV8wUuPNhDRwJDIrVRZ0rkUwKFYvzLx3r42KEefvtyhMe3Wzy63aArbaGki5pJMXxtUA9QAIBFANNndVWptab5vefWAp1pV3E/Iylw6mKBvz7aw2GzBNrjYkS77FQYK1EQwhUFQqA7a/HCLoufPB3hmTctOgcttAVaYmKocyBeNFnQlBgtYSfxfC411kIKQPB8r2jwIwNEufdmd9oiroAz91M4br7ABw5UmN00fGLmB1FNl8I4VRAR6EgAf3WUh786Ctg5aHHjqxqPbbe483WNrAbactezErmagukuCPLXnKEAIA1EpsC4S+EmiWW1HVGxv7jF3QwSyuUTm33gvIMUZiVH3jn1FI9ILfaU86+nPS5w4kKBExfGsCttccMrGv0hcP3Leujv39xnh4SDBRBXYqgFLC8SlHCeop3kRUAoSAFM9xWwooRQzWp3/u5KW7QnBFpyUalPHe7hhIVyKCpVbPjrschvvCICeSHgSWB2k8Bnj/Lw2aOA+zYrPLzV4JZ1GpkI6AuB3QMWbXEnlvNCuVAgU4tSABDUZ47wgHYxtFJ0MAKOXyBw1Bw5dHHHFHD2/sr1EQsnAkaIYjtcjFdrnlT+9RS+zllJd7MDgM8f48FaZxD+uF4j0MPG5Zk3DR7ZZtGUEwEQQG/WoiszMt0w7quAI2BBSuDCt3ojwtiAKwLsSKDhJh+KMgWepaJI+V0ImRDIaBeNmpcSaPKATx3hxvUeNcdZ9ubY8PHXOaNfGBLn7IM93x8XNZP44jHu/HvmTYP7txjcuk5jMALeGHDRs0SudsCWiJ4NOQSmfJcLoQAgmNrJlkq6taL5xTraAjNyoT8hpud05by3v3+bRHvCjqimfnqHwY4BiyZ/Yt+b4ghA3hAev1CiIy7QmZmcSMREFePlLYHIzbIvFjRSAOlcsV7x8JJFrQKZyPW5HzlbwJfAh97qIa6AJh97ePr5YVQ0+tXXCVg7LJ5OXCRx4iKJvznWQ1YD174UITTAszstHt1mkPCALb12j8i4wHCKrfBa8XKRF2sLVn3mnsNuBAoAMomGLjDAfz2jXc4Z+RuyHTE61KUAIgDO+z//YIXmGHDegS4FUDh9T9dY+1RhSiL/OnelLW54VaM/KJ0CGHmjEkOzBgAg7gFJf3JuVKUExmA4XN9QjynUrmyBCyiGC/NmJt03IuOOQToCTl8qcdQcMZSaMtZ5mh85xIMUdihHXWzwZcFESBr9vRdptuA8NNaJqybfzUnI05O1MFbgmjURsnq46wBwou66l109QUwCSjpr35N1NQdKjgyjxT2XtuFKFwoAMonKvyNeLAz2vLH254bS9AXAdx+LoATwo9UaR83JFQHOFGhPiKEhQFM9PS1vJPNipDtj8cLugiLA9J5FgPNSYlQjbDF1xr9w+FE9RptiCvjcUQq+cu+jyqWcVi4QOHqOm7o3I+nqLqo5cy1cukSI4Qp+GvyJq7XIn/ehcccz7g0XCn7+mNIH7esr3PczkSvI9CTw9JsGj+ZTaxgZXXt0m4uuMRJAAcAugEn0kqs+WQQwO+luvqEG7tlo8cT2EHEFHDFb4NKjPJy8WEKMdPQmfYpeXnzct9ngp8/k2gA10B+40GZHQuzRBhjpGjKWZea2C7if2To73/Pv9b2bzHDEKHfjv/t1IDSREwPzJY6e6+pPtAUia0d0dhRHABJe5QgAuyb3/VrKRwDy4qow318pAuAmLYph477doMlz30sW1NWgoL4mJgFrOAqQAoDU5M0gf5PNX+DtcXejzkTAfZstHtgS4KTFEp850pvUQUDF/899mw3++9kI928eOQgo/3p1jd5klAQ6MxafP8ZDk48R62cj40KwF7xV4TuPRpjdJOpqy5uxwGvddg+xk5/MJwRw+3qDG1/VznCLPU9CKYCfP++q01cukDhyTvU1AKT668gWGPx8BMANUCqoAXizqAagzG5va4GE58TaQAAYa0d01hSmHuqxroUCgEz76IEUbm+6hcC9myzu2RjgL5crfPeU4VHAYoIFihJATxb4u3tD/GFdfhSwGDEKuB6mnJncjPpyEQBf1m8rckJV/nlLDCVz+4X0ZJzxuHODwS1rLZQELn9Go8kH3rtcVdUFQPa8fnThTAThomVAURdAmOsCMMNGPRsBs5rEqOLPjnITYBCXAoA0gBhojQHWCty+3uCRbVn8v9P8oWVAhcV44xUuz9cb3LXR4KurQnRlgNZcbr8ex5oqUXkqnV/Hg2tsFcdztPxvvoe9OQa0xl06qj909Sn/+niEnz/nptklFHDOW9TQHIDC+oCIYmDEHIDCLoD7Nhs3B2CtK5DtC1wNTX4OwIykGFpQZQo6OQgFAEsAyNAUtpTvbh4fvy3Ae/ZXuOzd/tCNYzwKBAuH9nzmjhC3r9eIK4GUnzP8tv6KrjL5GQCHDM8AKEwPAMCFh3i4/BmN3mDYGE7HdJQumFuf91rnpgRC40b/9lrg/z0R4cdP5SYBLhA4LzcJsDCtMt2EQKHhz78POwddZ8xj2womAcZc+4zKva95I19s7O00GwRoKQAIqS4i4Cs3Ue+mtRrWAj89a3xEQKHx/+wdIX6/TmN2UsCgAZaZlJkCmCemWN1WThTk5wl4OUEwp8mtTb7zdYM/rrf44ZMaKxdIHDffDVoq3AUwHeoE8n+nJ4GuDPDblyI8tt3l8rsy+V0AAm1FuwBCeviMABCyNyF6DWBuk8DN6zRwx76LgELjf+kdIW5epzG3STTETcoWVvmP0iXAiNfogiDvrbbGXO4p1E4M3PqaxRXPaVx0qMKX3+ZBiZHbAEUDevwWw0V2P3wywtUvum2AsdzI646kGNoGyDa8xocds2TSCI3zxm5ep3HpHeFQ3n6s95nCf5c3/nMaxPgrCfQFFhe+VSGV6wAQRSmCyLjUyoVvVegL7IgUAans+epci2BLzM2+78oC//RQhA/fEuChLQa+HM6HN4oBzItlTzrj/9AWgw/fEuCfHorQlXXvQ+H2P64CZgSAyRkyMSJAA3OSAr9f69q8fniGn5sQVp3HlfdkAgN8+c8hfr825/nrxjmPjS3fAbBHJwDP+702iiY3iGhRs8C9Gy2e3RHi00cqJDzgc8d4ziDWeVog//otgP96KkImAn72rEZXxv3doa6d2RfcBkgBQKZJJGBeSuDalzSOmivw+WO8Eb3uFW9ouedd/kyEa1/SWNomhpb3oIHGsFazl96X7G0fj/t5oN1aXG3dhMtAAw9sMfjysR6OXyjrskiwsMjvka0GP1wd4Y71BjHltmJ2JNBw1w0BUwCkfiIBC1sEfvikxuo3jNs1bkf3ZjwJrH7D4IdPaixsaSDPv2AL4KLm0h0ApToBFjULNwqXp9Q+e8oCbkvkohaB+zdZfPiWAPdtNnWXEigM+d+32YX7799ksahFuL0dYJifUACQKfZQBIDewOIHj7kRsKJCJDv//MEI+MFjEXoDW/H59S4Cqo0A0PiP7zkZGecZtyfcEqhLbguwaqNBOho5C7+Wjb8UbpHSqo0Gl9wWwJMC7TmPPzLMFhE0YgrAgsnQ+vO6ZiWBP27QuOLZCF88tnwqIB/OvOLZCH/coLGoRSBoMDdGCCCjgVOWSsQkSo5KLbzRxyRw/CKBO9YbNCtuUBtP8uehNcCldwRo8oH/OCOGkxfLqtNVU/Wa79ts8MU/BxgMnRjw5MjNnmQ8eksMIwCEYBxSAbOSAr98PkJPtvRQG5sLZ/ZkgV8+H2FWsrFC/yjI/feHFkfOkYip4bB0yaU6uc16R86R6A8tawEmyJv2cgWqvVng47dmh1ICtWZQC43/x2/NojfrXrcn2c5HKABILfe8K2Bjr8VVL0RD3n6x9w8AV70QYWOvRUw1Zug/NG7L4pG5GfaVjHr+Z0fOkZidFEP962T8Z1hYCyQ9lxIoFAG1YljzQiVv/L3cpr38ayeEAoDULNoALTEXBegqigLkvf+unPffEhM1u8Vvn2/kxq1ZPX6hHEoJVEoXAO65ceX+LZnYdJWLBghcclsWd200Q22CU2Vjbe515XdgXHJbFkqKqgpqCUFD7QKwVLz1HAWIK2BDj8V1ayJ89mhvKOef/3jdmggbeizm1Nn627Hk/9MRcPIS6TayidEXJpncYJvjFkhXBxDj+T/hIkAAGgIX35LF+w9U+K93x6asJiB/bXzuTwFuelUjFRNQBeN7yQTZGcMIACETEgbvDfYMrRrrvt/IIW4lgIHI5f8TXvn8f3EdQMJzaYCBiHUAmKwqe7hNkzet1bhn49TUBORFxz0bDW5aq9EaE5Bgvp9QAJB6TQP4Aje+Gg3lNK0dLmK68dUILX7jhv8jA3TEUVX+v1QdQEec61gntd9IAClP4BO3Z3HfpskVAUMFf5sMPnF7FilPwAr2PxEKAFLHN1VfAdv73VaywiUuj24z2N5v4avGvMnlCwDnNwucuGj0/H9xHcCJiyTmN7MQcLJDwUoCSgh87LZhETDRHvhQwd8mg4/dloUSAkoy9UMoAAjqfxFObxa4b5MeKnCycF/n25oa9e/uyVq85wAFIfZcAFRJOETGCYH3HKDQk+ViIExFm6AQ+PhtWazaaGAncIueydU4rdpo8PGc8WebH6EAIGiUNEB7XOCWdRp9WZff7ssCt6zTaI83bvhfG6A1DpyyREGK6rz/wiiAFO7ftsZZADYVIiAmAWsEvrIqGDp2422TbcHx/sqqANaIoWFRhIDbAMFBgA1yHEMNJH33ZdJ3Xzfqsc2H/xe2CKxc4PS4HIMAyD935QKJhc0C2/qG972TyesOSCigLwPcv9nglCXjPy0wX/F/7yaDvoz7/yj2aGcYASBotHB4dwZ4eIu7uz28xaA70+Dh/4zF2Qc47z8aYx5fwP0bKYCzD1DoyTANMGUDYi3w8T8M1wOMVy++Lsj7f/wPWWAKZw8QMAVAyIQVAkqgK23xUE4APLTFoCttG9ar1QZoTexd+L9kGiBBz3Cqzl1PuWmBF9+SxZPbjevJ38eTVlvX7fHkdoOLb3FT/jxFAUAoAEiD3kiVcPl/AGjy3dcWDP9XlQZoYTcAprIeQLlj+oPHIgwE2KeNlfkNmAOB+32hcb+feX9CAUAa+kaaFwC6gcOd+xr+ZxoANTnPYUZS4PbXNK56IXIDm/YyIqNz58NVL0S4/TWNGUnBWQ+EAoA0vvF/dKupeiAOpnH4n2mA2o0EpKN9O6aFI6Lp+ROwCwBsApgOAsAXeDgnAFrjw1EA22Dh/8AAC/Yx/F8qDbCghd0AUx0FaE8IXPZ0hHculnjbPDmUyx9r7v+J7QaXPR2hPeG8fx7P2rAzhhEAQiZOBLTEBPoDi4e3GCS8xvN+8uH/9+y/b+H/UmmA9+zPNEAt1LF0pS3+/YkIQoz92Iqc9//vT0ToStuGrYMhjAAwBED2OJZKAP0h8MgWi6QnGmoDFwBoDbQVDP+x47RRMJ8G+NkzEbTmqTSVswE6EgL3bdS4a4PBaftJt0hIVCeAAeCuDQb3bdToSAimdGrNzjACQMjE5sdDA6T8xptzLgAEGpiTEli5cN/D/3ukARZKzEkJBJrdAFMvZAW+tioYMv62CvsihRMBX1sVQAm6/oQCgEwjgR33gG39Bte8qJHyG6+gTUogHVl89FBvTLP/x7Ib4KOHekhHFpJX+JRh4Ir3erJ2qKh1tFRW/uePbjXoyVpX/Me3klAAEEyzQipP5NYCN5j3H2lXJHbx4R6UGN8ph25DHXDx4Z4rHGMUAFM+2TIN3LtRDy3zGW3LoLHu+d1psI6DUACQ6VcE2OQLPLrNoDPTWFMA821d71ws0Rxzf+t4GmiRe/+aY+7/GI9WNIJ9SmW1JQRuX6+HtgeWO5ctMLTd7/b1Gm3M/RMKAIJpuGs94QGPbDHoyozvUpUp9wgFMBBYHDlHwh/HefHFBWi+BI6cIzEQ2IaepVAv46239o2eBigM/2/ts2zjJBQAZPqKgEYcAxwZoCMJHDlXTtigo/zvPHKuREcSnB5XA2mA3gxw3yY9dG6XO+cB97zeDMP/hAKAYHqnAmyjzf7PVf+fuEgOpQQmIs0AACcuct0AIesAMNVpgPaEwM1r9VBEy5YJ/3dlgJvXarQz/E/AOQBjcxnzD0JqtSAssLjoUH+o+n8i0huFQ4EuOlTh2w+EmNnEOfJT2tmigHW7La5bE+Kzx/jQRcc+//V1a0Ks220wJ8XjVbt2pnFGATICQMgkef+ZCJjTLHDJ4T6kmNgQr5JOAFxyuI85zQKZiFGAWjgHeoPKKYDegMeJMALAQYCksW7+AgiNxY/OjKMtgaqnwu1rN0BbAvjRmTF87JYsfCUYIMPU1X40xwWueynC54/10eQPr/vNh/8HQ+C6lyI0xzn3n4MAGQEgBI1S+d+btTh5qcLp+6kJN/6FkwGNBU7fT+HkpQq9WXYETPXNNh25SFApMpH7OW/KhAKAkEa60ATw5bf7k+5B5P+/L7/dnxTRQcofh5gHbO+zuO6lEMDwhMv8x+teCrG9zyLm0fsnFACENIT3352xOG0/heMWSNgxroUdj//fWuC4BRKn7afQnWEUAFPc2dIblO4C6A0ab+slAWsAWARApvMNP+FNjfdfKgrwwCYNw+pyTNUGyNaYwPVrInwhVweQnw44GALXr4nQGhPc4sgiAEYACEGDbP2bmxI4eq6EAKYkDC9z++iPnisxl1sCp74OIASyRXUA2ch9nzdkQgFASCNt/TvMg5Tjt/Vvr+cCSOCjh3FL4JTXAfRbXPOiqwMIct7+NS+G2N7P/D+hACCkYbb+zUgKfOwIf9y3/mEvtwR+7AgfM5LcEogpbgnM12HYgloNDv4hFACENEjV/2Boccy8idn6ty9bAo+ZJzEYWnYFYGo3XWa1W/iT1RaPbjNo8gWLAAkFACGNMvznb1b4NbPVLb+Z7m9W+FwRXAObLrPaFQBmtfs64XGSOaEAIKSu8aRr/Tt1P4XjFkqYSW79Q4WWQGOB4xZKnJprCfR4B5gSEZD0h429gNt8SeNPKAAIqfPQf6CBmAL+doU/tDukprqYrHttMeVeK1MBk38M8kYfBakBQjgHgMsACeq48M8AkbG4+n1xvH1B7Xj/xVGAty+QuPp9cXz091nACkjB6vNJu+kKoDNt8cgWg5OWqCFVMHQP41tU83bGcBsgIaQ455/RFledG8fJS9XQSt5ajFJEBjh5qcJV58aR0ZY1AZPo/XsS6EoDD29xViQdAppWn1AAEIK6Xvhz6lKFU/dzxr+W8+tebi7BqfspnMpFQZMuApQA4jnn/9o1Ebb1WcQ5A4BQABBSxwt/VriRv/XgUYtc2P/LK7goaCpEQD7vH0SsASAUAITUp/cvXU73tFzVv62xvP+oi4IWukVBnWk7pcOKpqNgRJ2IRUIBQAgpgTFAW0Lgb4/z666IyyLXFXCcj7aE4KIgTF7BaPE+AEIoAMZjGyAffEzSIyaBHf0Wf7vCw9sXSOg68f4LowA61xXwtys87Oi3iEke14l8aA20xAR+86JTAHElXPcSH/XzoAAgBNN+4E9n2uLs5QqfOtp3M97r8IpSuYLATx3t4+zlLhXAAUGMABBGAAghZfK3mciN1v27E9xudyHqc8GOgHvtTb77W3zp/jYWBk5ODQALAAkFACF1ZDCtdcb/mg/E8bY6DP2XSwW8bYHENR+Iu/0FlhsDMcFZS4BjgAk4CXB8iwAImdjQ/8Yei++9K4aTlyqEGvAVGmKWQajdgKAvH+fh63cFWNomELIwcIIWMwkMhsDDW3RuNwDvXfUj2wwjAIRgGg786QuAiw738OmjPTfwRzXO3+cpVw/w6aM9XHS4h74AHBA0UTdfCewcsHh0i0FCMRVAGAHYt8EaPJ5kgtVyVgMtcYH/PDuGhCeGFruggdIbSgJN0v2NR/40g3To9tbz+hq/e1XMA7b0Gvz2pRBzUsArGfe+UwPUR5yZNQCEYPrN+k9HwH+eHUPcE9ANmiMXcPUAcc+JgHTEYTUTgbYu5UIIIwAsASA1jC+BN/otLjzMw7uWqZrb8ocJ2hr4rmUK7ztI4bcvRJjXzHqA8bxfyZwA0Ib3rrqzM4YCgJBpY/x3DFh84K0eLntPHNpOjxY5kesMuOw9cYQauOnlCHNTFAHj4v0bl0q65oUI2gAJLgIiFACE1F7F/+60xfsP9vDzc+Iu5F+n/f57kwrIC52fnxMHAPzh1QgzkgIRRcC4DQPivAUC1gAQUnvGvztjccp+asgANlrRX1UzDzAsAk7ZT6E7w0mB4z0MiBAKAEJq6MYcaNer/Y13uHW5dpresAv/9m+8w4cvBQJN40UIBQAhDWjwIu364a85L463LVB1P+kP4zYpUOGa8+KIjHuPKAIIoQAgBA1T+Gacsbv6/XGcslS5JT80dFDCiaJTlipc/f44Iuu+pggghAKAkLq/GIQF+kPgqve7fHdkwHw3RtZFRAY4Zb+cCGAkgBB2AYBzAEidh/21AfoDi/MO8XAajX/VIuCiG7ND3+c4WwKOAmQEgJB6Mv6hBiIL/Oa8BC5/bxzauNGspAoR8AEXCQgZCSCEEYCp3NFEyFgNWZAz/td8wIX9jaXx3xsR8JEbs4ABYrmFQoQ0agDAMgJASGP0+Ydm2PizqG3vRcA1H4gjNOCcAEIoAAhBTY/33Z22OGWpwu/OZ8HfeImA353vOid2p90GQUIIBQAhNTfb/5wDPVx/QQLvWOz6/Gn8900EaAu8Y7HC9RckcM6BHnYMUAQQwhoAMDlDUBNjbWMK2N5v8f63erjy3DisBXP+GMdhQcbNUrjyXDc6+aaXIsxvdpMDeWkS2hlGAAiZmjY/C7zePWz886l+Gv9xFAFyWGxdeW4c73+rh9e77bTZoEgIBQAhNeaZ9gdAR0LgX94Vw8/PjU/r2f6TuTvg5+fG8S/viqEjIdAfcKIiIRQAhGByQv5KAG8OWPzFgQr3fyKBrxzvQ9H4T5oIUAL4yvE+7v9EAn9xoMKbAxZKTK+NioSANQCETM1kvw8e6uFnfxmHkkCYq/SnAZq8VcKRAdoSAj/7S1cXcOsrEZp8AcXJgYQwAkAIxjnkn4nccJ+rz0u4fL9wxsan8Z90EeDnDH2+OPDq8xKIrDtGTAkQQgFAyLhs8hNw+f6WOHD1B+I48wA1VIDGkP/URmTyhZhnHuAmB7bE3bESuWNHCKEAIGTMxsWTbhZ9X2Dx3gMVHv9MEqfs54w/vUzUVqugdUODHv9MEu89UKEvsAi1O4YUaYSANQBjxVoL5B8E02moT08WCLTF/GaJn58bx5kHuNOaxr+2RUBbXOCKc+O48DWFL90eYHu/QUwJtMVdrQYhtWhnGqluhUWApH6rzC2wudfivLd6OGGJwkVHeOhIiKEZHTT+tS0C8sfpzAM8PPIZhaufi/DwJo0bcsOD8nUbhBAKAEKGxs5mIjfV7/+eHsPfHB8bMvaGA2dQTwWC+WPWkRD4wgoff/12H8c+EuDHj4cINJDwuFmQENYAEHqNwj260i4Md8W5cXz1hBgEnJFgb399zwyIjBMFXz0hhivOjcNYd6zzx50QQgFApqHhlwLoyVr0Bxan7+8Wzpy2zEOoh4sAaSPqOxqQLwIMNXDaMreo6fT9FfoDi56shaQQIARMAZBp0dInBRBpoCdwXuDpyxT+6u0xnLZMAXCFZL7ie9Vo+Mod2xOXKJy4JIlVGzQueyLAva9raAukfAFPudQBa34JoQAgDbRMxhgg0EA6tJiRFDh9kcJfvz2GU3OG39rhMbOkcaM+xrrIwGnLFE5blsQ9GzR+8kSA1dsNOtMWSV8gJgEp3dRHQggFAKnXELACugYtEp7A7JTAJUf5uPhIH7OaxAjDLzlLHtOlNgAYFgKnLlM4dVkSuwYtfvVsiF88E2HXgEUma9HRJBBx5TAh01QAmMba0zydQv1KOI9/R79b2vPF42I4doFCcwxDK7hNrqefhn/6CoH8RMdZTQJ/e3wMnzk2htXbNP7jsQC3vaoxq0kglksfMDVAJoS8jTEUAITstbcvhTP+mQjozFrs1y7xN8f7+Equqh9wYd388xjuJ/lzwFonCJtjwMn7KZy0XxL/+nCAXz4d4fVug5a4QMIbfh61ACEUAKQGqrxD4zy0/sAiq4Fl7RJfe4ePTxztoz0hRnh6ij0qpELUqDAy9NUTYvjUMT6ufDrElU9F2NBtEFdA0heQwk2MzLeKEkIoAMgkeW1CANkI2DloMTMpEFfASUs9HL84N70v6Qx/ZJzRp7dPqhWVeSGgDdCecKmBS47ycfVzER7ZrPHYFo1AA9v7LToSAvFcZEBTCRDSQLsAeCxrLrwf6GFPf/kMic+8zcepyxSOnCfRFh+28nnD79HjJ/sQXcoLgY6kwBeO8/GF43z0ZC2efcPgng0aN70UYV3ncGQgppgmINO6BIARADK+nn7e6EcGmJEUOPktHo5fpPCRIzzMSI507Wn4yUQKAU+6hUMnLVU4aanCF4/zcc1zER7ZovHwJo3dgxaeHCkGGBkgjADUszTjBTwlRn8gzBn9JoGTl7vlPOcf6mFOaqSnn48O5G/WhEyUEBi6LeS8/BkFkYE3Byyuf9EtH3p4s8buAYoBUqWdMRQAZJoubskX5gUaGCjy9E9YrHD+YSONPj19MtXnbX6qZGFkYE5K4PMrfHx+RU4MvBDh4c2lIwPA8KAhagLCCACZHga/oP0uq51XtDu3nKVao09Pn9RqZGCEGDjOx+ePKy0GtAVa4249cTwvCHLRRgoCQgFAGsrYDxl8A+zOWkgA81sEkr7Al1b6aIkJXHC4h9lNNPqkccXAzkGL656P0BdYXPt8hHRosb3PwmBPQUBRQCgASF2E8Qvz8KEZ7o/enbWwub7qQoPfHBP4yBEe4p5AygeNPpkWYmB2kxMDAPDFlTFkI4trnovQXyQItHXXU2tcuNZE6eYOFNYfMH1AKADIuBtzlBibKsSezw2Ne0gx3Jqnc/n71rhAzAP+5ngfngRiqrLBR0EBII0+aVgxUFAImPLdFsIvlBAEgXa1MFc/FyGIgN6sxc4BCyUx1HJorPu9eWFQjC5TwEzRQCgApqtBrzACNxvteaPIG/eMdr/P5n5v3tDPSAoMhBanLvPwtgUS/SHwziUKRy+QEBBDs/fLGXzQ4JNpNnHQEwWGuIIgAIDPrYjBwuLpbQYPbNJo9oEntxk8uEkj5Qt0pYeFQf7azH/MRw9s0b0gXuYOXRhZoGggFAB17p3nDS0w8uaQD8uLIkO/sFVAFvwyKYDBnHE/Zr6EASCHvg+csETh2AUSUW5iWikKXwMNPiF71smUEwQAcgJa4KT9FE7ab7g4oDvjugpWbzN4eJNGkz/SeIcF0YN8twIAGGuxtdcObUO0OVFiLZDwhiMLxVdzOdFQbmUyBQMFQH0TFs0CmGIy0Z4vI2+gQz283Swf+puRFGjLGeWc3YWxcGH5lT58NVL5xzyBi47w4KuRHoO2GDFhrxJ5Y59vkQJz+ITstSAoNKSmYBuhJ4cF98n7KZxcIAwK+cJxMWhrR0QBQp0XBnbIcTC5PRlPbTN4aJNGU04EDM88sNhSIBoKt2m2xAVkiVtkpdQE4TZAgrGtLl0+U4ww8iLnhZ+4xMMhcyTS4XA0YDC0eMcShWMWKBgDhLmr2eYu9LbE2AfjR6Z0eiD/mgSNPSETNytDjAwDFgqDUh47ADT5pWOHhSmG4hRAZ9oOzeVwhYcCgba45tkIWT0cTRBwEYPfPB8hG9mh+4DNFS92Z3K/S/AYMgLAXQB7/xos4CngtP0V/IKrSeR+FveB4xcrHD5X7vHvMpH7t6mYGPXvLPeM0FROQRBCapPQOC+82mteCGBmURvuQGARVwJ/tWJP0XD1sxFOXaZGpBfzAmD1No03Ntk9UhOkfACAAoCULBoKNPCjR8OhEGDhzzIR8IMHQ7QnRl7UeUUeVwIfOdJzo0iLfj4YAu/I5fHzYcBiDz/lizFHCURRZIAQsm9OSHEKoDAyUMnLHgjtHhGC/LW+eijkP9JIl/p5qEf+XmOBrb0Wvip9jcc9gSSNPyMAXAYwPmHAjmT5n0XGYiAorfB7YfH/3Zvd4y8orOQvTgnk6wXiHvCRI0bWC5QSD6EBOhKiZAqgVBEgRQEhZYx9URFg/poqTgF0ZSx8Wd6II5fvv+a5ENmiQsA8PRk7FPK3Rde/BZBQzoh3RaWv2fkt5SOl1loa/7HLPAoAgjFV2xbfKEophOKRusXdAj0ZW1I82Czwz/dmS0Ye8uKhI9cGeOIShbctVOgPgHcuVThmgYQA0Fwi/VDcBkhBQGjwc9dwURFgf2Bh4Qr0Htio0RwDntyqR7QBDhnxEtdpuVbAfI5/QYso697k2wLLRRgiw2NIKABqu17BApGdOPHQmXYFQLe/GuGml6I9BgF99AjfDS/JRRPi3p5pheJBQIQ07HVaweAPhBbZaNhr1wb49XPh0CCgvKHPDwLqjFwrYCUjrisEMG1BjQ8hFAAUD2MWD/kio/wc87ww6M1a2Czwv3MRBCWAHz0SIukDHz7cR3O8siBQkpEB0jjXV34UsChj8PuzwG+eD5EOge19puQo4LyhL/TMacQJBUBjlwDUhXgo3nPuiVwEoaCquD+w6MsC/9+9WQjkBIEHfPgIH80x4MIjfMxuGllLQDFA6t7oF0TZdg5a/Pa5EP0B8JvnQqQjYFuvgS0Q0bMKrpmhZUB2z0I8wjYACgBS0/nNwgiCJwDI4bRCoSBQAvjBgwFOWKJwwhKFCw73MSdFMUDq3+i/OWBx3fMhHt7k1gF3pkeuA56dux7yxp65dUIBQBpeFBQLgkADd6yNcOsrEcUAaTij70mXu8/32tPgEwoAQkFgh9sL815RtWIgMiNXERMyKRHbXB7ek9Ub/XwBIA0+oQAgBOWrlkcTA8cvUbjoSB8zkoIFhGTSPf38sKvOtMXVz4Z4hEafEAoAMjli4OaXIvzsyRAfOMTDKft7OGqeRFtiZGSAbYVkvNr2Cj39nozFM28Y3Ls+wo1rIqzbbRD3aPQJaRgBEGK4+pZdAFPPUJoAQEtMoDUOvNlv8S/3B/jpEyF85XYinLBE4aKjhiMDjAiQffX4vbyn/4wL7z+yWSPUwO60RUdCYHZKDKUEWKlP9kZkWgsYbgMkpIobc06UeRKY3ywQmpGRgcseD/Gpt/n45LH+0NpUnYskUAiQ0c6vfI+9J4HujMXPV4e44skQG7qGPX0p3LkXGXr6hFAAkCm5WYcFUwRb4wIi4Tyzf7wriytWh7jkGB9fOzE2NM5UFxQNErLH2Fs5PGDnBw8G+MVTIV7vMmiJC8xpHvb0OYCHEAoAUoORAV+53uqutMU378zi4Y0aXz4hhrctlEO7CQo9PYJpXWeSF4RKuNkUT241+OHDAW59JcLslAvxM6dPCAUAqRNvLsoZ90VtAqvWR3hkk8bslMAnjvXxsaN9zGoSztOzw6uPyfQhvyI3LwB3DVpc9XSIK1eH2DlgkY4sFrUJRJqGnxAKAFKfKQINtCcFjHF92v+0KosfPRLg2AUKn18Zw2n7K7ctjUJgWhn+/HFetV7jPx8NsHqba+FLegIxBcR9wYI+QigACBpklXLMAxK5G/vd6yPcsyHCqft7+NxxMZyeEwKaaYGGDvfnj+3d6zX+67EA96yPYKxbSNWRFC6/b0dfv00IoQAgddjTLQTQFneb1e5+LcI96yOcsszD374jhncuVQg0EFN8vxqJ/DF9YKPGvz0U4N4NzvDnt+1pGn1CKAC4DXAaDRmCEwKwwN3rIjywQePaDyVw+gEeTEFVOAMC9d3LL4Uz/ne/FuFD12YQaOvaQwWNPuE2wPFG8oiSekoPaAt0JAWUBD5xQwbffyBwSjZn/A0FIOo115+f3vf9BwJ84oYMlHTHmh4/IYwAEALAVXrHlEsTfONPWazeqvGOpQofPcpHR1IMCXRGA+pgwVSuyK8rbfHrZ0I8tFHjdy9EmN/iCvxY1U8IBQAhe3iNALC4XeBPayP84eUIP3w4xH+eE8e73+LtUUhGULNFfn9aG+Hzt2Sxvc8gptwxDXVutDchhAKgWm+CYNoVjLXE3bjXvqzFBb9J432H+PjRe+NoSwiKgBo2/j0Ziy/dmsXv14RIeG6Ij7HumBJSD7YmC9YAEDLlBiU0gO8BrQmBP7wc4egfD2LV+ghKDBcRktox/qvWu2P0h5cjtCYEfM8dQx4rQigACNnrGfHNcaAvsPjQtRn8aa0TAflOAYIpS9nkxzn/aa2r8O8LLJrjGOrnJ4RQABCyz90CCc9VlV9wbRoXX5+Bzc2RDw3TRVOxBErmRjlffH0GF1ybhifdMWJ1PyFgDcBekSmxqBmWd3gCkzP4bTHg+ucDCFj86C8TQyuHLdglMBnGXwDwc6t6v/SHDK5/PsSclICBbZid6mSahRkbaBYAuwBIY08TBDCnWeAPL0V4cusAPnGsj6+cGB9KC3CfwMQKMG2Bf30wiytXh9jeazGnWdDrJwRMARCCyUoJNMddr/nX/5jFx65PDw2fYV3AxA32MRb42PVpfP2PWXSlXb6fxp8QCgBCJt0oKQEs6xC48YUQF1+fHoricdgMxnVIE+AipBdfn8aNL4RY1iGGIi6EEDAFQAimICed1cDcZicCAODqC5JDoWrOC8A+t/jlx/ledJ0z/nObBbLs6yeEEQBCaoHQOBHw+zUhzv3VIB583bUKMhKwb56/EsCDr0c491eD+P0aZ/xDvqeEMALAbYCkpkSABmYlBe55LcJDr2tc95EkTjvAQ2SGvVhSvfH3JLDqtQgXXJNGoC1mJd04X0LAbYCMABBSi4arIyngS+CCa9JY9VoETzISgL0I++eNv5/b4Mf3kBBGALgLgNR8OkApwMCJAEYCxu7537UuwoeuTUNJ914y7E8aPQhgGAEgBA3TIeArQDESMGbPf9egxWduysDCrWhmpT8hFACE1J0IiFEEjKngb9VrEVb85wACbd1YXxp/QigACKlXr5YiYGwFfz1ZOzR1kRBCAUBIQ4iA869J456cCKB3Oxz2v+e1COdf43L+TR6NPyEUAIQ0mAjwFHDe1Wk8vkVDiektAvKDkh7fonHe1Wl4yr1HFEaEgF0A4BwA0mAGLy6BQW3x7VVZ/P7ipqH59tNtgVDhbP9vr8oi1BbNMbb6EbANIMsIACFo5DkBd62LcPF1aQDOEE4njVm4Nvni69K4a13EPn9CwBQAIdNCBMxuEvjd8yEuvs5tETRmeogAC/e3GuuM/++eDzG7icafEAoAQjB9hgXNaxa4/rkQn7rRFb9Nh8I3a10x5KduTOP650LM42x/QigACJmWC4RaBG54IcKf10YQDV4UqC0gBPDntRFueCHC3BYaf0IoAAiZplgDJD3gMzdlkA0tlGjMVICFq/jPhm7KX9JzfzshBOwCqNVwJbsAyIR6xQBiEugetPj0jRn89P0JxDwBJYcL5RrB+GsDBJHFpTdl0D1o0Rxjux8hI2wNIwCETM/2wNY4cPVTIS57LHCTAhto7W2k3bCfyx4LcPVTIVrjNP6EgCkAQki+M2B+q8APHgiw6rUIfoMMxNG5pUirXovwgwcCzG9lxT8hFACEEIzojRdAqIHzfp3G45vrf1Lg0KS/zRrn/TqNULu/kc4/IWANAEcBEoIR0/ESHtCVtvj2qgyu/XATYp6AFfVXD2Dh8pqDoftbQm046Y+QslcLGsbOMAJACPY+FTCzSeAPL0dD9QC6Do2mNsN5/z+8HGEmh/0QAqYACCEVCTUwv0Xg+/dn8eim+ksF5EP/j27S+P79WcxvEQg1jyshFACEEIzaMw+gO2Px/fuzEHWWAhBwuf7v359Fd8ZCMYlGCFgDwBIAQqoissCMhMCf10Z4ZGOElUu9Ic+61r1/KYBHNrrphjMSDP0TMqZtgIwAEEIEAGMsfnB/4DYG1oEQtbk1vz+4P4AxFoKHkRAwBUAIGbM33ZZwq4PvWhu5AUE17CVEucK/u9ZGuGtdhLaE4MAfQigACCF761EnPeDCawaxap0TAaYGjaqxzvivWhfhwmsG3ax/Gn9CKAAIIftQECjd47xfD+KxTRoCtdUVoHNh/8c2aZz368Gh10v7TwgFACFkH73ruHLLdL53X+11BQi4qv/v3ZdFEFnEVW1GKQghYBdA1TdegEVMpCYIDdCWFLgz1xVwfI10BeRfwyMbI9y5NkJbUiBk1T8h2JuGM0YACCFlPW0Li+/eF7i5+jXymkINfPe+ABas+ieEEQDOASAEE5EKaPIEntwSoT9r0dEk3BKhKbw8pAB6shZPbonQ5AkYev+E7P06AEYACCHl7hG+AjoHLK54IoC2U7snQBuXArjiiQCdAxa+olYmBCwCJIRMSBTAAAlf4MrVbtCON0XV9hau7c8YiytXB0j49P4JIRQAhEyo4Y0rYHuvxeot2k0QnQIFYKx7Lau3aGzvdZX/9P4JIRQAhEzkBSaATGjxvfvciOCpqAHI/7/fuy9AJrSQrP4jhFAAEIIJb71rTw4vChKTvC5YW9f3n1/4057kyF9CCNgFQMhkLgr6/n0BbvyYN6lRgLz3//37cgt/rOA1QggHATACQMhkLgq6e22EO1+NIMXk1AKY3LrfO1+NcPdaLvwhhFAAEDIli4I8CXzmhjR60i4PP5G22Ob7/tMWn7kh7ToQaPwJIRQAhEx+1DDpAzv6DH76eAAzwXMBtHERgJ8+HmBHn0HSZ+SfEILGrAHgzY3UOpEBmnyBK58M8JV3xofmAogJ6vvXBrjyyQBNvkBkeI0QQlvDCAAhUzodcEefxb3ro6HUwESkGwDg3vURdvRx6h8hhAKAkCnHl0DnoMVTWzWAiWkJzP/Op7ZqdA5a+LzKCSEUAIRgyjsCUjFnnEM9MSuClXBb/57aqpGKgZX/hBA0+BwAO/wgpIZP06QH3LsunJAtgbZg69+960IkPcAaXhOEjBsjinezjAAQQsZWB9CdtvjZ49lx3xKY3/r3s8ez6E4z/08IoQAgpPa2BD4ZALn5AONhpC3c74J11f/c+kcIoQAgpMaiADEFvNFn8eCGaGhq33hM/gOABzdEeKPPIkbvnxBCAUBIbeFJN6Xvz2tD6HEqXbHWhf//vDZET9q6aAAhhFAAEFI7aAO0JQVufjEalzSALQj/3/xihLakmNBJg4QQCgBCyN4WA0pga68ZlzRAYfh/a6+BLxn+J4RQABCCRk8DMPxPCJm+uwBsY+1pJo1PpIHWhEsD/NOZ2OvdAPnwf2Rc+L81IRBpXgqETETozlo0THcN/QRCpjgNsKVn39IAheH/LT0M/xNCKAAIQb2kAe7ahzRAPvx/F8P/hBAKAEJQd90Adi+6AWxORFhW/xNCKAAIwbRJAzD8TwihACAE0y8NwPA/IYTbAC3YBUDqEq2BtoTAzS+MrRtgRPX/CxHaEgJa8/0kZMLtDCMAhJBxHQrUbXDfa+FwW2s1ra8A7nstxNZuhv8JIdNRAAhhRdGWZkLqCV8CXYMWT21xLryuwpLnn/PUFo2uQQufcp6QyQoDGAqAWjkcSigI0TQuG1UImQK0BZriAqu3aGRCCyUqe/MWgBJAJrRYvUWjKS6qEg2EkH00/kJASL+pEZIBdS4AMkC8TUWd27pNtu9R4ccARgJInU6yTHjAQ69rSAnIKsYBSgFI6f5NwgP1LyETfZUKJW02HQRvvvAYgASyfYYCYCrlWKxZYeeaTt23wwkAyzQoqU+UdB79A+ujUesA8j97YH3kIgYM/xMyCRbTkyY7GPTf8uVHAcSRzRh2AUx8wkWUqcO0Q86Q8pusZREUqeNCQAVs73Yh/dPf4kPb8pGA/M9Wb9HY1W8xv10gZAcAIRN+pVohhbfw6GT06h39gCjsP7P11isg6/yeWfhlRPNPUOdTAZNxgae2aGSj8nUA+fx/NnJFg8k4p/8RMlkIWCN0oDkHYDLf88qqykJ4TYDIxUYFz1JSt3UA96/XCDUQ98qf8FIAoXbPTXiNUpNMSI1jLADRZJVQ1TmmjABMgLdfQNBnACTCHWseNdl0AKEky6FIvYuAavyLQIPFf4RMovkXfgwm0/NY1LmtG/FWBWT2zm5RAIzJ8Nuyb2w2awDE+2/70mM2MxBAchgqqd+cVsIDNnUZ/PLJLACUDO3nv/fLJ7PY1GWcCODbR8jEp//9GEzfzkew66VOxJoVRu/WrWkxIGvUw7dV/GxE0YW34KgkpFS8FRI0wEyAagr6Qg32/hMy6dW68VSB7SxXBFgXQqCeagAqdgkIk46E1VkASYoAUs9IYRHq0V2LULvnEkImyfpbY4XOZJxNEqM5qqLW0wCyTtcwFLypWYuWBbHwtdXbop4tv5XxJsCCDVGkbjsBWhICVz2ZRX/WDi0GKl4A1J+1uOrJLFoS7AAgZFKqc5Tv6YHugb4H/uU6ACn07dKcBDi1dQEFomAwkkIoKAFGAAjqus0ICCJAVIh7CZF7Dt8uQiZvECBsEgM7ooKotC1jk0Q9FALKOqn8r+zjuHGMSb3rpcdNZpCdAKQhyEZ79zNCyEQUAMZhgr5HZXagB7EWVWSXSqUA2AWwj4bfjpICcB+DwACI99zxPx6zmYEIQsk9SjP44KMOHtYCCQVs7jK46ok9OwHyn1/1RBabuwwSKid1+eCDj4l8GOHFYHrfeCLY9lwnYikPyI5mu6opZqcAGOMo4HKpAOPNOTgOIKBcJWjwTgB2ABCCyU3MGWOFEAqAByENyncA1M00Oq+O8v6ivLLKWjTPS0SvPrJF926+wV94zKfMQJeGqJu/j5CithaU7QTIdwAIUUdDxwmp6wJAz4sGu9N9D3zvtwBS6NutR51OCxYBTlQXQP7rAhUmLDBoTBT0wRreE0lDdAIMFHQC5DsABtgBQMjkm0qrM6JvW7qovc9W+LzmxYCs4XG/tsoIgPte/24NoGXwge/eoAe7M1Aeh6QS1HMnQCYqHwHIsAOAkMmyTFomUjA9m28Mdz77Bprn+UDWoPz2v3JdAJYCYHwjAAUfhQEA0b89Dasz9b3okBC38KdcLEvS+hMyidbHWBMFfUinzSgrgOvC80eN1wAUT1EaLeRicnUA8XDnc2+Y7s03ujqAgHUApG6XAikBpGKitPEvdbshhIz/lSg9Tw90pwfv/86NAJpz0eZKu2owhh0BjABgbCuBK6kti3RamzDTB2sMg6SkbseNS2D3gMX9r4UARkYCMlH5yAAhZCI6AHQa/fn8vyjfks4agElNAYx89HdGAJqDR77/ezPYYyEl6wBIXeJLoHvQ4oH10VBEIF/w96snstjSzS2AhExK/j/ZDN277fZo1wvbivL/pR6opzSArOEhQJX2ANjSIiCwiDV7me3PvGEy3U8IPzn6FEFCargVsFQKgBEAQibL+ZfSZgYj/cZzDyCd9hGEpgrDX/xRcB3w+AgCUUFluYefUtj9eo/u3Xy/8JSBpZNE6lcElDL0LAAkZNLy/9Jk+3v67/jqYwASCPo0Rp9YK5gCGP9CQJSYvVw0CwAGA10hgNbswz/+kxnosZBsByT1Cz19QqYy/J+C7t9+B4zfidRcDwhMgc0xGH0GQE0PCJJ1tvlPjJJrsUBgEGtW2R2Pb3NpgDjTAKRuQwClUgCEEExe+H/r0w8is00hHBH+R5k0AGsAJqgOABXUltkzDbCxR/dselB4MTANQOrR84/7wP2vhchGdkTYn1EBQiZj/K8vTbZvoP/Orz8KIIGgX5eJPBfbolJOKzgHYHz2ABSH/+UeSiyXBgge+/dbvdmHfgpeogMmtJU3rBNSWwIg4Qvc/1qEbATEveEugCZfAMYltpjcImRC3H8t/LjUO57/DYzqQmpuMwZ2RBUK0g3YBTChKYDRRgbbEWmA1JxY5oXfr9M9m28XiWYLC82TmtTbMKBUTAzJViWBbORmA8R9RgIImbArT0jPDvbp/nu/9Vtk3ohjoEsXOZqm6PN9jW5TAIyxHsCUTQEAFmGkAcT0G888jCgQgOBsYFLXRYBSANkIeGB9hERM0PsnZIIuOxFrgs32Pq93vrwDfsrPFf+Va/8brV2dEYAJmgdgSqgy9wg6NfxUqv+mT96pu7c8IuIpCVhGAUhdk58NQONPyMRdZVaHUXbtrf+Fzo0ZICZG2JbRCwGZAhhnETDakoXSYiCWkkAyY3o3PQzPZzEgQb0uBWJrICGTV/yHTF//4P3ffQbwmxAORGXC/2YU448yWwEpAMYxDVB+LONAdwjoluxj/36r6d/VC+VzJgBBvaUAMhHfB0Imq/dfxJqguzZch0y2E6kOWSb8b0bp/6+LVICs0wFpQKWdAEPCINBItfvZF29eb3avvVbEU2AxIKmXkzzhAVu7Da56PFsfu0UJqX/v3zMDXb0D937z18juSGCgW1cR/sdeDASiANjHToAKhn9EFCAC0Dxw7z9cbQa6GAUgdR0B4BhgQibQ+4+nYHa/cm20dtUmpOb4QKCrDP9X8vQF5wCM71hgMUohhhkRBWianYjW3rPJ7HrlWm/JykvtYJeGqJu/nUz3ceTCjlwEZHIDAChjCRnHC833zMDu3oE//8PVAFK51j9TIgJQbfgf4C6ACesGKN4PUK4/02CwOwLQNHDXP1xtBnczCkBQp1vJcdXjGWztNkj4tP+EjK/33wyza+210ev3bETTbB8Io4o1ZiOHAKFewv71XgRYaQqTKZ0KCDWaZsei1+/ZZHatvVbEm1kLQOqyC4CrgAmZoNz/4O7egbu+eQ2AZgx261GG/hjU8Q6Aeh4EhAqh//IPFwVIDdz1zWsYBSD15PVnouEzlTUAhEyM9693vvrb6PV7N+W8f106pTzm/H9N2xhVR/fBUh8LRYwo+Fzmvi54vgGaZsfNzjVv+ge9r0PNXHaMDbMaghMCSe2OAlaewGs7NT62Io6EL/Dghgh3vxKhKS4YCSBkfHL/wgS9ff23fOEfbM+GEGFoARMBKKwB0BWEAKoUA4wATEAqwJSp0NyzI2CwOwL8pvTd37raDPZkoWKKAVVSTxEAQgjGs81Gi1SL1G++er3eePfGMt7/aPP/6/bq9OrQ8JcLgpqi7oASgiCM4DfFo9fveiN46eZ/jB/xoe8jEgYCDKySmj3jC1W6MfXoZxBSkxeXRrxZmV0bn8n88as/gZ9qwWB3WMKBrLQGuFLfP+cATODwH6D8PmZb5uBZhIMR/Kbk4M2fvEX3bn9aJNslrGFBIKmLCyAVEzT8hIzLRSWEkEpk19x0Wbj9sW7Akznv34xh7G+pQUBgCmDyxgHbMiOCi0WAHs7lxCxiLSJ69db/slF2ENLjZnVS0ye8EkBkgPtfCxGLMXFFyD57/7GkiHaveyD9p799EH5TK8KesMCG6IJHNZ5/3Xn/9dwFUEoMmDLhf71HPUDYHULFWgb/+OU7oy2P/Uak2jwYRgFIbZ70UgJtSYEgsnjgtQgJX8AavjeEYG/na8qYsOFgdvDXH/x7+L5EGOoio18pCoAyibi6k+WNUARY6oCYMkUbw4ou3ZtF06xZ6Tu+fpnZvekZ0dThwXJdMKmtk9yXQHe/dZ6/J5zxp/dPyD5cWNIKPy6Dl27+x6hrbTfQ5OWG/tgyuf9yzmXdIxvoXlluN0CpIg4DhBphaKM3nugJ1tzwn1Zn0xCKqQBSU/gK6BmwuP+1CJ50aQBCyD6G/jtfe2Dw5k/eBt+LI+yJSrT66THUANh6DP/X8zpgVDEIaJQ6AFiEPQGSM9sH//SVu6LNj18jW9s8TggkNdf2InPFf4SQfbiYjIWXVDZMZwd//cFvwE/5CMNSPf7lWv9QofLfMgJQe1sCSw1uGKnwXCpgRvqPX/tp9MbahxBLKoCpAFJbJzqL/gjZ14E/nobV6XDNTd+M+l/tBmw+9K9L2AdTIQUwlkVA4ByAiZsFUGlLYLlogCiICAggFBjsUdHg6sGBX73375svfeQu4SXjCActBAevktpIbpnR9o8RQiqO+5VtbV72lXuvGrjlUzcgOXMu0rszRVX/puwQudLRALAGoDZrAUyZOgBdpOxyPw9DeK2JqH9Dd/jSTd+E1WlIT7MegNTKWd0cE9CGZyQhe5n3V9Ebax/K/OlrP0Vy5hyke4OivH+5nL+pciNgXUpyhfqeklrpZ8WPwn0BxTsFJEzWIN7eFL7428e9ZWfO9BYcfKzNDEYQQvECIlN2kgs3mmRem8TrnQY3PBOgJSGgKQQIqSbvb+AllI0ywcCVp38s2vVCP6JIFqz6LXYMTYmUgC2xdp4RgBqvCyhXyFEqEpCrB+gLkJw5J/Onr/00euPVR0Syw+eUQIKp7ViG77sBQNt6LCyTUoSMZc2vhYCOXvr9N6L+rT3wWuNAGBbZAVM+Olyy1RyN4P03ShFgpaJAUyYFYIsOfO4RRkj3mmjH6qD3shWf0z2bnxOJVkURQKZ6K2AqJpDw+F4QUj1CCz+pgmev+cbALZ/6A6xKIBoK/Zs9ZsOU9/xLLQBiBKCGOwJMheINW0H55esBfIQ9QfTCjf9hdWggfQHL2Wtk6ogMkI7ArVWEVBf6j0RTh6d3rX148NZL/4jkjBmIesMS9/xSnn+59r+GmQCIBqgBKFULIMp8r/Bhi4TPnvUCJmvhtTaF625Zp9qWrlfzjng3IASMhsvKEjJ50taTAn0Zi+e3RvAUJwESMqrxT8309O61j/Re+c4vwfc9pAc03A1clxn6o0tEBGyZEcANg2qgtemVPha2CIqC6IcoIxYAkzVIzkiFa65/XrXtv0HNO/IMCGFhjaAIIFMR4goNwMZUQioafy2SHZ7evfbR3suP/gLMoEA2EEAUlin2Kzb4ukQd2WizZygAajQKYMuIAlGViIjSBsk5LeGaa5+TrYu3eotWnAkd6gYsniR10hFACKlg/BOtSvdueb73smMvhdUSkAImKGf8Kw2KMyi/dRaNEg1otBqASsuCdJmBD6UmBA5/nX4zQHJGx+Btf/1HvXvtw25pkIl4tRFCSA21+8mYsDo00Qs3/BhhTxbwFKJ0WOTpj5YGGG3dL1MAdVgLUGoegKiQKhj5eRQByWY/++yv/hg7+H2Hy7bFSxEMRBCCkQBCCJnaNhkD5QNKIXzm6q8N3vmle+C1tCDqy5bx+sst/Sk3BbDa9fSMANRQFKBUV4ApuRq4ckGIce2Bg0DYg96fHPUlveuVR0VqlgerQ85jJYSQKRvyp6F8QEgRPnf11wZu/+ztSM5ozRn/Sl5/8f1fo/zSn4Ydvt3Ig4DKHTxTYjCQLXOiaAC5iVFRCOtJIETvZSu+qHe/+ohsm+0DwsByVQshhEx+zr9dQUoZPn/NVwdu/eztSHTMQLozW8KZq5T3H23zX0MV/qFBUwAYQ1sgihYKFYqh0l0BgICJDGTcQzRgsk/9cpW35GTI5MyjoWISJjIQLNMihJBJafVLdnim/43VwUs3/vPgrZ9dhURHBzJdmQqV/pWiAMVTZNHIof9GFgCV2v/KVf+PJhqGn2ciC3gKUiBYffmdmLF8k5pzxBkQQsBoy1ptQgiZ6D7/WZ7Zve7R3h8d+IXo1Vs2wGtpQdATFBn7aM9I7ogoQLmpf6gwBAgUAPU5G6DUOuFSA4LE6KLCACYSaJ7fEb3wm+dEy9IN3ryjzoD0JEykWRxICCETMBNbQIvULC/a9cqjfZcf/SVIBcRb4wh6smU8fl1U6KfLbPkz08XoTzcBsK+fF6cLhgVD0K+R6GiJXv7d86J54UY197ATpJ9IIAqYDiCEkPHz+i2kZ0WsWenu1x/ov+xtXwGyAJRE0BdUGO9rKnQAlBv2U6mgnAKgAesBUBQJGG2K4DBRxsBraYpevWlt9Pr9N6n9Tj5IdSxZjGDAABDMCBBCyL6V+sNLSEhpwhd++/cDvzr9PyGl52qzg6j0YreSNQClusEqLfpp+CjAdNh1X8mzL+ft25JFgOV+pwksvJaY7XktHbzwmzv9gz9wsEzNXQqrDaw2TAkQQsheNHVZG4lYyrMm6g+e/tX/St/+2VvhtbQiGtAwJirRsaXLdACYgjG/5Xr9mQKYRvUA5YoCK40NtiXSAblTKjDwkj5MJIJH/+1W2XHAa2rOoWeIWItElGZdACGEjCXkL6QVbTNVtOu1Rwevv+Az4dM/fSk34Kc45B9VMemv1NRXi2nS7z/dBUA1kQBUKBYcrbvADnUImEjAS8TDl25YI9sWvyBaFs6TqTkLEQ4awIK1AYQQMkrI32+SMJEx256+sv+q035gu9b1w2uJI+oLKxT6mRLhfl1myl81I37tdDKK0zESIEpsByz8KHMiqfBzVfA9BcAr+tp97jXHEfX3A16i5Qsv/UC1LTnRRhkgCgykZDSAEEL28PoFhJ8SRmf7g+ev+efM7Z/7PbzELESRLbHRT1cx57+4C6CaoT/TJgqgMD0FQDX5/UoRAzuKeBIwgUGiJQkIBI/+622yfb8NctYhx0m/KQEdWLfUndEAQgiBNQYqJoWfErpn44ODN3zor8Mnf/ISEh3tCPpDwOgyYX9Tose/+GNxmN+Mkuu309EgYhrXA8gScwFkUTRAlYgKqDJRgcKvPcCTQBSoJSd2NP3lFd9Sbfu5aIAOIgjhTc/DQAih4TcGgBCxZmF0ti966Xf/Z/APn74TgA+vxcvl+00JQ1+uyr9U619x5T8q5P3tdPWIMc3rAQpFgCz4XnFKIGfURxUDIwWD1+Ij6osAhE3v/e93e4dc8A0Za2m1mW64EcOKaQFCyPSZ6mOMFolWD0JCd254cPC2T/1vvenBLsCL5/avlKvqjyr0/Fea90/jTwFQVWdAsRgoJQL2zPuX/17ucy8nHKKMWnjcvMTp3zvPm3PoJ0SiXdh0lzs5BesDCCENa/ctYA2kr0RTG3TX5iejDat+mf7DJY8BEPCafUT9QZneflNF2L/Ssp9iETBtQ/8UAPsuAkSJSEB1QsBLeIgyBkBP8uzLTvMPOuejItm+EkLBZnvdiUohQAhpNMOvYkrEW2EG3+w1u169YeDqU3+BKOoBvGZnxKOo8mr2qrz+csV+ldr97HQPhVMEoGSHQKmUQKmHquJjweeeRKI5hkx3PwAvee4vV/rLTv+ISM4YFgIWlh0DhJCGMfwDb/aZnS/ekFn1P6/XWx/eDKAZXrNE1B9WyONXEgGmaKNfhOFhP7aC8Z/WoX8KgNHHBZcTAoVRAOSiAGKUIsFygkDAS3hAJBFFgwC85HuvPN4/4IwPjxACLiIgeLwIIXVr+He9eENm1T/8Tm99ZDOAJBIdHjJ9ERCVKtyrxvjbCrP9y+X8bdG0VwsaP4qAMl+X6g4oFgCqQBiookJBMUokYPixpxBYOUIIhAOA0RoQksOECCE1ObvXGAspBGRMiHhLgeH/n9frrQ9vHYPhN6NU9psSIgAF0QBUKPoDjT8FQLUioNSwoEqtgqKEga8cBRgpBHwgEsNC4IqV3v5nXiTirYcJP9Vkw0HABBbGWkhGBQghtVLYp5SItcCGaVid7TJvvnBL5p5vXp/z+JuQaPeR6Q+LDL+tMLhHV2jri0rk+U0F48+cPwXAPq8QLi4MLJUOQIl0gCjZGjhSOIwUA04IAFE0ACCplp0xM3H8350n5x15jlDxDuEnYYO+XFQAwkUFGBkghExSG581BkJKyJgQfhNsODBoM90vRq/96VfB6h+/qHc81wUghkR7DJn+qIThj0p48pW8fV00z98W/LvRCv1o/CkAxm15UKEAQIHxLm4VLFcbUCgAClMFYs/UQLOHKIPcxZNVc4/oiB37+cO85e+5SCTaDhV+KgUTwUUGIooBQsjEGPz84B4hFaQPkWiFzfQ5b3/HczdnHv7OjXrDnzsBpAEkkGhXJQx/Kc9fl/jalPk3UYWNfrZEBIDGnwJgXIsDq6kNEKN0C4iKaYBSz/c8JwYy3QbAIICkOuDsOckTv3E6UvOOk81zDxN+c3JIDFgDWBMBkBQEhJCxe/jO4rs7nq8gxLDRD9OdtnfLHdGWh54KV1/+lN79Yg+AGOApeAmBKBMBUaWFPKU8f1umur/UNr9Svf1mFINP408BMC4pgUoCAFUKgWofamTtgZefI2BzF1g/gFa1/1lzku/85mlomrdSti44CDpoEU0dQJCFjdKFgkAMryamKCCE5L17mzemYsjgx1tdbV+6Mw0dZWzvlj9GWx56Olx9xVN693NduXtTHIl2hahfI4rKFehV+9Bl1vaWC/ObKhf60PhTAExoXUBxSqCSEBB7IQJEUapAAJ5CYigqoHNioEMtON73D73wWLX/6QcI4R0lWxcdAhM2i6YOwAA22+uuB6OHRUFuDOGeZwRFAiGNYeDzDXDWAsLkbKKA8hWshfCSgB8HjIXJdKahw0B3rr1N6OxA5v5/vg39b2Z01ys7cvegnNGPDKKMBiJbxks3Jbx7O0qYX5fJ75dq8aPnTwEwpSJgtMFBokSOX5QoAiwlCkRRykAU/c4CMeHJnBjIXzABgAyAGWrB8b7/1g8eo5acdIgN+zw16+BzIGNSSNUsku1Dl48TBqbgT7KADnO/j6cKIXVk9EVufogH6RUu34HwmwAVz4sBmIE3B4WXhOnb+qLN9j6NbI+XefDbt+QM/ps5I5wCACTa/ZzRj3JG35aZuW/LePOVPPxyvyf/c4wy0x9s9aMAmGwRUColgKI5AcXCQJXoJCglCEoJAFFmLHHB9z0BL+FSBZldhYIgC0CpWYfNh/QC/8iLj1aL3nkosr3aSpVQMw/+C0jl59N+gBAyNTsJIXgZEVJvSMCmu2F12A9rJWCN8JLS9G1dYzOdT8HoBMJ0kHnon29FGAT6jSf7AXTn7iN5g+8BsC68D1uQ1y/lkZcSAOW+Z4oMe3EkAGV6+hnypwCouVkBxRGA4tQAKhhsWcaoq1H2EFQQAMUPT8BLKHgJBURApjvIPTfIPQBAqo4D50LF5NCkrERLLHbit/5CenHfreMuxBT87ZIXGyGTjim6HxVeh9Yg3iLDLQ+9qJ/91dMQJgEdGnhN0G+s7gPQU3CvSg3dq+JtHoQwiPqjnMEv1V9fjQAo1ao32nPMKOH+asf58n5EATCldQHlxEDx3IByAkDsWfw3WgqgkgAoIQjcGGIJLyGByL3OTHdY9LdYAAMlvsfzhhDU4CS+PYkBiBflzIcNvfPuTYGxL1dYV26zXrmP5Xr1y1Xzm1GMfrnWPob8KQBqWgSUEwTlPPdy3r6qwvBXKQDKvS5v5M88AF5z4e8sbfytFUV1g7wICRn/Wr4xXmeeRZQxrmOo0DhGlabklWqpM2UW7IwmAKo19OWEx1gK/Wj8KQBq4v0rlxYQo6wbFmVGDVcK9csKAmIvBMAewmW02gdCSO1HAoqNph1FAFQarlPJcFcq4huL4bcVXicNPwVAXYoAlDHApYSAqCLcP5rnL0cx/rKCwd9XAcDzipDJCfGPpwAoZegref52FINfKnpgyvTyl3s9o+X2afwpAOqiQBDjJASq9fhlBa9fovQsg0pjkHnOEFJ/QqGUGChnZMuN0x1NAFQq4Kt2RW+pHD+NPwVAQ20VrBQVKB4mJEYx+pXEAsrMIygnAMYSBeB5Q0h9hv4xSvjfjuL5lxu/W0kY2DFs6qu2pY+GnwKgbtMClYRApfHCYpSfyTIri8u1JIpRXsNYPH+eR4TUVlqgkjEttymvnHduqzTs5Yx9NVEHVPD+afgpABq2PqCSQcYoAmAsYqFS+qFaw88aAELqtwbAjiIITBUFgRilYr/SqN5y3v9ohp/GnwKg4d5jMUp0oNBrtwWevR3F0FcSDfsqAKo9Z3heEVIbAqCaoTmVigExiggo9XOB4Ql/2AePn4afAmDaCYGxrCFGlUKgnOGfKAFACKm9IsCxCoBqcvaVnltNbp+GnwKA73mVg4XKiYLiyEA57388ev8ZASCkvlMAqKIosNqfF8/nH01oCBp+CgBSnRAoZZxRpk7Alqjur2Twq/3dNPqE1K8gqMb4VysIRIn8/mh1BdXO6afhpwDgMajQOWCr9NRLCYNqw/zVGH6eM4TUXzugGIOXXslwG1TfZggafgoAMj7HYjQjXUkYlEoRjNX4i6KbCc8pQmrP8y9l7MdSGyCqMPLVRBSqeZ2EAoDsQ7i9eEHPWHL3suBClEUXpiy6QEWJjYA8lwipPSEgqhiiI4q8eVGhOn8sn1dj2Gn4KQDIBIiBvSngK/f7ZYWLVvKwEFLTmDIrvO0YvPJKn4sq8/o0/BQAZIrEQLn1vWPJ6/P8IATTZmLgeBp8Gn0KADLFx01UCA+y0p8QdgeU+t7eGnwafQoAUuPHUFSRNxQ8lwhpmLkA1Rh50ODTeJDpe0z3dc4/bwSE1Ma1PtE5eV7rFACEx5jnEiF1FgGgsSe8aRMee0IIDT2NACE8NwihgSeEEEIIIYQQQgghhBBCCCGEEEIIIYQQQgghhBBCCCGEEEIIIYQQQgghhBBCCCGEEEIIIYQQQgghhBBCCCGEEEIIIYQQQgghhBBCCCGEEEIIIYQQQgghhBBCCCGEEEIIIYQQQgghhBBCCCGEEEIIIYQQQgghhBBCCCGEEEIIIYQQQgiZNP5/5I8AWy+HKdwAAAAASUVORK5CYII="

SWIFT_SRC = r"""
import Cocoa
import WebKit

final class AppDelegate: NSObject, NSApplicationDelegate, WKUIDelegate, WKNavigationDelegate, WKScriptMessageHandler {
    var window: NSWindow!
    var web: WKWebView!
    var server: Process?
    let outPipe = Pipe()
    let inPipe = Pipe()
    var buffer = ""
    var quitting = false

    func applicationDidFinishLaunching(_ notification: Notification) {
        buildMenu()
        let cfg = WKWebViewConfiguration()
        cfg.userContentController.add(self, name: "donmac")
        web = WKWebView(frame: .zero, configuration: cfg)
        web.uiDelegate = self
        web.navigationDelegate = self
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1060, height: 800),
                          styleMask: [.titled, .closable, .miniaturizable, .resizable],
                          backing: .buffered, defer: false)
        window.title = "Dọn Mac"
        window.minSize = NSSize(width: 640, height: 480)
        window.contentView = web
        window.center()
        window.setFrameAutosaveName("DonMacMainWindow")
        window.makeKeyAndOrderFront(nil)
        web.loadHTMLString(Self.loadingHTML, baseURL: nil)
        startServer()
        NSApp.activate(ignoringOtherApps: true)
    }

    static let loadingHTML = "<html><body style='margin:0;height:100vh;display:flex;align-items:center;justify-content:center;font:15px -apple-system;color:#888;background:Canvas'><style>:root{color-scheme:light dark}</style>Đang khởi động Dọn Mac…</body></html>"

    func startServer() {
        guard let res = Bundle.main.resourcePath else { return }
        var candidates: [String] = []
        if let p = Bundle.main.object(forInfoDictionaryKey: "DonMacPython") as? String { candidates.append(p) }
        candidates += ["/opt/homebrew/bin/python3", "/usr/local/bin/python3", "/usr/bin/python3"]
        guard let py = candidates.first(where: { FileManager.default.isExecutableFile(atPath: $0) }) else {
            showError("Không tìm thấy Python 3. Mở Terminal và chạy: xcode-select --install")
            return
        }
        let logPath = NSHomeDirectory() + "/Library/Logs/DonMac.log"
        FileManager.default.createFile(atPath: logPath, contents: nil)
        let p = Process()
        p.executableURL = URL(fileURLWithPath: py)
        let support = NSHomeDirectory() + "/Library/Application Support/DonMac/don_mac.py"
        let script = FileManager.default.fileExists(atPath: support) ? support : res + "/don_mac.py"
        p.arguments = [script, "--native"]
        p.standardOutput = outPipe
        p.standardInput = inPipe
        p.standardError = FileHandle(forWritingAtPath: logPath) ?? FileHandle.nullDevice
        outPipe.fileHandleForReading.readabilityHandler = { [weak self] h in
            let d = h.availableData
            guard !d.isEmpty, let s = String(data: d, encoding: .utf8) else { return }
            DispatchQueue.main.async { self?.consume(s) }
        }
        p.terminationHandler = { [weak self] _ in
            DispatchQueue.main.async { self?.serverEnded() }
        }
        do {
            try p.run()
            server = p
        } catch {
            showError("Không chạy được Python: \(error.localizedDescription)")
        }
    }

    func consume(_ s: String) {
        buffer += s
        while let r = buffer.range(of: "\n") {
            let line = String(buffer[..<r.lowerBound])
            buffer = String(buffer[r.upperBound...])
            if line.hasPrefix("DONMAC_URL "), let u = URL(string: String(line.dropFirst(11))) {
                web.load(URLRequest(url: u))
            }
        }
    }

    func serverEnded() {
        if !quitting { NSApp.terminate(nil) }
    }

    func showError(_ msg: String) {
        let a = NSAlert()
        a.messageText = "Dọn Mac"
        a.informativeText = msg
        a.alertStyle = .critical
        a.runModal()
        NSApp.terminate(nil)
    }

    func applicationWillTerminate(_ notification: Notification) {
        quitting = true
        if let s = server, s.isRunning { s.terminate() }
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }

    // Hộp thoại confirm()/alert() của trang
    func webView(_ webView: WKWebView, runJavaScriptAlertPanelWithMessage message: String,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping () -> Void) {
        let a = NSAlert()
        a.messageText = "Dọn Mac"
        a.informativeText = message
        a.addButton(withTitle: "OK")
        a.beginSheetModal(for: window) { _ in completionHandler() }
    }

    func webView(_ webView: WKWebView, runJavaScriptConfirmPanelWithMessage message: String,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (Bool) -> Void) {
        let a = NSAlert()
        a.messageText = "Dọn Mac"
        a.informativeText = message
        a.addButton(withTitle: "Đồng ý")
        a.addButton(withTitle: "Hủy")
        a.beginSheetModal(for: window) { r in completionHandler(r == .alertFirstButtonReturn) }
    }

    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
        guard let s = message.body as? String else { return }
        if s == "relaunch" { relaunch() }
        if s == "quit" { NSApp.terminate(nil) }
    }

    func relaunch() {
        let t = Process()
        t.executableURL = URL(fileURLWithPath: "/bin/sh")
        t.arguments = ["-c", "sleep 1; /usr/bin/open \"$0\"", Bundle.main.bundlePath]
        try? t.run()
        NSApp.terminate(nil)
    }

    @objc func rescan() {
        web.evaluateJavaScript("var b=document.getElementById('rescan'); if(b) b.click();", completionHandler: nil)
    }

    @objc func reloadPage() { web.reload() }

    func buildMenu() {
        let main = NSMenu()
        let appItem = NSMenuItem()
        main.addItem(appItem)
        let appMenu = NSMenu()
        appMenu.addItem(withTitle: "Giới thiệu Dọn Mac", action: #selector(NSApplication.orderFrontStandardAboutPanel(_:)), keyEquivalent: "")
        appMenu.addItem(NSMenuItem.separator())
        appMenu.addItem(withTitle: "Ẩn Dọn Mac", action: #selector(NSApplication.hide(_:)), keyEquivalent: "h")
        appMenu.addItem(withTitle: "Thoát Dọn Mac", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        appItem.submenu = appMenu

        let editItem = NSMenuItem()
        main.addItem(editItem)
        let edit = NSMenu(title: "Sửa")
        edit.addItem(withTitle: "Cắt", action: #selector(NSText.cut(_:)), keyEquivalent: "x")
        edit.addItem(withTitle: "Sao chép", action: #selector(NSText.copy(_:)), keyEquivalent: "c")
        edit.addItem(withTitle: "Dán", action: #selector(NSText.paste(_:)), keyEquivalent: "v")
        edit.addItem(withTitle: "Chọn tất cả", action: #selector(NSText.selectAll(_:)), keyEquivalent: "a")
        editItem.submenu = edit

        let viewItem = NSMenuItem()
        main.addItem(viewItem)
        let view = NSMenu(title: "Xem")
        let r1 = view.addItem(withTitle: "Quét lại", action: #selector(rescan), keyEquivalent: "r")
        r1.target = self
        let r2 = view.addItem(withTitle: "Tải lại giao diện", action: #selector(reloadPage), keyEquivalent: "R")
        r2.target = self
        viewItem.submenu = view

        let winItem = NSMenuItem()
        main.addItem(winItem)
        let win = NSMenu(title: "Cửa sổ")
        win.addItem(withTitle: "Thu nhỏ", action: #selector(NSWindow.performMiniaturize(_:)), keyEquivalent: "m")
        win.addItem(withTitle: "Đóng", action: #selector(NSWindow.performClose(_:)), keyEquivalent: "w")
        winItem.submenu = win
        NSApp.windowsMenu = win
        NSApp.mainMenu = main
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.regular)
app.run()
"""

LAUNCHER = """#!/bin/bash
# Bản dự phòng khi không biên dịch được app gốc: mở giao diện trong trình duyệt.
RES="$(cd "$(dirname "$0")/../Resources" && pwd)"
SCRIPT="$HOME/Library/Application Support/DonMac/don_mac.py"
[ -f "$SCRIPT" ] || SCRIPT="$RES/don_mac.py"
for p in "__PY__" /opt/homebrew/bin/python3 /usr/local/bin/python3 /usr/bin/python3; do
  if [ -x "$p" ] && "$p" -c 'import sys; sys.exit(sys.version_info < (3, 8))' 2>/dev/null; then
    exec "$p" "$SCRIPT" --app
  fi
done
osascript -e 'display alert "Dọn Mac cần Python 3" message "Mở Terminal và chạy: xcode-select --install" as critical'
"""


def compile_native(exe):
    """Biên dịch app gốc bằng Swift (có sẵn trong Command Line Tools, Homebrew cũng cần bộ này)."""
    import tempfile
    tmp = tempfile.mkdtemp(prefix="donmac-")
    src = os.path.join(tmp, "main.swift")
    with open(src, "w", encoding="utf-8") as f:
        f.write(SWIFT_SRC)
    cmd = ["xcrun", "swiftc", "-O", "-swift-version", "5", src, "-o", exe,
           "-framework", "Cocoa", "-framework", "WebKit"]
    print("   Đang biên dịch app (khoảng 10–30 giây)…")
    r = run(cmd, 600)
    shutil.rmtree(tmp, ignore_errors=True)
    if r and r.returncode == 0 and os.path.exists(exe):
        return True, ""
    return False, (r.stderr.strip()[-1500:] if r else "swiftc không chạy được")


SUPPORT_DIR = DATA_DIR


def install():
    """Cài/cập nhật. Code Python nằm ở ~/Library/Application Support/DonMac (ngoài app), nên khi chỉ
    cập nhật code thì app giữ nguyên chữ ký → macOS GIỮ quyền “Toàn quyền truy cập ổ đĩa” đã cấp."""
    if sys.platform != "darwin":
        sys.exit("Chỉ cài được trên macOS.")
    import hashlib
    with open(os.path.realpath(__file__), "rb") as f:
        me = f.read()  # đọc trước, phòng khi đang chạy từ chính bản cài cũ
    os.makedirs(SUPPORT_DIR, exist_ok=True)
    tmp = os.path.join(SUPPORT_DIR, ".don_mac.py.new")
    with open(tmp, "wb") as f:
        f.write(me)
    os.replace(tmp, os.path.join(SUPPORT_DIR, "don_mac.py"))

    shell_id = hashlib.sha256((SWIFT_SRC + LAUNCHER + ICON_B64 + sys.executable + "shell-1").encode()).hexdigest()[:16]
    targets = ["/Applications", os.path.join(HOME, "Applications")]
    existing = next((os.path.join(t, f"{APP_NAME}.app") for t in targets
                     if os.path.isdir(os.path.join(t, f"{APP_NAME}.app"))), None)
    same_shell = False
    if existing:
        try:
            with open(os.path.join(existing, "Contents", "Info.plist"), "rb") as f:
                same_shell = plistlib.load(f).get("DonMacShell") == shell_id
        except Exception:
            same_shell = False
    # tắt bản đang chạy (cả kiểu cũ lẫn mới)
    for pat in (r"Application Support/DonMac/don_mac\.py --(native|app)$",
                r"Contents/Resources/don_mac\.py --(native|app)$"):
        run(["pkill", "-f", pat], 10)
    time.sleep(0.8)
    if same_shell:
        print(f"✅ Đã cập nhật {APP_NAME} lên v{VERSION}. App giữ nguyên nên KHÔNG cần cấp lại quyền.")
        subprocess.run(["open", existing])
        return

    apps = next((t for t in targets if os.path.isdir(t) and os.access(t, os.W_OK)), targets[1])
    os.makedirs(apps, exist_ok=True)
    dest = os.path.join(apps, f"{APP_NAME}.app")
    for old in targets:
        o = os.path.join(old, f"{APP_NAME}.app")
        if os.path.exists(o):
            shutil.rmtree(o, ignore_errors=True)
    c = os.path.join(dest, "Contents")
    os.makedirs(os.path.join(c, "MacOS"))
    os.makedirs(os.path.join(c, "Resources"))
    exe = os.path.join(c, "MacOS", "DonMac")
    native, err = compile_native(exe)
    if not native:
        print("⚠️  Không biên dịch được app gốc, dùng bản mở trong trình duyệt.")
        print("   (Cài Command Line Tools bằng: xcode-select --install, rồi cài lại để có cửa sổ riêng.)")
        if err:
            print("   Chi tiết:", err.splitlines()[-1] if err.splitlines() else err)
        with open(exe, "w") as f:
            f.write(LAUNCHER.replace("__PY__", sys.executable))
    os.chmod(exe, 0o755)
    with open(os.path.join(c, "Info.plist"), "wb") as f:
        plistlib.dump({
            "CFBundleName": APP_NAME, "CFBundleDisplayName": APP_NAME, "CFBundleIdentifier": APP_BUNDLE_ID,
            "CFBundleExecutable": "DonMac", "CFBundleIconFile": "AppIcon", "CFBundlePackageType": "APPL",
            "CFBundleShortVersionString": "4", "CFBundleVersion": "4",
            "LSMinimumSystemVersion": "11.0", "LSUIElement": not native, "NSHighResolutionCapable": True,
            "LSApplicationCategoryType": "public.app-category.utilities",
            "NSHumanReadableCopyright": "Công cụ dọn dung lượng cá nhân",
            "NSAppleEventsUsageDescription": "Dọn Mac dùng Finder để chuyển ứng dụng vào Thùng rác.",
            "DonMacPython": sys.executable, "DonMacShell": shell_id if native else "fallback",
            "NSAppTransportSecurity": {"NSAllowsLocalNetworking": True, "NSAllowsArbitraryLoadsInWebContent": True},
        }, f)
    with open(os.path.join(c, "Resources", "AppIcon.icns"), "wb") as f:
        f.write(base64.b64decode(ICON_B64))
    run(["xattr", "-cr", dest], 30)
    # Ký ad-hoc để macOS nhớ quyền đã cấp cho app (không phải cho python)
    run(["codesign", "--force", "--deep", "--sign", "-", "--identifier", APP_BUNDLE_ID, dest], 120)
    lsreg = ("/System/Library/Frameworks/CoreServices.framework/Frameworks/"
             "LaunchServices.framework/Support/lsregister")
    if os.path.exists(lsreg):
        run([lsreg, "-f", dest], 30)
    print(f"✅ Đã cài {APP_NAME} v{VERSION} vào {dest}" + (" (app gốc, cửa sổ riêng)" if native else ""))
    print("   Lần này cần bật lại “Toàn quyền truy cập ổ đĩa” MỘT LẦN; các bản cập nhật sau sẽ giữ quyền.")
    subprocess.run(["open", dest])


def main():
    if "--install" in sys.argv:
        return install()
    if "--auto-clean" in sys.argv:  # chạy nền theo lịch: chỉ dọn mục An toàn, ghi lịch sử
        mb = 200
        if "--min-mb" in sys.argv:
            try:
                mb = int(sys.argv[sys.argv.index("--min-mb") + 1])
            except (ValueError, IndexError):
                pass
        return sys.exit(auto_clean("--dry-run" in sys.argv, mb))
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    if NATIVE:
        print("DONMAC_URL " + url, flush=True)

        def parent_watch():  # app gốc đóng → stdin hết → tắt server
            try:
                sys.stdin.read()
            except Exception:
                pass
            server.shutdown()
        threading.Thread(target=parent_watch, daemon=True).start()
        if has_fda():
            start_scan()
        server.serve_forever()
        return
    print(f"Dọn Mac đang chạy tại {url}")
    print("Nhấn Ctrl+C (hoặc nút “Thoát” trên trang) để tắt.")
    start_scan()
    if APP_MODE:
        threading.Thread(target=watchdog, args=(server,), daemon=True).start()
    threading.Timer(0.3, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    print("Đã tắt.")


if __name__ == "__main__":
    main()
