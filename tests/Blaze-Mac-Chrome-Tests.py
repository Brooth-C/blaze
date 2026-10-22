"""Native adapter contracts that run without a macOS framework installation."""
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
        self.children = children
        self.evaluator = evaluator
        self.scripts = []

    def respondsToSelector_(self, selector):
        return self.evaluator and selector == 'evaluateJavaScript:completionHandler:'

    def subviews(self):
        return self.children

    def evaluateJavaScript_completionHandler_(self, script, callback):
        self.scripts.append((script, callback))


class MacChromeTests(unittest.TestCase):
    def test_navigation_is_a_fixed_product_allowlist(self):
        for section in mac_chrome.SECTIONS:
            script = mac_chrome.navigation_script(section)
            self.assertEqual(script, 'window.BlazeDesktop?.selectSection(' + json.dumps(section) + ')')
            self.assertNotIn('eval(', script)
        for invalid in [None, 1, '', 'settings', 'explore);fetch("https://example.com")']:
            with self.subTest(value=invalid), self.assertRaises(ValueError):
                mac_chrome.navigation_script(invalid)

    def test_webview_is_found_without_a_private_pywebview_registry(self):
        web = View(evaluator=True)
        root = View([View(), View([web])])
        self.assertIs(mac_chrome.find_webview(root), web)
        self.assertIsNone(mac_chrome.find_webview(View()))
        self.assertIsNone(mac_chrome.find_webview(None))

    def test_missing_mac26_class_is_a_normal_runtime_fallback(self):
        self.assertIsNone(mac_chrome.glass_class(SimpleNamespace()))
        cls = object()
        self.assertIs(mac_chrome.glass_class(SimpleNamespace(NSGlassEffectView=cls)), cls)

    def test_main_thread_is_required_before_appkit_import(self):
        errors = []

        def worker():
            try:
                mac_chrome.MacNavigation(None).install()
            except RuntimeError as error:
                errors.append(str(error))

        thread = threading.Thread(target=worker)
        thread.start()
        thread.join()
        self.assertEqual(errors, ['Native navigation must be installed on the Cocoa main thread.'])

    def adapter(self):
        web = View(evaluator=True)
        native = Mock()
        native.contentView.return_value = View([web])
        adapter = mac_chrome.MacNavigation(SimpleNamespace(native=native))
        adapter.native = native
        adapter.control = Mock()
        return adapter, web, native

    def test_native_actions_route_to_the_existing_web_application(self):
        adapter, web, _ = self.adapter()
        adapter.navigate(2)
        self.assertEqual(web.scripts, [(mac_chrome.navigation_script('library'), None)])
        for invalid in [-1, 4, 'library', None]:
            adapter.navigate(invalid)
        self.assertEqual(len(web.scripts), 1)

    def test_sync_reads_authoritative_selection_and_appearance(self):
        adapter, web, native = self.adapter()
        appearance = Mock()
        appkit = SimpleNamespace(NSAppearance=appearance, NSAppearanceNameAqua='Aqua', NSAppearanceNameDarkAqua='DarkAqua')
        adapter.sync()
        self.assertTrue(adapter.evaluating)
        adapter.sync()
        self.assertEqual(len(web.scripts), 1, 'Only one probe may be in flight.')
        with patch.dict(sys.modules, {'AppKit': appkit}):
            web.scripts[0][1](json.dumps({'section': 'studio', 'appearance': 'dark'}), None)
        adapter.control.setSelectedSegment_.assert_called_once_with(3)
        appearance.appearanceNamed_.assert_called_once_with('DarkAqua')
        native.setAppearance_.assert_called_once_with(appearance.appearanceNamed_.return_value)
        self.assertTrue(adapter.receipt['web_navigation'])
        self.assertEqual(adapter.receipt['selected'], 'studio')
        self.assertFalse(adapter.evaluating)

    def test_late_callback_after_close_does_not_touch_native_objects(self):
        adapter, web, _ = self.adapter()
        adapter.timer, adapter.target = Mock(), SimpleNamespace(owner=adapter)
        timer = adapter.timer
        adapter.sync()
        adapter.stop()
        timer.invalidate.assert_called_once()
        self.assertIsNone(adapter.target.owner)
        web.scripts[0][1](json.dumps({'section': 'studio'}), None)
        adapter.control.setSelectedSegment_.assert_not_called()
        adapter.navigate(0)
        adapter.sync()
        self.assertEqual(len(web.scripts), 1)

    def test_bad_or_not_ready_web_state_never_hides_navigation_early(self):
        adapter, web, _ = self.adapter()
        for state, error in [(None, None), ('broken', None), ('[]', None), ('{}', 'not loaded')]:
            adapter.sync()
            web.scripts[-1][1](state, error)
            self.assertFalse(adapter.evaluating)
        adapter.control.setSelectedSegment_.assert_not_called()
        self.assertNotIn('web_navigation', adapter.receipt)


if __name__ == '__main__':
    unittest.main()
