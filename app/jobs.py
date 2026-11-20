"""작업창 버튼 일 — 감독에게 묻기 · 본문 다시 수집 · 진행 상황 점검

- 한 번에 하나만 돕니다(서버 전체). 두 번째 요청은 429.
- 모든 외부 실행은 셸 없이 인자 목록으로 합니다. 질문은 stdin으로 넘깁니다.
  시간이 넘으면 프로세스 묶음 전체(자식 포함)를 끝냅니다.
- 묻기 결과는 00_수집/ask_log.jsonl에 서버만 덧붙여 씁니다. 감독이 다시 들어올 때 읽습니다.
  Stage 7A 자기적용의 질문·답은 글자를 남기지 않습니다(비공개). 화면에만 보여 줍니다.
- 버튼은 0N_*.md 같은 설교자 파일을 쓰지 않습니다. claude -p에는 쓰기 도구가 없습니다.
"""
import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import gate

SCRIPTS = Path(__file__).resolve().parents[1] / "skills/dwelling-sermon-coach/scripts"
MAX_Q = 1000
TAIL_BYTES = 256 * 1024
RESUME_GONE = ("No conversation found", "valid session")


class JobError(Exception):
    def __init__(self, code, msg):
        super().__init__(msg)
        self.code, self.msg = code, msg


