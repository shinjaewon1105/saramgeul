"""한국어 글의 AI 냄새를 수치로 잰다.

기준값은 KatFishNet(ACL 2025)의 사람 대 LLM 에세이 통계와 Wikipedia "Signs of AI
writing", im-not-ai 룰북에서 가져왔다. 점수는 0(사람 쪽)~100(AI 쪽)이다.

    python score.py 글.md
    python score.py 새글.md --orig 원문.md     # 원문 뼈대가 남았는지도 본다
    python score.py 글.md --json
"""
import argparse
import json
import re
import statistics
from pathlib import Path

from ko import ROOT, hangul_len, kiwi, paragraphs, read_text, sentences

SYMBOLS = {
    "P1 가운데점": r"[·ㆍ‧・]",
    "P2 화살표": r"[→⇒←↔⟶➔➜]",
    "P3 줄표": r"[—–]|(?<=[가-힣])\s-\s(?=[가-힣])",
    "P4 둥근 따옴표, 말줄임": r"[“”‘’…]",
    "P5 이모지, 장식": "[\U0001F300-\U0001FAFF☀-➿✓✔✅•▪◦]",
    "P6 괄호 영어": r"\([A-Za-z][^)]*\)",
    "C2 굵은 글씨": r"\*\*[^*]+\*\*",
}
STRUCT = {
    "C1 소제목": r"(?m)^\s{0,3}#{1,6}\s",
    "C1 목록": r"(?m)^\s*([-*+•]|\d+[.)])\s+",
}


def load_tsv(name):
    rows = []
    for line in (ROOT / "references" / name).read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        pat, label, w = line.split("\t")
        rows.append((re.compile(pat, re.M), label, float(w)))
    return rows


def load_phrases():
    return load_tsv("phrases-ko.tsv")


def cv(values):
    if len(values) < 2:
        return 0.0
    m = statistics.mean(values)
    return statistics.pstdev(values) / m if m else 0.0


def bigrams(s):
    s = re.sub(r"\s+", "", s)
    return {s[i:i + 2] for i in range(len(s) - 1)}


def skeleton(new_sents, orig_sents):
    """새 글의 문장 중 원문 문장과 거의 같은 짝이 있는 비율."""
    orig = [bigrams(s) for s in orig_sents]
    hits = 0
    for s in new_sents:
        b = bigrams(s)
        if not b:
            continue
        best = max((len(b & o) / len(b | o) for o in orig if o), default=0)
        if best >= 0.45:
            hits += 1
    return hits / max(len(new_sents), 1)


