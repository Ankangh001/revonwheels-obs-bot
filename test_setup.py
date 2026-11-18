import copy
import json
from pathlib import Path
import tempfile
import unittest
from bot import CONFIG
from obs_client import ObsError
from setup_obs import Setup, SCENES, PS5_INPUT, PC_INPUT


class SetupOBS:
    def __init__(self):
        self.calls=[];self.scenes={};self.inputs={'GTA V Game Capture':{'inputName':'GTA V Game Capture','inputKind':'game_capture'},'Video Capture Device':{'inputName':'Video Capture Device','inputKind':'dshow_input'}}
        self.settings={};self.active=False;self.plugin_active=False;self.next_id=1
        self.device_list=[{'itemName':'HP Wide Vision HD Camera','itemValue':'webcam','itemEnabled':True},{'itemName':'UGREEN Capture','itemValue':'capture','itemEnabled':True}]
        self.owned_active=False
    def key(self,d):return (d.get('canvasUuid','main'),d.get('sceneName'))
    def call(self,k,**d):
        self.calls.append((k,copy.deepcopy(d)))
        if k=='GetVideoSettings':return {'baseWidth':1920,'baseHeight':1080,'outputWidth':1280,'outputHeight':720}
        if k=='GetInputList':return {'inputs':list(self.inputs.values())}
        if k=='GetSpecialInputs':return {}
        if k=='GetStreamStatus':return {'outputActive':self.active}
        if k=='GetOutputList':return {'outputs':[]}
        if k=='GetSceneList':return {'scenes':[{'sceneName':name} for canvas,name in self.scenes if canvas==d.get('canvasUuid','main')]}
        if k=='CreateScene':self.scenes[self.key(d)]=[];return {}
        if k=='GetSceneItemList':
            if self.key(d) not in self.scenes:raise ObsError('Scene missing')
            return {'sceneItems':copy.deepcopy(self.scenes[self.key(d)])}
        if k in ('CreateInput','CreateSceneItem'):
            if k=='CreateInput':
                n=d['inputName'];self.inputs[n]={'inputName':n,'inputKind':d['inputKind'],'inputUuid':'uuid-'+n};self.settings[n]=copy.deepcopy(d['inputSettings'])
            else:
                n=d.get('sourceName') or next(x for x,v in self.inputs.items() if v.get('inputUuid')==d['sourceUuid'])
                if d.get('canvasUuid') and n.startswith('ROW - '):self.assert_uuid=d['sourceUuid']
            item={'sourceName':n,'sceneItemId':self.next_id,'sceneItemEnabled':d.get('sceneItemEnabled',True)};self.next_id+=1
            self.scenes[self.key(d)].append(item);return {'sceneItemId':item['sceneItemId'],'inputUuid':self.inputs[n].get('inputUuid')}
        if k=='SetInputSettings':
            n=d.get('inputName') or next(x for x,v in self.inputs.items() if v.get('inputUuid')==d['inputUuid'])
            self.settings[n].update(d['inputSettings']);return {}
        if k=='GetSourceActive':return {'videoActive':self.owned_active,'audioActive':False}
        if k=='SetSceneItemEnabled':
            for x in self.scenes[self.key(d)]:
                if x['sceneItemId']==d['sceneItemId']:x['sceneItemEnabled']=d['sceneItemEnabled']
        if k=='GetInputPropertiesListPropertyItems':return {'propertyItems':copy.deepcopy(self.device_list)}
        return {}
    def vendor(self,k,**d):
        self.calls.append((k,copy.deepcopy(d)))
        if k=='get_canvas':return {'canvas':[{'name':'YouTube Vertical','uuid':'vertical','width':720,'height':1280}]}
        if k=='get_outputs':return {'outputs':[{'name':'Twitch','active':self.plugin_active}]}
        return {'success':True}


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.o=SetupOBS();self.config=copy.deepcopy(CONFIG)
        self.files={k:self.root/(k+'.asset') for k in ('landscape','portrait','brb','music','countdown')}
        for p in self.files.values():p.write_text('asset')
        (self.root/'config.json').write_text(json.dumps(self.config))
        self.s=Setup(self.o,self.config,self.root,self.files)
    def tearDown(self):self.tmp.cleanup()
    def test_plan_is_read_only(self):
        self.s.plan()
        self.assertFalse(any(k.startswith(('Create','Set','Start','Stop')) for k,d in self.o.calls))
    def test_build_is_idempotent_and_never_broadcasts(self):
        self.s.build('ps5');counts=(len(self.o.scenes),len(self.o.inputs),self.o.next_id)
        self.s.build('ps5')
        self.assertEqual(counts,(len(self.o.scenes),len(self.o.inputs),self.o.next_id))
        self.assertEqual(len(self.o.scenes),8)
        self.assertFalse(any(k.startswith(('Start','Stop')) or k=='SetCurrentProgramScene' for k,d in self.o.calls))
        self.assertNotIn(PS5_INPUT,self.o.inputs)
    def test_main_and_extra_outputs_block_setup(self):
        for target in ('active','plugin_active'):
            setattr(self.o,target,True)
            with self.assertRaises(ObsError):self.s.build('pc')
            self.assertEqual(len(self.o.scenes),0)
            setattr(self.o,target,False)
    def test_live_staging_only_adds_unused_scenes_and_sources(self):
        self.o.active=True;self.o.plugin_active=True
        self.s.build('ps5',stage=True)
        self.assertEqual(len(self.o.scenes),8)
        self.assertFalse(any(k in ('SetCurrentProgramScene','StartStream','StopStream') for k,d in self.o.calls))
        self.o.owned_active=True;before=len(self.o.calls)
        with self.assertRaises(ObsError):self.s.build('ps5',stage=True)
        self.assertFalse(any(k.startswith(('Create','Set')) for k,d in self.o.calls[before:]))
    def test_cross_canvas_music_reference_uses_source_uuid(self):
        self.s.build('ps5')
        shares=[d for k,d in self.o.calls if k=='CreateSceneItem' and d.get('canvasUuid') and d.get('sourceUuid')=='uuid-ROW - Banner Music']
        self.assertTrue(shares)
    def test_collision_is_not_overwritten(self):
        self.o.scenes[('main',SCENES['prepare'][0])]=[]
        with self.assertRaises(ObsError):self.s.build('pc')
        self.assertEqual(self.o.scenes[('main',SCENES['prepare'][0])],[])
    def test_capture_number_preserves_selected_identity(self):
        self.s.build('ps5');self.s.devices()
        self.o.device_list.reverse()
        self.s.capture('2')
        self.assertEqual(self.o.settings[PS5_INPUT]['video_device_id'],'capture')
    def test_stale_device_selection_is_rejected(self):
        self.s.build('ps5');self.s.devices();self.o.device_list=self.o.device_list[:1]
        with self.assertRaises(ObsError):self.s.capture('2')
        self.assertNotIn(PS5_INPUT,self.o.inputs)
    def test_webcam_cannot_be_selected_as_capture(self):
        self.s.build('ps5');self.s.devices()
        with self.assertRaises(ObsError):self.s.capture('1')
        self.assertNotIn(PS5_INPUT,self.o.inputs)
    def test_activate_routes_commands_but_never_streams(self):
        self.s.build('pc');self.s.activate()
        self.assertEqual(self.config['scenes'],SCENES)
        self.assertEqual(len([1 for k,d in self.o.calls if k=='SetCurrentProgramScene']),1)
        self.assertFalse(any(k.startswith('Start') for k,d in self.o.calls))
        self.s.rollback();self.assertEqual(self.config['scenes'],CONFIG['scenes'])

    def test_auto_ps5_from_zero_sources(self):
        self.o.inputs={}
        self.s.automatic('ps5')
        self.assertEqual(len(self.o.scenes),8)
        self.assertEqual(self.o.settings[PS5_INPUT]['video_device_id'],'capture')
        probe=[x for x in self.o.scenes[('main',SCENES['gameplay'][0])] if x['sourceName']=='ROW - Device Probe']
        self.assertFalse(probe[0]['sceneItemEnabled'])
        self.assertEqual(self.config['microphone'],'ROW - Microphone')
        self.assertTrue(any(k=='SetInputMute' and d.get('inputMuted') for k,d in self.o.calls))
        self.assertFalse(any(k.startswith('Start') for k,d in self.o.calls))

    def test_auto_pc_from_zero_sources_is_repeatable(self):
        self.o.inputs={}
        self.o.device_list=[{'itemName':'Grand Theft Auto V','itemValue':'GTA V:grcWindow:GTA5.exe'}]
        self.s.automatic('pc')
        self.assertEqual(self.o.settings[PC_INPUT]['window'],'GTA V:grcWindow:GTA5.exe')
        count=(len(self.o.scenes),len(self.o.inputs),self.o.next_id)
        self.s.automatic('pc')
        self.assertEqual(count,(len(self.o.scenes),len(self.o.inputs),self.o.next_id))
        self.assertIn('ROW - Game Audio',self.config['mute_on_safe'])

    def test_auto_ambiguous_cards_does_not_pick_one(self):
        self.o.inputs={}
        self.o.device_list.append({'itemName':'Elgato HD60','itemValue':'second'})
        result=self.s.automatic('ps5')
        self.assertIn('Multiple capture cards',result)
        self.assertNotIn(PS5_INPUT,self.o.inputs)

    def test_auto_missing_game_does_not_capture_desktop(self):
        self.o.inputs={}
        result=self.s.automatic('pc')
        self.assertIn('Game capture pending',result)
        self.assertEqual(self.o.settings[PC_INPUT]['window'],'')
        self.assertEqual(self.o.settings[PC_INPUT]['capture_mode'],'window')

    def test_auto_reuses_global_audio(self):
        original=self.o.call
        self.o.call=lambda k,**d: {'mic1':'Mic/Aux','desktop1':'Desktop Audio'} if k=='GetSpecialInputs' else original(k,**d)
        self.s.automatic('pc')
        self.assertNotIn('ROW - Game Audio',self.o.inputs)
        self.assertNotIn('ROW - Microphone',self.o.inputs)
        self.assertEqual(self.config['microphone'],'Mic/Aux')

    def test_auto_live_does_not_mutate(self):
        self.o.plugin_active=True
        with self.assertRaises(ObsError):self.s.automatic('ps5')
        self.assertFalse(any(k.startswith(('Create','Set')) for k,d in self.o.calls))

if __name__=='__main__':unittest.main()
