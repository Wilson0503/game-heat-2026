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


class Hud(E2E):
    def test_tab_hold_shows_scoreboard(self):
        p = self.open()
        p.keyboard.press("a")  # 先有一次操作；載入後第一次 Tab 會落到「切換到樓層導覽圖」
        p.keyboard.down("Tab"); self.assertTrue(p.is_visible("#scoreboard"))
        rows = p.eval_on_selector_all("#scoreboard tbody tr[data-id]", "els => els.map(e => e.dataset.id)")
        self.assertEqual(rows, [g["id"] for g in sorted([g for g in SITE["games"] if g["rank"] and g["rank"] <= 10], key=lambda g: g["rank"])])
        self.assertIn("口徑不同，不參與排名", p.inner_text("#scoreboard"))
        p.keyboard.up("Tab"); self.assertFalse(p.is_visible("#scoreboard"))

    def test_mobile_toggle(self):
        p = self.open(mobile=True)
        p.tap("#sb-toggle"); self.assertTrue(p.is_visible("#scoreboard"))
        self.assertEqual(p.get_attribute("#sb-toggle", "aria-expanded"), "true")
        p.tap("#sb-toggle"); self.assertFalse(p.is_visible("#scoreboard"))
        box = p.locator("#sb-toggle").bounding_box()
        self.assertGreaterEqual(min(box["width"], box["height"]), 44)

    def test_scoreboard_click_goes_to_game(self):
        p = self.open()
        p.keyboard.press("a"); p.keyboard.down("Tab")  # 桌機沒有計分板按鈕，按住 Tab
        g = min((g for g in SITE["games"] if g["rank"]), key=lambda g: g["rank"])
        p.click(f'#scoreboard tr[data-id="{g["id"]}"] button')
        p.keyboard.up("Tab")
        p.wait_for_function(f"GH.state.room === '{g['room_slug']}' && GH.state.game === '{g['id']}'")
        self.assertFalse(p.is_visible("#scoreboard"))

    def test_minimap_jump_and_visited(self):
        p = self.open()
        p.click('#minimap button[data-room="sim"]')
        p.wait_for_function("GH.state.room === 'sim'")
        p.click("#turn-back"); p.wait_for_function("GH.state.room === null")
        self.assertIn("visited", p.get_attribute('#minimap button[data-room="sim"]', "class"))
        self.assertIn("sim", p.evaluate("JSON.parse(localStorage.getItem('gh.visited'))"))

    def test_killfeed_static_and_clickable(self):
        p = self.open()
        kills = p.locator("#killfeed .kill")
        self.assertTrue(3 <= kills.count() <= 4)
        before = p.inner_text("#killfeed"); p.wait_for_timeout(3000); self.assertEqual(before, p.inner_text("#killfeed"), "不自動輪播")
        kills.first.click()
        p.wait_for_function("GH.state.room !== null || document.querySelector('#scene').classList.contains('in-room')")

    def test_minimap_plan_toggle(self):
        p = self.open()
        p.click("#minimap .to-plan"); p.wait_for_function("GH.state.view === 'plan'")
        self.assertTrue(p.is_visible("#plan"))
        p.keyboard.press("Tab")
        self.assertFalse(p.is_visible("#scoreboard"), "導覽圖裡 Tab 是正常焦點移動")

