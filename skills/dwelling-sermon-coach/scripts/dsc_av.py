#!/usr/bin/env python3
"""Stage 1 본문만남 — 본문 낭독 영상(mp4) 만들기.

본문만남 HTML(번역 탭·김상훈 배열)의 본문 단(data-sec="main")을 그대로 읽어,
번역마다 절 단위로 macOS 음성(기본 「Jian (Premium)」)으로 낭독하고,
절마다 배열 화면(들여쓰기·구문 색)을 띄워 음성과 맞춘 1920×1080 영상으로 합칩니다.

사용:
  python3 dsc_av.py --html Stage1_..._본문만남.html --out 본문낭독_....mp4
        [--order nkrv,rnksv,nkt,kct] [--voice "Jian (Premium)"] [--rate 175] [--work 임시폴더]

- 글자는 HTML에 있는 그대로 씁니다(지어내거나 고치지 않음). 절 번호·표제는 읽지 않습니다.
- 출력: --out mp4 하나와 같은 이름의 .timeline.json(절마다 시작·끝 초).
- 필요한 것: macOS `say`, ffmpeg/ffprobe, Pillow, 한글 글꼴(AppleSDGothicNeo).
"""
import argparse
import html as H
import json
import re
import shutil
import subprocess
import sys
import tempfile
from html.parser import HTMLParser
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

NAMES = {"nkt": "새한글", "rnksv": "새번역", "kct": "공동번역", "nkrv": "개역개정", "esv": "ESV"}
COL = {"bg": (246, 247, 249), "card": (255, 255, 255), "ink": (21, 25, 30), "muted": (93, 102, 114),
       "line": (221, 226, 232), "accent": (31, 95, 174), "s": (30, 96, 145), "v": (168, 50, 50), "g": (45, 106, 79),
       "soft": (238, 241, 245)}
FONT = "/System/Library/Fonts/AppleSDGothicNeo.ttc"
W, Hh = 1920, 1080
GAP_VERSE, GAP_TR, OPEN_SEC = 0.6, 1.6, 3.0


