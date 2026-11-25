import json, hashlib
from pathlib import Path
P = Path(r"D:\windows\Desktop\蓝色星原简体汉化独立版\payload\tw_game")
E = Path(r"E:\AzurPromilia_TC\AzurPromilia_TC_game\AzurPromilia_Data")
plan = json.load(open(r"D:\windows\Desktop\蓝色星原简体汉化独立版\tools\deployment-plan.json", encoding="utf-8"))
tw = [g for g in plan["games"] if g["id"]=="tw_game"][0]
print("%-62s %-10s %-10s %-10s" % ("file","cur==src","cur==tgt","payload==tgt"))
for f in tw["files"]:
    rp = f["relative_path"]
    cur = E/rp
    if not cur.exists():
        print("%-62s MISSING" % rp); continue
    h = hashlib.sha256(cur.read_bytes()).hexdigest()
    pl = P/rp
    ph = hashlib.sha256(pl.read_bytes()).hexdigest() if pl.exists() else "-"
    print("%-62s %-10s %-10s %-10s" % (rp[:62], h==f["source_sha256"], h==f["target_sha256"], ph==f["target_sha256"]))
