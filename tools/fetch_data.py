# tools/fetch_data.py
"""SPEC.md 第 3.4 節：重抓所有來源。用法：python -m tools.fetch_data [--to 2026-10]"""
import argparse, datetime as dt, json, re, shutil, sys, time, urllib.error, urllib.request
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
UA = "game-heat-2026/1.0 (personal research; contact via GitHub)"
GENERATED = ["steam_top_ccu_raw.json", "top100_enriched.json", "steamcharts_monthly.json",
             "fortnitegg_1y_raw.json", "fortnitegg_now.json", "rolimons_gamelist.json",
             "fetch_log.json", "raw"]
_last = [0.0]
_ROW = re.compile(r'<td class="month-cell left[^"]*">\s*(.*?)\s*</td>.*?<td[^>]*>\s*([\d.]+)\s*</td>'
                  r'.*?</td>.*?</td>\s*<td[^>]*>\s*(\d+)\s*</td>', re.S)


def now_iso():
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat(timespec="seconds")


def is_bot_wall(status, body):
    b = body[:5000].lower()
    return status in (403, 429, 503) and ("just a moment" in b or "cloudflare" in b) \
        or "challenge-platform" in b or "cf-chl" in b


def get(url, headers=None, want_json=True):
    wait = 1.0 - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            status, body = r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        status, body = e.code, e.read().decode("utf-8", "replace")
    finally:
        _last[0] = time.time()
    if is_bot_wall(status, body):
        raise RuntimeError(f"防機器人驗證（HTTP {status}），依規格跳過")
    if status != 200:
        raise RuntimeError(f"HTTP {status}")
    return json.loads(body) if want_json else body


def parse_steamcharts(html):
    return {m: {"avg": float(a), "peak": int(p)} for m, a, p in _ROW.findall(html)}


def sum_rolimons(payload):
    games = payload.get("games") if isinstance(payload, dict) else None
    if not payload.get("success") or not isinstance(games, dict):
        return None
    return sum(int(v[1]) for v in games.values() if isinstance(v, list) and len(v) > 1)


def archive(data_dir, stamp):
    present = [n for n in GENERATED if (data_dir / n).exists()]
    if not present:
        return None
    dest = data_dir / "archive" / stamp
    dest.mkdir(parents=True, exist_ok=True)
    for n in present:
        shutil.move(str(data_dir / n), str(dest / n))
    return dest


def write(data_dir, name, obj):
    p = data_dir / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


def run_sources(data_dir, sources, log):
    """sources: [(id, url, fn)]；fn() 回傳 {檔名: 內容}。單一來源失敗只記錄，不中斷。"""
    for sid, url, fn in sources:
        try:
            for name, obj in fn().items():
                write(data_dir, name, obj)
            log[sid] = {"ok": True, "fetched_at": now_iso(), "error": None, "url": url}
        except Exception as e:  # noqa: BLE001 — 規格要求單一來源失敗不中斷
            log[sid] = {"ok": False, "fetched_at": now_iso(), "error": str(e), "url": url}


# ---- 各來源 ----
CCU_URL = "https://api.steampowered.com/ISteamChartsService/GetGamesByConcurrentPlayers/v1/"


def src_steam_ccu():
    return {"steam_top_ccu_raw.json": get(CCU_URL)}


def _ranks(data_dir):
    return json.loads((data_dir / "steam_top_ccu_raw.json").read_text(encoding="utf-8"))["response"]["ranks"]


