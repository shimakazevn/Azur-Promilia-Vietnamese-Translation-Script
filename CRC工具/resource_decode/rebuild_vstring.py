"""Rebuild decrypted vstring file, preserving existing numeric keys.

Appended text hashes are copied from official CN pool, not guessed.
"""
import struct
from array import array
from vstring_pool import VStringPool

class HashIndex:
 def __init__(self,pool):
  self.pool=pool;self.data=pool.data
  self.total,self.start,self.offset_start,self.hash_start,self.capacity,self.count=struct.unpack_from('<6I',self.data)
  self.offsets=array('I');self.offsets.frombytes(self.data[self.offset_start-pool.base:self.hash_start-pool.base])
  assert len(self.offsets)==self.capacity
 def bucket(self,index):
  p=self.offsets[index]
  if not p:return []
  p-=self.pool.base;n=struct.unpack_from('<I',self.data,p)[0]
  return [struct.unpack_from('<Qi',self.data,p+4+12*i) for i in range(n)]
 def key_hashes(self):
  out={}
  for i in range(self.capacity):
   for h,k in self.bucket(i):
    assert h%self.capacity==i
    if k in out:assert out[k]==h
    out[k]=h
  return out
 def lookup(self,h,text=None):
  for candidate,key in self.bucket(h%self.capacity):
   if candidate==h and (text is None or self.pool[key]==text):return key
  return None

def rebuild(pool,additions):
 """Return decrypted bytes for additions [(utf8 string, official ulong hash)]."""
 base=pool.base;index=HashIndex(pool);by_bucket={}
 for i,(text,h) in enumerate(additions):by_bucket.setdefault(h%index.capacity,[]).append((h,pool.count+i))
 hash_payload=bytearray();offsets=array('I')
 hash_start=base+24+index.capacity*4
 for i in range(index.capacity):
  items=index.bucket(i)+by_bucket.get(i,[])
  if not items:offsets.append(0);continue
  offsets.append(hash_start+len(hash_payload));hash_payload.extend(struct.pack('<I',len(items)))
  for h,k in items:hash_payload.extend(struct.pack('<Qi',h,k))
 hash_total=24+len(offsets)*4+len(hash_payload)
 header=struct.pack('<6I',hash_total,base,base+24,hash_start,index.capacity,pool.count+len(additions))
 old_offsets=array('I');old_offsets.frombytes(pool.data[pool.offset_start-base:pool.string_start-base])
 old_payload=pool.data[pool.string_start-base:]
 extra=bytearray()
 string_start=base+hash_total+20+4*(pool.count+len(additions))
 delta=string_start-pool.string_start
 new_offsets=array('I',(o+delta for o in old_offsets))
 for text,_ in additions:
  b=text.encode('utf-8');new_offsets.append(string_start+len(old_payload)+len(extra));extra.extend(struct.pack('<i',len(b)));extra.extend(b)
 string_total=20+len(new_offsets)*4+len(old_payload)+len(extra)
 string_header=struct.pack('<5I',string_total,base+hash_total,base+hash_total+20,string_start,pool.count+len(additions))
 return header+offsets.tobytes()+hash_payload+string_header+new_offsets.tobytes()+old_payload+extra

def additions_from_cn(tw,cn,cn_keys):
 """Reuse existing exact TW strings; otherwise append CN text + official hash.

 Returns (additions, map_cn_key_to_tw_key).
 """
 ti=HashIndex(tw);ci=HashIndex(cn);hashes=ci.key_hashes();added={};mapping={};items=[]
 for key in cn_keys:
  text=cn[key]
  if text is None:mapping[key]=0;continue
  h=hashes[key];found=ti.lookup(h,text)
  if found is not None:mapping[key]=found;continue
  token=(text,h)
  if token not in added:added[token]=tw.count+len(items);items.append(token)
  mapping[key]=added[token]
 return items,mapping

def append_custom_texts(tw,texts,existing_items=()):
 """Return append items and text->key, using validated native short hash.

 Optional existing_items carries official CN additions already planned.
 Resource paths and >=192 UTF8 bytes are intentionally unsupported.
 """
 from vstring_hash import text_hash
 index=HashIndex(tw);items=list(existing_items)
 planned={s:tw.count+i for i,(s,h) in enumerate(items)};mapping={}
 for text in texts:
  if text.startswith(('Assets/','assets/')):raise ValueError('Resource paths use special hash normalization')
  h=text_hash(text)
  if text in planned:mapping[text]=planned[text];continue
  found=index.lookup(h,text)
  if found is not None:mapping[text]=found;continue
  planned[text]=tw.count+len(items);mapping[text]=planned[text];items.append((text,h))
 return items,mapping
