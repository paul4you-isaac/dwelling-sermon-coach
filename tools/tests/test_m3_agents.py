#!/usr/bin/env python3
"""M3 수집·기록보관 스크립트 시험 (네트워크 없이).

  python3 -m unittest discover -s tools/tests
"""
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "skills/dwelling-sermon-coach/scripts"))
import check_privacy  # noqa: E402
import dsc_archive  # noqa: E402
import dsc_bible as B  # noqa: E402
import dsc_collect  # noqa: E402
import dsc_collect as C  # noqa: E402

REF = "고린도후서 4:1-18"


def run(mod, argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = mod.main(argv)
    return code, json.loads(buf.getvalue())


class TestBible(unittest.TestCase):
    def test_parse_ref(self):
        p = B.parse_ref("고후 4:1-18")
        self.assertEqual((p["book"]["usfm"], p["start"], p["end"]), ("2CO", [4, 1], [4, 18]))
        p = B.parse_ref("요한복음 15:1-16:4")
        self.assertEqual((p["start"], p["end"]), ([15, 1], [16, 4]))
        p = B.parse_ref("시편 23")
        self.assertEqual((p["start"], p["end"]), ([23, 1], [23, None]))
        self.assertEqual(B.ref_label(B.parse_ref("고린도후서 4:7")), "고린도후서4_7")
        self.assertEqual(B.ref_label(B.parse_ref(REF)), "고린도후서4_1-18")
        with self.assertRaises(B.RefError):
            B.parse_ref("없는책 1:1")
        with self.assertRaises(B.RefError):
            B.parse_ref("창세기 12:9-1")

    def test_platform_rejects_wrong_bible(self):
        state = {"x/chapters/2CO.4/with-study-content": {"data": {"chapter": {
            "bibleId": "a5f9087beeef2fdc-01", "content": [], "copyright": ""}}}}
        page = '<script id="IBEP-main-state" type="application/json">%s</script>' % json.dumps(state)
        with self.assertRaises(ValueError):
            B.parse_platform(page, "2CO", 4, "d30958d1302f9bd8-01")   # NA28을 요청했는데 개역개정이 옴

    def test_platform_verse_across_paragraph(self):
        content = [
            {"type": "paragraph", "style": "p", "content": [
                {"type": "verse-text", "verseId": "JHN.16.4", "content": "앞 반절이다."},
                {"type": "study", "verseId": "JHN.16.4"}]},
            {"type": "paragraph", "style": "s", "content": [{"type": "text", "content": "성령의 일"}]},
            {"type": "paragraph", "style": "p", "content": [
                {"type": "verse-text", "verseId": "JHN.16.4", "content": "또 뒤 반절."}]}]
        state = {"x/chapters/JHN.16/with-study-content": {"data": {"chapter": {
            "bibleId": "B", "content": content, "copyright": "c"}}}}
        page = '<script id="IBEP-main-state" type="application/json">%s</script>' % json.dumps(state, ensure_ascii=False)
        d = B.parse_platform(page, "JHN", 16, "B")
        self.assertEqual(d["verses"][4], "앞 반절이다. 또 뒤 반절.")

    def test_old_site_verse_split_by_heading(self):
        page = ('<span><span class="number">4&nbsp;</span>앞 반절이다.<br /><br />'
                '<font class="smallTitle">성령의 일</font><br />또 <a class=comment href="#">2)</a>뒤 반절. '
                "<div id='D_1' class=D2>각주</div></font></span><br /><span><span class=\"number\">5&nbsp;</span>다음 절.</span></td>")
        v = B.parse_old_site(page)
        self.assertEqual(v, {4: "앞 반절이다. 또 뒤 반절.", 5: "다음 절."})

    def test_clauses(self):
        self.assertEqual(B.split_clauses("ὅτι ὁ θεὸς ὁ εἰπών· ἐκ σκότους φῶς λάμψει.", "NT"),
                         ["ὅτι ὁ θεὸς ὁ εἰπών·", "ἐκ σκότους φῶς λάμψει."])
        heb = "וַיֹּ֤אמֶר יְהוָה֙ אָבִ֑יךָ אֶל־הָאָ֖רֶץ אַרְאֶֽךָּ׃"
        self.assertEqual(len(B.split_clauses(heb, "OT")), 2)
        self.assertEqual([B.letters(i) for i in (0, 1, 25, 26)], ["a", "b", "z", "aa"])


class TestWeek(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.wd = self.root / "S_20261108"
        self.cfg = self.root / "cfg.json"
        self.mat = self.root / "materials"
        self.mat.mkdir()
        (self.mat / "B_고린도후서_시험.md").write_text(
            "# 고린도후서\n\n## 3:12-18\n앞\n\n## 4:7-12 질그릇\n발췌\n\n## 5:1-10\n뒤\n", encoding="utf-8")
        (self.mat / "고린도후서.pdf").write_text("pdf는 보지 않음 4:7", encoding="utf-8")
        self.cfg.write_text(json.dumps({"materials_dirs": [str(self.mat)], "logos_bridge": "",
                                        "preacher": "시험 목사", "church": "시험교회"}), encoding="utf-8")
        self.c = ["--config", str(self.cfg)]

    def tearDown(self):
        self.tmp.cleanup()

    def arch(self, *a):
        return run(dsc_archive, list(a) + ["--week-dir", str(self.wd)] + self.c)

    def coll(self, task):
        return run(dsc_collect, [task, "--week-dir", str(self.wd), "--ref", REF] + self.c)

    def test_gate_and_advance(self):
        code, r = self.arch("init", "--ref", REF, "--sermon-date", "2026-11-08")
        self.assertEqual(r["status"], "ok")
        self.assertEqual(json.loads((self.wd / "progress.json").read_text())["current_stage"], "0")
        for stage in ("0",):
            _, r = self.coll("commentary")
            self.assertEqual(r["status"], "refused")
        self.assertFalse((self.wd / "00_수집/주석").exists(), "0단계 동안 주석 폴더가 비어 있어야 함")
        _, r = self.arch("advance_stage", "--to", "1")
        self.assertEqual(r["status"], "refused")                 # 설교자 확인 없음
        for s in ("1", "2", "3"):
            _, r = self.arch("advance_stage", "--to", s, "--confirmed-by-preacher")
            self.assertEqual(r["status"], "ok")
            _, r = self.coll("commentary")
            self.assertEqual(r["status"], "refused", "Stage %s에서 주석 수집이 거절돼야 함" % s)
        _, r = self.arch("advance_stage", "--to", "2", "--confirmed-by-preacher")
        self.assertEqual(r["status"], "refused")                 # 되돌리기 금지
        self.arch("advance_stage", "--to", "4", "--confirmed-by-preacher")
        _, r = self.coll("commentary")
        self.assertIn(r["status"], ("ok", "partial"))
        self.assertEqual(r["counts"]["commentary"], 1)           # md 주석 1, pdf 제외, Logos 경로 없음
        out = (self.wd / "00_수집/주석/B_고린도후서_시험_고린도후서4_1-18.md").read_text(encoding="utf-8")
        self.assertIn("4:7-12 질그릇", out)
        self.assertNotIn("3:12-18", out)
        self.assertNotIn("5:1-10", out)
        self.assertTrue(any("Logos" in m for m in r["missing"]))
        _, r = self.arch("advance_stage", "--to", "7A", "--confirmed-by-preacher")
        self.assertEqual(r["status"], "issues")                  # 5·6 건너뜀 알림
        _, r = self.coll("commentary")
        self.assertEqual(r["status"], "refused")                 # 7A에서 다시 차단

    def test_safe_write_outside(self):
        base = self.root / "S_20261108/00_수집"
        base.mkdir(parents=True)
        with self.assertRaises(dsc_collect.Refused):
            dsc_collect.safe_write(base, "../밖.md", "x")
        (base / "link").symlink_to(self.root)
        with self.assertRaises(dsc_collect.Refused):
            dsc_collect.safe_write(base, "link/밖.md", "x")

    def test_bridge_allowlist(self):
        for cmd in ("open", "collect", "export", "publish"):
            with self.assertRaises(dsc_collect.Refused):
                dsc_collect.bridge({"logos_bridge": "/bin/echo"}, cmd)

    def test_legacy_week_readonly(self):
        self.wd.mkdir()
        (self.wd / "01_본문만남_2026-11-08_고린도후서4_1-18.md").write_text("---\n---\n", encoding="utf-8")
        _, r = self.arch("init", "--ref", REF, "--sermon-date", "2026-11-08")
        self.assertEqual(r["status"], "refused")
        _, r = self.arch("validate")
        self.assertTrue(r.get("legacy"))

    def test_validate(self):
        self.arch("init", "--ref", REF, "--sermon-date", "2026-11-08")
        good = ("---\ndsc_version: 1.0.0\ndate: 2026-11-06\nsermon_date: 2026-11-08\ntext: 고린도후서 4:1-18\n"
                "stage: 7\nsession: 자기적용\npreacher: 시험 목사\nchurch: 시험교회\nstatus: dwelling\n"
                "%stags: [dwelling-sermon-coach, 2corinthians, stage-7a-self%s]\n---\n본문\n")
        f = self.wd / "07A_자기적용_2026-11-06_고린도후서4_1-18.md"
        f.write_text(good % ("private: true\n", ", private"), encoding="utf-8")
        _, r = self.arch("validate")
        self.assertEqual(r["issues"], [])
        f.write_text(good % ("", ""), encoding="utf-8")
        _, r = self.arch("validate")
        probs = " ".join(i["problem"] for i in r["issues"])
        self.assertIn("private: true가 없습니다", probs)
        (self.wd / "06A_자기적용_2026-11-06_x.md").write_text("---\n---\n", encoding="utf-8")
        (self.wd / "02_동행일지_2026-11-06_x.md").write_text("---\nsermon-date: 2026-11-08\nstage: 3\n---\n", encoding="utf-8")
        _, r = self.arch("validate")
        probs = " ".join(i["problem"] + i["suggestion"] for i in r["issues"])
        self.assertIn("07A_자기적용_…로 바꾸십시오", probs)
        self.assertIn("하이픈 키 sermon-date", probs)
        self.assertIn("파일명 번호(2)와 stage 값(3)", probs)

    def test_render_stage3_protects_manual_edit(self):
        self.arch("init", "--ref", REF, "--sermon-date", "2026-11-08")
        (self.wd / "03_원어관찰.json").write_text(json.dumps({"unit": "verse", "verses": [
            {"ref": "4:7", "note": "질그릇에 담긴 보배 앞에 머묾", "updated": "x"}]},
            ensure_ascii=False), encoding="utf-8")
        _, r = self.arch("render_stage3")
        self.assertEqual(r["status"], "ok")
        md = Path(r["saved"][0])
        self.assertIn("generated: true", md.read_text(encoding="utf-8"))
        self.assertIn("## 고린도후서 4:7", md.read_text(encoding="utf-8"))
        self.assertIn("질그릇에 담긴 보배 앞에 머묾", md.read_text(encoding="utf-8"))
        md.write_text(md.read_text(encoding="utf-8") + "\n손으로 고침\n", encoding="utf-8")
        _, r = self.arch("render_stage3")
        self.assertEqual(r["status"], "issues")
        self.assertIn("손으로 고침", md.read_text(encoding="utf-8"))   # 덮어쓰지 않음


class TestPrivacy(unittest.TestCase):
    S = "나는 이번 주에 아무에게도 말하지 못한 두려움을 마주했다."
    V = "우리가 이 보배를 질그릇에 가졌으니."

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.wd = Path(self.tmp.name) / "S_20261122"
        (self.wd / "00_수집").mkdir(parents=True)
        (self.wd / "progress.json").write_text('{"dsc_version":"1.0.0"}', encoding="utf-8")
        self.self_md = self.wd / "07A_자기적용_2026-11-20_x.md"
        self.self_md.write_text("---\nprivate: true\ntags: [stage-7a-self, private]\n---\n%s\n%s\n" % (self.S, self.V),
                                encoding="utf-8")
        (self.wd / "01_본문만남_2026-11-22_x.md").write_text("---\n---\n%s\n" % self.V, encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def check(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = check_privacy.main([str(self.wd), "--json"])
        out = buf.getvalue()
        self.assertNotIn("두려움", out, "7A 문장을 출력하면 안 됨")
        return code, json.loads(out)["result"]["S_20261122"]

    def test_clean(self):
        # 7A에도 있는 성경 인용이 개요에 들어가도, 01에 먼저 있던 문장이면 유출이 아닙니다.
        (self.wd / "설교_20261122_x_개요.md").write_text("---\nstage: 9\n---\n%s\n" % self.V, encoding="utf-8")
        code, r = self.check()
        self.assertEqual((code, r["errors"]), (0, []))           # 성경 인용(01에 있던 문장)은 7A 문장이 아님

    def test_leak_md_and_flags(self):
        o = self.wd / "설교_20261122_x_개요.md"
        o.write_text("---\nstage: 9\n---\n%s\n" % self.S, encoding="utf-8")
        code, r = self.check()
        self.assertEqual(code, 1)
        self.assertTrue(any(e.startswith("leak:") for e in r["errors"]))
        o.write_text("---\nstage: 9\nprivate: true\n---\n%s\n" % self.S, encoding="utf-8")
        self.assertEqual(self.check()[0], 0)
        o.write_text("---\nstage: 9\nshared_by_preacher: true\n---\n%s\n" % self.S, encoding="utf-8")
        code, r = self.check()
        self.assertEqual(code, 0)
        self.assertTrue(any(w.startswith("shared:") for w in r["warnings"]))

    def test_leak_html_and_log(self):
        h = self.wd / "설교_20261122_x_개요.html"
        h.write_text("<html><head></head><body>나는 이번 주에 <b>아무에게도</b> 말하지 못한 두려움을 마주했다.</body></html>",
                     encoding="utf-8")
        self.assertEqual(self.check()[0], 1)
        h.write_text('<html><head><meta name="dsc-private" content="true"></head><body>%s</body></html>' % self.S,
                     encoding="utf-8")
        self.assertEqual(self.check()[0], 0)
        (self.wd / "00_수집/ask_log.jsonl").write_text(json.dumps({"q": self.S}, ensure_ascii=False) + "\n",
                                                       encoding="utf-8")
        code, r = self.check()
        self.assertEqual(code, 0)
        self.assertTrue(any(w.startswith("log-leak:") for w in r["warnings"]))

    def test_missing_private_flag(self):
        self.self_md.write_text("---\ntags: [stage-7a-self]\n---\n%s\n" % self.S, encoding="utf-8")
        code, r = self.check()
        self.assertEqual(code, 1)
        self.assertEqual(sum(e.startswith("private-flag:") for e in r["errors"]), 2)



class TestReviewFixes(unittest.TestCase):
    """독립 검토(M3)가 찾은 문제가 다시 생기지 않게 고정합니다."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.wd = self.root / "S_20261108"
        self.cfg = self.root / "cfg.json"
        self.cfg.write_text("{}", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def arch(self, *a):
        return run(dsc_archive, list(a) + ["--week-dir", str(self.wd), "--config", str(self.cfg)])

    def init(self):
        return self.arch("init", "--ref", REF, "--sermon-date", "2026-11-08")

    def test_unclosed_frontmatter_never_echoes_7a(self):
        self.init()
        (self.wd / "07A_자기적용_2026-11-06_x.md").write_text(
            "---\nstatus: SECRET 문장\nSecret-Key: SECRET\n본문 SECRET\n", encoding="utf-8")
        _, r = self.arch("validate")
        self.assertNotIn("SECRET", json.dumps(r, ensure_ascii=False))
        (self.wd / "07A_자기적용_2026-11-06_x.md").write_text(
            "---\nstatus: SECRET\nstage: SECRET\nSecret-Key: x\n---\n본문\n", encoding="utf-8")
        _, r = self.arch("validate")
        self.assertNotIn("SECRET", json.dumps(r, ensure_ascii=False))

    def test_render_stage3_never_overwrites_unknown_file(self):
        self.init()
        (self.wd / "03_원어관찰.json").write_text('{"clauses": []}', encoding="utf-8")
        import datetime as dt
        mine = self.wd / ("03_원어관찰_%s_고린도후서4_1-18.md" % dt.date.today().isoformat())
        mine.write_text("설교자 원고\n", encoding="utf-8")
        _, r = self.arch("render_stage3")
        self.assertEqual(r["status"], "issues")
        self.assertEqual(mine.read_text(encoding="utf-8"), "설교자 원고\n")

    def test_commentary_skips_private_material(self):
        mat = self.root / "materials"
        (mat / "S_20261101").mkdir(parents=True)
        body = "## 4:7-12\n자기적용 비밀\n"
        (mat / "07A_자기적용_2026-11-01_고린도후서4_1-18.md").write_text(body, encoding="utf-8")
        (mat / "06A_자기적용_2026-10-01_고린도후서4_1-18.md").write_text(body, encoding="utf-8")
        (mat / "S_20261101" / "설교_고린도후서4.md").write_text(body, encoding="utf-8")
        (mat / "고린도후서_메모.md").write_text("---\nprivate: true\n---\n" + body, encoding="utf-8")
        (mat / "B_고린도후서_공개.md").write_text("## 4:7-12\n공개 주석\n", encoding="utf-8")
        self.cfg.write_text(json.dumps({"materials_dirs": [str(mat)]}), encoding="utf-8")
        self.init()
        self.arch("advance_stage", "--to", "4", "--confirmed-by-preacher")
        _, r = run(dsc_collect, ["commentary", "--week-dir", str(self.wd), "--ref", REF, "--config", str(self.cfg)])
        self.assertEqual(r["counts"]["commentary"], 1)
        for f in (self.wd / "00_수집/주석").iterdir():
            self.assertNotIn("비밀", f.read_text(encoding="utf-8"))

    def test_symlinked_collect_dir_refused(self):
        self.wd.mkdir()
        outside = self.root / "outside"
        outside.mkdir()
        (self.wd / "00_수집").symlink_to(outside)
        with self.assertRaises(dsc_collect.Refused):
            dsc_collect.safe_write(self.wd / "00_수집", "passage.json", "x")
        self.assertEqual(list(outside.iterdir()), [])

    def test_planted_tmp_symlink_not_followed(self):
        base = self.wd / "00_수집"
        base.mkdir(parents=True)
        victim = self.root / "victim.txt"
        victim.write_text("원래", encoding="utf-8")
        (base / "passage.json.tmp").symlink_to(victim)
        dsc_collect.safe_write(base, "passage.json", "새 내용")
        self.assertEqual(victim.read_text(encoding="utf-8"), "원래")

    def test_pericopes_missing_last_chapter(self):
        p = B.parse_ref("고린도후서 4-5")
        nk = {4: {"verses": {1: "가", 2: "나"}, "headings": [(1, "제목")]}}
        self.assertEqual(dsc_collect.pericopes(p, nk), {})

    def test_odd_stage_values(self):
        self.init()
        pj = self.wd / "progress.json"
        for bad in (4, "7a", " 4 "):
            st = json.loads(pj.read_text(encoding="utf-8"))
            st["current_stage"] = bad
            pj.write_text(json.dumps(st), encoding="utf-8")
            self.assertEqual(dsc_collect.read_stage(self.wd), dsc_archive.norm_stage(bad))
            _, r = self.arch("status")
            self.assertEqual(r["status"], "ok")
        for bad in ("7", None, True, "4B"):
            st = json.loads(pj.read_text(encoding="utf-8"))
            st["current_stage"] = bad
            pj.write_text(json.dumps(st), encoding="utf-8")
            with self.assertRaises(dsc_collect.Refused):
                dsc_collect.read_stage(self.wd)
            _, r = self.arch("advance_stage", "--to", "9", "--confirmed-by-preacher")
            self.assertEqual(r["status"], "refused")

    def test_init_validates_input(self):
        _, r = self.arch("init", "--ref", "없는책 1:1", "--sermon-date", "2026-11-08")
        self.assertEqual(r["status"], "refused")
        _, r = self.arch("init", "--ref", REF, "--sermon-date", "11/08")
        self.assertEqual(r["status"], "refused")

    def test_init_week_must_sit_under_vault_root(self):
        # M6: 감독이 vault_root 아래에 output/을 덧붙여 작업창이 주간을 못 찾음
        self.cfg.write_text(json.dumps({"vault_root": str(self.root)}), encoding="utf-8")
        wrong = self.root / "output" / "S_20261108"
        _, r = run(dsc_archive, ["init", "--week-dir", str(wrong), "--ref", REF,
                                 "--sermon-date", "2026-11-08", "--config", str(self.cfg)])
        self.assertEqual(r["status"], "refused")
        self.assertFalse(wrong.exists())
        _, r = self.init()
        self.assertEqual(r["status"], "ok")
        # 설정은 NFD로 적혀 있어도 같은 폴더면 받습니다
        import unicodedata
        kr = self.root / unicodedata.normalize("NFC", "주간묵상")
        kr.mkdir()
        self.cfg.write_text(json.dumps({"vault_root": unicodedata.normalize("NFD", str(kr))}), encoding="utf-8")
        _, r = run(dsc_archive, ["init", "--week-dir", str(kr / "S_20261115"), "--ref", REF,
                                 "--sermon-date", "2026-11-15", "--config", str(self.cfg)])
        self.assertEqual(r["status"], "ok")

    def test_privacy_no_week_found_fails(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            with contextlib_redirect_stderr():
                code = check_privacy.main([str(self.root / "없는곳")])
        self.assertNotEqual(code, 0)


def contextlib_redirect_stderr():
    from contextlib import redirect_stderr
    return redirect_stderr(io.StringIO())


class TestFreeze(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.wd = Path(tempfile.mkdtemp()) / "S_20261108"
        self.col = self.wd / "00_수집"
        self.col.mkdir(parents=True)
        self.prev = {"reference": "고린도후서 4:7", "version": 3, "clauses": [{"id": "4.7a", "text": "옛"}]}
        (self.col / "passage.json").write_text(json.dumps(self.prev, ensure_ascii=False), encoding="utf-8")

    def result(self, ref="고린도후서 4:7"):
        return {"reference": ref, "clauses": [{"id": "4.7a", "text": "새"}, {"id": "4.7b", "text": "새2"}], "notes": []}

    def notes(self, obj):
        (self.wd / "03_원어관찰.json").write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")

    def test_no_notes_regenerates(self):
        r = self.result()
        C.freeze_clauses(C.freeze_check(self.wd, self.col), r)
        self.assertEqual(len(r["clauses"]), 2)
        self.assertEqual(r["version"], 4)

    def test_notes_same_ref_freezes(self):
        self.notes({"clauses": [{"id": "4.7a", "observe": "기록"}]})
        r = self.result()
        C.freeze_clauses(C.freeze_check(self.wd, self.col), r)
        self.assertEqual(r["clauses"], self.prev["clauses"])
        self.assertTrue(r["clauses_frozen"])

    def test_orphan_notes_count_as_written(self):
        self.notes({"clauses": [], "_orphans": [{"id": "4.9a", "apply": "기록"}]})
        r = self.result()
        C.freeze_clauses(C.freeze_check(self.wd, self.col), r)
        self.assertTrue(r.get("clauses_frozen"))

    def test_changed_ref_keeps_new_and_warns(self):
        self.notes({"clauses": [{"id": "4.7a", "observe": "기록"}]})
        r = self.result("고린도후서 5:1")
        C.freeze_clauses(C.freeze_check(self.wd, self.col), r)
        self.assertNotIn("clauses_frozen", r)
        self.assertTrue(r["notes"])

    def test_unreadable_previous_with_notes_refused(self):
        self.notes({"clauses": [{"id": "4.7a", "observe": "기록"}]})
        (self.col / "passage.json").write_text("{깨짐", encoding="utf-8")
        with self.assertRaises(C.Refused):
            C.freeze_check(self.wd, self.col)
        (self.col / "passage.json").unlink()
        with self.assertRaises(C.Refused):
            C.freeze_check(self.wd, self.col)


def syn_passage():
    return {"reference": "고린도후서 4:7-8", "book": {"testament": "NT"},
            "original": {"NA28": {"name": "NA28", "verses": [
                {"ref": "4:7", "text": "Ἔχομεν δὲ τὸν θησαυρὸν τοῦτον ἐν ὀστρακίνοις σκεύεσιν,"},
                {"ref": "4:8", "text": "ἐν παντὶ θλιβόμενοι ἀλλ’ οὐ στενοχωρούμενοι,"}]}},
            "translations": {"NKT": {"verses": [{"ref": "4:7", "text": "그런데 우리는 이 보물을 질그릇에 담아 가지고 있어요."}]},
                             "ESV": {"verses": [{"ref": "4:7", "text": "But we have this treasure in jars of clay,"}]}}}


def syn_draft():
    return {"verses": [{"ref": "4:7", "title": "질그릇", "main_verbs": ["Ἔχομεν"],
        "clauses": [{"id": "4.7a", "label": "main verb", "family": "main", "indent": 0,
                     "words": [{"g": "Ἔχομεν", "p": "동직.현능.1복"}, {"g": "δὲ", "p": "접"}, {"g": "τὸν", "p": "관.목.남단"},
                               {"g": "θησαυρὸν", "p": "명.목.남단"}, {"g": "τοῦτον", "p": "대지시.목.남단"}],
                     "literal": "우리가 가지고 있다 / 그런데 / 이 보물을", "nk": "우리는 이 보물을", "esv": "But we have this treasure"},
                    {"id": "4.7b", "label": "prep phr", "family": "prep", "indent": 1,
                     "words": [{"g": "ἐν", "p": "전(+여)"}, {"g": "ὀστρακίνοις", "p": "형.여.중복"}, {"g": "σκεύεσιν,", "p": "명.여.중복"}],
                     "literal": "~안에 / 질그릇들", "nk": "질그릇에 담아 가지고 있어요.", "esv": "in jars of clay,"}],
        "chain": [{"verb": "Ἔχομεν", "note": "현재 — 지금 가지고 있음"}],
        "commentary": ["주동사는 Ἔχομεν이다.", "전치사구가 그릇을 밝힌다."], "variant": ""}]}


class TestSyntax(unittest.TestCase):
    def test_valid_draft_passes(self):
        import dsc_syntax as SX
        errs, warns, out = SX.check(syn_draft(), syn_passage())
        self.assertEqual(errs, [])
        self.assertEqual(warns, [])
        self.assertEqual(out[0]["ref"], "4:7")

    def test_fabricated_or_missing_greek_fails(self):
        import dsc_syntax as SX
        d = syn_draft()
        d["verses"][0]["clauses"][1]["words"].pop()               # 낱말 하나 빠짐
        self.assertTrue(any("수집본" in e for e in SX.check(d, syn_passage())[0]))
        d = syn_draft()
        d["verses"][0]["clauses"][0]["words"][3]["g"] = "θησαυρόν"   # 악센트가 바뀜
        self.assertTrue(SX.check(d, syn_passage())[0])

    def test_translation_not_in_source_fails(self):
        import dsc_syntax as SX
        d = syn_draft()
        d["verses"][0]["clauses"][0]["nk"] = "우리는 이 보배를"       # 새한글이 아닌 말(개역개정식)
        self.assertTrue(any("새한글" in e for e in SX.check(d, syn_passage())[0]))
        d = syn_draft()
        d["verses"][0]["clauses"][0]["esv"] = "We hold this treasure"
        self.assertTrue(any("ESV" in e for e in SX.check(d, syn_passage())[0]))

    def test_shape_errors_and_parse_warnings(self):
        import dsc_syntax as SX
        d = syn_draft()
        d["verses"][0]["ref"] = "4:9"
        self.assertTrue(any("범위 밖" in e for e in SX.check(d, syn_passage())[0]))
        d = syn_draft()
        c = d["verses"][0]["clauses"][0]
        c["id"], c["family"], c["indent"] = "4.8a", "nope", 7
        errs = SX.check(d, syn_passage())[0]
        self.assertGreaterEqual(len(errs), 3)
        d = syn_draft()
        d["verses"][0]["clauses"][0]["words"][0]["p"] = "verb pres"
        d["verses"][0]["commentary"] = ["하나뿐"]
        errs, warns, _ = SX.check(d, syn_passage())
        self.assertEqual(errs, [])
        self.assertEqual(len(warns), 2)

    def test_hebrew_ignores_cantillation_and_maqaf(self):
        import dsc_syntax as SX
        p = {"book": {"testament": "OT"}, "translations": {},
             "original": {"BHS": {"name": "BHS", "verses": [{"ref": "23:1", "text": "מִזְמ֥וֹר לְדָוִ֑ד יְהוָ֥ה רֹ֝עִ֗י לֹ֣א אֶחְסָֽר׃"}]}}}
        d = {"verses": [{"ref": "23:1", "clauses": [
            {"id": "23.1a", "label": "pendent nom", "family": "etc", "indent": 0,
             "words": [{"g": "מִזְמוֹר", "p": "명.남단.절대"}, {"g": "לְדָוִד", "p": "전(לְ)+고유"}]},
            {"id": "23.1b", "label": "pred nom", "family": "etc", "indent": 0,
             "words": [{"g": "יְהוָה", "p": "고유"}, {"g": "רֹעִי", "p": "분칼.능.남단?"}]},
            {"id": "23.1c", "label": "main verb", "family": "main", "indent": 0,
             "words": [{"g": "לֹא", "p": "부정어"}, {"g": "אֶחְסָר׃", "p": "동칼.미완.1공단"}]}],
            "commentary": ["가", "나"]}]}
        errs, warns, _ = SX.check(d, p)
        self.assertEqual(errs, [])

    def test_install_via_collector_merges_and_removes_draft(self):
        import tempfile
        wd = Path(tempfile.mkdtemp()) / "S_20261108"
        col = wd / "00_수집"
        col.mkdir(parents=True)
        (col / "passage.json").write_text(json.dumps(syn_passage(), ensure_ascii=False), encoding="utf-8")
        (col / "구문분석_초안.json").write_text(json.dumps(syn_draft(), ensure_ascii=False), encoding="utf-8")
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = C.main(["syntax", "--week-dir", str(wd)])
        r = json.loads(buf.getvalue())
        self.assertEqual((code, r["status"]), (0, "ok"), r)
        self.assertFalse((col / "구문분석_초안.json").exists())
        sx = json.loads((col / "syntax.json").read_text(encoding="utf-8"))
        self.assertEqual([v["ref"] for v in sx["verses"]], ["4:7"])
        self.assertNotIn("Ἔχομεν", buf.getvalue())                 # 본문 글자를 출력하지 않음
        bad = syn_draft()
        bad["verses"][0]["clauses"][0]["nk"] = "지어낸 문장"
        (col / "구문분석_초안.json").write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
        before = (col / "syntax.json").read_text(encoding="utf-8")
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = C.main(["syntax", "--week-dir", str(wd)])
        self.assertEqual(code, 1)
        self.assertEqual((col / "syntax.json").read_text(encoding="utf-8"), before)
        self.assertTrue((col / "구문분석_초안.json").exists())


class TestSyntaxReview(unittest.TestCase):
    def errs(self, d, p=None):
        import dsc_syntax as SX
        return SX.check(d, p or syn_passage())[0]

    def words(self, d):
        return d["verses"][0]["clauses"][0]["words"]

    def test_gap_cannot_smuggle_text(self):
        d = syn_draft()
        self.words(d).append({"g": "ἐστιν ὁ θεός", "gap": True})
        self.assertTrue(self.errs(d))
        d = syn_draft()
        self.words(d).append({"g": "⟨ ἀπαγγέλλομεν ⟩", "gap": True, "p": "3절에서"})
        self.assertEqual(self.errs(d), [])

    def test_word_boundaries_enforced(self):
        d = syn_draft()                                          # 절 전체를 한 낱말로
        d["verses"][0]["clauses"] = [dict(d["verses"][0]["clauses"][0],
                                          words=[{"g": "Ἔχομεν δὲ τὸν θησαυρὸν τοῦτον ἐν ὀστρακίνοις σκεύεσιν,"}])]
        self.assertTrue(self.errs(d))
        d = syn_draft()                                          # 낱말 가운데를 쪼갬
        self.words(d)[0:1] = [{"g": "Ἔχο"}, {"g": "μεν"}]
        self.assertTrue(self.errs(d))
        for bad in ("", "—()", " Ἔχομεν"):
            d = syn_draft()
            self.words(d)[0]["g"] = bad
            self.assertTrue(self.errs(d), bad)
        import dsc_syntax as SX                                  # 문장부호를 끼워도 화면에는 수집본 글자만
        d = syn_draft()
        self.words(d)[0]["g"] = "Ἔχο-μεν"
        errs, _, out = SX.check(d, syn_passage())
        self.assertEqual((errs, out[0]["clauses"][0]["words"][0]["g"]), ([], "Ἔχομεν"))

    def test_source_letters_replace_draft_punctuation(self):
        import dsc_syntax as SX
        d = syn_draft()
        d["verses"][0]["clauses"][1]["words"][2]["g"] = "σκεύεσιν;"     # 물음표(;)를 붙임
        errs, _, out = SX.check(d, syn_passage())
        self.assertEqual(errs, [])
        self.assertEqual(out[0]["clauses"][1]["words"][2]["g"], "σκεύεσιν,")

    def test_main_verbs_and_chain_must_be_in_verse(self):
        d = syn_draft()
        d["verses"][0]["main_verbs"] = ["ἐγένετο"]
        self.assertTrue(self.errs(d))
        d = syn_draft()
        d["verses"][0]["chain"] = [{"verb": "ἐγένετο", "note": "x"}]
        self.assertTrue(self.errs(d))

    def test_main_verb_drops_source_punctuation_keeps_elision(self):
        # M6: 수집본 「σκεύεσιν,」를 주동사로 쓰면 쉼표까지 화면·생성본에 나옴
        import dsc_syntax as SX
        d = syn_draft()
        d["verses"][0]["main_verbs"] = ["σκεύεσιν"]
        d["verses"][0]["chain"] = [{"verb": "σκεύεσιν,", "note": "x"}]
        errs, _, out = SX.check(d, syn_passage())
        self.assertEqual(errs, [])
        self.assertEqual(out[0]["main_verbs"], ["σκεύεσιν"])
        self.assertEqual(out[0]["chain"][0]["verb"], "σκεύεσιν")
        src = [("ἀλλ’", None)]
        self.assertEqual(SX.source_token("ἀλλ’", src), "ἀλλ’")

    def test_malformed_types_do_not_crash(self):
        for mut in ({"id": ["x"]}, {"nk": ["x"]}, {"esv": 5}, {"words": "x"}, {"indent": True}):
            d = syn_draft()
            d["verses"][0]["clauses"][0].update(mut)
            self.assertTrue(self.errs(d), mut)

    def test_translation_spacing_and_verse_window(self):
        d = syn_draft()
        d["verses"][0]["clauses"][0]["esv"] = "Butwe havethis"
        self.assertTrue(self.errs(d))
        d = syn_draft()
        d["verses"][0]["clauses"][0]["esv"] = "e"                  # 낱말 가운데 한 글자
        self.assertTrue(self.errs(d))
        p = syn_passage()
        p["translations"]["ESV"]["verses"] += [{"ref": "4:8", "text": "x"}, {"ref": "4:9", "text": "far away words"}]
        p["original"]["NA28"]["verses"].append({"ref": "4:9", "text": "z"})
        d = syn_draft()
        d["verses"][0]["clauses"][0]["esv"] = "far away words"     # 두 절 떨어진 ESV
        self.assertTrue(self.errs(d, p))

    def test_messages_do_not_print_bible_text(self):
        d = syn_draft()
        self.words(d)[3]["g"] = "θησαυρόν"
        d["verses"][0]["clauses"][0]["nk"] = "지어낸 새한글"
        msg = " ".join(self.errs(d))
        for t in ("θησαυρ", "Ἔχομεν", "지어낸"):
            self.assertNotIn(t, msg)

    def test_render_keeps_legacy_and_orphan_notes(self):
        import tempfile
        wd = Path(tempfile.mkdtemp()) / "S_20261108"
        (wd / "00_수집").mkdir(parents=True)
        dsc_archive.main(["init", "--week-dir", str(wd), "--ref", REF, "--sermon-date", "2026-11-08"]) if False else None
        st = {"dsc_version": "1.0.0", "text": REF, "sermon_date": "2026-11-08", "current_stage": "3", "stage_entered": {}}
        (wd / "progress.json").write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
        (wd / "03_원어관찰.json").write_text(json.dumps({
            "verses": [{"ref": "4:7", "note": "절 노트"}, {"ref": "4:8", "note": "  "}],
            "clauses": [{"id": "4.7a", "observe": "예전 관찰"}],
            "_orphans": [{"id": "4.9b", "apply": "예전 짝 없는 적용"}, {"ref": "5:1", "note": "옮겨 간 노트"}, "깨짐"]},
            ensure_ascii=False), encoding="utf-8")
        r = dsc_archive.render_stage3(wd, {})
        text = Path(r["saved"][0]).read_text(encoding="utf-8")
        for want in ("절 노트", "예전 관찰", "예전 짝 없는 적용", "옮겨 간 노트", "## 짝 없는 기록"):
            self.assertIn(want, text)
        self.assertNotIn("## 고린도후서 4:8", text)                  # 빈 노트 절은 넣지 않음

    def test_split_notes_tolerates_bad_shapes(self):
        recs, olds = dsc_archive.split_notes({"verses": None, "_orphans": [{"observe": 5}], "clauses": "x"})
        self.assertEqual((recs, olds), ({}, []))


if __name__ == "__main__":
    unittest.main()
