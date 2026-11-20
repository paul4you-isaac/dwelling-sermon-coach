#!/usr/bin/env python3
"""관찰 작업창 서버 — 머무르는 설교 코치 v1.0.0 (Python 표준 라이브러리만 씁니다)

  python3 app/server.py [--config C] [--vault DIR] [--port N] [--render-delay 초]

지키는 것
- 127.0.0.1에만 붙습니다. Host가 127.0.0.1:포트·localhost:포트가 아니면 거부합니다.
- 실행할 때마다 무작위 토큰을 만들어 index.html에 넣고, 모든 /api 요청에 X-DSC-Token을 요구합니다.
- 다른 Origin·교차 사이트 요청을 거부합니다. CORS 헤더를 두지 않습니다. 쓰기 요청은 JSON만 받습니다.
- 주간 ID는 ^S_\\d{8}$만 받습니다. realpath+commonpath로 vault_root 밖(심볼릭 링크 포함)을 막습니다.
- 서버가 쓰는 파일은 03_원어관찰.json · 03_원어관찰_…md(생성본) · progress.json · 00_진행상황.md뿐입니다.
  모두 dsc_archive의 주간 잠금과 원자적 쓰기를 씁니다.
- 주석 API는 progress.json의 current_stage로 게이트를 직접 계산합니다(4·5·6·7B·8·9만 열림).
- 구판 주간(dsc_version 1.0.0이 아님)은 읽기 전용입니다. 07A·06A 자기적용 파일은 이름도 내보내지 않습니다.
- 원어관찰 기록은 단계와 상관없이 고칠 수 있습니다(설교자가 한 주 동안 다시 돌아와 고침).

한계: 토큰은 이 컴퓨터에서 127.0.0.1에 접속할 수 있는 프로그램이면 index.html에서 얻을 수 있습니다.
설교자 한 사람이 쓰는 맥을 전제로 합니다.
"""
import argparse
import datetime as dt
import hmac
import json
import os
import re
import secrets
import sys
import threading
import unicodedata
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

APP = Path(__file__).resolve().parent
ROOT = APP.parent
SCRIPTS = ROOT / "skills/dwelling-sermon-coach/scripts"
ASSETS = ROOT / "skills/dwelling-sermon-coach/assets"
sys.path.insert(0, str(SCRIPTS))
import dsc_archive as A  # noqa: E402
import dsc_syntax as SX  # noqa: E402
sys.path.insert(0, str(APP))
from jobs import JobError, Jobs  # noqa: E402
from dsc_collect import COMMENTARY_STAGES, SELF_RX  # noqa: E402

WEEK_RX = re.compile(r"^S_\d{8}$")
CLAUSE_RX = re.compile(r"^\d{1,3}\.\d{1,3}[a-z]{1,3}$")
REF_RX = re.compile(r"^\d{1,3}:\d{1,3}$")
MAX_BODY = 512 * 1024
MAX_FIELD = 20000
NOTES = "03_원어관찰.json"
STATIC = {"/app.js": (APP / "static/app.js", "text/javascript; charset=utf-8"),
          "/app.css": (APP / "static/app.css", "text/css; charset=utf-8"),
          "/dsc.css": (ASSETS / "dsc.css", "text/css; charset=utf-8")}
CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; "
       "base-uri 'none'; form-action 'none'; frame-ancestors 'none'")


class HTTPError(Exception):
    def __init__(self, code, msg, extra=None):
        super().__init__(msg)
        self.code, self.msg, self.extra = code, msg, extra or {}


def nfc(s):
    return unicodedata.normalize("NFC", s)


def stamp():
    return dt.datetime.now().astimezone().isoformat(timespec="microseconds")


def inside(child, parent):
    """child의 실제 경로가 parent의 실제 경로 안에 있는가 (심볼릭 링크를 따라간 뒤 비교)."""
    c, p = os.path.realpath(child), os.path.realpath(parent)
    try:
        return os.path.commonpath([c, p]) == p
    except ValueError:
        return False


