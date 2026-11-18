"""Repeatable OBS scene provisioning through authenticated OBS/Aitum APIs."""
import copy
import json
from pathlib import Path
import time
from obs_client import ObsError

ROOT=Path(__file__).resolve().parent
ASSETS=Path.home()/'Pictures'/'Streaming Assets'
FILES={
    'landscape':ASSETS/'gta-one-last-ride-landscape-v1.png',
    'portrait':ASSETS/'gta-one-last-ride-portrait-v1.png',
    'brb':ASSETS/'gta-be-right-back-v1.png',
    'music':ROOT.parent/'Los-Santos-Nights-original-banner-loop.wav',
    'countdown':ROOT.parent/'gta-vi-countdown.html',
}
FILES={k:(ROOT/'assets'/p.name if (ROOT/'assets'/p.name).exists() else p) for k,p in FILES.items()}
SCENES={
    'prepare':['ROW - Starting Soon','ROW - Vertical Starting Soon'],
    'gameplay':['ROW - Gameplay','ROW - Vertical Gameplay'],
    'brb':['ROW - Be Right Back','ROW - Vertical Be Right Back'],
}
SAFE=['ROW - Safe Screen','ROW - Vertical Safe Screen']
PS5_INPUT='ROW - PS5 Capture'
PC_INPUT='ROW - Game Capture'


