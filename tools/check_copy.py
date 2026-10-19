# tools/check_copy.py
"""SPEC 9.2 的文案檢查。用法：python -m tools.check_copy"""
import json, re, sys

BANNED = ["史詩級", "神作", "必玩", "天花板", "封神", "無敵"]
PLACEHOLDERS = ["【此處待作者補充", "⚠️請核對", "⚠️ 請核對", "待查核", "〔待填〕"]
FIELDS = {"now", "peak_24h", "peak_30d", "score", "months", "rank"}
_PH = re.compile(r"\{(\w+):([\w-]+)\}")
# 允許的「數字」：遊戲名裡的數字（CS2、Dota 2、V、FC 26…）。判斷方式：把佔位符與名稱白名單移除後，不得再出現兩位以上的數字或「萬」前的數字。
_NUM = re.compile(r"\d[\d,.]*\s*(萬|億|人|%|小時|個月)")


def lint_text(where, text):
    errs = []
    for p in PLACEHOLDERS:
        if p in text:
            errs.append(f"{where}：殘留佔位符 {p}")
    for w in BANNED:
        if w in text:
            errs.append(f"{where}：誇飾詞「{w}」")
    for f, _ in _PH.findall(text):
        if f not in FIELDS:
            errs.append(f"{where}：不支援的數字欄位 {{{f}:…}}")
    if _NUM.search(_PH.sub("", text)):
        errs.append(f"{where}：手寫數字「{_NUM.search(_PH.sub('', text)).group(0)}」，請改用 {{欄位:id}}")
    return errs


def lint_game(gid, g):
    errs = []
    for k in ("intro", "why_hot", "editor_note", "source"):
        if not g.get(k):
            errs.append(f"{gid}：缺 {k}")
    if len(g.get("intro", "")) > 40:
        errs.append(f"{gid}：介紹超過 40 字")
    for m in g.get("memes", []):
        if not m.rstrip().endswith("（轉述）"):
            errs.append(f"{gid}：社群梗缺「（轉述）」")
    for k in ("intro", "why_hot", "editor_note"):
        errs += lint_text(f"{gid}.{k}", g.get(k, ""))
    for m in g.get("memes", []):
        errs += lint_text(f"{gid}.memes", m)
    return errs


def required_ids(site):
    need = set()
    for g in site["games"]:
        if (g["room_rank"] and g["room_rank"] <= 5) or (g["rank"] and g["rank"] <= 10) \
                or g["status"] in ("dark_horse", "no_monthly", "spectator", "unranked_platform"):
            need.add(g["id"])
    return need


def check(copy, site):
    errs = []
    games = copy.get("games", {})
    for gid in sorted(required_ids(site) - set(games)):
        errs.append(f"{gid}：缺文案")
    for gid, g in games.items():
        errs += lint_game(gid, g)
    for k in ("hook", "spawn_note", "spectator_quote", "pain_points", "vote", "metric_table", "rules_note", "kill_feed"):
        if k not in copy:
            errs.append(f"缺 {k}")
    errs += lint_text("hook", json.dumps(copy.get("hook", {}), ensure_ascii=False))
    ids = {g["id"] for g in site["games"]}
    for i, k in enumerate(copy.get("kill_feed", [])):
        errs += lint_text(f"kill_feed[{i}]", k.get("text", ""))
        if k.get("target") not in ids:
            errs.append(f"kill_feed[{i}]：target {k.get('target')} 不存在")
    return errs


def main():
    errs = check(json.load(open("data/copy.json", encoding="utf-8")), json.load(open("data/site_data.json", encoding="utf-8")))
    print("\n".join(errs) or "文案檢查通過")
    sys.exit(1 if errs else 0)


if __name__ == "__main__":
    main()