class Workspace:
    """주간 폴더 읽기·쓰기. HTTP와 떼어 두어 시험하기 쉽게 합니다."""
    A = A
    CLAUSE_RX = CLAUSE_RX
    REF_RX = REF_RX
    inside = staticmethod(inside)

    def __init__(self, vault, cfg, render_delay=30.0):
        self.vault = Path(os.path.realpath(vault))
        self.cfg = cfg
        self.render_delay = render_delay
        self.timers = {}
        self.render_state = {}
        self.tlock = threading.Lock()
        self.recollecting = set()

    # ------------------------------------------------------------ 경로
    def week_dir(self, wid):
        if not isinstance(wid, str) or not WEEK_RX.match(wid):
            raise HTTPError(400, "주간 ID는 S_YYYYMMDD 형식이어야 합니다")
        p = self.vault / wid
        if not p.is_dir() or not inside(p, self.vault) or os.path.realpath(p) == str(self.vault):
            raise HTTPError(404, "주간 폴더가 없습니다")
        return Path(os.path.realpath(p))

    def file_in(self, wd, *parts):
        p = wd.joinpath(*parts)
        if p.exists() and not inside(p, wd):
            raise HTTPError(403, "주간 폴더 밖을 가리키는 경로입니다")
        return p

    def progress(self, wd):
        pj = wd / "progress.json"
        if pj.is_symlink() or (pj.exists() and not inside(pj, wd)):
            return None                                     # 밖을 가리키는 진행 기록은 믿지 않습니다(읽기 전용)
        try:
            st = A.read_progress(wd)
        except (OSError, ValueError):
            st = None
        if not isinstance(st, dict):
            return None
        if st is None or st.get("dsc_version") != A.DSC_VERSION:
            return None
        return st

    def v1(self, wd):
        st = self.progress(wd)
        if st is None:
            raise HTTPError(403, "구판(v0.4) 주간 폴더입니다. 작업창에서는 읽기만 합니다")
        if A.norm_stage(st.get("current_stage")) is None:
            raise HTTPError(409, "progress.json의 current_stage 값이 단계 대응표에 없습니다")
        return st

    # ------------------------------------------------------------ 목록·진행
    def weeks(self):
        out = []
        for d in sorted(self.vault.iterdir(), key=lambda x: x.name, reverse=True):
            if not WEEK_RX.match(d.name) or not d.is_dir() or not inside(d, self.vault):
                continue
            st = self.progress(Path(os.path.realpath(d)))
            out.append({"id": d.name, "legacy": st is None, "text": (st or {}).get("text", ""),
                        "sermon_date": (st or {}).get("sermon_date", ""),
                        "current_stage": A.norm_stage((st or {}).get("current_stage"))})
        return {"weeks": out}

    def progress_view(self, wid):
        wd = self.week_dir(wid)
        st = self.progress(wd)
        if st is None:
            files = sorted(nfc(f.name) for f in wd.iterdir()
                           if f.is_file() and not f.name.startswith(".") and not SELF_RX.match(nfc(f.name)))
            return {"id": wid, "legacy": True, "files": files}
        cur = A.norm_stage(st.get("current_stage"))
        if cur is None:
            raise HTTPError(409, "progress.json의 current_stage 값이 단계 대응표에 없습니다")
        i = A.ORDER.index(cur)
        nxt = A.ORDER[i + 1] if i + 1 < len(A.ORDER) else None
        return {"id": wid, "legacy": False, "text": st.get("text", ""), "sermon_date": st.get("sermon_date", ""),
                "current_stage": cur, "name": A.NAMES[cur],
                "next_stage": nxt and {"key": nxt, "name": A.NAMES[nxt]},
                "stages": [{"key": k, "name": A.NAMES[k],
                            "state": "now" if k == cur else ("done" if A.ORDER.index(k) < i else "later")}
                           for k in A.ORDER],
                "stage_entered": st.get("stage_entered", {}),
                "commentary_open": cur in COMMENTARY_STAGES,
                "render": self.render_state.get(wid)}

    # ------------------------------------------------------------ 본문
    def passage(self, wid):
        wd = self.week_dir(wid)
        p = self.file_in(wd, "00_수집", "passage.json")
        if not p.is_file():
            raise HTTPError(404, "본문 수집본(00_수집/passage.json)이 아직 없습니다")
        d = json.loads(p.read_text(encoding="utf-8"))
        keep = ("reference", "book", "range", "translations", "original", "clauses", "adjacent_pericopes",
                "missing", "notes", "version", "clauses_frozen", "collected_at")
        return {k: d.get(k) for k in keep}

    def clause_list(self, wd):
        p = self.file_in(wd, "00_수집", "passage.json")
        if not p.is_file():
            raise HTTPError(404, "본문 수집본이 없어 구문 목록을 만들 수 없습니다")
        return json.loads(p.read_text(encoding="utf-8")).get("clauses") or []

    def verse_refs(self, wd):
        """묵상 노트를 붙이는 절 목록(수집본 원어 절 순서, 없으면 개역개정)."""
        p = self.file_in(wd, "00_수집", "passage.json")
        if not p.is_file():
            raise HTTPError(404, "본문 수집본이 없어 절 목록을 만들 수 없습니다")
        d = json.loads(p.read_text(encoding="utf-8"))
        src = next(iter((d.get("original") or {}).values()), None) or (d.get("translations") or {}).get("NKRV") or {}
        return [v.get("ref") for v in src.get("verses", []) if isinstance(v, dict) and isinstance(v.get("ref"), str)]

    def syntax(self, wid):
        wd = self.week_dir(wid)
        p = self.file_in(wd, "00_수집", "syntax.json")
        if not p.is_file():
            return {"verses": []}
        d = json.loads(p.read_text(encoding="utf-8"))
        pas = self.file_in(wd, "00_수집", "passage.json")
        passage = json.loads(pas.read_text(encoding="utf-8")) if pas.is_file() else {}
        good, bad = SX.validated(d if isinstance(d, dict) else {}, passage)   # 지금 수집본과 다시 대조합니다
        return {"verses": list(good.values()), "rejected": bad,
                "made_at": d.get("made_at") if isinstance(d, dict) else None}

    # ------------------------------------------------------------ 원어관찰 묵상 노트 (절마다 하나)
    def read_notes(self, wd):
        p = self.file_in(wd, NOTES)
        if not p.is_file():
            return {}
        d = json.loads(p.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}

    @staticmethod
    def split_notes(data):
        return A.split_notes(data)

    def notes(self, wid):
        wd = self.week_dir(wid)
        recs, olds = self.split_notes(self.read_notes(wd))
        refs = set(self.verse_refs(wd)) if (wd / "00_수집/passage.json").is_file() else set()
        restored = set()
        for n in range(len(olds) - 1, -1, -1):              # 절이 다시 생겼으면 그 자리로(같은 절이 여럿이면 마지막 것)
            o = olds[n]
            if refs and o.get("ref") in refs and o["ref"] not in recs:
                recs[o["ref"]] = o
                restored.add(n)
        orphans = [o for n, o in enumerate(olds) if n not in restored] \
            + [dict(v) for k, v in recs.items() if refs and k not in refs]
        return {"verses": {k: {"note": v.get("note", ""), "updated": v.get("updated", "")}
                           for k, v in recs.items() if not refs or k in refs},
                "orphans": [{"ref": o.get("ref", ""), "note": o.get("note", "")} for o in orphans],
                "readonly": self.progress(wd) is None}

    def put_note(self, wid, ref, body):
        wd = self.week_dir(wid)
        self.v1(wd)
        if wid in self.recollecting:
            raise HTTPError(423, "본문을 다시 받는 중입니다. 끝나면 자동으로 다시 저장합니다")
        if not REF_RX.match(ref):
            raise HTTPError(400, "절 표시는 '장:절' 형식이어야 합니다")
        if "note" not in body:
            raise HTTPError(400, "묵상 노트(note)를 보내야 합니다")
        note, base = body["note"], body.get("base", "")
        if not isinstance(note, str) or not isinstance(base, str):
            raise HTTPError(400, "note·base 값은 문자열이어야 합니다")
        if len(note) > MAX_FIELD:
            raise HTTPError(413, "노트가 너무 깁니다(%d자 이하)" % MAX_FIELD)
        order = self.verse_refs(wd)
        if ref not in order:
            raise HTTPError(404, "이 본문에 없는 절입니다: %s" % ref)
        with A.progress_lock(wd):                         # 주간 잠금 안에서 다시 읽습니다
            data = self.read_notes(wd)
            recs, olds = self.split_notes(data)
            back = [o for o in olds if o.get("ref") == ref]
            if ref not in recs and back:                    # 짝 없던 기록의 절이 다시 생김 → 이어 씁니다
                recs[ref] = back[-1]
                olds = [o for o in olds if o is not back[-1]]
            cur = recs.get(ref, {})
            if cur.get("updated", "") != base:
                raise HTTPError(409, "다른 창에서 먼저 고쳤습니다",
                                {"current": {"note": cur.get("note", ""), "updated": cur.get("updated", "")}})
            new = stamp()
            if new <= cur.get("updated", ""):
                new = cur["updated"] + "+1"
            recs[ref] = {"ref": ref, "note": note, "updated": new}
            out = [recs.pop(r) for r in order if r in recs]
            orphans = olds + list(recs.values())            # 절 목록에 없는 기록은 버리지 않습니다
            doc = {"dsc_version": A.DSC_VERSION, "text": data.get("text") or self.v1(wd).get("text", ""),
                   "unit": "verse", "verses": out}
            if orphans:
                doc["_orphans"] = orphans
            A.atomic_write(wd / NOTES, json.dumps(doc, ensure_ascii=False, indent=1) + "\n")
        self.schedule_render(wid, wd)
        return {"updated": new}

    # ------------------------------------------------------------ 생성본 md
    def schedule_render(self, wid, wd):
        with self.tlock:
            t = self.timers.pop(wid, None)
            if t:
                t.cancel()
            if self.render_delay is None:
                return
            t = threading.Timer(self.render_delay, self.render_now, (wid, wd))
            t.daemon = True
            self.timers[wid] = t
            t.start()

    def render_now(self, wid, wd):
        with self.tlock:
            t = self.timers.pop(wid, None)
            if t:
                t.cancel()
        try:
            r = A.render_stage3(wd, self.cfg)
        except A.Refused as e:
            r = {"status": "refused", "issues": [{"problem": str(e)}]}
        except Exception as e:  # noqa: BLE001  (타이머 스레드가 조용히 죽지 않게)
            r = {"status": "error", "issues": [{"problem": "생성본을 만들지 못했습니다: %s" % type(e).__name__}]}
        state = {"at": A.now(), "status": r.get("status"),
                 "issues": [i.get("problem", "") + (" — " + i["suggestion"] if i.get("suggestion") else "")
                            for i in r.get("issues", [])]}
        self.render_state[wid] = state
        return state

    def flush_renders(self):
        """끄기 전에, 기다리던 생성본을 지금 만듭니다."""
        with self.tlock:
            pending = list(self.timers.items())
        for wid, t in pending:
            t.cancel()
            try:
                self.render_now(wid, self.week_dir(wid))
            except HTTPError:
                pass

    # ------------------------------------------------------------ 주석 (게이트)
    def commentary(self, wid):
        wd = self.week_dir(wid)
        st = self.v1(wd)
        cur = A.norm_stage(st.get("current_stage"))
        if cur not in COMMENTARY_STAGES:
            raise HTTPError(403, "주석은 Stage 4 1차청중부터 열립니다. Stage 7A 자기적용에서는 다시 닫힙니다 (지금 %s %s)"
                            % (cur, A.NAMES[cur]))
        d = self.file_in(wd, "00_수집", "주석")
        items = []
        if d.is_dir():
            for f in sorted(d.iterdir(), key=lambda x: nfc(x.name)):
                if f.suffix == ".md" and f.is_file() and inside(f, wd) and not SELF_RX.match(nfc(f.name)):
                    items.append({"name": nfc(f.name), "text": f.read_text(encoding="utf-8", errors="replace")})
        return {"stage": cur, "items": items}

    # ------------------------------------------------------------ 단계 (설교자 버튼)
    def enter_stage(self, wid, body):
        wd = self.week_dir(wid)
        st = self.v1(wd)
        if body.get("confirm") is not True:
            raise HTTPError(400, "설교자가 확인했을 때만 단계를 올립니다 (confirm: true)")
        cur = A.norm_stage(st.get("current_stage"))
        i = A.ORDER.index(cur)
        to = A.norm_stage(body.get("to"))
        if to is None or i + 1 >= len(A.ORDER) or to != A.ORDER[i + 1]:
            raise HTTPError(409, "작업창 버튼은 바로 다음 단계로만 갑니다 (지금 %s)" % cur)
        render = None
        if cur == "3" and (wd / NOTES).is_file():
            render = self.render_now(wid, wd)               # 원어관찰을 마칠 때 생성본을 만듭니다
        try:
            r = A.advance(wd, to, by="workspace")
        except A.Refused as e:
            raise HTTPError(409, str(e))
        return {"current_stage": r["current_stage"], "render": render}


