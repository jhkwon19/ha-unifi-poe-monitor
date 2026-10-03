# Home Assistant용 UniFi PoE Monitor

UniFi Network의 16포트 PoE 스위치에서 포트별 PoE 출력 전력을 읽어 Home
Assistant 센서로 제공하는 커스텀 통합 구성요소입니다.

현재 구현은 API 키로 로컬 UniFi 콘솔에 접속하며, 선택한 스위치와 모든 센서를
Home Assistant의 **기기 하나**로 등록합니다.

## 현재 구현된 기능

- UniFi API 키를 `X-API-Key` 헤더로 사용
- 설정 화면에서 로컬 콘솔 주소, API 키, 사이트 ID 및 SSL 검증 여부 입력
- 해당 사이트에서 16포트 UniFi 스위치를 검색한 뒤 대상 스위치 선택
- 스위치 MAC 주소를 고유 식별자로 사용하여 중복 등록 방지
- 5초마다 전력 데이터 갱신
- 연결 실패나 스위치 오프라인 상태를 Home Assistant의 업데이트 실패로 처리
- 모든 센서를 동일한 스위치 기기에 연결
- Home Assistant 재시작 후 누적 에너지 값 복원

## 생성되는 센서

| 센서 | 단위 | Home Assistant 분류 | 설명 |
|---|---:|---|---|
| `Port N PoE power` | W | `power`, `measurement` | 각 PoE 지원 포트가 현재 공급하는 전력 |
| `Total PoE power` | W | `power`, `measurement` | 전체 PoE 포트가 현재 공급하는 전력 합계 |
| `Total PoE energy` | kWh | `energy`, `total_increasing` | 전체 PoE 출력 전력을 시간에 따라 적분한 누적 사용량 |

테스트한 **USW Lite 16 PoE**는 16개 물리 포트 중 1~8번만 PoE를 지원합니다.
따라서 이 모델에서는 다음과 같이 총 10개 센서가 생성됩니다.

- 포트 1~8의 개별 PoE 전력 센서 8개
- 전체 PoE 전력 센서 1개
- 누적 PoE 에너지 센서 1개

포트 9~16은 PoE 미지원 포트이며 UniFi에서 전력값을 제공하지 않으므로 전력
센서를 생성하지 않습니다. 다른 16포트 모델에서는 API가 PoE 지원으로 보고한
포트에 대해서만 센서를 생성합니다.

## 측정값 계산 방식

포트별 전력은 UniFi 응답의 `port_table[].poe_power` 값을 사용합니다.

전체 전력은 스위치가 제공하는 `total_used_power` 값을 우선 사용합니다. 이 값이
없으면 모든 PoE 지원 포트의 전력값이 정상적으로 들어온 경우에만 포트값을
합산합니다. 일부 포트 데이터가 빠졌을 때 불완전한 합계를 정상값처럼 표시하지
않습니다.

누적 에너지는 연속된 전체 전력 측정값을 사다리꼴 방식으로 적분하여 kWh로
계산합니다. 계산식은 다음과 같습니다.

```text
증가 에너지(kWh) = (이전 전력 + 현재 전력) × 경과 시간(초) ÷ 7,200,000
```

누적값은 Home Assistant의 `RestoreSensor`로 복원됩니다. Home Assistant가 중지된
시간이나 API 연결이 끊긴 구간은 임의로 추정하지 않습니다. 따라서 장시간 중단이
있으면 실제 PoE 사용량보다 누적값이 작을 수 있습니다.

## 검증된 환경과 API

다음 환경에서 실제 API 키를 사용해 읽기 요청을 검증했습니다.

- 대상 장비: **USW Lite 16 PoE** (`USL16LP`)
- 물리 포트: 16개
- PoE 지원 포트: 1~8번
- 인증 방식: `X-API-Key`
- 사이트: `default`
- 테스트 시 포트별 전력 합계와 `total_used_power` 값이 일치함

공식 UniFi Network API의 문서화된 최신 통계 응답에는 포트별 소비 전력 값이
없습니다. 이 통합은 API 키로 접근 가능한 다음 로컬 Network 통계 경로를
사용합니다.

```text
/proxy/network/api/s/{site}/stat/device
```

이 응답에서 `port_table[].poe_power`와 `total_used_power`를 읽습니다. 해당 경로는
현재 공개된 공식 Network API 명세에 포함되지 않은 기존 통계 경로이므로 UniFi
Network 업데이트 후 응답 형식이나 접근 가능 여부가 바뀔 수 있습니다.

## HACS로 설치

이 저장소는 HACS 사용자 정의 저장소 형식을 지원합니다.

