# Источники слов

## Файлы data/*.txt
- `00_maths_workbook.txt` — по тетради учителя «Understanding maths questions» (Core mock 0580/11).
- `01_command_words.txt` — command words (официальные определения Cambridge) + Answer phrases (Physics).
- `02_maths_0580.txt` — 8 тем syllabus 0580.
- `03_physics_0625.txt` — practical skills + 6 тем 0625.
- `05_october_mock.txt` — формулировки из пробного экзамена Жени (октябрь 2026), которые вызвали трудности
  (подробно — `student.md`, только на компьютере).
- `06_hodder_textbook.txt` — недостающие термины из учебника Hodder Maths (Index + частые слова
  условий), разложены по существующим подколодам (новых подколод нет).
- `07_hodder_physics.txt` — то же по учебнику Hodder Physics 2014 (Index + частые слова текста),
  по существующим подколодам Physics. Темы, которых нет в syllabus 2026–2028 (logic gates,
  transistors, capacitors, CRO, cloud chamber…), сознательно пропущены.
- `08_computer_science_0478.txt` — новый предмет (2026-11-13): подколода «5 Computer Science 0478»
  (00 Question language + 10 тем syllabus). Отбор — по syllabus 0478 2026–2028 (v6) и
  формулировкам экзаменов 2024; учебник Hodder CS 2014 — для сверки (по старой программе).
  Пропущенное и слова, которым дописано значение из информатики, — в комментарии файла.
- `09_cs_chapter2_test.txt` — контрольная Жени по CS 0478, Chapter 2 (2026-11-14): слова формулировок
  заданий и mark scheme, которых не было в `08`, по существующим подколодам CS.

## Исходники от пользователя
- В папке «Загрузки» пользователя — сканы PDF без текстового слоя (имена файлов — в `student.md`),
  читать через Read с `pages` (≤ 20 страниц за раз).
- Учебники — в папке `books/` (не в корне проекта; новые учебники класть туда же). PDF с текстовым
  слоем, текст достаётся pypdf:
  - Hodder IGCSE Maths 2018 — Index на PDF-страницах 554–559;
  - Hodder IGCSE Physics 3rd ed. 2014 — Index на PDF-страницах 321–327;
  - Computer Science 0478 (с ebooks.papacambridge.com: поиск 0478 → e-books; файлы
    `https://ebooks.papacambridge.com/directories/CAIE/CAIE-ebooks/upload/<имя>.pdf`):
    `CS_0478_cambridge_igcse_computer_science.pdf` — Hodder (Watson, Williams) 2014, 192 стр.,
    Index на PDF-страницах ~185–191; `…_coursebook_public.pdf`, `…_revision_guide_public.pdf` —
    фрагменты Cambridge. Там же syllabus `CS_0478_syllabus_2026-2028.pdf` (+ `_update`) и
    экзамены `CS_0478_s24_qp_12/22`, `w24_qp_11/21` (с pastpapers.papacambridge.com).
    Не скачаны: «programming book for python» и «programming book_public» — если понадобятся
    слова из Python.
