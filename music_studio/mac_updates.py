"""Sparkle 2 native updates. Cocoa imports stay off non-Mac source/test paths."""
import json
from pathlib import Path
import threading
import time

CONFIG = Path(__file__).with_name('mac_update_config.json')
# Read only; do not reload audio or navigate when checking whether relaunch is safe.
IDLE_SCRIPT = '''JSON.stringify((()=>{
 const media=document.getElementById('media');
 const practice=window.BlazeMacPractice?.snapshot();
 return !!media && !!practice && media.paused && !practice.saving &&
 !practice.pitchBusy && !practice.downloadBusy && !practice.requestedMode &&
 (typeof importing === 'undefined' || !importing) &&
 !window.BlazeMacStudio?.viewState()?.pending;
})())'''


def configuration():
    import base64
    value = json.loads(CONFIG.read_text())
    if value['feed_url'] != 'https://github.com/Brooth-C/blaze/releases/latest/download/mac-appcast.xml':
        raise ValueError('Unexpected Mac update feed.')
    if len(base64.b64decode(value['public_key'], validate=True)) != 32:
        raise ValueError('Invalid update verification key.')
    return value


def jobs_busy(studio):
    """Do not replace the app while any executable/model consumer is working."""
    with studio.lock:
        if studio.closed or studio.state.get('busy'):
            return True
        if studio.stems and studio.stems.value.get('status') == 'running':
            return True
        audio = studio.practice_audio
        if audio:
            with audio.lock:
                if audio.saving or any(row['status'] == 'pending' for row in audio.jobs.values()):
                    return True
        downloads = studio.downloader
        return bool(downloads and downloads.worker and downloads.worker.is_alive())


class RelaunchGate:
    """A retained Sparkle install block runs exactly once, only after idle proof."""
    def __init__(self):
        self.pending = None

    def defer(self, handler):
        self.pending = handler
        return True

    def finish(self, idle):
        if not idle or self.pending is None:
            return False
        callback, self.pending = self.pending, None
        callback()
        return True


_target = None


def delegate_class():
    global _target
    if _target is None:
        import objc
        from Foundation import NSObject
        from music_studio.mac_chrome import _protocol_method
        protocol = objc.protocolNamed('SPUUpdaterDelegate')
        # Sparkle isn't a system framework with bundled PyObjC metadata. Supply
        # the void(void) install block ABI explicitly, including its implicit arg.
        objc.registerMetaDataForSelector(b'BlazeUpdateDelegate',
            b'updater:shouldPostponeRelaunchForUpdate:untilInvokingBlock:',
            {'arguments': {4: {'callable': {'retval': {'type': b'v'},
                                          'arguments': {0: {'type': b'^v'}}}}}})

        class BlazeUpdateDelegate(NSObject, protocols=[protocol]):
            @_protocol_method(objc, protocol, b'updater:shouldPostponeRelaunchForUpdate:untilInvokingBlock:')
            def updater_shouldPostponeRelaunchForUpdate_untilInvokingBlock_(self, updater, item, handler):
                self.owner.receipt['relaunch_deferred'] = True
                return self.owner.gate.defer(handler)

            def tick_(self, timer):
                if self.owner:
                    self.owner.poll()

        _target = BlazeUpdateDelegate
    return _target


class MacUpdater:
    def __init__(self, window, studio, receipt, start=True):
        self.window, self.studio, self.receipt = window, studio, receipt
        self.start = start
        self.gate = RelaunchGate()
        self.controller = self.delegate = self.timer = self.menu = self.item = None
        self.stopped = False
        self.polling = False
        self.idle_since = None

    def install(self):
        if self.controller is not None or self.stopped:
            return
        if threading.current_thread() is not threading.main_thread():
            raise RuntimeError('Sparkle must start on the Cocoa main thread.')
        import objc
        import AppKit
        from Foundation import NSBundle, NSTimer
        config = configuration()
        bundle = NSBundle.mainBundle()
        if bundle.objectForInfoDictionaryKey_('SUPublicEDKey') != config['public_key']:
            raise RuntimeError('The bundled update verification key does not match.')
        framework = Path(str(bundle.bundlePath())) / 'Contents/Frameworks/Sparkle.framework'
        objc.loadBundle('Sparkle', {}, bundle_path=str(framework))
        self.delegate = delegate_class().alloc().init()
        self.delegate.owner = self
        controller = objc.lookUpClass('SPUStandardUpdaterController')
        self.controller = controller.alloc().initWithStartingUpdater_updaterDelegate_userDriverDelegate_(False, self.delegate, None)
        main = AppKit.NSApp.mainMenu()
        if main is None or not main.numberOfItems():
            raise RuntimeError('The application menu is unavailable.')
        self.menu = main.itemAtIndex_(0).submenu()
        self.item = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_('Check for Updates…', 'checkForUpdates:', '')
        self.item.setTarget_(self.controller)
        self.menu.insertItem_atIndex_(self.item, min(2, self.menu.numberOfItems()))
        # Never silently install on quit; always use Sparkle's user-facing flow.
        if self.start:
            self.controller.startUpdater()
        self.timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            .5, self.delegate, 'tick:', None, True)
        self.receipt.update(installed=True, framework='Sparkle 2.10.1', signed_updates=True)

    def poll(self):
        if self.stopped or self.polling or not self.gate.pending:
            return
        if jobs_busy(self.studio):
            self.idle_since = None
            return
        from music_studio.mac_chrome import find_webview
        native = getattr(self.window, 'native', None)
        view = find_webview(native.contentView()) if native else None
        if view is None:
            return  # Fail closed if playback state cannot be established.
        self.polling = True

        def complete(value, error):
            self.polling = False
            if self.stopped or error or jobs_busy(self.studio):
                self.idle_since = None
                return
            try:
                idle = json.loads(str(value)) is True
            except (ValueError, TypeError):
                idle = False
            if not idle:
                self.idle_since = None
            else:
                now = time.monotonic()
                if self.idle_since is None:
                    self.idle_since = now
                elif now - self.idle_since >= 2:
                    self.gate.finish(True)

        view.evaluateJavaScript_completionHandler_(IDLE_SCRIPT, complete)

    def stop(self):
        self.stopped = True
        self.gate.pending = None
        if self.timer:
            self.timer.invalidate()
            self.timer = None
        if self.item is not None:
            self.menu.removeItem_(self.item)
            self.item = None
        if self.delegate:
            self.delegate.owner = None


def attach_updates(window, studio, receipt, start=True):
    from PyObjCTools import AppHelper
    adapter = MacUpdater(window, studio, receipt, start=start)

    def install():
        try:
            adapter.install()
        except Exception as error:
            adapter.stop()
            receipt.update(installed=False, error=str(error))
            print('Mac updater unavailable:', error)

    window.events.loaded += lambda: AppHelper.callAfter(install)
    window.events.closed += lambda: AppHelper.callAfter(adapter.stop)
    return adapter
