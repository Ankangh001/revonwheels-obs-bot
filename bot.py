"""RevOnWheels local command controller. No stream keys or cloud credentials."""
import argparse
import json
import os
from pathlib import Path
import sys
import time
from obs_client import OBS, ObsError

from runtime_paths import ROOT
CONFIG = json.loads((ROOT/('config.json' if (ROOT/'config.json').exists() else 'config.example.json')).read_text())
STATE = ROOT/'safe-state.json'
ALIASES = {'starting soon':'prepare','prepare stream':'prepare','prepare gta':'prepare','prepare gta 6':'prepare',
           'show gameplay':'gameplay','play':'gameplay','show break banner':'brb','break':'brb',
           'safe screen':'safe','hide gameplay':'safe','panic':'safe','resume stream':'resume',
           'stop all':'stop','stop all streams':'stop','stop streaming':'stop','go live everywhere':'live all',
           'go live youtube':'live youtube','show stream links':'links','save highlight':'highlight',
           'mute mic':'mic off','unmute mic':'mic on'}
HELP = '''COMMANDS
  dependencies check / download aitum / download obs / install aitum / install obs
  setup auto ps5  Build from empty scenes, detect HDMI card, audio, select banners
  setup auto pc   Build from empty scenes, detect running GTA game and audio
  setup plan      Inspect the automatic setup plan without changing OBS
  setup stage     Add a NEW inactive PS5 setup without interrupting outputs
  setup ps5       Build/repair all ROW scenes; capture waits for your card
  setup pc        Build/repair all ROW scenes using existing GTA V capture
  setup check     Validate the managed scene setup
  setup activate  Route bot commands to ROW scenes and show starting banners
  setup rollback  Restore original bot scene routing (delete nothing)
  devices         List connected video devices
  capture ps5 N   Select capture device number N from the devices list
  quality auto    Choose supported PS5 capture quality and match OBS output
  status          Read current OBS connection and outputs
  prepare         Starting Soon on BOTH layouts; hide webcam
  gameplay        Gameplay on BOTH layouts
  brb             Break banners on BOTH layouts
  safe            Cover both layouts, mute game/mic, hide webcam
  resume          Restore scenes/audio saved by safe
  camera off      Hide webcam in accessible scenes
  mic on / off    Unmute/mute microphone
  live all        Start YouTube + Twitch + Kick + YouTube Vertical
  live youtube    Start main YouTube and vertical only
  stop            Stop ALL stream outputs (keeps recordings running)
  highlight       Save replay buffer (must already be running)
  links           Show channel links
  doctor          Check one-time OBS setup
  help / quit
YouTube event creation/metadata and AI censorship are NOT implemented in v1.
live commands start encoder outputs; YouTube may still require Go live in Studio.'''


def connection():
    p = Path(os.environ.get('APPDATA',''))/'obs-studio/plugin_config/obs-websocket/config.json'
    if not p.exists(): raise ObsError('OBS WebSocket configuration not found. Open OBS Tools > WebSocket Server Settings.')
    c = json.loads(p.read_text(encoding='utf-8-sig'))
    if not c.get('server_enabled'):
        raise ObsError('One-time setup: OBS > Tools > WebSocket Server Settings > Enable WebSocket server > Apply. Keep authentication enabled. Then run doctor.')
    if not c.get('auth_required'):
        raise ObsError('Enable authentication in OBS WebSocket Server Settings first.')
    return OBS(c.get('server_port',4455),c.get('server_password',''))


