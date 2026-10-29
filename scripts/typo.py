"""사람이 실제로 하는 띄어쓰기 실수를 사람이 하는 비율만큼 넣는다. 규칙은 references/typos-ko.md.

규칙마다 확률은 KatFish 사람 논설문(2021년, 사람 181편)에서 잰 생략률이다. AI 글에서는
거의 0인데 사람 글에서는 꾸준히 나오는 것만 골랐다. 맞춤법 혼동은 기본으로 넣지 않는다.

    python typo.py 글.md -o 출력.md                 # light: 사람 비율 그대로
    python typo.py 글.md --mode casual              # 비율 1.6배, 마지막 마침표 생략
    python typo.py 글.md --spelling                 # 몇일, 금새 같은 맞춤법 혼동도 조금
    python typo.py 글.md --dry-run --seed 3         # 무엇을 바꿀지만 보여준다
"""
import argparse
import random
import re
import sys

from ko import read_text, write_text

# (이름, 정규식, 바꿀 꼴, 사람 비율, AI 비율). 정규식의 공백 하나를 지우거나 넣는다.
# 사람/AI 비율은 KatFish 논설문에서 잰 값이다.
SPACING = [
    ("할 수 → 할수", r"(?<=[가-힣]) (?=수 ?(있|없))", "", 0.13, 0.00),
    ("할 때 → 할때", r"(?<=[ㄹ을할갈볼될쓸올살]) (?=때[^문])", "", 0.25, 0.00),
    ("해야 한다 → 해야한다", r"(?<=야) (?=(한|할|하|했|합))", "", 0.26, 0.02),
    ("되어 있다 → 되어있다", r"(?<=[어아여해워져]) (?=있)", "", 0.53, 0.15),
    ("하는 것 → 하는것", r"(?<=[는은한던]) (?=것)", "", 0.09, 0.00),
    ("것 같다 → 것같다", r"(?<=것) (?=같)", "", 0.09, 0.00),
    ("하고 싶다 → 하고싶다", r"(?<=고) (?=싶)", "", 0.12, 0.00),
    ("할 뿐 → 할뿐", r"(?<=[ㄹ을할]) (?=뿐)", "", 0.25, 0.08),
    ("하지 않다 → 하지않다", r"(?<=지) (?=않)", "", 0.05, 0.00),
    ("공부 중 → 공부중", r"(?<=[가-힣]{2}) (?=중(이|에|인))", "", 0.62, 0.31),
    ("할 거다 → 할거다", r"(?<=[할될을]) (?=거(야|다|예|에|라|같))", "", 0.06, 0.00),
    ("그동안 → 그 동안", r"(?<=그)(?=동안)", " ", 0.67, 0.00),
]
SPELLING = [
    ("며칠 → 몇일", r"며칠", "몇일"),
    ("금세 → 금새", r"금세", "금새"),
    ("웬만 → 왠만", r"웬만", "왠만"),
    ("어떡해 → 어떻해", r"어떡해", "어떻해"),
    ("역할 → 역활", r"역할", "역활"),
    ("오랜만 → 오랫만", r"오랜만", "오랫만"),
    ("됐 → 됬", r"됐", "됬"),
    ("일부러 → 일부로", r"일부러", "일부로"),
]
PROTECT = re.compile(r'"[^"\n]*"|`[^`]*`|\$[^$]*\$|[A-Za-z0-9_./:-]+')
FACTOR = {"light": 1.0, "casual": 1.6}


def protected(text):
    spans = [(m.start(), m.end()) for m in PROTECT.finditer(text)]
    return lambda pos: any(a <= pos < b for a, b in spans)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", nargs="?", default="-")
    ap.add_argument("-o", "--output", default="-")
    ap.add_argument("--mode", choices=["off", "light", "casual"], default="light")
    ap.add_argument("--spelling", action="store_true", help="맞춤법 혼동도 드물게 넣는다 (글 하나에 많아야 1개)")
    ap.add_argument("--seed", type=int)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    text = read_text(args.input)
    if args.mode == "off":
        write_text(args.output, text)
        return
    rng = random.Random(args.seed)
    is_protected = protected(text)
    factor = FACTOR[args.mode]

    edits = []  # (시작, 끝, 바꿀 꼴, 이름)
    for name, pat, rep, p_human, _ in SPACING:
        p = min(p_human * factor, 0.9)
        for m in re.finditer(pat, text):
            if not is_protected(m.start()) and rng.random() < p:
                edits.append((m.start(), m.end(), rep, name))

    if args.spelling:
        cands = [(m.start(), m.end(), rep, name) for name, pat, rep in SPELLING
                 for m in re.finditer(pat, text) if not is_protected(m.start())]
        if cands:
            edits.append(rng.choice(cands))

    # 같은 자리를 두 번 고치지 않는다
    edits.sort(key=lambda e: e[0])
    uniq, last_end = [], -1
    for e in edits:
        if e[0] > last_end:
            uniq.append(e)
            last_end = e[1]

    new = text
    for a, b, rep, _ in reversed(uniq):
        new = new[:a] + rep + new[b:]
    if args.mode == "casual":
        new = re.sub(r"\.(\s*)$", r"\1", new)

    for a, _, _, name in uniq:
        ctx = text[max(0, a - 8):a + 8].replace("\n", " ")
        print(f"  {name}: ...{ctx}...", file=sys.stderr)
    print(f"typo: {len(uniq)}개 ({args.mode})", file=sys.stderr)
    if not args.dry_run:
        write_text(args.output, new)


if __name__ == "__main__":
    main()