# ---------------------------------------------------------------- HTML 읽기
class Stage1Parser(HTMLParser):
    """trblock → main section → .v(절) → .ln(줄, iN) → 조각(c-s/c-v/c-g)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tr = None; self.in_main = False; self.depth_main = 0
        self.verse = None; self.line = None; self.color = None; self.skip = 0
        self.head = False; self.head_text = ""
        self.data = {}          # tr → {"heading": str, "verses": [{"n": str, "lines": [(indent, [(text, color)])]}]}
        self.stack = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs); cls = (a.get("class") or "").split()
        self.stack.append((tag, cls, a))
        if "trblock" in cls:
            self.tr = a.get("data-tr"); self.data[self.tr] = {"heading": "", "verses": []}
        if a.get("data-sec") == "main" and self.tr:
            self.in_main = True; self.depth_main = len(self.stack)
        if not self.in_main:
            return
        if "sec-h" in cls:
            self.head = True; self.head_text = ""
        if "v" in cls and "sup" not in cls and "data-tts-unit" in a:
            self.verse = {"n": "", "lines": []}
        if "data-tts-skip" in a or "dsc-tts" in cls:
            self.skip += 1
            if self.verse is not None and "n" in cls:
                self.skip -= 1; self.color = "N"
        if "ln" in cls and self.verse is not None:
            ind = next((int(c[1:]) for c in cls if re.fullmatch(r"i\d", c)), 0)
            self.line = [ind, []]
        for c in ("c-s", "c-v", "c-g"):
            if c in cls:
                self.color = c[2]

    def handle_endtag(self, tag):
        if not self.stack:
            return
        t, cls, a = self.stack.pop()
        if self.in_main:
            if "sec-h" in cls:
                self.head = False; self.data[self.tr]["heading"] = self.head_text.strip()
            if self.color == "N" and "n" in cls:
                self.color = None
            elif any(c in cls for c in ("c-s", "c-v", "c-g")):
                self.color = None
            if ("data-tts-skip" in a or "dsc-tts" in cls) and not ("n" in cls and self.verse is not None):
                self.skip -= 1
            if "ln" in cls and self.line is not None and self.verse is not None:
                self.verse["lines"].append((self.line[0], self.line[1])); self.line = None
            if "v" in cls and self.verse is not None and "data-tts-unit" in a:
                self.data[self.tr]["verses"].append(self.verse); self.verse = None
        if self.in_main and len(self.stack) < self.depth_main:
            self.in_main = False

    def handle_data(self, d):
        if not self.in_main:
            return
        if self.head:
            self.head_text += d
        if self.color == "N" and self.verse is not None:
            self.verse["n"] += d.strip(); return
        if self.skip > 0 or self.line is None:
            return
        if d:
            self.line[1].append((d, self.color))


def read_html(path):
    p = Stage1Parser()
    p.feed(Path(path).read_text(encoding="utf-8"))
    return p.data


def line_text(segs):
    return re.sub(r"\s+", " ", "".join(t for t, _ in segs)).strip()


# ---------------------------------------------------------------- 음성
def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit("실행 실패: %s\n%s" % (" ".join(cmd[:3]), r.stderr[-800:]))
    return r.stdout


def duration(f):
    return float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(f)]).strip())


def speak(text, out_wav, voice, rate, pad):
    aiff = out_wav.with_suffix(".aiff")
    run(["say", "-v", voice, "-r", str(rate), "-o", str(aiff), text])
    run(["ffmpeg", "-y", "-v", "error", "-i", str(aiff), "-af", "apad=pad_dur=%.2f" % pad,
         "-ar", "48000", "-ac", "2", str(out_wav)])
    aiff.unlink()
    return duration(out_wav)


def silence(out_wav, sec):
    run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", "%.2f" % sec, str(out_wav)])
    return sec


# ---------------------------------------------------------------- 화면
def font(size, bold=False):
    return ImageFont.truetype(FONT, size, index=6 if bold else 2)   # AppleSDGothicNeo: 2=Regular, 6=Bold(SemiBold 근사)


def base(title, ref, step):
    im = Image.new("RGB", (W, Hh), COL["bg"]); d = ImageDraw.Draw(im)
    d.rounded_rectangle((80, 60, W - 80, Hh - 60), radius=28, fill=COL["card"], outline=COL["line"], width=2)
    d.rectangle((80, 60, W - 80, 64), fill=COL["accent"])
    d.text((130, 96), title, font=font(46, True), fill=COL["accent"])
    tw = d.textlength(ref, font=font(40, True))
    d.text((W - 130 - tw, 100), ref, font=font(40, True), fill=COL["ink"])
    d.line((130, 172, W - 130, 172), fill=COL["line"], width=2)
    foot = "이삭교회 · 머무르는 설교 코치 · 김상훈 배열 · 들여쓰기 = 문법적 서열"
    d.text((130, Hh - 118), foot, font=font(26), fill=COL["muted"])
    if step:
        sw = d.textlength(step, font=font(26))
        d.text((W - 130 - sw, Hh - 118), step, font=font(26), fill=COL["muted"])
    lx = 130 + d.textlength(foot, font=font(26)) + 40
    for key, lab in (("s", "주어"), ("v", "주동사"), ("g", "종속절")):
        d.rounded_rectangle((lx, Hh - 112, lx + 22, Hh - 90), radius=4, fill=COL[key])
        d.text((lx + 30, Hh - 118), lab, font=font(26), fill=COL["muted"]); lx += 30 + d.textlength(lab, font=font(26)) + 28
    return im, d


def verse_frame(path, tr_name, ref, vn, lines, step):
    im, d = base(tr_name, ref, step)
    top, bottom, left, right = 210, Hh - 150, 210, W - 150
    for size in range(64, 27, -2):
        f, fb = font(size), font(size, True)
        lh, ind = int(size * 1.55), int(size * 1.4)
        ok = len(lines) * lh <= bottom - top
        if ok:
            for i, segs in lines:
                if left + i * ind + d.textlength(line_text(segs), font=f) > right:
                    ok = False; break
        if ok:
            break
    y = top + max(0, (bottom - top - len(lines) * lh) // 2)
    d.text((130, y + 4), vn, font=font(int(size * .8), True), fill=COL["muted"])
    for i, segs in lines:
        x = left + i * ind
        for t, c in segs:
            t = re.sub(r"\s+", " ", t)
            if not t:
                continue
            ff = fb if c == "v" else f
            d.text((x, y), t, font=ff, fill=COL[c] if c in ("s", "v", "g") else COL["ink"])
            x += d.textlength(t, font=ff)
        y += lh
    im.save(path)


def card_frame(path, big, small, step=""):
    im, d = base("", "", step)
    tw = d.textlength(big, font=font(110, True))
    d.text(((W - tw) / 2, Hh / 2 - 120), big, font=font(110, True), fill=COL["accent"])
    sw = d.textlength(small, font=font(52))
    d.text(((W - sw) / 2, Hh / 2 + 40), small, font=font(52), fill=COL["ink"])
    im.save(path)


# ---------------------------------------------------------------- 조립
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--html", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--order", default="nkrv,rnksv,nkt,kct")
    ap.add_argument("--voice", default="Jian (Premium)")
    ap.add_argument("--rate", type=int, default=175)
    ap.add_argument("--work")
    a = ap.parse_args(argv)

    data = read_html(a.html)
    order = [k.strip() for k in a.order.split(",") if k.strip()]
    missing = [k for k in order if k not in data or not data[k]["verses"]]
    if missing:
        sys.exit("본문 단을 찾지 못한 번역: %s" % ", ".join(missing))
    m = re.search(r"([가-힣]+ \d+:\d+(?:-\d+)?)", data[order[0]]["heading"])
    ref = m.group(1) if m else "본문"
    bk, ch = (re.match(r"([가-힣]+) (\d+):", ref).groups() if m else ("", ""))

    work = Path(a.work) if a.work else Path(tempfile.mkdtemp(prefix="dsc-av-"))
    work.mkdir(parents=True, exist_ok=True)
    segs, t, timeline = [], 0.0, []
    names = " · ".join(NAMES.get(k, k) for k in order)

    img = work / "000_open.png"; card_frame(img, ref, "본문 낭독 — " + names, "지안(프리미엄)")
    wav = work / "000_open.wav"; dur = silence(wav, OPEN_SEC); segs.append((img, wav, dur)); t += dur
    for ti, k in enumerate(order, 1):
        tr = NAMES.get(k, k); verses = data[k]["verses"]
        img = work / ("%d00_title.png" % ti); card_frame(img, tr, ref, "%d / %d" % (ti, len(order)))
        intro = "%s. %s %s편 %s절부터 %s절까지." % (tr, bk, ch, verses[0]["n"], verses[-1]["n"]) if bk else tr
        wav = work / ("%d00_title.wav" % ti); dur = speak(intro, wav, a.voice, a.rate, 1.0)
        segs.append((img, wav, dur)); t += dur
        for vi, v in enumerate(verses, 1):
            text = " ".join(line_text(s) for _, s in v["lines"])
            img = work / ("%d%02d.png" % (ti, vi))
            verse_frame(img, tr, "%s %s:%s" % (bk, ch, v["n"]) if bk else v["n"], v["n"], v["lines"],
                        "%s %d / %d" % (tr, vi, len(verses)))
            wav = work / ("%d%02d.wav" % (ti, vi))
            pad = GAP_TR if vi == len(verses) else GAP_VERSE
            dur = speak(text, wav, a.voice, a.rate, pad)
            timeline.append({"tr": k, "name": tr, "verse": v["n"], "start": round(t, 2), "end": round(t + dur, 2), "text": text})
            segs.append((img, wav, dur)); t += dur
        print("✓ %s %d절 낭독" % (tr, len(verses)), flush=True)

    vlist, alist = work / "video.txt", work / "audio.txt"
    vlist.write_text("".join("file '%s'\nduration %.3f\n" % (i, d) for i, _, d in segs) + "file '%s'\n" % segs[-1][0])
    alist.write_text("".join("file '%s'\n" % w for _, w, _ in segs))
    out = Path(a.out)
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(vlist), "-f", "concat", "-safe", "0",
         "-i", str(alist), "-vf", "fps=30,format=yuv420p", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
         "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(out)])
    out.with_suffix(".timeline.json").write_text(json.dumps({"ref": ref, "voice": a.voice, "order": order,
                                                             "duration": round(t, 2), "verses": timeline},
                                                            ensure_ascii=False, indent=1), encoding="utf-8")
    if not a.work:
        shutil.rmtree(work, ignore_errors=True)
    print(json.dumps({"status": "ok", "mp4": str(out), "seconds": round(duration(out), 1), "segments": len(segs)},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
