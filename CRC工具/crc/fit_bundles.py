"""Repack localized UnityFS segments within original immutable manifest slots.

Only workspace candidates are written. Alignment padding holds CRC fixups.
"""
import sys,struct,json,io,hashlib,os,zlib,time,warnings
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
HERE=Path(__file__).resolve().parent
OLD=Path(os.environ.get('AZUR_WORK_DIR', r'C:\Users\xiaoxi\Documents\Codex\2026-11-24\new-chat\work'))
sys.path[:0]=[str(HERE.parent/'resource_decode'),str(OLD/'game_decrypt_bundle'),str(OLD/'analysis_deps'),str(OLD/'font_deps')]
from unity_setup import UnityPy
from reencrypt_bundle import encrypt_lz4
from UnityPy.streams import EndianBinaryReader
from UnityPy.helpers import ArchiveStorageManager as asm
from fontTools.ttLib import TTFont
from fontTools import subset
import lz4.block
import crcchain as C
from crcpatch import patch_crc
from now_cases import CASES
warnings.filterwarnings('ignore',message='No valid Unity version found')
DATA=Path(os.environ.get('AZUR_TW_DATA', r'E:\AzurPromilia_TC\AzurPromilia_TC_game\AzurPromilia_Data'))
PAY=Path(os.environ.get('AZUR_TW_OLD_PACK', r'D:\windows\Desktop\蓝色星原简体汉化独立版\payload\tw_game'))
OUT=HERE/'fixed_candidates'
def emit(x): print(json.dumps(x,ensure_ascii=False),flush=True)
def meta(raw):
 r=EndianBinaryReader(raw);r.read_string_to_null();r.read_u_int();r.read_string_to_null();r.read_string_to_null();hp=r.Position
 size=r.read_long();cs=r.read_u_int();us=r.read_u_int();fl=r.read_u_int();he=r.Position
 dec=asm.ArchiveStorageDecryptor(r) if fl&0x400 else None
 ep=r.Position;r.align_stream(16);start=r.Position
 bu=next(iter(UnityPy.load(raw).files.values()))
 ci=raw[size-cs:size] if fl&128 else raw[start:start+cs]
 info=bu.decompress_data(ci,us,fl);count=struct.unpack_from('>I',info,16)[0]
 p=start if fl&128 else start+cs
 if fl&512:p=(p+15)//16*16
 chunks=[]
 for i in range(count):
  u,c,f=struct.unpack_from('>IIH',info,20+10*i)
  d=bu.decompress_data(raw[p:p+c],u,f,i);assert len(d)==u;p+=c;chunks.append(d)
 return hp,he,ep,dec,info,b''.join(chunks)
def repack(raw,original,slot,algorithm='lz4',blocksize=131072):
 hp,he,ep,dec,info,plain=meta(raw)
 _,ohe,oep,odec,_,_=meta(original)
 assert raw[he:ep]==original[ohe:oep]
 compressed=[];entries=[]
 for i,p in enumerate(range(0,len(plain),blocksize)):
  chunk=plain[p:p+blocksize]
  c=lz4.block.compress(chunk,mode='high_compression',compression=12,store_size=False)
  if len(c)>=len(chunk):c=chunk;fl=0
  else:c=encrypt_lz4(c,i,odec);fl=0x103
  compressed.append(c);entries.append((len(chunk),len(c),fl))
 n=struct.unpack_from('>I',info,16)[0]
 ni=info[:16]+struct.pack('>I',len(entries))+b''.join(struct.pack('>IIH',*x) for x in entries)+info[20+10*n:]
 ci=lz4.block.compress(ni,mode='high_compression',compression=12,store_size=False)
 head=bytearray(raw[:he]);struct.pack_into('>QIII',head,hp,slot,len(ci),len(ni),0x643)
 out=head+original[ohe:oep];freepos=len(out);out.extend(bytes((-len(out))%16));assert len(out)-freepos>=4
 out+=ci;out.extend(bytes((-len(out))%16));out+=b''.join(compressed)
 actual=len(out)
 if actual>slot: return None,{'compressed':actual,'slot':slot,'overflow':actual-slot}
 out.extend(bytes(slot-len(out)))
 assert patch_crc(out,zlib.crc32(original)&0xffffffff,freepos)
 check=UnityPy.load(bytes(out));b=next(iter(check.files.values()))
 _,_,_,_,_,roundtrip=meta(bytes(out));assert roundtrip==plain
 return bytes(out),{'compressed':actual,'slot':slot,'padding':slot-actual,'fixup_offset':freepos,'objects':len(list(check.objects))}
