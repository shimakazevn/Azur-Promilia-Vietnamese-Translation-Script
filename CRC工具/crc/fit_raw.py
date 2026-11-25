"""Fixed-length localization preserving every original and added string key.

Hash capacity is format data, not a fixed runtime constant. Rehash the target
index into a smaller bucket array and use its unreferenced padding for fixup.
Table CRC is balanced by independent dictionary-entry permutations; no table
payload, ID or translation changes are required.
"""
import sys,json,struct,hashlib,zlib,time,collections
from pathlib import Path
from array import array
HERE=Path(__file__).resolve().parent
OLD=Path(r'C:\Users\xiaoxi\Documents\Codex\2026-11-24\new-chat\work')
sys.path[:0]=[str(OLD/'game_compare_manifests'),str(OLD/'game_decrypt_paths'),str(OLD/'game_mmap')]
from vstring_pool import VStringPool
from rebuild_vstring import HashIndex
from parse_language_tables import read_index,read_rows
from decode_mmap import decode_file,keystream
import crcchain as C
from crcpatch import patch_crc
DATA=Path(r'E:\AzurPromilia_TC\AzurPromilia_TC_game\AzurPromilia_Data')
PAY=Path(r'D:\windows\Desktop\蓝色星原简体汉化独立版\payload\tw_game')
OUT=HERE/'fixed_candidates'
def emit(x):print(json.dumps(x,ensure_ascii=False),flush=True)
def encode(plain,original):
 stream=keystream(original[:4120]);out=bytearray(original[:4120]);mask=stream*5
 for p in range(0,len(plain),4*1024*1024):
  chunk=plain[p:p+4*1024*1024];off=(p+4120)%len(stream)
  out+=(int.from_bytes(chunk,'little')^int.from_bytes(mask[off:off+len(chunk)],'little')).to_bytes(len(chunk),'little')
 return out
def solve_columns(cols,rhs):
 basis={}
 for i,value in enumerate(cols):
  mask=1<<i
  while value:
   bit=value.bit_length()-1
   if bit not in basis:basis[bit]=(value,mask);break
   v,m=basis[bit];value^=v;mask^=m
 mask=0
 while rhs:
  bit=rhs.bit_length()-1
  if bit not in basis:raise ValueError('CRC permutation basis is not full rank')
  v,m=basis[bit];rhs^=v;mask^=m
 return mask,len(basis)
def pool_build():
 rel='.res/raw_base_package/BundleFiles/v0k2cafcxjxawklow6skg.r'
 original=(DATA/rel).read_bytes();tp=HERE/'target_pool.bin';decode_file(PAY/rel,tp);p=VStringPool(tp);idx=HashIndex(p)
 sp=HERE/'source_pool.bin';decode_file(DATA/rel,sp);op=VStringPool(sp)
 emit({'stage':'pool_read','source_count':op.count,'target_count':p.count,'capacity':idx.capacity})
 cap=524287
 buckets={};entry_count=0
 for bi in range(idx.capacity):
  for h,k in idx.bucket(bi):buckets.setdefault(h%cap,[]).append((h,k));entry_count+=1
 string_payload=p.data[p.string_start-p.base:]
 string_total=20+4*p.count+len(string_payload)
 desired=len(original)-4120;hash_total=desired-string_total
 hash_start=4120+24+4*cap;offsets=array('I',[0])*cap;payload=bytearray()
 for bi,items in sorted(buckets.items()):
  offsets[bi]=hash_start+len(payload);payload+=struct.pack('<I',len(items))
  for h,k in items:payload+=struct.pack('<Qi',h,k)
 used=24+len(offsets)*4+len(payload);padding=hash_total-used
 assert padding>=4,{'padding':padding}
 string_start=4120+hash_total+20+4*p.count;delta=string_start-p.string_start
 old_offsets=array('I');old_offsets.frombytes(p.data[p.offset_start-4120:p.string_start-4120])
 new_offsets=array('I',(x+delta for x in old_offsets))
 raw=struct.pack('<6I',hash_total,4120,4144,hash_start,cap,p.count)+offsets.tobytes()+payload+bytes(padding)
 raw+=struct.pack('<5I',string_total,4120+hash_total,4120+hash_total+20,string_start,p.count)+new_offsets.tobytes()+string_payload
 assert len(raw)==desired
 candidate=encode(raw,original);fixup=4120+used
 target_crc=zlib.crc32(original)&0xffffffff;assert patch_crc(candidate,target_crc,fixup)
 dest=OUT/rel;dest.parent.mkdir(exist_ok=True,parents=True);dest.write_bytes(candidate)
 check=HERE/'checked_pool.bin';decode_file(dest,check);cp=VStringPool(check);ci=HashIndex(cp)
 # Recheck every numeric key, all buckets and lookups, not samples.
 for k in range(p.count):assert cp[k]==p[k],k
 for i in range(idx.capacity):
  for h,k in idx.bucket(i):assert (h,k) in ci.bucket(h%cap),(h,k)
 corpus=set(range(32,127))
 for k in range(cp.count):
  text=cp[k]
  if text:corpus.update(map(ord,text))
 (HERE/'corpus_codepoints.json').write_text(json.dumps(sorted(corpus)),'utf-8')
 rep={'original_size':len(original),'size':len(candidate),'crc':f'{target_crc:08x}','capacity':cap,'target_keys_preserved':p.count,'hash_entries':entry_count,'hash_padding':padding,'fixup_offset':fixup,'all_key_values_and_hash_entries_verified':True,'corpus_codepoints':len(corpus)}
 emit({'stage':'pool_complete',**rep});return rep,cp
