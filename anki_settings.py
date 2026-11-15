"""Настройки колоды IGCSE English в коллекции Anki (через официальную библиотеку Anki).

Что делает (можно запускать повторно — результат тот же):
  * наборы настроек «Maths» (подколоды 0, 1, 2), «Physics» (3, 4) и «Computer Science» (5):
    по 10 новых в день,
    300 повторений, максимальный интервал 60 дней, пиявка после 5 ошибок (только метка);
  * главная «IGCSE English» («По умолчанию»): 20 новых, 300 повторений — общий потолок;
  * новые карточки берутся «по позиции»; позиции новых карточек выравниваются по build_deck.py
    (Maths / Physics / Computer Science по очереди, порядок — STREAMS в build_deck.py).
    Позиции новым словам ставит уже сама сборка (импорт Anki 26.9 их сохраняет, проверено
    2026-11-04), поэтому после обычного импорта новых слов скрипт НЕ нужен. Нужен, если импорт
    создал новую подколоду (она получает пресет «По умолчанию») или сбились пресеты.

Запуск (Anki на компьютере ЗАКРЫТ, перед этим синхронизировать телефон и компьютер):
  python -m venv ankienv && ankienv\\Scripts\\python -m pip install anki==26.9.4 genanki
  ankienv\\Scripts\\python anki_settings.py            # путь к коллекции по умолчанию
Потом открыть Anki → «Синхронизировать» → синхронизировать телефон (полная синхронизация не нужна).
"""
import datetime
import glob
import os
import shutil
import subprocess
import sys

from anki.collection import Collection

import build_deck
from anki.deck_config_pb2 import DeckConfig

sys.stdout.reconfigure(encoding="utf-8")

# Папка профиля Anki: переменная ANKI_PROFILE или единственный профиль с коллекцией в %APPDATA%\Anki2
_found = glob.glob(os.path.join(os.environ.get("APPDATA", ""), "Anki2", "*", "collection.anki2"))
PROFILE = os.environ.get("ANKI_PROFILE") or (os.path.dirname(_found[0]) if len(_found) == 1 else "")
ROOT = "IGCSE English"
STREAMS = build_deck.STREAMS  # какие подколоды в Maths, Physics, Computer Science
PER_STREAM_NEW, ROOT_NEW, REVIEWS, MAX_IVL, LEECH = 10, 20, 300, 60, 5
LOWEST_POSITION = DeckConfig.Config.NEW_CARD_GATHER_PRIORITY_LOWEST_POSITION


def anki_running():
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq anki.exe"],
                         capture_output=True, text=True).stdout
    return "anki.exe" in out.lower()


def set_values(conf, new):
    conf["new"]["perDay"] = new
    conf["rev"]["perDay"] = REVIEWS
    conf["rev"]["maxIvl"] = MAX_IVL
    conf["lapse"]["leechFails"] = LEECH
    conf["lapse"]["leechAction"] = 1  # 1 = только пометить
    conf["newGatherPriority"] = LOWEST_POSITION


def main(path):
    if anki_running():
        sys.exit("Anki открыт — закройте его и запустите снова.")
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    folder = os.path.join(os.path.dirname(os.path.abspath(path)), "backups")
    if not os.path.isdir(folder):
        folder = os.path.dirname(os.path.abspath(path))
    backup = os.path.join(folder, f"before-anki_settings-{stamp}.anki2")
    shutil.copy2(path, backup)
    print("Резервная копия:", backup)

    col = Collection(path)
    dm = col.decks
    scm_before = col.db.scalar("select scm from col")

    default = dm.get_config(1)
    preset_ids = {}
    for name in STREAMS:
        found = [c for c in dm.all_config() if c["name"] == name]
        conf = found[0] if found else dm.get_config(
            dm.add_config_returning_id(name, clone_from=default))
        set_values(conf, PER_STREAM_NEW)
        dm.update_config(conf)
        preset_ids[name] = conf["id"]
    set_values(default, ROOT_NEW)
    dm.update_config(default)

    # подколоды → наборы
    for name, tops in STREAMS.items():
        for top in tops:
            for did in dm.deck_and_child_ids(dm.id_for_name(f"{ROOT}::{top}")):
                deck = dm.get(did)
                deck["conf"] = preset_ids[name]
                dm.save(deck)

    # позиции новых карточек — те же, что ставит build_deck.py (части STREAMS по очереди;
    # обе карточки записи — одна позиция), чтобы новые слова из следующего импорта встали на место
    pos = build_deck.positions()
    ids = ",".join(map(str, dm.deck_and_child_ids(dm.id_for_name(ROOT))))
    rows = col.db.all(f"select c.id, n.guid, c.due from cards c join notes n on n.id = c.nid "
                      f"where c.type = 0 and c.did in ({ids})")
    if missing := [g for _, g, _ in rows if g not in pos]:
        print(f"Внимание: {len(missing)} новых карточек нет в data/*.txt — позиции не тронуты.")
    changed = []
    for cid, guid, due in rows:
        if guid in pos and due != pos[guid]:
            card = col.get_card(cid)
            card.due = pos[guid]
            changed.append(card)
    if changed:
        col.update_cards(changed)
    col.set_config("nextPos", max(pos.values()) + 1)

    assert col.db.scalar("select scm from col") == scm_before, "схема изменилась — нужна полная синхронизация!"
    print(f"Наборы: {preset_ids}; новых карточек {len(rows)}, позиций изменено у {len(changed)}.")
    col.close()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(PROFILE, "collection.anki2"))
