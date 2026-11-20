#!/usr/bin/env python3
"""비공개 점검기 — 7A 자기적용 문장이 공개 파일로 새지 않았는지 봅니다.

  python3 check_privacy.py <주간 폴더 또는 볼트> [...] [--config C] [--json]

검사
  private-flag   07A 파일에 private: true와 tags의 private가 있다
  leak           07A 문장(15자 이상)이 다른 파일에 그대로 들어 있으면,
                 그 파일도 비공개 표시가 있어야 한다
                   md: frontmatter private: true / html: <meta name="dsc-private" content="true">
                 설교자가 공개 원고에 넣기로 확인했으면 오류 대신 안내로 냅니다
                   md: shared_by_preacher: true / html: <meta name="dsc-shared-by-preacher" content="true">
                 7A 이전 단계(01~06)·수집본에 이미 있던 문장은 7A 문장으로 보지 않습니다
                 (한계: 7A를 쓴 뒤 01~06 파일에 7A 문장을 옮겨 적으면 그 문장은 대조에서 빠집니다)
  log-leak       00_수집/ 안(작업 기록·수집본)에 7A 문장이 있다 → 경고
  stage3         설정 stage3_private(예전 이름 stage3_apply_private)가 true면 03_원어관찰 생성본에 private: true

지키는 것
- 7A 문장을 화면·파일·로그 어디에도 출력하지 않습니다. 파일 이름과 개수만 알립니다.
- 구판 주간(06A_자기적용)도 같은 방식으로 보되, 결과는 경고로만 냅니다(구판은 고치지 않음).
종료 코드: 오류가 있으면 1.
"""
import html
import json
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dsc_archive import frontmatter, load_config, stage3_private  # noqa: E402

SELF_RX = re.compile(r"^(07A|06A)_자기적용_.*\.md$")
PRIOR_RX = re.compile(r"^0[1-6]_.*\.(md|html)$|^Stage[1-5]_.*\.html$|^03_원어관찰\.json$")
MIN_LEN = 15
TEXT_SUFFIX = {".md", ".html", ".txt", ".json", ".jsonl"}


def nfc(s):
    return unicodedata.normalize("NFC", s)


def squash(s):
    return re.sub(r"\s+", "", nfc(s))


def body_of_md(text):
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end > 0:
            text = text[end + 4:]
    return text


def sentences(md_text):
    """7A 본문에서 문장을 뽑습니다. 제목·표·인용 기호는 지웁니다."""
    t = body_of_md(md_text)
    t = re.sub(r"(?m)^\s*(#+|>|[-*+]|\d+\.|\|)\s*", "", t)
    t = re.sub(r"[*_`「」『』“”\"'|]", "", t)
    parts = re.split(r"(?<=[.!?。])\s+|\n+", t)
    out = set()
    for p in parts:
        s = squash(p)
        if len(s) >= MIN_LEN:
            out.add(s)
    return out


def plain(path):
    raw = nfc(path.read_text(encoding="utf-8", errors="replace"))
    if path.suffix == ".html":
        raw = re.sub(r"<(script|style)\b.*?</\1>", " ", raw, flags=re.S | re.I)
        raw = html.unescape(re.sub(r"<[^>]+>", " ", raw))
    elif path.suffix in (".json", ".jsonl"):
        strings = []

        def walk(x):
            if isinstance(x, str):
                strings.append(x)
            elif isinstance(x, dict):
                for v in x.values():
                    walk(v)
            elif isinstance(x, list):
                for v in x:
                    walk(v)
        chunks = raw.splitlines() if path.suffix == ".jsonl" else [raw]
        for c in chunks:
            try:
                walk(json.loads(c))
            except ValueError:
                strings.append(c)
        raw = nfc("\n".join(strings))
    raw = re.sub(r"[*_`「」『』“”\"'|]", "", raw)
    return squash(raw)


def shared_ok(path):
    """설교자가 7A 문장을 공개 원고에 넣기로 확인한 표시."""
    if path.suffix == ".md":
        fm = frontmatter(path) or {}
        return str(fm.get("shared_by_preacher", "")).lower() == "true"
    if path.suffix == ".html":
        head = path.read_text(encoding="utf-8", errors="replace")[:5000]
        return bool(re.search(r'<meta\s+name="dsc-shared-by-preacher"\s+content="true"', head, re.I))
    return False