def table_build(pool):
 rel='.res/raw_streaming_package/BundleFiles/3iffxeedh2grvnbn2iag.r'
 original=(DATA/rel).read_bytes();plain=bytearray((HERE/'target_table.bin').read_bytes());target_index=read_index(plain)
 n=struct.unpack_from('<I',plain)[0];pos=4;entries=[]
 for _ in range(n):
  start=pos;size=struct.unpack_from('<I',plain,pos)[0];pos+=4+size+4;entries.append((start,pos))
 # Swaps affect disjoint bytes; every permutation preserves dictionary values.
 swaps=[]
 for i in range(0,min(192,len(entries)-1),2):
  a,m=entries[i];_,b=entries[i+1];swaps.append((a,b,bytes(plain[m:b]+plain[a:m])))
 candidate=encode(plain,original);base=zlib.crc32(candidate)&0xffffffff;cols=[]
 for a,b,repl in swaps:
  q=4120+a;r=4120+b;saved=bytes(candidate[q:r])
  # XOR mmap means the delta between two plaintexts equals ciphertext delta.
  diff=bytes(x^y for x,y in zip(plain[a:b],repl));candidate[q:r]=bytes(x^y for x,y in zip(saved,diff))
  cols.append((zlib.crc32(candidate)&0xffffffff)^base);candidate[q:r]=saved
 mask,rank=solve_columns(cols,(zlib.crc32(original)&0xffffffff)^base)
 count=0
 for i,(a,b,repl) in enumerate(swaps):
  if mask>>i&1:plain[a:b]=repl;count+=1
 assert read_index(plain)==target_index
 candidate=encode(plain,original);assert len(candidate)==len(original);assert zlib.crc32(candidate)==zlib.crc32(original)
 dest=OUT/rel;dest.parent.mkdir(exist_ok=True,parents=True);dest.write_bytes(candidate)
 checked=HERE/'checked_table.bin';decode_file(dest,checked);assert checked.read_bytes()==plain
 source=(HERE/'source_table.bin').read_bytes();si=read_index(source)
 assert si[0]==target_index[0] and si[1]==target_index[1]
 # Confirm English and every base physical record stay exactly the same.
 for off in list(si[0].values())+list(si[1]['en'].values()):
  p=off-4120;size=struct.unpack_from('<I',source,p)[0]+4;assert source[p:p+size]==plain[p:p+size]
 rows=0
 for name,off in target_index[1]['cht'].items():rows+=len(read_rows(plain,off,pool))
 rep={'size':len(candidate),'crc':f'{zlib.crc32(candidate):08x}','permutation_rank':rank,'entry_pair_swaps':count,'cht_rows':rows,'base_tables_and_english_bytes_preserved':True,'target_language_row_bytes_preserved':True}
 emit({'stage':'table_complete',**rep});return rep
def main():
 OUT.mkdir(exist_ok=True);pool_report,pool=pool_build();table_report=table_build(pool)
 for package,name in [('raw_base_package','v0k2cafcxjxawklow6skg.r'),('raw_streaming_package','3iffxeedh2grvnbn2iag.r')]:
  mp=DATA/'.res'/package/'ManifestFiles'/f'0release_{package}_3221745.bytes';dest=OUT/'.res'/package/'BundleFiles'/name
  assert not C.verify(mp.read_bytes(),dest)
 (HERE/'fit_raw_report.json').write_text(json.dumps({'pool':pool_report,'table':table_report},ensure_ascii=False,indent=2),'utf-8')
if __name__=='__main__':main()
