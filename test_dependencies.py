import unittest
from unittest.mock import patch
from dependencies import select_asset
from bot import execute

class DependencyTests(unittest.TestCase):
    def release(self,**changes):
        asset={'name':'aitum-stream-suite-windows-installer.exe','digest':'sha256:'+'a'*64,'browser_download_url':'https://github.com/Aitum/obs-aitum-stream-suite/releases/download/1.2.6/aitum-stream-suite-windows-installer.exe'}
        asset.update(changes)
        return {'assets':[asset]}
    def test_official_asset_selected(self):
        self.assertEqual(select_asset(self.release(),'aitum')[1],'a'*64)
    def test_untrusted_url_rejected(self):
        with self.assertRaises(RuntimeError):select_asset(self.release(browser_download_url='https://example.com/plugin.exe'),'aitum')
    def test_missing_digest_rejected(self):
        with self.assertRaises(RuntimeError):select_asset(self.release(digest=None),'aitum')
    def test_dependencies_does_not_require_obs(self):
        with patch('bot.connection',side_effect=AssertionError('must not connect')):
            self.assertIn('Requirements:',execute('dependencies check'))

if __name__=='__main__':unittest.main()
