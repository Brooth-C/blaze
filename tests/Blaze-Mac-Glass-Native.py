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
<style>body{font:16px -apple-system,sans-serif;margin:0;padding:36px;
background:#f8f5f0;color:#202020}h1{font-size:38px;letter-spacing:-1px}
p{max-width:640px;line-height:1.6;color:#606060}.art{height:180px;border-radius:18px;
background:linear-gradient(125deg,#e6bb8b,#d65727 40%,#314c64);margin:28px 0}
html[data-appearance=dark] body{background:#1e1c1b;color:#f5f2ef}
html[data-appearance=dark] p{color:#bbb8b4}</style>
<h1>Blaze</h1><p>Native source-list and toolbar compatibility proof. This is a
local test fixture using the same AppKit shell as the packaged app.</p>
<div class="art"></div><h2 id="section">Explore</h2><p id="query"></p>
<script>
const state={section:'explore',query:'',appearance:'APPEARANCE',hasMedia:false,studioWorkspace:true,
modal:false,nativeChromeInstalled:false};
window.BlazeMacStudio={snapshot:()=>({active:state.section==='studio'})};
window.BlazeMac={snapshot:()=>state,
installNativeChrome:()=>{state.nativeChromeInstalled=true;},
navigate:value=>{if(['explore','downloads','library','studio'].includes(value)){
state.section=value;document.getElementById('section').textContent=value;}},
search:(value,commit)=>{state.query=value;state.committed=commit;
window.BlazeMac.navigate('explore');document.getElementById('query').textContent=value;},
action:value=>{state.action=value;}};
</script></html>"""


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
    original_delegate = window.delegate()
    adapter.install()
    assert window.delegate() is original_delegate
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
                    from Foundation import NSIndexSet
                    row = adapter.row_for_section('downloads')
                    adapter.outline.selectRowIndexes_byExtendingSelection_(NSIndexSet.indexSetWithIndex_(row), False)
                    stage = 1
                elif stage == 1 and receipt['navigation'].get('selected') == 'downloads':
                    web.evaluateJavaScript_completionHandler_("window.BlazeMac.navigate('studio')", None)
                    stage = 2
                elif stage == 2 and receipt['navigation'].get('selected') == 'studio':
                    receipt['navigation']['roundtrip'] = True
                    assert adapter.studio_workspace and adapter.sidebar_item.isCollapsed(), receipt
                    assert not any(str(item.itemIdentifier()) == 'blaze.search' for item in window.toolbar().items()), receipt
                    assert not window.toolbar().isVisible(), receipt
                    expected = AppKit.NSAppearanceNameAqua if args.appearance == 'light' else AppKit.NSAppearanceNameDarkAqua
                    assert str(window.appearance().name()) == expected, receipt
                    assert str(window.title()) == 'Blaze · Music Studio', receipt
                    receipt['studio_workspace'] = {'sidebar_collapsed': True, 'search_hidden': True,
                                                   'appearance_preserved': True, 'same_webview': web.window() is window}
                    adapter.search('late toolbar edit', True)
                    stage, capture_at = 2.5, time.monotonic() + .4
                elif stage == 2.5 and time.monotonic() >= capture_at:
                    assert receipt['navigation'].get('selected') == 'studio', 'A delayed search action navigated away from Studio.'
                    receipt['studio_workspace']['stale_search_ignored'] = True
                    adapter.focus_search()
                    field = adapter.search_item.searchField()
                    field.setStringValue_('acoustic sessions')
                    field.sendAction_to_(field.action(), field.target())
                    stage = 3
                elif stage == 3 and receipt['navigation'].get('selected') == 'explore':
                    assert not adapter.studio_workspace and not adapter.sidebar_item.isCollapsed(), receipt
                    assert any(str(item.itemIdentifier()) == 'blaze.search' for item in window.toolbar().items()), receipt
                    assert window.toolbar().isVisible(), receipt
                    expected = AppKit.NSAppearanceNameAqua if args.appearance == 'light' else AppKit.NSAppearanceNameDarkAqua
                    assert str(window.appearance().name()) == expected, receipt
                    receipt['studio_workspace']['browse_restored'] = True
                    def search_result(value, error):
                        receipt['search'] = not error and value == 'true'
                    web.evaluateJavaScript_completionHandler_(
                        "JSON.stringify(window.BlazeMac.snapshot().query==='acoustic sessions' && window.BlazeMac.snapshot().committed===true)", search_result)
                    window.setContentSize_(AppKit.NSMakeSize(780, 600))
                    stage, capture_at = 4, time.monotonic() + .6
                elif stage == 4 and time.monotonic() >= capture_at:
                    assert receipt.get('search'), 'Native search did not reach the web app.'
                    assert adapter.outline.selectedRow() == adapter.row_for_section('explore')
                    frame, detail = adapter.surface.frame(), web.frame()
                    receipt['sidebar_size'] = {'width': frame.size.width, 'height': frame.size.height}
                    receipt['detail_size'] = {'width': detail.size.width, 'height': detail.size.height}
                    assert 180 <= frame.size.width <= 281 and frame.size.height >= 500, receipt
                    assert 400 <= detail.size.width <= 600 and detail.size.height >= 500, receipt
                    assert web.window() is window, 'The one WKWebView must remain hosted by the original window.'
                    assert window.contentViewController() is adapter.split
                    assert adapter.outline.className() == 'NSOutlineView'
                    assert adapter.search_item.className() == 'NSSearchToolbarItem'
                    receipt['single_webview'] = True
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
