# tools/build_data.py
"""讀 data/ → data/site_data.json → 注入 index.html。用法：python -m tools.build_data [--to 2026-09]"""
import argparse, datetime as dt, json, re
from pathlib import Path
from tools import rules

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
TW = dt.timezone(dt.timedelta(hours=8))
BEGIN, END = "<!-- DATA:BEGIN -->", "<!-- DATA:END -->"
SOURCE_NAMES = {"steam_ccu": "Steam 官方排行 API", "enriched": "Steam appdetails、SteamSpy", "steamcharts": "Steamcharts",
                "fortnitegg_1y": "fortnite.gg 每日峰值", "fortnitegg_now": "fortnite.gg 當下人數", "rolimons": "Rolimons"}


def _read(p):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def load_inputs(data_dir):
    return {"ccu": _read(data_dir / "steam_top_ccu_raw.json"), "enriched": _read(data_dir / "top100_enriched.json"),
            "charts": _read(data_dir / "steamcharts_monthly.json"), "fn_1y": _read(data_dir / "fortnitegg_1y_raw.json"),
            "fn_now": _read(data_dir / "fortnitegg_now.json"), "rolimons": _read(data_dir / "rolimons_gamelist.json"),
            "manual": _read(data_dir / "manual.json"), "copy": _read(data_dir / "copy.json"),
            "log": _read(data_dir / "fetch_log.json")}


def _base(id, name, name_en, appids):
    return {"id": id, "name": name, "name_en": name_en, "steam_appids": appids, "badge": "steam_main",
            "badge_note": None, "room": None, "room_slug": None, "room_reason": None, "monthly_peaks": {},
            "months": 0, "score": None, "rank": None, "room_rank": None, "status": "no_monthly", "now": None,
            "peak_24h": None, "peak_30d": None, "retention": None, "retention_tag": None, "tags": [], "copy": None}


def _finish(g, peaks, tags, genres, man, n_months):
    s, n = rules.score(peaks)
    g["monthly_peaks"], g["months"] = peaks, n
    g["score"] = round(s) if s is not None else None
    if g["status"] not in ("unranked_platform", "spectator"):
        g["status"] = rules.status_for(n)
    if g["status"] == "unranked_platform":
        g["room"], g["room_reason"] = None, "平台，不分房"
    else:
        g["room"], g["room_reason"] = rules.assign_room(g["id"], tags, genres, man["room_override"])
    g["room_slug"] = rules.ROOM_SLUG.get(g["room"])
    if g["status"] == "ranked" and n < n_months:
        g["tags"].append(f"上市 {n} 個月")
    g["retention"], g["retention_tag"] = rules.retention(g["now"], g["peak_30d"])
    if g["id"] in man.get("steam_partial", {}):
        g["badge"], g["badge_note"] = "steam_partial", man["steam_partial"][g["id"]]
    g["tags"] = list(dict.fromkeys(man.get("extra_tags", {}).get(g["id"], []) + g["tags"]))


