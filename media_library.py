"""Local media choices; originals are copied, never uploaded or overwritten."""
import json
from pathlib import Path
import shutil
import uuid
from runtime_paths import ROOT

IMAGE_KEYS={'landscape','portrait','brb'}
LABELS={'landscape':'Starting Soon · landscape','portrait':'Starting Soon · portrait','brb':'Break / Safe Screen artwork','music':'Banner music'}

def preferences(config):
    media=config.get('media',{})
    return {'mode':media.get('mode','included'),'files':dict(media.get('files',{})),
            'music_enabled':media.get('music_enabled',True),'countdown_enabled':media.get('countdown_enabled',True)}

def resolve(config,defaults):
    media=preferences(config)
    result=dict(defaults)
    if media['mode']=='custom':
        for key in LABELS:
            if media['files'].get(key):result[key]=Path(media['files'][key])
    return result

def import_file(key,source,root=ROOT):
    if key not in LABELS:raise ValueError('Unknown media slot.')
    source=Path(source)
    if not source.is_file():raise ValueError('Choose an existing media file.')
    extension=source.suffix.lower()
    allowed={'.png','.jpg','.jpeg','.webp'} if key in IMAGE_KEYS else {'.wav','.mp3','.ogg','.flac','.m4a'}
    if extension not in allowed:raise ValueError('Choose a supported '+('image' if key in IMAGE_KEYS else 'audio')+' file.')
    if key in IMAGE_KEYS:
        from PIL import Image
        with Image.open(source) as image:image.verify()
    folder=Path(root)/'custom-media';folder.mkdir(parents=True,exist_ok=True)
    destination=folder/(key+'-'+uuid.uuid4().hex+extension)
    shutil.copy2(source,destination)
    return str(destination)

def save(config,media,root=ROOT):
    if media.get('mode') not in ('included','custom'):raise ValueError('Choose included or custom media.')
    new=dict(config);new['media']=media
    target=Path(root)/'config.json';temporary=target.with_suffix('.tmp')
    temporary.write_text(json.dumps(new,indent=2));temporary.replace(target)
    config.clear();config.update(new)

def apply(config):
    from bot import connection
    from setup_obs import Setup
    obs=connection()
    try:
        setup=Setup(obs,config)
        mode=setup.manifest.get('mode')
        if mode not in ('pc','ps5'):raise ValueError('Prepare your PS5 or PC setup first, then apply media.')
        return setup.build(mode)
    finally:obs.close()
