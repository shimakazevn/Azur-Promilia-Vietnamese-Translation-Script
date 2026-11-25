# -*- coding: utf-8 -*-
import json
from pathlib import Path
p = Path(r"D:\windows\Desktop\蓝色星原简体汉化独立版\tools\deployment-plan.json")
j = json.loads(p.read_text(encoding="utf-8"))
for g in j["games"]:
    print("### game", g["id"], "files", len(g["files"]))
    for f in g["files"]:
        same = f["source_sha256"]==f["target_sha256"]
        print("   %-70s %-9s src=%s tgt=%s" % (f["relative_path"][-70:], "UNCHANGED" if same else "CHANGED", f["source_sha256"][:8], f["target_sha256"][:8]))
