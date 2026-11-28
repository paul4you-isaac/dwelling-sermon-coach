#!/usr/bin/env python3
"""기록보관 에이전트(dsc-archivist)가 부르는 기록 명령.

  python3 dsc_archive.py init          --week-dir D --ref "고린도후서 4:1-18" --sermon-date 2026-11-08
  python3 dsc_archive.py status        --week-dir D
  python3 dsc_archive.py validate      --week-dir D [--config C]
  python3 dsc_archive.py advance_stage --week-dir D --to 4 --confirmed-by-preacher
  python3 dsc_archive.py render_stage3 --week-dir D [--config C]

지키는 것 (코드로 강제)
- 설교자가 쓴 파일의 내용을 고치지 않습니다. 문제는 issues로만 보고합니다.
- 직접 쓰는 파일: progress.json · 00_진행상황.md · 03_원어관찰_…md · 03_나의번역_…md(생성본)뿐입니다.
- 07A(자기적용) 파일은 frontmatter만 읽습니다. 본문을 읽거나 출력하지 않습니다.
- progress.json은 임시 파일에 쓴 뒤 바꿔 끼웁니다(원자적 쓰기). 관찰 작업창 서버도 같은 함수를 씁니다.
"""
import argparse
import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import os
import re
import sys
import tempfile
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dsc_bible as B
import dsc_syntax as SX  # noqa: E402

DSC_VERSION = "1.0.0"
DEFAULT_CONFIG = Path.home() / ".config/dsc/dsc.config.json"
ORDER = ["0", "1", "2", "3", "4", "5", "6", "7A", "7B", "8", "9"]
NAMES = {"0": "수집", "1": "본문만남", "2": "동행일지", "3": "원어관찰", "4": "1차청중", "5": "맥락관찰",
         "6": "묵직한단어", "7A": "자기적용", "7B": "회중적용", "8": "원고점검", "9": "설교개요"}
DATE = r"\d{4}-\d{2}-\d{2}"
# 파일명 규칙 (stage-map.md). 값: (단계 키, 정규식)
FILE_RULES = [
    ("1", r"^01_본문만남_%s_.+\.md$" % DATE),
    ("2", r"^02_동행일지_%s(_%s)?_.+\.md$" % (DATE, DATE)),
    ("3", r"^03_원어관찰_%s_.+\.md$" % DATE),
    ("3", r"^03_나의번역_%s_.+\.md$" % DATE),
    ("4", r"^04_1차청중_%s_.+\.md$" % DATE),
    ("5", r"^05_맥락관찰_%s_.+\.md$" % DATE),
    ("6", r"^06_묵직한단어_%s_.+\.md$" % DATE),
    ("7A", r"^07A_자기적용_%s_.+\.md$" % DATE),
    ("7B", r"^07B_회중적용_%s_.+\.md$" % DATE),
    ("8", r"^08_원고점검_%s_.+\.md$" % DATE),
    ("8S", r"^설교_\d{8}_.+_묵상종합\.md$"),
    ("9", r"^설교_\d{8}_.+_개요\.md$"),
]
ALLOWED_OTHER = [
    r"^progress\.json$", r"^\.progress\.lock$", r"^\.render\.lock$", r"^00_진행상황\.md$", r"^03_원어관찰\.json$",
    r"^Stage1_.+_본문만남\.html$", r"^Stage1_.+_본문낭독\.(mp4|timeline\.json)$", r"^Stage4_.+_1차청중_페르소나\.html$", r"^Stage5_.+_페리코프3단\.html$",
    r"^설교_\d{8}_.+_개요\.html$", r".+_낭독본\.(md|html)$", r".+_원고_초고\.md$",
    r"^성경봉독_.+", r"^설교프롬프터_.+", r"^\.DS_Store$",
]
OLD_NAMES = {r"^03_1차청중_": "04_1차청중_", r"^04_맥락관찰_": "05_맥락관찰_", r"^05_묵직한단어_": "06_묵직한단어_",
             r"^06A_자기적용_": "07A_자기적용_", r"^06B_회중적용_": "07B_회중적용_", r"^07_원고점검_": "08_원고점검_"}
