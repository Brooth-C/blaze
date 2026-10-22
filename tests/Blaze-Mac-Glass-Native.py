"""Focused real-AppKit material/navigation proof on a macOS 26 runner.

This verifies the adapter and real framework classes, not the packaged web app
or device performance. The two packaged macOS 15 jobs cover its older fallback.
"""
from pathlib import Path
from types import SimpleNamespace
import argparse
import json
import platform
import subprocess
import sys
import time
import traceback

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from music_studio.mac_chrome import MacNavigation


HTML = """<!doctype html><html data-appearance="APPEARANCE"><meta charset="utf-8">
<style>body{font:18px -apple-system,sans-serif;margin:0;padding:55px;
background:#f8f5f0;color:#202020}h1{font-size:46px;letter-spacing:-1px}
p{max-width:640px;line-height:1.6;color:#606060}.art{height:240px;border-radius:24px;
background:linear-gradient(125deg,#e6bb8b,#d65727 40%,#314c64);margin:35px 0}
html[data-appearance=dark] body{background:#1e1c1b;color:#f5f2ef}
html[data-appearance=dark] p{color:#bbb8b4}</style>
<h1>Blaze</h1><p>Native navigation compatibility test. The navigation above uses
the same AppKit adapter as the packaged app; this content is a local test fixture.</p>
<div class="art"></div><h2 id="section">Explore</h2>
<script>let section='explore';window.BlazeDesktop={activeSection:()=>section,
selectSection:value=>{if(['explore','downloads','library','studio'].includes(value)){
section=value;document.getElementById('section').textContent=value;}}};</script>
</html>"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--appearance', choices=('light', 'dark'), default='light')
    parser.add_argument('--expect-reduced-transparency', action='store_true')
    parser.add_argument('--expect-increased-contrast', action='store_true')
    parser.add_argument('--expect-standard-material', action='store_true')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    import AppKit
    from Foundation import NSObject, NSTimer
    from WebKit import WKWebView
    app = AppKit.NSApplication.sharedApplication()
    app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyRegular)
    window = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
        AppKit.NSMakeRect(100, 120, 1000, 780),
        AppKit.NSWindowStyleMaskTitled | AppKit.NSWindowStyleMaskClosable | AppKit.NSWindowStyleMaskResizable,
        AppKit.NSBackingStoreBuffered, False)
    window.setReleasedWhenClosed_(False)
    window.setTitle_('Blaze · Native navigation fixture')
    web = WKWebView.alloc().initWithFrame_(AppKit.NSMakeRect(0, 0, 1000, 780))
    web.setAutoresizingMask_(AppKit.NSViewWidthSizable | AppKit.NSViewHeightSizable)
    window.setContentView_(web)
    web.loadHTMLString_baseURL_(HTML.replace('APPEARANCE', args.appearance), None)
    receipt = {'ok': False, 'os': platform.mac_ver()[0], 'appearance': args.appearance,
               'scope': 'real AppKit adapter with local HTML fixture; not packaged app or performance benchmark'}
    adapter = MacNavigation(SimpleNamespace(native=window), receipt.setdefault('navigation', {}))
    adapter.install()
    workspace = AppKit.NSWorkspace.sharedWorkspace()
    receipt['reduce_transparency'] = bool(workspace.accessibilityDisplayShouldReduceTransparency())
    receipt['increase_contrast'] = bool(workspace.accessibilityDisplayShouldIncreaseContrast())
    window.makeKeyAndOrderFront_(None)
    app.activateIgnoringOtherApps_(True)
    deadline, stage, capture_at = time.monotonic() + 25, 0, 0

    class BlazeGlassTestDriver(NSObject):
        def tick_(self, timer):
            nonlocal stage, capture_at
            try:
                if time.monotonic() > deadline:
                    raise RuntimeError('Native glass navigation proof timed out.')
                if stage == 0 and receipt['navigation'].get('web_navigation'):
                    assert receipt['navigation']['material'] == 'liquid-glass', receipt
                    assert receipt['navigation']['native_class'] == 'NSGlassEffectView', receipt
                    assert adapter.surface.contentView() is not None
                    if args.expect_reduced_transparency:
                        assert receipt['reduce_transparency'], 'Reduce Transparency was not enabled in the test session.'
                    if args.expect_increased_contrast:
                        assert receipt['increase_contrast'], 'Increase Contrast was not enabled in the test session.'
                    if args.expect_standard_material:
                        assert not receipt['reduce_transparency'] and not receipt['increase_contrast'], 'Standard material preferences were not enabled in the test session.'
                    adapter.control.setSelectedSegment_(1)
                    adapter.control.sendAction_to_(adapter.control.action(), adapter.control.target())
                    stage = 1
                elif stage == 1 and receipt['navigation'].get('selected') == 'downloads':
                    web.evaluateJavaScript_completionHandler_("window.BlazeDesktop.selectSection('studio')", None)
                    stage = 2
                elif stage == 2 and receipt['navigation'].get('selected') == 'studio':
                    receipt['navigation']['roundtrip'] = True
                    window.setContentSize_(AppKit.NSMakeSize(780, 600))
                    stage, capture_at = 3, time.monotonic() + .6
                elif stage == 3 and time.monotonic() >= capture_at:
                    frame = adapter.control.frame()
                    receipt['control_size'] = {'width': frame.size.width, 'height': frame.size.height}
                    assert frame.size.width > 400 and frame.size.height >= 28
                    output = args.output / 'navigation.png'
                    subprocess.run(['/usr/sbin/screencapture', '-x', '-l', str(window.windowNumber()), str(output)],
                                   check=True, timeout=10)
                    assert output.is_file() and output.stat().st_size > 100
                    receipt.update(ok=True, screenshot=output.name)
                    finish(timer)
            except Exception as error:
                receipt.update(error=str(error))
                traceback.print_exc()
                finish(timer)

    def finish(timer):
        timer.invalidate()
        adapter.stop()
        (args.output / 'navigation.json').write_text(json.dumps(receipt, indent=2) + '\n')
        app.stop_(None)
        # stop: does not itself wake NSApplication's event wait when called by
        # a run-loop timer rather than a mouse/key event.
        event = AppKit.NSEvent.otherEventWithType_location_modifierFlags_timestamp_windowNumber_context_subtype_data1_data2_(
            AppKit.NSEventTypeApplicationDefined, AppKit.NSMakePoint(0, 0), 0, 0, 0, None, 0, 0, 0)
        app.postEvent_atStart_(event, True)

    driver = BlazeGlassTestDriver.alloc().init()
    timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(.1, driver, 'tick:', None, True)
    app.run()
    timer.invalidate()
    window.close()
    print(json.dumps(receipt, indent=2))
    return 0 if receipt['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
