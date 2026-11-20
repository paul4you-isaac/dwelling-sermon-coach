"""작업창 버튼 → claude -p 호출의 단계별 권한 (계획서 §4, M0 실험 B)

프롬프트 지시가 아니라 **도구 권한**으로 막습니다.
- 도구는 Read·Glob·Grep 셋뿐입니다(--tools). 쓰기·셸·웹 도구는 아예 없습니다.
- 허용은 주간 폴더 안(./**)으로 한정합니다. 폴더 밖 읽기는 권한 거부입니다.
- 07A·06A 자기적용·묵상종합·묻기 기록(ask_log.jsonl)은 모든 단계에서 읽지 못합니다(버튼 경로).
- 주석(00_수집/주석/)은 4·5·6·7B·8·9단계에서만 읽을 수 있습니다. 0~3단계·7A에서는 거부입니다.
- 비공개 표시(md `private: true` · html dsc-private)가 있는 파일은 이름과 상관없이 거부합니다(부를 때마다 찾음).
- 설정 stage3_private가 true면 원어관찰 묵상 노트(03_원어관찰.json·생성본)도 거부합니다.
- --safe-mode로 CLAUDE.md·스킬·플러그인·훅을 끕니다(볼트 위쪽 CLAUDE.md가 지침을 덮지 못하게).
  M5 실험: 구독 로그인·--settings의 deny·--append-system-prompt-file·--resume은 그대로 작동.
"""
import json
import os
import re
import shutil
import unicodedata
from pathlib import Path

from dsc_collect import COMMENTARY_STAGES

TOOLS = ("Read", "Glob", "Grep")
ALWAYS_DENY_PATHS = ("./07A_*", "./06A_*", "./**/07A_*", "./**/06A_*", "./*묵상종합*", "./**/*묵상종합*",
                     "./00_수집/ask_log.jsonl")   # 묻기 기록: 7A 단계에서 적은 질문이 뒤 단계 답으로 새지 않게
COMMENTARY_PATHS = ("./00_수집/주석", "./00_수집/주석/**")
DENY_TOOLS = ("Write", "Edit", "NotebookEdit", "Bash", "WebFetch", "WebSearch", "Agent", "Task")

PROMPT = """# 머무르는 설교 코치 — 작업창 「감독에게 묻기」

당신은 설교자의 관찰 작업창에서 버튼 하나로 불린 감독의 보조입니다.
지금은 Stage {stage} {name} 단계입니다. 작업 폴더는 설교자의 주간 폴더입니다.

## 답하는 방식 (반드시)
- **관찰 질문 하나**만 드립니다. 한국어 경어체 한 문장, 「」 인용, 25~30자 안팎.
- 설교자가 사실을 물으면(단어가 어디에 또 쓰였는지, 시제·태·법·격, 직역) 사실만 한두 줄로 먼저 답하고, 이어서 관찰 질문 하나를 드립니다.
- **해석·신학 해설·적용·설교 문장을 드리지 않습니다.** 해석을 물으면 「해석은 Stage 4 1차청중 이후 주석과 함께 다시 만납니다」라고 짧게 돌려보내고 관찰 질문 하나를 드립니다.
- 설교자의 묵상 노트를 대신 쓰지 않습니다.
- 읽을 수 없는 파일이 있으면(권한 거부) 우회하지 말고, 읽을 수 없다고만 말합니다.
{commentary}
## 읽을 수 있는 것
- 주간 폴더 안 파일: `00_수집/passage.json`(본문·원어), `00_수집/syntax.json`(구문 분석), `03_원어관찰.json`(설교자 묵상 노트), 앞 단계 md.
- 쓰기 도구는 없습니다. 파일을 만들거나 고치지 않습니다.
"""
COMM_OPEN = "- 이 단계에서는 `00_수집/주석/`의 주석을 읽을 수 있습니다. 주석의 결론을 먼저 전하지 말고, 질문 하나로 설교자가 본문으로 돌아가게 합니다.\n"
COMM_SHUT = "- 이 단계에서는 주석을 읽지 않습니다(권한으로도 막혀 있습니다).\n"


