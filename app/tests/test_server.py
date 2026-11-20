#!/usr/bin/env python3
"""관찰 작업창 서버 시험 (M4 완료 기준). 네트워크 없이 임시 볼트에서 돕니다.

  python3 -m unittest discover -s app/tests
"""
import http.client
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
import server as SV  # noqa: E402
A = SV.A

PASSAGE = {
    "dsc_version": "1.0.0", "reference": "고린도후서 4:7-8", "version": 1,
    "book": {"ko": "고린도후서", "usfm": "2CO", "en": "2 Corinthians", "testament": "NT"},
    "range": {"start": [4, 7], "end": [4, 8]}, "collected_at": "2026-11-20T09:00:00+09:00",
    "translations": {"NKRV": {"name": "개역개정", "abbr": "NKRV", "source": "bible.bskorea.or.kr", "urls": [],
                              "copyright": "", "verses": [{"ref": "4:7", "text": "우리가 이 보배를 질그릇에 가졌으니"},
                                                          {"ref": "4:8", "text": "우리가 사방으로 우겨쌈을 당하여도"}],
                              "headings": []}},
    "original": {"NA28": {"name": "NA28", "verses": [
        {"ref": "4:7", "text": "Ἔχομεν δὲ τὸν θησαυρὸν τοῦτον ἐν ὀστρακίνοις σκεύεσιν, ἵνα ἡ ὑπερβολὴ τῆς δυνάμεως ᾖ τοῦ θεοῦ"},
        {"ref": "4:8", "text": "ἐν παντὶ θλιβόμενοι ἀλλ’ οὐ στενοχωρούμενοι,"}]}},
    "clauses": [{"id": "4.7a", "verse": "4:7", "text": "Ἔχομεν δὲ τὸν θησαυρὸν τοῦτον ἐν ὀστρακίνοις σκεύεσιν,"},
                {"id": "4.7b", "verse": "4:7", "text": "ἵνα ἡ ὑπερβολὴ τῆς δυνάμεως ᾖ τοῦ θεοῦ"},
                {"id": "4.8a", "verse": "4:8", "text": "ἐν παντὶ θλιβόμενοι ἀλλ’ οὐ στενοχωρούμενοι,"}],
    "adjacent_pericopes": {}, "missing": [], "notes": [],
}


def make_week(vault, wid="S_20261108", stage="3", legacy=False):
    wd = vault / wid
    (wd / "00_수집" / "주석").mkdir(parents=True)
    (wd / "00_수집" / "passage.json").write_text(json.dumps(PASSAGE, ensure_ascii=False), encoding="utf-8")
    (wd / "00_수집" / "주석" / "Logos_Harris_고린도후서4_7-8.md").write_text("---\nsource: test\n---\n주석 본문", encoding="utf-8")
    if not legacy:
        st = {"dsc_version": "1.0.0", "week": wid, "text": "고린도후서 4:7-8", "sermon_date": "2026-11-08",
              "current_stage": stage, "stage_entered": {"0": "x"}}
        (wd / "progress.json").write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
    else:
        (wd / "01_본문만남_2026-11-08_고린도후서4_7-8.md").write_text("---\nstage: 1\n---\n", encoding="utf-8")
    return wd


