#!/usr/bin/env python3
"""수집 에이전트(dsc-collector)가 부르는 수집 명령.

  python3 dsc_collect.py passage    --week-dir <주간 폴더> --ref "고린도후서 4:1-18" [--config <설정>]
  python3 dsc_collect.py commentary --week-dir <주간 폴더> --ref "고린도후서 4:1-18" [--config <설정>]
  python3 dsc_collect.py syntax     --week-dir <주간 폴더>      (감독의 00_수집/구문분석_초안.json → syntax.json)

지키는 것 (코드로 강제)
- 쓰기는 <주간 폴더>/00_수집/ 안으로만 합니다.
- 주석 수집은 progress.json의 current_stage가 주석 노출 단계(4·5·6·7B·8·9)일 때만 합니다.
- Logos 브리지는 읽기 명령(library·books·excerpt)만 부릅니다.
- 주석은 웹에서 찾지 않습니다. PDF·EPUB 원본에서 뽑지 않습니다.
- 표준 출력은 개수·경로·빠진 항목(구문 분석은 문제 목록)뿐입니다. 본문·주석 내용을 출력하지 않습니다.
- 구문 분석의 원어·새한글·ESV는 수집본 글자와 대조해 다르면 넣지 않습니다.
"""
import argparse
import datetime as dt
import fnmatch
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dsc_bible as B  # noqa: E402
from dsc_archive import frontmatter, norm_stage  # noqa: E402
import dsc_syntax as SX  # noqa: E402

DRAFT = "구문분석_초안.json"

SELF_RX = re.compile(r"^(07A|06A)_자기적용_")

DEFAULT_CONFIG = Path.home() / ".config/dsc/dsc.config.json"
COMMENTARY_STAGES = {"4", "5", "6", "7B", "8", "9"}
BRIDGE_ALLOWED = {"library", "books", "excerpt"}
TEXT_SUFFIX = {".md", ".txt"}
MAX_EXCERPT = 80000


class Refused(Exception):
    pass


def now():
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def load_config(path):
    p = Path(path or DEFAULT_CONFIG).expanduser()
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def collect_dir(week_dir):
    wd = Path(week_dir).expanduser().resolve()
    if not wd.is_dir():
        raise Refused("주간 폴더가 없습니다: %s" % wd)
    return wd, wd / "00_수집"


def safe_write(base, rel, text):
    """base(<주간>/00_수집) 안에만 씁니다.

    00_수집 자체가 링크이거나, 경로 중간·대상이 링크로 밖을 가리키면 거절합니다.
    임시 파일은 고유 이름(O_EXCL)으로 만들어 미리 심어 둔 링크를 따라가지 않습니다.
    """
    base = Path(base)
    if base.is_symlink():
        raise Refused("00_수집이 링크입니다. 쓰지 않습니다")
    base.mkdir(exist_ok=True)
    real_week = os.path.realpath(base.parent)
    real_base = os.path.realpath(base)
    if os.path.dirname(real_base) != real_week:
        raise Refused("00_수집이 주간 폴더 밖을 가리킵니다")
    target = base / rel
    real_target = os.path.realpath(target)
    if os.path.commonpath([real_base, real_target]) != real_base or target.is_symlink():
        raise Refused("00_수집 밖에 쓰려고 했습니다: %s" % rel)
    os.makedirs(os.path.dirname(real_target), exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".dsc.", suffix=".tmp", dir=os.path.dirname(real_target))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, real_target)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return str(target)


def safe_name(s):
    return re.sub(r'[\\/:*?"<>|\s]+', "_", B.nfc(s)).strip("_")[:80]


# ---------------------------------------------------------------- passage
def verses_in_range(p, chap_data):
    """chap_data: {장: {"verses": {절: 본문}}} → [(장, 절, 본문)] 범위 안."""
    (c1, v1), (c2, v2) = p["start"], p["end"]
    out = []
    for c in range(c1, c2 + 1):
        vs = chap_data.get(c, {}).get("verses", {})
        for v in sorted(vs):
            if (c, v) < (c1, v1):
                continue
            if v2 is not None and (c, v) > (c2, v2):
                continue
            out.append((c, v, vs[v]))
    return out


def fetch_version(abbr, p, chapters):
    data = {c: B.fetch_platform(abbr, p["book"]["usfm"], c) for c in chapters}
    return data