STAGE3_PATHS = ("./03_원어관찰.json", "./03_원어관찰_*")
UUID_RX = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
MODEL_RX = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._\-\[\]]{0,63}$")
GLOB_SPECIAL = re.compile(r"[*?\[\]{}!\\]")


def private_files(wd):
    """주간 폴더에서 비공개 표시가 있는 파일의 상대 경로(NFC·NFD 둘 다)."""
    from dsc_archive import frontmatter
    out = []
    for f in Path(wd).rglob("*"):
        if not f.is_file() or f.is_symlink() or f.suffix not in (".md", ".html"):
            continue
        try:
            if f.suffix == ".md":
                priv = str((frontmatter(f) or {}).get("private", "")).lower() == "true"
            else:
                priv = bool(re.search(r'<meta\s+name="dsc-private"\s+content="true"',
                                      f.read_text(encoding="utf-8", errors="replace")[:5000], re.I))
        except (OSError, ValueError):
            priv = True                                        # 읽지 못하면 막는 쪽으로
        if priv:
            rel = f.relative_to(wd).as_posix()
            for form in {unicodedata.normalize("NFC", rel), unicodedata.normalize("NFD", rel)}:
                out.append("./" + GLOB_SPECIAL.sub("?", form))   # 글롭 특수문자는 한 글자 자리로
    return sorted(set(out))


def deny_rules(stage, stage3_private=False, extra_paths=()):
    rules = list(DENY_TOOLS)
    paths = list(ALWAYS_DENY_PATHS) + ([] if stage in COMMENTARY_STAGES else list(COMMENTARY_PATHS))
    paths += (list(STAGE3_PATHS) if stage3_private else []) + list(extra_paths)
    for p in paths:
        for t in TOOLS:
            rules.append("%s(%s)" % (t, p))
    return rules


def settings(stage, stage3_private=False, extra_paths=()):
    return {"disableAllHooks": True,
            "permissions": {"deny": deny_rules(stage, stage3_private, extra_paths), "defaultMode": "dontAsk"}}


def prompt(stage, name, stage3_private=False):
    text = PROMPT.format(stage=stage, name=name, commentary=COMM_OPEN if stage in COMMENTARY_STAGES else COMM_SHUT)
    if stage3_private:
        text = text.replace("`03_원어관찰.json`(설교자 묵상 노트), ", "")
    return text


def claude_bin(cfg):
    """설정 claude_bin → PATH → ~/.local/bin/claude 순서로 찾습니다."""
    for c in (cfg.get("claude_bin"), shutil.which("claude"), str(Path.home() / ".local/bin/claude")):
        if c and os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    return None


def command(binary, settings_path, prompt_path, model="sonnet", resume=None, max_turns=6, budget=0.5):
    """셸을 거치지 않는 인자 목록. 질문은 stdin으로 넘깁니다."""
    args = [binary, "-p",
            "--setting-sources", "project",
            "--settings", str(settings_path),
            "--strict-mcp-config", "--mcp-config", json.dumps({"mcpServers": {}}),
            "--tools", ",".join(TOOLS),
            "--allowedTools"] + ["%s(./**)" % t for t in TOOLS] + [
            "--permission-mode", "dontAsk",
            "--max-turns", str(max_turns),
            "--max-budget-usd", str(budget),
            "--model=" + (model if MODEL_RX.match(str(model)) else "sonnet"),
            "--safe-mode",
            "--system-prompt-snapshot", "off",
            "--append-system-prompt-file", str(prompt_path),
            "--output-format", "json"]
    if resume and UUID_RX.match(str(resume)):
        args.append("--resume=" + resume)                 # 값이 옵션으로 읽히지 않게 = 로 붙입니다
    return args


def clean_env(env=None):
    """구독 로그인으로 돌게 API 키를 빼고, 훅·플러그인 쪽 변수도 넘기지 않습니다."""
    env = dict(os.environ if env is None else env)
    for k in list(env):
        if (k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL", "ANTHROPIC_MODEL", "CLAUDECODE")
                or k.startswith(("CLAUDE_PLUGIN_", "CLAUDE_CODE_USE_", "ANTHROPIC_DEFAULT_"))):
            env.pop(k)
    return env
