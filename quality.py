"""Choose advertised capture modes; never infer capability from a 4K label."""
import json
import time
from obs_client import ObsError

def enabled(items):
    return [x for x in items if x.get('itemEnabled',True)]

def choose_interval(items):
    # DirectShow intervals are in 100 ns units; 0/-1 are automatic sentinels.
    values=[int(x['itemValue']) for x in enabled(items) if isinstance(x.get('itemValue'),(int,float)) and x['itemValue']>0]
    values=[v for v in values if 29.9<=10000000/v<=60.1]
    return min(values) if values else None

def automatic(setup):
    from setup_obs import PS5_INPUT, SCENES
    s=setup.inspect();s.offline_only()
    if PS5_INPUT not in s.inputs:raise ObsError('Select the PS5 capture card first: setup auto ps5 or devices / capture ps5 N.')
    if PS5_INPUT not in s.manifest['inputs']:raise ObsError('Capture source is not owned by this bot; nothing changed.')
    ref=s.input_ref(PS5_INPUT)
    previous=s.o.call('GetInputSettings',**ref)['inputSettings']
    video=s.o.call('GetVideoSettings')
    folder=s.root/'backups';folder.mkdir(exist_ok=True)
    backup=folder/('quality-'+time.strftime('%Y%m%d-%H%M%S')+'.json')
    backup.write_text(json.dumps({'input':previous,'video':video},indent=2))
    def properties(name):return s.o.call('GetInputPropertiesListPropertyItems',**ref,propertyName=name)['propertyItems']
    try:
        formats=enabled(properties('video_format'))
        selected_format=next((x['itemValue'] for x in formats if str(x.get('itemName','')).upper()=='MJPEG'),0)
        format_name='MJPEG' if selected_format else 'Auto'
        resolutions={x['itemValue'] for x in enabled(properties('resolution'))}
        chosen=None
        for resolution in ('1920x1080','1280x720'):
            if resolution not in resolutions:continue
            s.o.call('SetInputSettings',**ref,inputSettings={'res_type':1,'resolution':resolution,'video_format':selected_format,'frame_interval':0},overlay=True)
            interval=choose_interval(properties('frame_interval'))
            if interval is not None:
                chosen=(resolution,interval);break
        if not chosen:raise ObsError('No advertised 1080p/720p capture mode at 30–60 fps. Original settings restored.')
        resolution,interval=chosen
        # Leave colour interpretation and HDMI audio settings unchanged.
        s.o.call('SetInputSettings',**ref,inputSettings={'res_type':1,'resolution':resolution,'frame_interval':interval,'video_format':selected_format},overlay=True)
        width,height=map(int,resolution.split('x'))
        fps=10000000/interval
        numerator,denominator=(60000,1001) if abs(fps-59.94)<.02 else ((30000,1001) if abs(fps-29.97)<.02 else (round(fps),1))
        # Raising a small base canvas would move existing artwork; refuse that case.
        if video['baseWidth']<width or video['baseHeight']<height:
            raise ObsError('Base canvas is smaller than the chosen capture mode. Resize/rebuild layouts first; original settings restored.')
        s.o.call('SetVideoSettings',outputWidth=width,outputHeight=height,fpsNumerator=numerator,fpsDenominator=denominator)
        actual=s.o.call('GetInputSettings',**ref)['inputSettings']
        output=s.o.call('GetVideoSettings')
        if actual.get('resolution')!=resolution or actual.get('frame_interval')!=interval or actual.get('video_format')!=selected_format or (output['outputWidth'],output['outputHeight'])!=(width,height):
            raise ObsError('OBS did not retain the requested quality settings.')
        if (output['fpsNumerator'],output['fpsDenominator'])!=(numerator,denominator):raise ObsError('OBS did not retain the requested output frame rate.')
        for vertical in (False,True):
            scene=s.ref(SCENES['gameplay'][int(vertical)],vertical)
            for item in s.o.call('GetSceneItemList',**scene)['sceneItems']:
                if item['sourceName']==PS5_INPUT:
                    w,h=(s.canvas['width'],s.canvas['height']) if vertical else (video['baseWidth'],video['baseHeight'])
                    s.fit(scene,item['sceneItemId'],w,h,crop=vertical)
        s.manifest['quality']={'resolution':resolution,'frame_interval':interval,'fps':round(fps,3),'verified_settings':True,'video_format':format_name}
        s.persist()
    except Exception:
        s.o.call('SetInputSettings',**ref,inputSettings=previous,overlay=False)
        s.o.call('SetVideoSettings',**video)
        raise
    return (f'Capture requested: {resolution} at {fps:.2f} fps; format {format_name}. OBS output: {width}x{height} at {numerator/denominator:.2f} fps. Settings read back successfully.\n'
            'Portrait canvas retained. Encoder bitrate unchanged. Confirm moving video/audio before streaming.\n'
            'PS5 resolution/HDCP cannot be changed from this laptop: set PS5 output to 1080p manually if needed.\nBackup: '+str(backup))
