import sys,struct,json,collections
from pathlib import Path
OLD=Path(r'C:\Users\xiaoxi\Documents\Codex\2026-11-24\new-chat\work')
sys.path[:0]=[str(OLD/'game_compare_manifests'),str(OLD/'game_decrypt_paths')]
from parse_language_tables import read_index
HERE=Path(__file__).resolve().parent
b=(HERE/'source_table.bin').read_bytes();base,langs,end=read_index(b)
print('base',list(base.items())[:10],'langs',[(k,list(v.items())[:2]) for k,v in langs.items()])
for k,off in list(langs['cht'].items())[:4]+list(langs['en'].items())[:2]:
 p=off-4120;n=struct.unpack_from('<I',b,p)[0];t=b[p+4:p+4+n];c,r,*lens=struct.unpack_from('>6I',t,8);s=36+sum(lens)
 print(k,'len',n,'head',t[:150].hex(' '),'fields',c,r,lens,'u32_32',t[32:36].hex(),'index',t[s:s+80].hex(' '),'rows',t[s+8+struct.unpack_from('<I',t,s+4)[0]:][:60].hex(' '))
