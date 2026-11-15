"""Слова Жени → колода в AnkiWeb, без человека (ночью в .github/workflows/report.yml).

    python .claude/skills/add-words/zhenya_apply.py            # сухой прогон: в AnkiWeb не отправляет
    python .claude/skills/add-words/zhenya_apply.py --push     # по-настоящему

До запуска: ankiweb_sync.py скачал свежую копию коллекции, inbox.py обновил data/zhenya_inbox.tsv,
Claude (nightly_prompt.md) дописал строки в data/*.txt и поставил словам статус и термин.
Здесь — только проверяемые шаги, без ИИ:
  1. сборка build_deck.py (слова Жени — первые позиции, метка zhenya);
  2. проверки — при любой ошибке ничего не отправляется, выход с ошибкой (письмо владельцу):
     все записи колоды из коллекции есть в сборке (ничего не переименовано и не перенесено),
     нет новых подколод, новых записей не больше MAX_NEW, у слов «добавлено»/«уже было» термин в сборке;
  3. на КОПИИ коллекции: обычная синхронизация (подтянуть, что пришло после скачивания) → импорт
     (как anki_import.py: «если новее», без расписания и пресетов) → позиции всех не начатых
     карточек по сборке (слова Жени впереди) → уже начатые слова этой ночи — к повторению
     сегодня → убрать обработанные записи из ящика «Новые слова»;
  4. --push: обычная синхронизация с AnkiWeb (полную — никогда), копия встаёт на место скачанной,
     чтобы страницы отчёта показали уже новое.
Ключ AnkiWeb — ANKIWEB_HKEY / ANKIWEB_ENDPOINT или auth.json (как в ankiweb_sync.py).
"""
import argparse
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, ROOT_DIR)
sys.path.insert(0, os.path.join(ROOT_DIR, ".claude", "skills", "zhenya-progress"))
import build_deck  # noqa: E402
import inbox as ib  # noqa: E402
from ankiweb_sync import AUTH_FILE, COL_FILE  # noqa: E402

from anki.collection import Collection, ImportAnkiPackageOptions, ImportAnkiPackageRequest  # noqa: E402
from anki.import_export_pb2 import IMPORT_ANKI_PACKAGE_UPDATE_CONDITION_IF_NEWER as IF_NEWER  # noqa: E402
from anki.sync import SyncAuth, SyncOutput  # noqa: E402

MAX_NEW = 40  # больше новых записей за ночь — подозрительно, нужен человек


def auth():
    if os.environ.get("ANKIWEB_HKEY"):
        s = {"hkey": os.environ["ANKIWEB_HKEY"], "endpoint": os.environ.get("ANKIWEB_ENDPOINT")}
    else:
        with open(AUTH_FILE, encoding="utf-8") as f:
            s = json.load(f)
    return SyncAuth(hkey=s["hkey"], endpoint=s.get("endpoint") or None)


