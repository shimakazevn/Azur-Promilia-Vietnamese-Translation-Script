"""Build JP UnityFS candidates in immutable original CRC/size slots; never deploy.

Imports the existing codec without calling its main or reading its DATA tree.
Only this directory's report and non-raw fixed_candidates are written.
"""
import sys, os
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
sys.dont_write_bytecode = True
from pathlib import Path
import json, hashlib, zlib, io, time, traceback
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent/'crc'))
import fit_bundles as F
import crcchain as C
from reencrypt_bundle import wrap
from fontTools.ttLib import TTFont
from fontTools.pens.recordingPen import DecomposingRecordingPen
BACKUP = Path(r'E:\YostarGames\AZUPRO_JP\.zhcn-jp-3219598-backup')
OLD = Path(r'C:\Users\xiaoxi\Documents\Codex\2026-11-24\new-chat\work\jp_localization')
TARGET = OLD/'game_candidate'
OUT = HERE/'fixed_candidates'
REPORT = HERE/'bundle_report.json'
def sha(b): return hashlib.sha256(b).hexdigest()
def crc(b): return zlib.crc32(b)&0xffffffff
def emit(v): print(json.dumps(v,ensure_ascii=False),flush=True)
def save(r): REPORT.write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8')
def objects(raw):
    return {o.path_id:o for o in F.UnityPy.load(raw).objects}
def font_info(fd):
    f=TTFont(io.BytesIO(fd)); cm=f.getBestCmap() or {}
    valid={cp:g for cp,g in cm.items() if g!='.notdef'}
    return f,valid
def outline(f,g):
    gs=getattr(f,'_jp_crc_glyphset',None)
    if gs is None:
        gs=f.getGlyphSet(); f._jp_crc_glyphset=gs
    p=DecomposingRecordingPen(gs); gs[g].draw(p)
    return sha(repr((p.value,gs[g].width)).encode())
def font_checks(original, target, candidate=None, required=None):
    a,b=objects(original),objects(target)
    c=objects(candidate) if candidate is not None else b
    assert a.keys()==b.keys()==c.keys(), 'object IDs changed'
    report=[]
    for pid,o in b.items():
        if o.type.name!='Font':
            assert o.get_raw_data()==c[pid].get_raw_data(), ('non-font changed',pid)
            continue
        ot=a[pid].read_typetree(); t=o.read_typetree(); ct=c[pid].read_typetree()
        name=t.get('m_Name','')
        assert {k:v for k,v in ot.items() if k!='m_FontData'}=={k:v for k,v in ct.items() if k!='m_FontData'}, ('JP font fields',name)
        if name.endswith('_origin'):
            assert a[pid].get_raw_data()==o.get_raw_data()==c[pid].get_raw_data(), ('origin changed',name)
            report.append({'font':name,'origin_byte_identical':True});continue
        fd=bytes(t.get('m_FontData',[])); cd=bytes(ct.get('m_FontData',[]))
        if not fd: continue
        f,cm=font_info(fd); cf,cc=font_info(cd)
        keep=set(cm) if required is None else set(cm)&required
        missing=keep-set(cc); assert not missing,(name,'lost glyphs',sorted(missing))
        # Compare actual outlines and advances, not merely cmap membership.
        bad=[cp for cp in sorted(keep) if outline(f,cm[cp])!=outline(cf,cc[cp])]
        assert not bad,(name,'glyph outline/advance changed',bad)
        metrics={}
        for table,attrs in [('head',['unitsPerEm']),('hhea',['ascent','descent','lineGap']),('OS/2',['sTypoAscender','sTypoDescender','sTypoLineGap','usWinAscent','usWinDescent'])]:
            if table in f and table in cf:
                metrics[table]={x:getattr(f[table],x) for x in attrs}
                assert all(getattr(f[table],x)==getattr(cf[table],x) for x in attrs),(name,table)
        report.append({'font':name,'jp_object_fields_preserved':True,'glyphs_checked':len(keep),'outline_and_advance_equal':True,'font_metrics':metrics,'missing_from_input':sorted((required or set())-set(cm)),'bytes_before':len(fd),'bytes_after':len(cd)})
    return report