COMMON = ["dsc_version", "date", "sermon_date", "text", "stage", "session", "preacher", "church", "status", "tags"]
STAGE_TAG = {"1": "stage-1-encounter", "2": "stage-2-dwelling", "3": "stage-3-original", "4": "stage-4-audience",
             "5": "stage-5-context", "6": "stage-6-keyword", "7A": "stage-7a-self", "7B": "stage-7b-congregation",
             "8": "stage-8-review", "9": "stage-9-outline", "8S": "묵상종합"}
EXTRA = {"3": ["generated"], "6": ["keyword"], "7A": ["private"], "8": ["keyword", "big_idea"],
         "9": ["keyword", "big_idea"], "8S": ["date_compiled", "keyword", "big_idea"]}


class Refused(Exception):
    pass


def now():
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def nfc(s):
    return unicodedata.normalize("NFC", s)


def _legacy_text(c):
    """M4 구문별 세 칸(관찰·해석·적용) 기록을 한 덩어리 글로."""
    return "\n".join("%s: %s" % (lab, c[k]) for k, lab in (("observe", "관찰"), ("interpret", "해석"), ("apply", "적용"))
                     if isinstance(c.get(k), str) and c[k].strip())


def split_notes(data):
    """03_원어관찰.json → (절 기록 {ref: 기록}, 짝 없는 기록 목록). 작업창 서버와 생성본이 함께 씁니다.

    - 형식이 어긋난 항목은 건너뜁니다(파일 전체를 못 읽게 만들지 않음).
    - M4 형식(구문별 세 칸, `clauses`·`_orphans`)은 버리지 않고 짝 없는 기록으로 바꿉니다.
    - 절마다 `note`(묵상 노트)와 `translation`(나의 번역)을 둡니다. `translation`이 없는 예전 파일은 빈 글로 읽습니다.
    """
    data = data if isinstance(data, dict) else {}
    def lst(k):
        return [x for x in data.get(k) or [] if isinstance(x, dict)] if isinstance(data.get(k), list) else []
    def tr(x):
        return x.get("translation") if isinstance(x.get("translation"), str) else ""
    recs = {}
    for v in lst("verses"):
        if isinstance(v.get("ref"), str) and isinstance(v.get("note", ""), str):
            recs[v["ref"]] = {"ref": v["ref"], "note": v.get("note", ""), "translation": tr(v),
                              "updated": str(v.get("updated", ""))}
    olds = []
    for o in lst("_orphans") + lst("clauses"):
        if isinstance(o.get("note"), str) or isinstance(o.get("translation"), str):
            text, ref = o.get("note") if isinstance(o.get("note"), str) else "", o.get("ref")
        else:
            text, ref = _legacy_text(o), o.get("id") or o.get("verse")
        if text.strip() or tr(o).strip():
            olds.append({"ref": ref if isinstance(ref, str) else "", "note": text, "translation": tr(o),
                         "updated": str(o.get("updated", ""))})
    return recs, olds


def stage3_private(cfg):
    """원어관찰 묵상 노트를 비공개로 다룰지. 예전 이름 stage3_apply_private도 읽습니다."""
    return bool(cfg.get("stage3_private", cfg.get("stage3_apply_private", False)))


def load_config(path):
    p = Path(path or DEFAULT_CONFIG).expanduser()
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def atomic_write(path, text):
    """같은 폴더의 고유 임시 파일(O_EXCL)에 쓰고 fsync 뒤 바꿔 끼웁니다."""
    path = Path(path)
    fd, tmp = tempfile.mkstemp(prefix="." + path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


@contextlib.contextmanager
def progress_lock(wd):
    """주간 폴더 쓰기 잠금. progress.json·03_원어관찰.json을 쓰는 모든 쪽(기록보관·작업창 서버)이 씁니다."""
    with open(Path(wd) / ".progress.lock", "a") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lk, fcntl.LOCK_UN)


def norm_stage(x):
    """단계 값을 표 기준 문자열로 맞춥니다. 표에 없으면 None."""
    if isinstance(x, bool) or x is None:
        return None
    k = str(x).strip().upper()
    return k if k in ORDER else None


def week(args):
    wd = Path(args.week_dir).expanduser().resolve()
    if not re.match(r"^S_\d{8}$", wd.name):
        raise Refused("주간 폴더 이름은 S_YYYYMMDD여야 합니다: %s" % wd.name)
    return wd


