#!/usr/bin/env python3
"""성경 본문 수집 모듈 (표준 라이브러리만).

- 책 이름표, 본문 범위 해석
- 대한성서공회 성경플랫폼(bible.bskorea.or.kr): 개역개정·새번역·새한글·공동번역 개정, BHS·NA28
- ESV: biblegateway.com
- 교차 검증: 대한성서공회 구 읽기 화면(www.bskorea.or.kr) — 개역개정·새번역·공동번역 개정
- 원어 구문(clause) 나누기: 문장부호 기준 기계적 분할

본문은 받은 글자 그대로 둡니다. 요약·교정·추측을 하지 않습니다.
"""
import html as _html
import json
import re
import unicodedata
import urllib.request
from html.parser import HTMLParser

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 "
      "(KHTML, like Gecko) Version/17.0 Safari/605.1.15")
TIMEOUT = 25

# (한국어 이름, 약칭들, USFM, 영어 이름, 구약/신약)
BOOKS = [
    ("창세기", ["창"], "GEN", "Genesis", "OT"), ("출애굽기", ["출"], "EXO", "Exodus", "OT"),
    ("레위기", ["레"], "LEV", "Leviticus", "OT"), ("민수기", ["민"], "NUM", "Numbers", "OT"),
    ("신명기", ["신"], "DEU", "Deuteronomy", "OT"), ("여호수아", ["수"], "JOS", "Joshua", "OT"),
    ("사사기", ["삿"], "JDG", "Judges", "OT"), ("룻기", ["룻"], "RUT", "Ruth", "OT"),
    ("사무엘상", ["삼상"], "1SA", "1 Samuel", "OT"), ("사무엘하", ["삼하"], "2SA", "2 Samuel", "OT"),
    ("열왕기상", ["왕상"], "1KI", "1 Kings", "OT"), ("열왕기하", ["왕하"], "2KI", "2 Kings", "OT"),
    ("역대상", ["대상"], "1CH", "1 Chronicles", "OT"), ("역대하", ["대하"], "2CH", "2 Chronicles", "OT"),
    ("에스라", ["스"], "EZR", "Ezra", "OT"), ("느헤미야", ["느"], "NEH", "Nehemiah", "OT"),
    ("에스더", ["에"], "EST", "Esther", "OT"), ("욥기", ["욥"], "JOB", "Job", "OT"),
    ("시편", ["시"], "PSA", "Psalms", "OT"), ("잠언", ["잠"], "PRO", "Proverbs", "OT"),
    ("전도서", ["전"], "ECC", "Ecclesiastes", "OT"), ("아가", ["아"], "SNG", "Song of Songs", "OT"),
    ("이사야", ["사"], "ISA", "Isaiah", "OT"), ("예레미야", ["렘"], "JER", "Jeremiah", "OT"),
    ("예레미야애가", ["애"], "LAM", "Lamentations", "OT"), ("에스겔", ["겔"], "EZK", "Ezekiel", "OT"),
    ("다니엘", ["단"], "DAN", "Daniel", "OT"), ("호세아", ["호"], "HOS", "Hosea", "OT"),
    ("요엘", ["욜"], "JOL", "Joel", "OT"), ("아모스", ["암"], "AMO", "Amos", "OT"),
    ("오바댜", ["옵"], "OBA", "Obadiah", "OT"), ("요나", ["욘"], "JON", "Jonah", "OT"),
    ("미가", ["미"], "MIC", "Micah", "OT"), ("나훔", ["나"], "NAM", "Nahum", "OT"),
    ("하박국", ["합"], "HAB", "Habakkuk", "OT"), ("스바냐", ["습"], "ZEP", "Zephaniah", "OT"),
    ("학개", ["학"], "HAG", "Haggai", "OT"), ("스가랴", ["슥"], "ZEC", "Zechariah", "OT"),
    ("말라기", ["말"], "MAL", "Malachi", "OT"),
    ("마태복음", ["마"], "MAT", "Matthew", "NT"), ("마가복음", ["막"], "MRK", "Mark", "NT"),
    ("누가복음", ["눅"], "LUK", "Luke", "NT"), ("요한복음", ["요"], "JHN", "John", "NT"),
    ("사도행전", ["행"], "ACT", "Acts", "NT"), ("로마서", ["롬"], "ROM", "Romans", "NT"),
    ("고린도전서", ["고전"], "1CO", "1 Corinthians", "NT"), ("고린도후서", ["고후"], "2CO", "2 Corinthians", "NT"),
    ("갈라디아서", ["갈"], "GAL", "Galatians", "NT"), ("에베소서", ["엡"], "EPH", "Ephesians", "NT"),
    ("빌립보서", ["빌"], "PHP", "Philippians", "NT"), ("골로새서", ["골"], "COL", "Colossians", "NT"),
    ("데살로니가전서", ["살전"], "1TH", "1 Thessalonians", "NT"), ("데살로니가후서", ["살후"], "2TH", "2 Thessalonians", "NT"),
    ("디모데전서", ["딤전"], "1TI", "1 Timothy", "NT"), ("디모데후서", ["딤후"], "2TI", "2 Timothy", "NT"),
    ("디도서", ["딛"], "TIT", "Titus", "NT"), ("빌레몬서", ["몬"], "PHM", "Philemon", "NT"),
    ("히브리서", ["히"], "HEB", "Hebrews", "NT"), ("야고보서", ["약"], "JAS", "James", "NT"),
    ("베드로전서", ["벧전"], "1PE", "1 Peter", "NT"), ("베드로후서", ["벧후"], "2PE", "2 Peter", "NT"),
    ("요한일서", ["요일"], "1JN", "1 John", "NT"), ("요한이서", ["요이"], "2JN", "2 John", "NT"),
    ("요한삼서", ["요삼"], "3JN", "3 John", "NT"), ("유다서", ["유"], "JUD", "Jude", "NT"),
    ("요한계시록", ["계"], "REV", "Revelation", "NT"),
]

