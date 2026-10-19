# tests/test_copy.py
import json, unittest
from tools import check_copy as c

class Lint(unittest.TestCase):
    def test_meme_needs_paraphrase_mark(self):
        self.assertTrue(any("社群梗缺「（轉述）」" in e for e in c.lint_game("x", {"intro": "a", "why_hot": "b", "memes": ["「哈」"], "editor_note": "c", "source": "claude"})))
    def test_banned_words(self):
        errs = c.lint_game("x", {"intro": "史詩級神作", "why_hot": "b", "memes": [], "editor_note": "c", "source": "claude"})
        self.assertTrue(any("誇飾" in e for e in errs))
    def test_hand_written_numbers(self):
        errs = c.lint_text("x", "有 119 萬人")
        self.assertTrue(any("手寫數字" in e for e in errs))
        self.assertEqual(c.lint_text("x", "有 {now:730} 人，Dota 2 與 CS2"), [])
    def test_placeholders(self):
        self.assertTrue(c.lint_text("x", "【此處待作者補充個人私房體驗】"))
        self.assertTrue(c.lint_text("x", "（⚠️請核對時間與細節）"))
    def test_intro_length(self):
        self.assertTrue(any("40" in e for e in c.lint_game("x", {"intro": "字" * 41, "why_hot": "b", "memes": [], "editor_note": "c", "source": "claude"})))
    def test_bad_placeholder_field(self):
        self.assertTrue(c.lint_text("x", "{dau:730}"))

class Real(unittest.TestCase):
    def test_real_copy_is_clean_and_complete(self):
        errs = c.check(json.load(open("data/copy.json", encoding="utf-8")),
                       json.load(open("data/site_data.json", encoding="utf-8")))
        self.assertEqual(errs, [], "\n".join(errs))

if __name__ == "__main__":
    unittest.main()
