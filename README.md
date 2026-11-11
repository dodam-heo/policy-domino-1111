# 정책 도미노

상위 정책이 바뀌면 **어느 공공기관의 어떤 사업·업무 기준을 어떻게 바꿔야 하는지** 공식 근거를 연결해 확인하는 웹 애플리케이션입니다. 중앙부처·지방자치단체·교육청·공공기관을 대상으로 합니다.

## 실행

Python 3.12 이상을 사용합니다.

```sh
python -m pip install 'pypdf>=5,<7'
python -m unittest discover -s tests -v
LAW_OC=dori python -m unified.engine --root data --streams 6 --details 60
python -m unified.gov24 --root data
python -m unified.impact --root data
python -m unified.publish --root data --output site/data.json
python -m http.server 8000 --directory site
```

브라우저에서 http://localhost:8000 을 엽니다. 사이트 이용자는 설치할 필요가 없습니다.

## 구성

- `unified/engine.py`: 법령·행정규칙(훈령·예규·고시·공고·지침·기타)·자치법규의 현행/연혁 목록, 판본 수집과 비교. 실패 구간과 대기 문서는 다음 실행에서 이어 처리합니다.
- `unified/attachments.py`: 공식 첨부 PDF·DOCX·HWPX를 보관하고 텍스트를 추출합니다. 읽지 못한 파일이나 이미지 표는 미확인 상태를 유지합니다.
- `unified/gov24.py`: 정부24 공공서비스 운영기관·지원대상·선정기준·법적 근거를 페이지별로 갱신합니다.
- `unified/impact.py`: 변경 조문과 공식 사업 운영근거를 대조합니다. 이름 유사성만으로 기관을 연결하지 않습니다.
- `unified/ai.py`: 호환 API를 통해 기관별 설명을 생성하고 원문 인용을 검사합니다. 제공자는 설정으로 교체할 수 있습니다.
- `unified/publish.py`, `site/`: 목록 필터, 기관 필터, 변경 핵심, 기관별 조치, 접을 수 있는 신구 비교를 제공합니다.
- `unified/audit.py`, `unified/migrate.py`: 과거 자료의 최초 대조·재사용 도구입니다. 운영 파이프라인에서는 실행하지 않습니다. 재사용 텍스트는 공식 원문을 재확인하기 전 완전한 원문으로 간주하지 않습니다.

원문은 `data/documents/`에 판본별로 압축 저장하고 비교·기관 연결은 별도 작은 파일로 누적합니다. 매 실행마다 과거의 거대한 JSON 전체를 다시 생성하지 않습니다. 웹 목록과 선택한 상세 데이터도 분리합니다.

## 자동 실행과 설정

매시간 `.github/workflows/unified.yml` 하나가 검증 → 수집 → 공공서비스 갱신 → 영향분석 → 화면 생성 → 데이터 저장 → 배포를 실행합니다.

| 설정 | 용도 |
|---|---|
| Variable `LAW_OC` | 법제처 인증 식별값. 기본 `dori` |
| Secret `GOV24_SERVICE_KEY` | 정부24 자료 갱신. 미설정 시 보관된 자료 사용 |
| Secret `GEMINI_API_KEY`, `PD_LLM_API_KEY` 또는 `OPENAI_API_KEY` | AI 설명 API 인증 |
| Variable `PD_LLM_MODEL` | 사용할 모델 이름. 기본 `gemini-3.5-flash-lite` |
| Variable `PD_LLM_URL` | 모델 API 주소. 기본 Gemini 공식 호환 API |
| Variable `PD_LLM_MAX_REQUESTS` | 실행당 신규 설명 한도. 기본 60, 기존 결과 재사용 후 다음 실행에서 이어 처리 |

Pages의 배포 원본은 **Settings → Pages → GitHub Actions**로 설정합니다.

## 해석 기준

수집된 판본 수는 전수 수집 완료를 의미하지 않습니다. 본문 차이를 확인해도 첨부가 미확인이면 추가 확인 대상으로 표시합니다. 기관 연결이 없는 경우 임의 기관을 생성하지 않습니다. 연결된 사업의 실제 반영 완료 여부는 별도의 공식 확인 없이는 판정하지 않습니다. AI 원문 인용 검사는 설명 전체의 의미적 정확성을 보장하지 않습니다.

공식 HWPX 표는 행·열의 이름을 보존해 비교합니다. PDF/HWPX 첨부 순서가 바뀌어도 대응 표 항목으로 비교하며, 공식 XML과 저장된 첨부를 새 파서로 다시 읽을 수 있습니다. 기관 연결은 정확한 변경 조문 인용, 고시의 상위법 위임과 사업 적용 기준, 또는 같은 정책 대상·상위법·종전 운영금액이 함께 일치하는 경우에만 생성합니다.

AI는 변경 정책별 핵심 요약과 기관·사업별 설명을 별도로 생성하며, 기존 결과를 재사용하고 남은 건은 다음 실행에서 계속 처리합니다. 새 저장소에는 별도로 API Secret이 등록되어야 하며, 인증 정보가 없으면 AI 호출은 실행되지 않습니다.

현재 배포는 Gemini를 사용합니다. 기존 `OPENAI_API_KEY` 이름에 등록한 Gemini 키도 읽으며, Secret 이름이 제공자를 결정하지 않습니다. UI 수정은 `[ui-only]` 커밋으로 수집 대기 없이 배포할 수 있습니다. 공식 자료 수집은 실행당 10분 범위에서 처리한 상태를 저장하고 다음 실행에서 이어집니다.
