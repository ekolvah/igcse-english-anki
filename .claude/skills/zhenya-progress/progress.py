"""Отчёт о занятиях Жени по колоде IGCSE English — читает КОПИЮ коллекции Anki (только чтение).

Запуск:  python .claude/skills/zhenya-progress/progress.py [--days 7] [--top 15]
Нужен только стандартный Python. Anki можно не закрывать: файл коллекции (+ -wal) копируется
во временную папку, оригинал не открывается. Данные с телефона видны только после синхронизации
телефона и компьютера.
"""
import argparse
import datetime as dt
import glob
import os
import re
import shutil
import sqlite3
import sys
import tempfile
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8")

# Папка профиля Anki: переменная ANKI_PROFILE или единственный профиль с коллекцией в %APPDATA%\Anki2
_found = glob.glob(os.path.join(os.environ.get("APPDATA", ""), "Anki2", "*", "collection.anki2"))
PROFILE = os.environ.get("ANKI_PROFILE") or (os.path.dirname(_found[0]) if len(_found) == 1 else "")
ROOT = "IGCSE English"
STREAM_OF_TOP = {"0": "Maths", "1": "Maths", "2": "Maths", "3": "Physics", "4": "Physics",
                 "5": "Computer Science"}
INBOX = "Новые слова"  # колода-ящик: сюда Женя пишет незнакомые слова (inbox.py; создаёт anki_settings.py)
IGCSE_MODELS = (1730716800, 1730803200)  # типы записей колоды (старый и MODEL_ID из build_deck.py)
ROLLOVER_H = 4  # новый день в Anki начинается в 4:00
F_TERM, F_RUMAIN = 0, 7  # индексы полей Term и RuMain (FIELDS в build_deck.py)
DIRECTION = {0: "EN→RU", 1: "RU→EN"}


def open_copy(profile):
    src = os.path.join(profile, "collection.anki2")
    tmp = tempfile.mkdtemp(prefix="anki-copy-")
    for suffix in ("", "-wal"):
        if os.path.exists(src + suffix):
            shutil.copy2(src + suffix, os.path.join(tmp, "collection.anki2" + suffix))
    con = sqlite3.connect(os.path.join(tmp, "collection.anki2"))
    con.create_collation("unicase", lambda a, b: (a.lower() > b.lower()) - (a.lower() < b.lower()))
    return con, tmp


def anki_day(ms):
    return (dt.datetime.fromtimestamp(ms / 1000) - dt.timedelta(hours=ROLLOVER_H)).date()


def clean(s):
    return re.sub(r"<[^>]+>", "", s or "").replace("&nbsp;", " ").strip()


