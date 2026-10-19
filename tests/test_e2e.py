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


class Plan(E2E):
    def ranked_in(self, slug):
        return sorted([g for g in SITE["games"] if g["room_slug"] == slug and g["room_rank"] and g["room_rank"] <= 5],
                      key=lambda g: g["room_rank"])

    def test_plan_shows_all_rooms_in_order(self):
        p = self.open("#view=plan")
        self.assertTrue(p.is_visible("#plan"))
        slugs = p.eval_on_selector_all("#plan section[data-room]", "els => els.map(e => e.dataset.room)")
        self.assertEqual(slugs, [r["slug"] for r in sorted(SITE["rooms"], key=lambda r: r["order"])])
        for r in SITE["rooms"]:
            ids = p.eval_on_selector_all(f'#plan section[data-room="{r["slug"]}"] .room-top .card', "els => els.map(e => e.dataset.id)")
            self.assertEqual(ids, [g["id"] for g in self.ranked_in(r["slug"])])

    def test_every_number_has_context(self):
        p = self.open("#view=plan")
        bad = p.evaluate("""[...document.querySelectorAll('#plan .card')].filter(c =>
            !c.querySelector('.badge') || !c.querySelector('.meta .basis')).map(c => c.dataset.id)""")
        self.assertEqual(bad, [])

    def test_no_nan_or_null_text(self):
        p = self.open("#view=plan")
        text = p.inner_text("#plan")
        for bad in ("NaN", "null", "undefined", "【此處待作者補充", "⚠️請核對"):
            self.assertNotIn(bad, text)

    def test_retention_tag_has_time(self):
        p = self.open("#view=plan")
        missing = p.evaluate("""[...document.querySelectorAll('#plan .tag--retention')].filter(t =>
            !/\\d{4}\\/\\d{2}\\/\\d{2} \\d{2}:\\d{2}/.test(t.getAttribute('title') || '')).length""")
        self.assertEqual(missing, 0)

    def test_memes_marked_paraphrase(self):
        p = self.open("#view=plan")
        memes = p.eval_on_selector_all("#plan .meme", "els => els.map(e => e.textContent.trim())")
        self.assertTrue(memes)
        self.assertTrue(all(m.endswith("（轉述）") for m in memes))

    def test_flip_card(self):
        p = self.open("#view=plan")
        first = p.locator("#plan .room-top .card").first
        first.click()
        self.assertIn("is-open", first.get_attribute("class"))
        self.assertEqual(p.locator("#plan .card.is-open").count(), 1)
        first.click()
        self.assertEqual(p.locator("#plan .card.is-open").count(), 0)

    def test_spectators_roblox_and_overrides(self):
        p = self.open("#view=plan")
        spec = p.inner_text("#plan-spectators")
        for g in SITE["games"]:
            if g["status"] == "spectator":
                self.assertIn(g["name"], spec)
        self.assertIn("熱度高，不代表適合每個人。人少，也不代表遊戲已死。", spec)
        rules_text = p.inner_text("#plan-rules")
        self.assertIn("PUBG", rules_text); self.assertIn("候選", rules_text)
        self.assertIn("口徑不同，不參與排名", p.inner_text("#plan"))

    def test_vote_is_local_only(self):
        p = self.open("#view=plan")
        p.locator("#plan-graffiti button").first.click()
        self.assertIn("只記在你的瀏覽器", p.inner_text("#plan-graffiti"))
        self.assertIsNotNone(p.evaluate("localStorage.getItem('gh.vote')"))


if __name__ == "__main__":
    unittest.main()
