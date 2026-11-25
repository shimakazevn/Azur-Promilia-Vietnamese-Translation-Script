# -*- coding: utf-8 -*-
import json, hashlib
from pathlib import Path
plan = json.loads(Path(r"D:\windows\Desktop\蓝色星原简体汉化独立版\tools\deployment-plan.json").read_text(encoding="utf-8"))
g = [x for x in plan["games"] if x["id"]=="tw_game"][0]
E = Path(r"E:\AzurPromilia_TC\AzurPromilia_TC_game")
for f in g["files"]:
    p = E/f["relative_path"]
    if p.exists():
        h = hashlib.sha256(p.read_bytes()).hexdigest()
        print("%-58s size=%-10d sha=%s" % (f["relative_path"][-58:], p.stat().st_size, h))
        print("    plan.src=%s" % f["source_sha256"])
        print("    plan.tgt=%s" % f["target_sha256"])
        if f.get("previous_sha256"):
            for q in f["previous_sha256"]:
                print("    plan.prv=%s" % q)