def pericopes(p, nkrv):
    """개역개정 소제목으로 앞·뒤 페리코페를 정합니다. nkrv: {장: 장 데이터}.

    시편은 소제목 대신 편(장)이 단락이므로 앞·뒤 편 전체를 씁니다.
    """
    if p["book"]["usfm"] == "PSA":
        (c1, _), (c2, _) = p["start"], p["end"]
        out = {}
        for side, c in (("before", c1 - 1), ("after", c2 + 1)):
            vs = nkrv.get(c, {}).get("verses") or {}
            out[side] = {"title": "시편 %d편" % c, "range": "%d:1-%d:%d" % (c, c, max(vs)), "source": "NKRV",
                         "verses": [{"ref": "%d:%d" % (c, v), "text": t} for v, t in sorted(vs.items())]} if vs else None
        return out
    seq, heads = [], {}
    for c in sorted(nkrv):
        for v, t in nkrv[c]["verses"].items():
            seq.append((c, v, t))
        for v, title in nkrv[c]["headings"]:
            heads[(c, v)] = title
    if not seq:
        return {}
    (c1, v1), (c2, v2) = p["start"], p["end"]
    if v2 is not None:
        end = (c2, v2)
    else:
        last = [(c, v) for c, v, _ in seq if c == c2]
        if not last:
            return {}
        end = max(last)
    keys = [(c, v) for c, v, _ in seq]
    starts = sorted(k for k in heads)

    def block(a, b):
        items = [(c, v, t) for c, v, t in seq if a <= (c, v) <= b]
        if not items:
            return None
        rng = "%d:%d-%d:%d" % (items[0][0], items[0][1], items[-1][0], items[-1][1])
        first = (items[0][0], items[0][1])
        title = heads.get(first)
        if title is None:   # 소제목 중간에서 시작하면 그 소제목을 이어받습니다
            gov = [k for k in starts if k <= first]
            title = (heads[gov[-1]] + " (이어짐)") if gov else ""
        return {"title": title, "range": rng, "source": "NKRV",
                "verses": [{"ref": "%d:%d" % (c, v), "text": t} for c, v, t in items]}

    before = after = None
    prev_heads = [k for k in starts if k < (c1, v1)]
    if prev_heads:
        a = prev_heads[-1]
        b = keys[keys.index((c1, v1)) - 1] if (c1, v1) in keys and keys.index((c1, v1)) > 0 else None
        if b and a <= b:
            before = block(a, b)
    if end in keys and keys.index(end) + 1 < len(keys):
        a = keys[keys.index(end) + 1]
        nxt = [k for k in starts if k > a]
        b = keys[keys.index(nxt[0]) - 1] if nxt else keys[-1]
        after = block(a, b)
    return {"before": before, "after": after}


def remap_psalm(entry, od, nkrv, p, chapters):
    """시편: BHS는 표제를 1절(때로 1-2절)로 셉니다. 장마다 (BHS 절 수 - 개역개정 절 수)만큼 밀어
    한국어 절 번호에 맞춥니다. 원래 번호는 bhs_ref로 남깁니다."""
    (c1, v1), (c2, v2) = p["start"], p["end"]
    out, shifts = [], {}
    for c in chapters:
        ov, kv = od.get(c, {}).get("verses", {}), nkrv.get(c, {}).get("verses", {})
        if not ov or not kv:
            continue
        k = len(ov) - len(kv)
        if k < 0:
            k = 0
        shifts[c] = k
        for v in sorted(kv):
            if (c, v) < (c1, v1) or (v2 is not None and (c, v) > (c2, v2)):
                continue
            t = ov.get(v + k)
            if t is None:
                continue
            item = {"ref": "%d:%d" % (c, v), "text": t}
            if k:
                item["bhs_ref"] = "%d:%d" % (c, v + k)
            out.append(item)
    if any(shifts.values()):
        entry["verses"] = out
        entry["versification"] = {"rule": "시편 표제 보정: 한국어 절 = 원어 절 - 표제 절 수",
                                  "shift": {str(c): k for c, k in shifts.items()}}


