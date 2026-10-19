# tests/test_rules.py
import unittest
from tools import rules

M = rules.month_keys("2026-01", "2026-09")

class MonthKeys(unittest.TestCase):
    def test_range(self):
        self.assertEqual(len(M), 9)
        self.assertEqual(M[0], ("2026-01", "January 2026"))
        self.assertEqual(M[-1], ("2026-09", "September 2026"))
    def test_cross_year(self):
        ks = rules.month_keys("2025-11", "2026-02")
        self.assertEqual([k for k, _ in ks], ["2025-11", "2025-12", "2026-01", "2026-02"])

class Monthly(unittest.TestCase):
    def test_steam_monthly_skips_missing(self):
        chart = {"January 2026": {"avg": 1.0, "peak": 100}, "March 2026": {"avg": 1.0, "peak": 300},
                 "Last 30 Days": {"avg": 1.0, "peak": 999}}
        self.assertEqual(rules.steam_monthly(chart, M), {"2026-01": 100, "2026-03": 300})
    def test_steam_monthly_none(self):
        self.assertEqual(rules.steam_monthly(None, M), {})
    def test_sum_monthly_only_common_months(self):
        a = {"2026-01": 10, "2026-02": 20}; b = {"2026-01": 1}
        self.assertEqual(rules.sum_monthly(a, b), {"2026-01": 11})
    def test_daily_monthly_utc_max(self):
        start = 1767225600  # 2026-01-01 00:00 UTC
        vals = [5, 9, None] + [0] * 28 + [7]  # 第 32 天 = 2026-02-01
        out = rules.daily_monthly(start, 86400, vals, M)
        self.assertEqual(out, {"2026-01": 9, "2026-02": 7})
    def test_last30(self):
        self.assertEqual(rules.daily_peak_last30([1] * 40 + [50] + [None] * 5), 50)
        self.assertIsNone(rules.daily_peak_last30([None, None]))

class ScoreStatus(unittest.TestCase):
    def test_score_mean_of_present(self):
        self.assertEqual(rules.score({"2026-01": 100, "2026-02": 300}), (200.0, 2))
        self.assertEqual(rules.score({}), (None, 0))
    def test_status(self):
        self.assertEqual(rules.status_for(0), "no_monthly")
        self.assertEqual(rules.status_for(2), "dark_horse")
        self.assertEqual(rules.status_for(3), "ranked")

class Rooms(unittest.TestCase):
    OV = {"578080": ["射擊", "第一個標籤是 Survival"]}
    def test_override(self):
        self.assertEqual(rules.assign_room("578080", ["Survival"], [], self.OV), ("射擊", "人工:第一個標籤是 Survival"))
    def test_gta_tags_go_action(self):
        tags = ["Open World", "Action", "Multiplayer", "Crime", "Automobile Sim", "Third Person"]
        self.assertEqual(rules.assign_room("x", tags, [], {}), ("動作冒險", "標籤:Crime"))
    def test_generic_tag_last(self):
        tags = ["Co-op", "Action", "FPS"]
        self.assertEqual(rules.assign_room("x", tags, [], {})[0], "射擊")
        self.assertEqual(rules.assign_room("x", ["Open World", "Adventure"], [], {}), ("動作冒險", "通用標籤:Adventure"))
    def test_genre_fallback_keeps_order(self):
        self.assertEqual(rules.assign_room("x", [], ["休閒", "獨立製作", "大型多人連線", "模擬"], {}), ("休閒", "類型:休閒"))
        self.assertEqual(rules.assign_room("x", [], ["動作", "冒險", "大型多人連線", "角色扮演"], {}), ("角色扮演", "類型:角色扮演"))
        self.assertEqual(rules.assign_room("x", [], ["動作"], {}), ("動作冒險", "類型:動作"))
        self.assertEqual(rules.assign_room("x", [], ["運動"], {}), ("模擬", "類型:運動"))
    def test_unknown(self):
        self.assertEqual(rules.assign_room("x", [], ["免費遊玩"], {}), (None, "無法判斷"))

class Retention(unittest.TestCase):
    def test_tags(self):
        self.assertEqual(rules.retention(30, 100), (0.3, "退燒中"))
        self.assertEqual(rules.retention(90, 100), (0.9, "穩如磐石"))
        self.assertEqual(rules.retention(60, 100), (0.6, None))
    def test_missing(self):
        self.assertEqual(rules.retention(None, 100), (None, None))
        self.assertEqual(rules.retention(10, None), (None, None))
        self.assertEqual(rules.retention(10, 0), (None, None))

class Ranking(unittest.TestCase):
    def g(self, id, room, score, status="ranked"):
        return {"id": id, "room": room, "score": score, "status": status}
    def test_rank_and_room_rank(self):
        gs = [self.g("a", "射擊", 10), self.g("b", "射擊", 30), self.g("c", "策略", 20),
              self.g("d", "射擊", 99, "dark_horse")]
        rules.rank_games(gs)
        by = {x["id"]: x for x in gs}
        self.assertEqual((by["b"]["rank"], by["c"]["rank"], by["a"]["rank"]), (1, 2, 3))
        self.assertEqual((by["b"]["room_rank"], by["a"]["room_rank"], by["c"]["room_rank"]), (1, 2, 1))
        self.assertIsNone(by["d"]["rank"]); self.assertIsNone(by["d"]["room_rank"])
    def test_room_totals_top5(self):
        gs = [self.g(str(i), "射擊", i) for i in range(1, 8)]
        rules.rank_games(gs)
        self.assertEqual(rules.room_totals(gs)["射擊"], 7 + 6 + 5 + 4 + 3)
    def test_door_glow(self):
        g = rules.door_glow({"射擊": 1000, "策略": 100, "休閒": 10})
        self.assertAlmostEqual(g["射擊"], 1.0); self.assertAlmostEqual(g["休閒"], 0.25)
        self.assertAlmostEqual(g["策略"], 0.625)
        self.assertEqual(rules.door_glow({"射擊": 5, "策略": 5}), {"射擊": 1.0, "策略": 1.0})
        self.assertEqual(rules.door_glow({"射擊": 5, "策略": 0})["策略"], 0.25)

if __name__ == "__main__":
    unittest.main()