def build(inp, period):
    man = inp["manual"]
    months = rules.month_keys(*period)
    charts = inp["charts"] or {}
    enriched = {g["appid"]: g for g in (inp["enriched"] or [])}
    keep = set(man["keep_despite_type"])
    soft = set(man["exclude"]["software"])
    merged = {a for m in man["merge"].values() for a in m["appids"]}
    games = []

    for a, e in enriched.items():
        if a in soft or a in merged:
            continue
        if e.get("type") in man["exclude"]["demo_types"]:
            continue
        if e.get("type") not in (None, "game") and str(a) not in keep:
            continue
        fix = man["name_fix"].get(str(a), {})
        g = _base(str(a), fix.get("name") or e.get("name") or str(a), fix.get("name_en") or e.get("name_en") or "", [a])
        g["now"], g["peak_24h"] = e.get("concurrent_in_game"), e.get("peak_in_game")
        c = charts.get(str(a))
        g["peak_30d"] = ((c or {}).get("Last 30 Days") or {}).get("peak")
        if e.get("tw_store") is False or str(a) in man["name_fix"] and "台灣區" in man["name_fix"][str(a)].get("note", ""):
            g["tags"].append("台灣區未上架")
        _finish(g, rules.steam_monthly(c, months), e.get("tags"), e.get("genres"), man, len(months))
        games.append(g)

    for mid, m in man["merge"].items():
        parts = [enriched.get(a) for a in m["appids"]]
        if not all(parts):
            continue
        g = _base(mid, m["name"], m["name_en"], m["appids"])
        g["now"] = sum(p["concurrent_in_game"] for p in parts)
        g["peak_24h"] = None  # 兩版的 24 小時峰值發生時刻不同，不能相加
        g["peak_30d"] = None  # 同上，兩版 30 日峰值時刻不同，不相加；因此 GTA V 沒有留存標籤
        src = enriched[m["tags_from"]]
        _finish(g, rules.sum_monthly(*(rules.steam_monthly(charts.get(str(a)), months) for a in m["appids"])),
                src.get("tags"), src.get("genres"), man, len(months))
        games.append(g)

    for nid, n in man["non_steam"].items():
        g = _base(nid, n["name"], n["name_en"], [])
        g["badge"], g["badge_note"] = n["badge"], n.get("note")
        peaks = {}
        if nid == "fortnite":
            fn = (inp["fn_1y"] or {}).get("data")
            if fn:
                peaks = rules.daily_monthly(fn["start"], fn["step"], fn["values"], months)
                g["peak_30d"] = rules.daily_peak_last30(fn["values"])
            now = inp["fn_now"] or {}
            g["now"], g["peak_24h"] = now.get("now"), now.get("peak_24h")
        if nid == "roblox":
            g["status"] = "unranked_platform"
            if inp["rolimons"]:
                from tools.fetch_data import sum_rolimons
                g["now"] = sum_rolimons(inp["rolimons"])
        _finish(g, peaks, [], [], man, len(months))
        games.append(g)

    for s in man["spectators"]:
        g = _base(s["id"], s["name"], s["name_en"], [])
        g["badge"], g["badge_note"], g["status"] = "no_data", s["reason"], "spectator"
        g["room_reason"] = "查不到人數，不分房"
        games.append(g)

    rules.rank_games(games)
    totals = rules.room_totals(games)
    for _, name in rules.ROOMS:
        totals.setdefault(name, 0)
    glow = rules.door_glow(totals)
    order = sorted(totals, key=lambda k: -totals[k])
    rooms = [{"name": k, "slug": rules.ROOM_SLUG[k], "order": i + 1, "total": totals[k], "glow": glow[k]}
             for i, k in enumerate(order)]

    copy = inp["copy"] or {}
    for g in games:
        g["copy"] = (copy.get("games") or {}).get(g["id"])

    log = (inp["log"] or {}).get("sources", {})
    ccu_time = (inp["ccu"] or {}).get("response", {}).get("last_update")
    return {
        "generated_at": dt.datetime.now(TW).isoformat(timespec="seconds"),
        "snapshot_at": dt.datetime.fromtimestamp(ccu_time, TW).isoformat(timespec="minutes") if ccu_time else None,
        "period": {"from": period[0], "to": period[1]},
        "sources": [{"id": k, "name": SOURCE_NAMES.get(k, k), "url": v["url"], "ok": v["ok"], "fetched_at": v["fetched_at"]}
                    for k, v in log.items()],
        "games": games,
        "rooms": rooms,
        "overrides": [{"game": k, "name": next((g["name"] for g in games if g["id"] == k), k), "to": v[0], "reason": v[1]}
                      for k, v in man["room_override"].items()],
        "kill_feed": copy.get("kill_feed", []),
        "copy": {k: v for k, v in copy.items() if k not in ("games", "kill_feed")},
    }


def inject(html, payload):
    if BEGIN not in html or END not in html:
        raise ValueError("index.html 缺少 DATA:BEGIN / DATA:END 標記")
    safe = payload.replace("</", "<\\/")
    block = f'{BEGIN}<script type="application/json" id="site-data">{safe}</script>{END}'
    return re.sub(re.escape(BEGIN) + r".*?" + re.escape(END), lambda _: block, html, count=1, flags=re.S)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--to", default=None)
    args = ap.parse_args(argv)
    inp = load_inputs(DATA)
    to = args.to or (inp["log"] or {}).get("period_to") or "2026-09"
    site = build(inp, ("2026-01", to))
    text = json.dumps(site, ensure_ascii=False, separators=(",", ":"))
    (DATA / "site_data.json").write_text(json.dumps(site, ensure_ascii=False, indent=1), encoding="utf-8")
    idx = ROOT / "index.html"
    if idx.exists():
        idx.write_text(inject(idx.read_text(encoding="utf-8"), text), encoding="utf-8")
    ranked = sorted((g for g in site["games"] if g["rank"]), key=lambda g: g["rank"])[:10]
    for g in ranked:
        print(g["rank"], g["name"], g["score"], g["months"], g["room"])
    unknown = [g["name"] for g in site["games"] if g["room"] is None and g["status"] not in ("spectator", "unranked_platform")]
    if unknown:
        print("無法分房，請使用者決定：", unknown)


if __name__ == "__main__":
    main()