# 성경플랫폼 약어 → 표시 이름 (Stage 1 비교 순서: 새한글 → 새번역 → 공동번역 → 개역개정)
KOREAN = [("NKT", "새한글"), ("RNKSV", "새번역"), ("KCT", "공동번역 개정판"), ("NKRV", "개역개정")]
# 교차 검증: 성경플랫폼 약어 → 구 읽기 화면 version 값
CROSS = {"NKRV": "GAE", "RNKSV": "SAENEW", "KCT": "COGNEW"}
PLATFORM = {"bskorea": "https://bible.bskorea.or.kr/bible/{abbr}/{usfm}.{ch}",
            "diebibel": "https://www.die-bibel.de/bibel/{abbr}/{usfm}.{ch}"}
# 약어 → (사이트, 성경 ID). 사이트는 없는 역본을 요청받으면 다른 역본을 조용히 돌려주므로
# 응답의 bibleId를 반드시 대조합니다.
BIBLE_IDS = {
    "NKT": ("bskorea", "6ff8cbad2d1fce9a-01"), "NKRV": ("bskorea", "a5f9087beeef2fdc-01"),
    "RNKSV": ("bskorea", "da35b7e52f5c7865-01"), "KCT": ("bskorea", "c6404414d2b2d9f3-01"),
    "NA28": ("diebibel", "d30958d1302f9bd8-01"), "BHS": ("diebibel", "9f3cb709f9bded60-01"),
    "ESV": ("diebibel", "7f26fc27ef1520e2-01"),
}
SCRIPT_CHECK = {"NA28": re.compile(r"[\u0370-\u03ff\u1f00-\u1fff]"), "BHS": re.compile(r"[\u0590-\u05ff]"),
                "NKT": re.compile(r"[\uac00-\ud7a3]"), "NKRV": re.compile(r"[\uac00-\ud7a3]"),
                "RNKSV": re.compile(r"[\uac00-\ud7a3]"), "KCT": re.compile(r"[\uac00-\ud7a3]"),
                "ESV": re.compile(r"[A-Za-z]")}
OLD_SITE = "https://www.bskorea.or.kr/bible/korbibReadpage.php?version={ver}&book={book}&chap={ch}"
ESV_URL = "https://www.biblegateway.com/passage/?search={q}&version=ESV"


class RefError(ValueError):
    pass


