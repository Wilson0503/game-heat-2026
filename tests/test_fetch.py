# tests/test_fetch.py
import json, tempfile, unittest
from pathlib import Path
from tools import fetch_data as f

FIX = Path(__file__).parent / "fixtures"

class Parse(unittest.TestCase):
    def test_steamcharts(self):
        out = f.parse_steamcharts((FIX / "steamcharts_730.html").read_text(encoding="utf-8"))
        self.assertEqual(out["Last 30 Days"], {"avg": 1000.5, "peak": 1450000})
        self.assertEqual(out["September 2026"], {"avg": 900.25, "peak": 1400000})
    def test_bot_wall(self):
        self.assertTrue(f.is_bot_wall(403, "<title>Just a moment...</title>"))
        self.assertTrue(f.is_bot_wall(200, "cf-chl-bypass challenge-platform"))
        self.assertFalse(f.is_bot_wall(200, '{"ok":1}'))
    def test_fortnite_now_uses_in_match(self):
        # 當下與 24 小時峰值都取「對戰中」口徑，和每日峰值序列一致；不能取 online
        out = f.parse_fortnite_now((FIX / "fortnitegg_now.html").read_text(encoding="utf-8"))
        self.assertEqual(out, {"now": 523661, "peak_24h": 1893160})
        self.assertEqual(f.parse_fortnite_now("<html></html>"), {"now": None, "peak_24h": None})
    def test_rolimons_sum(self):
        payload = {"success": True, "games": {"1": ["A", 10, 0], "2": ["B", 5, 0]}}
        self.assertEqual(f.sum_rolimons(payload), 15)
        self.assertIsNone(f.sum_rolimons({"success": False}))

class Archive(unittest.TestCase):
    def test_moves_known_files(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "steamcharts_monthly.json").write_text("{}", encoding="utf-8")
            (d / "manual.json").write_text("{}", encoding="utf-8")
            dest = f.archive(d, "20261019-1513")
            self.assertTrue((dest / "steamcharts_monthly.json").exists())
            self.assertFalse((d / "steamcharts_monthly.json").exists())
            self.assertTrue((d / "manual.json").exists(), "人工檔不可被歸檔")
    def test_nothing_to_archive(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(f.archive(Path(d), "x"))

class Isolation(unittest.TestCase):
    def test_one_source_failure_does_not_stop_others(self):
        log = {}
        def ok(): return {"a.json": {"v": 1}}
        def boom(): raise RuntimeError("HTTP 500")
        with tempfile.TemporaryDirectory() as d:
            f.run_sources(Path(d), [("good", "u1", ok), ("bad", "u2", boom)], log)
            self.assertTrue(log["good"]["ok"]); self.assertFalse(log["bad"]["ok"])
            self.assertIn("HTTP 500", log["bad"]["error"])
            self.assertEqual(json.loads((Path(d) / "a.json").read_text(encoding="utf-8")), {"v": 1})

if __name__ == "__main__":
    unittest.main()
