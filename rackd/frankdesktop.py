"""Frank's short-lived, authenticated RFB connection to a managed Windows desktop.

Uses the existing SSH tunnel and its pinned key. No listening ports or Python packages.
Only raw framebuffer updates are requested; PNG encoding uses the standard library.
"""
import os
import select
import struct
import subprocess
import threading
import time
import zlib

from .util import DriverError

_LOCK = threading.Lock()
_MAX_PIXELS = 24_000_000
_NODE = r"""const c=require('crypto'),fs=require('fs'),x=JSON.parse(fs.readFileSync(0,'utf8'));
const k=Buffer.alloc(8);Buffer.from(x.p,'ascii').copy(k,0,0,8);
for(let j=0;j<8;j++){let v=k[j],r=0;for(let i=0;i<8;i++){r=(r<<1)|(v&1);v>>=1;}k[j]=r;}
const e=c.createCipheriv('des-ecb',k,null);e.setAutoPadding(false);process.stdout.write(Buffer.concat([e.update(Buffer.from(x.c,'hex')),e.final()]));"""
KEYS = {'enter':0xff0d,'tab':0xff09,'escape':0xff1b,'esc':0xff1b,'backspace':0xff08,'delete':0xffff,
        'space':0x20,'up':0xff52,'down':0xff54,'left':0xff51,'right':0xff53,'home':0xff50,'end':0xff57,
        'pageup':0xff55,'pagedown':0xff56,'insert':0xff63,'win':0xffeb,'ctrl':0xffe3,'alt':0xffe9,'shift':0xffe1}
KEYS.update({'f'+str(i):0xffbd+i for i in range(1,13)})

