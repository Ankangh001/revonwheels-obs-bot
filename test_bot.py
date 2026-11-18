import base64
import hashlib
import json
from pathlib import Path
import socket
import struct
import tempfile
import threading
import unittest
import copy
from bot import Controller, CONFIG, execute
from obs_client import OBS, ObsError


class FakeOBS:
    def __init__(self):
        self.calls=[]; self.main='Gameplay'; self.vertical='Vertical Gameplay'
        self.mutes={'Desktop Audio':False,'Mic/Aux':True}; self.active=False
        self.fail=set()

    def call(self,kind,**d):
        self.calls.append((kind,d))
        if kind in self.fail:raise ObsError('simulated '+kind)
        if kind=='GetCurrentProgramScene':return {'currentProgramSceneName':self.main}
        if kind=='SetCurrentProgramScene':self.main=d['sceneName']
        if kind=='GetInputMute':return {'inputMuted':self.mutes[d['inputName']]}
        if kind=='SetInputMute':self.mutes[d['inputName']]=d['inputMuted']
        if kind=='GetSceneList':return {'scenes':[{'sceneName':self.main}]}
        if kind=='GetSceneItemList':return {'sceneItems':[{'sourceName':'Video Capture Device','sceneItemId':4}]}
        if kind=='GetSceneItemEnabled':return {'sceneItemEnabled':False}
        if kind in ('GetStreamStatus','GetReplayBufferStatus'):return {'outputActive':self.active}
        if kind=='StartStream':self.active=True
        if kind=='StopStream':self.active=False
        return {}

    def vendor(self,kind,**d):
        self.calls.append((kind,d))
        if kind in self.fail:raise ObsError('simulated '+kind)
        if kind=='current_scene':return {'scene':self.vertical}
        if kind=='switch_scene':self.vertical=d['scene']
        if kind=='get_outputs':return {'outputs':[{'name':'Twitch','active':True,'stream_key':'DO-NOT-PRINT'}]}
        if kind=='get_canvas':return {'canvas':[{'name':'YouTube Vertical','uuid':'portrait-canvas'}]}
        if kind=='get_scenes':return {'scenes':[{'name':p[1]} for p in self.config['scenes'].values()]}
        return {'success':True}


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.o=FakeOBS()
        config=copy.deepcopy(CONFIG)
        config['scenes']={'prepare':['Starting Soon','Vertical Starting Soon'],'gameplay':['Gameplay','Vertical Gameplay'],'brb':['Be Right Back','Vertical Be Right Back']}
        config.pop('safe_scenes',None)
        config['mute_on_safe']=['Desktop Audio','Mic/Aux']
        self.o.config=config
        self.c=Controller(self.o,config=config,state_path=Path(self.tmp.name)/'state.json')
    def tearDown(self):self.tmp.cleanup()
    def test_prepare_never_starts_streams(self):
        self.c.run('prepare')
        self.assertEqual((self.o.main,self.o.vertical),('Starting Soon','Vertical Starting Soon'))
        self.assertFalse(any('Start' in k for k,d in self.o.calls))
        self.assertTrue(any(k=='SetSceneItemEnabled' and d['sceneItemEnabled'] is False for k,d in self.o.calls))
    def test_safe_is_latched_and_restores_original_mute_states(self):
        self.c.run('safe');self.c.run('safe')
        self.assertTrue(all(self.o.mutes.values()))
        self.assertEqual(self.o.main,'Be Right Back')
        with self.assertRaises(ObsError):self.c.run('gameplay')
        self.c.run('resume')
        self.assertEqual(self.o.mutes,{'Desktop Audio':False,'Mic/Aux':True})
        self.assertEqual((self.o.main,self.o.vertical),('Gameplay','Vertical Gameplay'))
        self.assertFalse(self.c.state_path.exists())
    def test_all_streams_excludes_recording(self):
        self.c.run('live all')
        self.assertEqual([d['output'] for k,d in self.o.calls if k=='start_output'],CONFIG['outputs'])
        self.assertFalse(any('Record' in k for k,d in self.o.calls))
    def test_youtube_only(self):
        self.c.run('live youtube')
        self.assertEqual([d['output'] for k,d in self.o.calls if k=='start_output'],['YouTube Vertical'])
    def test_vertical_camera_visibility_uses_canvas_uuid(self):
        original=self.o.call
        def canvas_aware(kind,**data):
            if data.get('sceneName','').startswith('Vertical '):
                self.assertEqual(data.get('canvasUuid'),'portrait-canvas')
            return original(kind,**data)
        self.o.call=canvas_aware
        self.c.run('prepare')
        writes=[d for k,d in self.o.calls if k=='SetSceneItemEnabled' and d.get('canvasUuid')]
        self.assertEqual(len(writes),3)
    def test_missing_vertical_canvas_does_not_claim_prepared(self):
        original=self.o.vendor
        self.o.vendor=lambda kind,**d: {'canvas':[]} if kind=='get_canvas' else original(kind,**d)
        with self.assertRaises(ObsError):self.c.run('prepare')
        self.assertFalse(any(k=='SetCurrentProgramScene' for k,d in self.o.calls))
    def test_stop_main_even_when_plugin_fails(self):
        self.o.active=True;self.o.fail={'stop_all_streams'}
        with self.assertRaises(ObsError):self.c.run('stop')
        self.assertFalse(self.o.active)
    def test_status_never_discloses_plugin_credentials(self):
        s=self.c.run('status')
        self.assertNotIn('DO-NOT-PRINT',s);self.assertNotIn('stream_key',s)
    def test_no_highlight_without_buffer(self):
        with self.assertRaises(ObsError):self.c.run('highlight')
        self.assertFalse(any(k=='SaveReplayBuffer' for k,d in self.o.calls))
    def test_unknown_command_does_not_connect(self):
        with self.assertRaises(ObsError):execute('make me famous')
    def test_safe_still_covers_if_audio_mute_fails(self):
        self.o.fail={'SetInputMute'}
        with self.assertRaises(ObsError):self.c.run('safe')
        self.assertEqual((self.o.main,self.o.vertical),('Be Right Back','Vertical Be Right Back'))


