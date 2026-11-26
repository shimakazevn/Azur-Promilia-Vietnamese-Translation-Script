from pathlib import Path
import struct,json,sys,collections
from vstring_pool import VStringPool
ROOT=Path('work/game_decrypt_paths')
def read_index(p):
 i=0
 def u():
  nonlocal i
  v=struct.unpack_from('<I',p,i)[0];i+=4;return v
 def s():
  nonlocal i
  n=u();v=p[i:i+n].decode();i+=n;return v
 base={s():u() for _ in range(u())};langs={}
 for z in range(u()):langs[s()]={s():u() for _ in range(u())}
 return base,langs,i
# Assignment evaluation order matters: language key must be read before count.
def read_index(p):
 i=0
 def u():
  nonlocal i
  v=struct.unpack_from('<I',p,i)[0];i+=4;return v
 def s():
  nonlocal i
  n=u();v=p[i:i+n].decode();i+=n;return v
 n=u();base={s():u() for _ in range(n)};ln=u();langs={}
 for z in range(ln):
  lang=s();n=u();langs[lang]={s():u() for _ in range(n)}
 return base,langs,i

def read_rows(p,physical,pool):
 off=physical-4120;n=struct.unpack_from('<I',p,off)[0];start=off+4;t=p[start:start+n];assert t[:8]==b'LRGB1001';col,row,*lens=struct.unpack_from('>6I',t,8);assert col==2,col
 pos=36+sum(lens);rows=[]
 stride,idbytes=struct.unpack_from('<II',t,pos);assert stride==12 or row==3,(stride,row)
 pos+=8+idbytes
 for r in range(row-3):
  key,val=struct.unpack_from('<qI',t,pos);rows.append({'id':key,'key':val,'value':pool[val],'value_offset':start+pos+8});pos+=12
 assert pos==n,(pos,n,row,idbytes)
 return rows
if __name__=='__main__':
 allrows={}
 for region,poolname in [('tw','tw_update_v0k2cafcxjxawklow6skg.bin'),('cn','cn_update_bjzqzapbodx6zodmvtrta.bin')]:
  p=(ROOT/(region+'-update-table-data.bin')).read_bytes();pool=VStringPool(Path('work/game_mmap/decoded')/poolname);base,langs,end=read_index(p);print(region,len(base),[(k,len(v)) for k,v in langs.items()],end,flush=True)
  result={lang:{name:read_rows(p,o,pool) for name,o in tables.items()} for lang,tables in langs.items()}
  (ROOT/(region+'-language-rows.json')).write_text(json.dumps(result,ensure_ascii=False,separators=(',',':')),encoding='utf8');allrows[region]=result
 tw=allrows['tw']['cht'];cn=allrows['cn'].get('chs',{});counts=collections.Counter();coverage=[];candidates=[];missing=[]
 for table,rows in tw.items():
  ref={x['id']:x for x in cn.get(table,[])};nmatch=0
  for row in rows:
   counts['tw_rows']+=1
   if row['id'] not in ref:missing.append({'table':table,'id':row['id'],'tw':row['value']});continue
   rr=ref[row['id']];counts['matched']+=1;nmatch+=1
   if row['value']!=rr['value']:
    counts['different']+=1;candidates.append({'table':table,'id':row['id'],'tw_key':row['key'],'cn_key':rr['key'],'tw_offset':row['value_offset'],'tw':row['value'],'cn':rr['value']})
   else:counts['same']+=1
  coverage.append({'table':table,'rows':len(rows),'matched':nmatch})
 report={'counts':dict(counts),'tables':coverage,'missing':missing};(ROOT/'language-coverage.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8');(ROOT/'official-cn-candidates.json').write_text(json.dumps(candidates,ensure_ascii=False,separators=(',',':')),encoding='utf8');print(dict(counts),flush=True);print(candidates[:3],flush=True)