def pct(ok, total):
    return f"{100 * ok / total:.0f}%" if total else "—"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7, help="за сколько последних дней")
    ap.add_argument("--top", type=int, default=15, help="сколько трудных слов показать")
    ap.add_argument("--profile", default=PROFILE)
    a = ap.parse_args()

    con, tmp = open_copy(a.profile)
    try:
        stream = {}  # deck id -> Maths / Physics / Computer Science
        for did, name in con.execute("select id, name from decks"):
            parts = name.split("\x1f")
            if parts[0] == ROOT and len(parts) > 1:
                stream[did] = STREAM_OF_TOP.get(parts[1][:1], "?")
        if not stream:
            sys.exit(f"Колода «{ROOT}» не найдена в {a.profile}")
        ids = ",".join(map(str, stream))

        cards = {}  # cid -> (stream, nid, ord, type, lapses)
        for cid, did, odid, nid, ord_, ctype, lapses in con.execute(
                f"select id, did, odid, nid, ord, type, lapses from cards "
                f"where did in ({ids}) or odid in ({ids})"):
            cards[cid] = (stream.get(did) or stream.get(odid), nid, ord_, ctype, lapses)

        today = anki_day(dt.datetime.now().timestamp() * 1000)
        start = today - dt.timedelta(days=a.days - 1)
        start_ms = int((dt.datetime.combine(start, dt.time()) +
                        dt.timedelta(hours=ROLLOVER_H)).timestamp() * 1000)

        first_seen = dict(con.execute("select cid, min(id) from revlog group by cid"))
        per_day = defaultdict(lambda: [0, 0, 0, 0])  # ответы, верно, мс, новых
        per_stream = defaultdict(lambda: [0, 0])
        review = [0, 0]  # повторения с интервалом (type=1): всего, верно
        wrong_by_card = defaultdict(int)
        for rid, cid, ease, rtype, ms in con.execute(
                "select id, cid, ease, type, time from revlog where id >= ? "
                "and ease > 0 and type in (0, 1, 2) order by id", (start_ms,)):
            if cid not in cards:
                continue
            ok = ease > 1
            d = per_day[anki_day(rid)]
            d[0] += 1; d[1] += ok; d[2] += ms
            if first_seen.get(cid) == rid:
                d[3] += 1
            s = per_stream[cards[cid][0]]
            s[0] += 1; s[1] += ok
            if rtype == 1:
                review[0] += 1; review[1] += ok
            if not ok:
                wrong_by_card[cid] += 1

        print(f"Период: {start} … {today} ({a.days} дн.)\n")
        print("День        Ответов  Верно   Минут  Новых")
        for i in range(a.days):
            day = start + dt.timedelta(days=i)
            n, ok, ms, new = per_day.get(day, [0, 0, 0, 0])
            print(f"{day}  {n:7}  {pct(ok, n):>5}  {ms / 60000:6.0f}  {new:5}")
        tot = [sum(v[k] for v in per_day.values()) for k in range(4)]
        active = sum(1 for v in per_day.values() if v[0])
        print(f"Итого       {tot[0]:7}  {pct(tot[1], tot[0]):>5}  {tot[2] / 60000:6.0f}  {tot[3]:5}"
              f"   (дней с занятиями: {active} из {a.days})")
        if tot[0]:
            print(f"Среднее время на ответ: {tot[2] / tot[0] / 1000:.0f} с")

        print("\nПо частям:", ", ".join(
            f"{k} — {v[0]} ответов, {pct(v[1], v[0])} верно" for k, v in sorted(per_stream.items()))
              or "нет ответов")
        print(f"Повторения выученного (интервал ≥ 1 дня): {review[0]}, верно {pct(review[1], review[0])}")

        state = defaultdict(lambda: [0, 0, 0])  # новые, учатся, выучены
        for st, _nid, _o, ctype, _l in cards.values():
            # cards.type: 0 новая, 1 изучается, 2 на повторении, 3 переучивается
            state[st][{0: 0, 1: 1, 3: 1}.get(ctype, 2)] += 1
        print("\nКарточки всего (новые / изучаются / на повторении):")
        for st, (n0, n1, n2) in sorted(state.items()):
            print(f"  {st}: {n0} / {n1} / {n2}")

        notes = {nid: (flds.split("\x1f"), tags) for nid, flds, tags in con.execute(
            f"select id, flds, tags from notes where id in "
            f"(select nid from cards where did in ({ids}) or odid in ({ids}))")}
        leeches = [nid for nid, (_f, tags) in notes.items() if " leech " in f" {tags.lower()} "]

        print(f"\nТрудные слова за период (ошибок; всего забываний):")
        hard = sorted(wrong_by_card.items(), key=lambda kv: (-kv[1], -cards[kv[0]][4]))[:a.top]
        for cid, wrong in hard:
            st, nid, ord_, _t, lapses = cards[cid]
            f = notes[nid][0]
            print(f"  {wrong:2} ; {lapses:2}  {DIRECTION.get(ord_, ord_)}  "
                  f"{clean(f[F_TERM])} — {clean(f[F_RUMAIN])}  [{st}]")
        if not hard:
            print("  нет")
        print(f"\nПиявки (метка leech): {len(leeches)}")
        for nid in leeches[:a.top]:
            f = notes[nid][0]
            print(f"  {clean(f[F_TERM])} — {clean(f[F_RUMAIN])}")
    finally:
        con.close()
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
