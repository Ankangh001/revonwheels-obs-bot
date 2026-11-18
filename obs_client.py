"""Dependency-free, loopback-only OBS WebSocket v5 client."""
import base64
import hashlib
import json
import os
import socket
import struct
import time
import uuid


class ObsError(RuntimeError):
    pass


class OBS:
    def __init__(self, port=4455, password='', timeout=8):
        self.sock = socket.create_connection(('127.0.0.1', port), timeout)
        self.sock.settimeout(timeout)
        self.buffer = b''
        try:
            key = base64.b64encode(os.urandom(16)).decode()
            self.sock.sendall((f'GET / HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n').encode())
            header = b''
            while b'\r\n\r\n' not in header:
                part = self.sock.recv(4096)
                if not part or len(header) > 65536:
                    raise ObsError('Invalid WebSocket handshake')
                header += part
            head, self.buffer = header.split(b'\r\n\r\n', 1)
            expected = base64.b64encode(hashlib.sha1((key+'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest()).decode()
            fields = dict(line.decode().split(':', 1) for line in head.split(b'\r\n')[1:] if b':' in line)
            fields = {k.lower(): v.strip() for k,v in fields.items()}
            if head.split(b'\r\n')[0].split()[1] != b'101' or fields.get('sec-websocket-accept') != expected:
                raise ObsError('OBS WebSocket handshake rejected')
            hello = self.recv()
            if hello.get('op') != 0:
                raise ObsError('Expected OBS Hello')
            identify = {'rpcVersion': 1, 'eventSubscriptions': 0}
            auth = hello['d'].get('authentication')
            if auth:
                secret = base64.b64encode(hashlib.sha256((password+auth['salt']).encode()).digest()).decode()
                identify['authentication'] = base64.b64encode(hashlib.sha256((secret+auth['challenge']).encode()).digest()).decode()
            self.send({'op':1,'d':identify})
            if self.recv().get('op') != 2:
                raise ObsError('OBS authentication failed')
        except Exception:
            self.close()
            raise

    def close(self):
        self.sock.close()

    def read(self, n):
        while len(self.buffer) < n:
            part = self.sock.recv(max(4096,n-len(self.buffer)))
            if not part:
                raise ObsError('OBS disconnected')
            self.buffer += part
        result,self.buffer = self.buffer[:n],self.buffer[n:]
        return result

    def frame(self, payload, opcode=1):
        mask = os.urandom(4)
        size = len(payload)
        h = bytes([0x80|opcode])
        h += bytes([0x80|size]) if size < 126 else (bytes([0xfe])+struct.pack('!H',size) if size < 65536 else bytes([0xff])+struct.pack('!Q',size))
        self.sock.sendall(h+mask+bytes(b^mask[i%4] for i,b in enumerate(payload)))

    def send(self, obj):
        self.frame(json.dumps(obj).encode())

    def recv(self):
        pieces = bytearray()
        while True:
            a,b = self.read(2)
            opcode,fin,size = a&15,a&128,b&127
            if size == 126: size = struct.unpack('!H',self.read(2))[0]
            elif size == 127: size = struct.unpack('!Q',self.read(8))[0]
            if size > 16*1024*1024: raise ObsError('OBS frame too large')
            mask = self.read(4) if b&128 else None
            payload = self.read(size)
            if mask: payload = bytes(v^mask[i%4] for i,v in enumerate(payload))
            if opcode == 8: raise ObsError('OBS closed connection; check WebSocket password')
            if opcode == 9:
                self.frame(payload,10)
                continue
            if opcode == 10: continue
            if opcode not in (0,1): raise ObsError('Unsupported OBS frame')
            pieces.extend(payload)
            if len(pieces)>16*1024*1024: raise ObsError('OBS message too large')
            if fin: return json.loads(pieces.decode())

    def call(self, kind, **data):
        rid = str(uuid.uuid4())
        self.send({'op':6,'d':{'requestType':kind,'requestId':rid,'requestData':data}})
        deadline = time.monotonic()+8
        while time.monotonic()<deadline:
            msg = self.recv()
            if msg.get('op') != 7 or msg['d'].get('requestId') != rid: continue
            result = msg['d']
            if not result['requestStatus']['result']:
                raise ObsError(f"{kind}: {result['requestStatus'].get('comment','request rejected')}")
            return result.get('responseData',{})
        raise ObsError(f'{kind}: response timed out')

    def vendor(self, kind, **data):
        r = self.call('CallVendorRequest',vendorName='aitum-stream-suite',requestType=kind,requestData=data).get('responseData',{})
        if r.get('success') is False or r.get('error'):
            raise ObsError(f"Aitum {kind}: {r.get('error','request rejected')}")
        return r
