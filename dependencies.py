"""Download official Windows prerequisites without silently running installers."""
import hashlib
import json
import os
from pathlib import Path
import re
import urllib.parse
import urllib.request

from runtime_paths import ROOT
PACKAGES={
    'aitum':('Aitum/obs-aitum-stream-suite',lambda n:n=='aitum-stream-suite-windows-installer.exe'),
    'obs':('obsproject/obs-studio',lambda n:bool(re.fullmatch(r'OBS-Studio-.*-Windows-x64-Installer\.exe',n,re.I))),
}

def fetch(url):
    request=urllib.request.Request(url,headers={'User-Agent':'RevOnWheels-OBS-Bot','Accept':'application/vnd.github+json'})
    return urllib.request.urlopen(request,timeout=45)

def select_asset(release,package):
    repo,predicate=PACKAGES[package]
    assets=[a for a in release['assets'] if predicate(a['name'])]
    if len(assets)!=1:raise RuntimeError('No unique official Windows installer found for '+package)
    asset=assets[0]
    url=urllib.parse.urlparse(asset['browser_download_url'])
    if url.scheme!='https' or url.netloc!='github.com' or not url.path.startswith('/'+repo+'/releases/download/'):
        raise RuntimeError('Installer URL is outside the official release repository.')
    if Path(asset['name']).name!=asset['name'] or '/' in asset['name'] or '\\' in asset['name']:
        raise RuntimeError('Unsafe release filename.')
    digest=asset.get('digest') or ''
    if not re.fullmatch(r'sha256:[0-9a-fA-F]{64}',digest):
        raise RuntimeError('Official release has no SHA-256 digest; refusing an unverified download.')
    return asset,digest.split(':',1)[1].lower()

def download(package='aitum'):
    if package not in PACKAGES:raise RuntimeError('Choose aitum or obs.')
    repo=PACKAGES[package][0]
    with fetch('https://api.github.com/repos/'+repo+'/releases/latest') as response:release=json.load(response)
    asset,expected=select_asset(release,package)
    folder=ROOT/'downloads';folder.mkdir(exist_ok=True)
    target=folder/asset['name'];partial=target.with_suffix('.partial')
    digest=hashlib.sha256()
    try:
        with fetch(asset['browser_download_url']) as source,partial.open('wb') as dest:
            while True:
                block=source.read(1024*1024)
                if not block:break
                digest.update(block);dest.write(block)
        if digest.hexdigest()!=expected:raise RuntimeError('SHA-256 mismatch. Installer was not accepted.')
        partial.replace(target)
    finally:
        if partial.exists():partial.unlink()
    (folder/(package+'-verified.json')).write_text(json.dumps({'version':release['tag_name'],'file':target.name,'sha256':expected,'url':asset['browser_download_url']},indent=2))
    return f'Downloaded {package} {release["tag_name"]}; SHA-256 verified.\n{target}\nClose OBS, then run dependencies install {package} to open the installer.'

def install(package):
    if package not in PACKAGES:raise RuntimeError('Choose aitum or obs.')
    if os.name!='nt':raise RuntimeError('Windows installers require Windows.')
    folder=ROOT/'downloads';record=folder/(package+'-verified.json')
    if not record.exists():raise RuntimeError('Run dependencies download '+package+' first.')
    meta=json.loads(record.read_text());name=meta['file']
    if Path(name).name!=name or '/' in name or '\\' in name:raise RuntimeError('Invalid installer record.')
    target=folder/name
    if hashlib.sha256(target.read_bytes()).hexdigest()!=meta['sha256']:raise RuntimeError('Installer changed; download it again.')
    # Native installer provides elevation, licence, compatibility and destination UI.
    os.startfile(str(target))
    return 'Installer opened. Complete its prompts, then reopen OBS and run doctor. Installation is not yet verified.'

def run(command):
    args=command.split()
    if args==['dependencies','check']:
        return 'Requirements: OBS Studio (built-in WebSocket), Aitum Stream Suite, Python 3.10+.\nDownload: dependencies download aitum | dependencies download obs\nInstallers run only with an explicit dependencies install <package> command.\nClose OBS before installation. Reopen OBS and run doctor to verify the plugin.'
    if len(args)==3 and args[1] in ('download','install'):
        return download(args[2]) if args[1]=='download' else install(args[2])
    raise RuntimeError('Use dependencies check, dependencies download aitum/obs, or dependencies install aitum/obs.')

if __name__=='__main__':
    import sys
    try:print(run('dependencies '+' '.join(sys.argv[1:] or ['check'])))
    except Exception as exc:print('ERROR:',exc);sys.exit(1)
