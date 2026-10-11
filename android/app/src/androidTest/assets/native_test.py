import json
import subprocess
from pathlib import Path
from yt_dlp import YoutubeDL
from yt_dlp.postprocessor.ffmpeg import FFmpegExtractAudioPP, FFmpegMergerPP

folder=Path(fixture_directory)
with YoutubeDL({'ffmpeg_location':ffmpeg_path,'quiet':True,'no_warnings':True}) as downloader:
    audio=folder/'fixture-audio.wav'
    info={'filepath':str(audio),'ext':'wav','vcodec':'none','acodec':'pcm_s16le'}
    _,converted=FFmpegExtractAudioPP(downloader,preferredcodec='mp3',preferredquality='192').run(info)
    result=Path(converted['filepath'])
    assert result.is_file() and result.stat().st_size>100
    probe=subprocess.run([ffprobe_path,'-v','error','-show_entries','stream=codec_name','-of','json',str(result)],check=True,capture_output=True,text=True)
    assert json.loads(probe.stdout)['streams'][0]['codec_name']=='mp3'
    merged=folder/'merged.mkv'
    merge_info={'filepath':str(merged),'ext':'mkv','requested_formats':[{'vcodec':'h264','acodec':'none','protocol':'file'},{'vcodec':'none','acodec':'pcm_s16le','protocol':'file'}],'__files_to_merge':[str(folder/'fixture-video.mp4'),str(audio)]}
    FFmpegMergerPP(downloader).run(merge_info)
    probe=subprocess.run([ffprobe_path,'-v','error','-show_entries','stream=codec_type','-of','json',str(merged)],check=True,capture_output=True,text=True)
    assert {stream['codec_type'] for stream in json.loads(probe.stdout)['streams']}=={'video','audio'}
runtime=subprocess.run([quickjs_path,'-e','print(1 + 2)'],check=True,capture_output=True,text=True)
assert runtime.stdout.strip()=='3'