def cmd_passage(args, cfg):
    wd, col = collect_dir(args.week_dir)
    p = B.parse_ref(args.ref)
    frz = freeze_check(wd, col)
    (c1, _), (c2, _) = p["start"], p["end"]
    book = p["book"]
    chapters = list(range(c1, c2 + 1))
    near = [c for c in (c1 - 1, c2 + 1) if c >= 1]
    missing, saved = [], []
    result = {"dsc_version": "1.0.0", "reference": B.ref_text(p), "book": book,
              "range": {"start": p["start"], "end": p["end"]}, "collected_at": now(),
              "translations": {}, "original": {}, "clauses": [], "adjacent_pericopes": {},
              "missing": missing}

    def take(abbr, label, slot):
        try:
            data = fetch_version(abbr, p, chapters)
        except Exception as e:  # noqa: BLE001
            missing.append({"item": label, "reason": str(e)[:200]})
            return None
        vs = verses_in_range(p, data)
        if not vs:
            missing.append({"item": label, "reason": "범위 안 절이 없습니다"})
            return None
        (_, v1), (c2, v2) = p["start"], p["end"]
        last = max(data[c2]["verses"]) if data[c2]["verses"] else 0
        if v2 is not None and v2 > last:
            missing.append({"item": "%s %d:%d-%d" % (label, c2, last + 1, v2),
                            "reason": "%d장은 %d절까지입니다" % (c2, last)})
        entry = {"name": label, "abbr": abbr, "source": B.PLATFORM[B.BIBLE_IDS[abbr][0]].split("/")[2],
                 "urls": [data[c]["url"] for c in chapters], "copyright": data[chapters[0]]["copyright"],
                 "method": "자동 fetch", "verses": [{"ref": "%d:%d" % (c, v), "text": t} for c, v, t in vs],
                 "headings": [{"before": "%d:%d" % (c, v), "title": t}
                              for c in chapters for v, t in data[c]["headings"]]}
        sup = [{"chapter": c, "text": t} for c in chapters for t in data[c].get("superscriptions", [])]
        if sup:
            entry["superscriptions"] = sup     # 시편 표제: 역본마다 절 번호에 넣기도 하고 빼기도 합니다
        comb = {k: v for c in chapters for k, v in data[c].get("combined", {}).items()}
        if comb:
            entry["combined_verses"] = comb
        slot[abbr] = entry
        return data

    kdata = {}
    for abbr, label in B.KOREAN:
        data = take(abbr, label, result["translations"])
        if data:
            kdata[abbr] = data
        if data and abbr in B.CROSS:
            checks = []
            for c in chapters:
                try:
                    other, url = B.fetch_old_site(B.CROSS[abbr], book["usfm"], c)
                    r = B.cross_check(data[c]["verses"], other)
                    r.update({"chapter": c, "source": "www.bskorea.or.kr", "url": url})
                except Exception as e:  # noqa: BLE001
                    r = {"chapter": c, "status": "unavailable", "reason": str(e)[:160]}
                checks.append(r)
            result["translations"][abbr]["cross_check"] = checks
        elif data:
            result["translations"][abbr]["cross_check"] = [{"status": "single_source",
                                                            "reason": "두 번째 공식 출처가 없습니다"}]
    esv = take("ESV", "ESV", result["translations"])
    if esv:
        checks = []
        for c in chapters:
            try:
                other = B.fetch_esv(book["en"], c)
                r = B.cross_check(esv[c]["verses"], other["verses"])
                r.update({"chapter": c, "source": "biblegateway.com", "url": other["url"]})
            except Exception as e:  # noqa: BLE001
                r = {"chapter": c, "status": "unavailable", "reason": str(e)[:160]}
            checks.append(r)
        result["translations"]["ESV"]["cross_check"] = checks

    orig_abbr = "BHS" if book["testament"] == "OT" else "NA28"
    od = take(orig_abbr, orig_abbr, result["original"])
    if od and book["usfm"] == "PSA" and "NKRV" in kdata:
        remap_psalm(result["original"][orig_abbr], od, kdata["NKRV"], p, chapters)
    if od:
        for item in result["original"][orig_abbr]["verses"]:
            parts = B.split_clauses(item["text"], book["testament"])
            c, v = item["ref"].split(":")
            for i, t in enumerate(parts):
                result["clauses"].append({"id": "%s.%s%s" % (c, v, B.letters(i)), "verse": item["ref"],
                                          "text": t, "method": "문장부호 기계 분할"})

    # 원어와 개역개정의 절 수가 다르면 알립니다 (시편 표제 등 절 번호 체계 차이)
    notes = []
    if orig_abbr in result["original"] and "NKRV" in result["translations"]:
        no, nk_n = len(result["original"][orig_abbr]["verses"]), len(result["translations"]["NKRV"]["verses"])
        if no != nk_n:
            notes.append("%s %d절 · 개역개정 %d절 — 절 번호 체계가 다릅니다(시편 표제 등). 절끼리 맞춰 볼 때 주의하십시오."
                         % (orig_abbr, no, nk_n))
    result["notes"] = notes

    # 앞·뒤 페리코페 (개역개정 소제목 기준)
    nk = {}
    for c in sorted(set(chapters + near)):
        try:
            nk[c] = B.fetch_platform("NKRV", book["usfm"], c)
        except Exception:  # noqa: BLE001  (책의 처음·끝 장 밖은 없음)
            pass
    adj = pericopes(p, nk) if nk else {}
    result["adjacent_pericopes"] = adj
    for side, label in (("before", "앞 페리코페"), ("after", "뒤 페리코페")):
        if not adj.get(side):
            missing.append({"item": label, "reason": "찾지 못했거나 책의 처음·끝입니다"})

    late = freeze_check(wd, col)                    # 받는 동안 첫 기록이 생겼을 수 있어 쓰기 직전에 다시 봅니다
    if late["written"] and not frz["written"]:
        frz = late
    freeze_clauses(frz, result)
    label = B.ref_label(p)
    saved.append(safe_write(col, "passage.json", json.dumps(result, ensure_ascii=False, indent=1)))
    saved.append(safe_write(col, "본문_%s.md" % label, render_passage_md(result)))
    n_tr = len(result["translations"])
    status = "ok" if not missing else ("failed" if n_tr == 0 else "partial")
    return {"status": status, "saved": saved,
            "counts": {"translations": n_tr, "original": len(result["original"]),
                       "clauses": len(result["clauses"]), "commentary": 0},
            "missing": [m["item"] for m in missing], "notes": result.get("notes", []),
            "cross_check": {k: [c.get("status") for c in v.get("cross_check", [])]
                            for k, v in result["translations"].items()}}