def is_private(path):
    if path.suffix == ".md":
        fm = frontmatter(path) or {}
        return str(fm.get("private", "")).lower() == "true"
    if path.suffix == ".html":
        head = path.read_text(encoding="utf-8", errors="replace")[:5000]
        return bool(re.search(r'<meta\s+name="dsc-private"\s+content="true"', head, re.I))
    return False


def weeks(paths):
    out = []
    for a in paths:
        p = Path(a).expanduser().resolve()
        if re.match(r"^S_\d{8}$", p.name):
            out.append(p)
        elif p.is_dir():
            out += sorted(d for d in p.rglob("S_*") if d.is_dir() and re.match(r"^S_\d{8}$", d.name))
    return out


def check_week(wd, cfg):
    errs, warns, notes = [], [], []
    selfs = [f for f in wd.rglob("*") if f.is_file() and SELF_RX.match(nfc(f.name))]
    try:
        legacy = json.loads((wd / "progress.json").read_text(encoding="utf-8")).get("dsc_version") != "1.0.0"
    except (OSError, ValueError):
        legacy = True
    report = warns if legacy else errs
    pool = set()
    for f in selfs:
        fm = frontmatter(f) or {}
        tags = fm.get("tags") if isinstance(fm.get("tags"), list) else []
        if str(fm.get("private", "")).lower() != "true":
            report.append("private-flag: %s에 private: true가 없습니다" % f.name)
        if "private" not in tags:
            report.append("private-flag: %s tags에 private가 없습니다" % f.name)
        pool |= sentences(f.read_text(encoding="utf-8", errors="replace"))

    # 7A 이전 단계(01~06)와 수집본에 이미 있던 문장은 7A에서 생긴 문장이 아닙니다(성경 인용·앞 단계 기록).
    if pool:
        for f in wd.rglob("*"):
            if f.is_file() and f.suffix in TEXT_SUFFIX and f not in selfs and (
                    PRIOR_RX.match(nfc(f.name)) or f.relative_to(wd).parts[0] == "00_수집" and f.name == "passage.json"):
                text = plain(f)
                pool = {s for s in pool if s not in text}
    if pool:
        for f in sorted(wd.rglob("*")):
            if not f.is_file() or f.suffix not in TEXT_SUFFIX or f in selfs:
                continue
            text = plain(f)
            hits = sum(1 for s in pool if s in text)
            if not hits:
                continue
            rel = f.relative_to(wd)
            if PRIOR_RX.match(nfc(f.name)):
                continue
            if rel.parts[0] == "00_수집":
                warns.append("log-leak: %s에 7A 문장 %d개가 있습니다 (작업 기록·수집본)" % (rel, hits))
            elif is_private(f):
                continue
            elif shared_ok(f):
                notes.append("shared: %s에 7A 문장 %d개 — 설교자가 공개를 확인함(shared_by_preacher)" % (rel, hits))
            else:
                report.append("leak: %s에 7A 문장 %d개가 있는데 비공개 표시가 없습니다 "
                              "(private: true 또는 설교자 확인 shared_by_preacher: true)" % (rel, hits))

    if stage3_private(cfg) and not legacy:
        for f in wd.glob("03_원어관찰_*.md"):
            if not is_private(f):
                errs.append("stage3: %s에 private: true가 없습니다 (설정 stage3_private)" % f.name)
    return errs, warns + notes


def main(argv):
    as_json = "--json" in argv
    cfg_path = None
    args = []
    it = iter(argv)
    for a in it:
        if a == "--config":
            cfg_path = next(it, None)
        elif a != "--json":
            args.append(a)
    cfg = load_config(cfg_path)
    ws = weeks(args)
    if not ws:
        print("주간 폴더(S_YYYYMMDD)를 찾지 못했습니다: %s" % " ".join(args), file=sys.stderr)
        return 2
    total, result = 0, {}
    for wd in ws:
        e, w = check_week(wd, cfg)
        result[wd.name] = {"errors": e, "warnings": w}
        total += len(e)
    if as_json:
        print(json.dumps({"weeks": len(ws), "errors": total, "result": result}, ensure_ascii=False, indent=1))
    else:
        for name, r in result.items():
            print(("✗ " if r["errors"] else "✓ ") + name)
            for x in r["errors"]:
                print("    오류  " + x)
            for x in r["warnings"]:
                print("    경고  " + x)
        print("\n주간 %d개, 오류 %d건" % (len(ws), total))
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
