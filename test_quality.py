import copy
from quality import automatic, choose_interval
from setup_obs import PS5_INPUT
import test_setup
from obs_client import ObsError
import unittest

class QualityTests(unittest.TestCase):
    setUp=test_setup.SetupTests.setUp
    tearDown=test_setup.SetupTests.tearDown
    def ready(self):
        self.s.build('ps5');self.s.devices();self.s.capture('2')
    def test_selects_supported_1080p60_and_preserves_audio(self):
        self.ready()
        self.assertEqual(self.o.video['outputWidth'],1920)
        self.assertEqual(self.o.settings[PS5_INPUT]['frame_interval'],166666)
        self.assertEqual(self.o.settings[PS5_INPUT]['audio_output_mode'],0)
        self.assertFalse(any(k.startswith('Start') for k,d in self.o.calls))
    def test_1080p30_fallback(self):
        self.o.intervals=[333333]
        self.ready()
        self.assertEqual(self.o.video['fpsNumerator'],30)
    def test_720p_fallback(self):
        self.o.resolutions=['1280x720'];self.ready()
        self.assertEqual(self.o.video['outputHeight'],720)
    def test_unsupported_modes_restore_settings(self):
        self.ready();before=copy.deepcopy(self.o.settings[PS5_INPUT]);video=copy.deepcopy(self.o.video)
        self.o.resolutions=['640x480']
        with self.assertRaises(ObsError):automatic(self.s)
        self.assertEqual(self.o.settings[PS5_INPUT],before);self.assertEqual(self.o.video,video)
    def test_live_quality_does_not_mutate(self):
        self.ready();self.o.plugin_active=True;start=len(self.o.calls)
        with self.assertRaises(ObsError):automatic(self.s)
        self.assertFalse(any(k.startswith('Set') for k,d in self.o.calls[start:]))
    def test_disabled_and_auto_fps_are_not_capabilities(self):
        items=[{'itemValue':0},{'itemValue':-1},{'itemValue':166666,'itemEnabled':False},{'itemValue':333333}]
        self.assertEqual(choose_interval(items),333333)
    def test_rejected_output_rolls_back(self):
        self.ready();before=copy.deepcopy(self.o.settings[PS5_INPUT]);video=copy.deepcopy(self.o.video)
        original=self.o.call;failed=[False]
        def reject(k,**d):
            if k=='SetVideoSettings' and not failed[0]:failed[0]=True;raise ObsError('Video reset failed')
            return original(k,**d)
        self.o.call=reject
        with self.assertRaises(ObsError):automatic(self.s)
        self.assertEqual(self.o.settings[PS5_INPUT],before);self.assertEqual(self.o.video,video)

if __name__=='__main__':unittest.main()
