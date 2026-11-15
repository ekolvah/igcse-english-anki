"""Проверка новых строк data/*.txt до сборки колоды.

Запуск (из корня проекта):
    PYTHONIOENCODING=utf-8 python .claude/skills/add-words/check_words.py data/08_new.txt [ещё файлы]

Для каждой строки печатает, какие ответы засчитаются (RU и EN), подсказку RU→EN после маскировки,
и предупреждения (!). Предупреждения — не обязательно ошибки, но каждое надо посмотреть глазами.
"""
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
PROJECT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT))
import build_deck as b  # noqa: E402


def main(paths):
    targets = {Path(p).resolve() for p in paths}
    known_terms = defaultdict(list)   # term.lower() -> [(файл, подколода)]
    known_decks = set()
    for path in sorted(b.DATA.glob("*.txt")):
        if path.resolve() in targets:
            continue
        for deck, term, *_ in b.parse(path):
            known_terms[term.lower()].append((path.name, deck))
            known_decks.add(deck)

    total = warned = 0
    seen_here = {}
    for p in paths:
        path = Path(p)
        print(f"=== {path.name}")
        for deck, term, ru, definition, example, flag in b.parse(path):
            total += 1
            warn = []
            if deck not in known_decks:
                top = deck.split("::")[0]
                extra = ("" if any(d.split("::")[0] == top for d in known_decks) else
                         "; новая подколода верхнего уровня — добавить её в STREAMS в build_deck.py")
                warn.append(f"новая подколода «{deck}» — нужно согласие пользователя{extra}")
            for f, d in known_terms.get(term.lower(), []):
                # одно слово — одна карточка, даже если оно есть в обоих предметах
                warn.append(f"термин уже есть: {f} / {d} — не добавлять; если значение другое, "
                            f"дописать его в существующую строку («…; in physics — …»)")
            if term.lower() in seen_here:
                warn.append(f"повтор в этих файлах: {seen_here[term.lower()]}")
            seen_here[term.lower()] = deck

            ru_vars = b.ru_accept(ru)
            if len(ru_vars[0].split()) > 4:
                warn.append(f"основной RU-вариант длинный ({len(ru_vars[0].split())} слов) — "
                            f"пояснение убрать в скобки или после точки")
            inside = " ".join(b.PAREN.findall(ru)).lower()
            for v in ru_vars[1:]:
                if len(v.split()) == 1 and v.lower() in inside.split() and not b.is_abbrev(v):
                    warn.append(f"слово из скобок «{v}» засчитается как ответ — точно верно?")

            spell = b.spelling(term)
            two_way = not (flag == "-" or "…" in spell or len(spell.split()) > b.MAX_EN_WORDS)
            hint = b.mask(definition, term) if two_way else ""
            if two_way:
                for w in re.findall(r"[A-Za-z]{4,}", spell):
                    if w.lower() not in b.STOP and re.search(rf"\b{w}", hint, re.I):
                        warn.append(f"подсказка RU→EN выдаёт ответ: «{w}» не скрыто")
            if not definition:
                warn.append("нет определения — у карточки RU→EN не будет подсказки")

            print(f"- {term}  [{deck}]")
            print(f"    RU ответы: {' | '.join(ru_vars)}")
            print(f"    EN ответы: {' | '.join(b.en_accept(term)) if two_way else '(нет карточки RU→EN)'}")
            if two_way:
                print(f"    подсказка: {hint}")
            for w in warn:
                print(f"    ! {w}")
            warned += bool(warn)
    print(f"\nСтрок: {total}, с предупреждениями: {warned}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1:])