def run(args, cwd, stdin_text, timeout, env=None):
    """셸 없이 실행합니다. 시간이 넘으면 프로세스 묶음 전체를 끝내고 JobError(504)."""
    if timeout <= 0:
        raise JobError(504, "시간이 다 되어 실행하지 않았습니다")
    try:
        p = subprocess.Popen(args, cwd=str(cwd), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, env=env, shell=False, start_new_session=True,
                             text=True, encoding="utf-8", errors="replace")
    except OSError as e:
        raise JobError(502, "실행하지 못했습니다: %s" % type(e).__name__)
    try:
        out, err = p.communicate(stdin_text, timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except OSError:
            pass
        p.communicate()
        raise JobError(504, "%d초 안에 끝나지 않아 멈췄습니다" % round(timeout))
    return subprocess.CompletedProcess(args, p.returncode, out, err)


class Jobs:
    def __init__(self, ws, cfg, ask_timeout=60, collect_timeout=240):
        self.ws, self.cfg = ws, cfg
        self.ask_timeout, self.collect_timeout = ask_timeout, collect_timeout
        self.busy = threading.Lock()
        self.A = ws.A

    # ------------------------------------------------------------ 공통
    def one_at_a_time(self):
        if not self.busy.acquire(blocking=False):
            raise JobError(429, "다른 버튼 일을 처리하고 있습니다. 끝난 뒤 다시 누르십시오")

    def config_args(self):
        c = self.cfg.get("_config_path")
        return ["--config", str(c)] if c else []

    # ------------------------------------------------------------ 감독에게 묻기
    def ask(self, wid, body):
        q = body.get("question")
        if not isinstance(q, str) or not q.strip():
            raise JobError(400, "질문을 적어 주십시오")
        if len(q) > MAX_Q:
            raise JobError(413, "질문은 %d자 이하로 적어 주십시오" % MAX_Q)
        ref = body.get("verse")
        if ref is not None and (not isinstance(ref, str) or not self.ws.REF_RX.match(ref)):
            raise JobError(400, "절 표시는 '장:절' 형식이어야 합니다")
        wd = self.ws.week_dir(wid)
        st = self.ws.v1(wd)
        stage = self.A.norm_stage(st.get("current_stage"))
        binary = gate.claude_bin(self.cfg)
        if not binary:
            raise JobError(503, "claude 실행 파일을 찾지 못했습니다. 설정 claude_bin을 확인하십시오")
        context = ""
        if ref:
            try:                                            # 절 맥락은 덧붙임일 뿐, 없어도 묻습니다
                pas = json.loads((wd / "00_수집" / "passage.json").read_text(encoding="utf-8"))
                ov = next(iter((pas.get("original") or {}).values()), {}) or {}
                text = next((v.get("text", "") for v in ov.get("verses", []) if v.get("ref") == ref), "")
            except Exception:  # noqa: BLE001
                text = ""
            context = "지금 보고 있는 절: %s %s\n\n" % (ref, text)
        stdin_text = context + "설교자의 질문:\n" + q.strip() + "\n"
        self.one_at_a_time()
        try:
            started = time.time()
            deadline = started + self.ask_timeout
            sessions = st.get("session_ids") if isinstance(st.get("session_ids"), dict) else {}
            resume = sessions.get(stage)
            try:
                out = self._claude(binary, wd, stage, stdin_text, resume, deadline)
                if out.get("_resume_failed"):
                    out = self._claude(binary, wd, stage, stdin_text, None, deadline)
            except JobError as e:
                out = {"is_error": True, "_error": e.msg, "_code": e.code}
            took = round(time.time() - started, 1)
            denials = [d.get("tool_name", "") if isinstance(d, dict) else "" for d in out.get("permission_denials") or []]
            ok = not out.get("is_error") and isinstance(out.get("result"), str)
            entry = {"at": self.A.now(), "stage": stage, "verse": ref, "question": q.strip(),
                     "answer": out.get("result") if ok else None, "status": "ok" if ok else "error",
                     "error": None if ok else (out.get("_error") or out.get("subtype") or "응답 오류"),
                     "session_id": out.get("session_id"), "seconds": took,
                     "cost_usd": out.get("total_cost_usd"), "permission_denials": denials}
            logged = dict(entry)
            if stage == "7A":                               # 자기적용 단계의 글은 남기지 않습니다
                logged.update(question=None, answer=None, private=True)
            self.log(wd, logged)
            sid = out.get("session_id")
            if ok and gate.UUID_RX.match(str(sid or "")) and sid != resume:
                with self.A.progress_lock(wd):
                    fresh = self.ws.v1(wd)
                    ids = fresh.get("session_ids") if isinstance(fresh.get("session_ids"), dict) else {}
                    ids[stage] = sid
                    fresh["session_ids"] = ids
                    self.A.write_progress(wd, fresh)
            if not ok:
                raise JobError(out.get("_code") or 502, "감독이 답하지 못했습니다: %s" % entry["error"])
            return {k: entry[k] for k in ("at", "stage", "verse", "question", "answer", "seconds", "permission_denials")}
        finally:
            self.busy.release()

    def _claude(self, binary, wd, stage, stdin_text, resume, deadline):
        s3 = self.A.stage3_private(self.cfg)
        with tempfile.TemporaryDirectory(prefix="dsc-gate-") as td:
            sp, pp = Path(td) / ("gate-stage%s.json" % stage), Path(td) / "ask-prompt.md"
            sp.write_text(json.dumps(gate.settings(stage, s3, gate.private_files(wd)), ensure_ascii=False), encoding="utf-8")
            pp.write_text(gate.prompt(stage, self.A.NAMES[stage], s3), encoding="utf-8")
            args = gate.command(binary, sp, pp, model=self.cfg.get("ask_model", "sonnet"), resume=resume)
            p = run(args, wd, stdin_text, deadline - time.time(), env=gate.clean_env())
        if resume and p.returncode != 0 and any(m in (p.stderr or "") for m in RESUME_GONE):
            return {"_resume_failed": True}                 # 세션이 없어졌으면 새로 시작합니다
        try:
            out = json.loads(p.stdout)
        except ValueError:
            out = None
        if not isinstance(out, dict):
            return {"is_error": True, "_error": "응답을 읽지 못했습니다 (종료 코드 %s)" % p.returncode}
        return out

    def log(self, wd, entry):
        col = wd / "00_수집"
        if col.is_symlink() or (col.exists() and not self.ws.inside(col, wd)):
            raise JobError(403, "00_수집이 주간 폴더 밖을 가리킵니다")
        col.mkdir(exist_ok=True)
        target = col / "ask_log.jsonl"
        if target.is_symlink():
            raise JobError(403, "ask_log.jsonl이 링크입니다. 쓰지 않았습니다")
        line = json.dumps(entry, ensure_ascii=False) + "\n"
        with self.A.progress_lock(wd):
            fd = os.open(str(target), os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
            with os.fdopen(fd, "a", encoding="utf-8") as f:
                f.write(line)
                f.flush()
                os.fsync(f.fileno())

    def history(self, wid, limit=5):
        """지금 단계의 최근 문답만 돌려줍니다(다른 단계 글은 화면에 보내지 않음)."""
        wd = self.ws.week_dir(wid)
        st = self.ws.progress(wd)
        stage = self.A.norm_stage((st or {}).get("current_stage"))
        p = self.ws.file_in(wd, "00_수집", "ask_log.jsonl")
        if not p.is_file() or stage is None:
            return {"items": []}
        with open(p, "rb") as f:
            f.seek(0, os.SEEK_END)
            f.seek(max(0, f.tell() - TAIL_BYTES))
            raw = f.read().decode("utf-8", errors="replace")
        items = []
        for line in raw.splitlines():
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if isinstance(e, dict) and e.get("stage") == stage and not e.get("private"):
                items.append({k: e.get(k) for k in ("at", "stage", "verse", "clause", "question", "answer", "status", "error")})
        return {"items": items[-limit:]}

    # ------------------------------------------------------------ 본문 다시 수집
    def recollect(self, wid, body):
        if body.get("confirm") is not True:
            raise JobError(400, "설교자가 확인했을 때만 다시 수집합니다 (confirm: true)")
        wd = self.ws.week_dir(wid)
        st = self.ws.v1(wd)
        self.one_at_a_time()
        self.ws.recollecting.add(wid)                       # 그동안 원어관찰 쓰기를 잠시 막습니다(구문 동결 판단 보호)
        try:
            args = [sys.executable, "-I", str(SCRIPTS / "dsc_collect.py"), "passage", "--week-dir", str(wd),
                    "--ref=" + st.get("text", "")] + self.config_args()
            p = run(args, wd, "", self.collect_timeout)
        finally:
            self.ws.recollecting.discard(wid)
            self.busy.release()
        return self._script_json(p)

    # ------------------------------------------------------------ 진행 상황 점검
    def check(self, wid):
        wd = self.ws.week_dir(wid)
        self.ws.v1(wd)
        self.one_at_a_time()
        try:
            v = self._script_json(run([sys.executable, "-I", str(SCRIPTS / "dsc_archive.py"), "validate",
                                       "--week-dir", str(wd)] + self.config_args(), wd, "", 60))
            pv = self._script_json(run([sys.executable, "-I", str(SCRIPTS / "check_privacy.py"), str(wd), "--json"]
                                       + self.config_args(), wd, "", 60))
        finally:
            self.busy.release()
        res = (pv.get("result") or {}).get(wd.name, {}) if isinstance(pv, dict) else {}
        # 비공개 점검 결과는 파일 이름과 개수뿐입니다(7A 문장은 check_privacy가 내보내지 않음)
        return {"issues": v.get("issues", []) if isinstance(v, dict) else [],
                "privacy": {"errors": len(res.get("errors", [])), "messages": res.get("errors", []) + res.get("warnings", [])}}

    @staticmethod
    def _script_json(p):
        try:
            out = json.loads(p.stdout)
        except ValueError:
            raise JobError(502, "스크립트 결과를 읽지 못했습니다 (종료 코드 %s)" % p.returncode)
        return out
