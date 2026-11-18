"""Separate bundled read-only resources from a packaged app's local data."""
import os
from pathlib import Path
import shutil
import sys

BUNDLE=Path(__file__).resolve().parent
PACKAGED=bool(getattr(sys,'frozen',False))
ROOT=(Path(os.environ.get('LOCALAPPDATA',str(Path.home()/'AppData/Local')))/'RevOnWheels') if PACKAGED else BUNDLE

def initialise():
    if not PACKAGED:return
    ROOT.mkdir(parents=True,exist_ok=True)
    example=ROOT/'config.example.json'
    if not example.exists():shutil.copy2(BUNDLE/'config.example.json',example)
    assets=ROOT/'assets';assets.mkdir(exist_ok=True)
    for source in (BUNDLE/'assets').iterdir():
        if source.is_file() and not (assets/source.name).exists():shutil.copy2(source,assets/source.name)

initialise()
