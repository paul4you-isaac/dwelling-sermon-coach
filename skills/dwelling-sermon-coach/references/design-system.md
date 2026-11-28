# 디자인 시스템 · HTML · TTS 표준 (v1.0.0 확정)

모든 단계 HTML, 관찰 작업창, 사용자 매뉴얼은 **하나의 디자인 시스템**을 씁니다.
설교자가 M2에서 **시안 B 「작업대」**를 골랐습니다(2026-11-20). 고딕 글꼴, 밝은 회색 바탕, 파란 강조, 둥근 카드입니다.

| 파일 | 역할 |
|---|---|
| `assets/dsc.css` | 색·글꼴·간격 토큰, 라이트/다크, 공통 클래스 |
| `assets/dsc-tts.js` | 공통 낭독. 울림 방지 4규칙과 pitch 1.0을 코드로 지킴 |
| `assets/templates/*.html` | 템플릿 5종 (본문만남·1차청중·페리코프·설교개요 + `base.html`). CSS·JS가 이미 인라인됨 |
| `references/template_stage3_원어관찰.html` | Stage 3 원어관찰 관찰 작업창의 화면 기준 파일(정적 사본). 절마다 5중 인터리니어 · 주동사 해설 · 「나의 번역」 · 「감독에게 번역 묻기」 · 「묵상 노트」, 아래 막대(노트 저장 · 감독에게 묻기 · 감독과 마무리). 작업창(`app/static`)을 고칠 때 기준으로 삼음 |
| `references/template_stage5_맥락관찰.html` | Stage 5 맥락관찰 기준 파일. 번역 탭 · 세 단(늘 펼침) · 본문 장면 소제목 · 단별 보조 TTS 막대 · 연속 재생. Stage 5 맥락관찰은 이 파일을 복사해 씀 |
| `references/template_stage4_1차청중.html` | Stage 4 1차청중 기준 파일. 페르소나 카드마다 보조 TTS 막대(`data-mirror`), 맨 위 산책 모드. Stage 4 1차청중은 이 파일을 복사해 씀 |
| `references/template_stage1_본문만남.html` | Stage 1 본문만남 기준 파일. 공통 CSS·TTS 블록에 Stage 1 본문만남 전용 `<style data-dsc="stage1">`·`<script data-dsc="stage1">`(번역 탭·페리코페 접기·단락별 TTS 막대)을 더함. Stage 1 본문만남은 이 파일을 복사해 씀 |
| `tools/build_html.py` | CSS·JS를 고친 뒤 템플릿에 다시 인라인 |
| `tools/check_html.py` | 생성 HTML 자동 점검 (§5) |

---

## 1. 공통 규칙

- HTML은 **템플릿을 복사해** 만듭니다. `{{…}}` 자리만 채우고, 인라인된 `<style data-dsc="css">`·`<script data-dsc="tts">` 블록은 고치지 않습니다.
- HTML은 **한 파일로 자급**합니다. `<!doctype html>` 바로 다음 줄의 주석 `<!-- dsc.css v1.0.0 -->`을 지우지 않습니다. doctype보다 앞에 두면 브라우저가 호환 모드로 그립니다.
- 외부 글꼴·스크립트를 불러오지 않습니다. 오프라인·iCloud·휴대폰에서도 열려야 합니다.
- 라이트/다크는 기기 설정을 따릅니다. `<html data-theme="light|dark">`로 고정할 수도 있습니다.
- 설교자 원문과 AI 문장을 시각적으로 구분합니다. AI 문장은 보라색 글자와 【AI】 배지입니다.

| 클래스 | 용도 |
|---|---|
| `.preacher-text` | 설교자 원문·성경 본문 |
| `.claude-text` | AI가 쓴 보조 문장. **안에 반드시** `.ai-badge` |
| `.ai-badge` | AI 문장 앞 배지. 글자는 【AI】 |
| `.persona-block` | 설교자가 쓴 페르소나 원문 |
| `.legend-bar` | 상단 범례 (설교자 원문 / 【AI】 / 구문 색) |
| `.c-s` `.c-v` `.c-g` | 주어 · 주동사 · 종속절·인용·분사 |
| `.ln` `.i1`~`.i3` | 배열 한 줄과 들여쓰기 단계 |
| `.greek` `.hebrew` | 원어 글꼴 (히브리어는 오른쪽→왼쪽) |
| `.card` `.vrow` `.tr` `.vn` | 카드·번역 한 줄·번역 이름·절 번호 |
| `.peri` `.peri.main` | Stage 5 페리코프 3단 (그늘 / 머무르는 자리 / 빛) |
| `.move` + `.n-intro`~`.n-end` | Stage 9 개요 6단계 서사 |
| `.missing` | `[미제공]` 표시 |