class Session:
    def __init__(self, manager, device):
        self.manager, self.device, self.proc, self.keyfile = manager, device, None, None
    def read(self, n):
        out=bytearray(); deadline=time.monotonic()+30
        while len(out)<n:
            remain=deadline-time.monotonic()
            if remain<=0 or not select.select([self.proc.stdout],[],[],remain)[0]:
                raise DriverError('истекло время ожидания рабочего стола')
            part=os.read(self.proc.stdout.fileno(),min(n-len(out),262144))
            if not part: raise DriverError('соединение с рабочим столом прервано')
            out.extend(part)
        return bytes(out)
    def send(self,b):
        self.proc.stdin.write(b)
    def open(self):
        import json
        state=self.manager.state(self.device['id'])
        if not state.get('ready'): raise DriverError('сначала установи плагин рабочего стола')
        self.proc,self.keyfile,banner=self.manager.spawn(self.device)
        if banner[:8]!=b'RFB 003.': raise DriverError('неподдерживаемая версия рабочего стола')
        self.send(b'RFB 003.008\n')
        n=self.read(1)[0]; types=self.read(n)
        if 2 not in types: raise DriverError('сервер не поддерживает вход плагина')
        self.send(b'\x02'); challenge=self.read(16)
        try:
            result=subprocess.run(['node','--openssl-legacy-provider','-e',_NODE],input=json.dumps({'p':state['password'],'c':challenge.hex()}).encode(),capture_output=True,timeout=8)
        except (OSError,subprocess.SubprocessError): raise DriverError('недоступен компонент входа в рабочий стол')
        if result.returncode or len(result.stdout)!=16: raise DriverError('не удалось подготовить вход в рабочий стол')
        self.send(result.stdout)
        if self.read(4)!=b'\0\0\0\0': raise DriverError('вход в рабочий стол отклонён')
        self.send(b'\x01'); hdr=self.read(24)
        self.w,self.h=struct.unpack('>HH',hdr[:4]); n=struct.unpack('>I',hdr[20:24])[0]
        if n>65536: raise DriverError('некорректный ответ рабочего стола')
        self.read(n); self.dimensions()
        # Explicit little-endian 32-bit true colour, red at bit 16.
        self.send(b'\x00\0\0\0'+struct.pack('>BBBBHHHBBBxxx',32,24,0,1,255,255,255,16,8,0))
        self.send(b'\x02\0\0\x02'+struct.pack('>ii',0,-223))
    def dimensions(self):
        if not self.w or not self.h or self.w*self.h>_MAX_PIXELS: raise DriverError('неподдерживаемый размер экрана')
        scale=min(1,1280/self.w,900/self.h)
        self.sw=max(1,round(self.w*scale));self.sh=max(1,round(self.h*scale))
    def frame(self):
        for _ in range(6):
            self.send(b'\x03\0'+struct.pack('>HHHH',0,0,self.w,self.h))
            h=self.read(4)
            if h[0]!=0: raise DriverError('неожиданный ответ рабочего стола')
            rects=struct.unpack('>H',h[2:])[0]; image=bytearray(self.w*self.h*4); covered=0
            for _ in range(rects):
                x,y,w,h,enc=struct.unpack('>HHHHi',self.read(12))
                if enc==-223:
                    self.w,self.h=w,h;self.dimensions();image=bytearray(self.w*self.h*4);covered=0;continue
                if enc!=0 or x+w>self.w or y+h>self.h: raise DriverError('неподдерживаемый формат изображения')
                data=self.read(w*h*4); covered+=w*h
                for row in range(h): image[((y+row)*self.w+x)*4:((y+row)*self.w+x+w)*4]=data[row*w*4:(row+1)*w*4]
            if covered>=self.w*self.h: return image
        raise DriverError('не удалось получить полный кадр рабочего стола')
    def pointer(self,x,y,mask): self.send(struct.pack('>BBHH',5,mask,x,y))
    def key(self,key,down): self.send(struct.pack('>BBxxI',4,int(down),key))
    def xy(self,x,y):
        if isinstance(x,bool) or isinstance(y,bool) or not isinstance(x,(int,float)) or not isinstance(y,(int,float)) or not (0<=x<self.sw and 0<=y<self.sh):
            raise DriverError('координаты должны быть в пределах последнего снимка')
        return min(self.w-1,round(x*self.w/self.sw)),min(self.h-1,round(y*self.h/self.sh))
    def action(self,a):
        op=a.get('op')
        if op in ('click','double_click','right_click','move','drag','scroll'):
            x,y=self.xy(a.get('x'),a.get('y'));self.pointer(x,y,0)
            if op=='drag':
                x2,y2=self.xy(a.get('to_x'),a.get('to_y'));self.pointer(x,y,1)
                try:
                    for i in range(1,13): self.pointer(round(x+(x2-x)*i/12),round(y+(y2-y)*i/12),1);time.sleep(.025)
                finally:self.pointer(x2,y2,0)
            elif op=='scroll':
                amount=a.get('amount',-3)
                if isinstance(amount,bool) or not isinstance(amount,int) or not -10<=amount<=10: raise DriverError('прокрутка: от -10 до 10')
                for _ in range(abs(amount)):self.pointer(x,y,8 if amount>0 else 16);self.pointer(x,y,0)
            elif op!='move':
                for _ in range(2 if op=='double_click' else 1):self.pointer(x,y,4 if op=='right_click' else 1);self.pointer(x,y,0);time.sleep(.08)
        elif op=='type':
            text=a.get('text')
            if not isinstance(text,str) or len(text)>2000:raise DriverError('текст должен быть не длиннее 2000 знаков')
            for ch in text:
                k=0xff0d if ch=='\n' else 0xff09 if ch=='\t' else ord(ch) if 32<=ord(ch)<=255 else 0x01000000|ord(ch)
                self.key(k,True);self.key(k,False)
        elif op=='key':
            parts=str(a.get('key') or '').lower().split('+')
            if not 1<=len(parts)<=4:raise DriverError('неизвестное сочетание клавиш')
            keys=[]
            for p in parts:
                p=p.strip();k=KEYS.get(p) or (ord(p) if len(p)==1 and 32<=ord(p)<=126 else None)
                if not k:raise DriverError('неизвестная клавиша: '+p[:20])
                keys.append(k)
            try:
                for k in keys:self.key(k,True)
            finally:
                for k in reversed(keys):self.key(k,False)
        elif op!='shot':raise DriverError('неизвестное действие рабочего стола')
    def png(self,raw):
        rows=bytearray()
        for y in range(self.sh):
            rows.append(0); sy=min(self.h-1,int(y*self.h/self.sh))
            for x in range(self.sw):
                sx=min(self.w-1,int(x*self.w/self.sw));i=(sy*self.w+sx)*4
                rows.extend((raw[i+2],raw[i+1],raw[i]))
        def chunk(t,b):return struct.pack('>I',len(b))+t+b+struct.pack('>I',zlib.crc32(t+b)&0xffffffff)
        return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',self.sw,self.sh,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(rows,3))+chunk(b'IEND',b'')
    def close(self): self.manager.cleanup(self.proc,self.keyfile)

def run(manager,device,args):
    if not _LOCK.acquire(timeout=2):raise DriverError('Франк уже работает с экраном; попробуй ещё раз')
    session=Session(manager,device)
    try:
        session.open(); frame=session.frame()
        if args.get('op')!='shot': session.action(args);time.sleep(.5);frame=session.frame()
        return session.png(frame),session.sw,session.sh
    finally:
        session.close();_LOCK.release()
