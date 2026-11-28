#!/usr/bin/env python3
"""공통 CSS·TTS를 HTML 안에 그대로 넣습니다 (인라인).

<style data-dsc="css"></style> 와 <script data-dsc="tts"></script> 의 내용을
assets/dsc.css · assets/dsc-tts.js 의 현재 내용으로 바꿉니다.

사용:
  python3 tools/build_html.py                 # 템플릿 5종 + Stage 1 기준 파일 갱신
  python3 tools/build_html.py 파일.html ...    # 지정한 파일 갱신
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "skills" / "dwelling-sermon-coach" / "assets"
CSS_RE = re.compile(r'(<style data-dsc="css">)(.*?)(</style>)', re.S)
JS_RE = re.compile(r'(<script data-dsc="tts">)(.*?)(</script>)', re.S)


def build(path: Path, css: str, js: str) -> bool:
    src = path.read_text(encoding="utf-8")
    out = CSS_RE.sub(lambda m: m.group(1) + "\n" + css.strip() + "\n" + m.group(3), src)
    out = JS_RE.sub(lambda m: m.group(1) + "\n" + js.strip() + "\n" + m.group(3), out)
    if out != src:
        path.write_text(out, encoding="utf-8")
        return True
    return False


def main(argv):
    css = (ASSETS / "dsc.css").read_text(encoding="utf-8")
    js = (ASSETS / "dsc-tts.js").read_text(encoding="utf-8")
    if "</script" in js.lower() or "</style" in css.lower():
        sys.exit("자산 안에 닫는 태그가 있어 인라인할 수 없습니다.")
    files = [Path(a) for a in argv] or (sorted((ASSETS / "templates").glob("*.html"))
                                        + sorted((ASSETS.parent / "references").glob("template_*.html")))
    for f in files:
        print(("갱신 " if build(f, css, js) else "같음 ") + str(f))


if __name__ == "__main__":
    main(sys.argv[1:])
