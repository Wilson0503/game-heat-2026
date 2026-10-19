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


class Scene(E2E):
    def test_layout_from_order(self):
        p = self.open()
        lay = p.evaluate("GH.scene.layout")
        order = [r["slug"] for r in sorted(SITE["rooms"], key=lambda r: r["order"])]
        doors = [x for x in lay if "slug" in x]
        self.assertEqual([(d["station"], d["side"]) for d in doors],
                         [(1, "left"), (1, "right"), (2, "left"), (2, "right"), (3, "left"), (3, "right")])
        self.assertEqual([d["slug"] for d in doors], order)
        self.assertEqual({x["special"] for x in lay if "special" in x}, {"spectators", "graffiti"})

    def test_door_plate_and_glow(self):
        p = self.open()
        for r in SITE["rooms"]:
            top = min((g for g in SITE["games"] if g["room_slug"] == r["slug"] and g["room_rank"]), key=lambda g: g["room_rank"])
            plate = p.inner_text(f'.door[data-room="{r["slug"]}"] .plate')
            self.assertIn(r["name"], plate); self.assertIn(top["name"], plate)
            glow = p.evaluate(f'getComputedStyle(document.querySelector(\'.door[data-room="{r["slug"]}"]\')).getPropertyValue("--glow")')
            self.assertAlmostEqual(float(glow), r["glow"], places=3)

    def test_doors_are_buttons(self):
        p = self.open()
        self.assertEqual(p.eval_on_selector_all(".door", "els => els.every(e => e.tagName === 'BUTTON')"), True)

    def test_deep_link_room(self):
        p = self.open("#room=action&game=gtav")
        self.assertTrue(p.is_visible('.room[data-room="action"]'))
        self.assertIn("is-open", p.get_attribute('.room[data-room="action"] .card[data-id="gtav"]', "class"))

    def test_turn_back_and_history(self):
        p = self.open()
        p.evaluate("GH.go({room:'shooter'})")
        p.wait_for_selector('.room[data-room="shooter"]:not([hidden])')
        p.click("#turn-back")
        p.wait_for_function("GH.state.room === null")
        p.evaluate("GH.go({room:'strategy'})")
        p.go_back()
        p.wait_for_function("GH.state.room === null")
        order = next(r["order"] for r in SITE["rooms"] if r["slug"] == "strategy")
        self.assertEqual(p.evaluate("GH.scene.station"), (order + 1) // 2)

    def test_room_themes_present(self):
        p = self.open()
        for slug in ("shooter", "rpg", "sim", "strategy", "casual", "action"):
            self.assertEqual(p.locator(f'.room[data-room="{slug}"].theme--{slug}').count(), 1)


class Input(E2E):
    def test_keyboard_walk_and_open(self):
        p = self.open()
        p.keyboard.press("w"); p.wait_for_function("GH.scene.station === 1 && !document.body.classList.contains('is-moving')")
        p.keyboard.press("a"); self.assertEqual(p.evaluate("GH.scene.facing"), "left")
        p.keyboard.down("e"); p.wait_for_timeout(700); p.keyboard.up("e")
        first = sorted(SITE["rooms"], key=lambda r: r["order"])[0]["slug"]
        p.wait_for_function(f"GH.state.room === '{first}'")
        p.keyboard.press("Escape"); p.wait_for_function("GH.state.room === null")

    def test_short_hold_does_not_open(self):
        p = self.open()
        p.keyboard.press("w"); p.keyboard.press("d")
        p.keyboard.down("e"); p.wait_for_timeout(300); p.keyboard.up("e")
        p.wait_for_timeout(500)
        self.assertIsNone(p.evaluate("GH.state.room"))
        self.assertEqual(p.evaluate("getComputedStyle(document.querySelector('.hold-ring')).getPropertyValue('--p').trim() || '0'"), "0")

    def test_enter_opens_immediately(self):
        p = self.open()
        p.keyboard.press("ArrowUp"); p.keyboard.press("ArrowRight"); p.keyboard.press("Enter")
        second = sorted(SITE["rooms"], key=lambda r: r["order"])[1]["slug"]
        p.wait_for_function(f"GH.state.room === '{second}'")

    def test_rapid_moves_settle(self):
        p = self.open()
        for _ in range(6): p.keyboard.press("w")
        p.wait_for_function("!document.body.classList.contains('is-moving')")
        self.assertEqual(p.evaluate("GH.scene.station"), 4)
        for _ in range(9): p.keyboard.press("s")
        p.wait_for_function("!document.body.classList.contains('is-moving')")
        self.assertEqual(p.evaluate("GH.scene.station"), 0)

    def test_swipe_and_long_press_mobile(self):
        p = self.open(mobile=True)
        drag = lambda x0, y0, x1, y1: (p.mouse.move(x0, y0), p.mouse.down(), p.mouse.move(x1, y1, steps=5), p.mouse.up())
        drag(187, 600, 187, 400)  # 上滑 = 前進
        p.wait_for_function("GH.scene.station === 1")
        drag(300, 400, 80, 400)   # 左滑 = 轉向左門
        self.assertEqual(p.evaluate("GH.scene.facing"), "left")
        drag(80, 400, 300, 400)   # 右滑 = 轉回正面
        self.assertEqual(p.evaluate("GH.scene.facing"), "front")
        self.assertIsNone(p.evaluate("GH.state.room"), "滑動不會順便開門")
        # 長按：Playwright 的 mouse 產生的是 pointerType "mouse"，所以直接送觸控指標事件
        p.evaluate("GH.scene.turn('left')")
        door = ".door--left:not([hidden])"
        touch = lambda typ, pid: p.dispatch_event(door, typ, {"pointerType": "touch", "pointerId": pid, "isPrimary": True,
                                                             "clientX": 100, "clientY": 400, "bubbles": True})
        touch("pointerdown", 7); p.wait_for_timeout(300); touch("pointerup", 7)
        p.wait_for_timeout(400); self.assertIsNone(p.evaluate("GH.state.room"), "短按不開門")
        touch("pointerdown", 8); p.wait_for_timeout(700)
        p.wait_for_function("GH.state.room !== null")
        touch("pointerup", 8)

    def test_first_tab_reaches_skip_link(self):
        p = self.open()
        p.keyboard.press("Tab")
        self.assertEqual(p.evaluate("document.activeElement.className"), "skip")
        self.assertFalse(p.is_visible("#scoreboard"))
        p.keyboard.press("Enter"); p.wait_for_function("GH.state.view === 'plan'")


if __name__ == "__main__":
    unittest.main()
