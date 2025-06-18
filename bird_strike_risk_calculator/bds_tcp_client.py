import socket
import json
import threading
import time
import queue
import logging
from typing import Optional, Dict, Any
from enum import Enum

class RiskLevel(Enum):
    """위험도 레벨 정의"""
    BR_HIGH = "BR_HIGH"
    BR_MEDIUM = "BR_MEDIUM"
    BR_LOW = "BR_LOW"
    BR_NORMAL = "BR_NORMAL"

class BDSTCPClient:
    """BDS와 Main Server 간의 TCP 통신을 담당하는 클래스"""
    
    def __init__(self, host: str = "localhost", port: int = 5200, 
                 min_send_interval: float = 1.0):
        """
        TCP 클라이언트 초기화
        
        Args:
            host: Main Server 호스트 주소
            port: Main Server 포트 번호 (기본: 5200)
            min_send_interval: 최소 메시지 전송 간격 (초)
        """
        self.host = host
        self.port = port
        self.min_send_interval = min_send_interval
        
        # 연결 관리
        self.socket: Optional[socket.socket] = None
        self.connected = False
        self.running = False
        
        # 메시지 큐 및 상태 관리
        self.message_queue = queue.Queue()
        self.last_sent_risk = None
        self.last_send_time = 0
        
        # 스레드 관리
        self.sender_thread: Optional[threading.Thread] = None
        self.reconnect_thread: Optional[threading.Thread] = None
        
        # 로깅 설정
        self.logger = logging.getLogger(__name__)
        
    def start(self) -> bool:
        """TCP 클라이언트 시작"""
        if self.running:
            self.logger.warning("TCP 클라이언트가 이미 실행 중입니다.")
            return True
            
        self.running = True
        
        # 초기 연결 시도
        if not self._connect():
            self.logger.error("초기 연결에 실패했습니다. 재연결을 시도합니다.")
        
        # 메시지 전송 스레드 시작
        self.sender_thread = threading.Thread(target=self._sender_worker, daemon=True)
        self.sender_thread.start()
        
        # 재연결 스레드 시작
        self.reconnect_thread = threading.Thread(target=self._reconnect_worker, daemon=True)
        self.reconnect_thread.start()
        
        self.logger.info(f"BDS TCP 클라이언트가 시작되었습니다. ({self.host}:{self.port})")
        return True
    
    def stop(self):
        """TCP 클라이언트 중지"""
        self.running = False
        self._disconnect()
        
        # 스레드 종료 대기
        if self.sender_thread and self.sender_thread.is_alive():
            self.sender_thread.join(timeout=2.0)
        if self.reconnect_thread and self.reconnect_thread.is_alive():
            self.reconnect_thread.join(timeout=2.0)
            
        self.logger.info("BDS TCP 클라이언트가 중지되었습니다.")
    
    def send_risk_update(self, risk_level: RiskLevel, additional_data: Optional[Dict[str, Any]] = None):
        """
        위험도 업데이트 메시지 전송
        
        Args:
            risk_level: 위험도 레벨
            additional_data: 추가 데이터 (선택사항)
        """
        current_time = time.time()
        
        # 중복 메시지 필터링 (같은 위험도 레벨이고 최소 간격 미달)
        if (self.last_sent_risk == risk_level and 
            current_time - self.last_send_time < self.min_send_interval):
            return
        
        # 위험도 레벨을 Main Server 형식으로 변환
        br_result = self._convert_risk_level(risk_level)
        
        message = {
            "type": "event",
            "event": "BR_CHANGED", 
            "result": br_result,
            "timestamp": current_time
        }
        
        # 추가 데이터가 있으면 포함
        if additional_data:
            message.update(additional_data)
        
        # 메시지 큐에 추가
        try:
            self.message_queue.put_nowait(message)
            self.last_sent_risk = risk_level
            self.last_send_time = current_time
        except queue.Full:
            self.logger.warning("메시지 큐가 가득 참. 메시지를 버립니다.")
    
    def send_heartbeat(self):
        """하트비트 메시지 전송"""
        message = {
            "type": "heartbeat",
            "timestamp": time.time(),
            "status": "alive"
        }
        
        try:
            self.message_queue.put_nowait(message)
        except queue.Full:
            self.logger.warning("하트비트 메시지 큐가 가득 참.")
    
    def send_connection_status(self, status: str):
        """연결 상태 메시지 전송"""
        message = {
            "type": "connection",
            "status": status,
            "timestamp": time.time()
        }
        
        try:
            self.message_queue.put_nowait(message)
        except queue.Full:
            pass  # 연결 상태 메시지는 중요하지 않으므로 조용히 무시
    
    def _convert_risk_level(self, risk_level: RiskLevel) -> str:
        """위험도 레벨을 Main Server 형식으로 변환"""
        return risk_level.value  # enum 값을 그대로 반환
    
    def _connect(self) -> bool:
        """Main Server에 연결"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(5.0)  # 5초 타임아웃
            self.socket.connect((self.host, self.port))
            self.connected = True
            
            self.logger.info(f"Main Server에 연결되었습니다. ({self.host}:{self.port})")
            self.send_connection_status("connected")
            return True
            
        except Exception as e:
            self.logger.error(f"연결 실패: {e}")
            self._disconnect()
            return False
    
    def _disconnect(self):
        """연결 해제"""
        self.connected = False
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            self.socket = None
    
    def send_message(self, message: Dict):
        """메시지 전송"""
        if not self.connected:
            return False
            
        try:
            # JSON 문자열로 변환
            message_str = json.dumps(message)
            message_bytes = message_str.encode('utf-8')
            
            # 메시지 길이를 4바이트로 전송
            length_bytes = len(message_bytes).to_bytes(4, byteorder='big')
            self.socket.sendall(length_bytes)
            
            # 실제 메시지 전송
            self.socket.sendall(message_bytes)
            return True
            
        except Exception as e:
            print(f"❌ 메시지 전송 오류: {e}")
            self.connected = False
            return False
    
    def _sender_worker(self):
        """메시지 전송 워커 스레드"""
        while self.running:
            try:
                # 큐에서 메시지 가져오기 (1초 타임아웃)
                message = self.message_queue.get(timeout=1.0)
                
                # 연결되어 있으면 메시지 전송
                if self.connected:
                    self.send_message(message)
                else:
                    # 연결되지 않았으면 다시 큐에 넣기 (중요한 메시지만)
                    if message.get("type") == "event":
                        try:
                            self.message_queue.put_nowait(message)
                        except queue.Full:
                            pass
                
                self.message_queue.task_done()
                
            except queue.Empty:
                continue
            except Exception as e:
                self.logger.error(f"메시지 전송 워커 오류: {e}")
    
    def _reconnect_worker(self):
        """재연결 워커 스레드"""
        reconnect_interval = 5.0  # 5초마다 재연결 시도
        last_heartbeat = time.time()
        
        while self.running:
            current_time = time.time()
            
            # 연결되지 않았으면 재연결 시도
            if not self.connected:
                self.logger.info("재연결을 시도합니다...")
                if self._connect():
                    last_heartbeat = current_time
            
            # 연결되어 있으면 주기적으로 하트비트 전송
            elif current_time - last_heartbeat > 30.0:  # 30초마다 하트비트
                self.send_heartbeat()
                last_heartbeat = current_time
            
            time.sleep(reconnect_interval)
    
    def get_status(self) -> Dict[str, Any]:
        """클라이언트 상태 정보 반환"""
        return {
            "connected": self.connected,
            "running": self.running,
            "host": self.host,
            "port": self.port,
            "queue_size": self.message_queue.qsize(),
            "last_sent_risk": self.last_sent_risk.value if self.last_sent_risk else None,
            "last_send_time": self.last_send_time
        }


# 사용 예시
if __name__ == "__main__":
    # 로깅 설정
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # TCP 클라이언트 생성 및 시작
    client = BDSTCPClient(host="localhost", port=5200)
    client.start()
    
    try:
        # 테스트 메시지 전송
        time.sleep(2)
        client.send_risk_update(RiskLevel.WARNING, {"bird_count": 3, "distance": 150.5})
        time.sleep(2)
        client.send_risk_update(RiskLevel.CRITICAL, {"bird_count": 5, "distance": 50.2})
        time.sleep(2)
        client.send_risk_update(RiskLevel.NORMAL)
        
        # 상태 확인
        print("클라이언트 상태:", client.get_status())
        
        # 10초 대기
        time.sleep(10)
        
    except KeyboardInterrupt:
        print("\n프로그램을 종료합니다...")
    finally:
        client.stop() 