class Acceptance(E2E):
    def test_embedded_matches_site_data(self):
        p = self.open()
        self.assertEqual(p.evaluate("GH.data.games.length"), len(SITE["games"]))
        self.assertEqual(p.evaluate("GH.data.games.map(g => g.id + ':' + g.rank).join(',')"),
                         ",".join(f"{g['id']}:{g['rank'] if g['rank'] is not None else 'null'}" for g in SITE["games"]))

    def test_each_game_in_one_room(self):
        p = self.open("#view=plan")
        ids = p.eval_on_selector_all("#plan section[data-room] .card", "els => els.map(e => e.dataset.id)")
        self.assertEqual(len(ids), len(set(ids)))

    def test_reduced_motion_defaults_to_plan(self):
        p = self.open(reduced=True)
        self.assertTrue(p.is_visible("#plan"))
        self.assertEqual(p.evaluate("getComputedStyle(document.querySelector('.world')).transitionDuration"), "0s")

    def test_all_hash_states(self):
        for h, check in [("#", "GH.state.room === null && GH.state.view === 'walk'"),
                         ("#room=shooter", "GH.state.room === 'shooter'"),
                         ("#room=shooter&game=730", "GH.state.game === '730'"),
                         ("#view=plan", "GH.state.view === 'plan'")]:
            p = self.open(h); p.wait_for_function(check)

    def test_no_horizontal_scroll_mobile(self):
        for h in ("#", "#view=plan", "#room=action", "#room=shooter&game=730"):
            p = self.open(h, mobile=True); p.wait_for_timeout(700)
            over = p.evaluate("""[document.documentElement, ...document.querySelectorAll('.room:not([hidden]), #plan')]
                .some(e => e.scrollWidth > e.clientWidth + 1)""")
            self.assertFalse(over, h)

    def test_touch_targets(self):
        p = self.open(mobile=True)
        sel = "#sb-toggle, #turn-back, #mm-toggle, .kill, .mm-cell, .to-plan, .vote, .linkish"
        count = lambda: p.evaluate(f"""[...document.querySelectorAll('{sel}')].filter(e => e.offsetParent)
            .map(e => e.getBoundingClientRect()).filter(r => r.width < 44 || r.height < 44).length""")
        self.assertEqual(count(), 0)
        p.tap("#mm-toggle"); self.assertEqual(count(), 0, "展開後的小地圖格子也要 44 px")
        p = self.open("#view=plan", mobile=True); self.assertEqual(count(), 0)

    def test_open_card_keeps_siblings_in_view(self):
        p = self.open("#room=shooter&game=730"); p.wait_for_timeout(800)
        tops = p.eval_on_selector_all(".room:not([hidden]) .stage .card", "els => els.map(e => e.getBoundingClientRect().top)")
        self.assertTrue(tops and max(tops) < 900 * 0.6, tops)

    def test_hint_matches_device(self):
        self.assertIn("按住 E", self.open().inner_text(".hint"))
        m = self.open(mobile=True).inner_text(".hint")
        self.assertIn("滑", m); self.assertNotIn("Tab", m)

    def test_screenshots(self):
        SHOTS.mkdir(exist_ok=True)
        cases = ["#", "#room=shooter", "#room=strategy", "#room=sim", "#room=casual", "#room=rpg", "#room=action",
                 "#room=shooter&game=730", "#view=plan"]
        for mobile in (False, True):
            for h in cases:
                p = self.open(h, mobile=mobile); p.wait_for_timeout(800)
                name = (h.strip("#").replace("=", "-").replace("&", "_") or "spawn") + ("-mobile" if mobile else "-desktop")
                p.screenshot(path=str(SHOTS / f"{name}.png"), full_page=(h == "#view=plan"))
        p = self.open(); p.keyboard.press("a"); p.keyboard.down("Tab"); p.screenshot(path=str(SHOTS / "scoreboard-desktop.png"))  # 載入後第一次 Tab 落到跳過連結; p.keyboard.up("Tab")
        self.assertEqual(self.errors, [])

