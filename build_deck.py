"""Собирает колоду Anki IGCSE_Maths_Physics.apkg из текстовых файлов в data/.

Формат строки в data/*.txt:
    term | русский | definition | example | flag
- "# ..."   — комментарий
- "## A::B" — все строки ниже идут в подколоду "IGCSE English::A::B"
- flag "-"  — не делать карточку RU→EN (для очень длинных фраз).
  Старый флаг "+" больше ничего не значит: карточка RU→EN создаётся для всех слов.

Каждое слово даёт две карточки, и в обеих ответ надо напечатать:
  1. EN → RU: видит/слышит английское слово, печатает перевод.
  2. RU → EN: видит перевод и определение, печатает английское слово.
На обороте карточка сама пишет «Верно / Почти / Неверно» (card_check.js).

Запуск:  python build_deck.py
"""
import os
import re
import sys
from pathlib import Path

import genanki

ROOT = Path(__file__).parent
DATA = ROOT / "data"
OUT = ROOT / "IGCSE_Maths_Physics.apkg"
# слова, которые Женя записал сам (колода «Новые слова» → .claude/skills/zhenya-progress/inbox.py)
INBOX_LOG = Path(os.environ.get("ZHENYA_INBOX_LOG") or DATA / "zhenya_inbox.tsv")
ZHENYA_DONE = ("добавлено", "уже было")
ROOT_DECK = "IGCSE English"
CHECK_JS = (ROOT / "card_check.js").read_text(encoding="utf-8")

# Фиксированные ID: не менять, иначе при повторном импорте Anki создаст дубликаты.
MODEL_ID = 1730803200          # v2: ввод ответа в обеих карточках
DECK_ID_BASE = 1730716900
GUID_SALT = "v2"

MAX_EN_WORDS = 6               # длиннее — без карточки RU→EN

CSS = """
.card { font-family: -apple-system, Roboto, "Segoe UI", sans-serif; font-size: 22px;
        text-align: center; color: #1d1d1f; background: #fafafa; padding: 12px; }
.nightMode.card, .night_mode .card { color: #e8e8e8; background: #1e1e1e; }
.term { font-size: 30px; font-weight: 600; }
.ru { font-size: 24px; color: #0b6e4f; }
.nightMode .ru, .night_mode .ru { color: #6fd3a8; }
.def { font-size: 18px; margin-top: 14px; color: #444; }
.nightMode .def, .night_mode .def { color: #bbb; }
.ex { font-size: 17px; margin-top: 10px; font-style: italic; color: #666; }
.nightMode .ex, .night_mode .ex { color: #999; }
.topic { font-size: 12px; color: #999; margin-bottom: 10px; }
.hint { font-size: 14px; color: #999; margin: 12px 0 6px; }
input#typeans { font-size: 22px; }
.typed { font-size: 18px; margin: 6px 0; }
.v { font-size: 26px; font-weight: 700; margin-top: 8px; }
.v.ok { color: #1a8f3c; } .v.almost { color: #b8860b; } .v.wrong { color: #c62828; }
.nightMode .v.ok, .night_mode .v.ok { color: #5fd47f; }
.nightMode .v.almost, .night_mode .v.almost { color: #f0c040; }
.nightMode .v.wrong, .night_mode .v.wrong { color: #ff6b6b; }
.vh { font-size: 15px; color: #888; margin-bottom: 10px; }
#accept { display: none; }
.igb { margin: 22px 0 8px; display: flex; gap: 12px; justify-content: center; flex-wrap: wrap; }
.igbtn { font-size: 20px; font-weight: 600; padding: 14px 26px; border-radius: 12px;
         border: none; color: #fff; cursor: pointer; min-width: 180px; }
.igbtn.ok { background: #1a8f3c; } .igbtn.almost { background: #b8860b; }
.igbtn.wrong { background: #c62828; }
"""


def script(mode: str) -> str:
    return f"<script>\n{CHECK_JS}\nigCheck('{mode}');\n</script>"


def front_script() -> str:
    return f"<script>\n{CHECK_JS}\nigFront();\n</script>"


