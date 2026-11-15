// Проверка напечатанного ответа на обороте карточки Anki.
// Встраивается в шаблон скриптом build_deck.py. Работает в Anki и AnkiDroid.
// Ответ засчитывается, только если он совпадает с одним из вариантов в колоде.
// Не важны только регистр, ё/е, знаки препинания и лишние пробелы.

function igNorm(s) {
  return (s || "").toLowerCase()
    .replace(/ё/g, "е")
    .replace(/[\-‐‑–—\/]/g, " ")
    .replace(/[^0-9a-zа-я°²³π√ ]/g, " ")
    .replace(/\s+/g, " ").trim();
}

function igLev(a, b) {
  var m = a.length, n = b.length, d = [], i, j;
  for (i = 0; i <= m; i++) { d[i] = [i]; }
  for (j = 1; j <= n; j++) { d[0][j] = j; }
  for (i = 1; i <= m; i++) {
    for (j = 1; j <= n; j++) {
      d[i][j] = Math.min(d[i - 1][j] + 1, d[i][j - 1] + 1,
        d[i - 1][j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
    }
  }
  return d[m][n];
}

// Возвращает "ok", "typo" (одна буква не та — всё равно ошибка) или "wrong".
function igVerdict(mode, typed, variants) {
  var t = igNorm(typed);
  if (!t) return "wrong";
  var typo = false;
  for (var i = 0; i < variants.length; i++) {
    var v = igNorm(variants[i]);
    if (!v) continue;
    if (t === v) return "ok";
    if (v.length >= 5 && igLev(t, v) <= 1) typo = true;
  }
  return typo ? "typo" : "wrong";
}

// Достать напечатанный текст из сравнения, которое Anki рисует на обороте.
function igTyped(box) {
  var arrow = box.querySelector("#typearrow");
  if (arrow) {
    var t = "";
    for (var n = box.firstChild; n; n = n.nextSibling) {
      if (n.nodeName === "BR" || n === arrow) break;
      // typeMissed в строке ответа — это «-» на месте недостающих букв, их не печатали.
      if (n.className === "typeMissed") continue;
      t += n.textContent;
    }
    return t;
  }
  if (!box.querySelector("span")) return "";
  return box.textContent;  // совпало полностью (или незнакомая разметка)
}

// Ответить на карточку из скрипта: 1 = Снова, 2 = Трудно, 3 = Хорошо.
// Компьютер: pycmd("easeN"). AnkiDroid: JavaScript API (buttonAnswerEaseN).
var IG_DEV = "43490155+ekolvah@users.noreply.github.com";  // контакт автора колоды — его требует AnkiDroid JS API
function igAnswer(ease) {
  try {
    if (typeof pycmd === "function") { pycmd("ease" + ease); return true; }
  } catch (e) {}
  try {
    if (typeof AnkiDroidJS !== "undefined" && !window.igApi) {
      window.igApi = new AnkiDroidJS({ version: "0.0.3", developer: IG_DEV });
    }
  } catch (e) {}
  try {
    var f = window["buttonAnswerEase" + ease];
    if (typeof f === "function") { f(); return true; }
    var api = window.igApi;
    if (api && typeof api["ankiAnswerEase" + ease] === "function") { api["ankiAnswerEase" + ease](); return true; }
  } catch (e) {}
  return false;
}

var IG_BTN_NAME = { 1: "Снова", 3: "Хорошо" };

function igButtons(out, buttons) {
  var wrap = document.createElement("div");
  wrap.className = "igb";
  buttons.forEach(function (b) {
    var el = document.createElement("button");
    el.className = "igbtn " + b.cls;
    el.textContent = b.text;
    el.onclick = function () {
      if (!igAnswer(b.ease)) {
        wrap.innerHTML = '<div class="vh">Кнопка не сработала. Нажми внизу «' + IG_BTN_NAME[b.ease] +
          '» (если кнопок Anki нет — верни их в настройках AnkiDroid)</div>';
      }
    };
    wrap.appendChild(el);
  });
  out.appendChild(wrap);
}

// Лицевая сторона: кнопка «Проверить» — только на телефоне, где кнопки Anki скрыты.
// На компьютере (есть pycmd) ответ открывается клавишей Enter.
function igShowAnswer() {
  try {
    if (typeof AnkiDroidJS !== "undefined" && !window.igApi) {
      window.igApi = new AnkiDroidJS({ version: "0.0.3", developer: IG_DEV });
    }
  } catch (e) {}
  try {
    if (typeof showAnswer === "function") { showAnswer(); return true; }
    if (window.igApi && typeof window.igApi.ankiShowAnswer === "function") { window.igApi.ankiShowAnswer(); return true; }
  } catch (e) {}
  return false;
}

function igFront() {
  if (typeof pycmd === "function") return;
  var place = document.getElementById("igfront");
  if (!place) return;
  var b = document.createElement("button");
  b.className = "igbtn ok";
  b.textContent = "Проверить";
  b.onclick = function () {
    if (!igShowAnswer()) place.innerHTML = '<div class="vh">Нажми «Показать ответ»</div>';
  };
  var wrap = document.createElement("div");
  wrap.className = "igb";
  wrap.appendChild(b);
  place.appendChild(wrap);
}

function igCheck(mode) {
  var box = document.getElementById("typeans");
  var out = document.getElementById("verdict");
  var acc = document.getElementById("accept");
  if (!box || !out || !acc) return;
  var typed = igTyped(box);
  if (typed === null) return;
  var variants = acc.textContent.split("|");
  var v = igVerdict(mode, typed, variants);
  var html, buttons;
  if (v === "ok") {
    // Сравнение Anki красит лишний пробел, другой регистр или знак красным и рисует стрелку —
    // выглядит как ошибка, хотя ответ верный. Показываем просто ответ зелёным.
    var clean = document.createElement("span");
    clean.className = "typeGood";
    clean.textContent = typed.replace(/\s+/g, " ").trim();
    box.innerHTML = "";
    box.appendChild(clean);
    html = '<div class="v ok">✅ Верно</div>';
    buttons = [{ text: "Дальше →", ease: 3, cls: "ok" }];
  } else if (v === "typo") {
    html = '<div class="v wrong">❌ Ошибка в одной букве</div><div class="vh">посмотри, где ошибка</div>';
    buttons = [{ text: "Дальше → (повторю)", ease: 1, cls: "wrong" }];
  } else if (!igNorm(typed)) {
    html = '<div class="v wrong">❌ Ответ не написан</div>';
    buttons = [{ text: "Дальше → (повторю)", ease: 1, cls: "wrong" }];
  } else {
    html = '<div class="v wrong">❌ Неверно</div><div class="vh">запомни, как в колоде</div>';
    buttons = [{ text: "Дальше → (повторю)", ease: 1, cls: "wrong" }];
  }
  out.innerHTML = html;
  // Кнопки — в самом низу карточки, чтобы сначала прочитать перевод и пример.
  var place = document.getElementById("igbuttons") || out;
  igButtons(place, buttons);
}

if (typeof module !== "undefined") {
  module.exports = { igNorm: igNorm, igVerdict: igVerdict };
}