def read_progress(wd):
    pj = wd / "progress.json"
    if not pj.exists():
        return None
    return json.loads(pj.read_text(encoding="utf-8"))


def write_progress(wd, st):
    st["updated"] = now()
    atomic_write(wd / "progress.json", json.dumps(st, ensure_ascii=False, indent=1) + "\n")


# ---------------------------------------------------------------- frontmatter
def frontmatter(path, limit=200):
    """첫 --- 블록만 읽습니다(본문은 읽지 않음). 단순 YAML: key: value, 목록(- x 또는 [a, b])."""
    fm, lines = {}, []
    with open(path, encoding="utf-8", errors="replace") as f:
        first = f.readline()
        if first.strip() != "---":
            return None
        closed = False
        for _ in range(limit):
            line = f.readline()
            if not line:
                break
            if line.strip() == "---":
                closed = True
                break
            lines.append(line.rstrip("\n"))
        if not closed:          # 닫히지 않은 머리말은 본문일 수 있으므로 읽지 않습니다
            return None
    key = None
    for ln in lines:
        m = re.match(r"^([A-Za-z_][\w-]*)\s*:\s*(.*)$", ln)
        if m:
            key, val = m.group(1), m.group(2).strip()
            if val.startswith("[") and val.endswith("]"):
                fm[key] = [x.strip().strip("'\"") for x in val[1:-1].split(",") if x.strip()]
            elif val == "":
                fm[key] = []
            else:
                fm[key] = val.strip("'\"")
        elif key and re.match(r"^\s*-\s+", ln) and isinstance(fm.get(key), list):
            fm[key].append(re.sub(r"^\s*-\s+", "", ln).strip().strip("'\""))
    return fm


def stage_of(name):
    for key, rx in FILE_RULES:
        if re.match(rx, name):
            return key
    return None


# ---------------------------------------------------------------- tasks
def render_progress_md(wd, st):
    files = sorted(nfc(f.name) for f in wd.iterdir() if f.is_file())
    cur = norm_stage(st.get("current_stage")) or "0"
    rows = ["| 단계 | 이름 | 상태 | 들어간 때 | 파일 |", "|---|---|---|---|---|"]
    for k in ORDER:
        mine = [f for f in files if stage_of(f) in ((k, "8S") if k == "8" else (k,))]
        if k == "0":
            mine = ["00_수집/"] if (wd / "00_수집").is_dir() else []
        state = "진행 중" if k == cur else ("지남" if ORDER.index(k) < ORDER.index(cur) else "대기")
        rows.append("| %s | %s | %s | %s | %s |" % (k, NAMES[k], state, st.get("stage_entered", {}).get(k, ""),
                                                   " · ".join(mine) or "—"))
    out = ["---", "dsc_version: %s" % DSC_VERSION, "text: %s" % st.get("text", ""),
           "sermon_date: %s" % st.get("sermon_date", ""), "generated: true", "---", "",
           "# 진행 상황 — %s" % st.get("text", ""), "",
           "지금 단계: **%s %s** · 기록보관 에이전트가 만든 파일입니다. 손으로 고치지 마십시오." % (cur, NAMES.get(cur, "")),
           ""] + rows
    atomic_write(wd / "00_진행상황.md", "\n".join(out) + "\n")


