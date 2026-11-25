import json,hashlib,shutil,datetime
from pathlib import Path
HERE=Path(__file__).resolve().parent
PACK=HERE.parents[1]/'outputs'/'台服简体汉化-清单只读CRC版'
DESKTOP=Path(r'D:\windows\Desktop\台服简体汉化-清单只读CRC版')
DATA=Path(r'E:\AzurPromilia_TC\AzurPromilia_TC_game\AzurPromilia_Data')
plan=json.loads((PACK/'tools/crc-deployment.json').read_text('utf-8'))
checks=[]
for rec in plan['files']:
 p=DATA/rec['relative_path'];assert p.stat().st_size==rec['size'];assert hashlib.sha256(p.read_bytes()).hexdigest()==rec['target_sha256']
 checks.append(rec['relative_path'])
for rec in plan['readonly_files']:
 assert hashlib.sha256((DATA/rec['relative_path']).read_bytes()).hexdigest()==rec['sha256']
log=Path(r'C:\Users\xiaoxi\AppData\LocalLow\manjuu\AzurPromilia\Player.log').read_text('utf-8',errors='replace')
assert 'SDK登录回调, code:0' in log
assert 'PatchInfo 回调收到, success:True' in log
assert 'FsmVersionUpdateEnd --> Lens.Gameplay.Managers.FsmUpdaterDone' in log
assert 'Patch维护检查未通过' in log and 'isOpen=False' in log
receipt={
 'observed_at':datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),
 'installation':str(DATA.parent),'installed_resources':checks,'readonly_baselines_verified_after_launch':len(plan['readonly_files']),
 'local_size_crc_high_conditions_verified':True,'all_51_manifest_segments_verified':True,
 'launcher_startGame_completed':True,'client_updater_done_observed':True,'sdk_login_callback_code':0,'patchinfo_success':True,
 'simplified_chinese_visible':True,'visible_message':'服务器正在维护中，请星临者耐心等待',
 'server_isOpen':False,'server_state':1,'gameplay_entry_verified':False,
 'runtime_login_verified':False,'remaining_blocker':'正式服维护状态阻断进入游戏，无法完成角色/场景登录验证。',
 'crc_error_seen_in_this_startup':any(t in log for t in ('FileCrcError','FileNotComplete','FileOverflow')),
 'client_high_verifier_execution_observed':False,
 'note':'本地 CRC 与原版清单逐项吻合；实际启动运行到维护提示。未把日志未报错等同于服务器完整性验证已全部通过。'
}
assert not receipt['crc_error_seen_in_this_startup']
(PACK/'实际启动验证.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),'utf-8')
md='''# 本次实际结果

已应用到 `E:\\AzurPromilia_TC\\AzurPromilia_TC_game`，并在联网启动后再次校验。

- 7 个 .r 文件大小、51 个段 CRC、7 个整包 CRC 与原版一致。
- 18 个只读基线文件逐字节哈希一致，其中包括原版清单、.hash 和 ApplicationFootPrint。
- 汉化载荷、原版异常拒绝、应用、重复应用、校验及逐字节还原的隔离测试全部通过。
- 正常启动器 startGame 检查完成并拉起游戏；客户端走到 FsmUpdaterDone，SDK 登录回调 code:0，PatchInfo 请求成功。
- 实际画面已显示简体“服务器正在维护中，请星临者耐心等待”。
- 服务器返回 isOpen=False、state=1，维护检查阻断进服。角色/场景登录仍未验证，不能宣称服务器全部校验已通过。

桌面使用 **台服简体汉化-清单只读CRC版** 中的 BAT。旧的“蓝色星原简体汉化独立版”仍是历史版本，不应用本次结果评价它。

具体数据见 验证报告.json、脚本测试报告.json、实际启动验证.json。接口密钥未包含在本目录。
'''
(PACK/'本次实际结果.md').write_text(md,'utf-8')
readme=(PACK/'使用说明.md').read_text('utf-8')
readme=readme.replace('当前验证涵盖离线解密/解压/重载、数据语义、原版大小和 CRC 以及清单字节；实际登录及游戏显示尚须运行确认。','已完成离线解密/解压/重载、数据语义、原版大小和 CRC 以及清单字节校验；实际启动已进入简体维护提示画面，SDK 登录成功，服务器维护阻断角色/场景登录。')
(PACK/'使用说明.md').write_text(readme,'utf-8')
for path in PACK.rglob('*'):
 if not path.is_file():continue
 rel=path.relative_to(PACK);other=DESKTOP/rel
 if not other.exists() or hashlib.sha256(path.read_bytes()).digest()!=hashlib.sha256(other.read_bytes()).digest():
  other.parent.mkdir(exist_ok=True,parents=True);shutil.copy2(path,other)
 assert hashlib.sha256(path.read_bytes()).digest()==hashlib.sha256(other.read_bytes()).digest()
print(json.dumps({'installed_verified':True,'desktop_matches_release':True,'pack_count':7,'segment_count':51,'readonly_files':18,'sdk_login_code':0,'server_maintenance':True,'gameplay_entry_verified':False},ensure_ascii=False))
