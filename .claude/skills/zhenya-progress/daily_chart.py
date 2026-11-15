"""Строит страницу-график «Как занимается Женя» (out/zhenya-progress.html) по копии коллекции.

    python .claude/skills/zhenya-progress/daily_chart.py [--source synced|desktop] [--days 14]

synced (по умолчанию) — копия, скачанная ankiweb_sync.py; desktop — коллекция Anki на компьютере.
Шаблон страницы — chart_template.html рядом; строит и выкладывает страницу на GitHub Pages
.github/workflows/report.yml (каждую ночь).
Считается как в progress.py: «верно» = ответ не «Снова»; «карточек верно» = карточки, хотя бы раз
отвеченные верно за день; «с 1-й попытки» = первый ответ дня по карточке верный.
«Через сколько дней спросит снова» (iv) — на конец дня у каждой начатой карточки берётся интервал
из её последнего ответа (revlog.ivl: дни; ≤ 0 — ещё в шагах обучения, то есть сегодня-завтра)
и раскладывается по корзинам IV_BUCKETS. Растут дальние корзины — слова запоминаются.
По предметам (SUBJECTS; предмет подколоды — p.STREAM_OF_TOP по её номеру): в днях «sn» — новых
слов за день (первый ответ по слову), «sa» — ответов за день; в subj — всего слов, сейчас учит,
выучено (обе карточки на повторении с интервалом ≥ 7 дней, как в words_page.py) и ответов за
последние RECENT_DAYS дней. Нужно, чтобы видеть, что все три предмета идут равномерно.
Новые слова от Жени: из истории ящика data/zhenya_inbox.tsv (inbox.py) — в днях «nw» — сколько
слов он записал в этот день; в __INBOX_JSON__ — только правило подсчёта чтения (gap, min).
Сколько он читал («rd», минуты): время записи слова — id записи (момент создания, мс). Пока Женя
читает, он записывает незнакомые слова; перестал записывать — перестал читать. Слова дня по
времени делятся на сеансы: перерыв больше READ_GAP минут — новый сеанс. Сеанс длится от первого
до последнего слова, но не меньше READ_MIN минут (одно слово — тоже чтение). «ss» — сеансы
[начало, конец, слов], «ws» — слова [слово, минута]; минуты от полуночи дня Anki, после полуночи
— больше 1440 (день Anki идёт до 4:00).
Время («min», «sm» — по предметам, минуты): сумма revlog.time — сколько карточка была на экране до
ответа; Anki обрезает одну карточку до 60 с (настройка колоды), перерывы между карточками не входят.
"""
import argparse
import datetime as dt
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import inbox as ib  # noqa: E402
import progress as p  # noqa: E402
from ankiweb_sync import DATA_DIR  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
OUT = os.path.join(ROOT_DIR, "out", "zhenya-progress.html")
IV_BUCKETS = (1, 6, 20)  # ≤1 день | 2–6 | 7–20 | 21+ (верхние границы, дни)
SUBJECTS = [("Maths", "Математика"), ("Physics", "Физика"), ("Computer Science", "Информатика")]
SUBJ_IDX = {en: i for i, (en, _ru) in enumerate(SUBJECTS)}
RECENT_DAYS = 7
READ_GAP = 30  # мин: перерыв между словами больше — новый сеанс чтения
READ_MIN = 5   # мин: самый короткий сеанс (одно слово)
MONTHS = "января февраля марта апреля мая июня июля августа сентября октября ноября декабря".split()


