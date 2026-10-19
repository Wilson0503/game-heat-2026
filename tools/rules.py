# tools/rules.py
"""SPEC.md 第 4、6 節的計算規則。純函式，不讀檔、不連網。"""
import datetime as dt
import math

ROOMS = [("shooter", "射擊"), ("rpg", "角色扮演"), ("sim", "模擬"),
         ("strategy", "策略"), ("casual", "休閒"), ("action", "動作冒險")]
ROOM_SLUG = {name: slug for slug, name in ROOMS}

_TAGS = {
    "射擊": ["FPS", "Shooter", "Hero Shooter", "Battle Royale", "Third-Person Shooter", "Looter Shooter", "Tactical"],
    "角色扮演": ["RPG", "Action RPG", "MMORPG", "JRPG", "Souls-like", "Hack and Slash", "Massively Multiplayer"],
    "模擬": ["Simulation", "Survival", "Open World Survival Craft", "Farming Sim", "Life Sim", "Colony Sim",
             "Driving", "Automobile Sim", "Sandbox", "Fishing"],
    "策略": ["Strategy", "MOBA", "Turn-Based Strategy", "Grand Strategy", "RTS", "Card Battler", "Deckbuilding"],
    "休閒": ["Casual", "Idler", "Relaxing", "Precision Platformer", "Music"],
    "動作冒險": ["Crime", "Action Roguelike", "Rogue-like", "Fighting", "2D Fighter", "Horror", "Survival Horror", "Hunting"],
}
TAG_ROOM = {t: room for room, ts in _TAGS.items() for t in ts}
GENERIC_TAGS = ["Action", "Adventure"]
GENRE_SKIP = {"獨立製作", "大型多人連線", "免費遊玩", "搶先體驗"}
GENRE_ROOM = {"角色扮演": "角色扮演", "模擬": "模擬", "運動": "模擬", "競速": "模擬", "策略": "策略", "休閒": "休閒"}
GENRE_LAST = {"動作": "動作冒險", "冒險": "動作冒險"}
MIN_MONTHS = 3
_MONTH_EN = ["January", "February", "March", "April", "May", "June", "July",
             "August", "September", "October", "November", "December"]


def month_keys(frm, to):
    y, m = map(int, frm.split("-"))
    ty, tm = map(int, to.split("-"))
    out = []
    while (y, m) <= (ty, tm):
        out.append((f"{y}-{m:02d}", f"{_MONTH_EN[m - 1]} {y}"))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def steam_monthly(chart, months):
    out = {}
    for iso, label in months:
        row = (chart or {}).get(label)
        if row and row.get("peak") is not None:
            out[iso] = int(row["peak"])
    return out


def sum_monthly(*series):
    """逐月相加；只保留每個來源都有的月份（缺一邊就不能相加）。"""
    if not series:
        return {}
    common = set(series[0]).intersection(*series[1:])
    return {k: sum(s[k] for s in series) for k in sorted(common)}


def daily_monthly(start, step, values, months):
    want = {iso for iso, _ in months}
    out = {}
    for i, v in enumerate(values):
        if v is None:
            continue
        d = dt.datetime.fromtimestamp(start + i * step, dt.timezone.utc)
        iso = f"{d.year}-{d.month:02d}"
        if iso in want:
            out[iso] = max(out.get(iso, 0), int(v))
    return out


def daily_peak_last30(values):
    vals = [v for v in values[-30:] if v is not None]
    return max(vals) if vals else None


def score(peaks):
    if not peaks:
        return None, 0
    return sum(peaks.values()) / len(peaks), len(peaks)


def status_for(months):
    if months == 0:
        return "no_monthly"
    return "ranked" if months >= MIN_MONTHS else "dark_horse"


def assign_room(key, tags, genres, overrides):
    if key in overrides:
        room, why = overrides[key]
        return room, f"人工:{why}"
    tags = tags or []
    for t in tags:
        if t in TAG_ROOM:
            return TAG_ROOM[t], f"標籤:{t}"
    for t in tags:
        if t in GENERIC_TAGS:
            return "動作冒險", f"通用標籤:{t}"
    gs = [g for g in (genres or []) if g not in GENRE_SKIP]
    for g in gs:
        if g in GENRE_ROOM:
            return GENRE_ROOM[g], f"類型:{g}"
    for g in gs:
        if g in GENRE_LAST:
            return GENRE_LAST[g], f"類型:{g}"
    return None, "無法判斷"


def retention(now, peak30):
    if now is None or not peak30:
        return None, None
    r = round(now / peak30, 2)
    tag = "退燒中" if r < 0.4 else "穩如磐石" if r > 0.85 else None
    return r, tag


def rank_games(games):
    ranked = sorted((g for g in games if g["status"] == "ranked"), key=lambda g: -g["score"])
    for g in games:
        g["rank"] = None
        g["room_rank"] = None
    room_count = {}
    for i, g in enumerate(ranked, 1):
        g["rank"] = i
        room_count[g["room"]] = room_count.get(g["room"], 0) + 1
        g["room_rank"] = room_count[g["room"]]


def room_totals(games):
    totals = {}
    for g in games:
        if g.get("room_rank") and g["room_rank"] <= 5:
            totals[g["room"]] = totals.get(g["room"], 0) + g["score"]
    return {k: round(v) for k, v in totals.items()}


def door_glow(totals):
    pos = [t for t in totals.values() if t > 0]
    if not pos:
        return {k: 0.25 for k in totals}
    lo, hi = min(pos), max(pos)
    out = {}
    for k, t in totals.items():
        if t <= 0:
            out[k] = 0.25
        elif hi == lo:
            out[k] = 1.0
        else:
            out[k] = round(0.25 + 0.75 * math.log(t / lo) / math.log(hi / lo), 4)
    return out