class WebSocketTests(unittest.TestCase):
    def test_authenticated_rpc_with_ping_and_fragmented_response(self):
        server=socket.socket();server.bind(('127.0.0.1',0));server.listen(1)
        errors=[]
        def worker():
            try:
                s,_=server.accept();s.settimeout(3)
                def exact(n):
                    data=b''
                    while len(data)<n:
                        part=s.recv(n-len(data))
                        if not part:raise RuntimeError('Unexpected EOF')
                        data+=part
                    return data
                def recv_frame():
                    a,b=exact(2);n=b&127
                    if n==126:n=struct.unpack('!H',exact(2))[0]
                    elif n==127:n=struct.unpack('!Q',exact(8))[0]
                    self.assertTrue(b&128)
                    mask=exact(4);data=exact(n)
                    return a&15,bytes(v^mask[i%4] for i,v in enumerate(data))
                def frame(data,op=1,fin=True):
                    n=len(data);h=bytes([(128 if fin else 0)|op])
                    h+=bytes([n]) if n<126 else bytes([126])+struct.pack('!H',n)
                    s.sendall(h+data)
                head=b''
                while not head.endswith(b'\r\n\r\n'):head+=exact(1)
                key=[x.split(b': ',1)[1] for x in head.split(b'\r\n') if x.lower().startswith(b'sec-websocket-key:')][0]
                accept=base64.b64encode(hashlib.sha1(key+b'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').digest())
                s.sendall(b'HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: '+accept+b'\r\n\r\n')
                frame(json.dumps({'op':0,'d':{'rpcVersion':1,'authentication':{'salt':'salt','challenge':'challenge'}}}).encode())
                _,data=recv_frame();identify=json.loads(data)
                secret=base64.b64encode(hashlib.sha256(b'passwordsalt').digest())
                expected=base64.b64encode(hashlib.sha256(secret+b'challenge').digest()).decode()
                self.assertEqual(identify['d']['authentication'],expected)
                frame(b'{"op":2,"d":{"negotiatedRpcVersion":1}}')
                _,data=recv_frame();request=json.loads(data)
                frame(b'hello',9);op,pong=recv_frame();self.assertEqual((op,pong),(10,b'hello'))
                result=json.dumps({'op':7,'d':{'requestId':request['d']['requestId'],'requestStatus':{'result':True},'responseData':{'obsVersion':'33.0.1'}}}).encode()
                frame(result[:35],fin=False);frame(result[35:],op=0)
                s.close()
            except BaseException as e:errors.append(e)
            finally:server.close()
        t=threading.Thread(target=worker,daemon=True);t.start()
        o=OBS(server.getsockname()[1],'password')
        try:self.assertEqual(o.call('GetVersion'),{'obsVersion':'33.0.1'})
        finally:o.close()
        t.join(4);self.assertFalse(t.is_alive())
        if errors:raise errors[0]

if __name__=='__main__':unittest.main()
