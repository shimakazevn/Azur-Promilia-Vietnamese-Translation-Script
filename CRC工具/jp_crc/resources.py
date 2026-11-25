"""Only localize the bootstrap TextAsset; keep embedded SDK locales unchanged."""
from pathlib import Path
import json,sys,struct,hashlib
HERE=Path(__file__).resolve().parent
sys.path[:0]=[str(HERE.parent/'crc'),str(HERE)]
import fit_bundles as B
from baseline import ORIG,PAY
UnityPy=B.UnityPy
def main():
 src=(ORIG/'resources.assets').read_bytes();tar=(PAY/'resources.assets').read_bytes()
 env=UnityPy.load(src);tenv=UnityPy.load(tar)
 before={o.path_id:o.get_raw_data() for o in env.objects}
 bootstrap={}
 for o in tenv.objects:
  if o.type.name=='TextAsset' and o.read_typetree().get('m_Name')=='builtInLangString':bootstrap[o.path_id]=o.get_raw_data()
 assert len(bootstrap)==1
 for o in env.objects:
  if o.path_id in bootstrap:o.set_raw_data(bootstrap[o.path_id])
 saved=bytearray(env.file.save());unpadded=len(saved);assert len(saved)<=len(src),(len(saved),len(src))
 saved.extend(bytes(len(src)-len(saved)))
 version=struct.unpack_from('>I',saved,8)[0]
 if version>=22:struct.pack_into('>q',saved,24,len(saved))
 else:struct.pack_into('>I',saved,4,len(saved))
 checked=UnityPy.load(bytes(saved));after={o.path_id:o.get_raw_data() for o in checked.objects}
 assert before.keys()==after.keys()
 changed=[key for key in before if before[key]!=after[key]];assert changed==list(bootstrap)
 for key in before:assert after[key]==bootstrap.get(key,before[key])
 dest=HERE/'fixed_candidates/resources.assets';dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(saved)
 report={'size':len(saved),'original_size':len(src),'unpadded_size':unpadded,'padding':len(src)-unpadded,'changed_objects':changed,'only_bootstrap_text_asset_changed':True,'embedded_sdk_locales_original':True,'all_other_objects_preserved':True,'roundtrip_verified':True,'sha256':hashlib.sha256(saved).hexdigest()}
 (HERE/'resources_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8');print(json.dumps(report,ensure_ascii=False))
if __name__=='__main__':main()
