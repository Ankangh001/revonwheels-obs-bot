import copy
import tempfile
from pathlib import Path
import unittest
from PIL import Image
import media_library
import test_setup

class MediaTests(unittest.TestCase):
    def test_custom_file_is_copied_without_overwriting_original(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);original=root/'my-art.png';Image.new('RGB',(32,18),'purple').save(original)
            before=original.read_bytes()
            first=Path(media_library.import_file('landscape',original,root));second=Path(media_library.import_file('landscape',original,root))
            self.assertNotEqual(first,second);self.assertEqual(first.read_bytes(),before);self.assertEqual(original.read_bytes(),before)
    def test_invalid_image_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'broken.png';source.write_text('not a picture')
            with self.assertRaises(OSError):media_library.import_file('landscape',source,root)
            self.assertFalse((root/'custom-media').exists())
    def test_included_mode_ignores_custom_paths(self):
        defaults={'landscape':Path('bundled.png')}
        config={'media':{'mode':'included','files':{'landscape':'other.png'}}}
        self.assertEqual(media_library.resolve(config,defaults),defaults)
        config['media']['mode']='custom'
        self.assertEqual(media_library.resolve(config,defaults)['landscape'],Path('other.png'))
    def test_preferences_persist_and_keep_other_configuration(self):
        with tempfile.TemporaryDirectory() as folder:
            config={'canvas':'My canvas'};media={'mode':'custom','files':{},'music_enabled':False}
            media_library.save(config,media,folder)
            self.assertEqual(config['canvas'],'My canvas');self.assertEqual(config['media'],media)
            self.assertTrue((Path(folder)/'config.json').exists())

class MediaSetupTests(unittest.TestCase):
    setUp=test_setup.SetupTests.setUp
    tearDown=test_setup.SetupTests.tearDown
    def test_disable_existing_music_and_countdown_on_both_canvases(self):
        self.s.build('ps5')
        self.s.media.update(music_enabled=False,countdown_enabled=False)
        self.s.build('ps5')
        for (_,name),items in self.o.scenes.items():
            for item in items:
                if item['sourceName']=='ROW - Banner Music' or item['sourceName'].startswith('ROW - Countdown - '):self.assertFalse(item['sceneItemEnabled'],name)
        self.assertIn('8 managed scenes',self.s.check())
    def test_disabled_optional_media_can_be_absent(self):
        self.s.media.update(music_enabled=False,countdown_enabled=False)
        self.s.files['music'].unlink();self.s.files['countdown'].unlink()
        self.s.build('ps5')
        self.assertNotIn('ROW - Banner Music',self.o.inputs)
    def test_missing_required_artwork_stops_before_source_changes(self):
        self.s.files['landscape'].unlink()
        with self.assertRaises(Exception):self.s.build('ps5')
        self.assertFalse(any(k.startswith(('Create','Set')) for k,d in self.o.calls))
    def test_custom_art_is_used_in_source_settings(self):
        self.s.build('ps5')
        custom=self.root/'custom.png';custom.write_bytes(b'checked by file picker')
        self.s.files['landscape']=custom;self.s.build('ps5')
        self.assertEqual(self.o.settings['ROW - Prepare Art - Landscape']['file'],str(custom))
    def test_disabled_music_and_countdown_can_be_reenabled(self):
        self.s.build('ps5');self.s.media.update(music_enabled=False,countdown_enabled=False);self.s.build('ps5')
        self.s.media.update(music_enabled=True,countdown_enabled=True);self.s.build('ps5')
        for items in self.o.scenes.values():
            for item in items:
                if item['sourceName']=='ROW - Banner Music' or item['sourceName'].startswith('ROW - Countdown - '):self.assertTrue(item['sceneItemEnabled'])

if __name__=='__main__':unittest.main()
