export const downloads = Object.freeze({
  arm64: 'https://github.com/Brooth-C/blaze/releases/latest/download/Blaze-Mac-arm64.zip',
  x86_64: 'https://github.com/Brooth-C/blaze/releases/latest/download/Blaze-Mac-x86_64.zip',
});

export function isMac(nav) {
  if (nav.maxTouchPoints > 1 || /iPhone|iPad|iPod|Android/i.test(nav.userAgent || '')) return false;
  return /^(macOS|Mac OS)$/i.test(nav.userAgentData?.platform || '') || /Mac/i.test(nav.platform || '');
}

export function architecture(hints) {
  if (!/^(macOS|Mac OS)$/i.test(hints?.platform || '')) return null;
  if (/^(arm|arm64|aarch64)$/i.test(hints.architecture || '')) return 'arm64';
  if (/^(x86|x86_64|amd64)$/i.test(hints.architecture || '') && hints.bitness === '64') return 'x86_64';
  return null;
}

export function rendererArchitecture(renderer) {
  if (/\bApple (M\d+\b|GPU\b)/i.test(renderer)) return 'arm64';
  // Never infer Intel from the MacIntel platform / Intel Mac OS X user agent:
  // Apple Silicon browsers also report those compatibility strings.
  if (/\b(Intel|AMD|ATI|Radeon|NVIDIA|GeForce)\b/i.test(renderer)) return 'x86_64';
  return null;
}

export async function detectMac(nav, getRenderer) {
  if (!isMac(nav)) return null;
  let timer;
  try {
    if (nav.userAgentData?.getHighEntropyValues) {
      const hints = await Promise.race([
        nav.userAgentData.getHighEntropyValues(['architecture', 'bitness', 'platform']),
        new Promise(resolve => { timer = setTimeout(() => resolve(null), 1500); }),
      ]);
      const found = architecture(hints);
      if (found) return found;
    }
  } catch { /* Permission or privacy restrictions: try an available GPU hint. */ }
  finally { clearTimeout(timer); }
  try { return rendererArchitecture(getRenderer() || ''); }
  catch { return null; }
}