def freeze_check(wd, col):
    """다시 수집하기 전에 봅니다. 원어관찰 기록이 있는데 이전 수집본을 믿을 수 없으면 거절합니다(네트워크 전에)."""
    prev_p, notes_p = col / "passage.json", wd / "03_원어관찰.json"
    try:
        notes = json.loads(notes_p.read_text(encoding="utf-8")) if notes_p.exists() else {}
        if not isinstance(notes, dict):
            raise ValueError
    except (OSError, ValueError):
        raise Refused("03_원어관찰.json을 읽지 못했습니다. 구문 목록을 지킬 수 없어 다시 수집하지 않았습니다")
    recs = [c for key in ("verses", "clauses", "_orphans") for c in (notes.get(key) or []) if isinstance(c, dict)]
    written = any((c.get(k) or "").strip() for c in recs for k in ("note", "observe", "interpret", "apply")
                  if isinstance(c.get(k), str))
    prev = {}
    if prev_p.exists() or prev_p.is_symlink():
        try:
            if prev_p.is_symlink():
                raise ValueError
            prev = json.loads(prev_p.read_text(encoding="utf-8"))
            if not isinstance(prev, dict):
                raise ValueError
        except (OSError, ValueError):
            if written:
                raise Refused("원어관찰 기록이 있는데 이전 수집본(passage.json)을 읽지 못했습니다. "
                              "구문 목록을 지킬 수 없어 다시 수집하지 않았습니다")
            prev = {}
    if written and not prev.get("clauses"):
        raise Refused("원어관찰 기록이 있는데 이전 수집본에 구문 목록이 없습니다. 다시 수집하지 않았습니다")
    return {"prev": prev, "written": written}