class Controller:
    def __init__(self, obs, config=CONFIG, state_path=STATE):
        self.o,self.c,self.state_path = obs,config,Path(state_path)

    def scene_pair(self, main, vertical):
        # Both commands must complete before reporting success; never silently fall back.
        self.o.call('SetCurrentProgramScene',sceneName=main)
        self.o.vendor('switch_scene',canvas=self.c['canvas'],scene=vertical)
        for _ in range(20):
            a=self.o.call('GetCurrentProgramScene')['currentProgramSceneName']
            b=self.o.vendor('current_scene',canvas=self.c['canvas']).get('scene')
            if (a,b)==(main,vertical): return
            time.sleep(.1)
        raise ObsError('Both scene changes were requested, but could not be verified. Check OBS.')

    def camera_off(self):
        # OBS 33 resolves sceneName within a canvas, not across every canvas.
        # Always carry Aitum's canvas UUID into both visibility reads and writes.
        refs=[({'sceneName':s['sceneName']},s['sceneName'])
              for s in self.o.call('GetSceneList')['scenes']]
        canvases=self.o.vendor('get_canvas').get('canvas',[])
        canvas=next((c for c in canvases if c.get('name')==self.c['canvas'] or c.get('uuid')==self.c['canvas']),None)
        if not canvas:raise ObsError('Vertical canvas not found: '+self.c['canvas'])
        scenes=self.o.vendor('get_scenes',canvas=canvas['uuid']).get('scenes',[])
        expected={pair[1] for pair in self.c['scenes'].values()}
        actual={s['name'] for s in scenes}
        if expected-actual:raise ObsError('Vertical scenes missing: '+', '.join(sorted(expected-actual)))
        refs.extend(({'canvasUuid':canvas['uuid'],'sceneName':s['name']},s['name']) for s in scenes)
        hidden,unavailable=0,[]
        for ref,name in refs:
            try: items=self.o.call('GetSceneItemList',**ref)['sceneItems']
            except ObsError:
                unavailable.append(name)
                continue
            for item in items:
                if item['sourceName']==self.c['camera']:
                    self.o.call('SetSceneItemEnabled',**ref,sceneItemId=item['sceneItemId'],sceneItemEnabled=False)
                    check=self.o.call('GetSceneItemEnabled',**ref,sceneItemId=item['sceneItemId'])
                    if check['sceneItemEnabled']:raise ObsError('Webcam still visible in '+name)
                    hidden+=1
        return hidden,unavailable

    def run(self, command):
        if command.startswith('setup') or command in ('devices','quality auto') or command.startswith('capture ps5 '):
            from setup_obs import Setup
            s=Setup(self.o,self.c)
            if self.state_path.exists() and command not in ('setup plan','setup check','devices'):
                raise ObsError('Safe Screen is latched. Resume before changing the setup.')
            if command=='setup plan':return s.plan()
            if command=='quality auto':
                from quality import automatic
                return automatic(s)
            if command in ('setup auto pc','setup auto ps5'):return s.automatic(command.split()[-1])
            if command=='setup stage':return s.build('ps5',stage=True)
            if command in ('setup','setup ps5'):return s.build('ps5')
            if command=='setup pc':return s.build('pc')
            if command=='setup check':return s.check()
            if command=='setup activate':return s.activate()
            if command=='setup rollback':return s.rollback()
            if command=='devices':return s.devices()
            if command.startswith('capture ps5 '):return s.capture(command.removeprefix('capture ps5 '))
            raise ObsError('Unknown setup command. Type help.')
        if command in self.c['scenes']:
            if self.state_path.exists(): raise ObsError('Safe Screen is latched. Use resume before changing scenes.')
            if command=='prepare':
                _,missing=self.camera_off()
                if missing: raise ObsError('Cannot verify webcam-off in: '+', '.join(missing)+'. Check those scenes in OBS before preparing.')
            self.scene_pair(*self.c['scenes'][command])
            return 'Both layouts switched to '+command+'.'
        if command=='status':
            main=self.o.call('GetStreamStatus')
            outputs=self.o.vendor('get_outputs').get('outputs',[])
            # Never print plugin settings: output objects can contain credentials.
            names=[{k:x[k] for k in ('name','active','streaming','outputActive') if k in x} for x in outputs]
            return json.dumps({'main_stream_active':main['outputActive'],'scene':self.o.call('GetCurrentProgramScene')['currentProgramSceneName'],'vertical_scene':self.o.vendor('current_scene',canvas=self.c['canvas']).get('scene'),'outputs':names},indent=2)
        if command=='camera off':
            count,missing=self.camera_off()
            return f'Webcam hidden in {count} scene references.'+(' Could not inspect: '+', '.join(missing) if missing else '')
        if command in ('mic on','mic off'):
            if command=='mic on' and self.state_path.exists(): raise ObsError('Safe Screen is active; resume before unmuting.')
            self.o.call('SetInputMute',inputName=self.c.get('microphone','Mic/Aux'),inputMuted=command=='mic off')
            return command
        if command=='safe':
            if not self.state_path.exists():
                state={'main':self.o.call('GetCurrentProgramScene')['currentProgramSceneName'],
                       'vertical':self.o.vendor('current_scene',canvas=self.c['canvas'])['scene'],
                       'mutes':{n:self.o.call('GetInputMute',inputName=n)['inputMuted'] for n in self.c['mute_on_safe']}}
                self.state_path.write_text(json.dumps(state))
            errors=[]
            for name in self.c['mute_on_safe']:
                try:self.o.call('SetInputMute',inputName=name,inputMuted=True)
                except Exception as e:errors.append(str(e))
            # Cut avoids a fade exposing the outgoing scene during a manual cover.
            for action in (lambda:self.o.call('SetCurrentSceneTransition',transitionName='Cut'),
                           lambda:self.o.vendor('switch_transition',canvas=self.c['canvas'],transition='Cut'),
                           lambda:self.scene_pair(*self.c.get('safe_scenes',self.c['scenes']['brb'])), self.camera_off):
                try:action()
                except Exception as e:errors.append(str(e))
            if errors:raise ObsError('Safe Screen incomplete; check OBS immediately: '+'; '.join(errors))
            return 'Safe Screen active on both layouts. Game and mic muted. Use resume to restore. Not automatic censorship.'
        if command=='resume':
            if not self.state_path.exists(): raise ObsError('No saved Safe Screen state.')
            s=json.loads(self.state_path.read_text())
            self.scene_pair(s['main'],s['vertical'])
            for name,muted in s['mutes'].items():self.o.call('SetInputMute',inputName=name,inputMuted=muted)
            self.state_path.unlink()
            return 'Previous scenes and audio restored; camera stays off. Transitions remain Cut.'
        if command.startswith('live '):
            if self.state_path.exists():raise ObsError('Safe Screen is latched. Resume before starting outputs.')
            self.o.vendor('version')  # Preflight plugin before starting main.
            if not self.o.call('GetStreamStatus')['outputActive']:self.o.call('StartStream')
            outputs=self.c['outputs'] if command=='live all' else ['YouTube Vertical']
            errors=[]
            for name in outputs:
                try:self.o.vendor('start_output',output=name)
                except Exception as e:errors.append(name+': '+str(e))
            if errors:raise ObsError('Some outputs may already be sending. '+ '; '.join(errors))
            return 'Start requests sent. Run status and verify platform dashboards; YouTube may need Go live in Studio. This does not create a broadcast.'
        if command=='stop':
            errors=[]
            try:self.o.vendor('stop_all_streams')
            except Exception as e:errors.append(str(e))
            try:
                if self.o.call('GetStreamStatus')['outputActive']:self.o.call('StopStream')
            except Exception as e:errors.append(str(e))
            if errors:raise ObsError('Stop incomplete; use OBS Ctrl+Shift+F12: '+'; '.join(errors))
            return 'Stop requests sent for all streams. Recordings were not stopped. Check status; end YouTube in Studio if it stays live.'
        if command=='highlight':
            if not self.o.call('GetReplayBufferStatus')['outputActive']:raise ObsError('Replay Buffer is not running. Enable/configure it in OBS before using highlight.')
            self.o.call('SaveReplayBuffer')
            return 'Replay save requested. Check your OBS recording folder.'
        if command=='doctor':
            self.o.call('GetVersion')
            self.o.vendor('version')
            self.o.vendor('get_scenes',canvas=self.c['canvas'])
            return 'OBS authentication and Aitum canvas connection OK. Run status. Live publishing/PS5 capture are separate checks.'
        raise ObsError('Unknown command. Type help.')


