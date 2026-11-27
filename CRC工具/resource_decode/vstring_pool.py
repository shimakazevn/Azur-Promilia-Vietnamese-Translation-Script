"""Read decrypted vstring.bytes without touching installed clients.

Positions in decoded files retain their original encrypted-file base (4120).
"""
from pathlib import Path
import struct
class VStringPool:
 def __init__(self,path):
  self.path=Path(path);self.data=self.path.read_bytes();b=self.data
  self.hash_size=struct.unpack_from('<I',b)[0]
  self.total,self.start,self.offset_start,self.string_start,self.count=struct.unpack_from('<5I',b,self.hash_size)
  self.base=self.start-self.hash_size
  assert self.base==4120,(self.path,self.base)
  assert self.hash_size+self.total==len(b)
 def location(self,key):
  if key<0 or key>=self.count:raise IndexError(key)
  p=struct.unpack_from('<I',self.data,self.offset_start-self.base+key*4)[0]-self.base
  n=struct.unpack_from('<i',self.data,p)[0]
  return p,n
 def get(self,key):
  p,n=self.location(key)
  return None if n<0 else self.data[p+4:p+4+n].decode('utf-8')
 def __getitem__(self,key):return self.get(key)
 def __len__(self):return self.count
if __name__=='__main__':
 import sys,json
 pool=VStringPool(sys.argv[1]);print(json.dumps({'count':pool.count,'base':pool.base,'samples':{k:pool[k] for k in map(int,sys.argv[2:])}},ensure_ascii=False,indent=2))
