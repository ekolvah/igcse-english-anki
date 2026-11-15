"""Скачивает свежую копию коллекции из AnkiWeb — ТОЛЬКО скачивание, в AnkiWeb ничего не загружает.

Нужен пакет `anki` (pip install anki, версия как у Anki на компьютере). Основную коллекцию Anki
на компьютере не трогает: копия лежит отдельно, в %LOCALAPPDATA%\\zhenya-progress\\collection.anki2.

Первый раз (и если AnkiWeb перестал пускать) — войти, пароль вводится в окне и не сохраняется,
сохраняется только ключ входа (auth.json там же, вне git):
    python .claude/skills/zhenya-progress/ankiweb_sync.py --login
Дальше каждый день (так делает GitHub Actions, .github/workflows/report.yml):
    python .claude/skills/zhenya-progress/ankiweb_sync.py
На сервере GitHub auth.json нет — ключ берётся из переменных ANKIWEB_HKEY и ANKIWEB_ENDPOINT
(секреты репозитория). ZHENYA_DATA — другая папка для копии (по умолчанию как выше).
"""
import argparse
import getpass
import json
import os
import shutil
import sys
import tempfile

DATA_DIR = os.environ.get("ZHENYA_DATA") or os.path.join(
    os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "zhenya-progress")
AUTH_FILE = os.path.join(DATA_DIR, "auth.json")
COL_FILE = os.path.join(DATA_DIR, "collection.anki2")


def login():
    from anki.collection import Collection
    user = input("Почта AnkiWeb: ").strip()
    password = getpass.getpass("Пароль AnkiWeb (при вводе не виден): ")
    tmp = tempfile.mkdtemp(prefix="anki-login-")
    col = Collection(os.path.join(tmp, "collection.anki2"))
    try:
        auth = col.sync_login(user, password, None)
    finally:
        col.close()
        shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(AUTH_FILE, "w", encoding="utf-8") as f:
        json.dump({"hkey": auth.hkey, "endpoint": auth.endpoint}, f)
    print("Вход выполнен, ключ сохранён:", AUTH_FILE)


def download():
    from anki.collection import Collection
    from anki.sync import SyncAuth, SyncOutput
    if os.environ.get("ANKIWEB_HKEY"):
        saved = {"hkey": os.environ["ANKIWEB_HKEY"], "endpoint": os.environ.get("ANKIWEB_ENDPOINT")}
    elif os.path.exists(AUTH_FILE):
        with open(AUTH_FILE, encoding="utf-8") as f:
            saved = json.load(f)
    else:
        sys.exit("Нет входа в AnkiWeb — запустите с --login")
    auth = SyncAuth(hkey=saved["hkey"], endpoint=saved.get("endpoint") or None)

    # Каждый раз — новая ПУСТАЯ коллекция: для неё AnkiWeb всегда отвечает «полное скачивание»,
    # и загружать на сервер нечего (защита от порчи общей колоды Жени).
    tmp = tempfile.mkdtemp(prefix="anki-dl-")
    path = os.path.join(tmp, "collection.anki2")
    col = Collection(path)
    try:
        out = col.sync_collection(auth, sync_media=False)
        if out.new_endpoint:
            auth = SyncAuth(hkey=auth.hkey, endpoint=out.new_endpoint)
        if out.required not in (SyncOutput.FULL_DOWNLOAD, SyncOutput.FULL_SYNC):
            sys.exit(f"Неожиданный ответ AnkiWeb ({out.required}) — скачивание отменено")
        col.close_for_full_sync()
        col.full_upload_or_download(auth=auth, server_usn=None, upload=False)
        # после полного скачивания движок Anki сам заново открывает файл — открыть и закрыть,
        # иначе Windows не даст перенести его на место
        col.reopen(after_full_sync=True)
    finally:
        col.close(downgrade=False)
    os.makedirs(DATA_DIR, exist_ok=True)
    for suffix in ("-wal", "-shm"):  # старые журналы от прошлой копии не должны примешаться
        if os.path.exists(COL_FILE + suffix):
            os.remove(COL_FILE + suffix)
    os.replace(path, COL_FILE)
    shutil.rmtree(tmp, ignore_errors=True)
    print("Скачано из AnkiWeb:", COL_FILE)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--login", action="store_true", help="войти в AnkiWeb (спросит пароль)")
    a = ap.parse_args()
    if a.login:
        login()
    download()
