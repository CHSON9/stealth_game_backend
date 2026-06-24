# STEALTH! 실시간 사람 투명화 기반 스텔스 시스템 (Backend)

##  프로젝트 개요
* 실시간 멀티 카메라 입력 및 AI 컴퓨터 비전 엔진을 활용한 스텔스 인터랙티브 게임 시스템의 백엔드 
* **본인 담당 역할:** 프로젝트 전반의 **REST API 설계, Flask 기반 백엔드 서버 구축, 데이터베이스 스키마 설계 및 Socket.io 실시간 이벤트 제어 모듈 구현**을 전담함 (AI 컴퓨터 비전 알고리즘 및 파이프라인 파트는 다른 팀원이 담당함).

---

## 🛠 기술 스택
* **Language:** Python
* **Framework:** Flask, Flask-SocketIO, Flask-CORS
* **Database:** MySQL
* **Documentation:** Swagger (game_api_swagger_v2.py)

---

## 📂 파일 구조 및 담당 업무
올라간 레포지토리 파일 기준 본인이 직접 구현하고 연동한 핵심 내역임.

```text
├── game_server_v2.py           # Flask + Socket.io 통합 백엔드 구동 메인 서버 코어
└── game_api_swagger_v2.py     # 프론트엔드 협업용 REST API 엔드포인트 Swagger 문서 정의 파일
