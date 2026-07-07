<div align="center">

[中文](README.zh.md) | [English](README.md) | [日本語](README.ja.md) | **한국어**

</div>

<p align="center">
  <img src="assets/hero.svg" alt="SearchOS — 단일 사실 검색부터 전 영역 리서치까지, 인용이 달린 관계형 스키마 완성으로 통합" width="100%">
</p>

<h3 align="center">오픈 도메인 정보 탐색을 위한 멀티 에이전트 협업 시스템</h3>

<p align="center">
  <a href="https://antins-labs.github.io/SearchOS/"><img src="https://img.shields.io/badge/🌐_Website-searchos-2563EB?style=for-the-badge" alt="Website"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.11+"></a>
  <a href="https://github.com/langchain-ai/langgraph"><img src="https://img.shields.io/badge/Built_with-LangGraph-1C3C3C?style=for-the-badge&logo=langchain&logoColor=white" alt="LangGraph"></a>
  <a href="https://github.com/Textualize/textual"><img src="https://img.shields.io/badge/TUI-Textual-0B0B0B?style=for-the-badge&logo=gnometerminal&logoColor=white" alt="Textual TUI"></a>
  <a href="LEGAL.md"><img src="https://img.shields.io/badge/License-MIT-0E9B9B?style=for-the-badge" alt="License: MIT"></a>
</p>

<p align="center">
  <i>운영체제가 프로세스를 스케줄링하듯 검색을 스케줄링합니다: 오픈 도메인 질문을 정규화된
  커버리지 맵으로 컴파일하고, 빈 셀을 파이프라인 병렬 서브 에이전트에게 배정하며, 모든 증거를
  출처와 함께 공유 증거 그래프에 기록하고, 마지막으로 <b>검색 상태</b>로부터 인용이 달린 답을
  합성합니다 —— 상태는 시스템 안에 있고, 대화 히스토리 안에 있지 않습니다.</i>
</p>

<p align="center">
  <img src="assets/main.png" alt="SearchOS 시스템 개요: 멀티 에이전트 협업 + 미들웨어 + SOCM + 스킬 시스템" width="95%">
</p>

<p align="center">
  <a href="https://youtu.be/DZNXxMcxnMQ">
    <img src="assets/searchos-demo.gif" alt="SearchOS 데모: 터미널 TUI에서 실제 쿼리 실행 → 멀티 에이전트가 병렬로 테이블을 채움 → 웹 프런트엔드에서 합성된 답변 확인" width="95%">
  </a>
</p>

<p align="center">
  🎬 <b><a href="https://youtu.be/DZNXxMcxnMQ">전체 데모 영상 (YouTube)</a></b>
</p>

> **▶️ 빠른 실행:**
>
> ```bash
> pip install -e . && python -m searchos "2025년 QS 학과별 랭킹 각 분야 상위 5개 대학과 지원 마감일"
> ```
>
> 첫 실행 시 자동으로 **설정 마법사**가 시작됩니다: 모델 프로바이더(각사 coding plan / 종량제 API / 로컬 배포)를 선택하고 API 키만 입력하면 바로 동작합니다.
> 또는 `python -m searchos`로 풀스크린 TUI에 들어가 작업 파견, 도구 스트림, 커버리지 맵의 성장을 실시간으로 볼 수 있습니다.
> `./web/start.sh`로 REST/WS API(`:8000`) + 웹 프런트엔드(`:3000`)를 한 번에 띄워 브라우저에서 검색을 실행하고 에이전트 월과 커버리지 맵을 라이브로 볼 수도 있습니다.

## 📣 News

