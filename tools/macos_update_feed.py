"""Sign the exact tested Mac archive and generate its stable Sparkle appcast.

Private seed comes only from BLAZE_UPDATE_PRIVATE_KEY; never print it or accept
it as a command argument. This is separate from Apple Developer ID signing.
"""
import argparse
import base64
from datetime import datetime, timezone
from email.utils import format_datetime
import json
import os
from pathlib import Path
import re
import xml.etree.ElementTree as ET

NS = 'http://www.andymatuschak.org/xml-namespaces/sparkle'
ET.register_namespace('sparkle', NS)
ROOT = Path(__file__).resolve().parents[1]


def create_feed(archive, version, private_seed, public_key, published=None):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization
    if not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise ValueError('Stable numeric Mac version required.')
    archive = Path(archive)
    if archive.name != 'Blaze-Mac-arm64.zip' or not archive.is_file():
        raise ValueError('Expected the tested Apple Silicon Mac archive.')
    key = Ed25519PrivateKey.from_private_bytes(base64.b64decode(private_seed, validate=True))
    actual = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    if actual != base64.b64decode(public_key, validate=True):
        raise ValueError('Update signing key does not match the key embedded in Blaze.')
    payload = archive.read_bytes()
    signature = base64.b64encode(key.sign(payload)).decode('ascii')
    tag = 'macos-v' + version
    release = 'https://github.com/Brooth-C/blaze/releases/'
    rss = ET.Element('rss', version='2.0')
    channel = ET.SubElement(rss, 'channel')
    ET.SubElement(channel, 'title').text = 'Blaze for Mac'
    item = ET.SubElement(channel, 'item')
    ET.SubElement(item, 'title').text = 'Blaze ' + version
    ET.SubElement(item, 'pubDate').text = format_datetime(published or datetime.now(timezone.utc))
    ET.SubElement(item, f'{{{NS}}}version').text = version
    ET.SubElement(item, f'{{{NS}}}shortVersionString').text = version
    ET.SubElement(item, f'{{{NS}}}minimumSystemVersion').text = '13.0'
    ET.SubElement(item, 'link').text = release + 'tag/' + tag
    ET.SubElement(item, 'enclosure', {
        'url': release + 'download/' + tag + '/' + archive.name,
        'length': str(len(payload)), 'type': 'application/octet-stream',
        f'{{{NS}}}edSignature': signature})
    ET.indent(rss)
    return ET.tostring(rss, encoding='utf-8', xml_declaration=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--version', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    config = json.loads((ROOT / 'music_studio/mac_update_config.json').read_text())
    seed = os.environ.get('BLAZE_UPDATE_PRIVATE_KEY')
    if not seed:
        raise SystemExit('BLAZE_UPDATE_PRIVATE_KEY is required; refusing unsigned publication.')
    published = datetime.fromtimestamp(int(os.environ['SOURCE_DATE_EPOCH']), timezone.utc)
    args.output.write_bytes(create_feed(args.archive, args.version, seed, config['public_key'], published))
    print('Signed Mac update feed created.')