def nfc(s):
    return unicodedata.normalize("NFC", s or "")


def find_book(name):
    n = nfc(name).replace(" ", "")
    for b in BOOKS:
        if n == b[0] or n in b[1] or n.upper() == b[2] or n.lower() == b[3].replace(" ", "").lower():
            return {"ko": b[0], "usfm": b[2], "en": b[3], "testament": b[4]}
    raise RefError("책 이름을 알 수 없습니다: %s" % name)


def parse_ref(ref):
    """'고린도후서 4:1-18' · '고후 4:1-5:10' · '시편 23' → dict.

    end 절이 None이면 그 장 끝까지입니다.
    """
    s = nfc(ref).strip().replace("–", "-").replace("—", "-").replace("~", "-")
    m = re.match(r"^\s*(.+?)\s*(\d+)(?::(\d+))?(?:\s*-\s*(\d+)(?::(\d+))?)?\s*$", s)
    if not m:
        raise RefError("본문 범위를 읽을 수 없습니다: %s" % ref)
    book = find_book(m.group(1))
    c1 = int(m.group(2))
    v1 = int(m.group(3)) if m.group(3) else 1
    if m.group(4) and m.group(5):
        c2, v2 = int(m.group(4)), int(m.group(5))
    elif m.group(4):
        c2, v2 = (c1, int(m.group(4))) if m.group(3) else (int(m.group(4)), None)
    else:
        c2, v2 = c1, (None if not m.group(3) else v1)
    if (c2, v2 or 999) < (c1, v1):
        raise RefError("범위의 끝이 시작보다 앞섭니다: %s" % ref)
    return {"book": book, "start": [c1, v1], "end": [c2, v2]}


def ref_label(p):
    """파일명용 본문 표기: 고린도후서4_1-18 (v0.4 실사용 형식)."""
    (c1, v1), (c2, v2) = p["start"], p["end"]
    b = p["book"]["ko"]
    if c1 == c2 and v1 == v2:
        return "%s%d_%d" % (b, c1, v1)
    if c1 == c2:
        return "%s%d_%d-%s" % (b, c1, v1, v2 if v2 else "끝")
    return "%s%d_%d-%d_%s" % (b, c1, v1, c2, v2 if v2 else "끝")


def ref_text(p):
    (c1, v1), (c2, v2) = p["start"], p["end"]
    b = p["book"]["ko"]
    if c1 == c2 and v1 == v2:
        return "%s %d:%d" % (b, c1, v1)
    if c1 == c2:
        return "%s %d:%d-%s" % (b, c1, v1, v2 if v2 else "끝")
    return "%s %d:%d-%d:%s" % (b, c1, v1, c2, v2 if v2 else "끝")


def en_ref(p):
    (c1, v1), (c2, v2) = p["start"], p["end"]
    e = p["book"]["en"]
    if c1 == c2:
        return "%s %d:%d-%d" % (e, c1, v1, v2) if v2 else "%s %d" % (e, c1)
    return "%s %d:%d-%d:%d" % (e, c1, v1, c2, v2 or 200)


def http_get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html",
                                               "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read().decode("utf-8", errors="replace")


def clean(s):
    return re.sub(r"\s+", " ", nfc(s)).strip()


