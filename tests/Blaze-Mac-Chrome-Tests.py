"""Native bridge contracts runnable without AppKit; runtime proof is separate."""
from pathlib import Path
from types import SimpleNamespace
import json
import sys
import threading
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from music_studio import mac_chrome


class View:
    def __init__(self, children=(), evaluator=False):
        self.children, self.evaluator, self.scripts = children, evaluator, []

    def respondsToSelector_(self, selector):
        return self.evaluator and selector == 'evaluateJavaScript:completionHandler:'

    def subviews(self):
        return self.children

    def evaluateJavaScript_completionHandler_(self, script, callback):
        self.scripts.append((script, callback))


class Event(list):
    def __iadd__(self, callback):
        self.append(callback)
        return self


class MacChromeTests(unittest.TestCase):
    def test_formal_protocol_signature_is_used_without_bool_abi_rewriting(self):
        selector = b'outlineView:isItemExpandable:'
        for signature in (b'B@:@@', b'Z@:@@'):
            protocol = Mock()
            protocol.descriptionForInstanceMethod_.return_value = (selector, signature)
            objc = SimpleNamespace(selector=Mock())
            method = lambda self, outline, item: False
            mac_chrome._protocol_method(objc, protocol, selector)(method)
            objc.selector.assert_called_once_with(method, selector=selector, signature=signature)
        protocol.descriptionForInstanceMethod_.return_value = None
        with self.assertRaisesRegex(RuntimeError, 'Missing AppKit protocol method'):
            mac_chrome._protocol_method(objc, protocol, selector)

    @unittest.skipUnless(sys.platform == 'darwin', 'Real AppKit class conformance requires macOS.')
    def test_real_appkit_target_conforms_before_packaging(self):
        # This source check runs before model staging/decoder compilation and
        # packaging. A formal-protocol ABI mismatch must fail here, never be
        # hidden behind the launcher's working web-navigation fallback.
        import AppKit
        import objc
        target = mac_chrome._navigation_target().alloc().init()
        self.assertIsInstance(target, AppKit.NSObject)
        pairs = [
            ('NSOutlineViewDataSource', b'outlineView:isItemExpandable:'),
            ('NSOutlineViewDataSource', b'outlineView:numberOfChildrenOfItem:'),
            ('NSOutlineViewDelegate', b'outlineView:isGroupItem:'),
            ('NSOutlineViewDelegate', b'outlineView:shouldSelectItem:'),
            ('NSToolbarDelegate', b'toolbar:itemForItemIdentifier:willBeInsertedIntoToolbar:'),
            ('NSMenuItemValidation', b'validateMenuItem:'),
            ('NSToolbarItemValidation', b'validateToolbarItem:'),
        ]
        for protocol_name, selector in pairs:
            protocol = objc.protocolNamed(protocol_name)
            self.assertTrue(target.conformsToProtocol_(protocol), protocol_name)
            expected = protocol.descriptionForInstanceMethod_(selector)[1]
            actual = getattr(target, selector.decode('ascii').replace(':', '_')).signature
            self.assertEqual(objc.splitSignature(actual), objc.splitSignature(expected), selector)
        target.owner = None

    def test_bridge_uses_fixed_methods_and_json_arguments(self):
        for section in mac_chrome.SECTIONS:
            self.assertEqual(mac_chrome.navigation_script(section),
                             'window.BlazeMac?.navigate(' + json.dumps(section) + ')')
        for invalid in [None, 1, '', 'settings', 'explore);fetch("https://example.com")']:
            with self.subTest(value=invalid), self.assertRaises(ValueError):
                mac_chrome.navigation_script(invalid)
        for action in mac_chrome.ACTIONS:
            self.assertEqual(mac_chrome.action_script(action),
                             'window.BlazeMac?.action(' + json.dumps(action) + ')')
        with self.assertRaises(ValueError):
            mac_chrome.action_script('eval')
        query = '\");fetch("https://example.com");\\\n'
        self.assertEqual(mac_chrome.search_script(query, True),
                         'window.BlazeMac?.search(' + json.dumps(query) + ',true)')
        self.assertEqual(mac_chrome.search_script('a' * 400),
                         'window.BlazeMac?.search(' + json.dumps('a' * 200) + ',false)')
        for query, commit in [(None, False), ('query', 1)]:
            with self.assertRaises(ValueError):
                mac_chrome.search_script(query, commit)

    def test_public_webview_hierarchy_and_runtime_glass_fallback(self):
        web = View(evaluator=True)
        self.assertIs(mac_chrome.find_webview(View([View(), View([web])])), web)
        self.assertIsNone(mac_chrome.find_webview(View()))
        self.assertIsNone(mac_chrome.find_webview(None))
        self.assertIsNone(mac_chrome.glass_class(SimpleNamespace()))
        cls = object()
        self.assertIs(mac_chrome.glass_class(SimpleNamespace(NSGlassEffectView=cls)), cls)

    def test_install_requires_the_cocoa_main_thread_before_import(self):
        failures = []

        def worker():
            try:
                mac_chrome.MacNavigation(None).install()
            except RuntimeError as error:
                failures.append(str(error))
        thread = threading.Thread(target=worker)
        thread.start()
        thread.join()
        self.assertEqual(failures, ['Native navigation must be installed on the Cocoa main thread.'])

    def adapter(self):
        web, native = View(evaluator=True), Mock()
        native.contentView.return_value = View([web])
        adapter = mac_chrome.MacNavigation(SimpleNamespace(native=native))
        adapter.native, adapter.outline = native, Mock()
        adapter.search_item = Mock()
        adapter.search_item.searchField.return_value.currentEditor.return_value = None
        adapter.select_section = Mock()
        return adapter, web, native

    def apply(self, adapter, state):
        appearance = Mock()
        appkit = SimpleNamespace(NSAppearance=appearance, NSAppearanceNameAqua='Aqua',
                                 NSAppearanceNameDarkAqua='DarkAqua', NSWindowTitleVisible=0,
                                 NSWindowTitleHidden=1)
        with patch.dict(sys.modules, {'AppKit': appkit}):
            adapter._apply_state(state)
        return appearance

    def test_native_commands_route_to_the_single_web_application(self):
        adapter, web, _ = self.adapter()
        adapter.navigate(2)
        adapter.search('piano', True)
        adapter.action('settings')
        adapter.action('play')  # no loaded media
        self.assertEqual([script for script, _ in web.scripts], [
            mac_chrome.navigation_script('library'), mac_chrome.search_script('piano', True),
            mac_chrome.action_script('settings')])
        adapter.has_media = True
        adapter.action('play')
        self.assertEqual(web.scripts[-1][0], mac_chrome.action_script('play'))
        for invalid in [-1, 4, 'library', None, True]:
            adapter.navigate(invalid)
        self.assertEqual(len(web.scripts), 4)

    def test_modal_blocks_navigation_search_and_transport(self):
        adapter, web, native = self.adapter()
        self.apply(adapter, {'section': 'library', 'modal': True, 'hasMedia': True})
        adapter.navigate(0)
        adapter.search('piano')
        adapter.action('play')
        adapter.focus_search()
        self.assertEqual(web.scripts, [])
        native.makeFirstResponder_.assert_not_called()
        adapter.outline.setEnabled_.assert_called_with(False)

    def test_busy_studio_disables_import_before_opening_a_panel(self):
        adapter, _, _ = self.adapter()
        adapter.on_import = Mock()
        adapter.toolbar_items['blaze.import'] = Mock()
        self.apply(adapter, {'section': 'studio', 'busy': True})
        adapter.toolbar_items['blaze.import'].setEnabled_.assert_called_once_with(False)
        # No AppKit import is needed when the panel is correctly blocked here.
        adapter.import_file()
        self.assertIsNone(adapter.panel)
        adapter.on_import.assert_not_called()

    def studio_adapter(self, collapsed=False):
        adapter, web, native = self.adapter()
        adapter.split, adapter.sidebar_item = Mock(), Mock()
        sidebar_state = [collapsed]
        adapter.sidebar_item.isCollapsed.side_effect = lambda: sidebar_state[0]
        adapter.sidebar_item.setCollapsed_.side_effect = lambda value: sidebar_state.__setitem__(0, value)
        items = [Mock(), adapter.search_item, Mock()]
        for item, name in zip(items, ('blaze.sidebar', 'blaze.search', 'blaze.import')):
            item.itemIdentifier.return_value = name
        toolbar = native.toolbar.return_value
        toolbar.items.side_effect = lambda: list(items)
        toolbar.removeItemAtIndex_.side_effect = lambda index: items.pop(index)
        toolbar.insertItemWithItemIdentifier_atIndex_.side_effect = lambda name, index: items.insert(index, adapter.toolbar_items[name])
        adapter.toolbar_items['blaze.search'] = adapter.search_item
        return adapter, web, native, sidebar_state

    def test_studio_workspace_collapses_once_and_restores_original_browse_chrome(self):
        for originally_collapsed in (False, True):
            with self.subTest(originally_collapsed=originally_collapsed):
                adapter, _, native, sidebar_state = self.studio_adapter(originally_collapsed)
                state = {'section': 'studio', 'studioWorkspace': True, 'appearance': 'light',
                         'nativeChromeInstalled': True}
                appearance = self.apply(adapter, state)
                self.assertTrue(sidebar_state[0])
                native.toolbar().removeItemAtIndex_.assert_called_once_with(1)
                native.setTitle_.assert_called_with('Blaze · Music Studio')
                appearance.appearanceNamed_.assert_called_with('DarkAqua')
                # A user can reopen the browse sidebar while editing. Polling
                # the web state must not repeatedly collapse it.
                sidebar_state[0] = False
                self.apply(adapter, state)
                self.assertFalse(sidebar_state[0])
                adapter.sidebar_item.setCollapsed_.assert_called_once_with(True)
                self.apply(adapter, dict(state, section='explore'))
                self.assertEqual(sidebar_state[0], originally_collapsed)
                native.toolbar().insertItemWithItemIdentifier_atIndex_.assert_called_once_with('blaze.search', 1)
                self.assertIs(native.toolbar().items()[1], adapter.search_item)
                native.setTitle_.assert_called_with('Blaze')
                self.assertEqual(adapter.appearance, 'light')
                self.assertFalse(adapter.studio_workspace)

    def test_studio_workspace_requires_explicit_capability_and_real_studio_section(self):
        adapter, _, native, _ = self.studio_adapter()
        for state in ({'section': 'studio'}, {'section': 'studio', 'studioWorkspace': 'true'},
                      {'section': 'explore', 'studioWorkspace': True}):
            self.apply(adapter, state)
        native.toolbar().removeItemAtIndex_.assert_not_called()
        adapter.sidebar_item.setCollapsed_.assert_not_called()

    def test_search_shortcut_leaves_studio_and_restores_the_same_search_field(self):
        adapter, web, native, sidebar_state = self.studio_adapter()
        self.apply(adapter, {'section': 'studio', 'studioWorkspace': True, 'nativeChromeInstalled': True})
        with patch.dict(sys.modules, {'AppKit': SimpleNamespace(NSWindowTitleVisible=0, NSWindowTitleHidden=1)}):
            adapter.focus_search()
        self.assertFalse(sidebar_state[0])
        self.assertFalse(adapter.studio_workspace)
        self.assertEqual(web.scripts[-1][0], mac_chrome.navigation_script('explore'))
        adapter.search_item.beginSearchInteraction.assert_called_once()
        native.makeFirstResponder_.assert_called_once_with(adapter.search_item.searchField())
        self.assertIs(native.toolbar().items()[1], adapter.search_item)

    def test_sync_is_authoritative_and_has_only_one_request_in_flight(self):
        adapter, web, native = self.adapter()
        adapter.sync()
        adapter.sync()
        self.assertTrue(adapter.evaluating)
        self.assertEqual(len(web.scripts), 1)
        with patch.dict(sys.modules, {'AppKit': SimpleNamespace(
                NSAppearance=Mock(), NSAppearanceNameAqua='Aqua', NSAppearanceNameDarkAqua='DarkAqua')}):
            web.scripts[0][1](json.dumps({'section': 'studio', 'appearance': 'dark', 'query': 'piano'}), None)
        adapter.select_section.assert_called_once_with('studio')
        native.setAppearance_.assert_called_once()
        self.assertEqual(adapter.receipt['selected'], 'studio')
        self.assertTrue(adapter.receipt['web_navigation'])
        self.assertFalse(adapter.evaluating)
        adapter.search_item.searchField().setStringValue_.assert_called_once_with('piano')

    def test_web_flags_only_installed_after_native_host_and_on_reload(self):
        adapter, web, _ = self.adapter()
        self.apply(adapter, {'section': 'explore'})
        self.assertEqual(web.scripts, [])
        adapter.split = Mock()
        self.apply(adapter, {'section': 'explore', 'nativeChromeInstalled': False})
        self.assertEqual(web.scripts, [(mac_chrome.INSTALL_SCRIPT, None)])
        self.apply(adapter, {'section': 'explore', 'nativeChromeInstalled': True})
        self.assertEqual(len(web.scripts), 1)

    def test_sync_preserves_native_text_selection_and_composition(self):
        adapter, _, _ = self.adapter()
        field = adapter.search_item.searchField()
        field.currentEditor.return_value = object()
        self.apply(adapter, {'section': 'explore', 'query': 'server state'})
        field.setStringValue_.assert_not_called()
        field.currentEditor.return_value = None
        self.apply(adapter, {'section': 'explore', 'query': 'server state'})
        field.setStringValue_.assert_called_once_with('server state')

    def test_fallback_requests_are_handled_once_per_counter(self):
        adapter, _, _ = self.adapter()
        adapter.import_file, adapter.focus_search = Mock(), Mock()
        state = {'section': 'explore', 'importRequest': 1, 'focusSearchRequest': 3}
        self.apply(adapter, state)
        self.apply(adapter, state)
        adapter.import_file.assert_called_once()
        adapter.focus_search.assert_called_once()

    def test_source_list_selection_does_not_trigger_a_second_navigation(self):
        adapter, _, _ = self.adapter()
        del adapter.select_section  # use actual method
        adapter.outline.selectedRow.return_value = 1
        index_set = SimpleNamespace(indexSetWithIndex_=lambda value: value)
        seen = []
        adapter.outline.selectRowIndexes_byExtendingSelection_.side_effect = lambda *args: seen.append(adapter.syncing_selection)
        with patch.dict(sys.modules, {'Foundation': SimpleNamespace(NSIndexSet=index_set)}):
            adapter.select_section('studio')
        adapter.outline.selectRowIndexes_byExtendingSelection_.assert_called_once_with(6, False)
        self.assertEqual(seen, [True])
        self.assertFalse(adapter.syncing_selection)
        self.assertEqual(adapter.selected, 'studio')
        self.assertEqual(mac_chrome.row_for_section('library'), 3)
        self.assertEqual(mac_chrome.row_for_section('group-browse'), -1)

    def test_late_callback_after_close_ignores_native_objects(self):
        adapter, web, _ = self.adapter()
        adapter.timer, adapter.target = Mock(), SimpleNamespace(owner=adapter)
        timer = adapter.timer
        adapter.sync()
        adapter.stop()
        timer.invalidate.assert_called_once()
        self.assertIsNone(adapter.target.owner)
        web.scripts[0][1](json.dumps({'section': 'studio'}), None)
        adapter.select_section.assert_not_called()
        adapter.navigate(0)
        adapter.sync()
        self.assertEqual(len(web.scripts), 1)

    def test_bad_and_not_ready_state_never_hides_web_navigation(self):
        adapter, web, _ = self.adapter()
        adapter.split = Mock()
        for state, error in [(None, None), ('broken', None), ('[]', None), ('{}', 'not loaded'),
                             ('null', None), ('{"section":"unknown"}', None)]:
            adapter.sync()
            web.scripts[-1][1](state, error)
            self.assertFalse(adapter.evaluating)
        self.assertTrue(all(script == mac_chrome.SYNC_SCRIPT for script, _ in web.scripts))
        self.assertNotIn('web_navigation', adapter.receipt)

    def test_lifecycle_attaches_after_loaded_not_shown_and_close_is_scheduled(self):
        events = SimpleNamespace(loaded=Event(), shown=Event(), closed=Event())
        helper = SimpleNamespace(callAfter=Mock())
        with patch.dict(sys.modules, {'PyObjCTools': SimpleNamespace(AppHelper=helper)}):
            adapter = mac_chrome.attach_navigation(SimpleNamespace(events=events), on_import=Mock())
        self.assertEqual(events.shown, [])
        self.assertEqual(len(events.loaded), 1)
        events.loaded[0]()
        callback = helper.callAfter.call_args.args[0]
        with patch.object(adapter, 'install') as install:
            callback()
        install.assert_called_once()
        events.closed[0]()
        helper.callAfter.assert_called_with(adapter.stop)

    def test_native_import_cancels_preparation_before_background_file_validation(self):
        adapter, web, _ = self.adapter()
        adapter.on_import = Mock()
        panel, helper = Mock(), SimpleNamespace(callAfter=Mock())
        private_path = '/Users/listener/Music/private title.wav'
        panel.URL().path.return_value = private_path
        appkit = SimpleNamespace(NSOpenPanel=SimpleNamespace(openPanel=Mock(return_value=panel)),
                                 NSModalResponseOK=1)
        with patch.dict(sys.modules, {'AppKit': appkit, 'PyObjCTools': SimpleNamespace(AppHelper=helper)}):
            adapter.import_file()
            panel.beginSheetModalForWindow_completionHandler_.assert_called_once()
            finish_panel = panel.beginSheetModalForWindow_completionHandler_.call_args.args[1]
            self.assertEqual(web.scripts, [])
            finish_panel(1)
            self.assertTrue(adapter.importing)
            self.assertEqual(web.scripts[-1][0], 'JSON.stringify(window.BlazeMac?.beginImport() === true)')
            adapter.on_import.assert_not_called()
            # No second picker/validation can race the first selected file.
            adapter.import_file()
            appkit.NSOpenPanel.openPanel.assert_called_once()
            with patch.object(mac_chrome.threading, 'Thread') as thread:
                web.scripts[-1][1]('true', None)
            thread.assert_called_once()
            self.assertTrue(thread.call_args.kwargs['daemon'])
            thread.return_value.start.assert_called_once()
            adapter.on_import.assert_not_called()
            thread.call_args.kwargs['target']()
            adapter.on_import.assert_called_once_with(private_path)
            helper.callAfter.assert_called_once_with(adapter._import_finished, None)
            helper.callAfter.call_args.args[0](None)
        self.assertFalse(adapter.importing)
        self.assertEqual(web.scripts[-1][0], 'window.BlazeMac?.importCompleted()')
        self.assertTrue(all(private_path not in script for script, _ in web.scripts))

    def test_import_requires_explicit_web_preparation_confirmation(self):
        adapter, web, _ = self.adapter()
        adapter.on_import, adapter._import_finished = Mock(), Mock()
        panel = Mock()
        appkit = SimpleNamespace(NSOpenPanel=SimpleNamespace(openPanel=Mock(return_value=panel)),
                                 NSModalResponseOK=1)
        with patch.dict(sys.modules, {'AppKit': appkit,
                                    'PyObjCTools': SimpleNamespace(AppHelper=Mock())}):
            adapter.import_file()
            panel.beginSheetModalForWindow_completionHandler_.call_args.args[1](1)
            web.scripts[-1][1]('false', None)
        adapter.on_import.assert_not_called()
        adapter._import_finished.assert_called_once_with('Finish the current action before opening a file.')


if __name__ == '__main__':
    unittest.main()