def words(n, one, few, many):
    n10, n100 = n % 10, n % 100
    w = one if n10 == 1 and n100 != 11 else few if 2 <= n10 <= 4 and not 12 <= n100 <= 14 else many
    return f"{n} {w}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["synced", "desktop"], default="synced")
    ap.add_argument("--days", type=int, default=14, help="сколько последних дней на графике")
    a = ap.parse_args()
    src_dir = DATA_DIR if a.source == "synced" else p.PROFILE
    src_file = os.path.join(src_dir, "collection.anki2")
    if not os.path.exists(src_file):
        sys.exit(f"Нет коллекции: {src_file}")
    data_time = dt.datetime.fromtimestamp(os.path.getmtime(src_file))
    ns = len(SUBJECTS)

    con, tmp = p.open_copy(src_dir)
    try:
        decks = {}  # deck id -> номер предмета в SUBJECTS
        for did, name in con.execute("select id, name from decks"):
            parts = name.split("\x1f")
            if parts[0] == p.ROOT and len(parts) > 1:
                decks[did] = SUBJ_IDX.get(p.STREAM_OF_TOP.get(parts[1][:1]), 0)
        ids = ",".join(map(str, decks))
        cards, note_subj, note_cards = {}, {}, {}
        for cid, nid, ctype, did, odid, civl in con.execute(
                f"select id, nid, type, did, odid, ivl from cards where did in ({ids}) or odid in ({ids})"):
            cards[cid] = (nid, ctype)
            note_subj[nid] = decks[odid] if odid in decks else decks[did]
            note_cards.setdefault(nid, []).append((ctype, civl))
        per, ivl_log, seen = {}, [], set()
        for rid, cid, ease, ivl, ms in con.execute(
                "select id, cid, ease, ivl, time from revlog where ease > 0 and type in (0, 1, 2) order by id"):
            if cid not in cards:
                continue
            day = p.anki_day(rid)
            ivl_log.append((day, cid, ivl))
            d = per.setdefault(day, {"ans": 0, "ok": 0, "okc": set(), "first": {},
                                     "sn": [0] * ns, "sa": [0] * ns, "ms": [0] * ns})
            ok = ease > 1
            d["ans"] += 1
            d["ok"] += ok
            if ok:
                d["okc"].add(cid)
            d["first"].setdefault(cid, ok)
            nid = cards[cid][0]
            d["sa"][note_subj[nid]] += 1
            d["ms"][note_subj[nid]] += ms
            if nid not in seen:  # первый ответ по слову — новое слово этого дня
                seen.add(nid)
                d["sn"][note_subj[nid]] += 1
        started = len({nid for nid, t in cards.values() if t > 0})
        strong = con.execute(f"select count(*) from cards where (did in ({ids}) or odid in ({ids})) "
                             f"and type = 2 and ivl > {IV_BUCKETS[1]}").fetchone()[0]
        total_notes = len(note_cards)
    finally:
        con.close()
        shutil.rmtree(tmp, ignore_errors=True)

    subj = [{"name": ru, "total": 0, "learn": 0, "done": 0, "recent": 0} for _en, ru in SUBJECTS]
    for nid, cs in note_cards.items():
        s = subj[note_subj[nid]]
        s["total"] += 1
        if all(t == 2 and i > IV_BUCKETS[1] for t, i in cs):
            s["done"] += 1
        elif any(t > 0 for t, _i in cs):
            s["learn"] += 1

    inbox = sorted(ib.read_log().values(), key=lambda r: int(r["id"]))
    nw = {}  # день -> [(минута от полуночи дня Anki, слово)]
    for r in inbox:
        t = dt.datetime.fromtimestamp(int(r["id"]) / 1000)
        minute = (t.date() - dt.date.fromisoformat(r["day"])).days * 1440 + t.hour * 60 + t.minute
        nw.setdefault(r["day"], []).append((minute, r["word"]))

    def sessions(ws):
        ss = []
        for m, _w in sorted(ws):
            if ss and m - ss[-1][1] <= READ_GAP:
                ss[-1][1], ss[-1][2] = m, ss[-1][2] + 1
            else:
                ss.append([m, m, 1])
        return ss

    today = p.anki_day(dt.datetime.now().timestamp() * 1000)
    end = today if per.get(today, {}).get("ans") or today.isoformat() in nw else today - dt.timedelta(days=1)
    first_day = min(per) if per else end
    start = max(first_day, end - dt.timedelta(days=a.days - 1))
    days, state, k = [], {}, 0
    for i in range((end - start).days + 1):
        day = start + dt.timedelta(days=i)
        d = per.get(day)
        while k < len(ivl_log) and ivl_log[k][0] <= day:  # состояние карточек на конец дня
            state[ivl_log[k][1]] = ivl_log[k][2]
            k += 1
        iv = [0] * (len(IV_BUCKETS) + 1)
        for ivl in state.values():
            iv[sum(ivl > b for b in IV_BUCKETS)] += 1
        days.append({"iso": day.isoformat(), "ans": d["ans"] if d else 0, "ok": d["ok"] if d else 0,
                     "cards": len(d["okc"]) if d else 0,
                     "first": sum(d["first"].values()) if d else 0, "iv": iv,
                     "sn": d["sn"] if d else [0] * ns, "sa": d["sa"] if d else [0] * ns,
                     "min": round(sum(d["ms"]) / 60000) if d else 0,
                     "sm": [round(x / 60000) for x in d["ms"]] if d else [0] * ns,
                     "nw": len(nw.get(day.isoformat(), []))})
        ws = sorted(nw.get(day.isoformat(), []))
        ss = sessions(ws)
        days[-1].update(ws=[[w, m] for m, w in ws], ss=ss,
                        rd=sum(max(b - a, READ_MIN) for a, b, _n in ss))
    for d in days[-RECENT_DAYS:]:
        for j, n in enumerate(d["sa"]):
            subj[j]["recent"] += n
    active = sum(1 for d in days if d["ans"])
    ans, ok = sum(d["ans"] for d in days), sum(d["ok"] for d in days)
    avg_min = round(sum(d["min"] for d in days if d["ans"]) / active) if active else 0

    def human(day):
        return f"{day.day} {MONTHS[day.month - 1]}"

    if start == end:
        period = human(start)
    elif (start.year, start.month) == (end.year, end.month):
        period = f"{start.day}–{human(end)}"
    else:
        period = f"{human(start)} – {human(end)}"
    kpis = [
        (str(started), f"слов начато (из {total_notes})"),
        (str(strong), "карточек помнит прочно — Anki спросит через неделю и позже"),
        (f"{active} из {len(days)}", f"дней с занятиями, {period}"),
        (f"{round(100 * ok / ans)}%" if ans else "—", "верных ответов за эти дни"),
        (f"{avg_min} мин" if active else "—", "в среднем за день занятий"),
    ]
    kpi_html = "\n".join(f'    <div class="kpi"><b>{v}</b><span>{t}</span></div>' for v, t in kpis)
    sub = (f"Колода «IGCSE English», данные Anki на {human(data_time.date())} {data_time.year}, "
           f"{data_time:%H:%M}. Обновляется автоматически каждый день.")
    with open(os.path.join(HERE, "chart_template.html"), encoding="utf-8") as f:
        html = f.read()
    html = (html.replace("__SUB__", sub).replace("__KPIS__", kpi_html)
            .replace("__DAYS_JSON__", json.dumps(days, ensure_ascii=False))
            .replace("__SUBJ_JSON__", json.dumps({"subj": subj, "recent": RECENT_DAYS}, ensure_ascii=False))
            .replace("__INBOX_JSON__", json.dumps({"gap": READ_GAP, "min": READ_MIN})))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Готово: {OUT}  (дней {len(days)}, с занятиями {active}, ответов {ans}, "
          f"начато {words(started, 'слово', 'слова', 'слов')}, в среднем {avg_min} мин в день; учит сейчас: "
          + ", ".join(f"{s['name']} {s['learn']}" for s in subj) + ")")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
