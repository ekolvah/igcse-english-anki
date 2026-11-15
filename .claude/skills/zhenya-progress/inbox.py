"""Новые слова Жени: что он сам записал в AnkiDroid в колоду-ящик «Новые слова» → data/zhenya_inbox.tsv.

    python .claude/skills/zhenya-progress/inbox.py [--source synced|desktop]

synced (по умолчанию) — копия, скачанная ankiweb_sync.py; desktop — коллекция Anki на компьютере.
Каждую ночь запускает .github/workflows/report.yml и сохраняет файл в git: записи в ящике после
обработки удаляются, а история нужна для графика «Новые слова от Жени» (daily_chart.py).

Запись ящика — любая запись в колоде «Новые слова» и любая запись не нашего типа (IGCSE_MODELS)
в других колодах: вдруг Женя выбрал не ту колоду. Первое поле — слово, остальные — где встретил.
Строка файла: id записи (время создания, мс) | день (день Anki, с 4:00) | слово | контекст |
статус | что сделано | термин. Статусы:
  «ждёт» — в ящике, не обработано;
  «добавлено» / «уже было» — ставит тот, кто обработал слово (ночью Claude по
      .claude/skills/add-words/nightly_prompt.md, или агент на компьютере); «термин» — точный
      термин колоды: build_deck.py ставит такие слова первыми, zhenya_apply.py убирает их из ящика;
  «непонятно» — Claude не понял слово (причина в «что сделано»), запись остаётся в ящике;
      Женя исправил слово — снова «ждёт»;
  «удалено» — запись пропала из ящика до обработки.
Слово со статусом «ждёт» обновляется, если Женя его исправил. Файл можно править руками.
В GitHub Actions пишет в $GITHUB_OUTPUT waiting=<сколько ждёт>.
"""
import argparse
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import progress as p  # noqa: E402
from ankiweb_sync import DATA_DIR  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
LOG = os.environ.get("ZHENYA_INBOX_LOG") or os.path.join(ROOT_DIR, "data", "zhenya_inbox.tsv")
COLUMNS = ["id", "day", "word", "context", "status", "result", "term"]
WAITING, UNCLEAR, GONE = "ждёт", "непонятно", "удалено"
DONE = ("добавлено", "уже было")  # обработано: термин в колоде, запись убирается из ящика


def text(field):
    s = re.sub(r"<br\s*/?>|</div>", " ", field or "", flags=re.I)
    s = re.sub(r"<[^>]+>", "", s).replace("&nbsp;", " ").replace("&amp;", "&")
    s = s.replace("&lt;", "<").replace("&gt;", ">")
    return " ".join(s.split())  # без табуляций и переносов строк — они ломают TSV


def read_log(path=LOG):
    """Строки файла: {id: {колонка: значение}} в порядке файла."""
    rows = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            next(f, None)  # заголовок
            for line in f:
                if line.strip():
                    vals = (line.rstrip("\n").split("\t") + [""] * len(COLUMNS))[:len(COLUMNS)]
                    rows[vals[0]] = dict(zip(COLUMNS, vals))
    return rows


def write_log(rows, path=LOG):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\t".join(COLUMNS) + "\n")
        for r in sorted(rows.values(), key=lambda r: int(r["id"])):
            f.write("\t".join(text(r[c]) for c in COLUMNS) + "\n")


def inbox_notes(src_dir):
    """Записи ящика в коллекции: [(id, слово, контекст)]. None — колоды «Новые слова» нет."""
    con, tmp = p.open_copy(src_dir)
    try:
        dids = [did for did, name in con.execute("select id, name from decks")
                if name.split("\x1f")[0] == p.INBOX]
        if not dids:
            return None
        models = ",".join(map(str, p.IGCSE_MODELS))
        rows = con.execute(
            f"select id, flds from notes where mid not in ({models}) or id in "
            f"(select nid from cards where did in ({','.join(map(str, dids))}))").fetchall()
    finally:
        con.close()
        shutil.rmtree(tmp, ignore_errors=True)
    out = []
    for nid, flds in rows:
        fields = [text(x) for x in flds.split("\x1f")]
        fields = [x for x in fields if x]
        if fields:
            out.append((nid, fields[0], " / ".join(fields[1:])))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["synced", "desktop"], default="synced")
    a = ap.parse_args()
    src_dir = DATA_DIR if a.source == "synced" else p.PROFILE
    if not os.path.exists(os.path.join(src_dir, "collection.anki2")):
        sys.exit(f"Нет коллекции в {src_dir}")
    notes = inbox_notes(src_dir)
    if notes is None:
        sys.exit(f"В коллекции нет колоды «{p.INBOX}» — файл не тронут (создаёт её anki_settings.py)")

    rows = read_log()
    now = {str(nid) for nid, _w, _c in notes}
    added = 0
    for nid, word, context in notes:
        r = rows.get(str(nid))
        if r is None:
            rows[str(nid)] = {"id": str(nid), "day": p.anki_day(nid).isoformat(), "word": word,
                              "context": context, "status": WAITING, "result": "", "term": ""}
            added += 1
        elif r["status"] == UNCLEAR and (r["word"], r["context"]) != (word, context):
            r["word"], r["context"], r["status"], r["result"] = word, context, WAITING, ""
        elif r["status"] == WAITING:
            r["word"], r["context"] = word, context
    for r in rows.values():
        if r["status"] in (WAITING, UNCLEAR) and r["id"] not in now:
            r["status"], r["result"] = GONE, "убрано из «Новых слов» до обработки"
    write_log(rows)
    waiting = [r for r in rows.values() if r["status"] == WAITING]
    print(f"{LOG}: в ящике {len(notes)}, новых {added}, ждут обработки {len(waiting)}, всего в истории {len(rows)}")
    for r in waiting:
        print(f"  {r['day']}  {r['word']}" + (f"  ({r['context']})" if r["context"] else ""))
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
            f.write(f"waiting={len(waiting)}\n")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
