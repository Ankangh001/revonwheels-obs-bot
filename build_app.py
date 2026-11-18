"""Build with PyInstaller installed normally or into .build-tools."""
import os
from pathlib import Path
import subprocess
import sys

def main():
    root=Path(__file__).resolve().parent
    env=os.environ.copy()
    local=root/'.build-tools'
    if local.exists():env['PYTHONPATH']=str(local)+os.pathsep+env.get('PYTHONPATH','')
    subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onefile','--windowed',
                    '--name','RevOnWheels','--icon','assets/revonwheels-logo.png','--add-data','config.example.json;.','--add-data','assets;assets',
                    '--hidden-import','setup_obs','--hidden-import','quality','--hidden-import','dependencies',
                    'desktop.py'],cwd=root,env=env,check=True)
    print('Built:',root/'dist/RevOnWheels.exe')

if __name__=='__main__':main()