def src_enriched(data_dir):
    """appdetails（tchinese，cc=tw，失敗改 cc=us）＋ SteamSpy 前 8 個標籤。"""
    out, errors = [], []
    for r in _ranks(data_dir):
        a = r["appid"]
        g = {k: r[k] for k in ("rank", "appid", "concurrent_in_game", "peak_in_game")}
        detail, tw = None, True
        for cc in ("tw", "us"):
            try:
                j = get(f"https://store.steampowered.com/api/appdetails?appids={a}&l=tchinese&cc={cc}")
                write(data_dir, f"raw/appdetails/{a}.json", j)
                if j.get(str(a), {}).get("success"):
                    detail = j[str(a)]["data"]; break
            except RuntimeError as e:
                errors.append(f"appdetails {a} cc={cc}: {e}")
            tw = False
        if detail:
            g.update(name=detail.get("name"), type=detail.get("type"),
                     genres=[x["description"] for x in detail.get("genres", [])])
            if not tw:
                g["tw_store"] = False
        try:
            spy = get(f"https://steamspy.com/api.php?request=appdetails&appid={a}")
            write(data_dir, f"raw/steamspy/{a}.json", spy)
            tags = spy.get("tags") or {}
            g["tags"] = [t for t, _ in sorted(tags.items(), key=lambda kv: -kv[1])][:8] if isinstance(tags, dict) else []
            g["name_en"] = spy.get("name") or ""
        except RuntimeError as e:
            errors.append(f"steamspy {a}: {e}")
        out.append(g)
    if errors:
        print("\n".join(errors[:20]), file=sys.stderr)
    return {"top100_enriched.json": out}


def src_steamcharts(data_dir):
    out, failed = {}, []
    for r in _ranks(data_dir):
        a = r["appid"]
        try:
            out[str(a)] = parse_steamcharts(get(f"https://steamcharts.com/app/{a}", want_json=False))
        except RuntimeError as e:
            out[str(a)] = None
            failed.append(f"{a}:{e}")
    if failed:
        print("Steamcharts 失敗：" + ", ".join(failed), file=sys.stderr)
    return {"steamcharts_monthly.json": out}


FN_HEADERS = {"Referer": "https://fortnite.gg/player-count", "X-Requested-With": "XMLHttpRequest"}


def src_fortnite_1y():
    return {"fortnitegg_1y_raw.json": get("https://fortnite.gg/player-count-graph?range=1y&id=-1", FN_HEADERS)}


def parse_fortnite_now(html):
    """「對戰中」當下人數與 24 小時對戰峰值（和每日峰值序列同口徑）。格式對不上就是 null（顯示待查）。"""
    def num(cls):
        m = re.search(r"class='chart-stats-div " + cls + r"' data-n='(\d+)'", html)
        return int(m.group(1)) if m else None
    return {"now": num("js-players-now"), "peak_24h": num("js-24h-peak")}


def src_fortnite_now():
    return {"fortnitegg_now.json": parse_fortnite_now(get("https://fortnite.gg/player-count", want_json=False))}


def src_rolimons():
    j = get("https://api.rolimons.com/games/v1/gamelist")
    if sum_rolimons(j) is None:
        raise RuntimeError("Rolimons 回應格式不符（沒有 success/games）")
    return {"rolimons_gamelist.json": j}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--to", help="計算期間最後一個月 YYYY-MM；預設上一個完整月份")
    args = ap.parse_args(argv)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M")
    moved = archive(DATA, stamp)
    if moved:
        print(f"舊檔已移到 {moved}")
    log = {}
    run_sources(DATA, [
        ("steam_ccu", CCU_URL, src_steam_ccu),
        ("enriched", "store.steampowered.com/api/appdetails + steamspy.com", lambda: src_enriched(DATA)),
        ("steamcharts", "https://steamcharts.com/app/<appid>", lambda: src_steamcharts(DATA)),
        ("fortnitegg_1y", "https://fortnite.gg/player-count-graph?range=1y&id=-1", src_fortnite_1y),
        ("fortnitegg_now", "https://fortnite.gg/player-count", src_fortnite_now),
        ("rolimons", "https://api.rolimons.com/games/v1/gamelist", src_rolimons),
    ], log)
    today = dt.date.today().replace(day=1) - dt.timedelta(days=1)
    write(DATA, "fetch_log.json", {"run_at": now_iso(), "period_to": args.to or today.strftime("%Y-%m"),
                                   "sources": log})
    ok = [k for k, v in log.items() if v["ok"]]
    bad = {k: v["error"] for k, v in log.items() if not v["ok"]}
    print(f"成功 {len(ok)}：{', '.join(ok)}")
    for k, e in bad.items():
        print(f"失敗 {k}：{e}")
    from tools import build_data
    build_data.main(["--to", args.to] if args.to else [])


if __name__ == "__main__":
    main()
