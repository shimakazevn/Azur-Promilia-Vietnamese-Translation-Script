import sys,json,hashlib,subprocess,shutil,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
PACK=ROOT/'outputs'/'台服简体汉化-清单只读CRC版'
DATA=Path(r'E:\AzurPromilia_TC\AzurPromilia_TC_game\AzurPromilia_Data')
FIX=HERE/'release_test'/'AzurPromilia_TC_game'
FD=FIX/'AzurPromilia_Data'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def run(action,expect=0):
 start=time.monotonic()
 cmd=['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(PACK/'tools/Apply-CRCZH.ps1'),'-Action',action,'-Hint',str(FIX)]
 p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=120)
 output=p.stdout.decode('utf-8','replace');(HERE/('release_test_'+action+'.log')).write_text(output,'utf-8')
 print(json.dumps({'action':action,'exit_code':p.returncode,'seconds':round(time.monotonic()-start,2),'last_lines':output.splitlines()[-3:]},ensure_ascii=False),flush=True)
 assert p.returncode==expect,(action,p.returncode,output)
 return {'action':action,'exit_code':p.returncode,'seconds':round(time.monotonic()-start,2)}
def main():
 plan=json.loads((PACK/'tools/crc-deployment.json').read_text('utf-8'))
 FD.mkdir(parents=True,exist_ok=True);(FIX/'AzurPromilia.exe').touch()
 for record in plan['files']+plan['readonly_files']:
  rel=record['relative_path'];src=DATA/rel;dest=FD/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dest)
 checks=[run('ValidatePayload')]
 # A modified original manifest must refuse before writing any resource.
 guard=plan['readonly_files'][0];gp=FD/guard['relative_path'];saved=gp.read_bytes();bad=bytearray(saved);bad[0]^=1;gp.write_bytes(bad)
 checks.append(run('Apply',1))
 for f in plan['files']:assert sha(FD/f['relative_path'])==f['source_sha256']
 gp.write_bytes(saved)
 checks.append(run('Apply'))
 for f in plan['files']:assert sha(FD/f['relative_path'])==f['target_sha256']
 for f in plan['readonly_files']:assert sha(FD/f['relative_path'])==f['sha256']
 checks.append(run('Verify'))
 checks.append(run('Apply')) # idempotence
 checks.append(run('Restore'))
 for f in plan['files']:assert sha(FD/f['relative_path'])==f['source_sha256']
 for f in plan['readonly_files']:assert sha(FD/f['relative_path'])==f['sha256']
 checks.append(run('Verify'))
 # Production installation was read only throughout this test.
 for f in plan['files']:assert sha(DATA/f['relative_path'])==f['source_sha256']
 for f in plan['readonly_files']:assert sha(DATA/f['relative_path'])==f['sha256']
 result={'all_passed':True,'isolated_fixture':str(FIX),'production_installation_unchanged':True,'changed_guard_rejected_before_resource_writes':True,'apply_and_restore_byte_verified':True,'idempotent_apply_verified':True,'checks':checks}
 (PACK/'脚本测试报告.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf-8')
 print(json.dumps({'all_passed':True,'production_installation_unchanged':True}),flush=True)
if __name__=='__main__':main()
