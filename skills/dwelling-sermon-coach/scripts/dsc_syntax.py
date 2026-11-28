"""원어 구문 분석(00_수집/syntax.json) 검사·설치 — references/syntax-analysis.md

감독이 쓴 초안(00_수집/구문분석_초안.json)을 수집본(passage.json)과 대조합니다.
막는 것(오류): 원어 낱말이 수집본 그 절과 다름(빠짐·더함·바뀜), 새한글·ESV가 수집본에 없는 글,
              범위 밖 절, 구문 ID·라벨 계열·들여쓰기 형식
알리는 것(경고): 문법 분해 표기가 규격과 다름, 해설 문장 수(2~4)
"""
import json
import re
import unicodedata

FAMILIES = {"main", "ptc", "inf", "pur", "rel", "causal", "quest", "cond", "plain", "prep", "par", "etc"}
ID_RX = re.compile(r"^(\d{1,3})\.(\d{1,3})[a-z]{1,3}$")
REF_RX = re.compile(r"^(\d{1,3}):(\d{1,3})$")
# 비교에서 빼는 것: 문장부호·비평 부호·히브리어 강세(칸틸레이션)·마켑·소프 파숙·공백
STRIP_RX = re.compile("[\\s.,;:!?··;—–\\-()\\[\\]⟦⟧⸀⸁⸂⸃⸄⸅\"“”‘«»֑-ֽ֯־׀׃׆]")
ELISION = {"’": "ʼ", "᾽": "ʼ", "'": "ʼ", "᾿": "ʼ"}

NT_PARSE = re.compile(
    r"^(동[직가명희]\.(현|미완|과|현완|과완|미)(능|중|수|중수)\.[123][단복]"
    r"|분\.(현|과|현완|미)(능|중|수|중수)\.[주소여목호][남여중][단복]"
    r"|부정사\.(현|과|현완|미)(능|중|수|중수)"
    r"|(명|형|관|수사|대[가-힣]*)\.[주소여목호]\.([남여중]|[123])[단복]"
    r"|대[가-힣]*\.[주소여목호]\.[123][단복]"
    r"|전(\(\+[소여목]\))?|접|부|불변사|감탄|부정어|관계부)\??$")
OT_PARSE = re.compile(
    r"^((접\(와우\)|전\([^)]{1,4}\)|관|의문)\+)*"
    r"(동(칼|니|피|푸|히|호|히트|기타)\.(완|미완|와미완|와완|명|지시|청유)(\.[123]?[남여공]?[단복쌍])?"
    r"|분(칼|니|피|푸|히|호|히트)\.(능|수)\.[남여][단복쌍]"
    r"|부정사(칼|니|피|푸|히|호|히트)\.(연계|절대)"
    r"|(명|형|고유|수사|대[가-힣]*)(\.[남여공][단복쌍])?(\.(절대|연계))?"
    r"|전(\([^)]{1,4}\))?|접(\([^)]{1,4}\))?|부|불변사|부정어|관|목적표지)"
    r"(\+접미[123][남여공][단복])?\??$")


class SyntaxError_(Exception):
    pass


def norm(s):
    s = unicodedata.normalize("NFC", s or "")
    for a, b in ELISION.items():
        s = s.replace(a, b)
    return STRIP_RX.sub("", s)


