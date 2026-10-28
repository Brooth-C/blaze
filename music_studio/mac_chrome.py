"""Native Mac navigation around Blaze's existing, single WKWebView.

AppKit owns the window's sidebar, toolbar and standard commands. The web app
remains authoritative for navigation, search and playback. Framework imports
are deferred so source checks can run without macOS.
"""
import json
import threading

from music_studio.mac_sidebar import ROWS, build_sidebar, row_for_section
from music_studio.mac_toolbar import build_toolbar, install_menus


SECTIONS = ('explore', 'downloads', 'library', 'studio')
ACTIONS = ('import', 'settings', 'play', 'previous', 'next', 'open-player', 'close-player')
SYNC_SCRIPT = 'JSON.stringify(window.BlazeMac?.snapshot() ?? null)'
INSTALL_SCRIPT = 'window.BlazeMac?.installNativeChrome({sidebar:true,search:true})'


def navigation_script(section):
    if section not in SECTIONS:
        raise ValueError('Unknown Blaze section.')
    return 'window.BlazeMac?.navigate(' + json.dumps(section) + ')'


def search_script(query, commit=False):
    if not isinstance(query, str) or not isinstance(commit, bool):
        raise ValueError('Invalid search.')
    return 'window.BlazeMac?.search(' + json.dumps(query[:200]) + ',' + json.dumps(commit) + ')'


def action_script(action):
    if action not in ACTIONS:
        raise ValueError('Unknown Blaze action.')
    return 'window.BlazeMac?.action(' + json.dumps(action) + ')'


def find_webview(view):
    """Use the public native hierarchy, never pywebview's instance registry."""
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
    try:
        return getattr(appkit, 'NSGlassEffectView', None)
    except (AttributeError, ImportError):
        return None


_target_class = None


def _protocol_method(objc, protocol, selector):
    """Use the installed runtime's ABI rather than inferred bridge metadata.

    AppKit's formal protocols can use C++ bool (B) where PyObjC's historical
    selector metadata infers Objective-C BOOL (Z). Explicit runtime signatures
    keep class conformance correct on both Apple Silicon and Intel.
    """
    description = protocol.descriptionForInstanceMethod_(selector)
    if description is None:
        raise RuntimeError('Missing AppKit protocol method: ' + selector.decode('ascii'))

    def decorate(method):
        return objc.selector(method, selector=selector, signature=description[1])

    return decorate


