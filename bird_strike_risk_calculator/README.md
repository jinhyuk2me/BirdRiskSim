# TCP Communication Module

BirdRiskSim의 TCP 통신 관련 모듈들을 모아둔 디렉토리입니다.

## 📁 파일 구성

### `bds_tcp_client.py`
- **BDSTCPClient**: BDS에서 Main Server로 위험도 정보를 전송하는 TCP 클라이언트
- **RiskLevel**: 위험도 레벨 enum (NORMAL, LOW, CAUTION, HIGH, WARNING, CRITICAL)

### `test_tcp_server.py`
- **TestTCPServer**: 개발/테스트용 TCP 서버
- 포트 5200에서 실행되어 BDS 클라이언트의 메시지를 수신하고 출력

## 🚀 사용법

### 1. 테스트 서버 실행
```bash
python tcp_communication/test_tcp_server.py
```

### 2. 실시간 파이프라인 실행 (TCP 클라이언트 포함)
```bash
python data/scripts/real_time_pipeline.py
```

### 3. 모듈 import
```python
from tcp_communication import BDSTCPClient, RiskLevel, TestTCPServer
```

## 📊 메시지 형식

### 위험도 이벤트
```json
{
    "type": "event",
    "event": "BR_CHANGED",
    "result": "BR_MEDIUM",
    "timestamp": 1703123456.789,
    "distance": 150.5,
    "relative_speed": -25.3,
    "ttc": 6.2,
    "risk_score": 45.8
}
```

### 하트비트
```json
{
    "type": "heartbeat",
    "timestamp": 1703123456.789,
    "status": "alive"
}
```

### 연결 상태
```json
{
    "type": "connection",
    "status": "connected",
    "timestamp": 1703123456.789
}
```

## 🔧 설정

- **호스트**: localhost (기본값)
- **포트**: 5200 (기본값)
- **재연결 간격**: 5초
- **하트비트 간격**: 30초 