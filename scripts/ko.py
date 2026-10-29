"""스크립트들이 같이 쓰는 한국어 처리 도구."""
import re
import sys
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Windows 콘솔에서도 한글이 깨지지 않게
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass


@lru_cache(maxsize=1)
def kiwi():
    try:
        from kiwipiepy import Kiwi
    except ImportError:
        sys.exit("kiwipiepy가 필요하다: pip install kiwipiepy")
    return Kiwi()


def read_text(path):
    if path in (None, "-"):
        return sys.stdin.read()
    return Path(path).read_text(encoding="utf-8")


def write_text(path, text):
    if path in (None, "-"):
        sys.stdout.write(text)
    else:
        Path(path).write_text(text, encoding="utf-8", newline="")


def paragraphs(text):
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def sentences(text):
    """문단을 넘지 않게 문장을 나눈다. 마크다운 목록 줄은 한 문장으로 본다."""
    out = []
    for para in paragraphs(text):
        for line in para.split("\n"):
            line = line.strip()
            if not line:
                continue
            out.extend(s.text.strip() for s in kiwi().split_into_sents(line) if s.text.strip())
    return out


def hangul_len(s):
    """공백과 기호를 뺀 글자 수."""
    return len(re.sub(r"[\s\W_]", "", s))
