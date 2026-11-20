#!/usr/bin/env python3
"""작업창 버튼 일 시험 (M5). 진짜 claude 대신 가짜 실행 파일로 인자·환경·권한 설정을 확인합니다."""
import hashlib
import json
import os
import shutil
import stat
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_server import Live, make_week  # noqa: E402
import gate  # noqa: E402

FAKE = r'''#!/usr/bin/env python3
import json, os, sys, time
args = sys.argv[1:]
rec = {"args": args, "stdin": sys.stdin.read(), "cwd": os.getcwd(),
       "api_key": "ANTHROPIC_API_KEY" in os.environ}
s = args[args.index("--settings") + 1]
rec["settings"] = json.load(open(s))
rec["prompt"] = open(args[args.index("--append-system-prompt-file") + 1]).read()
mode = open(os.environ.get("FAKE_MODE_FILE", "/dev/null")).read().strip() if os.environ.get("FAKE_MODE_FILE") else ""
log = os.environ["FAKE_LOG"]
with open(log, "a") as f:
    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
if mode == "sleep":
    time.sleep(5)
if mode == "error":
    print(json.dumps({"is_error": True, "subtype": "error_max_turns", "result": ""})); sys.exit(1)
if mode == "gone" and any(a.startswith("--resume") for a in args):
    sys.stderr.write("No conversation found with session ID: x\n"); sys.exit(1)
if mode == "garbage":
    print("not json"); sys.exit(1)
sid = "00000000-0000-4000-8000-%012d" % sum(1 for _ in open(log))
print(json.dumps({"is_error": False, "result": "「질그릇」은 본문 어디에서 다시 나옵니까?", "session_id": sid,
                  "total_cost_usd": 0.01, "permission_denials": []}))
'''


def SID(n):
    return "00000000-0000-4000-8000-%012d" % n


class JobBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="dscjob_"))
        self.vault = self.tmp / "vault"
        self.vault.mkdir()
        self.wd = make_week(self.vault, stage="2")
        (self.wd / "02_동행일지_2026-11-03_고린도후서4_7-8.md").write_text("---\nstage: 2\n---\n설교자 원문", encoding="utf-8")
        fake = self.tmp / "claude"
        fake.write_text(FAKE, encoding="utf-8")
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
        self.log = self.tmp / "calls.jsonl"
        self.mode = self.tmp / "mode"
        self.mode.write_text("", encoding="utf-8")
        os.environ.update({"FAKE_LOG": str(self.log), "FAKE_MODE_FILE": str(self.mode), "ANTHROPIC_API_KEY": "sk-test"})
        self.live = Live(self.vault)
        self.live.httpd.jobs.cfg["claude_bin"] = str(fake)

    def tearDown(self):
        self.live.stop()
        for k in ("FAKE_LOG", "FAKE_MODE_FILE", "ANTHROPIC_API_KEY"):
            os.environ.pop(k, None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def calls(self):
        return [json.loads(x) for x in self.log.read_text(encoding="utf-8").splitlines()] if self.log.exists() else []

    def ask(self, q="ὀστρακίνοις는 어디에 또 나옵니까?", verse="4:7"):
        return self.live.req("POST", "/api/weeks/S_20261108/ask", {"question": q, "verse": verse})

    def set_stage(self, s):
        p = self.wd / "progress.json"
        st = json.loads(p.read_text(encoding="utf-8"))
        st["current_stage"] = s
        p.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")

    def snapshot(self):
        return {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in self.wd.iterdir()
                if f.is_file() and f.name[:2].isdigit()}


class TestAsk(JobBase):
    def test_round_trip_logged_and_session_kept(self):
        before = self.snapshot()
        code, d, _ = self.ask()
        self.assertEqual(code, 200, d)
        self.assertIn("질그릇", d["answer"])
        [c] = self.calls()
        self.assertEqual(c["cwd"], os.path.realpath(self.wd))
        self.assertIn("4:7", c["stdin"])
        self.assertIn("ὀστρακίνοις", c["stdin"])
        self.assertFalse(c["api_key"])
        a = c["args"]
        self.assertEqual(a[a.index("--tools") + 1], "Read,Glob,Grep")
        self.assertEqual(a[a.index("--permission-mode") + 1], "dontAsk")
        self.assertIn("Read(./**)", a)
        self.assertNotIn("--resume", a)
        log = [json.loads(x) for x in (self.wd / "00_수집" / "ask_log.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(log[0]["question"], "ὀστρακίνοις는 어디에 또 나옵니까?")
        self.assertEqual(log[0]["stage"], "2")
        st = json.loads((self.wd / "progress.json").read_text(encoding="utf-8"))
        self.assertEqual(st["session_ids"], {"2": SID(1)})
        self.ask("두 번째")
        self.assertEqual(self.calls()[1]["args"][-1], "--resume=" + SID(1))
        self.assertIn("--safe-mode", self.calls()[1]["args"])
        self.assertEqual(self.snapshot(), before)            # 설교자 파일(0N_*.md 등)은 그대로
        hist = self.live.req("GET", "/api/weeks/S_20261108/ask")[1]["items"]
        self.assertEqual(len(hist), 2)

    def test_new_stage_new_session(self):
        self.ask()
        self.set_stage("4")
        self.ask()
        self.assertFalse(any(a.startswith("--resume") for a in self.calls()[1]["args"]))

    def test_stage_permissions(self):
        for s in ("0", "1", "2", "3", "4", "7A", "7B", "9"):
            self.set_stage(s)
            self.ask()
            deny = self.calls()[-1]["settings"]["permissions"]["deny"]
            for t in ("Write", "Edit", "Bash", "WebFetch"):
                self.assertIn(t, deny)
            for t in ("Read", "Grep", "Glob"):
                self.assertIn("%s(./07A_*)" % t, deny, s)
                self.assertIn("%s(./*묵상종합*)" % t, deny, s)
                self.assertIn("%s(./00_수집/ask_log.jsonl)" % t, deny, s)
                closed = "%s(./00_수집/주석/**)" % t in deny
                self.assertEqual(closed, s in ("0", "1", "2", "3", "7A"), (s, t))
            self.assertTrue(self.calls()[-1]["settings"]["disableAllHooks"])

    def test_timeout_and_error_and_garbage(self):
        self.live.httpd.jobs.ask_timeout = 1
        self.mode.write_text("sleep", encoding="utf-8")
        code, d, _ = self.ask()
        self.assertEqual(code, 504)
        self.mode.write_text("error", encoding="utf-8")
        code, d, _ = self.ask()
        self.assertEqual(code, 502)
        self.assertIn("error_max_turns", d["error"])
        self.mode.write_text("garbage", encoding="utf-8")
        self.assertEqual(self.ask()[0], 502)
        log = (self.wd / "00_수집" / "ask_log.jsonl").read_text(encoding="utf-8")
        self.assertEqual(log.count('"status": "error"'), 3)          # 시간 초과도 남깁니다
        self.assertFalse(self.live.httpd.jobs.busy.locked())

    def test_one_at_a_time(self):
        self.live.httpd.jobs.busy.acquire()
        try:
            self.assertEqual(self.ask()[0], 429)
        finally:
            self.live.httpd.jobs.busy.release()
        self.mode.write_text("sleep", encoding="utf-8")
        out = []
        ts = [threading.Thread(target=lambda: out.append(self.ask()[0])) for _ in range(3)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(sorted(out), [200, 429, 429])

    def test_bad_inputs(self):
        self.assertEqual(self.ask(q="   ")[0], 400)
        self.assertEqual(self.ask(q="가" * 1001)[0], 413)
        self.assertEqual(self.ask(verse="../x")[0], 400)
        self.assertEqual(self.live.req("POST", "/api/weeks/S_20261108/ask", {"question": "x"}, token=False)[0], 401)
        make_week(self.vault, "S_20261101", legacy=True)
        self.assertEqual(self.live.req("POST", "/api/weeks/S_20261101/ask", {"question": "x"})[0], 403)
        self.assertEqual(self.calls(), [])

    def test_missing_binary(self):
        self.live.httpd.jobs.cfg["claude_bin"] = str(self.tmp / "없음")
        os.environ["PATH"], old = "/nonexistent", os.environ["PATH"]
        home = os.environ.get("HOME")
        os.environ["HOME"] = str(self.tmp)
        try:
            code, d, _ = self.ask()
        finally:
            os.environ["PATH"] = old
            os.environ["HOME"] = home
        self.assertEqual(code, 503)


class TestTools(JobBase):
    def test_recollect_needs_confirm_and_respects_freeze(self):
        self.assertEqual(self.live.req("POST", "/api/weeks/S_20261108/recollect", {})[0], 400)
        (self.wd / "03_원어관찰.json").write_text(json.dumps({"verses": [{"ref": "4:7", "note": "기록"}]}), encoding="utf-8")
        (self.wd / "00_수집" / "passage.json").write_text("{깨짐", encoding="utf-8")
        code, d, _ = self.live.req("POST", "/api/weeks/S_20261108/recollect", {"confirm": True})
        self.assertEqual(code, 200, d)
        self.assertEqual(d["status"], "refused")
        self.assertEqual((self.wd / "00_수집" / "passage.json").read_text(encoding="utf-8"), "{깨짐")

    def test_check_reports_without_private_text(self):
        (self.wd / "07A_자기적용_2026-11-06_고린도후서4_7-8.md").write_text(
            "---\nprivate: true\ntags: [private]\n---\n오늘 나는 질그릇처럼 깨어진 마음을 숨기고 있었습니다.\n", encoding="utf-8")
        (self.wd / "08_원고점검_2026-11-07_고린도후서4_7-8.md").write_text(
            "---\nstage: 8\n---\n오늘 나는 질그릇처럼 깨어진 마음을 숨기고 있었습니다.\n", encoding="utf-8")
        code, d, _ = self.live.req("POST", "/api/weeks/S_20261108/check", {})
        self.assertEqual(code, 200, d)
        self.assertGreaterEqual(d["privacy"]["errors"], 1)
        self.assertNotIn("깨어진 마음", json.dumps(d, ensure_ascii=False))


class TestReview(JobBase):
    def test_resume_gone_retries_fresh_and_saves_new_session(self):
        self.ask()
        self.mode.write_text("gone", encoding="utf-8")
        code, d, _ = self.ask("다시")
        self.assertEqual(code, 200, d)
        c = self.calls()
        self.assertTrue(c[1]["args"][-1].startswith("--resume="))
        self.assertFalse(any(a.startswith("--resume") for a in c[2]["args"]))
        st = json.loads((self.wd / "progress.json").read_text(encoding="utf-8"))
        self.assertEqual(st["session_ids"]["2"], SID(3))

    def test_injected_session_and_model_ignored(self):
        p = self.wd / "progress.json"
        st = json.loads(p.read_text(encoding="utf-8"))
        st["session_ids"] = {"2": "--add-dir=/etc"}
        p.write_text(json.dumps(st), encoding="utf-8")
        self.live.httpd.jobs.cfg["ask_model"] = "--dangerously-skip-permissions"
        self.ask()
        a = self.calls()[-1]["args"]
        self.assertFalse(any(x.startswith("--resume") or x.startswith("--add-dir") for x in a))
        self.assertNotIn("--dangerously-skip-permissions", a)
        self.assertIn("--model=sonnet", a)

    def test_7A_text_not_logged_and_history_by_stage(self):
        self.ask("2단계 질문")
        self.set_stage("7A")
        code, d, _ = self.ask("나의 숨긴 마음에 대해")
        self.assertEqual(code, 200)
        self.assertIn("질그릇", d["answer"])                     # 화면에는 보여 줌
        log = (self.wd / "00_수집" / "ask_log.jsonl").read_text(encoding="utf-8")
        self.assertNotIn("숨긴 마음", log)
        self.assertEqual(self.live.req("GET", "/api/weeks/S_20261108/ask")[1]["items"], [])
        self.set_stage("2")
        items = self.live.req("GET", "/api/weeks/S_20261108/ask")[1]["items"]
        self.assertEqual([i["question"] for i in items], ["2단계 질문"])

    def test_private_files_and_stage3_setting_denied(self):
        import unicodedata
        (self.wd / unicodedata.normalize("NFD", "08_원고점검_2026-11-07_고린도후서4_7-8.md")).write_text(
            "---\nprivate: true\n---\n비공개", encoding="utf-8")
        (self.wd / "Stage4_x_1차청중_페르소나.html").write_text(
            '<!doctype html><meta name="dsc-private" content="true">', encoding="utf-8")
        self.set_stage("8")
        self.live.httpd.jobs.cfg["stage3_private"] = True
        self.ask()
        c = self.calls()[-1]
        deny = c["settings"]["permissions"]["deny"]
        for want in ("Read(./08_원고점검_2026-11-07_고린도후서4_7-8.md)",
                     "Read(./" + unicodedata.normalize("NFD", "08_원고점검_2026-11-07_고린도후서4_7-8.md") + ")",
                     "Read(./Stage4_x_1차청중_페르소나.html)", "Read(./03_원어관찰.json)", "Grep(./03_원어관찰_*)"):
            self.assertIn(want, deny)
        self.assertNotIn("03_원어관찰.json", c["prompt"])
        self.assertNotIn("Read(./02_동행일지_2026-11-03_고린도후서4_7-8.md)", deny)

    def test_notes_blocked_while_recollecting(self):
        self.live.httpd.ws.recollecting.add("S_20261108")
        r = self.live.req("PUT", "/api/weeks/S_20261108/notes/4:7", {"note": "x", "base": ""})
        self.assertEqual(r[0], 423)

    def test_ask_without_passage_still_runs(self):
        (self.wd / "00_수집" / "passage.json").unlink()
        self.assertEqual(self.ask()[0], 200)

    def test_env_drops_provider_overrides(self):
        e = gate.clean_env({"ANTHROPIC_AUTH_TOKEN": "t", "ANTHROPIC_BASE_URL": "u", "CLAUDE_CODE_USE_BEDROCK": "1",
                            "ANTHROPIC_MODEL": "m", "HOME": "/h"})
        self.assertEqual(e, {"HOME": "/h"})

    def test_timeout_kills_process_group(self):
        script = self.tmp / "spawn.py"
        marker = self.tmp / "child.pid"
        script.write_text("import subprocess,sys,time\n"
                          "c=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'])\n"
                          "open(%r,'w').write(str(c.pid));time.sleep(30)\n" % str(marker), encoding="utf-8")
        import jobs
        with self.assertRaises(jobs.JobError):
            jobs.run([sys.executable, str(script)], self.tmp, "", 1.5)
        pid = int(marker.read_text())
        time.sleep(0.3)
        with self.assertRaises(ProcessLookupError):
            os.kill(pid, 0)


class TestGate(unittest.TestCase):
    def test_command_is_argument_list_without_shell_and_stdin_question(self):
        a = gate.command("/bin/claude", "/t/s.json", "/t/p.md")
        self.assertIsInstance(a, list)
        self.assertNotIn("--dangerously-skip-permissions", a)
        self.assertEqual(a[a.index("--setting-sources") + 1], "project")
        self.assertIn("--strict-mcp-config", a)

    def test_env_drops_keys(self):
        e = gate.clean_env({"ANTHROPIC_API_KEY": "x", "CLAUDECODE": "1", "PATH": "/bin"})
        self.assertEqual(e, {"PATH": "/bin"})


if __name__ == "__main__":
    unittest.main()