def _navigation_target():
    global _target_class
    if _target_class is None:
        import objc
        from Foundation import NSObject
        source = objc.protocolNamed('NSOutlineViewDataSource')
        outline_delegate = objc.protocolNamed('NSOutlineViewDelegate')
        toolbar_delegate = objc.protocolNamed('NSToolbarDelegate')
        menu_validation = objc.protocolNamed('NSMenuItemValidation')
        toolbar_validation = objc.protocolNamed('NSToolbarItemValidation')

        class BlazeNavigationTarget(NSObject, protocols=[
                source, outline_delegate, toolbar_delegate,
                objc.protocolNamed('NSTextFieldDelegate'),
                menu_validation, toolbar_validation]):
            def tick_(self, timer):
                if self.owner:
                    self.owner.sync()

            @_protocol_method(objc, source, b'outlineView:numberOfChildrenOfItem:')
            def outlineView_numberOfChildrenOfItem_(self, outline, item):
                return len(ROWS) if item is None else 0

            @_protocol_method(objc, source, b'outlineView:child:ofItem:')
            def outlineView_child_ofItem_(self, outline, index, item):
                return ROWS[index][0]

            @_protocol_method(objc, source, b'outlineView:isItemExpandable:')
            def outlineView_isItemExpandable_(self, outline, item):
                return False

            @_protocol_method(objc, outline_delegate, b'outlineView:isGroupItem:')
            def outlineView_isGroupItem_(self, outline, item):
                return str(item).startswith('group-')

            @_protocol_method(objc, outline_delegate, b'outlineView:shouldSelectItem:')
            def outlineView_shouldSelectItem_(self, outline, item):
                return bool(self.owner and not self.owner.modal and str(item) in SECTIONS)

            @_protocol_method(objc, outline_delegate, b'outlineView:viewForTableColumn:item:')
            def outlineView_viewForTableColumn_item_(self, outline, column, item):
                from music_studio.mac_sidebar import row_view
                return row_view(outline, str(item))

            @_protocol_method(objc, outline_delegate, b'outlineViewSelectionDidChange:')
            def outlineViewSelectionDidChange_(self, notification):
                if self.owner and not self.owner.syncing_selection:
                    outline = notification.object()
                    section = str(outline.itemAtRow_(outline.selectedRow()))
                    self.owner.navigate_section(section)

            @_protocol_method(objc, toolbar_delegate, b'toolbarAllowedItemIdentifiers:')
            def toolbarAllowedItemIdentifiers_(self, toolbar):
                from music_studio.mac_toolbar import toolbar_identifiers
                return toolbar_identifiers()

            @_protocol_method(objc, toolbar_delegate, b'toolbarDefaultItemIdentifiers:')
            def toolbarDefaultItemIdentifiers_(self, toolbar):
                from music_studio.mac_toolbar import toolbar_identifiers
                return toolbar_identifiers()

            @_protocol_method(objc, toolbar_delegate, b'toolbar:itemForItemIdentifier:willBeInsertedIntoToolbar:')
            def toolbar_itemForItemIdentifier_willBeInsertedIntoToolbar_(self, toolbar, identifier, inserted):
                return self.owner.toolbar_items.get(str(identifier)) if self.owner else None

            def controlTextDidChange_(self, notification):
                if self.owner:
                    self.owner.search(str(notification.object().stringValue()))

            def searchCommit_(self, sender):
                if self.owner:
                    self.owner.search(str(sender.stringValue()), commit=True)

            def focusSearch_(self, sender):
                if self.owner:
                    self.owner.focus_search()

            def importFile_(self, sender):
                if self.owner:
                    self.owner.import_file()

            def openSettings_(self, sender):
                if self.owner:
                    self.owner.action('settings')

            def openPlayer_(self, sender):
                if self.owner:
                    self.owner.action('open-player')

            def toggleSidebar_(self, sender):
                if self.owner:
                    self.owner.split.toggleSidebar_(sender)

            def selectSection_(self, sender):
                if self.owner:
                    self.owner.navigate(int(sender.tag()))

            def playback_(self, sender):
                if self.owner:
                    self.owner.action(('play', 'previous', 'next')[int(sender.tag())])

            @_protocol_method(objc, menu_validation, b'validateMenuItem:')
            def validateMenuItem_(self, item):
                if not self.owner or self.owner.stopped or self.owner.modal:
                    return False
                if item.action() in ('openPlayer:', 'playback:', b'openPlayer:', b'playback:'):
                    return self.owner.has_media
                if item.action() in ('importFile:', b'importFile:'):
                    return not self.owner.importing and not self.owner.busy
                return True

            @_protocol_method(objc, toolbar_validation, b'validateToolbarItem:')
            def validateToolbarItem_(self, item):
                if not self.owner or self.owner.stopped or self.owner.modal:
                    return False
                identifier = str(item.itemIdentifier())
                return ((identifier != 'blaze.player' or self.owner.has_media)
                        and (identifier != 'blaze.import' or not (self.owner.importing or self.owner.busy)))

        _target_class = BlazeNavigationTarget
    return _target_class


