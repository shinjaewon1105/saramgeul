"""기호와 쉼표를 기계적으로 정리한다.

안전하게 바꿀 수 있는 것은 바로 바꾸고, 문맥을 봐야 하는 것은 줄 번호와 함께
stderr로 알려 재작성 단계에서 손으로 고치게 한다.

    python clean.py 입력.md -o 출력.md
    python clean.py 입력.md --keep-commas   # 쉼표 솎아내기를 끈다
"""
import argparse
import re
import sys

from ko import kiwi, read_text, write_text

EMOJI = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F2FF️‍]"
)
MIDDOT = "·ㆍ‧・"

# 바로 바꿔도 뜻이 안 바뀌는 것
SAFE = [
    (re.compile(r"\*\*(.+?)\*\*"), r"\1", "굵은 글씨"),
    (re.compile(r"(?<!\w)__(.+?)__(?!\w)"), r"\1", "굵은 글씨"),
    (re.compile(r"(\d)[ \t]*[–—][ \t]*(\d)"), r"\1~\2", "범위 줄표"),
    (re.compile(r"[ \t]*[—–][ \t]*"), ", ", "줄표"),
    (re.compile(r"(?<=[가-힣])[ \t]+-[ \t]+(?=[가-힣])"), ", ", "줄표"),
    # 충·방전, 입·출력처럼 한 글자끼리 묶은 것은 붙여 쓴다
    (re.compile(rf"(?<![가-힣])([가-힣])[{MIDDOT}](?=[가-힣])"), r"\1", "가운데점"),
    (re.compile(rf"[ \t]*[{MIDDOT}][ \t]*"), ", ", "가운데점"),
    (re.compile(r"[“”]"), '"', "둥근 따옴표"),
    (re.compile(r"[‘’]"), "'", "둥근 따옴표"),
    (re.compile(r"…"), "...", "말줄임 기호"),
    (re.compile(r"[✓✔✅❌✗☑★☆▶►•▪◦]\s?"), "", "장식 기호"),
    (EMOJI, "", "이모지"),
]

# 알리기만 하는 것
FLAG = [
    (re.compile(r"[→⇒←↔⟶➔➜]"), "P2 화살표: 문장으로 풀어 쓴다"),
    (re.compile(r"^\s{0,3}#{1,6}\s"), "C1 소제목: 산문이면 없앤다"),
    (re.compile(r"^\s*([-*+]|\d+[.)])\s+"), "C1 목록: 산문으로 잇는다"),
    (re.compile(r"[가-힣]+\s?\([A-Za-z][^)]*\)"), "P6 괄호 영어 병기"),
    (re.compile(r"\([^)]{12,}\)"), "P6 괄호 보충 설명"),
    (re.compile(r";"), "세미콜론: 마침표로 끊는다"),
]


LONG_CLAUSE = 20  # 이보다 긴 절 뒤의 쉼표는 사람도 찍는다


def thin_commas(text):
    """사람이 잘 안 찍는 쉼표를 지운다 (KatFishNet K1, K2).

    - 접속부사 뒤 (그러나, 따라서,)
    - 문장 첫 부사 뒤 (특히, 결국, 실제로,)
    - 짧은 절의 연결어미 뒤 (먹고, 갔지만,)
    - 짧은 주어, 주제어 뒤 (이 변화는, 우리가,)
    KatFish 사람 논설문은 쉼표 있는 문장이 13%다. 그래도 긴 절 뒤 쉼표까지 다 지우면
    문장이 엉키고 일부러 걷어낸 티가 나므로 남긴다.
    """
    toks = kiwi().tokenize(text)
    drop = []
    seg_start = sent_start = 0
    for prev, tok in zip(toks, toks[1:]):
        if tok.tag == "SF":
            seg_start = sent_start = tok.start + tok.len
            continue
        if tok.form != "," or tok.tag != "SP":
            continue
        short = len(re.sub(r"\W", "", text[seg_start:tok.start])) < LONG_CLAUSE
        seg_start = tok.start + 1
        sentence_head = not re.sub(r"\W", "", text[sent_start:prev.start])
        if prev.tag == "MAJ":
            drop.append(tok.start)
        elif prev.tag == "MAG" and sentence_head:
            drop.append(tok.start)
        elif prev.tag == "EC" and prev.form != "지" and short:
            drop.append(tok.start)
        elif prev.tag in ("JX", "JKS") and short:
            drop.append(tok.start)
    if not drop:
        return text, 0
    chars = list(text)
    for pos in reversed(drop):
        if chars[pos] == ",":
            del chars[pos]
    return "".join(chars), len(drop)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", nargs="?", default="-")
    ap.add_argument("-o", "--output", default="-")
    ap.add_argument("--keep-commas", action="store_true", help="연결어미 뒤 쉼표를 그대로 둔다")
    args = ap.parse_args()

    text = read_text(args.input)
    counts = {}
    for pat, rep, name in SAFE:
        text, n = pat.subn(rep, text)
        if n:
            counts[name] = counts.get(name, 0) + n
    # 줄표를 쉼표로 바꾸며 생긴 ", ," 나 ",." 정리
    text = re.sub(r",[ \t]*,", ",", text)
    text = re.sub(r",[ \t]*([.!?])", r"\1", text)
    text = re.sub(r"[ \t]{2,}", " ", text)

    if not args.keep_commas:
        text, n = thin_commas(text)
        if n:
            counts["불필요한 쉼표"] = n

    flags = []
    for i, line in enumerate(text.split("\n"), 1):
        for pat, msg in FLAG:
            for m in pat.finditer(line):
                flags.append(f"  {i}행: {msg}  [{m.group(0).strip()[:30]}]")

    write_text(args.output, text)
    print("clean: " + (", ".join(f"{k} {v}" for k, v in counts.items()) or "바꾼 것 없음"), file=sys.stderr)
    if flags:
        print(f"손으로 고칠 곳 {len(flags)}개:", file=sys.stderr)
        print("\n".join(flags), file=sys.stderr)


if __name__ == "__main__":
    main()
