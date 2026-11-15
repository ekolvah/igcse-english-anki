"""Импорт IGCSE_Maths_Physics.apkg агентом — вместо пользователя (Anki на компьютере ЗАКРЫТ).

Порядок (так сделано 2026-11-13):
  python .claude/skills/add-words/anki_import.py pull     # 1. подтянуть занятия с телефона (AnkiWeb)
  python .claude/skills/add-words/anki_import.py import   # 2. импорт («если новее», без расписания)
  python anki_settings.py                                 # 3. только если есть новая подколода
  python .claude/skills/add-words/anki_import.py push     # 4. отправить в AnkiWeb
Шаг 1 обязателен: иначе anki_settings.py поменяет позиции у карточек, которые Женя уже начал на
телефоне, и при синхронизации его прогресс по ним откатится. pull останавливается, если на
компьютере есть несинхронизированные изменения; pull/push — только обычная синхронизация, при
требовании полной останавливается. Перед каждым шагом — копия коллекции в backups/ профиля.
Нужны пакет anki (версия как у Anki на компьютере) и вход в AnkiWeb (auth.json от ankiweb_sync.py).
"""
import datetime as dt
import glob
import json
import os
import shutil
import subprocess
import sys

from anki.collection import Collection, ImportAnkiPackageOptions, ImportAnkiPackageRequest
from anki.import_export_pb2 import IMPORT_ANKI_PACKAGE_UPDATE_CONDITION_IF_NEWER as IF_NEWER
from anki.sync import SyncAuth, SyncOutput

sys.stdout.reconfigure(encoding="utf-8")
# Папка профиля Anki: переменная ANKI_PROFILE или единственный профиль с коллекцией в %APPDATA%\Anki2
_found = glob.glob(os.path.join(os.environ.get("APPDATA", ""), "Anki2", "*", "collection.anki2"))
PROFILE = os.environ.get("ANKI_PROFILE") or (os.path.dirname(_found[0]) if len(_found) == 1 else "")
COL = os.path.join(PROFILE, "collection.anki2")
AUTH = os.path.expandvars(r"%LOCALAPPDATA%\zhenya-progress\auth.json")
APKG = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     "..", "..", "..", "IGCSE_Maths_Physics.apkg"))
BACKUP = os.path.join(PROFILE, "backups")


def anki_running():
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq anki.exe"], capture_output=True, text=True).stdout
    return "anki.exe" in out.lower()


def auth():
    with open(AUTH, encoding="utf-8") as f:
        s = json.load(f)
    return SyncAuth(hkey=s["hkey"], endpoint=s.get("endpoint") or None)


def state(col, label):
    n = col.db.scalar("select count(*) from revlog")
    mod, ls, scm = col.db.first("select mod, ls, scm from col")
    notes = col.db.scalar("select count(*) from notes")
    print(f"[{label}] ответов {n}, записей {notes}, mod {mod}, ls {ls}, scm {scm}")
    return mod, ls, scm


def sync(col, allow_local_changes):
    mod, ls, _ = state(col, "до синхронизации")
    if not allow_local_changes and mod > ls:
        sys.exit("На компьютере есть несинхронизированные изменения — остановлено")
    out = col.sync_collection(auth(), sync_media=False)
    names = {v: k for k, v in SyncOutput.ChangesRequired.items()}
    print("AnkiWeb:", names.get(out.required, out.required), out.server_message or "")
    if out.required not in (SyncOutput.NO_CHANGES, SyncOutput.NORMAL_SYNC):
        sys.exit("Требуется ПОЛНАЯ синхронизация — ничего не делаю, нужен человек")
    state(col, "после синхронизации")


def main(step):
    if anki_running():
        sys.exit("Anki открыт — закройте его")
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    shutil.copy2(COL, os.path.join(BACKUP, f"before-anki_import-{step}-{stamp}.anki2"))
    col = Collection(COL)
    try:
        if step == "pull":
            sync(col, allow_local_changes=False)
        elif step == "push":
            sync(col, allow_local_changes=True)
        elif step == "import":
            _, _, scm0 = state(col, "до импорта")
            req = ImportAnkiPackageRequest(package_path=APKG, options=ImportAnkiPackageOptions(
                merge_notetypes=False, update_notes=IF_NEWER, update_notetypes=IF_NEWER,
                with_scheduling=False, with_deck_configs=False))
            log = col.import_anki_package(req).log
            print("новых:", len(log.new), "обновлено:", len(log.updated), "без изменений:",
                  len(log.duplicate), "конфликт типа:", len(log.conflicting),
                  "первое поле совпало:", len(log.first_field_match), "пропущено:", len(log.missing_notetype))
            _, _, scm1 = state(col, "после импорта")
            print("схема изменилась (нужна полная синхронизация)!" if scm1 != scm0 else "схема не изменилась")
        else:
            sys.exit("шаг: pull | import | push")
    finally:
        col.close()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "")
