#!/usr/bin/env python3
"""Extract RADAR 1 FAT20 images, convert SND PCM with SoX, create REAPER sessions.

Supports the RADAR5.0/FAT20 layout reverse-engineered from this disk set.
Audio interpretation: 48 kHz signed 16-bit little-endian mono PCM.
Python 3.7+, standard library only; external SoX executable required.
"""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import wave


def extract_images(images, output, sox):
    OUT = output
    SOX = sox
    rows=[]
    for image_path in images:
        source=str(image_path)
        with open(source, 'rb') as header_file:
            header_file.seek(16384); header=header_file.read(512)
        disk_index=header[36]-0xF0
        if disk_index not in (0,1,2): raise ValueError('Unsupported RADAR disk index in '+source)
        disk='%d0'%disk_index
        dest=OUT/('HD'+disk)
        for folder in ['snd','wav','projects']:(dest/folder).mkdir(parents=True,exist_ok=True)
        with open(source,'rb') as f:
            f.seek(16384);b=f.read(512)
            assert b[3:11]==b'RADAR5.0' and b[54:59]==b'FAT20'
            f.seek(46080);fat=f.read(323*512)
            f.seek(46080+323*512);assert fat==f.read(323*512),'FAT copies differ'
            def nxt(c):return (int.from_bytes(fat[c*20//8:c*20//8+4],'little')>>((c%2)*4))&0xfffff
            def chain(c):
                seen=set()
                while 2<=c<66000 and c not in seen:
                    seen.add(c);yield c;c=nxt(c)
                if c<0xffff8:raise ValueError('Invalid chain terminator '+str(c))
            def blocks(c):
                for k in chain(c):
                    f.seek(393216+(k-2)*32768);d=f.read(32768)
                    assert len(d)==32768
                    yield d
            def entries(data):
                for i in range(0,len(data),32):
                    e=data[i:i+32]
                    if e[0]==0:break
                    if e[0]==229 or e[11]&8:continue
                    name=e[:8].decode('ascii').strip();ext=e[8:11].decode('ascii').strip()
                    if name not in ('.','..') and (not name or any(ch in name+ext for ch in '/\\:<>|?*') or '..' in name):
                        raise ValueError('Unsafe directory entry name')
                    yield name+('.'+ext if ext else ''),e[11],struct.unpack('<H',e[26:28])[0],struct.unpack('<I',e[28:32])[0]
            f.seek(376832);root=list(entries(f.read(16384)))
            for dirname,attr,c,size in root:
                if dirname not in ['AUDIO','PROJECTS']:continue
                listing=list(entries(b''.join(blocks(c))))
                for name,attr,c,size in listing:
                    if attr&16:continue
                    if dirname=='AUDIO' and not name.endswith('.SND'):continue
                    path=dest/('snd' if dirname=='AUDIO' else 'projects')/name
                    h=hashlib.sha256();remaining=size;count=0
                    with path.open('wb') as out:
                        for d in blocks(c):
                            count+=1;chunk=d[:remaining];out.write(chunk);h.update(chunk);remaining-=len(chunk)
                    assert remaining==0 and count==(size+32767)//32768,(name,remaining,count)
                    if dirname=='PROJECTS':continue
                    wav=dest/'wav'/(path.stem+'.wav')
                    cmd=[str(SOX),'-D','-t','raw','-e','signed-integer','-b','16','-L','-r','48000','-c','1',str(path),str(wav)]
                    result=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
                    assert result.returncode==0,result.stderr.decode(errors='replace')
                    with wave.open(str(wav),'rb') as w:
                        assert (w.getnchannels(),w.getsampwidth(),w.getframerate(),w.getnframes())==(1,2,48000,size//2)
                        wh=hashlib.sha256()
                        while True:
                            chunk=w.readframes(524288)
                            if not chunk:break
                            wh.update(chunk)
                    assert wh.hexdigest()==h.hexdigest(),'PCM mismatch'
                    rows.append(dict(image=source,snd=str(path.relative_to(OUT)),wav=str(wav.relative_to(OUT)),bytes=size,samples=size//2,duration_seconds=round(size/96000.0,6),pcm_sha256=h.hexdigest(),status='chain and WAV PCM verified'))
                    if len(rows)%100==0:print('Converted',len(rows),flush=True)
        print('Completed HD'+disk,flush=True)
    with (OUT/'manifest.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    summary={'files':len(rows),'pcm_bytes':sum(r['bytes'] for r in rows),'sample_rate':48000,'bits':16,'channels':1,'by_image':{d:sum(Path(r['wav']).parts[0]=='HD'+d for r in rows) for d in ['00','10','20']}}
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary),flush=True)


def build_projects(recovery_root):
    BASE = recovery_root
    OUT = BASE/'REAPER'
    OUT.mkdir()
    with (BASE/'manifest.csv').open(newline='', encoding='utf-8') as manifest_file:
        media={int(Path(r['wav']).stem,16):r for r in csv.DictReader(manifest_file)}
    reports=[];cliprows=[]
    def q(s):return '"'+s.replace('\\','/').replace('"',"'")+'"'
    for p in sorted((BASE/'HD00'/'projects').glob('PROJ*.BIN')):
        b=p.read_bytes();u=lambda o:struct.unpack_from('<I',b,o)[0]
        assert u(21)==48000
        n=u(301);off=317+n*20;markers=[];tracks=[];end=0
        for i in range(n):
            o=317+20*i;pos=u(o);id=u(o+4);name=b[o+8:o+20].split(b'\0')[0].decode('ascii').strip()
            if not name:name=('RADAR special marker %08X'%id) if id>=0xfffffffe else 'RADAR marker %d'%id
            markers.append(dict(samples=pos,radar_id=id,name=name))
        for t in range(24):
            count=u(off);off+=4;clips=[];prev=0
            for j in range(count):
                raw=struct.unpack_from('<8I',b,off);off+=32;pos,id,src,length=raw[3:7]
                assert id in media and src+length<=int(media[id]['samples'])
                assert pos>=prev;prev=pos+length;end=max(end,prev)
                clips.append(dict(position_samples=pos,source_id='%08X'%id,source_offset_samples=src,length_samples=length,raw_record=list(raw)))
                cliprows.append(dict(project=p.stem,track=t+1,clip=j+1,source_id='%08X'%id,position_samples=pos,source_offset_samples=src,length_samples=length))
            tracks.append(clips)
        assert off==len(b)
        lines=['<REAPER_PROJECT 0.1 7.0 1','  SAMPLERATE 48000','  TEMPO 120','  TIMELOCKMODE 1','  RIPPLE 0','  AUTOXFADE 0','  <NOTES','    |Recovered from Otari RADAR 1 '+p.name+'. Sample-accurate source positions and offsets.','    |Track names are generic; original mix/mute settings and tempo were not decoded.','    |Short rendered edit segments are preserved; no additional fades or normalization.','  >']
        for i,m in enumerate(markers,1):lines.append('  MARKER %d %.12f %s 0'%(i,m['samples']/48000.,q(m['name'])))
        for t,clips in enumerate(tracks,1):
            lines+=['  <TRACK','    NAME '+q('RADAR Track %02d'%t),'    VOLPAN 1 0 1 -1','    MUTESOLO 0 0 0','    MAINSEND 1']
            for c in clips:
                r=media[int(c['source_id'],16)];path=os.path.relpath(str(BASE/r['wav']),str(OUT)).replace('\\','/')
                lines+=['    <ITEM','      POSITION %.12f'%(c['position_samples']/48000.),'      LENGTH %.12f'%(c['length_samples']/48000.),'      SOFFS %.12f'%(c['source_offset_samples']/48000.),'      SNAPOFFS 0','      LOOP 0','      VOLPAN 1 0 1 -1','      FADEIN 1 0 0','      FADEOUT 1 0 0','      NAME '+q(c['source_id']),'      <SOURCE WAVE','        FILE '+q(path),'      >','    >']
            lines.append('  >')
        lines.append('>')
        rpp=OUT/(p.stem+'.rpp');rpp.write_text('\n'.join(lines)+'\n',encoding='utf-8')
        report=dict(project=p.stem,tracks=24,active_tracks=sum(bool(c) for c in tracks),clips=sum(map(len,tracks)),markers=markers,duration_samples=end,duration_seconds=end/48000.,track_clips=tracks)
        (OUT/(p.stem+'_decoded.json')).write_text(json.dumps(report,indent=2))
        # Verify serialized values round back to the exact source sample counts.
        text=rpp.read_text();import re
        for key,field in [('POSITION','position_samples'),('LENGTH','length_samples'),('SOFFS','source_offset_samples')]:
            actual=[round(float(v)*48000) for v in re.findall(r'^      '+key+r' ([0-9.]+)$',text,re.M)]
            expected=[c[field] for tr in tracks for c in tr];assert actual==expected
        assert text.count('<ITEM')==report['clips'] and text.count('<TRACK')==24
        reports.append({k:v for k,v in report.items() if k not in ['markers','track_clips']})
    with (OUT/'clips.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['project','track','clip','source_id','position_samples','source_offset_samples','length_samples']);w.writeheader();w.writerows(cliprows)
    (OUT/'summary.json').write_text(json.dumps(reports,indent=2))
    print(json.dumps(reports,indent=2))


def main():
    if sys.flags.optimize:
        raise ValueError('Run without -O/-OO: this converter uses assert for integrity checks.')
    parser=argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--images', nargs='+', type=Path, required=True, help='All images belonging to the project set; ordering does not matter')
    parser.add_argument('--output', required=True, type=Path, help='New or empty destination directory')
    parser.add_argument('--sox', type=Path, help='Path to sox.exe (otherwise checks the bundled sox folder and PATH)')
    args=parser.parse_args()
    images=[p.resolve() for p in args.images]
    if len(set(images))!=len(images): parser.error('Duplicate image path')
    disk_ids=set()
    for p in images:
        if not p.is_file(): parser.error('Image not found: '+str(p))
        with p.open('rb') as f:
            f.seek(16384); h=f.read(512)
        if len(h)!=512 or h[3:11]!=b'RADAR5.0' or h[54:59]!=b'FAT20':
            parser.error('Unsupported image header: '+str(p))
        # Guard the fixed geometry used by the recovered FAT20 reader.
        if (struct.unpack_from('<H',h,11)[0],h[13],struct.unpack_from('<H',h,14)[0],h[16],struct.unpack_from('<H',h,17)[0],struct.unpack_from('<H',h,22)[0]) != (512,64,58,2,512,323):
            parser.error('Unsupported filesystem geometry: '+str(p))
        disk_id=h[36]-0xF0
        if disk_id not in (0,1,2) or disk_id in disk_ids: parser.error('Invalid/duplicate disk ID: '+str(p))
        disk_ids.add(disk_id)
    if 0 not in disk_ids: parser.error('The primary RADAR disk (ID 0) is required for project metadata')
    bundled=Path(__file__).resolve().parent/'sox'/'sox-14.4.2'/'sox.exe'
    sox=str(args.sox.resolve()) if args.sox else (str(bundled) if bundled.is_file() else shutil.which('sox'))
    if not sox: parser.error('SoX not found; supply --sox "C:/path/to/sox.exe"')
    version=subprocess.run([sox,'--version'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True)
    print(version.stdout.decode(errors='replace').strip(),flush=True)
    output=args.output.resolve()
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        parser.error('Output must be a new or empty folder; existing recoveries will not be overwritten')
    output.mkdir(parents=True,exist_ok=True)
    try:
        extract_images(images,output,sox)
        build_projects(output)
    except Exception:
        print('Recovery stopped. Partial output is retained for inspection. Re-run into a new empty folder.',file=sys.stderr)
        raise
    print('Complete. Open the .rpp files in '+str(output/'REAPER'),flush=True)


if __name__=='__main__':
    main()