def cmd_init(args, cfg):
    wd = Path(args.week_dir).expanduser().resolve()
    if not re.match(r"^S_\d{8}$", wd.name):
        raise Refused("주간 폴더 이름은 S_YYYYMMDD여야 합니다: %s" % wd.name)
    root = cfg.get("vault_root")
    if root:
        # 작업창은 vault_root 바로 아래의 S_ 폴더만 봅니다. NFC/NFD·대소문자 표기 차이는 같은 폴더로 봅니다.
        rp = Path(root).expanduser().resolve()
        same = (os.path.samefile(wd.parent, rp) if wd.parent.exists() and rp.exists()
                else nfc(os.path.normcase(str(wd.parent))) == nfc(os.path.normcase(str(rp))))
        if not same:
            raise Refused("주간 폴더는 설정 vault_root 바로 아래에 둡니다: %s/%s "
                          "(리허설은 그 볼트를 vault_root로 둔 설정을 --config로 넘기십시오)" % (rp, wd.name))
    if not args.ref or not args.sermon_date:
        raise Refused("init에는 --ref와 --sermon-date가 필요합니다")
    try:
        args.ref = B.ref_text(B.parse_ref(args.ref))
    except B.RefError as e:
        raise Refused(str(e))
    if not re.match(r"^%s$" % DATE, args.sermon_date):
        raise Refused("설교일은 YYYY-MM-DD 형식이어야 합니다")
    st = read_progress(wd) if wd.exists() else None
    if st is not None and st.get("dsc_version") != DSC_VERSION:
        raise Refused("구판(v0.4) 주간 폴더입니다. 읽기 전용으로 둡니다.")
    if wd.exists() and st is None and any(
            f.is_file() and (stage_of(nfc(f.name)) or re.match(r"^0[1-9]A?B?_", nfc(f.name)))
            for f in wd.iterdir()):
        raise Refused("progress.json 없이 산출물이 있는 폴더(구판)입니다. 읽기 전용으로 둡니다.")
    (wd / "00_수집").mkdir(parents=True, exist_ok=True)
    if st is None:
        st = {"dsc_version": DSC_VERSION, "week": wd.name, "text": args.ref, "sermon_date": args.sermon_date,
              "current_stage": "0", "stage_entered": {"0": now()}, "history": [], "stage3_render": None}
        with progress_lock(wd):
            if read_progress(wd) is None:
                write_progress(wd, st)
    render_progress_md(wd, st)
    return {"status": "ok", "issues": [], "saved": [str(wd / "progress.json"), str(wd / "00_진행상황.md")]}


def need_v1(wd):
    st = read_progress(wd)
    if st is None or st.get("dsc_version") != DSC_VERSION:
        raise Refused("v1.0.0 주간 폴더가 아닙니다(progress.json 없음 또는 구판). 읽기 전용입니다.")
    return st


def cmd_status(args, cfg):
    wd = week(args)
    st = read_progress(wd)
    if st is None or st.get("dsc_version") != DSC_VERSION:
        legacy = sorted(nfc(f.name) for f in wd.iterdir() if f.is_file() and f.suffix == ".md")
        return {"status": "ok", "legacy": True, "files": legacy, "issues": []}
    cur = norm_stage(st.get("current_stage"))
    if cur is None:
        raise Refused("progress.json의 current_stage 값이 단계 대응표에 없습니다")
    files = {}
    for f in wd.iterdir():
        k = stage_of(nfc(f.name))
        if k:
            files.setdefault(k, []).append(nfc(f.name))
    col = wd / "00_수집"
    com = col / "주석"
    return {"status": "ok", "current_stage": cur, "name": NAMES[cur],
            "stage_entered": st.get("stage_entered", {}), "files": files,
            "collected": {"passage": (col / "passage.json").exists(),
                          "commentary": len(list(com.glob("*.md"))) if com.is_dir() else 0},
            "issues": []}


def cmd_advance(args, cfg):
    wd = week(args)
    need_v1(wd)
    if not args.confirmed_by_preacher:
        raise Refused("설교자가 다음 단계를 확인했을 때만 단계를 올립니다 (--confirmed-by-preacher)")
    return advance(wd, args.to)


def advance(wd, to_raw, by="archivist"):
    """단계를 올립니다. 설교자 확인은 부르는 쪽(감독의 --confirmed-by-preacher, 작업창 버튼)이 책임집니다."""
    to = norm_stage(to_raw)
    if to is None:
        raise Refused("알 수 없는 단계: %s" % to_raw)
    with progress_lock(wd):
        st = need_v1(wd)                      # 잠금 안에서 다시 읽습니다
        cur = norm_stage(st.get("current_stage"))
        if cur is None:
            raise Refused("progress.json의 current_stage 값이 단계 대응표에 없습니다")
        if ORDER.index(to) <= ORDER.index(cur):
            raise Refused("단계를 되돌리거나 같은 단계로 올릴 수 없습니다 (지금 %s → %s)" % (cur, to))
        skipped = ORDER[ORDER.index(cur) + 1:ORDER.index(to)]
        st.setdefault("history", []).append({"from": cur, "to": to, "at": now(), "skipped": skipped, "by": by})
        st["current_stage"] = to
        st.setdefault("stage_entered", {})[to] = now()
        write_progress(wd, st)
    render_progress_md(wd, st)
    issues = [{"file": "progress.json", "problem": "건너뛴 단계: %s" % ", ".join(skipped),
               "suggestion": "설교자가 건너뛰기로 했는지 확인하십시오"}] if skipped else []
    return {"status": "ok" if not issues else "issues", "issues": issues, "current_stage": to}