class Handler(BaseHTTPRequestHandler):
    server_version = "dsc-workspace"
    timeout = 30                                            # 본문을 보내지 않고 버티는 연결을 끊습니다
    sys_version = ""

    def log_message(self, fmt, *args):
        if self.server.verbose:
            sys.stderr.write("%s %s\n" % (self.command, fmt % args))

    # ------------------------------------------------------------ 응답
    def send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        if ctype.startswith("text/html"):
            self.send_header("Content-Security-Policy", CSP)
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def fail(self, code, msg, extra=None):
        self.send(code, dict({"error": msg}, **(extra or {})))

    # ------------------------------------------------------------ 검사
    def check_origin(self, api):
        port = self.server.server_address[1]
        hosts = {"127.0.0.1:%d" % port, "localhost:%d" % port}
        if (self.headers.get("Host") or "").lower() not in hosts:
            raise HTTPError(421, "허용하지 않는 Host입니다")
        origin = self.headers.get("Origin")
        if origin is not None and origin.lower() not in {"http://" + h for h in hosts}:
            raise HTTPError(403, "허용하지 않는 Origin입니다")
        site = self.headers.get("Sec-Fetch-Site")
        if site is not None and site not in ("same-origin", "none"):
            raise HTTPError(403, "다른 사이트에서 온 요청입니다")
        if api:
            tok = self.headers.get("X-DSC-Token") or ""
            if not hmac.compare_digest(tok.encode(), self.server.token.encode()):
                raise HTTPError(401, "토큰이 맞지 않습니다. 작업창을 새로 고치십시오")
            if self.command in ("PUT", "POST") and origin is None:
                raise HTTPError(403, "Origin이 없는 쓰기 요청입니다")

    def body_json(self):
        ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if ctype != "application/json":
            raise HTTPError(415, "JSON 요청만 받습니다")
        try:
            n = int(self.headers.get("Content-Length") or "0")
        except ValueError:
            raise HTTPError(400, "Content-Length가 잘못되었습니다")
        if n < 0:
            raise HTTPError(400, "Content-Length가 잘못되었습니다")
        if n > MAX_BODY:
            raise HTTPError(413, "요청이 너무 큽니다")
        try:
            obj = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
        except (ValueError, UnicodeDecodeError):
            raise HTTPError(400, "JSON을 읽지 못했습니다")
        if not isinstance(obj, dict):
            raise HTTPError(400, "JSON 객체여야 합니다")
        return obj

    def route(self):
        raw = urlsplit(self.path).path
        path = unquote(raw)
        if "\x00" in path or "\\" in path or any(seg in ("..", ".") for seg in path.split("/")):
            raise HTTPError(400, "허용하지 않는 경로입니다")
        return path

    # ------------------------------------------------------------ 처리
    def handle_any(self):
        try:
            path = self.route()
            api = path.startswith("/api/")
            self.check_origin(api)
            if api:
                return self.send(200, self.api(path))
            if self.command not in ("GET", "HEAD"):
                raise HTTPError(405, "허용하지 않는 메서드입니다")
            if path == "/healthz":
                return self.send(200, {"ok": True, "app": "dwelling-sermon-coach", "version": A.DSC_VERSION})
            if path in ("/", "/index.html"):
                html = (APP / "static/index.html").read_text(encoding="utf-8").replace("{{TOKEN}}", self.server.token)
                return self.send(200, html.encode("utf-8"), "text/html; charset=utf-8")
            if path in STATIC:
                f, ctype = STATIC[path]
                return self.send(200, f.read_bytes(), ctype)
            raise HTTPError(404, "없는 주소입니다")
        except HTTPError as e:
            self.fail(e.code, e.msg, e.extra)
        except Exception as e:  # noqa: BLE001  (연결을 끊지 않고 JSON으로 알립니다)
            if self.server.verbose:
                import traceback
                traceback.print_exc()
            try:
                self.fail(500, "서버 오류: %s" % type(e).__name__)
            except OSError:
                pass

    def api(self, path):
        ws = self.server.ws
        parts = path.strip("/").split("/")[1:]              # api 다음
        m = self.command
        if parts == ["weeks"] and m == "GET":
            return ws.weeks()
        if len(parts) >= 2 and parts[0] == "weeks":
            wid, rest = parts[1], parts[2:]
            if rest == ["progress"] and m == "GET":
                return ws.progress_view(wid)
            if rest == ["passage"] and m == "GET":
                return ws.passage(wid)
            if rest == ["syntax"] and m == "GET":
                return ws.syntax(wid)
            if rest == ["notes"] and m == "GET":
                return ws.notes(wid)
            if len(rest) == 2 and rest[0] == "notes" and m == "PUT":
                return ws.put_note(wid, rest[1], self.body_json())
            if rest == ["commentary"] and m == "GET":
                return ws.commentary(wid)
            if rest == ["stage", "enter"] and m == "POST":
                return ws.enter_stage(wid, self.body_json())
            jobs = self.server.jobs
            try:
                if rest == ["ask"] and m == "POST":
                    return jobs.ask(wid, self.body_json())
                if rest == ["ask"] and m == "GET":
                    return jobs.history(wid)
                if rest == ["recollect"] and m == "POST":
                    return jobs.recollect(wid, self.body_json())
                if rest == ["check"] and m == "POST":
                    return jobs.check(wid)
            except JobError as e:
                raise HTTPError(e.code, e.msg)
        raise HTTPError(404, "없는 API입니다")

    do_GET = do_HEAD = do_PUT = do_POST = handle_any

    def do_DELETE(self):
        self.fail(405, "허용하지 않는 메서드입니다")

    do_PATCH = do_OPTIONS = do_DELETE


