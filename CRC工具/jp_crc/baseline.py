"""Read-only inventory and verified original snapshot for JP CRC localization."""
from pathlib import Path
import hashlib,json,os,shutil,sys
HERE=Path(__file__).resolve().parent
OLD=Path(os.environ.get('AZUR_WORK_DIR', r'C:\Users\xiaoxi\Documents\Codex\2026-11-24\new-chat\work'))
JP=OLD/'jp_localization'
LIVE=Path(os.environ.get('AZUR_JP_ROOT', r'E:\YostarGames\AZUPRO_JP'))/'AzurPromiliaJP_Data'
BACK=LIVE.parent/'.zhcn-jp-3219598-backup'
ORIG=HERE/'originals'
PAY=JP/'game_candidate'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 plan=json.loads((JP/'deployment-plan.json').read_text('utf-8'))
 entries={f['relative_path']:f for f in plan['files']}
 rows=[]
 for rel,f in entries.items():
  src=BACK/rel
  assert src.is_file() and sha(src)==f['source_sha256'],('invalid original',rel)
  assert sha(PAY/rel)==f['target_sha256'],('invalid localized source',rel)
  dest=ORIG/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dest)
  h=sha(LIVE/rel)
  state='original' if h==f['source_sha256'] else 'old_localized' if h==f['target_sha256'] else 'other'
  rows.append({'relative_path':rel,'original_size':src.stat().st_size,'target_size':f['size'],'live_state':state,'live_sha256':h,'source_sha256':f['source_sha256']})
 # Additional baseline files are snapshot-only; provenance of unpack manifests
 # must not be assumed simply because they were not listed by the old patch.
 guards=[]
 for rel in entries:
  if not rel.endswith('.bytes'):continue
  p=LIVE/rel
  for q in p.parent.iterdir():
   if not q.is_file() or q.suffix not in ('.bytes','.hash'):continue
   r=q.relative_to(LIVE).as_posix()
   if r in entries:continue
   dest=ORIG/r;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(q,dest)
   guards.append({'relative_path':r,'sha256':sha(q),'provenance':'installed auxiliary baseline, not an authenticity proof'})
 result={'region':'jp','update_version':'3219598','builtin_version':'3075915','files':rows,'auxiliary_guards':guards,'live_untouched':True}
 (HERE/'baseline.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf-8')
 print(json.dumps({'originals_verified':len(rows),'live_states':{s:sum(x['live_state']==s for x in rows) for s in ('original','old_localized','other')},'auxiliary':len(guards)},ensure_ascii=False))
if __name__=='__main__':main()

