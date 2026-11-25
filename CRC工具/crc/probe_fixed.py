import sys, json, struct, hashlib, collections, time
from pathlib import Path
HERE=Path(__file__).resolve().parent
OLD=Path(r'C:\Users\xiaoxi\Documents\Codex\2026-11-24\new-chat\work')
sys.path[:0]=[str(OLD/'game_decrypt_bundle'),str(OLD/'game_compare_manifests'),str(OLD/'game_decrypt_paths'),str(OLD/'game_mmap'),str(OLD/'analysis_deps')]
from unity_setup import UnityPy
from UnityPy.streams import EndianBinaryReader
from UnityPy.helpers import ArchiveStorageManager as asm
from parse_language_tables import read_index,read_rows
from decode_mmap import decode_file
from vstring_pool import VStringPool
import crcchain as C
DATA=Path(r'E:\AzurPromilia_TC\AzurPromilia_TC_game\AzurPromilia_Data')
PAY=Path(r'D:\windows\Desktop\蓝色星原简体汉化独立版\payload\tw_game')
def emit(x): print(json.dumps(x,ensure_ascii=False),flush=True)
def ufs(raw):
 r=EndianBinaryReader(raw);r.read_string_to_null();r.read_u_int();r.read_string_to_null();r.read_string_to_null();hp=r.Position
 size=r.read_long();cs=r.read_u_int();us=r.read_u_int();fl=r.read_u_int();he=r.Position
 if fl&0x400: asm.ArchiveStorageDecryptor(r)
 ep=r.Position;r.align_stream(16);start=r.Position
 e=UnityPy.load(raw);bu=next(iter(e.files.values()))
 ci=raw[size-cs:size] if fl&128 else raw[start:start+cs]
 inf=bu.decompress_data(ci,us,fl);n=struct.unpack_from('>I',inf,16)[0]
 blockend=start if fl&128 else start+cs
 blockstart=(blockend+15)//16*16 if fl&512 else blockend
 blocks=[struct.unpack_from('>IIH',inf,20+10*i) for i in range(n)]
 return {'size':size,'flags':fl,'headerpos':hp,'headerend':he,'encryption_end':ep,'start':start,'header_padding':start-ep,'info_size':cs,'blockstart':blockstart,'info_padding':blockstart-blockend,'blocks':blocks,'objects':len(list(e.objects))},e
def main():
 manifests={};base=[]
 for mp,bd,nn in __import__('now_cases').CASES:
  p=DATA/mp;raw=p.read_bytes();m=manifests.setdefault(mp,C.parse(raw));hp=p.with_suffix('.hash')
  emit({'manifest':mp,'md5_matches':hp.read_bytes().strip().lower()==hashlib.md5(raw).hexdigest().encode()})
  base.append({'relative_path':mp,'sha256':hashlib.sha256(raw).hexdigest()})
  base.append({'relative_path':str(Path(mp).with_suffix('.hash')),'sha256':hashlib.sha256(hp.read_bytes()).hexdigest()})
  pm=C.parse((PAY/mp).read_bytes())
  for name in nn:
   rel=str(Path(bd)/name);src=(DATA/rel).read_bytes();tar=(PAY/rel).read_bytes()
   i=next(i for i,p in enumerate(m['packs']) if C.name_of(p)==name);j=next(i for i,p in enumerate(pm['packs']) if C.name_of(p)==name)
   emit({'pack':name,'size':len(src),'target_size':len(tar),'original_verified':not C.verify(raw,DATA/rel)})
   base.append({'relative_path':rel,'sha256':hashlib.sha256(src).hexdigest(),'size':len(src),'crc':m['packs'][i]['crc']})
   if src[:7]!=b'UnityFS':continue
   ss=C.segments(m,i);ts=C.segments(pm,j)
   for (bi,off,sz),(tj,to,tn) in zip(ss,ts):
    a=src[off:off+sz];b=tar[to:to+tn]
    if a==b:continue
    sa,ea=ufs(a);sb,eb=ufs(b)
    types=collections.Counter(o.type.name for o in eb.objects)
    emit({'bundle':name,'index':bi,'offset':off,'old':sa,'target':sb,'types':dict(types)})
    for o in eb.objects:
     if o.type.name=='Font':
      t=o.read_typetree();emit({'font':t.get('m_Name'),'bytes':len(t.get('m_FontData',[]))})
 (HERE/'baseline.json').write_text(json.dumps(base,ensure_ascii=False,indent=2),'utf-8')
 # Find gaps between top-level table records; only actual unreferenced ranges qualify.
 rel='.res/raw_streaming_package/BundleFiles/3iffxeedh2grvnbn2iag.r'
 for tag,root in [('source',DATA),('target',PAY)]:
  dest=HERE/(tag+'_table.bin');decode_file(root/rel,dest);data=dest.read_bytes();bt,langs,head=read_index(data)
  starts=sorted(set(bt.values())|{v for tab in langs.values() for v in tab.values()})
  spans=[(0,head)]
  for off in starts:
   p=off-4120;n=struct.unpack_from('<I',data,p)[0];spans.append((p,p+4+n))
  cursor=0;gaps=[]
  for a,b in sorted(spans):
   if a>cursor:gaps.append((cursor,a))
   cursor=max(cursor,b)
  if cursor<len(data):gaps.append((cursor,len(data)))
  emit({'table':tag,'size':len(data),'gaps':gaps[:25],'total_gap':sum(b-a for a,b in gaps),'langs':{k:len(v) for k,v in langs.items()}})
if __name__=='__main__':main()
