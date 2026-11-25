import sys,json
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,r'C:\Users\xiaoxi\Documents\Codex\2026-11-24\new-chat\work\game_decrypt_paths\pylibs')
import pefile
from capstone import Cs,CS_ARCH_X86,CS_MODE_64
DLL=Path(r'E:\AzurPromilia_TC\AzurPromilia_TC_game\GameAssembly.dll')
pe=pefile.PE(str(DLL),fast_load=True);md=Cs(CS_ARCH_X86,CS_MODE_64)
out=[]
with DLL.open('rb') as f:
 for name,rva,n in [('VStringHashWR.BeginRead',0x67E1C50,800),('VStringHashWR.GetVString',0x67E2360,1200),('VStringHashWR.GetBucketIndex',0x67E2160,150),('TableMgr.GetMMapStream',0x508DB10,1500)]:
  off=pe.get_offset_from_rva(rva);f.seek(off);code=f.read(n);out.append('### '+name)
  for i in md.disasm(code,pe.OPTIONAL_HEADER.ImageBase+rva):out.append(f'{i.address:x} {i.mnemonic:9} {i.op_str}')
(HERE/'layout_disassembly.txt').write_text('\n'.join(out),'utf-8')
print('Static read-only disassembly saved:',len(out),'lines')
