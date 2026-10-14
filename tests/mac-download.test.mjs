import test from 'node:test';
import assert from 'node:assert/strict';
import { architecture, detectMac, downloads, rendererArchitecture } from '../download-site/mac/detect.mjs';
const mac = {platform:'MacIntel', userAgent:'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)', maxTouchPoints:0};
test('client hints distinguish Apple Silicon and 64-bit Intel', () => {
  assert.equal(architecture({platform:'macOS',architecture:'arm',bitness:'64'}),'arm64');
  assert.equal(architecture({platform:'macOS',architecture:'x86',bitness:'64'}),'x86_64');
  assert.equal(architecture({platform:'Windows',architecture:'arm',bitness:'64'}),null);
});
test('Intel compatibility user agent never guesses an Intel processor', async () => {
  assert.equal(await detectMac(mac,()=> 'WebKit WebGL'),null);
  assert.equal(await detectMac(mac,()=> 'Apple M3'),'arm64');
});
test('privacy restrictions fall back safely and blocked WebGL remains unknown', async () => {
  const nav = {...mac,userAgentData:{platform:'macOS',getHighEntropyValues:async()=>{throw Error('blocked');}}};
  assert.equal(await detectMac(nav,()=> 'Apple M2'),'arm64');
  assert.equal(await detectMac(nav,()=> 'Apple GPU'),null);
  assert.equal(await detectMac(nav,()=>{throw Error('blocked');}),null);
});
test('client hints take precedence over renderer', async () => {
  const nav = {...mac,userAgentData:{platform:'macOS',getHighEntropyValues:async()=>({platform:'macOS',architecture:'arm',bitness:'64'})}};
  assert.equal(await detectMac(nav,()=> 'Intel Iris'),'arm64');
});
test('iPads with desktop mode and other platforms require manual selection', async () => {
  for(const nav of [{...mac,maxTouchPoints:5},{platform:'Win32',userAgent:'Windows',maxTouchPoints:0}])
    assert.equal(await detectMac(nav,()=> 'Apple GPU'),null);
});
test('renderer and downloads only expose supported official builds', () => {
  assert.equal(rendererArchitecture('ANGLE (Intel, Intel Iris OpenGL)'),'x86_64');
  assert.equal(rendererArchitecture('Apple'),null);
  assert.deepEqual(Object.keys(downloads),['arm64','x86_64']);
  for(const url of Object.values(downloads)) assert.match(url,/^https:\/\/github\.com\/Brooth-C\/blaze\/releases\/latest\/download\/Blaze-Mac-(arm64|x86_64)\.zip$/);
});
