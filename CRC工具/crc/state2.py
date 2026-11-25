# -*- coding: utf-8 -*-
import json, hashlib
from pathlib import Path
plan = json.loads(Path(r"D:\windows\Desktop\蓝色星原简体汉化独立版\tools\deployment-plan.json").read_text(encoding="utf-8"))
g = [x for x in plan["games"] if x["id"]=="tw_game"][0]
E = Path(r"E:\AzurPromilia_TC\AzurPromilia_TC_game")
D = Path(r"D:\windows\Desktop\蓝色星原简体汉化独立版\payload\tw_game")
print("%-62s %-9s %-9s %-9s" % ("file","E盘","payload","判定"))
for f in g["files"]:
    rel = f["relative_path"]
    pe = E/rel; pd = D/rel
    def sh(p):
        return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None
    se, sd = sh(pe), sh(pd)
    tag = lambda h: "SOURCE" if h==f["source_sha256"] else ("TARGET" if h==f["target_sha256"] else ("PREV" if h in f.get("previous_sha256",[]) else "?其它"))
    print("%-62s %-9s %-9s %-9s" % (rel[-62:], tag(se), tag(sd), "同" if se==sd else "异"))
