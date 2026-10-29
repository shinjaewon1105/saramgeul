# 사람글 (saramgeul)

AI가 쓴 한국어 글을 사람 글로 바꾸는 Claude Code 스킬이다.

기존 인간화 스킬은 금지어 목록을 들고 원문을 문장 단위로 고친다. 그러면 단어만 바뀌고 뼈대와 조수 말투는 남는다. 이 스킬은 원문에서 내용만 뽑아 새로 쓰고, 진짜 사람 글을 흉내 내며, 형태소 분석 지표와 과정을 모르는 판정 에이전트로 검사한다.

## 설치

```
pip install kiwipiepy
```

이 폴더를 `~/.claude/skills/saramgeul`에 두거나 연결한 뒤, 사람 글 예시와 기준 자료를 받는다.

```
python scripts/fetch_exemplars.py
```
엔진 A(이어쓰기 초안)를 쓰려면 Ollama와 로컬 모델(기본 `qwen3.5:9b`)이 필요하다. 없으면 엔진 B만 쓴다.

## 구성

```
SKILL.md                 절차 (정하기 → 재기 → 카드 → 설계 → 쓰기 → 정리 → 검사 → 고치기 → 실수)
references/
  research.md            설계 근거와 출처
  patterns-ko.md         한국어 AI 티 패턴 (판정용, ID 체계)
  phrases-ko.tsv         score.py가 세는 상투 표현 정규식
  hanjaeo-ko.tsv         쉬운 우리말이 있는 한자어 목록
  structure-ops.md       뼈대를 바꾸는 구체 작업
  judge.md               판정 에이전트 지시문
  typos-ko.md            사람다운 실수 규칙
scripts/
  score.py               AI 냄새 점수 (0~100)
  clean.py               기호 치환, 연결어미 뒤 쉼표 제거
  typo.py                띄어쓰기 생략 등 근거 있는 실수 주입
  local_draft.py         Ollama raw 이어쓰기로 초안 후보 생성
  fetch_exemplars.py     ChatGPT 이전 사람 글(KatFish, 나무위키 덤프)을 받는다
  calibrate.py           KatFish 사람 181편 / AI 590편으로 지표 변별력(AUROC)을 잰다
exemplars/               흉내 낼 사람 글 (fetch_exemplars.py가 채운다)
data/                    내려받은 자료 (저장소에 넣지 않음)
tests/                   샘플과 실행 기록
```

## 스크립트만 따로 쓰기

```
python scripts/score.py 글.md
python scripts/score.py 새글.md --orig 원문.md
python scripts/clean.py 글.md -o 정리.md
python scripts/typo.py 글.md --mode light --seed 1 -o 최종.md
python scripts/local_draft.py 카드.md --title "제목" -n 3 -o 초안.md
```

## score.py 지표

기준값은 `calibrate.py`로 KatFish 논설문(2021년 학생 글 181편, 같은 주제 LLM 글 590편)에 맞췄다. 전체 점수의 AUROC는 0.98, 사람 중앙값은 13점, AI 중앙값은 63점이다.

| 지표 | 사람 중앙값 | AI 중앙값 | AUROC |
|---|---|---|---|
| 연결어미 뒤 쉼표 비율 | 0.00 | 0.19 | 0.93 |
| 쉼표 있는 문장 비율 | 0.13 | 0.61 | 0.93 |
| 상투 표현 (500자당) | 1.0 | 5.4 | 0.88 |
| 품사 3-gram 다양성 | 0.60 | 0.48 | 0.88 (낮을수록 AI) |
| 의존명사, 보조용언 띄어쓴 비율 | 0.75 | 0.93 | 0.85 |
| 한자어 (100어절당) | 0.26 | 1.69 | 0.85 |
| `-적/-성/-화` (100어절당) | 0.92 | 3.89 | 0.81 |
| 문장 길이 변동계수 | 0.42 | 0.31 | 0.81 (낮을수록 AI) |

형식명사 수와 접속부사로 시작하는 문장 비율은 사람과 AI를 거의 가르지 못해(AUROC 약 0.5) 점수에서 뺐다. 사람 논설문 4편 중 1편은 쉼표가 하나도 없고, AI 글은 590편 중 1편뿐이다.

## 출처와 감사

설계 근거는 `references/research.md`에 있다. 패턴 체계는 [im-not-ai](https://github.com/epoko77-ai/im-not-ai)(MIT), [blader/humanizer](https://github.com/blader/humanizer), [Wikipedia: Signs of AI writing](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing)을 참고했고, 쉼표와 띄어쓰기 지표는 [KatFishNet](https://arxiv.org/abs/2503.00032)(ACL 2025)을 따랐다.

## 한계

- `score.py`는 학습된 분류기가 아니다. 점수가 낮다고 GPTZero 같은 상용 탐지기를 넘는다는 보장은 없다.
- 기준값은 학생 논설문 한 장르로 맞췄다. 블로그나 메신저 글은 따로 맞출 자료가 필요하다.
- 다음 단계로 생각하는 것: 사람 글과 AI 글 쌍으로 로컬 모델에 LoRA를 거는 것(arXiv 2605.19516의 HIP 방식). 엔진 A의 내용 정확도 문제를 줄일 수 있다.