def execute(command):
    command=' '.join(command.strip().lower().split())
    command=ALIASES.get(command,command)
    if command=='help':return HELP
    if command.startswith('dependencies'):
        from dependencies import run
        return run(command)
    if command=='links':return '\n'.join(f'{k}: {v}' for k,v in CONFIG['links'].items())
    if command not in {'setup auto pc','setup auto ps5','quality auto'}|set(CONFIG['scenes'])|{'status','camera off','mic on','mic off','safe','resume','live all','live youtube','stop','highlight','doctor','setup','setup plan','setup stage','setup pc','setup ps5','setup activate','setup check','setup rollback','devices'} and not command.startswith('capture ps5 '):
        raise ObsError('Unknown command. Type help.')
    o=connection()
    try:return Controller(o).run(command)
    finally:o.close()


def main():
    p=argparse.ArgumentParser(description='RevOnWheels local stream bot')
    p.add_argument('command',nargs='*')
    args=p.parse_args()
    if args.command:
        try:print(execute(' '.join(args.command)))
        except (OSError,ValueError,ObsError) as e:print('ERROR:',e);return 1
        return 0
    print('RevOnWheels Bot — local commands. No voice/chat integration.\n'+HELP)
    while True:
        try:
            command=input('\nRevOnWheels> ')
            if command.strip().lower() in ('quit','exit'):return 0
            if command.strip():print(execute(command))
        except (EOFError,KeyboardInterrupt):return 0
        except Exception as e:print('ERROR:',e)

if __name__=='__main__':sys.exit(main())