def sync(col, label):
    out = col.sync_collection(auth(), sync_media=False)
    names = {v: k for k, v in SyncOutput.ChangesRequired.items()}
    print(f"AnkiWeb ({label}):", names.get(out.required, out.required), out.server_message or "")
    if out.required not in (SyncOutput.NO_CHANGES, SyncOutput.NORMAL_SYNC):
        sys.exit("Требуется ПОЛНАЯ синхронизация — ничего не отправлено, нужен человек")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--push", action="store_true", help="отправить в AnkiWeb (без него — сухой прогон)")
    a = ap.parse_args()

    rows = ib.read_log()
    done = {r["id"]: r for r in rows.values() if r["status"] in ib.DONE}

    # 1. сборка
    decks, n_notes, _ = build_deck.build()
    import genanki
    tmp = tempfile.mkdtemp(prefix="zhenya-apply-")
    apkg = os.path.join(tmp, "deck.apkg")
    genanki.Package(list(decks.values())).write_to_file(apkg)
    build_guids = {n.guid for d in decks.values() for n in d.notes}
    build_terms = {n.fields[0].lower() for d in decks.values() for n in d.notes}
    pos = {n.guid: n.due for d in decks.values() for n in d.notes}
    front = {n.guid for d in decks.values() for n in d.notes if "zhenya" in n.tags}

    path = os.path.join(tmp, "collection.anki2")
    shutil.copy2(COL_FILE, path)
    col = Collection(path)
    try:
        # 2. проверки
        errors = []
        mid = build_deck.MODEL_ID
        col_guids = set(col.db.list(f"select guid from notes where mid = {mid}"))
        if gone := col_guids - build_guids:
            errors.append(f"{len(gone)} записей колоды нет в сборке — переименованы или перенесены?")
        col_decks = {d.name for d in col.decks.all_names_and_ids()}
        if new_decks := set(decks) - col_decks:
            errors.append(f"новые подколоды (только с согласия пользователя): {sorted(new_decks)}")
        new = build_guids - col_guids
        if len(new) > MAX_NEW:
            errors.append(f"новых записей {len(new)} > {MAX_NEW}")
        for r in done.values():
            if build_deck.esc(r["term"]).lower() not in build_terms:
                errors.append(f"слово «{r['word']}»: термина «{r['term']}» нет в колоде")
        if errors:
            sys.exit("Проверка не прошла, в AnkiWeb ничего не отправлено:\n  " + "\n  ".join(errors))
        print(f"Сборка: записей {n_notes}, новых {len(new)}, слов Жени первыми {len(front)}")

        # 3. синхронизация, импорт, позиции, ящик
        scm0 = col.db.scalar("select scm from col")
        if a.push:
            sync(col, "подтянуть")
        req = ImportAnkiPackageRequest(package_path=apkg, options=ImportAnkiPackageOptions(
            merge_notetypes=False, update_notes=IF_NEWER, update_notetypes=IF_NEWER,
            with_scheduling=False, with_deck_configs=False))
        log = col.import_anki_package(req).log
        print("Импорт: новых", len(log.new), "обновлено", len(log.updated),
              "конфликт типа", len(log.conflicting), "пропущено", len(log.missing_notetype))

        # все не начатые карточки — на позиции сборки (как anki_settings.py): слова Жени впереди,
        # остальные сдвигаются за ними. Безопасно: копия только что скачана и синхронизирована.
        moved, front_new = [], set()
        for cid, guid, due in col.db.all(
                f"select c.id, n.guid, c.due from cards c join notes n on n.id = c.nid "
                f"where c.type = 0 and n.mid = {mid}"):
            if guid in front:
                front_new.add(guid)
            if due != pos[guid]:
                card = col.get_card(cid)
                card.due = pos[guid]
                moved.append(card)
        if moved:
            col.update_cards(moved)
        col.set_config("nextPos", max(pos.values()) + 1)
        first = col.db.list(
            f"select distinct n.guid from cards c join notes n on n.id = c.nid where c.type = 0 "
            f"and n.mid = {mid} order by c.due limit {len(front_new) or 1}")
        print(f"Позиции выровнены по сборке у {len(moved)} новых карточек; не начатых слов Жени "
              f"{len(front_new)} (уже учит — {len(front) - len(front_new)}), они первые: "
              f"{'да' if set(first) == front_new or not front_new else 'НЕТ'}")

        inbox_dids = [d.id for d in col.decks.all_names_and_ids() if d.name == ib.p.INBOX]
        in_box = set(col.db.list(
            f"select id from notes where mid not in ({','.join(map(str, ib.p.IGCSE_MODELS))}) or id in "
            f"(select nid from cards where did in ({','.join(map(str, inbox_dids)) or 'null'}))"))
        remove = [int(i) for i in done if int(i) in in_box]

        # слово из ящика, которое Женя уже учит (повторение не сегодня), — к повторению сегодня:
        # спросил, значит, слово нужно сейчас. Только слова этой ночи, не все прежние.
        by_term = {n.fields[0].lower(): n.guid for d in decks.values() for n in d.notes}
        asked = {by_term[build_deck.esc(done[str(i)]["term"]).lower()] for i in remove}
        today = col.sched.today
        due_now = [cid for cid, guid in col.db.all(
            f"select c.id, n.guid from cards c join notes n on n.id = c.nid "
            f"where n.mid = {mid} and c.type = 2 and c.queue = 2 and c.due > {today}") if guid in asked]
        if due_now:
            col.sched.set_due_date(due_now, "0")
        print(f"Уже начатых карточек слов Жени — к повторению сегодня: {len(due_now)}")

        if remove:
            col.remove_notes(remove)
        print(f"Из ящика «{ib.p.INBOX}» убрано: {len(remove)}")
        if col.db.scalar("select scm from col") != scm0:
            sys.exit("Схема коллекции изменилась — нужна полная синхронизация, ничего не отправлено")

        # 4. отправка
        if not a.push:
            print("Сухой прогон: в AnkiWeb ничего не отправлено.")
            return
        sync(col, "отправить")
    finally:
        col.close()
    shutil.copy2(path, COL_FILE)  # страницы отчёта строятся уже по новой коллекции
    for suffix in ("-wal", "-shm"):
        if os.path.exists(COL_FILE + suffix):
            os.remove(COL_FILE + suffix)
    shutil.rmtree(tmp, ignore_errors=True)
    print("Отправлено в AnkiWeb.")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
