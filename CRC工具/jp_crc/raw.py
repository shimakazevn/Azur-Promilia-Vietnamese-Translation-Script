"""Build JP fixed-size pool and table candidates without touching manifests."""
from pathlib import Path
from array import array
import hashlib,json,struct,sys,zlib
HERE=Path(__file__).resolve().parent
sys.path[:0]=[str(HERE.parent/'crc'),str(HERE)]
import fit_raw as F
import crcchain as C
from baseline import ORIG,PAY
VStringPool,HashIndex=F.VStringPool,F.HashIndex
def emit(**x):print(json.dumps(x,ensure_ascii=False),flush=True)
OUT=HERE/'fixed_candidates'
POOL='.res/raw_base_package/BundleFiles/z5xzl3cg6ao0ilpbzykexg.r'
TABLE='.res/raw_streaming_package/BundleFiles/fcl0wxz2z6hoffogv4xgzw.r'
def build_pool():
 original=(ORIG/POOL).read_bytes()
 F.decode_file(ORIG/POOL,HERE/'source_pool.bin');op=VStringPool(HERE/'source_pool.bin')
 F.decode_file(PAY/POOL,HERE/'target_pool.bin');p=VStringPool(HERE/'target_pool.bin');idx=HashIndex(p)
 for k in range(op.count):assert p[k]==op[k],('original key changed',k)
 emit(stage='pool_read',source_keys=op.count,target_keys=p.count,old_capacity=idx.capacity)
 items=[]
 for bi in range(idx.capacity):items.extend(idx.bucket(bi))
 string_payload=p.data[p.string_start-p.base:]
 string_total=20+4*p.count+len(string_payload)
 desired=len(original)-4120;hash_total=desired-string_total
 for cap in (1048573,524287,262139,131071,65521):
  occupied=len({h%cap for h,k in items});used=24+4*cap+4*occupied+12*len(items)
  if hash_total-used>=4:break
 else:raise ValueError('No hash capacity fits original slot')
 buckets={}
 for h,k in items:buckets.setdefault(h%cap,[]).append((h,k))
 hash_start=4120+24+4*cap;offsets=array('I',[0])*cap;payload=bytearray()
 for bi,entries in sorted(buckets.items()):
  offsets[bi]=hash_start+len(payload);payload+=struct.pack('<I',len(entries))
  for h,k in entries:payload+=struct.pack('<Qi',h,k)
 used=24+4*cap+len(payload);padding=hash_total-used;assert padding>=4
 string_start=4120+hash_total+20+4*p.count;delta=string_start-p.string_start
 old_offsets=array('I');old_offsets.frombytes(p.data[p.offset_start-4120:p.string_start-4120])
 new_offsets=array('I',(x+delta for x in old_offsets))
 raw=struct.pack('<6I',hash_total,4120,4144,hash_start,cap,p.count)+offsets.tobytes()+payload+bytes(padding)
 raw+=struct.pack('<5I',string_total,4120+hash_total,4120+hash_total+20,string_start,p.count)+new_offsets.tobytes()+string_payload
 assert len(raw)==desired
 candidate=F.encode(raw,original);crc=zlib.crc32(original);fixup=4120+used
 assert F.patch_crc(candidate,crc,fixup)
 dest=OUT/POOL;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(candidate)
 F.decode_file(dest,HERE/'checked_pool.bin');cp=VStringPool(HERE/'checked_pool.bin');ci=HashIndex(cp)
 for k in range(p.count):assert cp[k]==p[k],k
 for bi,entries in buckets.items():assert ci.bucket(bi)==entries
 corpus=set(range(32,127))
 for k in range(cp.count):
  text=cp[k]
  if text:corpus.update(map(ord,text))
 tmp=HERE/'corpus_codepoints.tmp';tmp.write_text(json.dumps(sorted(corpus)),'utf-8');tmp.replace(HERE/'corpus_codepoints.json')
 lengths=[len(x) for x in buckets.values()]
 report={'original_size':len(original),'size':len(candidate),'crc32':f'{crc:08x}','source_keys_preserved':op.count,'target_keys_preserved':p.count,'capacity':cap,'hash_entries':len(items),'maximum_bucket_entries':max(lengths),'hash_padding':padding,'fixup_offset':fixup,'all_key_values_and_hash_buckets_verified':True,'corpus_codepoints':len(corpus)}
 emit(stage='pool_complete',**report)
 return report,cp
def build_table(pool):
 original=(ORIG/TABLE).read_bytes();F.decode_file(ORIG/TABLE,HERE/'source_table.bin');F.decode_file(PAY/TABLE,HERE/'target_table.bin')
 target=(HERE/'target_table.bin').read_bytes();source=(HERE/'source_table.bin').read_bytes();plain=bytearray(target)
 si=F.read_index(source);ti=F.read_index(target);assert si==ti and set(ti[1])=={'jp'}
 n=struct.unpack_from('<I',plain)[0];pos=4;entries=[]
 for _ in range(n):
  start=pos;size=struct.unpack_from('<I',plain,pos)[0];pos+=4+size+4;entries.append((start,pos))
 swaps=[]
 for i in range(0,min(192,len(entries)-1),2):
  a,m=entries[i];_,b=entries[i+1];swaps.append((a,b,bytes(plain[m:b]+plain[a:m])))
 candidate=F.encode(plain,original);base=zlib.crc32(candidate);cols=[]
 for a,b,repl in swaps:
  q=4120+a;r=4120+b;saved=bytes(candidate[q:r]);diff=bytes(x^y for x,y in zip(plain[a:b],repl))
  candidate[q:r]=bytes(x^y for x,y in zip(saved,diff));cols.append(zlib.crc32(candidate)^base);candidate[q:r]=saved
 mask,rank=F.solve_columns(cols,zlib.crc32(original)^base);swapped=0
 for i,(a,b,repl) in enumerate(swaps):
  if mask>>i&1:plain[a:b]=repl;swapped+=1
 assert F.read_index(plain)==ti
 for off in si[0].values():
  p=off-4120;sz=struct.unpack_from('<I',source,p)[0]+4;assert source[p:p+sz]==plain[p:p+sz]
 rows=0
 for name,off in ti[1]['jp'].items():
  p=off-4120;sz=struct.unpack_from('<I',target,p)[0]+4;assert plain[p:p+sz]==target[p:p+sz]
  rows+=len(F.read_rows(plain,off,pool))
 candidate=F.encode(plain,original);assert len(candidate)==len(original) and zlib.crc32(candidate)==zlib.crc32(original)
 dest=OUT/TABLE;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(candidate)
 F.decode_file(dest,HERE/'checked_table.bin');assert (HERE/'checked_table.bin').read_bytes()==plain
 report={'size':len(candidate),'crc32':f'{zlib.crc32(candidate):08x}','permutation_rank':rank,'entry_pair_swaps':swapped,'jp_rows':rows,'base_tables_unchanged':True,'localized_row_payloads_unchanged':True,'dictionary_mapping_unchanged':True}
 emit(stage='table_complete',**report);return report
def main():
 OUT.mkdir(exist_ok=True);pr,p=build_pool();tr=build_table(p)
 for rel,pkg in ((POOL,'raw_base_package'),(TABLE,'raw_streaming_package')):
  mp=ORIG/'.res'/pkg/'ManifestFiles'/f'0release_{pkg}_3219598.bytes';assert not C.verify(mp.read_bytes(),OUT/rel)
 (HERE/'raw_report.json').write_text(json.dumps({'pool':pr,'table':tr},ensure_ascii=False,indent=2),'utf-8')
if __name__=='__main__':main()