def cmd_validate(args, cfg):
    wd = week(args)
    st = read_progress(wd)
    if st is None or st.get("dsc_version") != DSC_VERSION:
        return {"status": "ok", "legacy": True, "issues": [],
                "note": "구판 주간 폴더는 검사하지 않습니다(읽기 전용)."}
    only = (args.stage or "").upper() or None
    issues = []
    for f in sorted(wd.iterdir(), key=lambda x: nfc(x.name)):
        name = nfc(f.name)
        if f.is_dir():
            if name not in ("00_수집",):
                issues.append({"file": name, "problem": "허용 목록에 없는 폴더", "suggestion": "주간 폴더 밖으로 옮기십시오"})
            continue
        key = stage_of(name)
        if key is None:
            if any(re.match(rx, name) for rx in ALLOWED_OTHER):
                continue
            old = next((new for rx, new in OLD_NAMES.items() if re.match(rx, name)), None)
            issues.append({"file": name, "problem": "파일명이 단계 대응표와 맞지 않습니다",
                           "suggestion": ("구판 번호입니다. %s…로 바꾸십시오" % old) if old
                           else "stage-map.md의 파일명 규칙을 따르십시오"})
            continue
        if only and key.rstrip("S") != only and key != only:
            continue
        fm = frontmatter(f)
        if fm is None:
            issues.append({"file": name, "problem": "YAML frontmatter가 없습니다", "suggestion": "output-templates.md의 머리말을 붙이십시오"})
            continue
        hide = key == "7A"           # 비공개 파일: 값을 메시지에 넣지 않습니다

        def val(v):
            return "(비공개 파일 — 값 생략)" if hide else v
        for k in fm:
            if "-" in k:
                issues.append({"file": name, "problem": "하이픈 키 %s" % val(k), "suggestion": "%s로 바꾸십시오" % val(k.replace("-", "_"))})
        need = [k for k in COMMON if not (key == "8S" and k in ("date", "stage", "session"))] + EXTRA.get(key, [])
        for k in need:
            if k not in fm or fm[k] in ("", []):
                issues.append({"file": name, "problem": "필수 키 %s가 없습니다" % k, "suggestion": "yaml-schema.md 참고"})
        if fm.get("dsc_version") not in (None, DSC_VERSION):
            issues.append({"file": name, "problem": "dsc_version이 %s입니다" % val(fm.get("dsc_version")), "suggestion": "1.0.0"})
        want_stage = {"7A": "7", "7B": "7", "8S": None}.get(key, key)
        if want_stage and fm.get("stage") and str(fm.get("stage")) != want_stage:
            issues.append({"file": name, "problem": "파일명 번호(%s)와 stage 값(%s)이 다릅니다" % (key, val(fm.get("stage"))),
                           "suggestion": "stage: %s" % want_stage})
        for dk in ("date", "sermon_date", "date_compiled"):
            if dk in fm and fm[dk] and not re.match(r"^%s$" % DATE, str(fm[dk])):
                issues.append({"file": name, "problem": "%s 형식이 YYYY-MM-DD가 아닙니다" % dk, "suggestion": "예: 2026-11-08"})
        if fm.get("status") and fm["status"] not in ("dwelling", "ready"):
            issues.append({"file": name, "problem": "status 값 %s" % val(fm["status"]), "suggestion": "dwelling 또는 ready"})
        if key == "8S" and fm.get("status") and fm["status"] != "ready":
            issues.append({"file": name, "problem": "묵상종합의 status가 ready가 아닙니다", "suggestion": "status: ready"})
        tags = fm.get("tags") if isinstance(fm.get("tags"), list) else []
        if tags and STAGE_TAG[key] not in tags:
            issues.append({"file": name, "problem": "단계 태그 %s가 없습니다" % STAGE_TAG[key], "suggestion": "tags에 추가"})
        if key == "7A":
            if str(fm.get("private", "")).lower() != "true":
                issues.append({"file": name, "problem": "07A에 private: true가 없습니다 (가장 중요)",
                               "suggestion": "frontmatter에 private: true를 넣으십시오"})
            if "private" not in tags:
                issues.append({"file": name, "problem": "07A tags에 private가 없습니다", "suggestion": "tags에 private 추가"})
        if key == "3" and stage3_private(cfg) and str(fm.get("private", "")).lower() != "true":
            issues.append({"file": name, "problem": "설정상 원어관찰 묵상 노트가 비공개인데 private: true가 없습니다",
                           "suggestion": "render_stage3로 다시 만드십시오"})
    return {"status": "ok" if not issues else "issues", "issues": issues}


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def cmd_render3(args, cfg):
    return render_stage3(week(args), cfg)