class Polish(E2E):
    def face(self, p, x):
        p.evaluate(f"GH.scene.station = {x['station']}; GH.scene.facing = '{x['side']}'; GH.scene.render(false)")

    def test_every_door_visible_when_faced(self):
        p = self.open()
        for x in p.evaluate("GH.scene.layout"):
            sel = f'.door[data-room="{x["slug"]}"]' if x.get("slug") else f'.door[data-special="{x["special"]}"]'
            self.face(p, x); p.wait_for_timeout(50)
            hit = p.evaluate("""sel => { const d = document.querySelector(sel), r = d.getBoundingClientRect();
                const cx = Math.min(Math.max(r.left + r.width / 2, 1), innerWidth - 1), cy = Math.min(Math.max(r.top + r.height / 2, 1), innerHeight - 1);
                const e = document.elementFromPoint(cx, cy); return !!e && e.closest('.door') === d; }""", sel)
            self.assertTrue(hit, sel + " 面對時要看得到，不能被牆蓋住")

    def test_plan_back_to_corridor(self):
        for kw in ({"hash": "#view=plan"}, {"reduced": True}):
            p = self.open(**kw)
            p.click("#plan .plan-back")
            p.wait_for_function("GH.state.view === 'walk' && GH.state.room === null")
            self.assertTrue(p.is_visible("#scene")); self.assertFalse(p.is_visible("#plan"))

    def test_plan_enter_room(self):
        p = self.open("#view=plan")
        p.click('#plan section[data-room="casual"] .plan-enter')
        p.wait_for_function("GH.state.room === 'casual' && document.body.classList.contains('in-room')")
        self.assertTrue(p.is_visible('.room[data-room="casual"]'))

    def test_tab_tip_persistent_on_desktop(self):
        p = self.open()
        self.assertTrue(p.is_visible("#tab-tip"))
        t = p.inner_text("#tab-tip"); self.assertIn("Tab", t); self.assertIn("總計分板", t)
        p.keyboard.press("w"); p.wait_for_timeout(500)
        self.assertTrue(p.is_visible("#tab-tip"), "操作過後提示仍要在")
        p.evaluate("GH.go({room:'shooter'}, {animate:false})")
        self.assertTrue(p.is_visible("#tab-tip"), "房間裡也能按 Tab")
        p = self.open("#view=plan"); self.assertFalse(p.is_visible("#tab-tip"), "導覽圖裡 Tab 是焦點移動")
        p = self.open(mobile=True); self.assertFalse(p.is_visible("#tab-tip"))
        self.assertIn("總計分板", p.inner_text("#sb-toggle"))

    def test_door_opening_effect(self):
        p = self.open()
        self.face(p, {"station": 1, "side": "left"})
        p.click('.door[data-room="shooter"]')
        p.wait_for_selector('.door[data-room="shooter"].is-opening', timeout=400)
        self.assertGreater(p.locator('.door[data-room="shooter"] .spark').count(), 0)
        p.wait_for_function("document.body.classList.contains('in-room')")
        p.click("#turn-back"); p.wait_for_function("GH.state.room === null")
        self.assertEqual(p.locator(".door.is-opening, .door .spark").count(), 0, "回到走廊後門要關上")
        self.face(p, {"station": 4, "side": "left"})
        p.click('.door[data-special="spectators"]')
        p.wait_for_selector('.door[data-special="spectators"].is-opening', timeout=400)
        p.wait_for_function("document.body.classList.contains('in-room')")
        self.assertEqual(self.errors, [])

    def test_pixel_sprites(self):
        p = self.open()
        for r in SITE["rooms"]:
            s = r["slug"]
            self.assertEqual(p.locator(f'.door[data-room="{s}"] svg.px').count(), 1, s)
            self.assertEqual(p.locator(f'.room[data-room="{s}"] .room-name svg.px').count(), 1, s)
            self.assertEqual(p.locator(f'#minimap button[data-room="{s}"] svg.px').count(), 1, s)
        self.assertEqual(p.evaluate("getComputedStyle(document.querySelector('svg.px')).shapeRendering"), "crispedges")
        p = self.open("#view=plan")
        self.assertEqual(p.locator("#plan section[data-room] h2 svg.px").count(), len(SITE["rooms"]))
    def test_hold_e_cancelled_by_turn(self):
        p = self.open()
        self.face(p, {"station": 1, "side": "left"}); p.wait_for_timeout(100)
        p.keyboard.down("e"); p.wait_for_timeout(200); p.keyboard.press("d"); p.wait_for_timeout(1200); p.keyboard.up("e")
        self.assertIsNone(p.evaluate("GH.state.room"), "按住 E 途中轉向就不該開門")

class Lobby(E2E):
    def test_corridor_is_inn(self):
        p = self.open()
        self.assertGreaterEqual(p.locator(".corridor .torch svg.px").count(), 6, "大廳牆上有火把")
        self.assertIn("rgb(138, 42, 34)", p.evaluate("getComputedStyle(document.querySelector('.floor')).backgroundImage"), "走道紅地毯")

    def test_rooms_have_own_genre_scene(self):
        p = self.open("#room=shooter")
        bgs = p.evaluate("[...document.querySelectorAll('.room[data-room]')].map(r => getComputedStyle(r).backgroundImage)")
        self.assertNotIn("none", bgs)
        self.assertEqual(len(set(bgs)), len(SITE["rooms"]), "每間房的場景都不同")
        self.assertEqual(p.locator(".rooms .sconce").count(), 0, "旅館火把只在大廳")

    def test_killfeed_translucent(self):
        p = self.open()
        a = p.evaluate("(getComputedStyle(document.querySelector('.kill')).backgroundColor.match(/rgba\(.*,\s*([\d.]+)\)/) || [0, 1])[1]")
        self.assertLessEqual(float(a), 0.6)