def measure(text, orig=None):
    sents = sentences(text)
    n = max(len(sents), 1)
    toks = kiwi().tokenize(text)
    m = {}

    # 쉼표 (K)
    m["쉼표 있는 문장 비율"] = sum("," in s for s in sents) / n
    # KatFishNet 정의: 쉼표 앞에 온 연결어미 수 / 연결어미 전체 수
    ec = [i for i, t in enumerate(toks) if t.tag == "EC"]
    ec_comma = sum(1 for i in ec if i + 1 < len(toks) and toks[i + 1].form == ",")
    m["연결어미 뒤 쉼표 비율"] = ec_comma / max(len(ec), 1)
    maj_comma = sum(1 for a, b in zip(toks, toks[1:]) if a.tag == "MAJ" and b.form == ",")
    m["접속부사 뒤 쉼표 수"] = maj_comma
    m["형태소당 쉼표"] = sum(t.form == "," for t in toks) / max(len(toks), 1)

    # 리듬 (E)
    lens = [hangul_len(s) for s in sents]
    m["문장 길이 평균"] = statistics.mean(lens) if lens else 0
    m["문장 길이 변동계수"] = cv(lens)
    flat = 0
    for a, b, c in zip(lens, lens[1:], lens[2:]):
        lo, hi = min(a, b, c), max(a, b, c)
        if hi and (hi - lo) / hi < 0.25:
            flat += 1
    m["비슷한 길이 3연속"] = flat
    # 했다체는 모두 '다'로 끝나니 형태소 대신 끝 세 글자로 본다 (었다, 한다, 이다, 있다 ...)
    endings = [re.sub(r"[^가-힣]", "", s)[-3:] for s in sents]
    run = best = 1
    for a, b in zip(endings, endings[1:]):
        run = run + 1 if a and a == b else 1
        best = max(best, run)
    m["같은 종결어미 최장 연속"] = best if endings else 0
    m["종결어미 종류"] = len(set(e for e in endings if e))

    starts = 0
    for s in sents:
        st = kiwi().tokenize(s)
        if st and st[0].tag == "MAJ":
            starts += 1
    m["접속부사로 시작한 문장 비율"] = starts / n
    plens = [hangul_len(p) for p in paragraphs(text)]
    m["문단 수"] = len(plens)
    m["문단 길이 변동계수"] = cv(plens)

    # 명사화와 형식명사 (F)
    eojeol = max(len(text.split()), 1)
    m["-적/-성/-화 per 100어절"] = 100 * sum(1 for t in toks if t.tag == "XSN" and t.form in ("적", "성", "화")) / eojeol
    m["형식명사 per 문장"] = sum(1 for t in toks if t.tag == "NNB" and t.form in ("것", "수", "바", "점")) / n

    # 품사 다양성 (KatFishNet: 사람이 높다)
    tags = [t.tag for t in toks if t.tag not in ("SP", "SF", "SS", "SE", "SO", "SW")]
    tri = list(zip(tags, tags[1:], tags[2:]))
    m["품사 3-gram 다양성"] = len(set(tri)) / max(len(tri), 1)

    # 띄어쓰기가 너무 완벽한가 (K4): 의존명사, 보조용언 앞 공백
    spaced = total = 0
    for a, b in zip(toks, toks[1:]):
        if (b.tag == "NNB" and b.form in ("수", "것", "때", "줄", "거")) or b.tag == "VX":
            if a.tag in ("ETM", "EC"):
                total += 1
                spaced += b.start > a.start + a.len
    m["의존명사/보조용언 띄어쓴 비율"] = spaced / total if total else None

    # 기호와 서식
    sym = {k: len(re.findall(p, text)) for k, p in SYMBOLS.items()}
    sym.update({k: len(re.findall(p, text)) for k, p in STRUCT.items()})
    m["기호"] = {k: v for k, v in sym.items() if v}

    # 상투 표현
    hits = []
    for pat, pid, w in load_phrases():
        for mm in pat.finditer(text):
            hits.append((pid, mm.group(0), w))
    m["상투 표현"] = hits

    # 쉬운 우리말이 있는 한자어 (W)
    hanja = []
    for pat, native, w in load_tsv("hanjaeo-ko.tsv"):
        for mm in pat.finditer(text):
            hanja.append((mm.group(0).strip(), native, w))
    m["한자어"] = hanja
    m["한자어 per 100어절"] = 100 * sum(w for _, _, w in hanja) / eojeol

    if orig is not None:
        osents = sentences(orig)
        m["원문 뼈대 잔존율"] = skeleton(sents, osents)
        m["분량 비율(새/원)"] = hangul_len(text) / max(hangul_len(orig), 1)
    m["문장 수"] = len(sents)
    m["글자 수"] = hangul_len(text)
    return m