@contextlib.contextmanager
def render_lock(wd):
    """생성본 만들기 전체(확인 → 쓰기 → 해시 기록)를 한 번에 하나만 하게 합니다(스레드·프로세스 모두)."""
    with open(Path(wd) / ".render.lock", "a") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lk, fcntl.LOCK_UN)


RENDER_NAME = re.compile(r"^03_원어관찰_%s_[^/\\]+\.md$" % DATE)
TRANSLATION_NAME = re.compile(r"^03_나의번역_%s_[^/\\]+\.md$" % DATE)


def render_stage3(wd, cfg):
    """03_원어관찰.json → 생성본 md 두 개(03_원어관찰_…md · 03_나의번역_…md).
    손으로 고친 생성본·설교자 파일은 덮어쓰지 않습니다."""
    with render_lock(wd):
        r = _render_stage3(wd, cfg)
        t = _render_translation(wd, cfg)
        if t is None:                         # 나의 번역을 아직 한 절도 쓰지 않았으면 만들지 않습니다
            return r
        return {"status": "ok" if r["status"] == t["status"] == "ok" else "issues",
                "issues": r.get("issues", []) + t.get("issues", []),
                "saved": r.get("saved", []) + t.get("saved", [])}


def _render_stage3(wd, cfg):
    st = need_v1(wd)
    src = wd / "03_원어관찰.json"
    if not src.exists():
        raise Refused("03_원어관찰.json이 없습니다 (관찰 작업창 또는 감독이 먼저 기록합니다)")
    data = json.loads(src.read_text(encoding="utf-8"))
    if not st.get("text"):
        raise Refused("progress.json에 본문(text)이 없습니다")
    label = B.ref_label(B.parse_ref(st["text"]))
    prev = st.get("stage3_render") or {}
    if not isinstance(prev, dict) or (prev.get("file") and not RENDER_NAME.match(nfc(str(prev["file"])))):
        raise Refused("progress.json의 stage3_render.file 값이 생성본 파일 이름이 아닙니다")
    out_name = prev.get("file") or "03_원어관찰_%s_%s.md" % (dt.date.today().isoformat(), label)
    target = wd / out_name
    issues = []
    if target.exists():
        known = prev.get("file") == out_name and prev.get("sha256")
        if not known:
            return {"status": "issues", "issues": [{"file": out_name, "problem": "같은 이름의 파일이 이미 있는데 생성 기록이 없습니다",
                                                    "suggestion": "덮어쓰지 않았습니다. 설교자 파일인지 확인하십시오"}]}
        if sha(target.read_text(encoding="utf-8")) != prev["sha256"]:
            return {"status": "issues", "issues": [{"file": out_name, "problem": "생성본이 마지막 생성 뒤 손으로 고쳐졌습니다",
                                                    "suggestion": "덮어쓰지 않았습니다. 고친 내용을 작업창에 옮긴 뒤 생성본을 지우고 다시 만드십시오"}]}
    private = stage3_private(cfg)
    tags = ["dwelling-sermon-coach", "stage-3-original"] + (["private"] if private else [])
    fm = ["---", "dsc_version: %s" % DSC_VERSION, "date: %s" % dt.date.today().isoformat(),
          "sermon_date: %s" % st.get("sermon_date", ""), "text: %s" % st["text"], "stage: 3", "session: 원어관찰",
          "preacher: %s" % cfg.get("preacher", ""), "church: %s" % cfg.get("church", ""), "status: dwelling",
          "generated: true"] + (["private: true"] if private else []) + ["tags: [%s]" % ", ".join(tags), "---", ""]
    body = ["# 원어관찰 — %s" % st["text"], "",
            "> 관찰 작업창(03_원어관찰.json)에서 만든 생성본입니다. 고치려면 작업창에서 고치십시오.", ""]
    col = wd / "00_수집"
    orig, syn = {}, {}
    try:
        pas = json.loads((col / "passage.json").read_text(encoding="utf-8"))
        ov = next(iter((pas.get("original") or {}).values()), {}) or {}
        orig = {v.get("ref"): v.get("text", "") for v in ov.get("verses", []) if isinstance(v, dict)}
    except (OSError, ValueError):
        pass
    try:
        sx = json.loads((col / "syntax.json").read_text(encoding="utf-8"))
        syn, _ = SX.validated(sx, pas)                                     # 수집본과 맞는 구문 분석만 씁니다
    except (OSError, ValueError, NameError):
        pass
    parts = []
    recs, olds = split_notes(data)
    for v in (x for x in recs.values() if x["note"].strip() or x["translation"].strip()):   # 빈 절은 넣지 않습니다
        ref = v["ref"]
        sv = syn.get(ref) or {}
        mv = " · ".join(x for x in sv.get("main_verbs", []) if isinstance(x, str))
        one = []
        if orig.get(ref):
            one += ["> %s" % orig[ref], ""]
        chain = " · ".join(x.get("verb", "") for x in sv.get("chain", []) if isinstance(x, dict))
        if mv:
            one += ["**구문** 【AI】 주동사 %s" % mv, ""]
        elif chain:
            one += ["**구문** 【AI】 정동사 없음 — %s" % chain, ""]
        if v["translation"].strip():
            one += ["**나의 번역**", "", v["translation"].strip(), ""]
        if v["note"].strip():
            one += ["**묵상**", "", v["note"].strip(), ""]
        parts.append(["## %s %s" % (B.parse_ref(st["text"])["book"]["ko"], ref), ""] + one)
    for i, part in enumerate(parts):
        body += (["---", ""] if i else []) + part
    if olds:                                                               # 설교자 글은 버리지 않습니다
        body += (["---", ""] if parts else []) + ["## 짝 없는 기록", "",
                 "> 지금 본문의 절과 이어지지 않는 예전 기록입니다(구문별 세 칸 기록 등). 원문 그대로 둡니다.", ""]
        for o in olds:
            body += ["**%s**" % (o["ref"] or "—"), ""]
            if o["translation"].strip():
                body += ["나의 번역: " + o["translation"].strip(), ""]
            if o["note"].strip():
                body += [o["note"].strip(), ""]
    text = "\n".join(fm + body)
    # 확인한 뒤 그사이(Obsidian 저장 등) 손으로 고쳤는지 바꿔 끼우기 직전에 한 번 더 봅니다
    if target.exists() and sha(target.read_text(encoding="utf-8")) != (prev.get("sha256") or ""):
        return {"status": "issues", "issues": [{"file": out_name, "problem": "생성본이 방금 손으로 고쳐졌습니다",
                                                "suggestion": "덮어쓰지 않았습니다"}]}
    atomic_write(target, text)
    with progress_lock(wd):
        fresh = need_v1(wd)                   # 그사이 다른 쪽이 바꾼 단계를 덮지 않도록 다시 읽습니다
        fresh["stage3_render"] = {"file": out_name, "sha256": sha(text), "at": now()}
        write_progress(wd, fresh)
    return {"status": "ok", "issues": issues, "saved": [str(target)]}