# ---------- 성경플랫폼 (IBEP) ----------
def parse_platform(page, usfm, ch, bible_id=None):
    """성경플랫폼 페이지의 IBEP-main-state JSON에서 장 하나를 읽습니다.

    돌려줌: {"verses": {절: 본문}, "headings": [(첫 절, 제목)], "copyright": str}
    """
    m = re.search(r'<script id="IBEP-main-state" type="application/json">(.*?)</script>', page, re.S)
    if not m:
        raise ValueError("성경플랫폼 데이터 블록이 없습니다")
    state = json.loads(m.group(1))
    key = next((k for k in state if k.endswith("/chapters/%s.%d/with-study-content" % (usfm, ch))), None)
    if not key:
        raise ValueError("%s %d장 데이터가 없습니다" % (usfm, ch))
    chap = state[key]["data"]["chapter"]
    if bible_id and chap.get("bibleId") != bible_id:
        raise ValueError("요청한 역본이 아닌 다른 역본(%s)이 왔습니다" % chap.get("bibleId"))
    verses, headings, pending = {}, [], []
    vid_re = re.compile(r"^%s\.%d\.(\d+)(?:-(?:%s\.%d\.)?(\d+))?$" % (re.escape(usfm), ch, re.escape(usfm), ch))
    sups, combined = [], {}

    def text_of(node):
        out = []

        def w(n):
            if isinstance(n, list):
                for x in n:
                    w(x)
            elif isinstance(n, dict):
                if n.get("type") in ("study", "note", "verse-number"):
                    return
                c = n.get("content")
                if isinstance(c, str):
                    out.append(c)
                else:
                    w(c)
        w(node)
        return "".join(out)

    def walk(nodes):
        for n in nodes if isinstance(nodes, list) else [nodes]:
            if not isinstance(n, dict):
                continue
            t, style, c = n.get("type"), n.get("style") or "", n.get("content")
            if t == "paragraph" and re.match(r"^(s\d*|ms\d*|mr|sr)$", style):
                title = clean(text_of(c))
                if title:
                    pending.append(title)
                continue
            if t == "paragraph" and style == "d":          # 시편 표제
                sup = clean(text_of(c))
                if sup:
                    sups.append(sup)
                if not any(isinstance(x, dict) and x.get("type") == "verse-text" for x in (c or [])):
                    continue
            if t == "verse-text":
                vm = vid_re.match(n.get("verseId") or "")
                if vm:
                    v = int(vm.group(1))
                    if vm.group(2):                              # 합쳐진 절 (예: 25-26)
                        combined["%d:%d" % (ch, v)] = "%d:%s-%s" % (ch, vm.group(1), vm.group(2))
                    if pending:
                        headings.append((v, " / ".join(pending)))
                        del pending[:]
                    piece = c if isinstance(c, str) else text_of(c)
                    if v in verses and last_para.get(v) != para[0]:
                        piece = " " + piece      # 소제목·단락을 넘어 이어지는 절
                    verses[v] = verses.get(v, "") + piece
                    last_para[v] = para[0]
                continue
            if t in ("study", "note"):
                continue
            if isinstance(c, list):
                if t == "paragraph":
                    para[0] += 1
                walk(c)
    para, last_para = [0], {}
    walk(chap.get("content") or [])
    return {"verses": {v: clean(t) for v, t in sorted(verses.items())},
            "headings": headings, "superscriptions": sups, "combined": combined, "copyright": clean(_html.unescape(re.sub(r"<[^>]+>", " ", chap.get("copyright") or "")))}


def fetch_platform(abbr, usfm, ch):
    site, bid = BIBLE_IDS[abbr]
    url = PLATFORM[site].format(abbr=abbr, usfm=usfm, ch=ch)
    d = parse_platform(http_get(url), usfm, ch, bid)
    chk = SCRIPT_CHECK[abbr]
    bad = [v for v, t in d["verses"].items() if not chk.search(t)]
    if not d["verses"] or bad:
        raise ValueError("%s 본문 글자가 맞지 않습니다 (절 %s)" % (abbr, bad[:5]))
    d["url"] = url
    return d


# ---------- ESV (biblegateway) ----------
class _ESV(HTMLParser):
    SKIP_TAGS = {"h1", "h2", "h3", "h4", "h5", "script", "style"}

    def __init__(self, ch):
        super().__init__(convert_charrefs=True)
        self.ch = ch
        self.stack = []          # (tag, verse|None, skip)
        self.verses = {}

    def _cur(self):
        verse, skip = None, False
        for _, v, s in self.stack:
            if v is not None:
                verse = v
            skip = skip or s
        return verse, skip

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = (a.get("class") or "").split()
        verse = None
        if tag == "span" and "text" in cls:
            for c in cls:
                m = re.match(r"^[\w]+-(\d+)-(\d+)$", c)
                if m and int(m.group(1)) == self.ch:
                    verse = int(m.group(2))
        skip = (tag in self.SKIP_TAGS or (tag == "sup" and ({"crossreference", "footnote", "versenum"} & set(cls)))
                or (tag == "span" and "chapternum" in cls) or (tag == "div" and "footnotes" in cls))
        if tag in ("br", "img", "hr", "meta", "link", "input"):
            return
        self.stack.append((tag, verse, bool(skip)))

    def handle_endtag(self, tag):
        for k in range(len(self.stack) - 1, -1, -1):
            if self.stack[k][0] == tag:
                del self.stack[k:]
                return

    def handle_data(self, data):
        verse, skip = self._cur()
        if verse is not None and not skip:
            self.verses[verse] = self.verses.get(verse, "") + data