def freeze_clauses(frz, result):
    """원어관찰 기록이 하나라도 있으면 구문 목록을 동결합니다(구문 id가 바뀌면 기록이 길을 잃음)."""
    prev = frz["prev"]
    try:
        result["version"] = int(prev.get("version") or 1) + 1 if prev else 1
    except (TypeError, ValueError):
        result["version"] = 2
    if not frz["written"]:
        return
    if prev.get("reference") == result["reference"]:
        result["clauses"] = prev["clauses"]
        result["clauses_frozen"] = True
        result["notes"].append("원어관찰 기록이 있어 구문 목록은 이전 수집본(version %s)을 그대로 씁니다." % prev.get("version", 1))
    else:
        result["notes"].append("본문이 바뀌었습니다(%s → %s). 이전 원어관찰 기록은 작업창에서 「짝 없는 기록」으로 보입니다."
                               % (prev.get("reference"), result["reference"]))


def render_passage_md(r):
    out = ["# 본문 수집 — %s" % r["reference"], "",
           "수집 시각: %s · 수집: dsc-collector (자동 fetch)" % r["collected_at"], "",
           "## 출처", "", "| 역본 | 출처 | 교차 검증 |", "|---|---|---|"]
    for k, t in list(r["original"].items()) + list(r["translations"].items()):
        cc = ", ".join(c.get("status", "") for c in t.get("cross_check", [])) or "—"
        out.append("| %s | %s | %s |" % (t["name"], " · ".join(t["urls"]), cc))
    if r["missing"]:
        out += ["", "## 빠진 항목", ""] + ["- %s: %s" % (m["item"], m["reason"]) for m in r["missing"]]
    refs = []
    for t in list(r["original"].values()) + list(r["translations"].values()):
        for v in t["verses"]:
            if v["ref"] not in refs:
                refs.append(v["ref"])
    order = list(r["original"].values()) + [r["translations"][a] for a in
                                            ("NKT", "RNKSV", "KCT", "NKRV", "ESV") if a in r["translations"]]
    for ref in refs:
        out += ["", "## %s" % ref, ""]
        for t in order:
            txt = next((v["text"] for v in t["verses"] if v["ref"] == ref), None)
            out.append("- **%s** %s" % (t["name"], txt if txt else "(없음)"))
    out += ["", "## 저작권", ""] + ["- %s: %s" % (t["name"], t["copyright"]) for t in order]
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- commentary
def read_stage(wd):
    pj = wd / "progress.json"
    if not pj.exists():
        raise Refused("progress.json이 없습니다. 기록보관 에이전트의 init이 먼저입니다.")
    st = json.loads(pj.read_text(encoding="utf-8"))
    if st.get("dsc_version") != "1.0.0":
        raise Refused("v1.0.0 주간 폴더가 아닙니다 (구판은 읽기 전용).")
    stage = norm_stage(st.get("current_stage"))
    if stage is None:
        raise Refused("progress.json의 current_stage 값이 단계 대응표에 없습니다")
    return stage


def bridge(cfg, *argv):
    if not argv or argv[0] not in BRIDGE_ALLOWED:
        raise Refused("Logos 브리지는 library·books·excerpt만 씁니다")
    path = cfg.get("logos_bridge")
    if not path or not Path(path).exists():
        raise FileNotFoundError("logos_bridge 경로가 설정에 없거나 파일이 없습니다")
    out = subprocess.run([sys.executable, "-I", path, "--json", *argv], capture_output=True, text=True,
                         timeout=120, cwd=str(Path(path).parent))
    if out.returncode != 0:
        raise RuntimeError("브리지 오류: %s" % out.stderr.strip()[:200])
    return json.loads(out.stdout)


def ref_patterns(p):
    """'4:7' · '4:7-12' · '4장 7절' 같은 표기에서 범위 안 절을 찾는 정규식."""
    (c1, v1), (c2, v2) = p["start"], p["end"]
    chs = "|".join(str(c) for c in range(c1, c2 + 1))
    return re.compile(r"(?<!\d)(%s)\s*(?::|장\s*)\s*(\d+)" % chs)


def in_range(p, c, v):
    (c1, v1), (c2, v2) = p["start"], p["end"]
    return (c1, v1) <= (c, v) <= (c2, v2 if v2 is not None else 999)


def book_names(p):
    b = next(x for x in B.BOOKS if x[2] == p["book"]["usfm"])
    en = b[3]
    names = [b[0], en, en.replace(" ", ""), b[2]] + b[1]
    m = re.match(r"^([123]) (\w+)$", en)
    if m:
        names += ["%s %s" % (m.group(1), m.group(2)[:3]), "%s%s" % (m.group(1), m.group(2)[:3])]
    return [n for n in names if len(n) >= 2]


