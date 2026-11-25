"""Read-only JP layout probe. Writes only its two sibling evidence files."""
import hashlib, json, re, struct, sys
from pathlib import Path
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
OLD = Path(r"C:\Users\xiaoxi\Documents\Codex\2026-11-24\new-chat\work\game_decrypt_paths")
sys.path.insert(0, str(OLD / 'pylibs'))
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_IMM, X86_OP_MEM, X86_REG_RIP
JP = Path(r"E:\YostarGames\AZUPRO_JP\GameAssembly.dll")
TW = Path(r"E:\AzurPromilia_TC\AzurPromilia_TC_game\GameAssembly.dll")
META = OLD.parent / 'jp_localization/audit/jp-global-metadata-decrypted.dat'
TARGETS = [('VStringHashWR.BeginRead', 0x67E1C50), ('VStringHashWR.GetBucketIndex', 0x67E2160), ('VStringHashWR.GetVString', 0x67E2360), ('TableMgr.GetMMapStream', 0x508DB10)]

def digest(data): return hashlib.sha256(data).hexdigest()
def main():
    md = Cs(CS_ARCH_X86, CS_MODE_64); md.detail = True
    tw, jp, metadata = TW.read_bytes(), JP.read_bytes(), META.read_bytes()
    tp, jp_pe = pefile.PE(data=tw, fast_load=True), pefile.PE(data=jp, fast_load=True)
    print('PE headers parsed', flush=True)
    base = jp_pe.OPTIONAL_HEADER.ImageBase
    # x64 exception entries provide independent candidate function starts and ends.
    def function_ranges(pe, data):
        directory=pe.OPTIONAL_HEADER.DATA_DIRECTORY[3]
        offset=pe.get_offset_from_rva(directory.VirtualAddress)
        return {a:b for a,b,_ in struct.iter_unpack('<III',data[offset:offset+directory.Size])}
    ranges = function_ranges(jp_pe,jp)
    tranges = function_ranges(tp,tw)
    text = []
    result = {'mode': 'static_only_no_target_execution', 'engine': 'local pefile/Capstone (not REA)',
              'inputs': [{'path': str(p), 'sha256': digest(b), 'size': len(b)} for p,b in [(JP,jp),(TW,tw),(META,metadata)]],
              'functions': [], 'metadata': {}, 'confirmed': [], 'unknown': []}
    # Mask only branch/call immediate addresses and RIP-relative displacements.
    # Preserve field displacements, constants, register choices and instruction bytes.
    for name, rva in TARGETS:
        size = tranges[rva] - rva
        off = tp.get_offset_from_rva(rva)
        code = tw[off:off+size]
        mask = bytearray(b'\xff' * len(code))
        for ins in md.disasm(code, tp.OPTIONAL_HEADER.ImageBase+rva):
            pos = ins.address - tp.OPTIONAL_HEADER.ImageBase-rva
            if ins.group(1) or ins.group(2):
                if ins.imm_size:
                    mask[pos+ins.imm_offset:pos+ins.imm_offset+ins.imm_size] = b'\0'*ins.imm_size
            if any(o.type == X86_OP_MEM and o.mem.base == X86_REG_RIP for o in ins.operands):
                mask[pos+ins.disp_offset:pos+ins.disp_offset+ins.disp_size] = b'\0'*ins.disp_size
        # Search a long literal anchor, then validate the entire masked function.
        spans = [(m.start(), m.end()) for m in re.finditer(b'\xff+', bytes(mask))]
        lo, hi = max(spans, key=lambda v:v[1]-v[0])
        anchor = code[lo:hi]; matches=[]; start=0
        while True:
            hit=jp.find(anchor,start)
            if hit < 0: break
            start=hit+1; candidate=hit-lo
            if candidate < 0: continue
            raw=jp[candidate:candidate+len(code)]
            if len(raw)!=len(code) or any(m and a!=b for a,b,m in zip(code,raw,mask)): continue
            crva=jp_pe.get_rva_from_offset(candidate)
            if crva in ranges and ranges[crva]-crva==size: matches.append(crva)
        entry={'name':name,'tw_rva':hex(rva),'size':size,'unmasked_bytes':sum(bool(m) for m in mask),
               'jp_candidates':[hex(m) for m in matches], 'mapping':'unique_full_function_masked_match' if len(matches)==1 else 'unresolved'}
        text.append('### '+name+' '+json.dumps(entry))
        if len(matches)==1:
            crva=matches[0];coff=jp_pe.get_offset_from_rva(crva)
            entry['jp_rva']=hex(crva);entry['instructions']=[]
            # BeginRead is split into contiguous Windows unwind fragments.
            disasm_size=size
            if name == 'VStringHashWR.BeginRead':
                end=crva+size
                while end in ranges: end=ranges[end]
                disasm_size=end-crva
            entry['disassembly_size']=disasm_size
            for ins in md.disasm(jp[coff:coff+disasm_size],base+crva):
                item={'rva':hex(ins.address-base),'bytes':ins.bytes.hex(),'mnemonic':ins.mnemonic,'operands':ins.op_str}
                entry['instructions'].append(item)
                text.append(f"{item['rva']:12} {item['bytes']:32} {ins.mnemonic:8} {ins.op_str}")
        result['functions'].append(entry)
    # Metadata v31: string heap is header pair at 24, methods pair at 48.
    so, sn = struct.unpack_from('<II',metadata,24)
    def string(i):
        if not 0<=i<sn:return ''
        end=metadata.find(b'\0',so+i,so+sn)
        return metadata[so+i:end].decode('utf-8','replace')
    mo,mn=struct.unpack_from('<II',metadata,48)
    methods=[]
    for off in range(mo,mo+mn,36):
        ni,declaring=struct.unpack_from('<II',metadata,off)
        n=string(ni)
        if n in ('BeginRead','GetBucketIndex','GetVString','GetMMapStream'):
            methods.append({'index':(off-mo)//36,'name':n,'declaring_type':declaring,'raw':metadata[off:off+36].hex()})
    result['metadata']={'version':struct.unpack_from('<I',metadata,4)[0], 'method_record_size':36,'matching_methods':methods,
                        'limitation':'Method names corroborate presence only; metadata records alone do not map native RVA.'}
    result['unknown']=['No game execution or runtime test performed.', 'Pool candidate bytes, collision chains and full translated resource correctness are not tested by this probe.']
    result['confirmed'] = [
        {'claim':'Four JP entry fragments uniquely match TW after masking only control-flow immediates and RIP displacements; field offsets/constants remain exact.', 'rvas':['0x67f3070','0x67f3580','0x67f3780','0x509f5b0']},
        {'claim':'BeginRead makes six sequential calls through stream +0x30, storing returned EAX at object +0x10,+0x14,+0x18,+0x1c,+0x20,+0x24; capacity used by lookup is the fifth field +0x20.', 'rvas':['0x67f30f2','0x67f30fb','0x67f311c','0x67f313d','0x67f315e','0x67f317f','0x67f31a0']},
        {'claim':'GetVString loads capacity from this+0x20 into R8D, calls mapped GetBucketIndex. It computes bucket address from this+0x18 + bucket_index*4; no original capacity literal is used in this dataflow.', 'rvas':['0x67f37d7','0x67f37e7','0x67f37f6','0x67f37fd']},
        {'claim':'GetBucketIndex uses unsigned RDX hash / zero-extended R8D capacity and returns remainder EDX; zero capacity takes error path.', 'rvas':['0x67f3584','0x67f3587','0x67f358c','0x67f358f','0x67f3591','0x67f3594']},
        {'claim':'GetVString reads a bucket offset then seeks to it, reads a dynamic bucket count, loops comparing entry hash against R12 and reads a returned value on equality.', 'rvas':['0x67f3853','0x67f3858','0x67f38a8','0x67f38c6','0x67f3948','0x67f3965','0x67f39be']},
        {'claim':'TableMgr.GetMMapStream builds an object graph at this+0x18 from stream this+0x10. Dynamic counts control outer and inner loops; each entry reads a key-like 64-bit return and value-like EAX and passes them to helper 0x8835b600. No fixed pool capacity appears in these loops.', 'rvas':['0x509f8cf','0x509f8d4','0x509f8fa','0x509f91b','0x509f93d','0x509f95b','0x509f965','0x509f984','0x509f9fc','0x509fa1a','0x509fa49','0x509fa6a','0x509faa6']}
    ]
    result['unknown'] += [
        'Full metadata-to-code registration mapping is not recovered; names are attributed by supplied TW anchors and unique masked JP code matches, not independently resolved JP symbols.',
        'Stream interface dispatch helpers and generic dictionary constructor/getter/setter callees have not been independently symbol-resolved; dictionary key/value semantics inferred from call/dataflow remain conditional.',
        'Static dynamic-capacity dataflow supports capacity 524287 in place of 1674319 when header/index/offsets are rebuilt consistently; it does not validate the actual candidate pool, dictionary serialization, collision chains, offsets, or runtime compatibility.'
    ]
    text.insert(0, json.dumps({k:v for k,v in result.items() if k!='functions'},ensure_ascii=False,indent=2))
    (HERE/'jp_layout_evidence.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    (HERE/'jp_layout_evidence.txt').write_text('\n'.join(text),encoding='utf-8')
    print(json.dumps([{k:v for k,v in f.items() if k!='instructions'} for f in result['functions']],indent=2))
    print('Metadata method candidates:',len(methods))
if __name__=='__main__':main()