class Live:
    """임시 볼트 위에 실제 서버를 띄웁니다."""

    def __init__(self, vault, render_delay=None, port=0):
        self.httpd = SV.make_server(vault, {"preacher": "시험", "church": "시험"}, port, render_delay)
        self.port = self.httpd.server_address[1]
        self.token = self.httpd.token
        self.th = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.th.start()

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    def req(self, method, path, body=None, token=True, host=None, origin="auto", ctype="application/json", extra=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        h = {"Host": host or "127.0.0.1:%d" % self.port}
        if token:
            h["X-DSC-Token"] = self.token if token is True else token
        if origin == "auto":
            if method in ("PUT", "POST"):
                h["Origin"] = "http://127.0.0.1:%d" % self.port
        elif origin is not None:
            h["Origin"] = origin
        data = None
        if body is not None:
            data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
            h["Content-Type"] = ctype
        h.update(extra or {})
        c.request(method, path, body=data, headers=h)
        r = c.getresponse()
        raw = r.read()
        c.close()
        try:
            return r.status, json.loads(raw.decode() or "{}"), r
        except ValueError:
            return r.status, raw.decode(), r


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="dscws_"))
        self.vault = self.tmp / "vault"
        self.vault.mkdir()
        self.wd = make_week(self.vault)
        self.live = Live(self.vault)

    def tearDown(self):
        self.live.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def put(self, ref, base="", note=""):
        return self.live.req("PUT", "/api/weeks/S_20261108/notes/%s" % ref, {"note": note, "base": base})

    def set_stage(self, s):
        p = self.wd / "progress.json"
        st = json.loads(p.read_text(encoding="utf-8"))
        st["current_stage"] = s
        p.write_text(json.dumps(st), encoding="utf-8")


class TestPersistence(Base):
    def test_write_restart_restore(self):
        code, d, _ = self.put("4:7", note="질그릇 — 깨지기 쉬운 그릇\n오늘 나의 연약함")
        self.assertEqual(code, 200, d)
        self.live.stop()
        self.live = Live(self.vault)                     # 재시작 (새 토큰)
        code, d, _ = self.live.req("GET", "/api/weeks/S_20261108/notes")
        self.assertEqual(code, 200)
        self.assertEqual(d["verses"]["4:7"]["note"], "질그릇 — 깨지기 쉬운 그릇\n오늘 나의 연약함")
        saved = json.loads((self.wd / "03_원어관찰.json").read_text(encoding="utf-8"))
        self.assertEqual([c["ref"] for c in saved["verses"]], ["4:7"])
        self.assertEqual(saved["unit"], "verse")

    def test_order_follows_passage(self):
        _, a, _ = self.put("4:8", note="셋째")
        _, b, _ = self.put("4:7", note="첫째")
        saved = json.loads((self.wd / "03_원어관찰.json").read_text(encoding="utf-8"))
        self.assertEqual([c["ref"] for c in saved["verses"]], ["4:7", "4:8"])

    def test_atomic_write_leaves_no_temp_and_old_file_on_failure(self):
        self.put("4:7", note="처음")
        before = (self.wd / "03_원어관찰.json").read_text(encoding="utf-8")
        orig = os.replace

        def boom(*a, **k):
            raise OSError("디스크 가득")
        A.os.replace = boom
        try:
            code, _, _ = self.put("4:8", note="두 번째")
        finally:
            A.os.replace = orig
        self.assertEqual(code, 500)
        self.assertEqual((self.wd / "03_원어관찰.json").read_text(encoding="utf-8"), before)
        leftovers = [f.name for f in self.wd.iterdir() if f.name.endswith(".tmp")]
        self.assertEqual(leftovers, [])

    def test_unknown_clause_and_bad_values(self):
        self.assertEqual(self.put("9:9", note="x")[0], 404)
        self.assertEqual(self.put("../x")[0], 400)
        self.assertEqual(self.live.req("PUT", "/api/weeks/S_20261108/notes/4:7",
                                       {"note": 3, "base": ""})[0], 400)
        self.assertEqual(self.put("4:7", note="가" * (SV.MAX_FIELD + 1))[0], 413)


