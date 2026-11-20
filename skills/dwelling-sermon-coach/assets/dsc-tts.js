/* dsc-tts.js v1.0.0 — 머무르는 설교 코치 공통 낭독
 * 울림 방지 4규칙: ① voice와 lang을 함께 지정하지 않음 ② 단위별 onend 순차 발화
 * ③ 로컬 음성 우선 ④ 성우 선택 상자 · 성우/속도 변경 시 즉시 멈춤. pitch는 1.0 고정.
 *
 * 마크업
 *  <div class="dsc-tts" data-tts-lang="ko-KR">            조절 막대 (페이지에 하나)
 *    <select class="dsc-voice"></select> <select class="dsc-rate">…</select>
 *    <button class="dsc-stop" type="button">■ 멈춤</button> <span class="dsc-tts-msg"></span></div>
 *  <button class="dsc-play" data-target="선택자">▶ 듣기</button>  선택자에 맞는 요소들(또는 그 안의 [data-tts-unit])을 차례로 읽음
 *  속성(단위 또는 그 조상에): data-voice="minsu|jian|yuna"  data-rate="0.85"(사용자 속도에 곱함)
 *  단위에: data-pause="5000"(다음 단위 전 쉼, ms)   읽지 않음: .ai-badge .tr [data-tts-skip]
 */
