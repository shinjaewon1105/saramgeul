"""로컬 Ollama 모델을 채팅이 아니라 '문서 이어쓰기'로 돌려 초안 후보를 만든다.

근거: "Base Models Look Human To AI Detectors"(arXiv 2605.19516). 탐지기는 기계 글 자체보다
지시 튜닝과 RLHF가 남긴 조수 말투에 반응한다. 채팅 템플릿 없이 raw 모드로 사람 글
모음집의 다음 글을 이어 쓰게 하면, 지시 모델이라도 조수 말투가 덜 끼어든다.

후보를 여러 개 만들어 score.py로 가장 낮은 것을 고른다. 내용 정확성은 보장하지 않으므로
이 초안은 반드시 Claude가 내용 카드와 대조해 고친다.

    python local_draft.py 카드.md --exemplars ../exemplars -n 3 -o 초안.md
"""
import argparse
import json
import random
import sys
import urllib.request
from pathlib import Path

from ko import ROOT, read_text, write_text

sys.path.insert(0, str(Path(__file__).parent))
import score  # noqa: E402

OLLAMA = "http://localhost:11434/api/generate"


def load_exemplars(folder, k, rng):
    files = [p for p in Path(folder).glob("*.md") if p.name.lower() != "readme.md"]
    rng.shuffle(files)
    out = []
    for p in files[:k]:
        body = p.read_text(encoding="utf-8").strip()
        out.append(body[:1800])
    return out


def build_prompt(cards, exemplars, title):
    parts = ["아래는 한 사람이 여러 해 동안 쓴 글을 모아 둔 공책이다. 맞춤법 검사기를 돌리지 않은 원본 그대로다.\n"]
    for i, ex in enumerate(exemplars, 1):
        parts.append(f"===== 글 {i} =====\n{ex}\n")
    n = len(exemplars) + 1
    parts.append(f"===== 글 {n} =====\n(쓰기 전에 적어 둔 메모: {cards.strip()})\n\n{title}\n\n")
    return "\n".join(parts)


def generate(model, prompt, temperature, num_predict, seed):
    body = json.dumps({
        "model": model,
        "prompt": prompt,
        "raw": True,
        "stream": False,
        "think": False,
        "options": {"temperature": temperature, "top_p": 0.95, "num_predict": num_predict,
                    "seed": seed, "stop": ["=====", "(쓰기 전에"]},
    }).encode()
    req = urllib.request.Request(OLLAMA, body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as r:
        return json.loads(r.read())["response"].strip()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cards", help="내용 카드 파일 (사실, 주장, 수치를 줄글이나 목록으로)")
    ap.add_argument("--exemplars", default=str(ROOT / "exemplars"))
    ap.add_argument("--title", default="")
    ap.add_argument("--model", default="qwen3.5:9b")
    ap.add_argument("-n", type=int, default=3)
    ap.add_argument("-k", type=int, default=2, help="예시 글 수")
    ap.add_argument("--temperature", type=float, default=0.95)
    ap.add_argument("--max-tokens", type=int, default=1200)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("-o", "--output", default="-")
    args = ap.parse_args()

    rng = random.Random(args.seed)
    cards = read_text(args.cards)
    best = None
    for i in range(args.n):
        exs = load_exemplars(args.exemplars, args.k, rng)
        prompt = build_prompt(cards, exs, args.title)
        text = generate(args.model, prompt, args.temperature, args.max_tokens, args.seed + i)
        if not text:
            continue
        s, _ = score.judge(score.measure(text))
        print(f"후보 {i + 1}: 점수 {s}, {len(text)}자", file=sys.stderr)
        if best is None or s < best[0]:
            best = (s, text)
    if best is None:
        sys.exit("후보를 만들지 못했다. ollama serve가 켜져 있는지 확인")
    print(f"선택: 점수 {best[0]}", file=sys.stderr)
    write_text(args.output, best[1] + "\n")


if __name__ == "__main__":
    main()