def make_server(vault, cfg, port=0, render_delay=30.0, verbose=False):
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    httpd.daemon_threads = True
    httpd.token = secrets.token_urlsafe(32)
    httpd.ws = Workspace(vault, cfg, render_delay)
    httpd.jobs = Jobs(httpd.ws, cfg)
    httpd.verbose = verbose
    return httpd


def main(argv=None):
    ap = argparse.ArgumentParser(description="관찰 작업창 서버")
    ap.add_argument("--config")
    ap.add_argument("--vault", help="vault_root 대신 쓸 폴더 (리허설용)")
    ap.add_argument("--port", type=int)
    ap.add_argument("--render-delay", type=float, default=30.0, help="입력이 멈춘 뒤 생성본을 다시 만드는 시간(초)")
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args(argv)
    cfg = A.load_config(a.config)
    if a.config:
        cfg["_config_path"] = str(Path(a.config).expanduser().resolve())
    vault = a.vault or cfg.get("vault_root")
    if not vault or not Path(vault).expanduser().is_dir():
        print("vault_root 폴더가 없습니다. ~/.config/dsc/dsc.config.json의 vault_root를 확인하십시오: %s" % vault,
              file=sys.stderr)
        return 2
    port = a.port or int(cfg.get("port") or 8787)
    try:
        httpd = make_server(Path(vault).expanduser(), cfg, port, a.render_delay, a.verbose)
    except OSError as e:
        print("포트 %d을 열지 못했습니다(이미 켜져 있을 수 있습니다): %s" % (port, e), file=sys.stderr)
        return 2
    print("관찰 작업창: http://127.0.0.1:%d  (끝내려면 Ctrl+C)" % port, flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
        httpd.ws.flush_renders()
    return 0


if __name__ == "__main__":
    sys.exit(main())
