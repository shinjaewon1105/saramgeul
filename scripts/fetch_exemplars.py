"""ChatGPT 이전에 사람이 쓴 한국어 글을 받아 exemplars/와 data/에 둔다.

출처 (둘 다 2022년 11월 ChatGPT 공개 이전 글이다):
- KatFish (github.com/Shinwoo-Park/katfishnet): 2021년 초중고 학생 논설문 사람 글 181편과
  같은 주제의 LLM 글 590편, 논문 초록. 라이선스가 명시돼 있지 않아 저장소에 포함하지 않고
  설치할 때 받는다. 지표 기준값을 맞추는 calibrate.py도 이 데이터를 쓴다.
- 나무위키 2022-03-01 덤프 (huggingface heegyu/namuwiki-extracted, CC BY-NC-SA 2.0).

    python fetch_exemplars.py            # 받고 예시 글을 고른다
    python fetch_exemplars.py --namu 6   # 나무위키 글 수
"""
import argparse
import json
import random
import re
import urllib.request
from pathlib import Path

from ko import ROOT

KATFISH = "https://raw.githubusercontent.com/Shinwoo-Park/katfishnet/main/katfish_dataset/{}.jsonl"
NAMU = "https://datasets-server.huggingface.co/rows?dataset=heegyu/namuwiki-extracted&config=default&split=train&offset={}&length=100"
PERSON = re.compile(r"유튜버|스트리머|BJ|배우|가수|아이돌|선수|출생|태어났|정치인|인물|작가|성우|모델|방송인|감독|\(\d{4}년")
DATA = ROOT / "data"
EX = ROOT / "exemplars"


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "saramgeul"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read().decode("utf-8", errors="replace")


def katfish(name):
    path = DATA / "katfish" / f"{name}.jsonl"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(get(KATFISH.format(name)), encoding="utf-8")
        print(f"받음: {path.relative_to(ROOT)}")
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def looks_copied(text):
    """신문 기사를 옮겨 적은 듯한 글은 거른다: 숫자, 기관명, 인용 보도 표현이 많다."""
    news = len(re.findall(r"\d+(개국|명|억|만|%|월|일|년)|밝혔다|전했다|보도|따르면", text))
    return news / max(len(text) / 500, 1) > 3


def para_split(text):
    """한 덩어리로 붙은 글을 서너 문장씩 문단으로 나눈다. 원문 문장은 고치지 않는다."""
    sents = re.split(r"(?<=[.!?])\s+", text.strip())
    out, cur = [], []
    rng = random.Random(len(text))
    target = rng.randint(3, 5)
    for s in sents:
        cur.append(s)
        if len(cur) >= target:
            out.append(" ".join(cur))
            cur, target = [], rng.randint(2, 6)
    if cur:
        out.append(" ".join(cur))
    return "\n\n".join(out)


def pick_katfish(rng, per_grade):
    rows = katfish("essay")
    sources = []
    for grade, label in (("고등", "논설문-고등"), ("중등", "논설문-중등")):
        pool = [r for r in rows if r["written_by"] == "human" and r["student_grade"] == grade
                and 600 <= len(r["text"]) <= 2500 and not looks_copied(r["text"])]
        rng.shuffle(pool)
        for i, r in enumerate(pool[:per_grade], 1):
            name = f"katfish-{label}-{i}.md"
            (EX / name).write_text(para_split(r["text"]) + "\n", encoding="utf-8")
            sources.append(f"| `{name}` | KatFish essay, {r['topic']} ({grade}, 사람) | 라이선스 미표기, 저장소에 넣지 않음 |")
    abstracts = [r for r in katfish("abstract") if r.get("written_by") == "human" and 400 <= len(r.get("text", "")) <= 1800]
    rng.shuffle(abstracts)
    for i, r in enumerate(abstracts[:per_grade], 1):
        name = f"katfish-초록-{i}.md"
        (EX / name).write_text(r["text"].strip() + "\n", encoding="utf-8")
        sources.append(f"| `{name}` | KatFish abstract (사람) | 라이선스 미표기, 저장소에 넣지 않음 |")
    return sources


def clean_namu(text):
    text = re.sub(r"\[\d+\]|\[\*[^\]]*\]|\[math\([^)]*\)\]", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def pick_namu(rng, n):
    sources, tries = [], 0
    while len(sources) < n and tries < 12:
        tries += 1
        data = json.loads(get(NAMU.format(rng.randrange(0, 570000))))
        for row in data.get("rows", []):
            r = row["row"]
            body = clean_namu(r.get("text", ""))
            hangul = len(re.findall(r"[가-힣]", body))
            if not (700 <= len(body) <= 2500) or hangul / max(len(body), 1) < 0.6:
                continue
            if body.count("\n") < 2 or re.search(r"^\s*[*\-|]", body, re.M):
                continue  # 목록, 표 위주 문서는 거른다
            if PERSON.search(body[:300] + r.get("title", "")):
                continue  # 실존 인물 문서는 넣지 않는다
            name = f"namu-설명-{len(sources) + 1}.md"
            (EX / name).write_text(body + "\n", encoding="utf-8")
            sources.append(f"| `{name}` | 나무위키 \"{r.get('title')}\" (2022-03-01 덤프) | CC BY-NC-SA 2.0 KR |")
            if len(sources) >= n:
                break
    return sources


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--per-grade", type=int, default=4)
    ap.add_argument("--namu", type=int, default=4)
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    EX.mkdir(exist_ok=True)
    for old in list(EX.glob("katfish-*.md")) + list(EX.glob("namu-*.md")):
        old.unlink()
    rows = pick_katfish(rng, args.per_grade) + pick_namu(rng, args.namu)
    table = "\n".join(["| 파일 | 출처 | 라이선스 |", "|---|---|---|", *rows])
    (EX / "SOURCES.md").write_text(
        "# 예시 글 출처\n\n`fetch_exemplars.py`가 만든 목록이다. 모두 ChatGPT 공개(2022-11) 이전에 사람이 쓴 글이다.\n"
        "KatFish 글은 학생이 쓴 원문 그대로라 띄어쓰기 실수가 남아 있다. 고치지 않는다. "
        "한 덩어리로 붙어 있던 글은 문장을 고치지 않고 문단만 나눴다.\n\n" + table + "\n",
        encoding="utf-8")
    print(f"예시 글 {len(rows)}개를 exemplars/에 썼다")


if __name__ == "__main__":
    main()
