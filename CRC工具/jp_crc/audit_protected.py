"""Hash-only audit of excluded binaries and baseline files; never modify targets."""
from pathlib import Path
import hashlib,json,sys
HERE=Path(__file__).resolve().parent
ROOT=Path(r'E:\YostarGames\AZUPRO_JP')
RECEIPT=HERE/'protected_original_sha256.json'
def digest(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def inventory():
 paths={p for p in ROOT.iterdir() if p.is_file() and p.suffix.lower() in ('.exe','.dll','.json','.marker','.cer','.crt','.pem','.key')}
 for root in (ROOT/'AntiCheatExpert',ROOT/'AzurPromiliaJP_Data/Plugins',ROOT/'AzurPromiliaJP_Data/il2cpp_data/Metadata'):
  paths.update(p for p in root.rglob('*') if p.is_file())
 return {p.relative_to(ROOT).as_posix():digest(p) for p in sorted(paths)}
def main():
 current=inventory()
 if '--verify' in sys.argv:
  before=json.loads(RECEIPT.read_text('utf-8'));assert before==current,'Excluded file set or byte hash changed'
  print(json.dumps({'protected_files_verified':len(current),'all_unchanged':True}))
 else:
  assert not RECEIPT.exists(),'Never replace original audit'
  RECEIPT.write_text(json.dumps(current,ensure_ascii=False,indent=2),'utf-8');print(json.dumps({'protected_files_snapshotted':len(current)}))
if __name__=='__main__':main()
