"""Строит страницу «Слова Жени» для репетитора (out/zhenya-words.html) по копии коллекции.

    python .claude/skills/zhenya-progress/words_page.py [--source synced|desktop]

Все слова колоды со статусом: учит сейчас / выучено / ещё впереди (в том порядке, в каком придут),
и трудные — ошибок за последние HARD_DAYS дней не меньше HARD_ERRORS. Шаблон — words_template.html
рядом; выкладывает .github/workflows/report.yml вместе с графиком (daily_chart.py).
Статус слова (записи — обе карточки EN→RU и RU→EN): «выучено» — все карточки на повторении (type 2)
с интервалом не меньше LEARNED_DAYS (спросит не чаще раза в неделю), «впереди» — все новые (type 0),
иначе «учит».
«iv» — по каждому направлению интервалы после ответов (revlog.ivl > 0, дни): растут (1 → 3 → 8) —
слово запоминается; стоят на 1–2 днях или падают после ошибки — нет.
"""
import argparse
import html as htmllib
import datetime as dt
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import progress as p  # noqa: E402
from ankiweb_sync import DATA_DIR  # noqa: E402
from daily_chart import MONTHS, ROOT_DIR, HERE  # noqa: E402

OUT = os.path.join(ROOT_DIR, "out", "zhenya-words.html")
HARD_DAYS, HARD_ERRORS = 14, 8
LEARNED_DAYS = 7  # то же в daily_chart.py (IV_BUCKETS[1] + 1)
F_RU, F_DEF, F_EX = 1, 2, 3  # поля «русский», определение, пример (FIELDS в build_deck.py)


def txt(s):
    return htmllib.unescape(p.clean(s))


def topic(name):
    """'IGCSE English\\x1f1 Command words\\x1fExam instructions' → 'Command words · Exam instructions'."""
    parts = name.split("\x1f")[1:]
    return " · ".join(s.split(" ", 1)[1] if s[:1].isdigit() and " " in s else s for s in parts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["synced", "desktop"], default="synced")
    a = ap.parse_args()
    src_dir = DATA_DIR if a.source == "synced" else p.PROFILE
    src_file = os.path.join(src_dir, "collection.anki2")
    if not os.path.exists(src_file):
        sys.exit(f"Нет коллекции: {src_file}")
    data_time = dt.datetime.fromtimestamp(os.path.getmtime(src_file))
    hard_from = (dt.datetime.now() - dt.timedelta(days=HARD_DAYS)).timestamp() * 1000

    con, tmp = p.open_copy(src_dir)
    try:
        decks = {did: name for did, name in con.execute("select id, name from decks")
                 if name.split("\x1f")[0] == p.ROOT and "\x1f" in name}
        ids = ",".join(map(str, decks))
        words, card_note = {}, {}
        for cid, nid, did, odid, ctype, due, ord_, civl in con.execute(
                f"select id, nid, did, odid, type, due, ord, ivl from cards where did in ({ids}) or odid in ({ids})"):
            w = words.setdefault(nid, {"types": [], "deck": decks.get(odid or did, ""), "pos": None,
                                       "ans": 0, "err": 0, "recent": 0, "last": 0})
            w["types"].append(ctype if ctype != 2 or civl >= LEARNED_DAYS else 1)  # 2 = выучено
            if ctype == 0:
                w["pos"] = due if w["pos"] is None else min(w["pos"], due)
            card_note[cid] = (nid, p.DIRECTION.get(ord_, str(ord_)))
        for rid, cid, ease, ivl in con.execute(
                "select id, cid, ease, ivl from revlog where ease > 0 and type in (0, 1, 2) order by id"):
            nid, direction = card_note.get(cid, (None, None))
            w = words.get(nid)
            if not w:
                continue
            if ivl > 0:  # по одному интервалу на день — последний (ошибка и переучивание в тот же день)
                tr = w.setdefault("iv", {}).setdefault(direction, [])
                day = p.anki_day(rid)
                if tr and tr[-1][0] == day:
                    tr[-1] = (day, ivl)
                else:
                    tr.append((day, ivl))
            w["ans"] += 1
            w["last"] = max(w["last"], rid)
            if ease == 1:
                w["err"] += 1
                w["recent"] += rid >= hard_from
        notes = {nid: flds.split("\x1f") for nid, flds in con.execute("select id, flds from notes")}
    finally:
        con.close()
        shutil.rmtree(tmp, ignore_errors=True)

    rows = []
    for nid, w in words.items():
        f = notes[nid]
        types = w["types"]
        status = "done" if all(t == 2 for t in types) else "new" if all(t == 0 for t in types) else "learn"
        rows.append({
            "en": txt(f[p.F_TERM]), "ru": txt(f[F_RU]), "def": txt(f[F_DEF]),
            "ex": txt(f[F_EX]), "topic": topic(w["deck"]), "s": status,
            "hard": w["recent"] >= HARD_ERRORS, "ans": w["ans"], "err": w["err"],
            "last": p.anki_day(w["last"]).isoformat() if w["last"] else None,
            "pos": w["pos"] if status == "new" else None,
            "iv": {d: [i for _day, i in tr] for d, tr in w.get("iv", {}).items()},
        })
    # впереди — в том порядке, в каком Anki их покажет; остальные — по трудности
    rows.sort(key=lambda r: (r["s"] == "new", r["pos"] or 0, -r["err"], r["en"].lower()))

    count = {k: sum(r["s"] == k for r in rows) for k in ("learn", "done", "new")}
    hard = sum(r["hard"] for r in rows)
    sub = (f"Колода «IGCSE English» — слова из заданий Cambridge IGCSE Maths 0580, Physics 0625 и Computer Science 0478. "
           f"Данные Anki на {data_time.day} {MONTHS[data_time.month - 1]} {data_time.year}, "
           f"{data_time:%H:%M}; страница обновляется каждый день.")
    with open(os.path.join(HERE, "words_template.html"), encoding="utf-8") as fh:
        html = fh.read()
    html = (html.replace("__SUB__", sub)
            .replace("__HARD_RULE__", f"{HARD_ERRORS} и больше ошибок за последние {HARD_DAYS} дней")
            .replace("__WORDS_JSON__", json.dumps(rows, ensure_ascii=False, separators=(",", ":"))))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(html)
    print(f"Готово: {OUT}  (учит {count['learn']}, выучено {count['done']}, впереди {count['new']}, "
          f"трудных {hard})")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