def font_subset(raw,corpus):
 env=UnityPy.load(raw);changed=[]
 for obj in env.objects:
  if obj.type.name!='Font':continue
  t=obj.read_typetree();fd=bytes(t.get('m_FontData',[]))
  if t.get('m_Name','').endswith('_origin'):continue
  if not fd:continue
  f=TTFont(io.BytesIO(fd));cmap=f.getBestCmap() or {};required=set(cmap)&corpus
  opt=subset.Options();opt.recalc_timestamp=False;opt.retain_gids=False;opt.notdef_glyph=True;opt.notdef_outline=True
  sub=subset.Subsetter(options=opt);sub.populate(unicodes=required);sub.subset(f)
  dest=io.BytesIO();f.save(dest);new=dest.getvalue();nf=TTFont(io.BytesIO(new));after_cmap=nf.getBestCmap() or {}
  missing=required-set(after_cmap);extra=set(after_cmap)-required
  if missing or extra:emit({'font_cmap_difference':t['m_Name'],'missing':sorted(missing),'extra':sorted(extra),'missing_glyphs':{str(cp):cmap[cp] for cp in missing}})
  assert all(cmap[cp]=='.notdef' for cp in missing),(t['m_Name'],missing)
  t['m_FontData']=list(new);obj.save_typetree(t);changed.append({'font':t['m_Name'],'old':len(fd),'new':len(new),'kept_codepoints':len(required),'original_codepoints':len(cmap)})
 return next(iter(env.files.values())).save(packer='lz4'),changed
def main():
 OUT.mkdir(exist_ok=True)
 # Full simplified CJK repertoire plus original traditional text coverage is
 # deliberately NOT assumed here: use actual corpus and common dynamic chars.
 corpus=set(range(32,127))|set(range(0x3000,0x3100))|set(range(0xff00,0xfff0))
 corpus_file=HERE/'corpus_codepoints.json'
 if corpus_file.exists():corpus.update(json.loads(corpus_file.read_text()))
 for lead in range(0xa1,0xf8):
  for trail in range(0xa1,0xff):
   try:corpus.update(map(ord,bytes([lead,trail]).decode('gb2312')))
   except UnicodeDecodeError:pass
 report=[]
 for mp,bd,names in CASES:
  if 'raw_' in bd:continue
  if '--static' in sys.argv and 'static_package' not in bd:continue
  m=C.parse((DATA/mp).read_bytes());tm=C.parse((PAY/mp).read_bytes())
  for name in names:
   src=(DATA/bd/name).read_bytes();tar=(PAY/bd/name).read_bytes();out=bytearray(src)
   pi=next(i for i,p in enumerate(m['packs']) if C.name_of(p)==name);ti=next(i for i,p in enumerate(tm['packs']) if C.name_of(p)==name)
   changes=[]
   for (bi,off,sz),(_,to,tn) in zip(C.segments(m,pi),C.segments(tm,ti)):
    a=src[off:off+sz];b=tar[to:to+tn]
    if a==b:continue
    env=UnityPy.load(b);hasfont=any(o.type.name=='Font' for o in env.objects)
    if hasfont and (len(b)>len(a)*1.2 or 'static_package' in bd):
     if not corpus_file.exists():emit({'waiting_for':'corpus','pack':name,'segment':bi});continue
     plain,fonts=font_subset(b,corpus)
     # Save generates an unencrypted bundle; reconstruct input with source
     # envelope via the existing, roundtrip-tested wrapper.
     from reencrypt_bundle import wrap
     b,_=wrap(plain,a);emit({'pack':name,'segment':bi,'font_subset':fonts})
    candidate,rep=repack(b,a,sz)
    if candidate is None:
     emit({'pack':name,'segment':bi,'fit':False,**rep});changes.append({'segment':bi,'ok':False,**rep});continue
    out[off:off+sz]=candidate
    emit({'pack':name,'segment':bi,'fit':True,**rep});changes.append({'segment':bi,'ok':True,**rep})
   ok=bool(changes) and all(x['ok'] for x in changes)
   if ok:
    dest=OUT/bd/name;dest.parent.mkdir(exist_ok=True,parents=True);dest.write_bytes(out)
    assert not C.verify((DATA/mp).read_bytes(),dest)
   report.append({'pack':name,'complete':ok,'changes':changes})
 rp=HERE/'fit_bundles_report.json'
 if '--static' in sys.argv and rp.exists():report=[x for x in json.loads(rp.read_text('utf-8')) if x['pack'] not in {y['pack'] for y in report}]+report
 rp.write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
if __name__=='__main__':main()

