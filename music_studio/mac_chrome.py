"""Small native navigation adapter for the existing Cocoa/WKWebView host.

The web application remains the only owner of playback and section state. This
module never exposes a Python object or arbitrary command executor to the page.
AppKit imports are deferred so older systems and non-Mac source checks can load
the module without importing macOS 26-only symbols.
"""
import json
import threading


SECTIONS = ('explore', 'downloads', 'library', 'studio')
LABELS = ('Explore', 'Downloads', 'Library', 'Studio')
SYNC_SCRIPT = """(() => {
  if (!window.BlazeDesktop) return null;
  document.body.dataset.nativeNavigation = 'true';
  return JSON.stringify({section: window.BlazeDesktop.activeSection(),
    appearance: document.documentElement.dataset.appearance || 'system'});
})()"""


def navigation_script(section):
    """Only these four product actions can cross from native UI to web UI."""
    if section not in SECTIONS:
        raise ValueError('Unknown Blaze section.')
    return 'window.BlazeDesktop?.selectSection(' + json.dumps(section) + ')'


def find_webview(view):
    """Find WKWebView through the public native NSView hierarchy."""
    if view is None:
        return None
    if view.respondsToSelector_('evaluateJavaScript:completionHandler:'):
        return view
    for child in view.subviews():
        found = find_webview(child)
        if found is not None:
            return found
    return None


def glass_class(appkit):
    """Runtime lookup, not an unconditional import of a new framework class."""
    try:
        return getattr(appkit, 'NSGlassEffectView', None)
    except (AttributeError, ImportError):
        return None


_target_class = None


def _navigation_target():
    global _target_class
    if _target_class is None:
        from Foundation import NSObject

        class BlazeNavigationTarget(NSObject):
            def activate_(self, sender):
                self.owner.navigate(sender.selectedSegment())

            def tick_(self, timer):
                self.owner.sync()

        _target_class = BlazeNavigationTarget
    return _target_class


class MacNavigation:
    """One titlebar accessory; AppKit reserves its space above web content."""
    def __init__(self, window, receipt=None, force_fallback=False):
        self.window = window
        self.receipt = receipt if receipt is not None else {}
        self.force_fallback = force_fallback
        self.native = self.accessory = self.target = self.timer = None
        self.control = self.surface = None
        self.stopped = False
        self.evaluating = False
        self.appearance = None

    def install(self):
        if threading.current_thread() is not threading.main_thread():
            raise RuntimeError('Native navigation must be installed on the Cocoa main thread.')
        if self.accessory is not None or self.stopped:
            return
        import AppKit
        from Foundation import NSTimer
        native = self.window.native
        if native is None:
            raise RuntimeError('The Cocoa window is not ready.')
        frame = AppKit.NSMakeRect(0, 0, 452, 44)
        container = AppKit.NSView.alloc().initWithFrame_(frame)
        control = AppKit.NSSegmentedControl.alloc().initWithFrame_(AppKit.NSMakeRect(8, 6, 436, 32))
        control.setSegmentCount_(len(SECTIONS))
        control.setTrackingMode_(AppKit.NSSegmentSwitchTrackingSelectOne)
        control.setSegmentStyle_(AppKit.NSSegmentStyleAutomatic)
        control.setAccessibilityLabel_('Blaze sections')
        for index, label in enumerate(LABELS):
            control.setLabel_forSegment_(label, index)
            control.setWidth_forSegment_(109, index)
        control.setSelectedSegment_(0)
        target = _navigation_target().alloc().init()
        target.owner = self
        control.setTarget_(target)
        control.setAction_('activate:')
        content = AppKit.NSView.alloc().initWithFrame_(frame)
        content.addSubview_(control)
        new_glass = None if self.force_fallback else glass_class(AppKit)
        if new_glass is not None:
            surface = new_glass.alloc().initWithFrame_(frame)
            # The controls are inside contentView, not a sibling over a blur.
            surface.setContentView_(content)
            surface.setStyle_(AppKit.NSGlassEffectViewStyleRegular)
            material = 'liquid-glass'
        else:
            surface = AppKit.NSVisualEffectView.alloc().initWithFrame_(frame)
            surface.setMaterial_(AppKit.NSVisualEffectMaterialTitlebar)
            surface.setState_(AppKit.NSVisualEffectStateFollowsWindowActiveState)
            surface.addSubview_(content)
            material = 'system-vibrancy'
        container.addSubview_(surface)
        accessory = AppKit.NSTitlebarAccessoryViewController.alloc().init()
        accessory.setView_(container)
        accessory.setLayoutAttribute_(AppKit.NSLayoutAttributeBottom)
        native.addTitlebarAccessoryViewController_(accessory)
        self.native, self.accessory, self.target = native, accessory, target
        self.control, self.surface = control, surface
        self.receipt.update(installed=True, material=material, native_class=surface.className(),
                            selected='explore', web_navigation=False)
        self.timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            .4, target, 'tick:', None, True)
        self.sync()

    def navigate(self, index):
        if self.stopped or not isinstance(index, int) or not 0 <= index < len(SECTIONS):
            return
        view = find_webview(self.native.contentView())
        if view is not None:
            view.evaluateJavaScript_completionHandler_(navigation_script(SECTIONS[index]), None)

    def sync(self):
        if self.stopped or self.evaluating or self.native is None:
            return
        view = find_webview(self.native.contentView())
        if view is None:
            return
        self.evaluating = True

        def complete(value, error):
            self.evaluating = False
            if self.stopped or error or not isinstance(value, str):
                return
            try:
                state = json.loads(value)
                if not isinstance(state, dict):
                    return
                section = state.get('section')
                if section in SECTIONS:
                    self.control.setSelectedSegment_(SECTIONS.index(section))
                    self.receipt.update(selected=section, web_navigation=True)
                appearance = state.get('appearance')
                if appearance in ('system', 'light', 'dark') and appearance != self.appearance:
                    import AppKit
                    name = {'light': AppKit.NSAppearanceNameAqua, 'dark': AppKit.NSAppearanceNameDarkAqua}.get(appearance)
                    self.native.setAppearance_(AppKit.NSAppearance.appearanceNamed_(name) if name else None)
                    self.appearance = appearance
            except (TypeError, ValueError):
                pass

        view.evaluateJavaScript_completionHandler_(SYNC_SCRIPT, complete)

    def stop(self):
        self.stopped = True
        if self.timer is not None:
            self.timer.invalidate()
            self.timer = None
        if self.target is not None:
            self.target.owner = None


def attach_navigation(window, receipt=None):
    """pywebview events run in workers; every AppKit operation is scheduled."""
    from PyObjCTools import AppHelper
    adapter = MacNavigation(window, receipt)

    def install():
        try:
            adapter.install()
        except Exception as error:
            # A native enhancement must not prevent access to the web controls.
            adapter.receipt.update(installed=False, error=str(error))
            print('Native navigation unavailable:', error)
            adapter.stop()

    def shown():
        AppHelper.callAfter(install)

    def closed():
        AppHelper.callAfter(adapter.stop)

    window.events.shown += shown
    window.events.closed += closed
    return adapter