(function (w, d) {
  "use strict";
  var S = w.speechSynthesis;
  var HINTS = {
    jian: ["jian", "지안", "yuna", "유나"],
    yuna: ["yuna", "유나"],
    minsu: ["minsu", "민수"],
    samantha: ["samantha"]
  };
  var DEFAULT_HINT = { ko: "jian", en: "samantha" };
  var PREMIUM = /premium|enhanced|프리미엄|고품질/i;
  var st = { voices: [], run: 0, rate: 1.0, lang: "ko-KR", panel: null, current: null, btn: null, utter: null, dog: 0 };

  function loadVoices() {
    return new Promise(function (resolve) {
      var v = S.getVoices();
      if (v.length) { resolve(v); return; }
      var done = false;
      function fin() { if (!done) { done = true; resolve(S.getVoices()); } }
      S.addEventListener("voiceschanged", fin, { once: true });
      setTimeout(fin, 1500);
    });
  }

  function base(lang) { return String(lang || "").toLowerCase().split(/[-_]/)[0]; }

  // 규칙 3: 로컬 음성 우선, 같은 조건이면 프리미엄 우선
  function sortVoices(list) {
    return list.slice().sort(function (a, b) {
      if (a.localService !== b.localService) return a.localService ? -1 : 1;
      var pa = PREMIUM.test(a.name), pb = PREMIUM.test(b.name);
      return pa === pb ? 0 : (pa ? -1 : 1);
    });
  }

  function voicesFor(lang) {
    var b = base(lang);
    return sortVoices(st.voices.filter(function (v) { return base(v.lang) === b; }));
  }

  function byHint(lang, hint) {
    var keys = HINTS[hint] || [];
    var list = voicesFor(lang);
    for (var k = 0; k < keys.length; k++) {
      for (var i = 0; i < list.length; i++) {
        if (list[i].name.toLowerCase().indexOf(keys[k]) !== -1) return list[i];
      }
    }
    return null;
  }

  function label(v) { return v.name + " (" + v.lang + ")" + (v.localService === false ? " (네트워크)" : ""); }

  function selectedVoice() {
    var sel = st.panel && st.panel.querySelector(".dsc-voice");
    if (!sel || !sel.value) return null;
    for (var i = 0; i < st.voices.length; i++) if (st.voices[i].voiceURI === sel.value) return st.voices[i];
    return null;
  }

  function msg(t) { var m = st.panel && st.panel.querySelector(".dsc-tts-msg"); if (m) m.textContent = t || ""; }

  function clearMark() {
    var on = d.querySelectorAll(".dsc-speaking");
    for (var i = 0; i < on.length; i++) on[i].classList.remove("dsc-speaking");
  }

  function markButton(btn) {
    if (st.btn) {
      st.btn.setAttribute("aria-pressed", "false");
      if (st.btn.getAttribute("data-label")) st.btn.textContent = st.btn.getAttribute("data-label");
    }
    st.btn = btn || null;
    if (btn) {
      if (!btn.getAttribute("data-label")) btn.setAttribute("data-label", btn.textContent);
      btn.setAttribute("aria-pressed", "true");
      btn.textContent = "■ " + btn.getAttribute("data-label").replace(/^▶\s*/, "");
    }
  }

  function stop() {
    st.run++;
    clearTimeout(st.dog);
    if (S) S.cancel();
    st.utter = null;
    clearMark();
    markButton(null);
    st.current = null;
    msg("");
  }

  function unitsOf(sel) {
    var out = [], t = d.querySelectorAll(sel);
    for (var i = 0; i < t.length; i++) {
      var u = t[i].querySelectorAll("[data-tts-unit]");
      if (u.length) out = out.concat(Array.prototype.slice.call(u)); else out.push(t[i]);
    }
    return out;
  }

  function textOf(el) {
    var c = el.cloneNode(true);
    var skip = c.querySelectorAll(".ai-badge,.tr,[data-tts-skip]");
    for (var i = 0; i < skip.length; i++) skip[i].parentNode.removeChild(skip[i]);
    return c.textContent.replace(/[「」『』]/g, " ").replace(/\s+/g, " ").trim();
  }

  function attr(el, name) {
    var h = el.closest ? el.closest("[" + name + "]") : (el.hasAttribute(name) ? el : null);
    return h ? h.getAttribute(name) : null;
  }

  function play(sel, lang, btn) {
    stop();
    var token = st.run, units = unitsOf(sel), i = 0;
    if (!units.length) return;
    st.current = sel;
    markButton(btn);
    function next(ms) { if (token === st.run) { clearTimeout(st.dog); setTimeout(step, ms); } }
    function step() {
      if (token !== st.run) return;
      clearMark();
      if (i >= units.length) { st.utter = null; markButton(null); st.current = null; msg(""); return; }
      var el = units[i++], text = textOf(el);
      if (!text) { step(); return; }
      var sv = selectedVoice();
      if (sv && base(sv.lang) !== base(lang)) sv = byHint(lang, DEFAULT_HINT[base(lang)]) || voicesFor(lang)[0] || null;
      var hint = attr(el, "data-voice");
      var vo = (hint && byHint(lang, hint)) || sv;
      var utter = new SpeechSynthesisUtterance(text);
      if (vo) utter.voice = vo;        // 규칙 1: 음성을 지정하면 lang 생략
      else utter.lang = lang;          // 폴백일 때만 lang
      var unitRate = parseFloat(attr(el, "data-rate"));
      utter.rate = Math.min(2, Math.max(0.5, (unitRate > 0 ? unitRate : 1) * st.rate));
      utter.pitch = 1.0;               // 고정
      var p = parseInt(el.getAttribute("data-pause"), 10);
      var pause = isNaN(p) ? 120 : p;
      utter.onend = function () { clearTimeout(st.dog); setTimeout(step, pause); };   // 규칙 2: 다음 단위
      utter.onerror = function () { next(120); };
      st.utter = utter;                // 참조를 잡아 두어야 onend가 사라지지 않음
      el.classList.add("dsc-speaking");
      msg("읽는 중 " + i + "/" + units.length);
      clearTimeout(st.dog);            // onend가 끝내 오지 않을 때를 대비한 감시
      st.dog = setTimeout(function () { if (token === st.run) { S.cancel(); next(120); } },
        8000 + text.length * 400 / utter.rate);
      if (S.paused) S.resume();
      S.speak(utter);
    }
    setTimeout(step, 60);              // cancel 직후 바로 speak하면 Safari가 삼킴
  }

  function fillVoices() {
    var sel = st.panel.querySelector(".dsc-voice");
    if (!sel) return;
    var keep = sel.value, list = voicesFor(st.lang);
    sel.innerHTML = "";
    list.forEach(function (v) {
      var o = d.createElement("option");
      o.value = v.voiceURI; o.textContent = label(v);
      sel.appendChild(o);
    });
    var def = byHint(st.lang, DEFAULT_HINT[base(st.lang)]) || list[0];
    if (keep && list.some(function (v) { return v.voiceURI === keep; })) sel.value = keep;
    else if (def) sel.value = def.voiceURI;
    if (!list.length) {
      var o = d.createElement("option");
      o.value = ""; o.textContent = "기본 음성 (" + st.lang + ")";
      sel.appendChild(o);
      msg("이 기기에서 " + st.lang + " 음성 목록을 아직 받지 못했습니다. 기본 음성으로 읽습니다.");
    } else msg("");
  }

  function disable(text) {
    var b = d.querySelectorAll(".dsc-play,.dsc-tts button,.dsc-tts select");
    for (var i = 0; i < b.length; i++) b[i].disabled = true;
    msg(text);
  }

  function init() {
    st.panel = d.querySelector(".dsc-tts");
    if (!st.panel) return;
    st.lang = st.panel.getAttribute("data-tts-lang") || "ko-KR";
    if (!S || !w.SpeechSynthesisUtterance) { disable("이 브라우저는 낭독을 지원하지 않습니다."); return; }
    var rate = st.panel.querySelector(".dsc-rate");
    if (rate) { st.rate = parseFloat(rate.value) || 1.0;
      rate.addEventListener("change", function () { st.rate = parseFloat(rate.value) || 1.0; stop(); }); }
    var sel = st.panel.querySelector(".dsc-voice");
    if (sel) sel.addEventListener("change", stop);       // 규칙 4: 바꾸면 즉시 멈춤
    var sb = st.panel.querySelector(".dsc-stop");
    if (sb) sb.addEventListener("click", stop);
    d.addEventListener("click", function (e) {
      var btn = e.target.closest && e.target.closest(".dsc-play");
      if (!btn || btn.disabled) return;
      var target = btn.getAttribute("data-target");
      if (!target) return;
      if (st.current === target) { stop(); return; }
      play(target, btn.getAttribute("data-lang") || st.lang, btn);
    });
    loadVoices().then(function (v) { st.voices = v || []; fillVoices(); });
    // iOS는 음성 목록을 늦게 채우기도 합니다. 올 때마다 다시 채웁니다.
    S.addEventListener("voiceschanged", function () { st.voices = S.getVoices(); fillVoices(); });
    w.addEventListener("pagehide", stop);   // stop() 안에서 speechSynthesis.cancel()
  }

  w.DSC = w.DSC || {};
  w.DSC.tts = { stop: stop, play: play, version: "1.0.0" };
  if (d.readyState === "loading") d.addEventListener("DOMContentLoaded", init); else init();
})(window, document);
