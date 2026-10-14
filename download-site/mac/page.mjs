import { detectMac, downloads } from './detect.mjs';

const processor = document.querySelector('#processor');
const button = document.querySelector('#download');
const status = document.querySelector('#status');
let manual = false;
let detected = null;

function update(choice, automatic = false) {
  const url = downloads[choice];
  button.setAttribute('aria-disabled', url ? 'false' : 'true');
  if (url) {
    button.href = url;
    const name = choice === 'arm64' ? 'Apple Silicon' : 'Intel';
    status.textContent = automatic ? `${name} Mac detected. Your download is ready.` : `${name} download selected.`;
    button.textContent = `Download for Mac · ${name}`;
  } else {
    button.removeAttribute('href');
    status.textContent = 'Choose your Mac processor to get the right download.';
    button.textContent = 'Download for Mac';
  }
}

function renderer() {
  const canvas = document.createElement('canvas');
  const gl = canvas.getContext('webgl');
  if (!gl) return null;
  try {
    const info = gl.getExtension('WEBGL_debug_renderer_info');
    return info ? gl.getParameter(info.UNMASKED_RENDERER_WEBGL) : null;
  } finally { gl.getExtension('WEBGL_lose_context')?.loseContext(); }
}

processor.addEventListener('change', () => {
  manual = true;
  update(processor.value || detected, !processor.value && !!detected);
});
button.addEventListener('click', event => {
  if (button.getAttribute('aria-disabled') === 'true') event.preventDefault();
});
detected = await detectMac(navigator, renderer);
if (!manual) update(detected, !!detected);