EN_RU_FRONT = """<div class="topic">{{Topic}}</div>
<div class="term">{{Term}}</div>
{{tts en_GB:Term}}
<div class="hint">Напиши перевод по-русски</div>
{{type:RuMain}}
<div id="igfront"></div>
""" + front_script()

EN_RU_BACK = """<div class="topic">{{Topic}}</div>
<div class="term">{{Term}}</div>
{{tts en_GB:Term}}
<hr id="answer">
{{type:RuMain}}
<div id="verdict"></div>
<div class="ru">{{Russian}}</div>
{{#Definition}}<div class="def">{{Definition}}</div>{{/Definition}}
{{#Example}}<div class="ex">{{Example}}</div>{{/Example}}
<div id="igbuttons"></div>
<div id="accept">{{RuAccept}}</div>
""" + script("ru")

RU_EN_FRONT = """{{#Spell}}<div class="topic">{{Topic}}</div>
<div class="ru">{{RuHint}}</div>
{{#Hint}}<div class="def">{{Hint}}</div>{{/Hint}}
<div class="hint">Напиши по-английски</div>
{{type:Spell}}
<div id="igfront"></div>
""" + front_script() + "{{/Spell}}"

RU_EN_BACK = """<div class="topic">{{Topic}}</div>
<div class="ru">{{RuHint}}</div>
<hr id="answer">
{{type:Spell}}
<div id="verdict"></div>
<div class="term">{{Term}}</div>
{{tts en_GB:Term}}
{{#Example}}<div class="ex">{{Example}}</div>{{/Example}}
<div id="igbuttons"></div>
<div id="accept">{{EnAccept}}</div>
""" + script("en")

FIELDS = ("Term", "Russian", "Definition", "Example", "Spell", "Hint", "Topic",
          "RuMain", "RuAccept", "RuHint", "EnAccept")

MODEL = genanki.Model(
    MODEL_ID,
    "IGCSE Term v2 (typing both ways)",
    fields=[{"name": n} for n in FIELDS],
    templates=[
        {"name": "1 EN → RU (type)", "qfmt": EN_RU_FRONT, "afmt": EN_RU_BACK},
        {"name": "2 RU → EN (type)", "qfmt": RU_EN_FRONT, "afmt": RU_EN_BACK},
    ],
    css=CSS,
)


class TermNote(genanki.Note):
    @property
    def guid(self):
        # Стабильный GUID: версия + подколода + термин. Исправленный перевод
        # при повторном импорте обновит карточку, прогресс сохранится.
        return genanki.guid_for(GUID_SALT, self.fields[6], self.fields[0])


PAREN = re.compile(r"\(([^)]*)\)")


def spelling(term: str) -> str:
    """Ответ для ввода: термин без пояснений в скобках."""
    return re.sub(r"\s*\([^)]*\)", "", term).strip()


def en_accept(term: str) -> list[str]:
    """Термин + сокращение из скобок: HCF, e.m.f., LDR…"""
    out = [spelling(term)]
    if "'" in out[0]:                      # Newton's law → и «Newtons law» тоже
        out.append(out[0].replace("'", ""))
    if term.strip() != out[0]:             # «by (a time)» целиком, как в колоде
        out.append(term.strip())
    for p in PAREN.findall(term):
        p = p.strip()
        if len(p) >= 2 and re.fullmatch(r"[A-Za-z.]+", p) and (
                sum(c.isupper() for c in p) >= 2 or "." in p):
            out.append(p)
    return out


def is_abbrev(s: str) -> bool:
    return bool(re.fullmatch(r"[A-ZА-ЯЁ0-9]{2,6}", s))


def _main_variants(ru: str) -> list[str]:
    main = PAREN.sub(" ", ru)
    main = re.split(r"[.!:—–→]", main)[0]          # всё после пояснения отбрасываем
    variants = [v.strip(" ,;") for v in re.split(r"[,;/]", main)]
    return [re.sub(r"\s+", " ", v) for v in variants if v.strip(" ,;")]


def _top_split(s: str, seps: str) -> list[str]:
    """Разрезать по символам seps, но не внутри скобок."""
    parts, cur, depth = [], "", 0
    for ch in s:
        depth += (ch == "(") - (ch == ")")
        if depth <= 0 and ch in seps:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    return parts + [cur]