- **2026-07-05** — 오픈소스 멀티 프로바이더 지원: `SF_PROVIDER` 한 줄로 21개 프리셋에 연결——각사 Coding Plan(즈푸 / Kimi / MiniMax / 알리바바 / Volcengine, Anthropic 프로토콜), 종량제 API(DeepSeek / OpenAI / OpenRouter / SiliconFlow / Gemini / xAI…), 로컬 배포(Ollama / vLLM). 첫 실행 시 CLI 설정 마법사 + 플러그형 검색 백엔드(Serper / Tavily). 추출 같은 고빈도 롤은 각사의 경량 모델로 자동 전환해 비용 절감. 🔌
- **2026-07-02** — 멀티 턴 후속 질문에 즉답: 후속 질문은 이전 라운드의 커버리지 맵을 이어받아, 답이 이미 테이블에 있으면 재검색하지 않습니다. 초장문 스킬 페이로드의 분할 추출도 출시. 🧠
- **2026-06-25** — 인터랙티브 TUI 커맨드 셸: `/skill` 접이식 다중 선택, 실행 중 실시간 개입(steering), 도구 스트림 화면 표시. 스킬 라이브러리를 core / catalog / runtime 3계층으로 재구성. split-tunnel 이그레스——중국 내 사이트는 직접 연결, 해외는 프록시 경유로 한 번의 실행에서 국내외 데이터 소스에 모두 도달. 🖥️

## ✨ 핵심 하이라이트

- 🗂️ **검색 상태를 시스템 자산으로 (SOCM)** — 작업 큐·증거 그래프·커버리지 맵을 모든 에이전트가 공유하는 영속화된 상태에 축적. 스냅숏 / 복원 / 리플레이가 가능하며, 수십 턴의 대화 히스토리에 묻히지 않습니다.
- 🧩 **커버리지 맵 주도, 리콜 우선** — 질문을 entity × attribute의 정규화된 멀티 테이블로 모델링. 파견은 항상 "빈 셀"을 겨냥하며, 모든 스키마 셀이 출처 있는 값으로 채워질 때까지 계속됩니다.
- ⚡ **파이프라인 병렬 서브 에이전트** — 여러 search agent의 search → open → find 단계가 에이전트 간에 겹치고, 비동기로 회수되며, 빈 슬롯은 즉시 재사용. 총 실행 시간은 직렬 합계가 아니라 가장 느린 단일 체인에 수렴합니다.
- 🔗 **모든 셀에 인용 포함** — 추출 미들웨어가 (entity, attribute, value, source)를 자동으로 증거 그래프에 기록. 답변은 셀 단위로 출처에 앵커되어 추적·검증이 가능합니다.
- 🛡️ **센서 안전망, 루프 자동 차단** — 모든 도구 호출에 대해 5종의 루프 / 정체 감지를 수행. 먼저 리마인더를 주입해 궤도를 수정하고, 개선되지 않으면 다른 각도에서 재파견합니다.
- 🧰 **스킬 시스템 + 멀티 프로바이더 기본 탑재** — access 스킬이 안티봇 / 로그인 월 뒤의 어려운 사이트를 공략하고, strategy 스킬이 랭킹 / 멀티홉 / 중의성 해소의 방법론을 제공. `SF_PROVIDER` 한 줄로 각사의 coding plan / API / 로컬 배포에 연결.

