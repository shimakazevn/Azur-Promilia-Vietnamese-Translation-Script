import struct,json,hashlib,subprocess
from pathlib import Path
HERE=Path(__file__).parent
OUT=HERE/'decoded';OUT.mkdir(exist_ok=True)
aeskey=(HERE/'local_mmap_key.bin').read_bytes()
aesiv=(HERE/'local_mmap_iv.bin').read_bytes()
cache={}
def keystream(header):
    encrypted=header[8:]
    identity=hashlib.sha256(encrypted).hexdigest()
    if identity not in cache:
        js="const fs=require('fs'),x=JSON.parse(fs.readFileSync(0,'utf8')),d=require('crypto').createDecipheriv('aes-256-cbc',Buffer.from(x[0],'hex'),Buffer.from(x[1],'hex'));process.stdout.write(Buffer.concat([d.update(Buffer.from(x[2],'hex')),d.final()]));"
        keys=subprocess.check_output(['node','-e',js],input=json.dumps([aeskey.hex(),aesiv.hex(),encrypted.hex()]).encode())
        assert len(keys)==4096
        cache[identity]=b''.join(keys[keys[block]:]+keys[:keys[block]] for block in range(256))
    return cache[identity]
def decode_file(source,destination):
    with source.open('rb') as f,destination.open('wb') as out:
        header=f.read(4120);assert struct.unpack_from('<II',header)==(1,4112)
        stream=keystream(header);period=len(stream);position=4120
        while chunk:=f.read(4*1024*1024):
            offset=position%period
            mask=(stream*5)[offset:offset+len(chunk)]
            decoded=(int.from_bytes(chunk,'little')^int.from_bytes(mask,'little')).to_bytes(len(chunk),'little')
            # XOR is reversible, including partial final chunks.
            assert (int.from_bytes(decoded,'little')^int.from_bytes(mask,'little')).to_bytes(len(chunk),'little')==chunk
            out.write(decoded);position+=len(chunk)
    return dict(source=str(source),output=str(destination),source_bytes=source.stat().st_size,output_bytes=destination.stat().st_size,sha256=hashlib.sha256(destination.read_bytes()).hexdigest(),header_bytes=4120)
if __name__=='__main__':
    records=[]
    roots={'tw':Path(r'E:\AzurPromilia_TC\AzurPromilia_TC_game\AzurPromilia_Data'),'cn':Path(r'D:\AzurPromilia\AzurPromilia_Game\AzurPromilia_Data')}
    for region,root in roots.items():
        for layer,folder in [('builtin',root/'StreamingAssets/.res/raw_base_package'),('update',root/'.res/raw_base_package/BundleFiles')]:
            for source in folder.glob('*.r'):
                with source.open('rb') as f:signature=f.read(8)
                if signature!=struct.pack('<II',1,4112):continue
                destination=OUT/f'{region}_{layer}_{source.stem}.bin'
                row=decode_file(source,destination);row.update(region=region,layer=layer)
                records.append(row);print(json.dumps(row),flush=True)
    (HERE/'decoded-inventory.json').write_text(json.dumps(records,indent=2),encoding='utf-8')