def _whole_variants(ru: str) -> list[str]:
    out = [ru.strip()]
    main = _top_split(ru, ".!:—–→")[0]
    for v in _top_split(main, ",;/"):
        v = re.sub(r"\s+", " ", v.strip(" ,;"))
        if "(" in v and v.count("(") == v.count(")"):
            out.append(v)
    return out


def ru_accept(ru: str) -> list[str]:
    """Варианты перевода, которые засчитываются как верные."""
    variants = _main_variants(ru)
    used = set()
    # «(электрический) ток» → ещё и «электрический ток»
    m = re.match(r"\s*\(([^)]+)\)\s*", ru)
    if m:
        used.add(m.group(1).strip())
        variants += _main_variants(m.group(1) + " " + ru[m.end():])
    # «равные (эквивалентные) дроби» → ещё и «эквивалентные дроби»
    for m in re.finditer(r"(\w+) \((\w+)\)(?= \w)", ru):
        used.add(m.group(2))
        variants += _main_variants(ru[:m.start()] + m.group(2) + ru[m.end():])
    # Напечатано ровно как в колоде — тоже верно: «к (сроку), не позже» целиком,
    # и части со скобками: «к (сроку)». Делим только по , ; / вне скобок.
    variants += _whole_variants(ru)
    parens = [p.strip() for p in PAREN.findall(ru) if p.strip() not in used]
    one_word_main = len(variants) == 1 and len(variants[0].split()) == 1
    for p in parens:
        if is_abbrev(p) or is_abbrev(variants[0] if variants else ""):
            if len(p.split()) <= 3 and not re.search(r"[=:]", p):
                variants.append(p)
        elif one_word_main and len(p.split()) == 1 and len(p) >= 5:
            variants.append(p.strip("«»"))
    seen, out = set(), []
    for v in variants:
        if v and v.lower() not in seen:
            seen.add(v.lower())
            out.append(v)
    return out or [ru]


STOP = {"than", "with", "from", "into", "that", "this", "more", "most", "your",
        "the", "and", "for", "are", "its", "per", "your", "not", "but", "all"}


def mask(text: str, term: str) -> str:
    """Скрыть в подсказке само слово и однокоренные, чтобы не выдать ответ."""
    if not text:
        return text
    words = re.findall(r"[A-Za-z]+", spelling(term))
    single = len(words) == 1
    for w in words:
        if len(w) < 3 or (not single and w.lower() in STOP):
            continue
        stem = w[:5] if len(w) >= 6 else w
        pat = (rf"\b{re.escape(stem)}[A-Za-z]*" if len(w) >= 6
               else rf"\b{re.escape(w)}(?:s|es|ed|ing|en|r|er|ers)?\b")
        text = re.sub(pat, "___", text, flags=re.IGNORECASE)
    return text


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def parse(path: Path):
    deck = None
    for n, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or (line.startswith("#") and not line.startswith("## ")):
            continue
        if line.startswith("## "):
            deck = line[3:].strip()
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 2 or not parts[0] or not parts[1]:
            sys.exit(f"{path.name}:{n}: нужно минимум 'term | перевод': {raw!r}")
        if len(parts) > 5:
            sys.exit(f"{path.name}:{n}: больше 5 полей — символ '|' внутри текста? {raw!r}")
        if deck is None:
            sys.exit(f"{path.name}:{n}: строка до первого заголовка '## ...'")
        parts += [""] * (5 - len(parts))
        yield deck, *parts[:5]


# Порядок новых карточек: части идут параллельно по кругу (Maths, Physics, Computer Science,
# Maths, …; кончилась одна часть — дальше остальные), внутри части —
# подколоды верхнего уровня в этом порядке (сначала язык заданий), подколоды — по алфавиту
# полного имени (как сортирует Anki), записи — по порядку в data/*.txt.
STREAMS = {
    "Maths": ["0 Maths question language", "1 Command words", "2 Maths 0580"],
    "Physics": ["4 Answer phrases (Physics)", "3 Physics 0625"],
    "Computer Science": ["5 Computer Science 0478"],
}


