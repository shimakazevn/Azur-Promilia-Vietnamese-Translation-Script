from UnityPy.streams import EndianBinaryReader
from UnityPy.helpers import CompressionHelper
from UnityPy.helpers import ArchiveStorageManager as asm
import struct,json,hashlib,zlib

def encrypt_lz4(data,index,dec):
 plain=bytes(data);out=bytearray(data);inv=[0]*16
 for i,n in enumerate(dec.index):inv[n]=i
 def byte(pos,idx):
  sub=dec.substitute
  b=sub[((idx>>2)&3)+4]+sub[idx&3]+sub[((idx>>4)&3)+8]+sub[((idx%256)>>6)+12]
  v=plain[pos];out[pos]=inv[((v>>4)+b)&15]*16+inv[((v&15)+b)&15]
  return v,pos+1,idx+1
 offset=0
 while offset<len(plain):
  idx=index;token,pos,idx=byte(offset,idx);high=token>>4;low=token&15
  if high==15:
   v=255
   while v==255:v,pos,idx=byte(pos,idx);high+=v
  pos+=high
  if pos<len(plain):
   _,pos,idx=byte(pos,idx);_,pos,idx=byte(pos,idx)
   if low==15:
    v=255
    while v==255:v,pos,idx=byte(pos,idx)
  offset=pos;index+=1
 return bytes(out)

def wrap(plain,original):
 r=EndianBinaryReader(plain)
 r.read_string_to_null();r.read_u_int();r.read_string_to_null();r.read_string_to_null()
 headerpos=r.Position;size=r.read_long();cs=r.read_u_int();us=r.read_u_int();fl=r.read_u_int();headend=r.Position
 r.align_stream(16);start=r.Position
 ci=plain[size-cs:size] if fl&128 else plain[start:start+cs]
 info=bytearray(CompressionHelper.decompress_lz4(ci,us));n=struct.unpack_from('>i',info,16)[0]
 pos=start if fl&128 else start+cs
 if fl&512:pos=(pos+15)//16*16
 sourceReader=EndianBinaryReader(original);sourceReader.Position=headend
 dec=asm.ArchiveStorageDecryptor(sourceReader);encHeader=original[headend:sourceReader.Position]
 blocks=[]
 for i in range(n):
  u,c,bf=struct.unpack_from('>IIH',info,20+10*i);data=plain[pos:pos+c];pos+=c
  if bf&63:
   encrypted=encrypt_lz4(data,i,dec)
   assert bytes(dec.decrypt_block(encrypted,i))==data
   data=encrypted;struct.pack_into('>H',info,28+10*i,bf|256)
  blocks.append(data)
 ci=CompressionHelper.compress_lz4(info)
 header=bytearray(plain[:headend]);newflags=0x643
 struct.pack_into('>III',header,headerpos+8,len(ci),len(info),newflags)
 output=header+encHeader;output.extend(bytes((-len(output))%16));output.extend(ci);output.extend(bytes((-len(output))%16))
 output.extend(b''.join(blocks));struct.pack_into('>Q',output,headerpos,len(output))
 return bytes(output),n

if __name__=='__main__':
 from unity_setup import *
 original=Path(r'E:\AzurPromilia_TC\AzurPromilia_TC_game\AzurPromilia_Data\StreamingAssets\.res\default_package\a66pm5ie1rrjguuzlsyq.r').read_bytes()
 plain=(HERE/'tw_a00_cn_font_plain.r').read_bytes();encrypted,n=wrap(plain,original)
 out=HERE/'tw_a00_cn_font_unitycn.r';out.write_bytes(encrypted)
 e=UnityPy.load(str(out));ep=UnityPy.load(plain)
 a={o.path_id:o.get_raw_data() for o in e.objects};b={o.path_id:o.get_raw_data() for o in ep.objects};assert a==b
 report=json.loads((HERE/'font_candidate_validation.json').read_text())
 report['encryptedCandidate']={'path':str(out),'bytes':len(encrypted),'sha256':hashlib.sha256(encrypted).hexdigest(),'crc32':f'{zlib.crc32(encrypted):08x}','flags':int(next(iter(e.files.values())).dataflags),'encryptionPreserved':True,'encryptionHeaderMatchesOriginal':encrypted[44:114]==original[44:114],'blocksRoundtripValidated':n,'allObjectRawDataMatchesPlainCandidate':True,'containerMatchesPlainCandidate':list(e.container)==list(ep.container),'runtimeAcceptanceTested':False}
 (HERE/'font_candidate_validation.json').write_text(json.dumps(report,indent=2),encoding='utf8');print(json.dumps(report['encryptedCandidate']))