class Setup:
    def __init__(self,obs,config,root=ROOT,files=None):
        self.o,self.config,self.root=obs,config,Path(root)
        self.files=files if files is not None else FILES
        self.manifest_path=self.root/'setup-manifest.json'
        self.manifest=json.loads(self.manifest_path.read_text()) if self.manifest_path.exists() else {'scenes':[],'inputs':[],'mode':None}
        self.canvas=None;self.video=None

    def inspect(self):
        canvas=self.o.vendor('get_canvas').get('canvas',[])
        self.canvas=next((c for c in canvas if c.get('name')==self.config['canvas'] or c.get('uuid')==self.config['canvas']),None)
        if not self.canvas:raise ObsError('Aitum canvas is missing. Add a 720x1280 canvas named '+self.config['canvas']+' in OBS first.')
        self.video=self.o.call('GetVideoSettings')
        self.inputs={x['inputName']:x for x in self.o.call('GetInputList')['inputs']}
        for x in self.o.call('GetInputList',canvasUuid=self.canvas['uuid'])['inputs']:
            old=self.inputs.get(x['inputName'])
            if old and old.get('inputUuid')!=x.get('inputUuid'):
                raise ObsError('Ambiguous source name across canvases: '+x['inputName'])
            self.inputs[x['inputName']]=x
        return self

    def input_ref(self,name):
        uuid=self.inputs[name].get('inputUuid')
        return {'inputUuid':uuid} if uuid else {'inputName':name}

    def automatic(self,mode):
        """Build from zero sources, discover capture, then select the banners."""
        if mode not in ('pc','ps5'):raise ObsError('Use setup auto pc or setup auto ps5.')
        self.inspect();self.offline_only()
        if not (self.root/'config-before-setup.json').exists():
            (self.root/'config-before-setup.json').write_text(json.dumps(self.config,indent=2))
        notes=[]
        if mode=='pc':
            ref=self.scene(SCENES['gameplay'][0],False)
            self.input(ref,PC_INPUT,'game_capture',{'capture_mode':'window','capture_cursor':True,'capture_overlays':False})
            windows=self.o.call('GetInputPropertiesListPropertyItems',**self.input_ref(PC_INPUT),propertyName='window').get('propertyItems',[])
            matches=[x for x in windows if x.get('itemEnabled',True) and x.get('itemValue') and any(t in str(x['itemValue']).lower() for t in ('gta5.exe','gta5_enhanced.exe','gta6.exe','gta vi','grand theft auto'))]
            if len(matches)==1:
                self.o.call('SetInputSettings',**self.input_ref(PC_INPUT),inputSettings={'window':matches[0]['itemValue'],'capture_mode':'window'},overlay=True)
                notes.append('Game window selected: '+matches[0]['itemName'])
            else:
                # Never capture a desktop or an arbitrary foreground application.
                self.o.call('SetInputSettings',**self.input_ref(PC_INPUT),inputSettings={'window':'','capture_mode':'window'},overlay=True)
                notes.append('Game capture pending: launch one GTA game, then run setup auto pc again.')
            self.manifest['pc_capture']=PC_INPUT;self.persist()
        self.build(mode)
        if mode=='ps5':
            self.devices()
            devices=json.loads((self.root/'capture-devices.json').read_text())
            candidates=[x for x in devices if self.is_capture_card(x['itemName'])]
            if len(candidates)==1:notes.append(self.capture_named(candidates[0]['itemName']))
            elif candidates:notes.append('Multiple capture cards detected; use devices then capture ps5 <number>.')
            else:notes.append('No clearly identified HDMI capture card connected. Connect it and rerun setup auto ps5.')
        self.configure_audio(mode)
        self.activate()
        return 'Automatic setup complete; Starting Soon selected. No stream started.\n'+'\n'.join(notes)+'\n'+self.check()

    @staticmethod
    def is_capture_card(name):
        name=name.casefold()
        excluded=('webcam','camera','virtual','facetime','wide vision')
        return not any(s in name for s in excluded) and any(s in name for s in ('elgato','ugreen','capture','cam link','avermedia','hd60','4k x','game live'))

    def configure_audio(self,mode):
        self.inspect()
        ref=self.ref(SCENES['gameplay'][0])
        special=self.o.call('GetSpecialInputs')
        # Reuse global audio. Creating another copy would produce doubled sound.
        mic=next((special.get(k) for k in ('mic1','mic2','mic3','mic4') if special.get(k)),None)
        if not mic:
            mic='ROW - Microphone'
            existed=mic in self.inputs
            self.input(ref,mic,'wasapi_input_capture',{'device_id':'default'})
            if not existed:self.o.call('SetInputMute',**self.input_ref(mic),inputMuted=True)
            for vertical in (False,True):self.item(self.ref(SCENES['gameplay'][int(vertical)],vertical),mic)
        targets=[mic]+[special[k] for k in ('desktop1','desktop2') if special.get(k)]
        if mode=='pc':
            desktop=next((special.get(k) for k in ('desktop1','desktop2') if special.get(k)),None)
            if not desktop:
                desktop='ROW - Game Audio'
                self.input(ref,desktop,'wasapi_output_capture',{'device_id':'default'})
                for vertical in (False,True):self.item(self.ref(SCENES['gameplay'][int(vertical)],vertical),desktop)
            targets.append(desktop)
        else:
            if PS5_INPUT in self.inputs:targets.append(PS5_INPUT)
            for vertical in (False,True):
                r=self.ref(SCENES['gameplay'][int(vertical)],vertical)
                for item in self.o.call('GetSceneItemList',**r)['sceneItems']:
                    if item['sourceName']=='ROW - Game Audio':
                        self.o.call('SetSceneItemEnabled',**r,sceneItemId=item['sceneItemId'],sceneItemEnabled=False)
        self.config['microphone']=mic
        self.config['mute_on_safe']=list(dict.fromkeys(targets))
        (self.root/'config.json').write_text(json.dumps(self.config,indent=2))

    def offline_only(self):
        # Fail closed: plugin outputs may still run while the main stream is stopped.
        main=self.o.call('GetStreamStatus')['outputActive']
        native=self.o.call('GetOutputList').get('outputs',[])
        active=[x.get('outputName','unknown') for x in native if x.get('outputActive')]
        extra=self.o.vendor('get_outputs').get('outputs',[])
        active.extend(x.get('name','Aitum output') for x in extra if any(x.get(k) is True for k in ('active','outputActive','streaming','recording')))
        if main or active:raise ObsError('Setup changes require outputs stopped. Use setup plan while live. Active: '+(', '.join(active) or 'main stream'))

    def ref(self,name,vertical=False):
        r={'sceneName':name}
        if vertical:r['canvasUuid']=self.canvas['uuid']
        return r

    def persist(self):
        tmp=self.manifest_path.with_suffix('.tmp')
        tmp.write_text(json.dumps(self.manifest,indent=2));tmp.replace(self.manifest_path)

    def scene(self,name,vertical):
        ref=self.ref(name,vertical)
        names={s['sceneName'] for s in self.o.call('GetSceneList',**({'canvasUuid':self.canvas['uuid']} if vertical else {}))['scenes']}
        if name in names:
            if name not in self.manifest['scenes']:raise ObsError('Name collision with an unmanaged scene: '+name)
        else:
            self.o.call('CreateScene',**ref)
            if name not in self.manifest['scenes']:self.manifest['scenes'].append(name)
            self.persist()
        return ref

    def input(self,ref,name,kind,settings):
        if name not in self.inputs:
            created=self.o.call('CreateInput',**ref,inputName=name,inputKind=kind,inputSettings=settings,sceneItemEnabled=True)
            self.inputs[name]={'inputName':name,'inputKind':kind,'inputUuid':created.get('inputUuid')}
            self.manifest['inputs'].append(name);self.persist()
        else:
            if name not in self.manifest['inputs']:raise ObsError('Name collision with an unmanaged input: '+name)
            if self.inputs[name]['inputKind']!=kind:raise ObsError('Wrong source type for '+name)
            self.o.call('SetInputSettings',**self.input_ref(name),inputSettings=settings,overlay=True)
        return self.item(ref,name)

    def item(self,ref,name):
        items=self.o.call('GetSceneItemList',**ref)['sceneItems']
        found=[x for x in items if x['sourceName']==name]
        if len(found)>1:raise ObsError('Duplicate managed source in '+ref['sceneName']+': '+name)
        if found:
            item=found[0]['sceneItemId']
            self.o.call('SetSceneItemEnabled',**ref,sceneItemId=item,sceneItemEnabled=True)
            return item
        source={'sourceUuid':self.inputs[name]['inputUuid']} if self.inputs.get(name,{}).get('inputUuid') else {'sourceName':name}
        return self.o.call('CreateSceneItem',**ref,**source,sceneItemEnabled=True)['sceneItemId']

    def fit(self,ref,item,w,h,crop=False):
        self.o.call('SetSceneItemTransform',**ref,sceneItemId=item,sceneItemTransform={
            'positionX':0.,'positionY':0.,'rotation':0.,'alignment':5,
            'cropTop':0,'cropBottom':0,'cropLeft':0,'cropRight':0,
            'boundsType':'OBS_BOUNDS_SCALE_OUTER' if crop else 'OBS_BOUNDS_SCALE_INNER',
            'boundsAlignment':0,'boundsWidth':float(w),'boundsHeight':float(h),'boundsCrop':bool(crop)})

    def top(self,ref,item):
        n=len(self.o.call('GetSceneItemList',**ref)['sceneItems'])
        self.o.call('SetSceneItemIndex',**ref,sceneItemId=item,sceneItemIndex=n-1)

    def plan(self):
        self.inspect()
        missing=[str(p) for p in self.files.values() if not p.exists()]
        return '\n'.join([
            'SETUP PLAN (read-only)',
            f"Landscape: {self.video['baseWidth']}x{self.video['baseHeight']} canvas; {self.video['outputWidth']}x{self.video['outputHeight']} output",
            f"Portrait: {self.canvas['width']}x{self.canvas['height']} on {self.canvas['name']}",
            'Create/repair 8 ROW scenes: Starting Soon, Gameplay, BRB, Safe Screen in both formats.',
            'Add artwork, original looping music, responsive countdown, and opaque safety cards.',
            'setup auto pc creates GTA capture/audio; setup auto ps5 detects a unique recognised HDMI card.',
            'Existing scenes, encoder profile, stream keys, output destinations and account settings are preserved.',
            'No broadcasting, event creation, title publication, or AI censorship.',
            'Missing assets: '+(', '.join(missing) if missing else 'none'),
        ])

    def build(self,mode,stage=False):
        self.inspect()
        if stage:
            # A first-time additive build cannot affect the current scene. Never
            # update existing managed sources while live, since they may be visible.
            reserved={n for pair in list(SCENES.values())+[SAFE] for n in pair}
            existing=set()
            for scope in ({},{'canvasUuid':self.canvas['uuid']}):
                existing.update(x['sceneName'] for x in self.o.call('GetSceneList',**scope)['scenes'])
            if (reserved&existing)-set(self.manifest['scenes']) or any(n.startswith('ROW - ') and n not in self.manifest['inputs'] for n in self.inputs):
                raise ObsError('Staging found unmanaged ROW names. Stop outputs and resolve collisions before setup.')
            for n in self.manifest['inputs']:
                if n not in self.inputs:continue
                uuid=self.inputs[n].get('inputUuid')
                source={'sourceUuid':uuid} if uuid else {'sourceName':n}
                active=self.o.call('GetSourceActive',**source)
                if active.get('videoActive') or active.get('audioActive'):
                    raise ObsError('Staging cannot modify an active ROW source: '+n+'. Stop outputs before repair.')
        else:self.offline_only()
        if mode not in ('pc','ps5'):raise ObsError('Use setup pc or setup ps5.')
        missing=[str(p) for p in self.files.values() if not p.exists()]
        if missing:raise ObsError('Missing setup assets: '+', '.join(missing))
        pc_capture=self.manifest.get('pc_capture','GTA V Game Capture')
        if mode=='pc' and pc_capture not in self.inputs:raise ObsError('Run setup auto pc to create the game capture source.')
        backup=self.root/'backups';backup.mkdir(exist_ok=True)
        stamp=time.strftime('%Y%m%d-%H%M%S')
        (backup/f'config-{stamp}.json').write_text(json.dumps(self.config,indent=2))
        for vertical in (False,True):
            suffix='Portrait' if vertical else 'Landscape'
            w,h=(self.canvas['width'],self.canvas['height']) if vertical else (self.video['baseWidth'],self.video['baseHeight'])
            for action,pair in list(SCENES.items())+[('safe',SAFE)]:
                ref=self.scene(pair[int(vertical)],vertical)
                if action=='gameplay':
                    # Remove neither old captures nor user-added sources; disable only managed alternate placeholders.
                    previous=self.o.call('GetSceneItemList',**ref)['sceneItems']
                    for x in previous:
                        if x['sourceName'] in ('GTA V Game Capture',PC_INPUT,PS5_INPUT,'ROW - Capture Pending'):
                            self.o.call('SetSceneItemEnabled',**ref,sceneItemId=x['sceneItemId'],sceneItemEnabled=False)
                    if mode=='pc':
                        item=self.item(ref,pc_capture);self.fit(ref,item,w,h,crop=vertical)
                    elif PS5_INPUT in self.inputs:
                        item=self.item(ref,PS5_INPUT);self.fit(ref,item,w,h,crop=vertical)
                    else:
                        item=self.input(ref,'ROW - Capture Pending','text_gdiplus_v3',{'text':'PS5 CAPTURE NOT CONNECTED\nConnect the capture card, then use:\ndevices\ncapture ps5 <number>','font':{'face':'Arial','size':48,'flags':1},'color':0xffffffff,'outline':True,'outline_size':3,'align':'center'})
                        self.fit(ref,item,w,h)
                    continue
                artwork=self.files['portrait' if vertical else 'landscape'] if action=='prepare' else self.files['brb']
                item=self.input(ref,f'ROW - {action.title()} Art - {suffix}','image_source',{'file':str(artwork)})
                self.fit(ref,item,w,h,crop=True)
                if action=='safe':
                    item=self.input(ref,f'ROW - Safety Card - {suffix}','text_gdiplus_v3',{'text':'SAFE SCREEN\nGameplay temporarily hidden','font':{'face':'Arial','size':64 if vertical else 90,'flags':1},'color':0xffffffff,'outline':True,'outline_size':4,'align':'center','bk_color':0xff170c20,'bk_opacity':100})
                    self.o.call('SetSceneItemTransform',**ref,sceneItemId=item,sceneItemTransform={
                        'positionX':w*.07,'positionY':h*.275,'alignment':5,'boundsAlignment':0,
                        'boundsType':'OBS_BOUNDS_SCALE_INNER','boundsWidth':w*.86,'boundsHeight':h*.45})
                    self.top(ref,item)
                music=self.input(ref,'ROW - Banner Music','ffmpeg_source',{'is_local_file':True,'local_file':str(self.files['music']),'looping':True,'restart_on_activate':False,'close_when_inactive':True})
                self.o.call('SetInputVolume',**self.input_ref('ROW - Banner Music'),inputVolumeDb=-8.)
                if action!='safe':
                    item=self.input(ref,f'ROW - Countdown - {suffix}','browser_source',{'is_local_file':False,'url':self.files['countdown'].resolve().as_uri(),'width':w,'height':h,'shutdown':False,'reroute_audio':False})
                    self.fit(ref,item,w,h);self.top(ref,item)
        self.manifest['mode']=mode;self.persist()
        report=self.check()
        return 'Setup built. Your current scenes were not switched. Run setup activate when ready.\n'+report

    def check(self):
        self.inspect()
        failures=[];count=0
        for action,pair in list(SCENES.items())+[('safe',SAFE)]:
            for vertical,name in enumerate(pair):
                try:
                    items=self.o.call('GetSceneItemList',**self.ref(name,bool(vertical)))['sceneItems']
                    if not items:failures.append(name+' is empty')
                    if any(x['sourceName']==self.config['camera'] and x['sceneItemEnabled'] for x in items):failures.append(name+' has visible webcam')
                    enabled={x['sourceName'] for x in items if x['sceneItemEnabled']}
                    suffix='Portrait' if vertical else 'Landscape'
                    if action=='gameplay':
                        capture=self.manifest.get('pc_capture','GTA V Game Capture') if self.manifest.get('mode')=='pc' else (PS5_INPUT if PS5_INPUT in self.inputs else 'ROW - Capture Pending')
                        expected={capture}
                    else:
                        expected={f'ROW - {action.title()} Art - {suffix}','ROW - Banner Music'}
                        expected.add(f'ROW - Safety Card - {suffix}' if action=='safe' else f'ROW - Countdown - {suffix}')
                    if expected-enabled:failures.append(name+' missing/enabled sources: '+', '.join(sorted(expected-enabled)))
                    count+=1
                except ObsError:failures.append(name+' missing')
        if failures:raise ObsError('Setup incomplete: '+'; '.join(failures))
        pending=self.manifest.get('mode')=='ps5' and PS5_INPUT not in self.inputs
        return f'{count} managed scenes verified. Webcam not added to managed scenes. '+('PS5 capture PENDING; no device selected.' if pending else 'Scene structure ready; verify live video/audio in OBS preview.')

    def activate(self):
        self.inspect();self.offline_only();self.check()
        if not self.manifest.get('mode'):raise ObsError('Run setup pc or setup ps5 first.')
        new=copy.deepcopy(self.config);new['scenes']=copy.deepcopy(SCENES);new['safe_scenes']=SAFE
        if self.manifest['mode']=='ps5' and PS5_INPUT in self.inputs:
            if PS5_INPUT not in new['mute_on_safe']:new['mute_on_safe'].append(PS5_INPUT)
        if not (self.root/'config-before-setup.json').exists():
            (self.root/'config-before-setup.json').write_text(json.dumps(self.config,indent=2))
        # Persist the routing BEFORE switching so a retry uses a coherent mapping.
        tmp=self.root/'config.tmp';tmp.write_text(json.dumps(new,indent=2));tmp.replace(self.root/'config.json')
        self.config.clear();self.config.update(new)
        self.o.call('SetCurrentProgramScene',sceneName=SCENES['prepare'][0])
        self.o.vendor('switch_scene',canvas=self.config['canvas'],scene=SCENES['prepare'][1])
        return 'Managed setup selected; Starting Soon on both layouts. Bot commands now target ROW scenes. No stream was started.'

    def devices(self):
        self.inspect()
        probe=next((n for n,x in self.inputs.items() if x['inputKind']=='dshow_input'),None)
        if not probe:
            self.offline_only()
            ref=self.scene(SCENES['gameplay'][0],False)
            probe='ROW - Device Probe'
            item=self.input(ref,probe,'dshow_input',{'active':False,'video_device_id':''})
            self.o.call('SetSceneItemEnabled',**ref,sceneItemId=item,sceneItemEnabled=False)
        result=self.o.call('GetInputPropertiesListPropertyItems',inputName=probe,propertyName='video_device_id')['propertyItems']
        devices=[x for x in result if x.get('itemEnabled',True) and x.get('itemValue')]
        (self.root/'capture-devices.json').write_text(json.dumps(devices,indent=2))
        return '\n'.join(['VIDEO DEVICES — select only your capture card, not the laptop webcam:']+[f"{i+1}. {x['itemName']}" for i,x in enumerate(devices)]+['Run capture ps5 <number> after checking the exact device name.'])

    def capture(self,number):
        self.inspect();self.offline_only()
        if self.manifest.get('mode')!='ps5':raise ObsError('Run setup ps5 before selecting a PS5 capture card.')
        snapshot=self.root/'capture-devices.json'
        if not snapshot.exists():raise ObsError('Run devices first, then capture ps5 <number>.')
        old=json.loads(snapshot.read_text())
        try:selected=old[int(number)-1]
        except (ValueError,IndexError):raise ObsError('Invalid device number. Run devices.')
        if int(number)<1:raise ObsError('Device numbers start at 1.')
        self.devices()
        current=json.loads(snapshot.read_text())
        if not any(x['itemName']==selected['itemName'] and x['itemValue']==selected['itemValue'] for x in current):
            raise ObsError('Device list changed. Run devices and select again; nothing configured.')
        return self.capture_named(selected['itemName'])

    def capture_named(self,name):
        self.inspect();self.offline_only()
        if self.manifest.get('mode')!='ps5':raise ObsError('Run setup ps5 first.')
        self.devices()
        devices=json.loads((self.root/'capture-devices.json').read_text())
        matched=[x for x in devices if x['itemName'].casefold()==name.casefold()]
        if len(matched)!=1:raise ObsError('Use the exact, unique device name shown by devices. No source changed.')
        d=matched[0]
        if any(x in d['itemName'].lower() for x in ('webcam','wide vision','integrated camera','facetime','virtual camera')):raise ObsError('That looks like a webcam or virtual camera. Select the HDMI capture card.')
        ref=self.ref(SCENES['gameplay'][0])
        self.input(ref,PS5_INPUT,'dshow_input',{'video_device_id':d['itemValue'],'active':True,'audio_output_mode':0,'res_type':0,'use_custom_audio_device':False})
        for vertical in (False,True):
            ref=self.ref(SCENES['gameplay'][int(vertical)],vertical)
            item=self.item(ref,PS5_INPUT)
            w,h=(self.canvas['width'],self.canvas['height']) if vertical else (self.video['baseWidth'],self.video['baseHeight'])
            self.fit(ref,item,w,h,crop=vertical)
            for x in self.o.call('GetSceneItemList',**ref)['sceneItems']:
                if x['sourceName']=='ROW - Capture Pending':self.o.call('SetSceneItemEnabled',**ref,sceneItemId=x['sceneItemId'],sceneItemEnabled=False)
        self.manifest['capture_name']=d['itemName'];self.persist()
        if PS5_INPUT not in self.config['mute_on_safe']:
            self.config['mute_on_safe'].append(PS5_INPUT)
            (self.root/'config.json').write_text(json.dumps(self.config,indent=2))
        return 'Capture card selected: '+d['itemName']+'. HDMI audio capture requested. Preview video and audio meters before going live; signal quality is not yet verified.'

    def rollback(self):
        self.offline_only()
        backup=self.root/'config-before-setup.json'
        if not backup.exists():raise ObsError('No pre-setup command mapping saved.')
        original=json.loads(backup.read_text());(self.root/'config.json').write_text(json.dumps(original,indent=2))
        self.config.clear();self.config.update(original)
        return 'Original bot scene routing restored. ROW scenes/assets remain available; nothing deleted. Run prepare to select original banners.'