class TestConflict(Base):
    def test_two_tabs_late_writer_gets_409(self):
        code, a, _ = self.put("4:7", note="탭 A 처음")
        base = a["updated"]
        code1, d1, _ = self.put("4:7", base=base, note="탭 A 고침")        # 탭 A
        code2, d2, _ = self.put("4:7", base=base, note="탭 B 고침")        # 탭 B (같은 base, 늦음)
        self.assertEqual(code1, 200)
        self.assertEqual(code2, 409)
        self.assertEqual(d2["current"]["note"], "탭 A 고침")
        self.assertEqual(d2["current"]["updated"], d1["updated"])
        saved = json.loads((self.wd / "03_원어관찰.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["verses"][0]["note"], "탭 A 고침")

    def test_first_write_conflict_when_base_missing(self):
        self.put("4:7", note="A가 먼저 씀")
        code, d, _ = self.put("4:7", base="", note="B는 빈 칸을 보고 씀")
        self.assertEqual(code, 409)

    def test_parallel_writers_one_wins(self):
        _, a, _ = self.put("4:7", note="처음")
        base, out = a["updated"], []

        def go(i):
            out.append(self.put("4:7", base=base, note="동시 %d" % i)[0])
        ts = [threading.Thread(target=go, args=(i,)) for i in range(6)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(sorted(out), [200] + [409] * 5)


class TestSecurity(Base):
    def test_bad_host_rejected(self):
        for host in ("evil.example:%d" % self.live.port, "127.0.0.1:1", "localhost.evil:%d" % self.live.port):
            self.assertEqual(self.live.req("GET", "/api/weeks", host=host)[0], 421, host)
        self.assertEqual(self.live.req("GET", "/", host="attacker.test")[0], 421)
        self.assertEqual(self.live.req("GET", "/api/weeks", host="localhost:%d" % self.live.port)[0], 200)

    def test_bad_origin_rejected(self):
        self.assertEqual(self.live.req("GET", "/api/weeks", origin="http://evil.example")[0], 403)
        self.assertEqual(self.put_with(origin="http://evil.example")[0], 403)
        self.assertEqual(self.put_with(origin="null")[0], 403)
        self.assertEqual(self.put_with(origin=None)[0], 403)              # 쓰기는 Origin 필수
        self.assertEqual(self.live.req("GET", "/api/weeks", extra={"Sec-Fetch-Site": "cross-site"})[0], 403)

    def put_with(self, origin):
        return self.live.req("PUT", "/api/weeks/S_20261108/notes/4:7",
                             {"note": "x", "base": ""}, origin=origin)

    def test_token_required(self):
        self.assertEqual(self.live.req("GET", "/api/weeks", token=False)[0], 401)
        self.assertEqual(self.live.req("GET", "/api/weeks", token="wrong")[0], 401)
        code, html, r = self.live.req("GET", "/", token=False)
        self.assertEqual(code, 200)
        self.assertIn(self.live.token, html)
        self.assertIn("script-src 'self'", r.getheader("Content-Security-Policy"))
        self.assertIsNone(r.getheader("Access-Control-Allow-Origin"))

    def test_json_only(self):
        code, _, _ = self.live.req("PUT", "/api/weeks/S_20261108/notes/4:7", b"note=x",
                                   ctype="application/x-www-form-urlencoded")
        self.assertEqual(code, 415)
        code, _, _ = self.live.req("PUT", "/api/weeks/S_20261108/notes/4:7", b"{bad", ctype="application/json")
        self.assertEqual(code, 400)

    def test_dotdot_and_bad_week_ids(self):
        for path in ("/api/weeks/../progress", "/api/weeks/%2e%2e/progress", "/api/weeks/S_20261108/../../x",
                     "/api/weeks/S_2026/progress", "/api/weeks/..%2Fvault/progress", "/../server.py",
                     "/static/../server.py"):
            code = self.live.req("GET", path)[0]
            self.assertIn(code, (400, 404), path)
            self.assertNotEqual(code, 200, path)

    def test_symlink_week_outside_vault(self):
        outside = self.tmp / "outside" / "S_20991231"
        make_week(self.tmp / "outside", "S_20991231")
        os.symlink(outside, self.vault / "S_20991231")
        self.assertEqual(self.live.req("GET", "/api/weeks/S_20991231/progress")[0], 404)
        ids = [w["id"] for w in self.live.req("GET", "/api/weeks")[1]["weeks"]]
        self.assertNotIn("S_20991231", ids)

    def test_symlinked_commentary_dir_outside(self):
        self.set_stage("4")
        shutil.rmtree(self.wd / "00_수집" / "주석")
        secret = self.tmp / "secret"
        secret.mkdir()
        (secret / "x.md").write_text("밖의 비밀", encoding="utf-8")
        os.symlink(secret, self.wd / "00_수집" / "주석")
        self.assertEqual(self.live.req("GET", "/api/weeks/S_20261108/commentary")[0], 403)

    def test_methods(self):
        self.assertEqual(self.live.req("DELETE", "/api/weeks")[0], 405)
        self.assertEqual(self.live.req("POST", "/", {"a": 1})[0], 405)


class TestGate(Base):
    def comm(self):
        return self.live.req("GET", "/api/weeks/S_20261108/commentary")

    def test_commentary_by_stage(self):
        for s, want in (("0", 403), ("1", 403), ("2", 403), ("3", 403), ("4", 200), ("5", 200), ("6", 200),
                        ("7A", 403), ("7B", 200), ("8", 200), ("9", 200)):
            self.set_stage(s)
            code, d, _ = self.comm()
            self.assertEqual(code, want, s)
            if code == 200:
                self.assertEqual(d["items"][0]["name"], "Logos_Harris_고린도후서4_7-8.md")
            else:
                self.assertNotIn("주석 본문", json.dumps(d, ensure_ascii=False))

    def test_stage_button_needs_confirm_and_next_only(self):
        r = self.live.req("POST", "/api/weeks/S_20261108/stage/enter", {"to": "4"})
        self.assertEqual(r[0], 400)
        r = self.live.req("POST", "/api/weeks/S_20261108/stage/enter", {"to": "6", "confirm": True})
        self.assertEqual(r[0], 409)
        r = self.live.req("POST", "/api/weeks/S_20261108/stage/enter", {"to": "2", "confirm": True})
        self.assertEqual(r[0], 409)
        self.assertEqual(self.comm()[0], 403)
        code, d, _ = self.live.req("POST", "/api/weeks/S_20261108/stage/enter", {"to": "4", "confirm": True})
        self.assertEqual(code, 200, d)
        self.assertEqual(d["current_stage"], "4")
        self.assertEqual(self.comm()[0], 200)
        st = json.loads((self.wd / "progress.json").read_text(encoding="utf-8"))
        self.assertEqual(st["history"][-1]["by"], "workspace")
        self.assertTrue((self.wd / "00_진행상황.md").exists())

    def test_legacy_week_read_only(self):
        make_week(self.vault, "S_20261101", legacy=True)
        code, d, _ = self.live.req("GET", "/api/weeks/S_20261101/progress")
        self.assertEqual(code, 200)
        self.assertTrue(d["legacy"])
        self.assertEqual(self.live.req("PUT", "/api/weeks/S_20261101/notes/4:7", {"note": "x", "base": ""})[0], 403)
        self.assertEqual(self.live.req("POST", "/api/weeks/S_20261101/stage/enter", {"to": "1", "confirm": True})[0], 403)
        self.assertEqual(self.live.req("GET", "/api/weeks/S_20261101/commentary")[0], 403)
        self.assertTrue(self.live.req("GET", "/api/weeks/S_20261101/notes")[1]["readonly"])
        self.assertFalse((self.vault / "S_20261101" / "03_원어관찰.json").exists())


class TestRender(Base):
    def md(self):
        return sorted(self.wd.glob("03_원어관찰_*.md"))

    def test_render_on_leaving_stage3_and_manual_edit_protected(self):
        self.put("4:7", note="질그릇")
        code, d, _ = self.live.req("POST", "/api/weeks/S_20261108/stage/enter", {"to": "4", "confirm": True})
        self.assertEqual(code, 200)
        self.assertEqual(d["render"]["status"], "ok")
        [f] = self.md()
        text = f.read_text(encoding="utf-8")
        self.assertIn("generated: true", text)
        self.assertIn("질그릇", text)
        f.write_text(text + "\n설교자가 Obsidian에서 덧붙인 줄\n", encoding="utf-8")   # 손으로 고침
        st = self.live.httpd.ws.render_now("S_20261108", self.wd)
        self.assertEqual(st["status"], "issues")
        self.assertIn("설교자가 Obsidian에서 덧붙인 줄", f.read_text(encoding="utf-8"))
        prog = self.live.req("GET", "/api/weeks/S_20261108/progress")[1]
        self.assertTrue(prog["render"]["issues"])

    def test_idle_render_after_delay(self):
        self.live.stop()
        self.live = Live(self.vault, render_delay=0.3)
        self.put("4:8", note="목적절")
        self.assertEqual(self.md(), [])
        for _ in range(40):
            if self.md():
                break
            time.sleep(0.05)
        self.assertEqual(len(self.md()), 1)
        self.assertIn("목적절", self.md()[0].read_text(encoding="utf-8"))

    def test_render_does_not_clobber_preacher_file(self):
        import datetime as dt
        label = "고린도후서4_7-8"
        own = self.wd / ("03_원어관찰_%s_%s.md" % (dt.date.today().isoformat(), label))
        own.write_text("설교자가 직접 만든 파일", encoding="utf-8")
        self.put("4:7", note="x")
        st = self.live.httpd.ws.render_now("S_20261108", self.wd)
        self.assertEqual(st["status"], "issues")
        self.assertEqual(own.read_text(encoding="utf-8"), "설교자가 직접 만든 파일")


class TestOrphans(Base):
    def test_orphan_notes_kept_when_clause_list_changes(self):
        self.put("4:8", note="남길 기록")
        p = self.wd / "00_수집" / "passage.json"
        d = json.loads(p.read_text(encoding="utf-8"))
        d["original"]["NA28"]["verses"] = d["original"]["NA28"]["verses"][:1]
        p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        code, n, _ = self.live.req("GET", "/api/weeks/S_20261108/notes")
        self.assertEqual([o["ref"] for o in n["orphans"]], ["4:8"])
        self.put("4:7", note="새 기록")
        saved = json.loads((self.wd / "03_원어관찰.json").read_text(encoding="utf-8"))
        self.assertEqual([o["ref"] for o in saved["_orphans"]], ["4:8"])
        self.assertEqual(saved["_orphans"][0]["note"], "남길 기록")


class TestReviewFixes(Base):
    def test_stage_advances_even_if_render_fails(self):
        self.put("4:7", note="x")
        p = self.wd / "progress.json"
        st = json.loads(p.read_text(encoding="utf-8"))
        del st["text"]
        p.write_text(json.dumps(st), encoding="utf-8")
        code, d, _ = self.live.req("POST", "/api/weeks/S_20261108/stage/enter", {"to": "4", "confirm": True})
        self.assertEqual(code, 200, d)
        self.assertEqual(d["current_stage"], "4")
        self.assertIn(d["render"]["status"], ("refused", "error"))

    def test_unexpected_error_returns_json_500(self):
        p = self.wd / "00_수집" / "passage.json"
        d = json.loads(p.read_text(encoding="utf-8"))
        d["original"]["NA28"]["verses"] = ["깨진 항목"]
        p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        code, body, _ = self.live.req("GET", "/api/weeks/S_20261108/notes")
        self.assertIn(code, (200, 500))
        self.assertIsInstance(body, dict)

    def test_parallel_renders_never_report_false_hand_edit(self):
        self.put("4:7", note="동시 생성")
        ws = self.live.httpd.ws
        out = []
        ts = [threading.Thread(target=lambda: out.append(ws.render_now("S_20261108", self.wd)["status"])) for _ in range(8)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(out, ["ok"] * 8)
        st = json.loads((self.wd / "progress.json").read_text(encoding="utf-8"))
        [f] = self.wd.glob("03_원어관찰_*.md")
        self.assertEqual(A.sha(f.read_text(encoding="utf-8")), st["stage3_render"]["sha256"])

    def test_bad_render_file_name_in_progress_refused(self):
        self.put("4:7", note="x")
        p = self.wd / "progress.json"
        st = json.loads(p.read_text(encoding="utf-8"))
        st["stage3_render"] = {"file": "../../밖.md", "sha256": "0"}
        p.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
        r = self.live.httpd.ws.render_now("S_20261108", self.wd)
        self.assertEqual(r["status"], "refused")
        self.assertFalse((self.tmp / "밖.md").exists())

    def test_self_application_files_hidden(self):
        self.set_stage("4")
        (self.wd / "00_수집" / "주석" / "07A_자기적용_2026-11-06_x.md").write_text("비공개 문장", encoding="utf-8")
        code, d, _ = self.live.req("GET", "/api/weeks/S_20261108/commentary")
        self.assertEqual(code, 200)
        self.assertNotIn("비공개 문장", json.dumps(d, ensure_ascii=False))
        lw = make_week(self.vault, "S_20261101", legacy=True)
        import unicodedata
        (lw / unicodedata.normalize("NFD", "06A_자기적용_2026-10-30_y.md")).write_text("z", encoding="utf-8")
        files = self.live.req("GET", "/api/weeks/S_20261101/progress")[1]["files"]
        self.assertFalse(any("자기적용" in f for f in files), files)

    def test_symlinked_progress_outside_not_trusted(self):
        out = self.tmp / "p.json"
        out.write_text(json.dumps({"dsc_version": "1.0.0", "text": "OUTSIDE-LEAK", "current_stage": "4"}), encoding="utf-8")
        wd = self.vault / "S_20261122"
        wd.mkdir()
        os.symlink(out, wd / "progress.json")
        self.assertNotIn("OUTSIDE-LEAK", json.dumps(self.live.req("GET", "/api/weeks")[1], ensure_ascii=False))

    def test_put_requires_all_fields_and_sane_length(self):
        r = self.live.req("PUT", "/api/weeks/S_20261108/notes/4:7", {"base": ""})
        self.assertEqual(r[0], 400)
        r = self.live.req("PUT", "/api/weeks/S_20261108/notes/4:7", b"{}", extra={"Content-Length": "-1"})
        self.assertEqual(r[0], 400)

    def test_localhost_origin_and_same_site(self):
        port = self.live.port
        code, _, _ = self.live.req("PUT", "/api/weeks/S_20261108/notes/4:7",
                                   {"note": "a", "base": ""},
                                   host="localhost:%d" % port, origin="http://localhost:%d" % port)
        self.assertEqual(code, 200)
        self.assertEqual(self.live.req("GET", "/api/weeks", extra={"Sec-Fetch-Site": "same-site"})[0], 403)

    def test_orphan_comes_back_when_clause_returns(self):
        self.put("4:8", note="돌아올 기록")
        p = self.wd / "00_수집" / "passage.json"
        full = p.read_text(encoding="utf-8")
        d = json.loads(full)
        d["original"]["NA28"]["verses"] = d["original"]["NA28"]["verses"][:1]
        p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        _, a, _ = self.put("4:7", note="중간 기록")          # 4.8a가 _orphans로 감
        p.write_text(full, encoding="utf-8")                      # 구문이 다시 생김
        n = self.live.req("GET", "/api/weeks/S_20261108/notes")[1]
        self.assertEqual(n["verses"]["4:8"]["note"], "돌아올 기록")
        self.assertEqual(n["orphans"], [])
        code, d2, _ = self.put("4:8", base=n["verses"]["4:8"]["updated"], note="이어 씀")
        self.assertEqual(code, 200, d2)
        saved = json.loads((self.wd / "03_원어관찰.json").read_text(encoding="utf-8"))
        self.assertNotIn("_orphans", saved)

    def test_pending_render_flushed_on_shutdown(self):
        self.live.stop()
        self.live = Live(self.vault, render_delay=60)
        self.put("4:7", note="끄기 직전 기록")
        self.live.httpd.ws.flush_renders()
        [f] = self.wd.glob("03_원어관찰_*.md")
        self.assertIn("끄기 직전 기록", f.read_text(encoding="utf-8"))


class TestVerseNotes(Base):
    def test_syntax_api(self):
        self.assertEqual(self.live.req("GET", "/api/weeks/S_20261108/syntax")[1]["verses"], [])
        (self.wd / "00_수집" / "syntax.json").write_text(json.dumps({"verses": [{"ref": "4:7", "clauses": []}]}), encoding="utf-8")
        d = self.live.req("GET", "/api/weeks/S_20261108/syntax")[1]
        self.assertEqual((d["verses"], d["rejected"]), ([], ["4:7"]))       # 수집본과 맞지 않는 절은 보이지 않음
        good = {"verses": [{"ref": "4:8", "main_verbs": [], "commentary": ["가", "나"], "chain": [{"verb": "θλιβόμενοι", "note": "x"}],
                            "clauses": [{"id": "4.8a", "label": "adv ptc", "family": "ptc", "indent": 1,
                                         "words": [{"g": w} for w in ["ἐν", "παντὶ", "θλιβόμενοι", "ἀλλ'", "οὐ", "στενοχωρούμενοι"]]}]}]}
        (self.wd / "00_수집" / "syntax.json").write_text(json.dumps(good, ensure_ascii=False), encoding="utf-8")
        d = self.live.req("GET", "/api/weeks/S_20261108/syntax")[1]
        self.assertEqual([v["ref"] for v in d["verses"]], ["4:8"])
        words = [w["g"] for w in d["verses"][0]["clauses"][0]["words"]]
        self.assertEqual(words[3], "ἀλλ’")                                    # 수집본 글자로 바뀌어 나감
        self.assertEqual(words[-1], "στενοχωρούμενοι,")

    def test_old_clause_notes_shown_as_orphans_not_lost(self):
        (self.wd / "03_원어관찰.json").write_text(json.dumps({"clauses": [
            {"id": "4.7a", "observe": "예전 관찰", "interpret": "", "apply": "예전 적용"}]}, ensure_ascii=False), encoding="utf-8")
        n = self.live.req("GET", "/api/weeks/S_20261108/notes")[1]
        self.assertEqual(n["verses"], {})
        self.assertIn("예전 관찰", n["orphans"][0]["note"])
        self.put("4:7", note="새 노트")
        saved = json.loads((self.wd / "03_원어관찰.json").read_text(encoding="utf-8"))
        self.assertIn("예전 적용", saved["_orphans"][0]["note"])
        self.assertNotIn("clauses", saved)

    def test_bad_ref(self):
        for ref in ("4.7a", "4:7a", "..", "4%3A7%3A1"):
            self.assertIn(self.put(ref, note="x")[0], (400, 404), ref)


class TestNotesReview(Base):
    def test_m4_orphans_visible(self):
        (self.wd / "03_원어관찰.json").write_text(json.dumps({"verses": [],
            "_orphans": [{"id": "4.9b", "observe": "OLD-ORPHAN"}]}), encoding="utf-8")
        n = self.live.req("GET", "/api/weeks/S_20261108/notes")[1]
        self.assertIn("OLD-ORPHAN", n["orphans"][0]["note"])
        self.assertEqual(n["orphans"][0]["ref"], "4.9b")

    def test_malformed_notes_file_does_not_500(self):
        (self.wd / "03_원어관찰.json").write_text(json.dumps({"verses": None, "clauses": [{"observe": 5}]}), encoding="utf-8")
        self.assertEqual(self.live.req("GET", "/api/weeks/S_20261108/notes")[0], 200)
        self.assertEqual(self.put("4:7", note="x")[0], 200)

    def test_duplicate_orphans_last_wins_everywhere(self):
        (self.wd / "03_원어관찰.json").write_text(json.dumps({"verses": [], "_orphans": [
            {"ref": "4:7", "note": "첫째", "updated": "a"}, {"ref": "4:7", "note": "둘째", "updated": "b"}]},
            ensure_ascii=False), encoding="utf-8")
        n = self.live.req("GET", "/api/weeks/S_20261108/notes")[1]
        self.assertEqual(n["verses"]["4:7"]["note"], "둘째")
        self.assertEqual(self.put("4:7", base=n["verses"]["4:7"]["updated"], note="이어 씀")[0], 200)


if __name__ == "__main__":
    unittest.main()
