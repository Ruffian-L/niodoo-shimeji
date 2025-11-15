import unittest

from modules.speech_bubble import SpeechBubbleOverlay, ensure_clipboard_permission


class DummyMemoryManager:
    def __init__(self, pref="ask"):
        self.pref = pref
        self.set_calls = []

    def get_pref(self, key, default=None):
        return self.pref

    def set_pref(self, key, value):
        self.pref = value
        self.set_calls.append((key, value))

class TestOverlay(unittest.TestCase):
    def test_start_stop(self):
        overlay = SpeechBubbleOverlay()
        overlay.start()
        overlay.stop()


class TestClipboardConsent(unittest.TestCase):
    def test_pref_allow_skips_prompt(self):
        memory = DummyMemoryManager(pref="allow")
        def fail_prompt():  # pragma: no cover - should never run
            raise AssertionError("Prompt should not be invoked when pref=allow")
        allowed, final_pref = ensure_clipboard_permission(memory, fail_prompt)
        self.assertTrue(allowed)
        self.assertEqual(final_pref, "allow")
        self.assertEqual(memory.set_calls, [])

    def test_pref_deny_skips_prompt(self):
        memory = DummyMemoryManager(pref="deny")
        def fail_prompt():  # pragma: no cover - should never run
            raise AssertionError("Prompt should not be invoked when pref=deny")
        allowed, final_pref = ensure_clipboard_permission(memory, fail_prompt)
        self.assertFalse(allowed)
        self.assertEqual(final_pref, "deny")

    def test_prompt_persists_allow(self):
        memory = DummyMemoryManager(pref="ask")
        prompt_calls = []
        def prompt():
            prompt_calls.append(True)
            return True, True
        allowed, final_pref = ensure_clipboard_permission(memory, prompt)
        self.assertTrue(allowed)
        self.assertEqual(final_pref, "allow")
        self.assertEqual(memory.pref, "allow")
        self.assertEqual(memory.set_calls, [("clipboard_consent", "allow")])
        self.assertEqual(len(prompt_calls), 1)

    def test_prompt_persists_deny(self):
        memory = DummyMemoryManager(pref="ask")
        allowed, final_pref = ensure_clipboard_permission(memory, lambda: (False, True))
        self.assertFalse(allowed)
        self.assertEqual(final_pref, "deny")
        self.assertEqual(memory.pref, "deny")

    def test_prompt_without_remember(self):
        memory = DummyMemoryManager(pref="ask")
        allowed, final_pref = ensure_clipboard_permission(memory, lambda: (False, False))
        self.assertFalse(allowed)
        self.assertEqual(final_pref, "ask")
        self.assertEqual(memory.set_calls, [])
