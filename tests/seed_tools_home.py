#!/usr/bin/env python3
"""HOME giả cho kiểm thử giao diện feature 003: python3 tests/seed_tools_home.py /tmp/fh3"""
import os, plistlib, subprocess, sys
root = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "/tmp/fh3")
subprocess.check_call([sys.executable, os.path.join(os.path.dirname(__file__), "make_fake_home.py"), root], stdout=subprocess.DEVNULL)
def W(rel, data):
    p = os.path.join(root, rel); os.makedirs(os.path.dirname(p), exist_ok=True); open(p, "wb").write(data)
blob = os.urandom(3 * 1024 * 1024)
W("Documents/Trip/holiday.mov", blob); W("Downloads/holiday (1).mov", blob)
app = os.path.join(root, "Applications/Foo.app"); os.makedirs(app + "/Contents/MacOS", exist_ok=True)
plistlib.dump({"CFBundleIdentifier": "com.test.foo", "CFBundleName": "Foo", "CFBundleShortVersionString": "2.1"}, open(app + "/Contents/Info.plist", "wb"))
W("Applications/Foo.app/Contents/MacOS/bin", b"x" * 400000)
W("Library/Application Support/com.test.foo/data.db", b"x" * 600000)
W("Library/Application Support/com.gone.app/store.db", b"x" * 800000)
W("Library/Caches/com.gone.app/c.bin", b"x" * 300000)
W("Library/LaunchAgents/com.gone.helper.plist", b"")
plistlib.dump({"Label": "com.gone.helper", "ProgramArguments": ["/Applications/Gone.app/Contents/MacOS/helper"], "RunAtLoad": True},
              open(os.path.join(root, "Library/LaunchAgents/com.gone.helper.plist"), "wb"))
import time
old = time.time() - 90 * 86400
for v in ("2.1.300", "2.1.322"):
    W(f".local/share/claude/versions/{v}", b"x" * 700000); os.utime(os.path.join(root, f".local/share/claude/versions/{v}"), (old, old))
W(".claude/projects/-p/a.jsonl", b"x" * 500000); os.utime(os.path.join(root, ".claude/projects/-p/a.jsonl"), (old, old))
W(".codex/generated_images/x.png", b"x" * 400000); os.utime(os.path.join(root, ".codex/generated_images/x.png"), (old, old))
W("Library/Application Support/Claude/vm_bundles/claudevm.bundle/rootfs.img", b"x" * 900000)
print(root)