def spaced(s):
    """공백 묶음을 한 칸으로 (띄어쓰기는 지킵니다)."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", s or "")).strip()


MAQAF = "־"
GAP_RX = re.compile(r"^⟨[^⟩]{0,40}⟩$")


def pieces(verse_text):
    """수집본 절을 낱말 조각으로: 공백으로 나누고, 히브리어는 마켑 뒤에서도 나눕니다. [(조각, 공백 낱말 번호)]."""
    out = []
    for wi, tok in enumerate(unicodedata.normalize("NFC", verse_text or "").split()):
        for part in re.split("(?<=%s)" % MAQAF, tok):
            if part and norm(part):                    # 파섹(׀)처럼 글자 없는 부호만의 토큰은 낱말로 세지 않습니다
                out.append((part, wi))
    return out


def found(frag, text):
    """frag가 text 안에 낱말 경계에서 시작·끝나는가 (띄어쓰기 그대로)."""
    return bool(re.search(r"(?:^|(?<=\s))" + re.escape(frag) + r"(?=\s|$)", text))


def match_words(words, src):
    """초안 낱말을 수집본 조각에 하나씩 맞춥니다. 맞으면 수집본 글자로 바꿔 넣습니다. 오류 문구 목록."""
    errs, k = [], 0
    for n, w in enumerate(words):
        g = w["g"]
        if not g.strip() or re.search(r"\s", g):
            errs.append("낱말 %d이 비었거나 공백을 품고 있습니다" % (n + 1))
            return errs
        target = norm(g)
        if not target:
            errs.append("낱말 %d에 글자가 없습니다(문장부호뿐)" % (n + 1))
            return errs
        acc, raw, start = "", "", k
        while k < len(src) and len(acc) < len(target) and src[k][1] == src[start][1]:
            raw += src[k][0]
            acc += norm(src[k][0])
            k += 1
        if acc != target:
            errs.append("낱말 %d이 수집본 %d번째 낱말과 다릅니다(빠짐·더함·바뀜·쪼갬)" % (n + 1, (src[start][1] + 1) if start < len(src) else 0))
            return errs
        w["g"] = raw                                   # 화면·파일에는 늘 수집본 글자가 갑니다
    if k != len(src):
        errs.append("수집본 낱말 %d개가 구문에 빠졌습니다" % (len(src) - k))
    return errs


# 낱말 앞뒤의 문장부호(생략 부호 ’ ᾽ 는 낱말의 일부라 남김). M6: 「ἐγκακοῦμεν,」처럼 쉼표가 주동사에 붙어 나옴
EDGE_PUNCT = ".,;:!?\u00b7\u0387\u037e;—–-()[]⟦⟧⸀⸁⸂⸃⸄⸅\"“”‘«»׃׀"


def source_token(word, src):
    """주동사·동사 계단 낱말이 그 절 수집본 낱말이면 수집본 글자(앞뒤 문장부호 뺌)를, 아니면 None."""
    t = norm(word)
    for part, _ in src:
        if t and norm(part) == t:
            return part.strip(EDGE_PUNCT) or part
    return None


def check(draft, passage):
    """(오류 목록, 경고 목록, 정리된 절 목록). 오류·경고 문구에 성경 글자를 넣지 않습니다."""
    errs, warns = [], []
    if not isinstance(draft, dict) or not isinstance(draft.get("verses"), list) or not draft["verses"]:
        return ["초안에 verses 목록이 없습니다"], [], []
    orig = next(iter((passage.get("original") or {}).values()), None)
    if not orig:
        return ["수집본에 원어 본문이 없어 대조할 수 없습니다"], [], []
    testament = (passage.get("book") or {}).get("testament", "NT")
    parse_rx = OT_PARSE if testament == "OT" else NT_PARSE
    ovs = {v["ref"]: v["text"] for v in orig.get("verses", []) if isinstance(v, dict)}
    order = list(ovs)
    tr = passage.get("translations") or {}
    nk_all = spaced(" ".join(v.get("text", "") for v in (tr.get("NKT") or {}).get("verses", []) if isinstance(v, dict)))
    esv_by = {v.get("ref"): v.get("text", "") for v in (tr.get("ESV") or {}).get("verses", []) if isinstance(v, dict)}
    out, seen = [], set()
    for vi, v in enumerate(draft["verses"]):
        where = "verses[%d]" % vi
        if not isinstance(v, dict):
            errs.append("%s: 객체가 아닙니다" % where)
            continue
        ref = v.get("ref")
        if not isinstance(ref, str) or not REF_RX.match(ref):
            errs.append("%s: ref는 '장:절' 형식이어야 합니다" % where)
            continue
        where = ref
        if ref in seen:
            errs.append("%s: 같은 절이 두 번 있습니다" % where)
        seen.add(ref)
        if ref not in ovs:
            errs.append("%s: 수집본 범위 밖의 절입니다" % where)
            continue
        c, n = REF_RX.match(ref).groups()
        idx = order.index(ref)
        esv_near = spaced(" ".join(esv_by.get(r, "") for r in order[max(0, idx - 1):idx + 2]))   # ESV는 그 절 ±1절
        src = pieces(ovs[ref])
        clauses = v.get("clauses")
        if not isinstance(clauses, list) or not clauses:
            errs.append("%s: clauses가 없습니다" % where)
            continue
        words_all, ids, before = [], set(), len(errs)
        for ci, cl in enumerate(clauses):
            cw = "%s 구문 %d" % (ref, ci + 1)
            if not isinstance(cl, dict):
                errs.append("%s: 객체가 아닙니다" % cw)
                continue
            cid = cl.get("id")
            m = ID_RX.match(cid) if isinstance(cid, str) else None
            if not m or m.groups() != (c, n):
                errs.append("%s: id는 '%s.%s' + 알파벳이어야 합니다" % (cw, c, n))
            elif cid in ids:
                errs.append("%s: id가 겹칩니다" % cw)
            else:
                ids.add(cid)
            if cl.get("family") not in FAMILIES:
                errs.append("%s: family는 %s 가운데 하나여야 합니다" % (cw, "·".join(sorted(FAMILIES))))
            if not isinstance(cl.get("label"), str) or not cl["label"].strip() or len(cl["label"]) > 60:
                errs.append("%s: label이 없거나 너무 깁니다" % cw)
            if not isinstance(cl.get("indent"), int) or isinstance(cl.get("indent"), bool) or not 0 <= cl["indent"] <= 3:
                errs.append("%s: indent는 0~3 정수여야 합니다" % cw)
            ws = cl.get("words")
            if not isinstance(ws, list) or not ws:
                errs.append("%s: words가 없습니다" % cw)
                continue
            for wn, w in enumerate(ws):
                if not isinstance(w, dict) or not isinstance(w.get("g"), str):
                    errs.append("%s: 낱말 %d에 g(원어)가 없습니다" % (cw, wn + 1))
                    continue
                if w.get("gap"):                         # 생략된 동사 자리 표시: ⟨ … ⟩ 꼴만, 화면에서 【AI】
                    if not GAP_RX.match(w["g"]):
                        errs.append("%s: 낱말 %d — gap은 ⟨ … ⟩ 꼴(40자 이하)만 됩니다" % (cw, wn + 1))
                    continue
                words_all.append(w)
                pc = w.get("p", "")
                if not isinstance(pc, str):
                    errs.append("%s: 낱말 %d의 분해(p)가 문자열이 아닙니다" % (cw, wn + 1))
                elif pc and not parse_rx.match(pc):
                    warns.append("%s: 낱말 %d의 분해 「%s」가 규격 표기와 다릅니다" % (cw, wn + 1, pc))
            for key, label in (("literal", "직역"), ("nk", "새한글"), ("esv", "ESV")):
                val = cl.get(key, "")
                if not isinstance(val, str):
                    errs.append("%s: %s 값이 문자열이 아닙니다" % (cw, label))
                    continue
                if key == "literal" or not val.strip():
                    continue
                frag = spaced(val)
                if not found(frag, nk_all if key == "nk" else esv_near):
                    errs.append("%s: %s 조각이 수집본에 없습니다(띄어쓰기까지 그대로 잘라 붙입니다%s)"
                                % (cw, label, "" if key == "nk" else ", 그 절 앞뒤 한 절 안"))
                elif len(frag) < 2:
                    warns.append("%s: %s 조각이 한 글자입니다" % (cw, label))
        if len(errs) == before:
            for e in match_words(words_all, src):
                errs.append("%s: %s" % (ref, e))
        mv = v.get("main_verbs", [])
        if not isinstance(mv, list) or any(not isinstance(x, str) for x in mv):
            errs.append("%s: main_verbs는 낱말 목록이어야 합니다" % ref)
            mv = []
        fixed_mv = []
        for x in mv:
            t = source_token(x, src)
            if t is None:
                errs.append("%s: main_verbs의 낱말이 이 절 수집본에 없습니다" % ref)
            else:
                fixed_mv.append(t)
        chain = v.get("chain", [])
        if not isinstance(chain, list) or any(not isinstance(x, dict) or not isinstance(x.get("verb"), str) for x in chain):
            errs.append("%s: chain은 {verb, note} 목록이어야 합니다" % ref)
            chain = []
        fixed_chain = []
        for x in chain:
            parts = [y for y in re.split(r"\s*·\s*|\s+", x["verb"].strip()) if y]
            toks = [source_token(y, src) for y in parts]
            if not parts or None in toks:
                errs.append("%s: 동사 계단의 낱말이 이 절 수집본에 없습니다" % ref)
                continue
            note = x.get("note", "")
            fixed_chain.append({"verb": " · ".join(toks), "note": note if isinstance(note, str) else ""})
        com = v.get("commentary", [])
        if not isinstance(com, list) or any(not isinstance(x, str) for x in com):
            errs.append("%s: commentary는 문장 목록이어야 합니다" % ref)
        elif not 2 <= len(com) <= 4:
            warns.append("%s: 해설은 2~4문장입니다 (지금 %d)" % (ref, len(com)))
        for key in ("title", "variant"):
            if not isinstance(v.get(key, ""), str):
                errs.append("%s: %s 값이 문자열이 아닙니다" % (ref, key))
        keep = {k: v.get(k) for k in ("ref", "title", "clauses", "commentary", "variant") if k in v}
        keep.update(main_verbs=fixed_mv, chain=fixed_chain)
        out.append(keep)
    return errs, warns, out


def validated(syntax, passage):
    """저장된 syntax.json을 지금 수집본과 다시 대조합니다. ({절: 정리된 절}, [맞지 않는 절])."""
    good, bad = {}, []
    for v in (syntax or {}).get("verses", []) if isinstance((syntax or {}).get("verses"), list) else []:
        ref = v.get("ref") if isinstance(v, dict) else None
        try:
            errs, _, out = check({"verses": [v]}, passage)
        except Exception:  # noqa: BLE001
            errs, out = ["검사 중 오류"], []
        if errs or not out:
            bad.append(ref if isinstance(ref, str) else "?")
        else:
            good[ref] = out[0]
    return good, bad


def merge(existing, verses, passage, made_at):
    """기존 syntax.json에 절 단위로 덮어 넣고 수집본 절 순서로 정렬합니다."""
    orig = next(iter((passage.get("original") or {}).values()))
    order = [v["ref"] for v in orig.get("verses", [])]
    cur = {v["ref"]: v for v in (existing or {}).get("verses", []) if isinstance(v, dict) and v.get("ref") in order}
    for v in verses:
        cur[v["ref"]] = v
    return {"dsc_version": "1.0.0", "reference": passage.get("reference"),
            "testament": (passage.get("book") or {}).get("testament"), "original": orig.get("name"),
            "made_by": "감독(claude)", "made_at": made_at,
            "verses": [cur[r] for r in order if r in cur]}


def dumps(obj):
    return json.dumps(obj, ensure_ascii=False, indent=1)