### 비공개 표시 (HTML)
- 7A 자기적용 문장이 들어간 HTML은 `<head>`에 `<meta name="dsc-private" content="true">`를 넣습니다.
- 설교자가 그 문장을 공개하기로 확인했으면 대신 `<meta name="dsc-shared-by-preacher" content="true">`를 넣습니다.
- `scripts/check_privacy.py`가 이 표시를 읽습니다(`agents-protocol.md` §5).

### 낭독 마크업
- 조절 막대 `.dsc-tts`(페이지에 하나, `data-tts-lang`)에 `.dsc-voice`·`.dsc-rate`·`.dsc-stop`을 둡니다.
  - 예외: Stage 1 본문만남·Stage 5 맥락관찰은 단락마다, Stage 4 1차청중은 페르소나 카드마다 보조 막대 `.dsc-tts.sec-tts[data-mirror]`를 더 둡니다. 낭독은 맨 위 막대 하나가 맡고, 보조 막대는 성우·속도를 맨 위 막대와 함께 움직입니다(`references/template_stage1_본문만남.html`, `references/template_stage4_1차청중.html`).
- 듣기 버튼 `.dsc-play`의 `data-target`은 CSS 선택자입니다. 맞는 요소들 안의 `[data-tts-unit]`을 차례로 읽습니다.
- `data-voice`(minsu·jian·yuna)·`data-rate`(선택한 속도에 곱함)는 단위나 그 조상 요소에 둡니다. `data-pause`(다음 단위 전 쉼, ms)는 단위에 둡니다.
- 한 단위는 **한 문장 또는 한 절**입니다. 긴 글을 한 단위로 두면 Chrome이 15초쯤에서 끊습니다.
- `.ai-badge`·`.tr`·`[data-tts-skip]`은 읽지 않습니다.

## 2. 본문 시각화 색 (토큰으로 유지)

| 토큰 | 값 | 뜻 |
|---|---|---|
| `--syn-subject` | `#1e6091` | 주절 주어 |
| `--syn-verb` | `#a83232` | 주동사 |
| `--syn-sub` | `#2d6a4f` | 종속절·인용문·분사 |

## 3. 6단계 서사 색 (설교개요)

도입 `#1565c0` · 발단 `#e65100` · 전개 `#2e7d32` · 위기 `#c62828` · 절정 `#f57f17` · 결말 `#4527a0`

---

## 4. 음성·TTS

### 음성 기본값

| 탭 | 음성 | 비고 |
|---|---|---|
| 한국어 4개 | 지안 Jian (ko-KR) | 프리미엄 우선 · 폴백 유나 Yuna → ko-KR 기본 |
| ESV | Samantha (en-US) | 영문 차분한 낭독 |
| BHS / NA28 | 비활성화 | 원어 음성 안정성 부족 |

음성은 고정하지 않습니다. 위 순서로 **기본 선택만** 하고, 설교자가 성우 선택 상자에서 바꿀 수 있게 합니다.

### 울림(에코) 방지 4규칙 (절대 준수)

실전 운영(시편 100:1-5, 2026-11-02)에서 한국어 프리미엄 음성에 울림이 생겼습니다.
원인은 네 가지입니다. 모든 HTML은 네 규칙을 **함께** 적용합니다.

**규칙 1 — `voice`와 `lang`을 함께 지정하지 않습니다.**
둘을 함께 지정하면 일부 브라우저가 같은 문장을 두 번 발화합니다.

```javascript
if (vo) utter.voice = vo;        // 음성 지정 시 lang 생략
else    utter.lang  = 'ko-KR';   // 폴백일 때만 lang
```

