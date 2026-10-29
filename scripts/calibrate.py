"""KatFish 논설문(사람 181편, LLM 590편)으로 score.py 지표가 사람과 AI를 얼마나 가르는지 잰다.

지표마다 사람과 AI의 중앙값, AUROC(0.5는 못 가름, 1.0이나 0.0은 완벽히 가름)를 보여 준다.
기준값을 고칠 때 이 표를 근거로 쓴다. 먼저 fetch_exemplars.py로 데이터를 받아야 한다.

    python calibrate.py              # 전체
    python calibrate.py --limit 200  # 빠르게
"""
import argparse
import json
import random
import statistics

from ko import ROOT
import score

SKIP = {"기호", "상투 표현", "한자어", "문장 수", "글자 수", "문단 수"}


def auroc(pos, neg):
    """AI(pos)가 사람(neg)보다 클 확률."""
    if not pos or not neg:
        return None
    wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return wins / (len(pos) * len(neg))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", default=str(ROOT / "data" / "calibration.json"))
    args = ap.parse_args()

    path = ROOT / "data" / "katfish" / "essay.jsonl"
    rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    random.Random(0).shuffle(rows)
    if args.limit:
        rows = rows[:args.limit]

    feats = {"human": [], "ai": []}
    for i, r in enumerate(rows, 1):
        m = score.measure(r["text"])
        s, _ = score.judge(m)
        f = {k: v for k, v in m.items() if k not in SKIP and isinstance(v, (int, float))}
        f["기호, 서식 개수"] = sum(m["기호"].values())
        f["상투 표현 가중합/500자"] = sum(w for _, _, w in m["상투 표현"]) / max(m["글자 수"] / 500, 1)
        f["AI 냄새 점수"] = s
        feats["human" if r["written_by"] == "human" else "ai"].append(f)
        if i % 100 == 0:
            print(f"  {i}/{len(rows)}")

    names = sorted({k for f in feats["human"] + feats["ai"] for k in f})
    table = []
    for k in names:
        h = [f[k] for f in feats["human"] if f.get(k) is not None]
        a = [f[k] for f in feats["ai"] if f.get(k) is not None]
        if not h or not a:
            continue
        table.append((k, statistics.median(h), statistics.median(a), auroc(a, h)))
    table.sort(key=lambda t: -abs(t[3] - 0.5))

    print(f"\n사람 {len(feats['human'])}편, AI {len(feats['ai'])}편")
    print(f"{'지표':<28}{'사람 중앙값':>10}{'AI 중앙값':>10}{'AUROC':>8}")
    for k, h, a, auc in table:
        print(f"{k:<28}{h:>10.3f}{a:>10.3f}{auc:>8.3f}")
    (ROOT / "data").mkdir(exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fp:
        json.dump([dict(zip(("지표", "사람", "AI", "AUROC"), t)) for t in table], fp, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