def _render_translation(wd, cfg):
    """03_원어관찰.json의 나의 번역 → 03_나의번역_{작업일}_{본문}.md. 설교자 글자 그대로 옮깁니다."""
    st = need_v1(wd)
    recs, _ = split_notes(json.loads((wd / "03_원어관찰.json").read_text(encoding="utf-8")))
    prev = st.get("stage3_translation_render") or {}
    if not isinstance(prev, dict) or (prev.get("file") and not TRANSLATION_NAME.match(nfc(str(prev["file"])))):
        raise Refused("progress.json의 stage3_translation_render.file 값이 나의 번역 파일 이름이 아닙니다")
    if not prev.get("file") and not any(v["translation"].strip() for v in recs.values()):
        return None
    label = B.ref_label(B.parse_ref(st["text"]))
    out_name = prev.get("file") or "03_나의번역_%s_%s.md" % (dt.date.today().isoformat(), label)
    target = wd / out_name
    if target.exists():
        if not (prev.get("file") == out_name and prev.get("sha256")):
            return {"status": "issues", "issues": [{"file": out_name, "problem": "같은 이름의 파일이 이미 있는데 생성 기록이 없습니다",
                                                    "suggestion": "덮어쓰지 않았습니다. 설교자 파일인지 확인하십시오"}]}
        if sha(target.read_text(encoding="utf-8")) != prev["sha256"]:
            return {"status": "issues", "issues": [{"file": out_name, "problem": "나의 번역 생성본이 마지막 생성 뒤 손으로 고쳐졌습니다",
                                                    "suggestion": "덮어쓰지 않았습니다. 고친 내용을 작업창에 옮긴 뒤 생성본을 지우고 다시 만드십시오"}]}
    orig, order = {}, []
    try:
        pas = json.loads((wd / "00_수집" / "passage.json").read_text(encoding="utf-8"))
        ov = next(iter((pas.get("original") or {}).values()), {}) or {}
        for v in ov.get("verses", []):
            if isinstance(v, dict) and isinstance(v.get("ref"), str):
                order.append(v["ref"])
                orig[v["ref"]] = v.get("text", "")
    except (OSError, ValueError, AttributeError):
        pass
    order += [r for r in recs if r not in order]
    private = stage3_private(cfg)
    tags = ["dwelling-sermon-coach", "stage-3-original"] + (["private"] if private else [])
    fm = ["---", "dsc_version: %s" % DSC_VERSION, "date: %s" % dt.date.today().isoformat(),
          "sermon_date: %s" % st.get("sermon_date", ""), "text: %s" % st["text"], "stage: 3", "session: 나의번역",
          "preacher: %s" % cfg.get("preacher", ""), "church: %s" % cfg.get("church", ""), "status: dwelling",
          "generated: true"] + (["private: true"] if private else []) + ["tags: [%s]" % ", ".join(tags), "---", ""]
    body = ["# 나의 번역 — %s" % st["text"], "",
            "> 관찰 작업창(03_원어관찰.json)의 「나의 번역」에서 만든 생성본입니다. 작업창에서 수정하십시오.", ""]
    book = B.parse_ref(st["text"])["book"]["ko"]
    for i, ref in enumerate(order):
        mine = (recs.get(ref) or {}).get("translation", "")
        body += (["---", ""] if i else []) + ["## %s %s" % (book, ref), ""]
        if orig.get(ref):
            body += ["> %s" % orig[ref], ""]
        body += [mine.strip("\n") if mine.strip() else "(비어 있음)", ""]
    text = "\n".join(fm + body)
    atomic_write(target, text)
    with progress_lock(wd):
        fresh = need_v1(wd)
        fresh["stage3_translation_render"] = {"file": out_name, "sha256": sha(text), "at": now()}
        write_progress(wd, fresh)
    return {"status": "ok", "issues": [], "saved": [str(target)]}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("task", choices=["init", "status", "validate", "advance_stage", "render_stage3"])
    ap.add_argument("--week-dir", required=True)
    ap.add_argument("--ref")
    ap.add_argument("--sermon-date")
    ap.add_argument("--to")
    ap.add_argument("--stage")
    ap.add_argument("--confirmed-by-preacher", action="store_true")
    ap.add_argument("--config")
    a = ap.parse_args(argv)
    cfg = load_config(a.config)
    fn = {"init": cmd_init, "status": cmd_status, "validate": cmd_validate,
          "advance_stage": cmd_advance, "render_stage3": cmd_render3}[a.task]
    try:
        r = fn(a, cfg)
    except (Refused, B.RefError) as e:
        r = {"status": "refused", "reason": str(e), "issues": []}
    print(json.dumps(r, ensure_ascii=False, indent=1))
    return 0 if r["status"] in ("ok", "issues") else 1


if __name__ == "__main__":
    sys.exit(main())
