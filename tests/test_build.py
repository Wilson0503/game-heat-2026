# tests/test_build.py
import json, unittest
from tools import build_data as b

def chart(peaks):
    names = ["January", "February", "March", "April", "May", "June", "July", "August", "September"]
    c = {f"{names[i]} 2026": {"avg": 1.0, "peak": p} for i, p in enumerate(peaks) if p is not None}
    c["Last 30 Days"] = {"avg": 1.0, "peak": 200}
    return c

def inputs(**over):
    base = {
        "ccu": {"response": {"last_update": 1792394032, "ranks": []}},
        "enriched": [
            {"rank": 1, "appid": 730, "concurrent_in_game": 100, "peak_in_game": 150, "name": "Counter-Strike 2",
             "name_en": "Counter-Strike: Global Offensive", "type": "game", "genres": ["動作"], "tags": ["FPS"]},
            {"rank": 2, "appid": 271590, "concurrent_in_game": 10, "peak_in_game": 20, "name": "GTA V 傳承版",
             "type": "game", "genres": ["動作"], "tags": ["Open World", "Action", "Crime"]},
            {"rank": 3, "appid": 3240220, "concurrent_in_game": 5, "peak_in_game": 9, "name": "GTA V 強化版",
             "type": "game", "genres": ["動作"], "tags": ["Shooter"]},
            {"rank": 4, "appid": 431960, "concurrent_in_game": 1, "peak_in_game": 1, "name": "Wallpaper Engine", "type": "game"},
            {"rank": 5, "appid": 5166840, "concurrent_in_game": 1, "peak_in_game": 1, "name": "X Demo", "type": "demo"},
            {"rank": 6, "appid": 2676230, "concurrent_in_game": 3, "peak_in_game": 4, "name": "FiveM", "type": "advertising",
             "genres": [], "tags": [], "tw_store": False},
            {"rank": 7, "appid": 1867240, "concurrent_in_game": 3, "peak_in_game": 4, "name": "WARDOGS", "type": "game",
             "genres": ["動作"], "tags": []},
            {"rank": 8, "appid": 3393110, "concurrent_in_game": 9, "peak_in_game": 9},
        ],
        "charts": {"730": chart([100] * 9), "271590": chart([10] * 9), "3240220": chart([5] * 8 + [None]),
                   "2676230": chart([3] * 9), "1867240": chart([None] * 8 + [40]), "3393110": None,
                   "431960": chart([1] * 9)},
        "fn_1y": None, "fn_now": None, "rolimons": None, "copy": None, "log": None,
        "manual": json.load(open("data/manual.json", encoding="utf-8")),
    }
    base.update(over)
    return base

class Build(unittest.TestCase):
    def setUp(self):
        self.site = b.build(inputs(), ("2026-01", "2026-09"))
        self.by = {g["id"]: g for g in self.site["games"]}

    def test_excludes_software_and_demo(self):
        self.assertNotIn("431960", self.by); self.assertNotIn("5166840", self.by)
    def test_keeps_fivem_despite_type(self):
        self.assertIn("2676230", self.by); self.assertEqual(self.by["2676230"]["room"], "角色扮演")
        self.assertIn("模組平台", self.by["2676230"]["tags"])
        self.assertIn("台灣區未上架", self.by["2676230"]["tags"])
    def test_gta_merged_common_months_and_legacy_tags(self):
        self.assertNotIn("271590", self.by); self.assertNotIn("3240220", self.by)
        g = self.by["gtav"]
        self.assertEqual(g["steam_appids"], [271590, 3240220])
        self.assertEqual(g["months"], 8); self.assertEqual(g["score"], 15)
        self.assertEqual(g["room"], "動作冒險"); self.assertEqual(g["now"], 15)
        self.assertEqual(g["badge"], "steam_partial")
    def test_name_fix(self):
        self.assertEqual(self.by["730"]["name_en"], "Counter-Strike 2")
        self.assertEqual(self.by["3393110"]["name"], "AION 2")
    def test_status(self):
        self.assertEqual(self.by["730"]["status"], "ranked")
        self.assertEqual(self.by["1867240"]["status"], "dark_horse")
        self.assertEqual(self.by["3393110"]["status"], "no_monthly")
        self.assertIsNone(self.by["3393110"]["score"])
    def test_month_tag(self):
        self.assertIn("上市 8 個月", self.by["gtav"]["tags"])
        self.assertFalse(any(t.startswith("上市") for t in self.by["730"]["tags"]))
    def test_spectators_and_roblox(self):
        self.assertEqual(self.by["lol"]["status"], "spectator"); self.assertEqual(self.by["lol"]["badge"], "no_data")
        self.assertEqual(self.by["roblox"]["status"], "unranked_platform")
        self.assertIsNone(self.by["roblox"]["room"])
    def test_missing_now_is_null(self):
        self.assertIsNone(self.by["roblox"]["now"])
        self.assertIsNone(self.by["fortnite"]["now"])
        self.assertEqual(self.by["fortnite"]["status"], "no_monthly")
    def test_rooms_ordered_by_total(self):
        names = [r["name"] for r in self.site["rooms"]]
        self.assertEqual(len(names), 6)
        totals = [r["total"] for r in self.site["rooms"]]
        self.assertEqual(totals, sorted(totals, reverse=True))
        self.assertEqual(self.site["rooms"][0]["order"], 1)
    def test_retention(self):
        self.assertEqual(self.by["730"]["retention"], 0.5)  # 100 / 200
    def test_overrides_exported(self):
        self.assertTrue(any(o["game"] == "2676230" for o in self.site["overrides"]))

class Fortnite(unittest.TestCase):
    def test_fortnite_monthly_from_daily(self):
        start = 1767225600  # 2026-01-01 UTC
        fn = {"success": True, "data": {"start": start, "step": 86400, "values": [100] * 31 + [200] * 28 + [300] * 31}}
        site = b.build(inputs(fn_1y=fn, fn_now={"now": 80, "peak_24h": 90}), ("2026-01", "2026-09"))
        g = {x["id"]: x for x in site["games"]}["fortnite"]
        self.assertEqual(g["monthly_peaks"], {"2026-01": 100, "2026-02": 200, "2026-03": 300})
        self.assertEqual(g["score"], 200); self.assertEqual(g["now"], 80); self.assertEqual(g["peak_30d"], 300)
        self.assertEqual(g["room"], "射擊"); self.assertEqual(g["badge"], "cross_platform")

class Inject(unittest.TestCase):
    def test_inject_idempotent(self):
        html = '<a><!-- DATA:BEGIN --><script type="application/json" id="site-data">{}</script><!-- DATA:END --></a>'
        once = b.inject(html, '{"x":1}')
        self.assertIn('{"x":1}', once)
        self.assertEqual(b.inject(once, '{"x":1}'), once)
    def test_inject_escapes_script_close(self):
        out = b.inject('<!-- DATA:BEGIN --><!-- DATA:END -->', '{"t":"</script>"}')
        self.assertNotIn('"</script>"', out)
    def test_inject_requires_markers(self):
        with self.assertRaises(ValueError):
            b.inject("<html></html>", "{}")

if __name__ == "__main__":
    unittest.main()
