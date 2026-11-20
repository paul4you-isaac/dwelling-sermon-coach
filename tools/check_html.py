#!/usr/bin/env python3
"""DSC 생성 HTML 점검기 (design-system.md 규칙).

검사
  marker    <!-- dsc.css v1.0.0 --> 표지
  viewport  모바일 viewport 메타
  offline   외부 자원·별도 파일 불러오기 없음 (한 파일 자급)
  inline    인라인 CSS·TTS 블록이 assets/dsc.css·dsc-tts.js와 똑같음, 다른 낭독 스크립트 없음
  classes   .claude-text 요소마다 【AI】 배지
  legend    AI 문장이 있으면 .legend-bar 범례
  fill      {{…}} 자리 남김 없음 (templates/ 밖 파일만)
  낭독이 있는 페이지(speechSynthesis 사용)만:
  tts-r1    utter.lang 지정은 else 분기에서만 (voice와 함께 지정 금지)
  tts-pitch pitch = 1.0 고정
  tts-r2    onend에서 setTimeout으로 다음 단위 순차 발화
  tts-r3    localService로 로컬 음성 우선 정렬
  tts-r4    성우 선택 상자(.dsc-voice) + 성우·속도를 바꾸면 멈춤
  tts-load  voiceschanged 대기에 시간 제한
  tts-hide  pagehide에서 speechSynthesis.cancel()
  mobile    375px 폭에서 가로 넘침 없음 (--mobile, Chrome 필요)

사용
  python3 tools/check_html.py [파일·폴더 ...] [--mobile]
  인자가 없으면 템플릿 5종과 docs/samples/를 검사합니다.
  종료 코드: 오류가 있으면 1.
"""
import os
import re
import subprocess
import sys
import tempfile
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT = [ROOT / "skills/dwelling-sermon-coach/assets/templates", ROOT / "docs/samples"]
ASSETS = ROOT / "skills/dwelling-sermon-coach/assets"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

MARKER = re.compile(r"<!--\s*dsc\.css v1\.0\.0\s*-->")
VIEWPORT = re.compile(r'<meta[^>]+name="viewport"[^>]+width=device-width', re.I)
RES_ATTR = re.compile(r'\s(?:src|srcset|poster|data)\s*=\s*["\']?([^"\'\s>]+)', re.I)
LINK_HREF = re.compile(r'<link\b[^>]*\shref\s*=\s*["\']?([^"\'\s>]+)', re.I)
CSS_URL = re.compile(r"@import|url\(\s*['\"]?(?!data:|#)[^)'\"\s]", re.I)
LANG_SET = re.compile(r"([\w.]+)\.lang\s*=(?!=)")
PITCH = re.compile(r"\.pitch\s*=\s*([^;\s]+)")


def scripts(html):
    return "\n".join(re.findall(r"<script\b[^>]*>(.*?)</script>", html, re.S | re.I))


def strip_comments_js(js):
    js = re.sub(r"/\*.*?\*/", "", js, flags=re.S)
    return re.sub(r"(?m)(^|[^:])//.*$", r"\1", js)


class _Scan(HTMLParser):
    """.claude-text 요소마다 안에 .ai-badge가 있는지, .legend-bar가 있는지 셉니다."""
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}

    def __init__(self):
        super().__init__()
        self.stack = []      # [태그, claude-text 여부, 배지 찾음]
        self.missing = 0
        self.claude = 0
        self.legend = False

    def handle_starttag(self, tag, attrs):
        cls = (dict(attrs).get("class") or "").split()
        if "ai-badge" in cls:
            for fr in self.stack:
                if fr[1]:
                    fr[2] = True
        if "legend-bar" in cls:
            self.legend = True
        if tag in self.VOID:
            return
        is_ct = "claude-text" in cls
        if is_ct:
            self.claude += 1
        self.stack.append([tag, is_ct, False])

    def handle_endtag(self, tag):
        for k in range(len(self.stack) - 1, -1, -1):
            if self.stack[k][0] == tag:
                for fr in self.stack[k:]:
                    if fr[1] and not fr[2]:
                        self.missing += 1
                del self.stack[k:]
                return


def body_only(html):
    return re.sub(r"<(style|script)\b[^>]*>.*?</\1>", "", html, flags=re.S | re.I)