class Reveal(E2E):
    def cover(self, slug): return f'.room[data-room="{slug}"] .board-cover'

    def test_first_visit_cover_then_deal(self):
        p = self.open("#room=sim"); p.wait_for_function("document.body.classList.contains('in-room')")
        self.assertTrue(p.is_visible(self.cover("sim"))); self.assertIn("翻開", p.inner_text(self.cover("sim")))
        self.assertTrue(p.evaluate("document.querySelector('.room[data-room=\"sim\"] .stage .card').inert"), "翻開前卡片不能按")
        self.assertIn("board-cover", p.evaluate("document.activeElement.className"))
        p.click(self.cover("sim"))
        p.wait_for_selector('.room[data-room="sim"] .stage .card .fx', timeout=3000)
        p.wait_for_function("[...document.querySelectorAll('.room[data-room=\"sim\"] .stage .card')].every(c => !c.inert)", timeout=5000)
        self.assertFalse(p.is_visible(self.cover("sim")))
        top = min((g for g in SITE["games"] if g["room_slug"] == "sim" and g["room_rank"]), key=lambda g: g["room_rank"])
        p.wait_for_timeout(2500)
        self.assertEqual(p.inner_text(f'.room[data-room="sim"] .card[data-id="{top["id"]}"] .big'), p.evaluate(f"GH.fmt.num({top['score']})"), "數字跑完要停在正確值")
        self.assertIn("sim", p.evaluate("JSON.parse(localStorage.getItem('gh.revealed'))"))

    def test_second_visit_skips_cover(self):
        p = self.open("#room=sim"); p.click(self.cover("sim")); p.wait_for_timeout(300)
        p.click("#turn-back"); p.wait_for_function("GH.state.room === null")
        p.evaluate("GH.go({room:'sim'}, {animate:false})"); self.assertFalse(p.is_visible(self.cover("sim")))
        p.reload(); p.wait_for_function("window.GH && GH.ready === true")
        p.evaluate("GH.go({room:'sim'}, {animate:false})"); self.assertFalse(p.is_visible(self.cover("sim")), "重新整理後也記得")

    def test_deep_link_game_skips_cover(self):
        p = self.open("#room=shooter&game=730")
        self.assertFalse(p.is_visible(self.cover("shooter")))
        self.assertIn("is-open", p.get_attribute('.room[data-room="shooter"] .card[data-id="730"]', "class"))

    def test_every_ranked_game_has_own_effect(self):
        p = self.open()
        fx = p.evaluate("GH.FX")
        for g in SITE["games"]:
            if g["room_rank"] and g["room_rank"] <= 5: self.assertIn(g["id"], fx, g["name"])
        self.assertEqual(len({f["t"] for f in fx.values()}), len(fx), "每款遊戲的特效台詞都不同")

    def test_card_click_plays_its_effect(self):
        p = self.open("#room=casual&game=3419430"); p.wait_for_timeout(300)
        p.click('.room[data-room="casual"] .card[data-id="322170"]')
        p.wait_for_selector('.card[data-id="322170"] .fx-cap', timeout=1000)
        self.assertEqual(p.inner_text('.card[data-id="322170"] .fx-cap'), p.evaluate("GH.FX['322170'].t"))

    def test_reduced_motion_reveal_without_fx(self):
        p = self.open("#room=rpg", reduced=True)
        p.click(self.cover("rpg"))
        self.assertFalse(p.is_visible(self.cover("rpg")))
        self.assertFalse(p.evaluate("document.querySelector('.room[data-room=\"rpg\"] .stage .card').inert"))
        p.wait_for_timeout(300); self.assertEqual(p.locator(".fx").count(), 0)

    def test_keyboard_reveal_and_arrow_between_cards(self):
        p = self.open("#room=action"); p.wait_for_function("document.body.classList.contains('in-room')")
        p.keyboard.press("Enter")
        p.wait_for_function("[...document.querySelectorAll('.room[data-room=\"action\"] .stage .card')].every(c => !c.inert)", timeout=5000)
        first = p.evaluate("document.activeElement.dataset.id")
        p.keyboard.press("ArrowRight")
        second = p.evaluate("document.activeElement.dataset.id")
        self.assertNotEqual(first, second, "房間裡方向鍵要能換卡")
        p.keyboard.press("Enter"); self.assertIn("is-open", p.get_attribute(f'.card[data-id="{second}"]', "class"))

    def test_storage_blocked_still_works(self):
        ctx = self.browser.new_context(); self.addCleanup(ctx.close)
        ctx.add_init_script("Object.defineProperty(window, 'localStorage', {get(){ throw new Error('denied'); }})")
        p = ctx.new_page(); errs = []; p.on("pageerror", lambda e: errs.append(str(e)))
        p.goto(URL + "#room=sim"); p.wait_for_function("window.GH && GH.ready === true", timeout=5000)
        p.click(self.cover("sim")); self.assertEqual(errs, [])

if __name__ == "__main__":
    unittest.main()