class MacNavigation:
    """One source list and toolbar; no new media owner or NSWindow delegate."""
    def __init__(self, window, receipt=None, force_fallback=False, on_import=None):
        self.window = window
        self.receipt = receipt if receipt is not None else {}
        self.force_fallback, self.on_import = force_fallback, on_import
        self.native = self.target = self.timer = self.split = None
        self.outline = self.control = self.surface = self.search_item = self.sidebar_item = None
        self.toolbar_items, self.menu_items = {}, []
        self.stopped = self.evaluating = self.syncing_selection = False
        self.modal = self.has_media = self.busy = False
        self.appearance = self.selected = None
        self.import_request = self.focus_search_request = 0
        self.panel = None
        self.importing = False
        self.studio_workspace = False
        self._studio_sidebar_was_collapsed = self._studio_search_index = None

    def install(self):
        if threading.current_thread() is not threading.main_thread():
            raise RuntimeError('Native navigation must be installed on the Cocoa main thread.')
        if self.split is not None or self.stopped:
            return
        import AppKit
        from Foundation import NSTimer
        native = self.window.native
        web = find_webview(native.contentView()) if native is not None else None
        if web is None:
            raise RuntimeError('The loaded Cocoa web view is not ready.')
        self.native = native
        self.target = _navigation_target().alloc().init()
        self.target.owner = self
        original_controller, original_view = native.contentViewController(), native.contentView()
        original_toolbar = native.toolbar()
        try:
            sidebar, self.outline, self.surface, material = build_sidebar(
                self.target, None if self.force_fallback else glass_class(AppKit))
            self.control = self.outline
            detail = AppKit.NSViewController.alloc().init()
            detail.setView_(web)
            split = AppKit.NSSplitViewController.alloc().init()
            split.splitView().setVertical_(True)
            split.splitView().setDividerStyle_(AppKit.NSSplitViewDividerStyleThin)
            split.splitView().setAutosaveName_('BlazeMainSidebar')
            sidebar_item = AppKit.NSSplitViewItem.sidebarWithViewController_(sidebar)
            sidebar_item.setMinimumThickness_(182)
            sidebar_item.setMaximumThickness_(280)
            sidebar_item.setPreferredThicknessFraction_(.18)
            sidebar_item.setCanCollapse_(True)
            sidebar_item.setAllowsFullHeightLayout_(True)
            self.sidebar_item = sidebar_item
            split.addSplitViewItem_(sidebar_item)
            split.addSplitViewItem_(AppKit.NSSplitViewItem.splitViewItemWithViewController_(detail))
            split.view().setFrame_(original_view.frame())
            self.split = split
            build_toolbar(self)
            native.setContentViewController_(split)
            # NSSplitViewController manages child constraints and window resize.
            split.splitView().setPosition_ofDividerAtIndex_(210, 0)
            native.setTitle_('Blaze')
            native.setTitleVisibility_(AppKit.NSWindowTitleHidden)
            native.setToolbarStyle_(AppKit.NSWindowToolbarStyleUnified)
            install_menus(self)
            self.receipt.update(installed=True, material=material,
                                native_class=self.surface.className(),
                                sidebar_class=self.outline.className(),
                                host_class=split.className(),
                                toolbar_class=native.toolbar().className(),
                                sidebar_width=round(self.surface.frame().size.width),
                                web_navigation=False)
            self.timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
                .3, self.target, 'tick:', None, True)
            self.sync()
        except Exception:
            native.setToolbar_(original_toolbar)
            if original_controller is not None:
                native.setContentViewController_(original_controller)
            else:
                native.setContentView_(original_view)
            self.split = None
            raise

    def _evaluate(self, script, callback=None):
        if self.stopped or self.native is None:
            return
        web = find_webview(self.native.contentView())
        if web is not None:
            web.evaluateJavaScript_completionHandler_(script, callback)
            return True
        return False

    @staticmethod
    def row_for_section(section):
        return row_for_section(section)

    def select_section(self, section):
        row = row_for_section(section)
        if row < 0 or self.outline is None:
            return
        from Foundation import NSIndexSet
        if self.outline.selectedRow() != row:
            self.syncing_selection = True
            try:
                self.outline.selectRowIndexes_byExtendingSelection_(NSIndexSet.indexSetWithIndex_(row), False)
            finally:
                self.syncing_selection = False
        self.selected = section

    def navigate(self, index):
        if isinstance(index, int) and not isinstance(index, bool) and 0 <= index < len(SECTIONS):
            self.navigate_section(SECTIONS[index])

    def navigate_section(self, section):
        if not self.stopped and not self.modal and section in SECTIONS:
            self._evaluate(navigation_script(section))

    def search(self, query, commit=False):
        if not self.stopped and not self.modal:
            self._evaluate(search_script(query, commit))

    def focus_search(self):
        if self.stopped or self.modal or self.search_item is None:
            return
        if self.studio_workspace:
            self._set_studio_workspace(False)
            self._evaluate(navigation_script('explore'))
        self.search_item.beginSearchInteraction()
        self.native.makeFirstResponder_(self.search_item.searchField())
        self.search_item.searchField().selectText_(None)

    def action(self, action):
        if action not in ACTIONS:
            raise ValueError('Unknown Blaze action.')
        if self.stopped or self.modal:
            return
        if action == 'import':
            self.import_file()
        elif action not in ('play', 'previous', 'next', 'open-player') or self.has_media:
            self._evaluate(action_script(action))

    def import_file(self):
        """Paths stay native; an asynchronous sheet avoids blocking the bridge."""
        if (self.stopped or self.modal or self.busy or self.panel is not None
                or self.importing or self.on_import is None):
            return
        import AppKit
        from PyObjCTools import AppHelper
        panel = AppKit.NSOpenPanel.openPanel()
        panel.setCanChooseFiles_(True)
        panel.setCanChooseDirectories_(False)
        panel.setAllowsMultipleSelection_(False)
        panel.setPrompt_('Open in Studio')
        panel.setMessage_('Choose an audio or video file to open in Blaze.')
        self.panel = panel

        def complete(response):
            self.panel = None
            if self.stopped or response != AppKit.NSModalResponseOK:
                return
            selected = str(panel.URL().path())
            self.importing = True

            def ready(value, error):
                if self.stopped:
                    return
                if error or value != 'true':
                    self._import_finished('Finish the current action before opening a file.')
                    return

                def load():
                    try:
                        self.on_import(selected)
                    except Exception as error:
                        AppHelper.callAfter(self._import_finished, str(error))
                    else:
                        AppHelper.callAfter(self._import_finished, None)

                threading.Thread(target=load, name='BlazeNativeImport', daemon=True).start()

            if not self._evaluate('JSON.stringify(window.BlazeMac?.beginImport() === true)', ready):
                self._import_finished('The interface is not ready. Try opening the file again.')

        panel.beginSheetModalForWindow_completionHandler_(self.native, complete)

    def _import_finished(self, error):
        self.importing = False
        if self.stopped:
            return
        if error:
            import AppKit
            alert = AppKit.NSAlert.alloc().init()
            alert.setMessageText_('This file could not be opened')
            alert.setInformativeText_(error)
            alert.addButtonWithTitle_('OK')
            alert.beginSheetModalForWindow_completionHandler_(self.native, None)
        else:
            self._evaluate('window.BlazeMac?.importCompleted()')

    def sync(self):
        if self.stopped or self.evaluating or self.native is None:
            return
        self.evaluating = True

        def complete(value, error):
            self.evaluating = False
            if self.stopped or error or not isinstance(value, str):
                return
            try:
                state = json.loads(value)
                if not isinstance(state, dict) or state.get('section') not in SECTIONS:
                    return
                self._apply_state(state)
            except (TypeError, ValueError):
                return

        web = find_webview(self.native.contentView())
        if web is None:
            self.evaluating = False
        else:
            web.evaluateJavaScript_completionHandler_(SYNC_SCRIPT, complete)

    def _apply_state(self, state):
        self.modal = bool(state.get('modal'))
        self.has_media = bool(state.get('hasMedia'))
        self.busy = bool(state.get('busy'))
        self.select_section(state['section'])
        self.receipt.update(selected=state['section'], web_navigation=True)
        self._set_studio_workspace(state['section'] == 'studio' and state.get('studioWorkspace') is True)
        # Reapply flags after reload, only when the real host is installed.
        if self.split is not None and not state.get('nativeChromeInstalled'):
            self._evaluate(INSTALL_SCRIPT)
        if self.outline is not None:
            self.outline.setEnabled_(not self.modal)
        if self.search_item is not None:
            field = self.search_item.searchField()
            field.setEnabled_(not self.modal)
            query = state.get('query')
            # NSTextView is AppKit's live field editor. Preserve selection/IME.
            if isinstance(query, str) and field.currentEditor() is None and field.stringValue() != query:
                field.setStringValue_(query[:200])
        for name, item in self.toolbar_items.items():
            item.setEnabled_(not self.modal and (name != 'blaze.player' or self.has_media)
                             and (name != 'blaze.import' or not (self.importing or self.busy)))
        appearance = 'dark' if self.studio_workspace else state.get('appearance')
        if appearance in ('system', 'light', 'dark') and appearance != self.appearance:
            import AppKit
            name = {'light': AppKit.NSAppearanceNameAqua,
                    'dark': AppKit.NSAppearanceNameDarkAqua}.get(appearance)
            self.native.setAppearance_(AppKit.NSAppearance.appearanceNamed_(name) if name else None)
            self.appearance = appearance
        for key, attribute, action in [('importRequest', 'import_request', self.import_file),
                                       ('focusSearchRequest', 'focus_search_request', self.focus_search)]:
            value = state.get(key, 0)
            if isinstance(value, int) and value > getattr(self, attribute):
                setattr(self, attribute, value)
                action()

    def _set_studio_workspace(self, active):
        """Give the editor room without taking ownership of web navigation.

        Collapse only on a real transition, so the sidebar toggle still works
        inside Studio. Keep its previous browse state and the original toolbar
        item instance for restoration. No second web view or window is created.
        """
        if (active == self.studio_workspace or self.native is None
                or self.split is None or self.sidebar_item is None):
            return
        import AppKit
        toolbar = self.native.toolbar()
        if active:
            self._studio_sidebar_was_collapsed = bool(self.sidebar_item.isCollapsed())
            self.sidebar_item.setCollapsed_(True)
            self._studio_search_index = next((i for i, item in enumerate(toolbar.items())
                                              if str(item.itemIdentifier()) == 'blaze.search'), None)
            if self._studio_search_index is not None:
                toolbar.removeItemAtIndex_(self._studio_search_index)
            self.native.setTitle_('Blaze · Music Studio')
            self.native.setTitleVisibility_(AppKit.NSWindowTitleVisible)
        else:
            self.sidebar_item.setCollapsed_(self._studio_sidebar_was_collapsed)
            if (self._studio_search_index is not None and not any(
                    str(item.itemIdentifier()) == 'blaze.search' for item in toolbar.items())):
                toolbar.insertItemWithItemIdentifier_atIndex_(
                    'blaze.search', min(self._studio_search_index, len(toolbar.items())))
            self._studio_sidebar_was_collapsed = self._studio_search_index = None
            self.native.setTitle_('Blaze')
            self.native.setTitleVisibility_(AppKit.NSWindowTitleHidden)
        self.studio_workspace = active
        self.receipt.update(studio_workspace=active,
                            studio_chrome_restored=not active,
                            sidebar_collapsed=bool(self.sidebar_item.isCollapsed()))

    def stop(self):
        self.stopped = True
        if self.panel is not None:
            self.panel.cancel_(None)
            self.panel = None
        if self.timer is not None:
            self.timer.invalidate()
            self.timer = None
        if self.target is not None:
            self.target.owner = None
        for menu, item in self.menu_items:
            menu.removeItem_(item)
        self.menu_items.clear()


def attach_navigation(window, receipt=None, on_import=None):
    """Install after loaded: Cocoa first attaches WKWebView at navigation."""
    from PyObjCTools import AppHelper
    adapter = MacNavigation(window, receipt, on_import=on_import)

    def install():
        try:
            adapter.install()
        except Exception as error:
            adapter.receipt.update(installed=False, error=str(error))
            print('Native navigation unavailable:', error)
            adapter.stop()

    def loaded():
        AppHelper.callAfter(install)

    def closed():
        AppHelper.callAfter(adapter.stop)

    window.events.loaded += loaded
    window.events.closed += closed
    return adapter
