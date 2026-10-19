# tests/test_e2e.py
import json, unittest
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
URL = (ROOT / "index.html").as_uri()
SITE = json.loads((ROOT / "data" / "site_data.json").read_text(encoding="utf-8"))
SHOTS = ROOT / "screenshots"


class E2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch(channel="msedge")

    @classmethod
    def tearDownClass(cls):
        cls.browser.close(); cls.pw.stop()

    def open(self, hash="", mobile=False, reduced=False):
        opts = dict(viewport={"width": 375, "height": 812}, has_touch=True, is_mobile=True, device_scale_factor=2) \
            if mobile else dict(viewport={"width": 1440, "height": 900})
        ctx = self.browser.new_context(reduced_motion="reduce" if reduced else "no-preference", **opts)
        page = ctx.new_page()
        self.requests, self.errors = [], []
        page.on("request", lambda r: self.requests.append(r.url))
        page.on("console", lambda m: m.type == "error" and self.errors.append(m.text))
        page.on("pageerror", lambda e: self.errors.append(str(e)))
        page.goto(URL + hash)
        page.wait_for_function("window.GH && GH.ready === true")
        self.addCleanup(ctx.close)
        return page


class Skeleton(E2E):
    def test_loads_offline_without_errors(self):
        p = self.open()
        self.assertEqual([u for u in self.requests if not u.startswith("file:")], [])
        self.assertEqual(self.errors, [])
        self.assertEqual(p.get_attribute("html", "lang"), "zh-Hant")

    def test_fmt(self):
        p = self.open()
        self.assertEqual(p.evaluate("GH.fmt.num(null)"), "⚠️ 待查")
        self.assertEqual(p.evaluate("GH.fmt.num(2859426)"), "285.9 萬")
        self.assertEqual(p.evaluate("GH.fmt.num(8123)"), "8,123")
        self.assertEqual(p.evaluate("GH.fmt.fill('有 {rank:730} 名')"), f"有 {next(g['rank'] for g in SITE['games'] if g['id']=='730')} 名")

    def test_hash_roundtrip(self):
        p = self.open()
        self.assertEqual(p.evaluate("GH.hash.parse('#room=shooter&game=730')"), {"view": "walk", "room": "shooter", "game": "730"})
        self.assertEqual(p.evaluate("GH.hash.parse('#view=plan')"), {"view": "plan", "room": None, "game": None})
        self.assertEqual(p.evaluate("GH.hash.serialize({view:'walk',room:'action',game:'gtav'})"), "#room=action&game=gtav")
        self.assertEqual(p.evaluate("GH.hash.serialize({view:'walk',room:null,game:null})"), "#")

    def test_invalid_hash_falls_back(self):
        p = self.open()
        self.assertEqual(p.evaluate("GH.hash.parse('#room=xyz&game=730')"), {"view": "walk", "room": None, "game": None})
        self.assertEqual(p.evaluate("GH.hash.parse('#room=shooter&game=nope')"), {"view": "walk", "room": "shooter", "game": None})
        self.assertEqual(p.evaluate("GH.hash.parse('#room=strategy&game=730')"), {"view": "walk", "room": "strategy", "game": None},
                         "遊戲不在該房間時只保留房間")

    def test_size_budget(self):
        self.assertLess((ROOT / "index.html").stat().st_size, 400 * 1024)


if __name__ == "__main__":
    unittest.main()