def fetch_esv(book_en, ch):
    url = ESV_URL.format(q=urllib.request.quote("%s %d" % (book_en, ch)))
    page = http_get(url)
    i = page.find('class="passage-text"')
    if i < 0:
        raise ValueError("ESV 본문 영역이 없습니다")
    p = _ESV(ch)
    p.feed(page[i:])
    if not p.verses:
        raise ValueError("ESV 절을 찾지 못했습니다")
    return {"verses": {v: clean(t) for v, t in sorted(p.verses.items())}, "headings": [],
            "copyright": "ESV® Bible, © 2001 by Crossway (biblegateway.com 표시본)", "url": url}


# ---------- 교차 검증: 구 읽기 화면 ----------
def parse_old_site(page):
    """구 읽기 화면: 절 번호 span으로 자르고, 소제목·각주는 지웁니다. 소제목을 사이에 둔 절도 하나로 잇습니다."""
    page = re.sub(r"<div id='D_[^']*'.*?</div>", "", page, flags=re.S)       # 각주 팝업
    page = re.sub(r"<a class=comment[^>]*>.*?</a>", "", page, flags=re.S)     # 각주 표지 ㄱ)
    page = re.sub(r'<font class="smallTitle">.*?</font>', " ", page, flags=re.S)  # 소제목
    verses = {}
    chunks = re.split(r'<span class="number">', page)
    for ch in chunks[1:]:
        m = re.match(r"(\d+)(?:&nbsp;|\s)*</span>", ch)
        if not m:
            continue
        body = ch[m.end():]
        body = re.split(r"</td>|<div\b|<table\b|<script\b", body, maxsplit=1)[0]
        body = re.sub(r"<br\s*/?>", " ", body)
        t = clean(_html.unescape(re.sub(r"<[^>]+>", "", body)))
        v = int(m.group(1))
        if t and v not in verses:
            verses[v] = t
    return verses


def fetch_old_site(ver, usfm, ch):
    url = OLD_SITE.format(ver=ver, book=usfm.lower(), ch=ch)
    v = parse_old_site(http_get(url))
    if not v:
        raise ValueError("구 읽기 화면에서 절을 찾지 못했습니다")
    return v, url


def norm_cmp(s):
    return re.sub(r"[\s\W_]+", "", nfc(s))


def cross_check(primary, other):
    """같은 절끼리 글자(공백·문장부호 제외)를 비교합니다."""
    diff = [v for v in primary if v in other and norm_cmp(primary[v]) != norm_cmp(other[v])]
    absent = [v for v in primary if v not in other]
    return {"status": "match" if not diff and not absent else "differ",
            "verses_differ": diff, "verses_absent": absent}


# ---------- 원어 구문 나누기 ----------
GREEK_BREAK = re.compile(r"(?<=[··.;;])\s+")
HEBREW_BREAK = re.compile(r"(?<=[֑׃])\s*(?=\S)")


def split_clauses(text, testament):
    """문장부호(헬라어 · . ;) 또는 아트나흐·소프 파숙(히브리어)으로 기계적으로 나눕니다."""
    if testament == "OT":
        parts = []
        for chunk in re.split(r"(?<=׃)", text):
            # 아트나흐가 붙은 낱말 뒤에서 나눔
            m = re.search(r"\S*֑\S*\s", chunk)
            if m:
                parts += [chunk[:m.end()], chunk[m.end():]]
            else:
                parts.append(chunk)
    else:
        parts = GREEK_BREAK.split(text)
    return [clean(p) for p in parts if clean(p)]


def letters(n):
    s = ""
    n += 1
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(97 + r) + s
    return s