def check_file(path: Path):
    html = path.read_text(encoding="utf-8")
    errs = []
    if not MARKER.search(html):
        errs.append("marker: <!-- dsc.css v1.0.0 --> 표지가 없습니다")
    if not VIEWPORT.search(html):
        errs.append("viewport: 모바일 viewport 메타가 없습니다")
    body = body_only(html)
    res = [u for u in RES_ATTR.findall(body) + LINK_HREF.findall(body) if not u.startswith(("data:", "#"))]
    if res:
        errs.append("offline: 다른 파일·외부 자원을 불러옵니다 (%s)" % ", ".join(res[:3]))
    styles = "\n".join(re.findall(r"<style\b[^>]*>(.*?)</style>", html, re.S | re.I))
    styles += "\n" + "\n".join(re.findall(r'\sstyle\s*=\s*"([^"]*)"', body, re.I))
    if CSS_URL.search(styles):
        errs.append("offline: CSS가 다른 파일·외부 자원을 불러옵니다")

    for kind, asset, rx in (("css", "dsc.css", r'<style data-dsc="css">(.*?)</style>'),
                            ("tts", "dsc-tts.js", r'<script data-dsc="tts">(.*?)</script>')):
        blocks = re.findall(rx, html, re.S)
        want = (ASSETS / asset).read_text(encoding="utf-8").strip()
        if kind == "css" and not blocks:
            errs.append("inline: 공통 CSS 블록(<style data-dsc=\"css\">)이 없습니다")
        for b in blocks:
            if b.strip() != want:
                errs.append("inline: %s 블록이 assets/%s와 다릅니다 (tools/build_html.py로 갱신)" % (kind, asset))
    for m in re.finditer(r"<script\b([^>]*)>(.*?)</script>", html, re.S | re.I):
        if 'data-dsc="tts"' not in m.group(1) and "speechSynthesis" in m.group(2):
            errs.append("inline: 공통 dsc-tts.js 밖에 낭독 스크립트가 있습니다")
            break

    sc = _Scan()
    sc.feed(body)
    sc.close()
    if sc.missing:
        errs.append("classes: 【AI】 배지 없는 .claude-text %d곳" % sc.missing)
    if sc.claude and not sc.legend:
        errs.append("legend: AI 문장이 있는데 .legend-bar 범례가 없습니다")
    if "templates" not in path.parts and re.search(r"\{\{[^}]*\}\}", body):
        errs.append("fill: 채우지 않은 {{…}} 자리가 남았습니다")

    js = strip_comments_js(scripts(html))
    if "speechSynthesis" in js:
        utt = set(re.findall(r"(\w+)\s*=\s*new\s+SpeechSynthesisUtterance", js))
        for m in LANG_SET.finditer(js):
            if m.group(1).split(".")[-1] not in utt:
                continue
            before = js[max(0, m.start() - 12): m.start()]
            if not re.search(r"else\s*$", before):
                errs.append("tts-r1: else 분기 밖에서 lang을 지정합니다 (voice와 함께 지정 위험)")
                break
        pitches = PITCH.findall(js)
        if not pitches:
            errs.append("tts-pitch: pitch를 1.0으로 지정하지 않았습니다")
        elif any(p not in ("1", "1.0") for p in pitches):
            errs.append("tts-pitch: pitch가 1.0이 아닙니다 (%s)" % ", ".join(pitches))
        if not re.search(r"onend\s*=\s*function[^{]*\{[^}]*setTimeout\(", js):
            errs.append("tts-r2: onend에서 다음 단위를 순차 발화하지 않습니다")
        if "localService" not in js:
            errs.append("tts-r3: 로컬 음성 우선 정렬(localService)이 없습니다")
        if not re.search(r'<select[^>]+class="[^"]*\bdsc-voice\b', html):
            errs.append("tts-r4: 성우 선택 상자(.dsc-voice)가 없습니다")
        if not re.search(r'dsc-voice"\)[\s\S]{0,200}?addEventListener\("change",\s*stop\)', js):
            errs.append("tts-r4: 성우를 바꿀 때 낭독을 멈추지 않습니다")
        if not re.search(r'dsc-rate"\)[\s\S]{0,300}?addEventListener\("change",\s*function[^}]*stop\(\)', js):
            errs.append("tts-r4: 속도를 바꿀 때 낭독을 멈추지 않습니다")
        if "voiceschanged" not in js or not re.search(r"setTimeout\(\s*fin\s*,\s*\d+", js):
            errs.append("tts-load: voiceschanged 대기에 시간 제한이 없습니다")
        stop_cancels = re.search(r"function stop\(\)\s*\{[^}]*\.cancel\(\)", js)
        if not (re.search(r'"pagehide"[\s\S]{0,80}?cancel\(\)', js)
                or (stop_cancels and re.search(r'"pagehide",\s*stop\b', js))):
            errs.append("tts-hide: pagehide에서 발화를 취소하지 않습니다")
    return errs


def mobile_overflow(path: Path):
    """Chrome headless 375px 폭에서 scrollWidth를 잽니다. 넘친 폭(px) 또는 None."""
    if not os.path.exists(CHROME):
        return None
    html = path.read_text(encoding="utf-8")
    probe = ('<script>addEventListener("load",function(){var w=document.documentElement.scrollWidth;'
             'document.body.setAttribute("data-probe",w+"/"+innerWidth)})</script></body>')
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td) / "probe.html"
        tmp.write_text(html.replace("</body>", probe, 1), encoding="utf-8")
        try:
            out = subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                                  "--window-size=375,812", "--virtual-time-budget=2000",
                                  "--user-data-dir=" + td + "/u", "--dump-dom", tmp.as_uri()],
                                 capture_output=True, text=True, timeout=60).stdout
        except Exception:
            return None
    m = re.search(r'data-probe="(\d+)/(\d+)"', out)
    if not m:
        return None
    return max(0, int(m.group(1)) - int(m.group(2)))


def collect(args):
    files = []
    for a in args or DEFAULT:
        p = Path(a)
        if p.is_dir():
            files += sorted(p.rglob("*.html"))
        elif p.exists():
            files.append(p)
    return files


def main(argv):
    mobile = "--mobile" in argv
    args = [a for a in argv if a != "--mobile"]
    files = collect(args)
    total = 0
    for f in files:
        errs = check_file(f)
        if mobile:
            over = mobile_overflow(f)
            if over is None:
                errs.append("mobile: 측정하지 못했습니다 (Chrome 없음 또는 실패)")
            elif over > 0:
                errs.append("mobile: 375px 폭에서 가로로 %dpx 넘칩니다" % over)
        rel = f.resolve().relative_to(ROOT) if f.resolve().is_relative_to(ROOT) else f
        print(("✗ " if errs else "✓ ") + str(rel))
        for e in errs:
            print("    " + e)
        total += len(errs)
    print("\n%d개 파일, 오류 %d건" % (len(files), total))
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