def corpus():
    p=HERE/'corpus_codepoints.json'
    if not p.exists(): return None
    data=json.loads(p.read_text('utf-8'))
    if isinstance(data,dict): data=data['codepoints']
    points={int(x) for x in data}|set(range(32,127))|set(range(0x3000,0x3100))|set(range(0xff00,0xfff0))
    # GB2312 common simplified characters; JIS X 0208 common Japanese repertoire.
    for encoding in ('gb2312','euc_jp'):
        for lead in range(0xa1,0xff):
            for trail in range(0xa1,0xff):
                try: points.update(map(ord,bytes([lead,trail]).decode(encoding)))
                except UnicodeDecodeError: pass
    return points
def main():
    HERE.mkdir(exist_ok=True)
    plan=json.loads((OLD/'deployment-plan.json').read_text('utf-8'))
    entries={x['relative_path']:x for x in plan['files']}
    report={'status':'building','deployed':False,'plan_sha256':sha((OLD/'deployment-plan.json').read_bytes()),'packs':[],'manifests':[]}
    save(report)
    packs=sorted(p for p in TARGET.rglob('*.r') if not any(x.startswith('raw_') for x in p.relative_to(TARGET).parts))
    report['discovered_non_raw_count']=len(packs)
    names={p.name for p in packs}
    manifests=[]
    # Discover every original and target manifest, including cross-version references.
    for root,label in [(BACKUP,'original'),(TARGET,'target')]:
        for path in sorted(root.rglob('*.bytes')):
            if 'rollback' in path.relative_to(root).parts:continue
            with path.open('rb') as stream: magic=stream.read(4)
            if magic!=b'OOY\0':continue
            raw=path.read_bytes(); m=C.parse(raw)
            refs=[i for i,p in enumerate(m['packs']) if C.name_of(p) in names]
            if not refs:continue
            rel=path.relative_to(root).as_posix(); e=entries.get(rel)
            assert e,('manifest absent from deployment plan',label,rel)
            expected=e['source_sha256' if label=='original' else 'target_sha256']
            assert sha(raw)==expected,('manifest SHA mismatch',label,rel)
            h=path.with_suffix('.hash')
            assert h.read_text().strip().lower()==hashlib.md5(raw).hexdigest(),('manifest MD5',path)
            manifests.append((label,rel,m,raw,refs))
            report['manifests'].append({'tree':label,'path':rel,'sha256':sha(raw),'plan_sha256_verified':True,'md5_verified':True,'referenced_packs':[C.name_of(m['packs'][i]) for i in refs]})
    save(report)
    for path in packs:
        rel=path.relative_to(TARGET).as_posix(); entry=entries[rel]
        result={'path':rel,'complete':False,'segments':[]};report['packs'].append(result);save(report)
        try:
            src=(BACKUP/rel).read_bytes(); tar=path.read_bytes()
            assert sha(src)==entry['source_sha256'],('source SHA mismatch',rel)
            assert sha(tar)==entry['target_sha256'],('target SHA mismatch',rel)
            result.update(source_sha256=sha(src),target_sha256=sha(tar),plan_sha256_verified=True)
            refs={label:[(mr,m,raw,pi) for lab,mr,m,raw,indices in manifests if lab==label for pi in indices if C.name_of(m['packs'][pi])==path.name] for label in ('original','target')}
            assert refs['original'] and refs['target'],('unreferenced pack',rel)
            for label, data, pp in [('original',src,BACKUP/rel),('target',tar,path)]:
                for mr,m,raw,pi in refs[label]:
                    assert not C.verify(raw,pp),(label,mr,C.verify(raw,pp))
            _,om,_,oi=refs['original'][0]; _,tm,_,ti=refs['target'][0]
            ss=C.segments(om,oi); ts=C.segments(tm,ti)
            # Match by stable bundle hash, never assume identical segment ordering.
            tmap={tuple(tm['hashes'][tm['bundles'][bi]['nameIndex']]):(bi,off,size) for bi,off,size in ts}
            out=bytearray(src)
            for bi,off,size in ss:
                key=tuple(om['hashes'][om['bundles'][bi]['nameIndex']]); tbi,to,tn=tmap[key]
                a=src[off:off+size]; b=tar[to:to+tn]
                seg={'bundle':bi,'target_bundle':tbi,'offset':off,'original_size':size,'original_crc':crc(a),'target_size':tn,'changed':a!=b}
                result['segments'].append(seg)
                if a!=b:
                    candidate,rep=F.repack(b,a,size); seg['initial_repack']=rep
                    required=None
                    if candidate is None:
                        fonts=any(o.type.name=='Font' for o in F.UnityPy.load(b).objects)
                        if not fonts:
                            raise ValueError('Localized non-font segment exceeds original slot; translation is unchanged: '+str(rep))
                        required=corpus()
                        if required is None:
                            seg['waiting_for']='corpus_codepoints.json';save(report);emit({'waiting_for':'corpus_codepoints.json','pack':rel})
                            while required is None:
                                time.sleep(2);required=corpus()
                        seg.pop('waiting_for',None)
                        seg['corpus_sha256']=sha((HERE/'corpus_codepoints.json').read_bytes());seg['required_codepoints']=len(required)
                        plain,changes=F.font_subset(b,required)
                        wrapped,_=wrap(plain,a)
                        font_checks(a,b,wrapped,required)
                        candidate,rep=F.repack(wrapped,a,size);seg['subset']=changes;seg['subset_repack']=rep
                        if candidate is None:raise ValueError('Font subset still exceeds original slot; no translations removed: '+str(rep))
                    assert F.meta(candidate)[-1]==F.meta(b if required is None else wrapped)[-1]
                    seg['roundtrip_plain_equal']=True
                    seg['fonts']=font_checks(a,b,candidate,required)
                    ao,bo,co=objects(a),objects(b),objects(candidate)
                    assert bo.keys()==co.keys()
                    for pid,obj in bo.items():
                        if required is None or obj.type.name!='Font':assert obj.get_raw_data()==co[pid].get_raw_data(),('object altered',pid)
                    seg['non_font_objects_unchanged_from_target']=True
                    seg['changed_from_original_objects']=[{'id':pid,'type':o.type.name} for pid,o in co.items() if o.get_raw_data()!=ao[pid].get_raw_data()]
                    out[off:off+size]=candidate
                else:seg['roundtrip_plain_equal']=True
                data=out[off:off+size];seg.update(candidate_size=len(data),candidate_crc=crc(data),size_ok=len(data)==size,crc_ok=crc(data)==om['bundles'][bi]['crc'])
                assert seg['size_ok'] and seg['crc_ok'];emit({'pack':path.name,'segment':bi,'ok':True,'subset':bool(seg.get('subset'))})
                save(report)
            result['references']=[]
            for mr,m,raw,pi in refs['original']:
                pk=m['packs'][pi]; checks=[]
                assert len(out)==pk['size'] and crc(out)==pk['crc'],('pack mismatch',mr)
                for bi,off,size in C.segments(m,pi):
                    data=out[off:off+size];ok=len(data)==size and crc(data)==m['bundles'][bi]['crc'];assert ok,(mr,bi)
                    checks.append({'bundle':bi,'offset':off,'size':size,'crc':crc(data),'size_ok':len(data)==size,'crc_ok':ok})
                result['references'].append({'manifest':mr,'pack_size':len(out),'pack_crc':crc(out),'size_ok':True,'crc_ok':True,'all_segments':checks})
            dest=OUT/rel;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(out)
            for mr,m,raw,pi in refs['original']:assert not C.verify(raw,dest)
            result.update(complete=True,candidate_sha256=sha(out),candidate_size=len(out),candidate_crc=crc(out),output=str(dest))
        except Exception as exc:
            result['error']=str(exc);result['traceback']=traceback.format_exc();emit({'pack':rel,'error':str(exc)})
        save(report)
    report['status']='complete' if all(p['complete'] for p in report['packs']) else 'incomplete'
    report['complete_count']=sum(p['complete'] for p in report['packs']);save(report)
    emit({'status':report['status'],'complete':report['complete_count'],'total':len(packs)})
if __name__=='__main__': main()