> 📊 **WideSearch / GISA**의 모든 headline F1에서 선두, 열거형 **Set · F1은 차순위 베이스라인을 +13.4 상회**(자세한 내용은 [평가](#-평가) 참조).

## 🎥 Gallery

<table align="center">
  <tr>
    <td width="50%" align="center">
      <a href="https://youtu.be/YhJdc7Qhr1U" title="SearchOS-demo1 · YouTube에서 보기">
        <img src="assets/gallery/demo1.jpg" alt="SearchOS-demo1" width="100%">
      </a>
      <sub>▶️ <b>SearchOS-demo1</b></sub>
    </td>
    <td width="50%" align="center">
      <a href="https://youtu.be/Qve7GX7yahs" title="SearchOS-demo2 · YouTube에서 보기">
        <img src="assets/gallery/demo2.jpg" alt="SearchOS-demo2" width="100%">
      </a>
      <sub>▶️ <b>SearchOS-demo2</b></sub>
    </td>
  </tr>
  <tr>
    <td width="50%" align="center">
      <a href="https://youtu.be/IA_-sO2avTA" title="SearchOS-demo3 · YouTube에서 보기">
        <img src="assets/gallery/demo3.jpg" alt="SearchOS-demo3" width="100%">
      </a>
      <sub>▶️ <b>SearchOS-demo3</b></sub>
    </td>
    <td width="50%" align="center">
      <a href="https://youtu.be/HxCLoauXoYg" title="SearchOS-demo4 · YouTube에서 보기">
        <img src="assets/gallery/demo4.jpg" alt="SearchOS-demo4" width="100%">
      </a>
      <sub>▶️ <b>SearchOS-demo4</b></sub>
    </td>
  </tr>
  <tr>
    <td colspan="2" align="center">
      <a href="https://youtu.be/-QmjRr_3B1s" title="SearchOS-demo5 · YouTube에서 보기">
        <img src="assets/gallery/demo5.jpg" alt="SearchOS-demo5" width="50%">
      </a>
      <br><sub>▶️ <b>SearchOS-demo5</b></sub>
    </td>
  </tr>
</table>

<p align="center"><sub>썸네일을 클릭하면 YouTube에서 재생됩니다 (데모는 계속 추가 예정)</sub></p>

<!-- 영상 추가: 위의 <td>…</td> 블록을 복사해 youtu.be 링크·assets/gallery 썸네일·제목만 교체하면 됩니다 -->

## 💡 Why SearchOS

범용 에이전트나 Deep Search 에이전트를 장기 검색 작업에 그대로 쓰면 흔히 다음 실패 모드가 나타납니다:

* **과정이 불투명** — 중간 검색 결과가 수십 턴의 대화 히스토리에 묻히고, 컨텍스트 압축 후 사실이 쉽게 유실됩니다. 실행 도중 진행 상황이 보이지 않고, 복원도 리플레이도 불가능합니다.
* **"무한 루프"에 빠지기 쉬움** — 무엇을 이미 조사했는지 기억하지 못합니다: 같은 쿼리를 표현만 바꿔 반복 실행하고, 같은 엔티티의 속성을 다른 서브태스크에서 중복 검색합니다.
* **역할 분담이 모호** — 서브 에이전트가 검색·읽기·기억·요약을 모두 떠안아, 작업이 길어지면 어딘가 반드시 무너집니다: 추출된 필드의 기준이 제각각이고 출처가 사라집니다.
* **못 들어가고, 찾을 줄도 모름** — 안티봇·로그인 월·깊은 디렉터리에 막혀 어려운 사이트를 열지 못합니다. 랭킹·멀티홉·중의성 해소 같은 복잡한 문제는 검색 횟수를 늘리는 것만으로는 풀리지 않습니다.

SearchOS는 이 네 가지 실패에 각각 메커니즘 수준의 해법을 제시합니다:

* **검색 상태를 대화 히스토리에 두지 않음 (SOCM)** — 작업 큐·증거 그래프·커버리지 맵을 모든 에이전트가 공유하는 영속화된 상태(`search_state.json`)에 두어 언제든 스냅숏 / 복원 / 리플레이 가능. 서브 에이전트 쪽은 3계층 컨텍스트(SOCM 스냅숏 → 검색 세그먼트별 에피소드 요약 → 최근 워킹 메모리)로 전체 히스토리를 대체하고, 안정된 프리픽스는 prompt cache 친화적입니다.
* **엔티티 단위 모델링 + 센서의 루프 차단** — 내부는 기본 키 + 속성의 정규화된 멀티 테이블(외래 키 포함). 같은 엔티티의 사실은 한 번만 조사하고, 파견은 항상 커버리지 맵의 빈 셀을 겨냥합니다. LoopSensor는 모든 도구 호출에 대해 5종의 루프 감지(무진전·검색만 하고 읽지 않음·쿼리 중복·하드 루프·상태 증분 제로)를 수행하고, 먼저 리마인더를 주입해 궤도를 수정하며, 개선되지 않으면 `looped`로 표시해 오케스트레이션 계층이 다른 각도에서 재파견합니다.
* **검색과 추출의 분리** — 서브 에이전트는 올바른 페이지를 찾는 데만 집중합니다. 페이지를 열 때마다 추출 미들웨어가 judge 모델로 (entity, attribute, value, source, confidence)를 자동 추출해 증거 그래프에 기록하고, 값의 단위 정규화·원문 발췌 앵커링·해시 보존을 수행합니다——기준이 일관되고 출처를 추적할 수 있습니다.
* **어려운 사이트는 스킬로 공략, 복잡한 문제는 방법론으로 검색** — 검색 에이전트 전용 스킬 시스템을 최초로 도입: 사이트 레벨의 access 스킬이 안티봇 / 로그인 월로 인한 "못 여는" 문제를 해결하고, strategy 검색 방법론이 랭킹 / 멀티홉 / 중의성 해소 같은 "찾을 줄 모르는" 문제를 해결하며, 쿼리별로 라우팅되어 주입됩니다(수량·라우팅·어블레이션은 아래 [스킬 시스템](#-스킬-시스템) 참조).

## 🧩 Framework

```
사용자 쿼리
   │
   ▼
┌─────────────────────────── Orchestrator (유일한 의사결정자) ─────────────────────┐
│   Explore 정찰 → create_schema로 커버리지 맵 구축 → enqueue_tasks 파견           │
│   → check_agents 폴링 → 평가/조정 → 커버리지 충분 또는 예산 소진 → 합성          │
└──────┬──────────────────────────┬─────────────────────────────┬─────────────────┘
       ▼                          ▼                             ▼
  explore_agent              search_agent × N              writer_agent
 (쿼리 분류 / hub 페이지 /  (서브태스크별로 웹 검색,       (SOCM을 읽어
  후보 엔티티 / 검색 플랜)   상태를 직접 쓰지 않음)         인용 달린 섹션 작성)
       │                          │                             │
       └────────────┬─────────────┴─────────────────────────────┘
                    ▼
      3계층 미들웨어: Context → Sensor → Extraction
     (프롬프트 조립 / 예산·루프 모니터링 / judge 기반 자동 증거 추출)
                    │
                    ▼
┌──────────── SOCM · Search-Oriented Context Management (공유 검색 상태) ──────────┐
│  Frontier Memory   작업 큐: priority + blocked_by DAG, 3종 작업이 하나의 풀 공유  │
│  Evidence Graph    증거 그래프: finding / source / confidence,                    │
│                    support-conflict 엣지                                          │
│  Coverage Map      커버리지 맵: entity × attribute, 멀티 테이블 + 외래 키,        │
│                    컬럼 레벨 타입 / 포맷 / 검증                                   │
│  Strategy Memory   전략과 실패의 기억   ·   Writer Outline   ·   Budget           │
└───────────────────────────────────────────────────────────────────────────────────┘
```

한 세션은 다음 6단계를 순환합니다:

1. **Explore** — 정찰병이 선행: 쿼리 타입 판정, hub 페이지 위치 파악, 후보 엔티티와 검색 플랜 생성을 수행하며, 구체적인 속성값은 추출하지 않습니다.
2. **Schema** — Orchestrator가 엔티티 타입별로 정규화된 커버리지 맵(멀티 테이블 + 관계)을 구축. Explore가 발견한 엔티티는 모두 시드 행으로 자리 잡습니다.
3. **Dispatch** — 공백을 자기완결적인 자연어 서브태스크로 분할해 우선순위와 의존관계에 따라 search agent에게 병렬 파견합니다.
4. **Extract** — 페이지를 열 때마다 Extraction 미들웨어가 (entity, attribute, value, source, confidence)를 자동 추출해 증거 그래프에 기록하고 커버리지 맵을 밝힙니다.
5. **Assess** — 서브태스크를 폴링해 회수: 새 엔티티는 테이블에 추가, 나쁜 소스는 블랙리스트, 충돌은 중재로, 빈 셀은 타깃을 좁혀 보완합니다.
6. **Synthesize** — 커버리지 자체 점검을 통과하면 SOCM에서 사용자가 원하는 형식으로 join하여, 항목마다 인용을 달아 출력합니다.

### 출력은 이런 모습입니다

모든 셀에 출처 번호가 앵커되고 문서 끝에 해당 출처가 나열됩니다——"인용이 달린 관계형 스키마 완성"이 결과물로 구현된 모습입니다(실제 실행에서 발췌. 쿼리는 중국어로 *홍콩의 최근 몇 년간 인기 보험을 정리해 줘*):

```markdown
### 홍콩 주요 보험사
| 회사       | 영문명          | 2024 APE 순위 | 2023 보험료 규모 |
|-----------|----------------|--------------|-----------------|
| 友邦保険   | AIA [6]        | 1위 [6]       | 871억 HKD [6]   |
| 保誠       | Prudential [6] | 2위 [6]       | 653억 HKD [6]   |
| 匯豐保険   | HSBC Life [6]  | 3위 [6]       | 555억 HKD [6]   |
| 宏利       | Manulife [6]   | 4위 [6]       | 498억 HKD [6]   |

### 정보 출처
[6] https://www.ia.org.hk/tc/infocenter/press_releases/20250425.html, https://inews.hket.com/…
```

전체 결과물(trajectory·페이지 캐시·SOCM 상태를 포함한 리플레이 가능한 디렉터리)은 `searchos_workspace/<타임스탬프>/`에 있습니다.

## 🚀 설치

Python ≥ 3.11이 필요합니다:

```bash
pip install -e .            # 기본 의존성 (OpenAI/Anthropic 양 프로토콜 클라이언트 포함, coding plan 즉시 사용 가능)
pip install -e ".[eval]"    # 평가용: pandas / numpy / python-dotenv
pip install -e ".[all]"     # 모든 옵션 백엔드: tavily / playwright / crawl4ai / langsmith
```

## ⚙️ 설정

**첫 실행 시 설정 마법사가 자동으로 시작됩니다**: 사용 가능한 모델 설정이 감지되지 않으면 `python -m searchos`가 커맨드라인에서 프로바이더 선택과 API 키 입력을 안내하고 `.env`에 기록합니다(`python -m searchos --setup`으로 언제든 재설정 가능).

수동 설정도 가능합니다——[`.env.example`](.env.example)을 `.env`로 복사하고 `SF_PROVIDER` 프리셋 하나를 골라 해당 API 키만 넣으면 됩니다(12개 모델 롤 바인딩이 자동 생성됩니다):

```bash
# 각사 Coding Plan (Anthropic 프로토콜 구독 엔드포인트, 가성비 우수)
SF_PROVIDER=zhipu-coding      # 또는 kimi-coding / minimax-coding / qwen-coding / volcengine-coding
ZHIPU_API_KEY=xxx

# 또는 종량제 API (OpenAI 프로토콜)
SF_PROVIDER=deepseek          # 또는 moonshot / dashscope / openai / openrouter / siliconflow / gemini ...
DEEPSEEK_API_KEY=xxx

# 또는 로컬 배포
SF_PROVIDER=ollama            # 또는 vllm
SF_MODEL=qwen3:32b

SF_JINA_API_KEY=...           # 옵션: Jina 페칭 (미설정 시 비인증 쿼터 사용, 429가 나기 쉬움)
```

전체 프리셋(각사 엔드포인트·모델 ID·키 발급 방법·알려진 특이사항)은 [`docs/providers.md`](docs/providers.md)를 참조하세요. `SF_PROVIDER`를 설정하지 않으면 [`searchos/config/settings.py`](searchos/config/settings.py) 내장 게이트웨이 기본값(`OPENAI_API_KEY` + `SF_EXTRACTION_API_KEY`)이 사용됩니다.

모든 설정은 `settings.py`에 집약되며 `SF_` 프리픽스 환경 변수로 덮어씁니다. 중첩 필드는 `__`로 구분합니다(부분 덮어쓰기는 기본값과 **깊은 병합**을 하므로 작성한 필드만 변경됩니다). 모델은 **롤** 단위로 바인딩되어(12개 롤 → 모델 프로파일) 어블레이션과 비용 절감이 쉽습니다:

| 자주 쓰는 설정 | 설명 |
| --- | --- |
| `SF_MODEL` / `SF_FAST_MODEL` | 프리셋의 메인 / 경량 모델 덮어쓰기 |
| `SF_API_BASE` | 엔드포인트 덮어쓰기 (국제판 도메인 전환 등) |
| `SF_SEARCH_PROVIDER` | 검색 백엔드: `serper` \| `tavily` \| `ragflow` (미설정 시 보유 키로 추론) |
| `SF_BROWSER_BACKEND` | 페칭 백엔드: `jina` \| `aiohttp` \| `crawl4ai` \| `search_engine` |
| `SF_ROLES__JUDGE=main` | 특정 롤의 모델 프로파일만 교체 (고급 / 어블레이션) |
| `SF_PROFILES__MAIN__TEMPERATURE=0.3` | 단일 프로파일의 필드 레벨 덮어쓰기 (고급 / 어블레이션) |
| `SF_MAX_PARALLEL_AGENTS` | 서브 에이전트 동시 실행 상한 (기본 8) |
| `SF_ENABLE_EXPLORE` / `SF_ENABLE_SKILLS` | 어블레이션 스위치: 정찰 끄기 / 스킬 끄기 |
| `SF_SKIP_SYNTHESIS` | 평가 모드: 합성을 건너뛰고 커버리지 맵에서 바로 테이블 출력 |

## 🧭 빠른 시작

| 커맨드 | 동작 |
| --- | --- |
| `python -m searchos "<query>"` | 단일 쿼리, 결과는 `searchos_workspace/<타임스탬프>/output/report.md`에 기록 |
| `python -m searchos` | 풀스크린 Textual TUI: 실시간 패널, 실행 중 개입, 멀티 턴 후속 질문, `/skill` 스킬 관리 |
| `python -m eval.run --benchmark widesearch --range 1-50` | 평가 실행 (다음 절 참조) |

### 인터랙티브 TUI

`python -m searchos`로 풀스크린 화면에 들어갑니다: 상단은 실시간 대시보드(작업 파견·서브 에이전트 상태·커버리지 맵 성장), 하단은 도구 스트림. 하나의 입력창이 타이밍에 따라 자동으로 분기합니다:

| 타이밍 | 자연어를 입력하면 |
| --- | --- |
| 대기 중 | 새 검색 실행 시작 |
| **실행 중** | **실시간 개입 (steering)**——텍스트가 즉시 실행 중인 Orchestrator에 주입되며 서브 에이전트는 중단되지 않습니다. 제약 추가("2024년 데이터만"), 궤도 수정, 좋은 데이터 소스 제시에 사용 |
| 실행 종료 후 | **멀티 턴 후속 질문**——이전 라운드의 커버리지 맵과 증거를 이어받습니다: 답이 이미 테이블에 있으면 바로 답변(재검색 없음), 없으면 기존 테이블을 증분 확장하며 처음부터 다시 만들지 않습니다 |

슬래시 커맨드는 언제든 사용 가능합니다 (실행 중에도 유효):

| 커맨드 | 별칭 / 단축키 | 동작 |
| --- | --- | --- |
| `/new` | `/clear` · `Ctrl-N` | 새 주제: 대화 히스토리와 커버리지 맵을 비우고, 다음 질문은 새 워크스페이스에서 시작 |
| `/effort [low\|medium\|high\|max]` | — | 투입 레벨: 이터레이션 상한·동시 실행 수·에이전트당 검색 예산·실행 시간 제한·스킬 라우팅 top-k를 한 번에 조정. 인자 없이 실행하면 인터랙티브 선택기가 열리며, 실행 중 변경은 다음 라운드부터 적용 |
| `/skill` | — | 스킬 관리: 인자 없이 실행하면 그룹화된 다중 선택 대화상자 표시. 서브커맨드 `list`(목록), `only <이름…>`(화이트리스트, 접두어 매칭), `on` / `off <이름…>`(켜기/끄기), `all`(라우터에 반환)로 활성 세트를 세밀하게 제어 |
| `/verbose` | `/detail` · `Ctrl-T` | 간략 / 상세 도구 스트림 전환 |
| `/stop` | `/cancel` · `Esc` | 현재 실행 중단 (대기 중 Esc는 프로그램 종료) |
| `/help` | `/?` | 커맨드 도움말 |
| `/quit` | `/exit` · `Ctrl-D` | SearchOS 종료 |

`/effort` 4단계 예산 한눈에 보기 (전역 settings를 수정하며 현재 세션에 즉시 반영. 병렬 서브 에이전트 수는 8로 고정되어 레벨에 따라 변하지 않습니다):

| 레벨 | 오케스트레이션 이터레이션 | 에이전트당 검색 수 | 실행 시간 상한 | 라우팅 top-k |
| --- | :---: | :---: | :---: | :---: |
| `low` | 25 | 10 | 10 min | 20 |
| `medium` (기본) | 50 | 20 | 30 min | 40 |
| `high` | 100 | 35 | 60 min | 60 |
| `max` | 150 | 50 | 120 min | 80 |

설계 문서: [docs/tui-textual-redesign.md](docs/tui-textual-redesign.md).

## 🧰 스킬 시스템

3가지 카테고리의 스킬이 [`searchos/skills/library/`](searchos/skills/library/)에 통합 배치되어 있습니다:

| 카테고리 | 수량 | 설명 |
| --- | --- | --- |
| **access** | 248 | 사이트 레벨 데이터 획득, 도메인명으로 명명 (예: `en_wikipedia_org`). URL 매칭 시 자동 라우팅, 또는 typed 도구로 서브 에이전트가 능동 호출 |
| **strategy** | 40+ | 추론 방법론: `ranking_top_n`, `entity_disambiguation`, `multi_hop_bridge`…, 안티패턴 체크리스트 첨부 가능 |
| **orchestrator** | 소수 | 오케스트레이션 계층 방법론, playbook으로 통째로 주입 |

런타임에는 LLM 라우터가 access 카탈로그를 쿼리 관련 top-k로 사전 필터링합니다(fail-open). 서브 에이전트 파견 시 휴대할 수 있는 스킬은 최대 3개이며, 어떤 access 스킬에도 매칭되지 않는 페이지는 범용 추출 미들웨어로 폴백합니다.

```bash
SEARCHOS_SKILL_ONLY=en_wikipedia_org,ranking_top_n   # 화이트리스트
SEARCHOS_SKILL_LAYERS_DISABLED=access                # 계층 단위 비활성화
SEARCHOS_SKILLS_DISABLED=1                           # 전체 비활성화
```

세션 종료 후 고빈도 도메인을 자동 마이닝해 새 access 스킬을 구워 넣을 수도 있습니다 (`SF_ENABLE_ACCESS_SKILL_GENERATION`, 기본값 꺼짐).

## 📊 평가

**WideSearch**(와이드 테이블 검색)와 **GISA**(오픈 도메인 정보 검색)에서 5개 대표 베이스라인(ReAct / Plan-and-Solve / A-MapReduce / Web2BigTable / Table-as-Search)과 비교. **max@3**(문제당 3회 실행 중 최고값, ×100) headline 점수:

| Benchmark | 지표 | 최강 베이스라인 | **SearchOS** |
| --- | --- | :---: | :---: |
| WideSearch | Item · F1 | 76.0 | **80.1** |
| WideSearch | Row · F1 | 54.5 | **55.6** |
| GISA | Table · F1 | 74.8 | **76.9** |
| GISA | Set · F1 | 63.1 | **76.5** |
| GISA | List · F1 | 67.1 | **68.1** |

SearchOS는 두 벤치마크의 모든 headline F1에서 선두이며, 향상은 주로 **리콜**에서 옵니다——커버리지 맵 주도의 파견이 모든 스키마 셀에 출처 있는 값이 들어갈 때까지 빈 셀을 계속 채웁니다. 완전한 집합을 열거하는 **Set · F1은 차순위 베이스라인을 +13.4 상회**했습니다. 상세 분석(Precision / Recall / EM, 문제 유형별)은 논문을 참조하세요.

## 🗂️ 프로젝트 구조

```
searchos/
├── agents/        Orchestrator (prompt / catalog / scheduler / lifecycle)와 3종 서브 에이전트 정의
├── harness/       SearchSession 메인 루프, 3계층 미들웨어, 합성, 트라젝토리와 대화 로그
├── socm/          공유 검색 상태: Frontier / Evidence Graph / Coverage Map / Strategy
├── tools/         롤별 도구: schema, tasks, writer, simple_browser …
├── skills/        스킬 시스템: core 계약 / catalog 등록과 라우팅 / runtime 실행 / evolution 진화 / library 스킬 라이브러리
├── tui/           Textual 풀스크린 인터페이스 (실시간 대시보드, /skill 관리, 후속 질문과 개입)
├── config/        settings.py (pydantic-settings, SF_ 프리픽스 덮어쓰기) + 모델 롤 바인딩
└── cli.py         python -m searchos 진입점

eval/              평가 프레임워크: run.py 진입점, runner, benchmarks, scorers, reformat
datasets/          WideSearch / GISA / xbench / browsecomp / frames / webwalker
baselines/         비교용 베이스라인 (gpt-oss-simple-browser 등)
eval_results/      평가 출력 (문제당 1 디렉터리, 완전히 리플레이 가능한 세션 포함)
searchos_workspace/ 인터랙티브 실행의 세션 워크스페이스 (타임스탬프 디렉터리)
```

## 🙏 Acknowledgements

SearchOS는 [LangGraph](https://github.com/langchain-ai/langgraph) / [LangChain](https://github.com/langchain-ai/langchain) / [deepagents](https://github.com/langchain-ai/deepagents) 위에 구축되었으며, TUI는 [Textual](https://github.com/Textualize/textual) 기반입니다. 평가 데이터와 공식 스코어러는 [WideSearch](https://github.com/ByteDance-Seed/WideSearch), [GISA](https://github.com/RUC-NLPIR/GISA), xbench 등 벤치마크 원저자의 것이며, 저작권은 각 저자에게 귀속됩니다 (`datasets/` 각 하위 디렉터리의 LICENSE와 [LEGAL.md](LEGAL.md) 참조).

## 📚 Citation

논문(*SearchOS-v1*)은 준비 중이며, 공개 후 이곳을 논문 인용으로 교체할 예정입니다. 그때까지 이 프로젝트가 연구에 도움이 되었다면 리포지토리를 인용해 주세요:

```bibtex
@misc{searchos2026,
  title        = {SearchOS-v1: Towards Robust Open-Domain Information-Seeking Agents Collaboration},
  author       = {Zhang, Yuyao and Gao, Junjie and Wu, Zhengxian and Zhang, Jin and Ma, Shihan and Yao, Yao and Qi, Weiran and Xu, Xingzhong and Yang, Kai and Wen, Ji-Rong and Dou, Zhicheng},
  year         = {2026},
  howpublished = {\url{https://github.com/antins-labs/SearchOS}}
}
```

## 📄 License

MIT. [LEGAL.md](LEGAL.md)도 참조하세요.