def sections_for(text, p):
    """제목(#)으로 나눈 절 가운데 범위 안 구절을 다루는 절만 모읍니다."""
    pat = ref_patterns(p)
    parts = re.split(r"(?m)^(?=#{1,6}\s)", text)
    keep = []
    for sec in parts:
        head = sec.split("\n", 1)[0]
        scope = head if head.startswith("#") else sec[:400]
        hits = [(int(m.group(1)), int(m.group(2))) for m in pat.finditer(scope)]
        if any(in_range(p, c, v) for c, v in hits):
            keep.append(sec.strip())
    return keep


def scan_materials(cfg, p):
    """설정의 자료 폴더에서 .md·.txt만 봅니다 (PDF·EPUB 제외)."""
    names = [n.lower() for n in book_names(p)]
    glob = cfg.get("md_commentary_glob") or "B_*.md"
    found = []
    for d in cfg.get("materials_dirs") or []:
        root = Path(d).expanduser()
        if not root.is_dir():
            found.append(("__missing__", str(root)))
            continue
        for f in sorted(root.rglob("*")):
            if f.suffix.lower() not in TEXT_SUFFIX or not f.is_file():
                continue
            if (SELF_RX.match(B.nfc(f.name))
                    or any(re.match(r"^S_\d{8}$", part) for part in f.relative_to(root).parts)):
                continue          # 설교자의 자기적용·주간 폴더는 주석 자료가 아닙니다
            if f.suffix.lower() == ".md":
                fm = frontmatter(f) or {}
                if str(fm.get("private", "")).lower() == "true":
                    continue
            fname = B.nfc(f.name).lower()
            kind = "md주석" if fnmatch.fnmatch(B.nfc(f.name), glob) else "자료폴더"
            if not any(n in fname for n in names):
                # 파일명에 책 이름이 없으면 앞부분만 보고 판단합니다.
                try:
                    head = B.nfc(f.read_text(encoding="utf-8", errors="replace")[:4000]).lower()
                except OSError:
                    continue
                if not any(n in head for n in names):
                    continue
            found.append((kind, f))
    return found


def cmd_commentary(args, cfg):
    wd, col = collect_dir(args.week_dir)
    stage = read_stage(wd)
    if stage not in COMMENTARY_STAGES:
        raise Refused("지금 단계(%s)에서는 주석을 모으지 않습니다. 주석은 Stage 4(1차청중)부터입니다." % stage)
    p = B.parse_ref(args.ref)
    label = B.ref_label(p)
    saved, missing, sources = [], [], []

    # ① 자료 폴더 · ③ md 주석
    for kind, f in scan_materials(cfg, p):
        if kind == "__missing__":
            missing.append("자료 폴더 없음: %s" % f)
            continue
        text = B.nfc(f.read_text(encoding="utf-8", errors="replace"))
        secs = sections_for(text, p)
        if not secs:
            continue
        body = "\n\n".join(secs)
        cut = len(body) > MAX_EXCERPT
        head = ["---", "source_kind: %s" % kind, "source_file: \"%s\"" % f, "reference: %s" % B.ref_text(p),
                "sections: %d" % len(secs), "truncated: %s" % ("true" if cut else "false"),
                "collected_at: %s" % now(), "collected_by: dsc-collector", "---", "",
                "> 출처: %s · %s (제목 단위 발췌, 원문 그대로)" % (kind, f.name), ""]
        stem = re.sub(r"^B_", "", B.nfc(f.stem)) if kind == "md주석" else f.stem
        rel = "주석/%s_%s_%s.md" % ("B" if kind == "md주석" else "자료", safe_name(stem), label)
        saved.append(safe_write(col, rel, "\n".join(head) + body[:MAX_EXCERPT] + "\n"))
        sources.append(f.name)

    # ② Logos 수집본 (읽기 명령 excerpt만)
    try:
        books = bridge(cfg, "excerpt", B.en_ref(p), "--max-chars", str(MAX_EXCERPT))
    except Refused:
        raise
    except Exception as e:  # noqa: BLE001
        books = []
        missing.append("Logos: %s" % str(e)[:160])
    for bk in books or []:
        text = (bk.get("text") or "").strip()
        if not text:
            continue
        head = ["---", "source_kind: Logos", "source_title: \"%s\"" % (bk.get("title") or "").replace('"', "'"),
                "source_author: \"%s\"" % (bk.get("author") or ""), "source_file: \"%s\"" % bk.get("file", ""),
                "reference: %s" % B.ref_text(p), "sections: %s" % bk.get("sections", ""),
                "truncated: %s" % ("true" if bk.get("truncated") else "false"),
                "collected_at: %s" % now(), "collected_by: dsc-collector (logos_bridge excerpt)", "---", "",
                "> 출처: Logos 수집본 · %s · %s · 절 제목: %s" % (
                    bk.get("title", ""), bk.get("author", ""), " / ".join(bk.get("headings") or [])), ""]
        rel = "주석/Logos_%s_%s.md" % (safe_name(Path(bk.get("file") or bk.get("title") or "book").stem), label)
        saved.append(safe_write(col, rel, "\n".join(head) + text + "\n"))
        sources.append(bk.get("title") or bk.get("file"))

    if not saved:
        missing.append("이 본문을 다루는 주석을 찾지 못했습니다")
    return {"status": "ok" if saved and not missing else ("partial" if saved else "failed"),
            "saved": saved, "counts": {"commentary": len(saved)}, "sources": sources, "missing": missing}


