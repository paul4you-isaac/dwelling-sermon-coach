#!/usr/bin/env python3
"""단계 번호 점검기 — references/stage-map.md 규칙을 강제한다.

검사 항목
1. 「Stage N」 바로 뒤(20자 안)에 그 단계의 이름(별칭)이 있는가.
   - 이름이 없으면, 그 줄이 속한 `Stage N` 제목 절 안일 때만 허용.
   - 다른 단계의 이름이 붙어 있으면 불일치 오류.
2. 「Stage 4-5」 같은 범위 표기 금지 (단계마다 이름을 붙여 따로 쓴다).
3. 구판 파일명(03_1차청중, 06A_자기적용, Stage3_…_1차청중 등) 금지.
4. 「N단계」는 9단계·0단계와 예외 표현(6단계 서사 등)에만 허용.

사용: python3 tools/check_stage_refs.py [경로 ...]   (기본: skills agents README.md CONNECTORS.md)
종료 코드: 오류가 있으면 1.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 별칭: 긴 것부터 맞춘다.
ALIASES = {
    "0": ["자료 수집", "수집"],
    "1": ["본문만남", "본문 만남", "본문낭독"],
    "2": ["동행일지", "본문과 동행", "동행"],
    "3": ["원어·구문 관찰", "원어 관찰", "원어관찰", "원어"],
    "4": ["1차청중", "1차 청중"],
    "5": ["맥락관찰", "맥락 살피기", "맥락", "페리코프"],
    "6": ["묵직한 한 단어", "묵직한단어", "묵직한 단어"],
    "7": ["오늘적용", "오늘 적용", "적용"],
    "7A": ["자기적용", "자기 적용", "자신에게"],
    "7B": ["회중적용", "회중 적용", "회중에게"],
    "8": ["원고점검", "원고 4문", "4문", "묵상종합"],
    "9": ["설교개요", "설교 개요", "개요"],
}
ALIAS_LIST = sorted(((a, k) for k, v in ALIASES.items() for a in v), key=lambda x: -len(x[0]))

# 허용 관계: 참조 키 → 받아들이는 별칭 키
ACCEPT = {k: {k} for k in ALIASES}
ACCEPT["7"] = {"7", "7A", "7B"}
ACCEPT["7A"] = {"7A", "7"}
ACCEPT["7B"] = {"7B", "7"}

STAGE_RE = re.compile(r"Stage\s?(\d{1,2})([AB])?")
RANGE_RE = re.compile(r"Stage\s?\d[AB]?\s?[-~–]\s?\d")
HEAD_RE = re.compile(r"^(#{1,4})\s+.*?Stage\s?(\d)([AB])?")
DANGYE_RE = re.compile(r"(\d+)단계")
DANGYE_OK_CONTEXT = ["서사", "Baxter", "Robinson", "baxter", "sermon-coach", "fallback", "sermon-editor",
                     "편집", "11단계", "10단계", "검증 단계"]

NEW_FILE = {"1차청중": "04", "맥락관찰": "05", "묵직한단어": "06", "자기적용": "07A",
            "회중적용": "07B", "원고점검": "08", "원어관찰": "03", "동행일지": "02", "본문만남": "01"}
FILE_RE = re.compile(r"(?<![\w])(0\d[AB]?)_(" + "|".join(NEW_FILE) + r")")
HTML_RE = re.compile(r"Stage(\d)_[^\s`|)]*?(1차청중|페리코프|본문만남|본문낭독)")
HTML_NEW = {"본문만남": "1", "본문낭독": "1", "1차청중": "4", "페리코프": "5"}

SKIP_FILES = {"stage-map.md", "CHANGELOG.md"}


def first_alias(text):
    best = None
    for alias, key in ALIAS_LIST:
        i = text.find(alias)
        if i != -1 and (best is None or i < best[0]):
            best = (i, key, alias)
    return best


def check_file(path):
    errs = []
    section = None  # 현재 Stage 제목 절의 키
    in_code = False
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip().startswith("```"):
            in_code = not in_code
        hm = HEAD_RE.match(line) if not in_code else None
        parent = section
        if hm:
            hkey = hm.group(2) + (hm.group(3) or "")
            # 같은 단계 절 안의 하위 제목(### Stage 1 산출물 등)은 이름 생략 허용
            level = len(hm.group(1))
            if level <= 2 or section is None:
                section = hkey
            if level >= 3 and parent and hkey in ACCEPT.get(parent, {parent}) | {parent}:
                hm = None
        elif not in_code and re.match(r"^#{1,2}\s", line):
            section = None

        if RANGE_RE.search(line):
            errs.append((n, "범위 표기 금지(단계마다 이름을 붙여 따로)", line))

        for m in STAGE_RE.finditer(line):
            key = m.group(1) + (m.group(2) or "")
            if key not in ALIASES:
                errs.append((n, f"없는 단계 번호 Stage {key}", line))
                continue
            after = line[m.end():m.end() + 20]
            fa = first_alias(after)
            if fa and fa[0] <= 12:
                if fa[1] not in ACCEPT[key]:
                    errs.append((n, f"Stage {key} 뒤 이름 불일치: 「{fa[2]}」은 Stage {fa[1]}", line))
                continue
            if hm:  # 제목 줄 자체
                errs.append((n, f"제목의 Stage {key}에 이름이 없음", line))
                continue
            if section and key in ACCEPT.get(section, {section}) | ({section} if section.startswith(key) else set()):
                continue
            errs.append((n, f"Stage {key}에 이름이 없음(자기 절 밖)", line))

        for m in FILE_RE.finditer(line):
            num, name = m.group(1), m.group(2)
            if NEW_FILE[name] != num:
                errs.append((n, f"구판 파일명 {num}_{name} → {NEW_FILE[name]}_{name}", line))
        for m in HTML_RE.finditer(line):
            num, name = m.group(1), m.group(2)
            if HTML_NEW[name] != num:
                errs.append((n, f"구판 HTML 이름 Stage{num}_…{name} → Stage{HTML_NEW[name]}", line))

        for m in DANGYE_RE.finditer(line):
            num = m.group(1)
            if num in ("9", "0"):
                continue
            tail = line[m.end():m.end() + 6]
            if any(c in line for c in DANGYE_OK_CONTEXT) or tail.lstrip().startswith("서사"):
                continue
            errs.append((n, f"「{num}단계」 사용 — 9단계 또는 예외 표현만 허용", line))
    return errs


def main(argv):
    targets = argv or ["skills", "agents", "README.md", "CONNECTORS.md"]
    files = []
    for t in targets:
        p = (ROOT / t) if not Path(t).is_absolute() else Path(t)
        if p.is_dir():
            files += sorted(p.rglob("*.md"))
        elif p.exists():
            files.append(p)
    total = 0
    for f in files:
        if f.name in SKIP_FILES:
            continue
        for n, msg, line in check_file(f):
            total += 1
            rel = f.relative_to(ROOT) if f.is_relative_to(ROOT) else f
            print(f"{rel}:{n}: {msg}\n    {line.strip()[:120]}")
    print(f"\n점검 파일 {len(files)}개 · 오류 {total}건")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
