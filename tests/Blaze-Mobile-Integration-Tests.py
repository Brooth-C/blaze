"""Real HTTPS fixture downloads, audio conversion and two-stream merging."""
import datetime
import functools
import importlib.util
import ipaddress
import json
from pathlib import Path
import ssl
import subprocess
import tempfile
import threading
import unittest
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

import imageio_ffmpeg
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from yt_dlp.extractor.common import InfoExtractor
from yt_dlp.networking import _helper

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('mobile_integration',ROOT/'android/app/src/main/python/blaze_mobile.py')
b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)


class Callback:
    def isCancelled(self):return False
    def onProgress(self,percent,message):pass


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self,*args):pass


class MobileIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        scratch=ROOT/'build';scratch.mkdir(exist_ok=True)
        cls.temp=tempfile.TemporaryDirectory(dir=scratch);cls.folder=Path(cls.temp.name).resolve()
        assert cls.folder.is_relative_to(scratch.resolve())
        assets=ROOT/'android/app/src/androidTest/assets'
        for name in ('fixture-video.mp4','fixture-audio.wav'):(cls.folder/name).write_bytes((assets/name).read_bytes())
        cls.ffmpeg=imageio_ffmpeg.get_ffmpeg_exe()
        subprocess.run([cls.ffmpeg,'-y','-i',str(cls.folder/'fixture-audio.wav'),'-c:a','aac',str(cls.folder/'fixture-audio.m4a')],check=True,capture_output=True)
        key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'Blaze isolated test server')])
        now=datetime.datetime.now(datetime.timezone.utc)
        certificate=(x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now-datetime.timedelta(hours=1)).not_valid_after(now+datetime.timedelta(days=1)).add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address('127.0.0.1'))]),critical=False).add_extension(x509.BasicConstraints(ca=True,path_length=None),critical=True).sign(key,hashes.SHA256()))
        (cls.folder/'certificate.pem').write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
        (cls.folder/'key.pem').write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),functools.partial(QuietHandler,directory=str(cls.folder)))
        tls=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);tls.load_cert_chain(str(cls.folder/'certificate.pem'),str(cls.folder/'key.pem'));cls.server.socket=tls.wrap_socket(cls.server.socket,server_side=True)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.base=f'https://127.0.0.1:{cls.server.server_port}'
        original_load=_helper.ssl_load_certs
        def load_test_ca(context,*args,**kwargs):
            original_load(context,*args,**kwargs);context.load_verify_locations(cafile=str(cls.folder/'certificate.pem'))
            assert context.verify_mode==ssl.CERT_REQUIRED and context.check_hostname
        cls.cert_patch=patch.object(_helper,'ssl_load_certs',side_effect=load_test_ca);cls.cert_patch.start()

    @classmethod
    def tearDownClass(cls):
        cls.cert_patch.stop();cls.server.shutdown();cls.server.server_close();cls.thread.join(timeout=2)
        assert cls.folder.is_relative_to((ROOT/'build').resolve());cls.temp.cleanup()

    def test_real_https_audio_to_mp3(self):
        output=self.folder/'mp3'
        result=json.loads(b.download(self.base+'/fixture-audio.wav','audio',str(output),Callback(),'{"audio":"mp3"}',self.ffmpeg,token='convert'))
        self.assertTrue(result['path'].endswith('.mp3'));self.assertGreater(Path(result['path']).stat().st_size,100)
        verify=subprocess.run([self.ffmpeg,'-v','error','-i',result['path'],'-f','null','-'],capture_output=True)
        self.assertEqual(verify.returncode,0,verify.stderr.decode())

    def test_real_two_stream_https_merge(self):
        base=self.base
        class FixtureIE(InfoExtractor):
            _VALID_URL=r'https://127\.0\.0\.1:\d+/entry/(?P<id>\d+)'
            def _real_extract(self,url):
                return {'id':self._match_id(url),'title':'Synthetic video','formats':[{'format_id':'v','url':base+'/fixture-video.mp4','ext':'mp4','vcodec':'h264','acodec':'none','height':64,'width':64},{'format_id':'a','url':base+'/fixture-audio.m4a','ext':'m4a','vcodec':'none','acodec':'aac'}]}
        original=b.MobileYDL
        class FixtureYDL(original):
            def __init__(self,params):
                super().__init__(params,auto_init=False);self.add_info_extractor(FixtureIE());self.add_default_info_extractors()
        with patch.object(b,'MobileYDL',FixtureYDL):
            result=json.loads(b.download(base+'/entry/1','video',str(self.folder/'merge'),Callback(),'{"quality":"720"}',self.ffmpeg,token='merge'))
        self.assertTrue(result['path'].endswith('.mkv'))
        decoded=subprocess.run([self.ffmpeg,'-v','error','-i',result['path'],'-map','0:v:0','-map','0:a:0','-f','null','-'],capture_output=True)
        self.assertEqual(decoded.returncode,0,decoded.stderr.decode())
        self.assertEqual(list((self.folder/'merge').glob('*.part')),[])

    def test_stopped_conversion_can_retry_existing_source(self):
        class StopProcessing(Callback):
            stopped=False
            def isCancelled(self):return self.stopped
            def onProgress(self,percent,message):
                if 'Converting' in message:self.stopped=True
        output=self.folder/'retry'
        with self.assertRaises(b.DownloadCancelled):b.download(self.base+'/fixture-audio.wav','audio',str(output),StopProcessing(),'{"audio":"mp3"}',self.ffmpeg,token='stop-processing')
        self.assertTrue((output/'source.wav').is_file())
        result=json.loads(b.download(self.base+'/fixture-audio.wav','audio',str(output),Callback(),'{"audio":"mp3"}',self.ffmpeg,token='retry-processing'))
        self.assertTrue(result['path'].endswith('.mp3'));self.assertGreater(Path(result['path']).stat().st_size,100)


if __name__=='__main__':unittest.main()