def cmd_syntax(args, cfg):
    """감독의 구문 분석 초안을 수집본과 대조해 syntax.json에 넣습니다(references/syntax-analysis.md)."""
    wd, col = collect_dir(args.week_dir)
    if col.is_symlink() or not col.is_dir():
        raise Refused("00_수집 폴더가 없거나 링크입니다")
    draft_p, pas_p = col / DRAFT, col / "passage.json"
    for f in (draft_p, pas_p):
        if f.is_symlink():
            raise Refused("%s가 링크입니다" % f.name)
    if not pas_p.is_file():
        raise Refused("수집본(passage.json)이 없습니다. 먼저 본문을 수집하십시오")
    if not draft_p.is_file():
        raise Refused("초안(00_수집/%s)이 없습니다" % DRAFT)
    try:
        draft = json.loads(draft_p.read_text(encoding="utf-8"))
        passage = json.loads(pas_p.read_text(encoding="utf-8"))
    except ValueError as e:
        raise Refused("JSON을 읽지 못했습니다: %s" % e)
    try:
        errs, warns, verses = SX.check(draft, passage)
    except Exception as e:  # noqa: BLE001  (형식이 크게 어긋난 초안도 문제 목록으로 돌려줍니다)
        errs, warns, verses = ["초안을 검사하지 못했습니다: %s" % type(e).__name__], [], []
    if errs:
        return {"status": "failed", "saved": [], "missing": [], "problems": errs[:40], "warnings": warns[:40],
                "counts": {"verses": 0}}
    cur_p = col / "syntax.json"
    try:
        existing = json.loads(cur_p.read_text(encoding="utf-8")) if cur_p.is_file() and not cur_p.is_symlink() else {}
    except ValueError:
        existing = {}
    merged = SX.merge(existing, verses, passage, now())
    saved = [safe_write(col, "syntax.json", SX.dumps(merged))]
    os.unlink(draft_p)
    return {"status": "ok", "saved": saved, "missing": [], "warnings": warns[:40],
            "counts": {"verses": len(verses), "verses_total": len(merged["verses"]),
                       "clauses": sum(len(v["clauses"]) for v in verses)}}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("task", choices=["passage", "commentary", "syntax"])
    ap.add_argument("--week-dir", required=True)
    ap.add_argument("--ref")
    ap.add_argument("--config")
    a = ap.parse_args(argv)
    cfg = load_config(a.config)
    try:
        if a.task != "syntax" and not a.ref:
            raise Refused("--ref가 필요합니다")
        r = {"passage": cmd_passage, "commentary": cmd_commentary, "syntax": cmd_syntax}[a.task](a, cfg)
    except (Refused, B.RefError) as e:
        r = {"status": "refused", "reason": str(e), "saved": [], "missing": []}
    print(json.dumps(r, ensure_ascii=False, indent=1))
    return 0 if r["status"] in ("ok", "partial") else 1


if __name__ == "__main__":
    sys.exit(main())
