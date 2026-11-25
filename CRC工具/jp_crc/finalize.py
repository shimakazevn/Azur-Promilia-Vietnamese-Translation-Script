"""Create factual install receipt and byte-verified desktop release copy."""
from pathlib import Path
import ctypes,datetime,hashlib,json,shutil,sys
HERE=Path(__file__).resolve().parent
sys.path[:0]=[str(HERE),str(HERE.parent/'crc')]
from baseline import LIVE
from audit_protected import inventory
import crcchain as C
PACK=HERE.parents[1]/'outputs/日服简体汉化-清单只读CRC版'
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def main():
 plan=json.loads((PACK/'tools/crc-deployment.json').read_text('utf-8'))
 protected=json.loads((HERE/'protected_original_sha256.json').read_text('utf-8'));assert inventory()==protected
 for e in plan['files']:assert sha(LIVE/e['relative_path'])==e['target_sha256'],('not installed',e['relative_path'])
 for e in plan['readonly_files']:assert sha(LIVE/e['relative_path'])==e['sha256'],('baseline modified',e['relative_path'])
 tests=json.loads((HERE/'release_test/脚本测试报告.json').read_text('utf-8'));assert tests['all_passed']
 shutil.copy2(HERE/'release_test/脚本测试报告.json',PACK/'脚本测试报告.json')
 receipt={'created_at':datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),'region':'jp','game_data':str(LIVE),'installed':True,'resource_files_verified':len(plan['files']),'packs_verified':sum(x['relative_path'].endswith('.r') for x in plan['files']),'segments_verified':sum(len(x.get('segments',[])) for x in plan['files']),'readonly_files_unchanged':len(plan['readonly_files']),'protected_files_unchanged':len(protected),'runtime_launch_tested':False,'runtime_login_verified':False,'note':'Offline size/CRC and manifest equality do not establish server acceptance.'}
 (PACK/'安装验证.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),'utf-8')
 (PACK/'本次实际结果.md').write_text(f'''# 日服本次实际结果

- 已安装：更新版本 3219598，内置版本 3075915。
- {receipt['packs_verified']} 个 `.r` 包及 resources.assets 均与原版等长；{receipt['segments_verified']} 个段 CRC32 及整包 CRC32 全部与原版清单一致。
- {receipt['readonly_files_unchanged']} 项清单/基线保持原字节；清单 MD5 与原版 .hash 一致。
- {receipt['protected_files_unchanged']} 项排除文件哈希未变，包括 EXE、DLL、metadata、SDK/插件及 ACE 文件。
- 隔离测试通过：载荷校验、篡改清单拒绝、写入中途失败回滚、应用、重复应用、完整校验、还原。
- 文本数据未压短，470,994 行日服语言表保持目标译文；完整原字符串键和新增译文保留。
- resources.assets 仅改启动文字，内嵌 SDK locale 保持日服原版。
- 尚未实际启动日服、完成登录或进入游戏；不能据此宣称服务器 High 校验已实际执行或通过。

仅使用本目录新脚本，不要再运行旧版会改清单的汉化脚本。启动器执行 MD5 修复可能还原资源；CRC32 相同不代表 MD5 相同。
''','utf-8')
 evidence=HERE/'jp_layout_evidence.json'
 if evidence.is_file():shutil.copy2(evidence,PACK/'日服读取逻辑静态验证.json')
 desktop_buf=ctypes.create_unicode_buffer(32768)
 assert ctypes.windll.shell32.SHGetFolderPathW(None,0x10,None,0,desktop_buf)==0
 desktop=Path(desktop_buf.value);dest=desktop/PACK.name
 if dest.exists():dest=desktop/(PACK.name+'-'+datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).strftime('%Y%m%d-%H%M%S'))
 assert not dest.exists();shutil.copytree(PACK,dest)
 count=0
 for p in PACK.rglob('*'):
  if p.is_file():assert sha(p)==sha(dest/p.relative_to(PACK));count+=1
 print(json.dumps({'receipt':receipt,'desktop':str(dest),'desktop_files_verified':count},ensure_ascii=False))
if __name__=='__main__':main()