**규칙 2 — 절 단위로 나누어 순차 발화합니다.**
`onend`에서 다음 절을 이어 발화합니다. `speak()`를 한꺼번에 쌓지 않습니다.

```javascript
u.onend = function(){ setTimeout(step, 120) };   // 다음 절
```

**규칙 3 — 로컬 음성을 네트워크 음성보다 우선합니다.**
`voice.localService === false`인 음성은 뒤로 내리고 이름 뒤에 「(네트워크)」를 붙입니다.

```javascript
list.sort(function(a,b){ return (a.localService===b.localService)?0:(a.localService?-1:1) });
```

**규칙 4 — 성우 선택 상자를 반드시 제공합니다.**
현재 탭 언어에 맞는 음성만 올립니다. **성우·속도를 바꾸면 낭독을 즉시 멈춥니다.**

### 속도·음높이

| 항목 | 값 | 비고 |
|---|---|---|
| rate | `1.0` | 기본값 |
| pitch | `1.0` | **고정**. 바꾸면 울림이 생깁니다 |

### 페르소나별 음성 (Stage 4 1차청중 스토리 TTS)

| 페르소나 결 | 속도 | 음높이 | 음성 |
|---|---|---|---|
| 노년 남성 | 0.85 | 1.0 | 민수 (Minsu) |
| 중년 남성 | 0.95 | 1.0 | 민수 (Minsu) |
| 청년 남성 | 1.00 | 1.0 | 민수 (Minsu) |
| 청년 여성 | 1.00 | 1.0 | 지안 (Jian) → 유나 (Yuna) |
| 노년 여성 | 0.85 | 1.0 | 지안 (Jian) → 유나 (Yuna) |

페르소나 TTS에도 울림 방지 4규칙을 그대로 적용합니다.

- 정확한 성우 지정: 단위나 그 조상에 `data-voice-uri="<voiceURI>"`를 두면 `data-voice`(힌트)보다 앞서 그 성우로 읽습니다(v1.0.2). Stage 4 1차청중 카드별 성우 상자가 씁니다.
- `dsc-tts.js`는 음성 목록을 채운 뒤 문서에 `dsc-voices` 이벤트를 보내고, `DSC.tts.voices(lang)` · `DSC.tts.voiceFor(lang, hint)` · `DSC.tts.label(voice)`를 내놓습니다.

### 음성 로딩 (필수)

`getVoices()`는 처음에 빈 배열을 줄 수 있습니다. `voiceschanged`가 끝내 오지 않는 기기도 있어 타임아웃을 둡니다.

```javascript
function loadVoices() {
  return new Promise(function(resolve){
    var v = speechSynthesis.getVoices();
    if (v.length) { resolve(v); return; }
    var done = false;
    function fin(){ if(!done){ done = true; resolve(speechSynthesis.getVoices()) } }
    speechSynthesis.addEventListener('voiceschanged', fin, { once: true });
    setTimeout(fin, 1500);
  });
}
```

- 페이지 로드 때 한 번 불러 성우 선택 상자를 채웁니다.
- 음성이 끝내 없으면 안내를 띄우고 재생 버튼을 끕니다.
- `pagehide`에서 `speechSynthesis.cancel()`을 불러 남은 발화를 끊습니다.

---

## 5. 점검

`tools/check_html.py [파일·폴더] [--mobile]`

| 항목 | 내용 |
|---|---|
| marker · viewport · offline | 버전 표지, 모바일 viewport, 외부 자원 없음 |
| classes · legend | `.claude-text`마다 【AI】 배지, AI 문장이 있으면 범례 |
| inline | 인라인 CSS·TTS가 `assets/` 파일과 똑같음, 다른 낭독 스크립트 없음 |
| fill | `{{…}}` 자리 남김 없음 (템플릿 밖 파일) |
| tts-r1 ~ r4 | 울림 방지 4규칙 (성우·속도 변경 시 멈춤 포함) |
| tts-pitch · tts-load · tts-hide | pitch 1.0, voiceschanged 시간 제한, pagehide 취소 |
| mobile | 375px 폭에서 가로 넘침 없음 (Chrome 필요) |

인자가 없으면 템플릿 5종과 `docs/samples/`를 검사합니다. 오류가 있으면 종료 코드 1입니다.