def judge(m):
    """각 지표를 통과/주의/실패로 가르고 0~100 점수를 낸다."""
    checks = []

    def add(name, value, ok, warn, weight, note, higher_is_ai=True):
        if value is None:
            return
        if higher_is_ai:
            state = "실패" if value >= warn else "주의" if value > ok else "통과"
        else:
            state = "실패" if value <= warn else "주의" if value < ok else "통과"
        checks.append((name, value, state, weight, note))

    # 기준값과 가중치는 calibrate.py 결과(KatFish 논설문 사람 181, AI 590)에 맞췄다.
    # 괄호 안은 사람 중앙값 / AI 중앙값 / AUROC.
    add("쉼표 있는 문장 비율", m["쉼표 있는 문장 비율"], 0.3, 0.45, 12, "사람 0.13 / AI 0.61 / 0.93 (K3)")
    add("연결어미 뒤 쉼표 비율", m["연결어미 뒤 쉼표 비율"], 0.06, 0.12, 12, "사람 0.00 / AI 0.19 / 0.93 (K1)")
    add("접속부사 뒤 쉼표 수", m["접속부사 뒤 쉼표 수"], 0, 2, 4, "그러나, 따라서, (K2)")
    add("문장 길이 변동계수", m["문장 길이 변동계수"], 0.4, 0.3, 8, "사람 0.42 / AI 0.31 / 0.81 (E1)", higher_is_ai=False)
    add("비슷한 길이 3연속", m["비슷한 길이 3연속"] / max(m["문장 수"] - 2, 1), 0.12, 0.25, 4, "0.75 (E1)")
    add("같은 종결어미 최장 연속", m["같은 종결어미 최장 연속"], 3, 5, 3, "사람 2 / AI 3 / 0.69 (E2)")
    if m["문단 수"] >= 3:
        add("문단 길이 변동계수", m["문단 길이 변동계수"], 0.35, 0.2, 4, "고르면 AI (C5)", higher_is_ai=False)
    add("-적/-성/-화 per 100어절", m["-적/-성/-화 per 100어절"], 2, 4, 6, "사람 0.92 / AI 3.89 / 0.81 (F1)")
    if m["문장 수"] >= 8:
        add("품사 3-gram 다양성", m["품사 3-gram 다양성"], 0.55, 0.47, 4, "사람 0.60 / AI 0.48 / 0.88", higher_is_ai=False)
    if m["문장 수"] >= 8 and m["문장 길이 평균"] < 22:
        add("짧은 문장만 이어짐", m["문장 길이 변동계수"], 0.5, 0.4, 5, "2026년형 (E5)", higher_is_ai=False)
    sym_total = sum(m["기호"].values())
    add("기호, 서식 개수", sym_total, 0, 3, 12, "P, C1, C2")
    phr = sum(w for _, _, w in m["상투 표현"]) / max(m["글자 수"] / 500, 1)
    add("상투 표현 (500자당 가중합)", phr, 1.5, 3.5, 14, "사람 1.0 / AI 5.4 / 0.88")
    add("한자어 per 100어절", m["한자어 per 100어절"], 0.7, 1.4, 10, "사람 0.26 / AI 1.69 / 0.85 (W1)")
    if m["의존명사/보조용언 띄어쓴 비율"] is not None and m["글자 수"] > 300:
        add("의존명사/보조용언 띄어쓴 비율", m["의존명사/보조용언 띄어쓴 비율"], 0.85, 0.95, 6, "사람 0.75 / AI 0.93 / 0.85 (K4)")
    if "원문 뼈대 잔존율" in m:
        add("원문 뼈대 잔존율", m["원문 뼈대 잔존율"], 0.2, 0.35, 15, "고쳐 쓰기만 했는지")

    total_w = sum(c[3] for c in checks)
    bad = sum(c[3] * (1 if c[2] == "실패" else 0.4 if c[2] == "주의" else 0) for c in checks)
    score = round(100 * bad / total_w) if total_w else 0
    return score, checks


def fmt(v):
    if isinstance(v, float):
        return f"{v:.2f}"
    return str(v)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", nargs="?", default="-")
    ap.add_argument("--orig", help="원문 파일. 뼈대 잔존율과 분량 비율을 같이 잰다")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    text = read_text(args.input)
    orig = Path(args.orig).read_text(encoding="utf-8") if args.orig else None
    m = measure(text, orig)
    score, checks = judge(m)

    if args.json:
        print(json.dumps({"score": score, "checks": checks, "metrics": m}, ensure_ascii=False, indent=1, default=str))
        return

    print(f"AI 냄새 점수: {score}/100  (문장 {m['문장 수']}, 글자 {m['글자 수']})")
    print("기준: 25 이하면 통과, 26~45는 손볼 곳 있음, 46 이상은 다시 쓴다")
    for name, value, state, _, note in checks:
        mark = {"통과": "  ", "주의": "△ ", "실패": "✗ "}[state]
        print(f"{mark}{name}: {fmt(value)}  [{state}] {note}")
    if m["기호"]:
        print("  기호: " + ", ".join(f"{k} {v}" for k, v in m["기호"].items()))
    if m["상투 표현"]:
        print("  상투 표현: " + ", ".join(f"{pid} '{s}'" for pid, s, _ in m["상투 표현"][:25]))
    if m["한자어"]:
        print("  한자어: " + ", ".join(f"'{w}'→{n}" for w, n, _ in m["한자어"][:20]))
    print(f"  참고: 품사 3-gram 다양성 {m['품사 3-gram 다양성']:.2f}, 종결어미 {m['종결어미 종류']}종, 문장 평균 {m['문장 길이 평균']:.1f}자")
    if "분량 비율(새/원)" in m:
        print(f"  참고: 분량 비율 {m['분량 비율(새/원)']:.2f} (0.70~0.90 권장)")


if __name__ == "__main__":
    main()
