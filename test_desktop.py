import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import desktop

class DesktopTests(unittest.TestCase):
    def test_open_obs_does_not_launch_duplicate(self):
        from types import SimpleNamespace
        with patch.object(desktop.Path,'exists',return_value=True), patch.object(desktop.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout='"obs64.exe","123","Console","1","10 K"')), patch.object(desktop.subprocess,'Popen') as launch:
            self.assertIn('already running',desktop.open_obs());launch.assert_not_called()
    def test_open_obs_launches_when_not_running(self):
        from types import SimpleNamespace
        with patch.object(desktop.Path,'exists',return_value=True), patch.object(desktop.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout='INFO: No tasks are running')), patch.object(desktop.subprocess,'Popen') as launch:
            self.assertIn('launch requested',desktop.open_obs());launch.assert_called_once()
    def test_status_uses_all_activity_fields(self):
        raw=json.dumps({'main_stream_active':True,'scene':'Gameplay','vertical_scene':None,'outputs':[{'name':'Kick','streaming':True},{'name':'Twitch','active':False}]})
        status=desktop.status_summary(raw)
        self.assertEqual(status['output'],'Main OBS, Kick')
        self.assertEqual(status['portrait'],'No scene')
        self.assertTrue(status['live'])
    def test_stopped_status(self):
        self.assertFalse(desktop.status_summary('{"outputs": []}')['live'])
    def test_import_keeps_local_backup_and_updates_controller(self):
        original=copy.deepcopy(desktop.CONFIG)
        try:
            with tempfile.TemporaryDirectory() as folder:
                root=Path(folder)/'app';root.mkdir();source=Path(folder)/'old';source.mkdir()
                (root/'config.json').write_text('{"previous": true}')
                config={'canvas':'YouTube Vertical','scenes':{'gameplay':['A','B']}}
                (source/'config.json').write_text(json.dumps(config))
                with patch.object(desktop,'ROOT',root):desktop.import_setup(source)
                self.assertEqual(desktop.CONFIG,config)
                self.assertEqual(json.loads((root/'config.json').read_text()),config)
                self.assertTrue(list((root/'backups').rglob('config.json')))
        finally:desktop.CONFIG.clear();desktop.CONFIG.update(original)
    def test_import_invalid_folder_does_not_replace_config(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'config.json').write_text('{"invalid": true}')
            with self.assertRaises(ValueError):desktop.import_setup(root)
    def test_go_live_requires_user_choice(self):
        from types import SimpleNamespace
        calls=[];app=SimpleNamespace(run=calls.append)
        with patch.object(desktop.messagebox,'askyesno',return_value=False):
            desktop.App.go_live(app,'live all')
        self.assertEqual(calls,[])
        with patch.object(desktop.messagebox,'askyesno',return_value=True):
            desktop.App.go_live(app,'live youtube')
        self.assertEqual(calls,['live youtube'])

if __name__=='__main__':unittest.main()