1. Home Assistant에서 **HACS → 통합 구성요소**로 이동합니다.
2. 오른쪽 위 메뉴에서 **사용자 정의 저장소**를 엽니다.
3. 저장소 주소에 다음 URL을 입력합니다.

   ```text
   https://github.com/jhkwon19/ha-unifi-poe-monitor
   ```

4. 유형으로 **통합 구성요소(Integration)**를 선택하고 저장소를 추가합니다.
5. HACS에서 **UniFi PoE Monitor**를 찾아 다운로드합니다.
6. Home Assistant를 다시 시작합니다.
7. **설정 → 기기 및 서비스 → 통합 구성요소 추가**에서 **UniFi PoE Monitor**를
   검색하고 연결 정보를 입력합니다.

현재 HACS 기본 저장소에는 등록되어 있지 않으므로 처음 한 번은 사용자 정의
저장소 URL을 추가해야 합니다.

## 수동 설치

1. 이 저장소의 `custom_components/unifi_poe_monitor` 디렉터리를 Home Assistant의
   `config/custom_components/` 아래에 복사합니다.
2. Home Assistant를 다시 시작합니다.
3. **설정 → 기기 및 서비스 → 통합 구성요소 추가**로 이동합니다.
4. **UniFi PoE Monitor**를 검색합니다.
5. 다음 값을 입력합니다.
   - 컨트롤러 URL: 로컬 UniFi 콘솔 주소(예: `https://192.168.1.1`)
   - UniFi API 키
   - 사이트 ID: 일반적으로 `default`
   - SSL 인증서 검증 여부
6. 검색된 16포트 PoE 스위치를 선택합니다.

로컬 UniFi 콘솔이 자체 서명 인증서를 사용한다면 설정 화면에서 **SSL 인증서
검증**을 끄십시오. 공인 또는 내부 신뢰 인증서를 사용한다면 검증을 켜두는 것이
좋습니다.

## Home Assistant 에너지 대시보드 설정

에너지 대시보드에서 **개별 기기 → 기기 추가**를 선택한 뒤 다음과 같이
연결합니다.

| 에너지 대시보드 항목 | 선택할 센서 |
|---|---|
| 기기 에너지 사용량 | `Total PoE energy` |
| 기기 전력 소비량 | `Total PoE power` |

누적 에너지 센서는 `kWh`, `device_class: energy`, `state_class:
total_increasing`으로 등록됩니다. 전체 전력 센서는 `W`, `device_class: power`,
`state_class: measurement`로 등록됩니다. 따라서 Home Assistant가 장기 통계를
생성한 뒤 에너지 대시보드의 선택 목록에 표시될 수 있는 형태입니다.

새 센서는 장기 통계가 처음 생성될 때까지 에너지 대시보드 선택 목록에 바로
나타나지 않을 수 있습니다.

## 측정 범위에 대한 주의사항

이 통합이 측정하는 값은 스위치가 각 포트로 내보내는 **PoE 출력 전력**입니다.
스위치 본체의 CPU, 팬, 전원 변환 손실 등 자체 동작에 필요한 전력은 포함하지
않습니다. UniFi 응답에서 스위치 AC 입력 측 전체 소비 전력은 제공되지 않았습니다.

따라서 `Total PoE power`와 `Total PoE energy`는 스위치 전체 콘센트 소비량이
아니라 연결된 PoE 장비들에 공급된 전력과 그 누적값입니다. 스위치 자체 소비량을
포함한 실제 전기 사용량이 필요하면 스위치 전원 입력에 별도 전력계를 설치해야
합니다.

## 개발용 `.env`

저장소 루트의 `.env` 파일은 실제 API 응답을 읽기 전용으로 검증할 때만
사용합니다.

```dotenv
UNIFI_API_KEY=발급받은_API_키
UNIFI_BASE_URL=https://로컬_UniFi_콘솔_주소
```

`.env`는 `.gitignore`에 포함되어 있으며 Home Assistant 통합 실행 중에는 읽지
않습니다. Home Assistant에서는 통합 설정 화면에 API 키를 별도로 입력해야 합니다.
API 키가 들어 있는 `.env` 파일을 저장소에 커밋하거나 외부에 공유하지 마십시오.

## 현재 제한 사항

- 현재 설정 흐름은 물리 포트가 정확히 16개인 UniFi 스위치만 선택 대상으로 표시
- 포트별 누적 에너지 센서는 제공하지 않으며 포트별 순간 전력만 제공
- 전체 누적 에너지는 UniFi가 제공한 누적 계량값이 아니라 5초 간격 전력값을
  Home Assistant에서 적분한 값
- Home Assistant 또는 통합이 중단된 시간의 에너지는 소급 계산하지 않음
- 문서화되지 않은 기존 UniFi 통계 경로에 의존하므로 향후 호환성이 달라질 수 있음

## 라이선스

이 프로젝트는 [MIT License](LICENSE)로 배포됩니다.