def interleave(decks: dict) -> list:
    """Записи всех подколод в порядке изучения (по одной из каждой части STREAMS по кругу).
    decks: полное имя подколоды → список записей (что угодно, лишь бы порядок файла)."""
    streams = []
    for tops in STREAMS.values():
        items = []
        for top in tops:
            prefix = f"{ROOT_DECK}::{top}"
            for name in sorted(n for n in decks if n == prefix or n.startswith(prefix + "::")):
                items += decks[name]
        streams.append(items)
    known = {n for tops in STREAMS.values() for t in tops for n in decks
             if n == f"{ROOT_DECK}::{t}" or n.startswith(f"{ROOT_DECK}::{t}::")}
    if unknown := set(decks) - known:
        sys.exit(f"Подколоды не входят ни в одну часть STREAMS: {sorted(unknown)}")
    return [s[i] for i in range(max(map(len, streams))) for s in streams if i < len(s)]


def zhenya_first() -> list[str]:
    """Термины (lower) слов Жени со статусом «добавлено»/«уже было» — в порядке записи.
    Раз спросил — слово нужно сейчас: такие записи получают первые позиции (решение 2026-11-15)."""
    if not INBOX_LOG.exists():
        return []
    lines = INBOX_LOG.read_text(encoding="utf-8").splitlines()
    head, out = lines[0].split("\t"), []
    for line in lines[1:]:
        r = dict(zip(head, line.split("\t")))
        term = r.get("term", "").strip().lower()
        if r.get("status") in ZHENYA_DONE and term and term not in out:
            out.append(term)
    return out


def build():
    """Подколоды с записями; у записей уже стоит позиция (note.due)."""
    decks: dict[str, genanki.Deck] = {}
    seen: set[tuple[str, str]] = set()
    notes = cards = 0

    for path in sorted(DATA.glob("*.txt")):
        for deck_name, term, ru, definition, example, flag in parse(path):
            full = f"{ROOT_DECK}::{deck_name}"
            key = (full, term.lower())
            if key in seen:
                print(f"  дубликат пропущен: {term!r} в {deck_name}")
                continue
            seen.add(key)
            if full not in decks:
                decks[full] = genanki.Deck(DECK_ID_BASE + len(decks), full)

            spell = spelling(term)
            if flag == "-" or "…" in spell or len(spell.split()) > MAX_EN_WORDS:
                spell = ""
            ru_vars = ru_accept(ru)
            topic = deck_name.split("::")[-1]
            tag = deck_name.split("::")[0].split(" ", 1)[-1].split()[0].lower()

            fields = [term, ru, definition, example, spell,
                      mask(definition, term) if spell else "", topic,
                      ru_vars[0], "|".join(ru_vars),
                      mask(ru, term), "|".join(en_accept(term))]
            decks[full].add_note(TermNote(model=MODEL, fields=[esc(f) for f in fields],
                                          tags=[tag]))
            notes += 1
            cards += 2 if spell else 1

    # позиция новой карточки (Anki: «по возрастанию позиции»); обе карточки записи — одна позиция.
    # Сначала слова Жени (метка zhenya), потом все остальные по очереди частей STREAMS.
    by_term = {n.fields[0].lower(): n for d in decks.values() for n in d.notes}
    first = zhenya_first()
    first = [esc(t) for t in first]  # поля записей уже экранированы
    if missing := [t for t in first if t not in by_term]:
        sys.exit(f"{INBOX_LOG.name}: термина нет в data/*.txt: {missing}")
    front = [by_term[t] for t in first]
    for note in front:
        note.tags.append("zhenya")
    front_ids = set(map(id, front))
    rest = [n for n in interleave({n: d.notes for n, d in decks.items()}) if id(n) not in front_ids]
    for pos, note in enumerate(front + rest, 1):
        note.due = pos
    return decks, notes, cards


def positions() -> dict[str, int]:
    """guid записи → позиция; использует anki_settings.py, чтобы в коллекции был тот же порядок."""
    return {note.guid: note.due for d in build()[0].values() for note in d.notes}


def main():
    decks, notes, cards = build()
    genanki.Package(list(decks.values())).write_to_file(OUT)
    print(f"Готово: {OUT}")
    print(f"Подколод: {len(decks)}, записей: {notes}, карточек: {cards}")
    for name, d in decks.items():
        print(f"  {len(d.notes):4}  {name}")


if __name__ == "__main__":
    main()
