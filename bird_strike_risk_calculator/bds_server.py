#!/usr/bin/env python3
"""
🎯 Real-time BDS (Bird Detection System) Server Pipeline

실시간 항공기 탐지, 삼각측량, 트래킹 및 위험도 계산을 수행하는 통합 서버
"""

import os
import gc
import time
import json
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from pathlib import Path
import numpy as np
import cv2
import threading
import queue
import glob
import pandas as pd
import sys
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed

# 프로젝트 루트를 sys.path에 추가
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

# 🎯 항공 감지 모듈 import (YOLO 로직 통합)
from aviation_detector import AviationDetector
from bds_tcp_client import BDSTCPClient, RiskLevel

# 🔥 세션 트래킹 시스템 임포트 (Episode → Session 변경 반영)
from byte_track import SessionTracker

# 📐 삼각측량 모듈 임포트
from triangulate import (
    triangulate_objects_realtime,
    get_projection_matrix_simple,
    get_projection_matrix,
    load_camera_parameters
)

# 🛣️ 경로 기반 위험도 계산 모듈 임포트
from route_based_risk_calculator import RouteBasedRiskCalculator

warnings.filterwarnings('ignore')

class RealTimePipeline:
    """실시간 BDS 파이프라인"""
    
    def __init__(self, config_path: Optional[str] = None):
        """
        파이프라인 초기화
        
        Args:
            config_path: 설정 파일 경로 (선택사항)
        """
        self.project_root = Path(__file__).parent.parent
        self.config = self.load_config(config_path)
        
        # 🎯 항공 감지 시스템 (통합 모듈 사용)
        self.aviation_detector = None
        self.camera_params = []
        self.projection_matrices = []
        
        # 🔥 트래킹 시스템 (byte_track.py의 고급 시스템 사용)
        self.tracker = None
        
        # 🛣️ 경로 기반 위험도 계산기
        self.route_calculator = None
        
        # TCP 클라이언트 (Main Server 통신)
        self.tcp_client = None
        
        # 실시간 처리용 큐
        self.frame_queue = queue.Queue(maxsize=10)
        
        # 상태 관리
        self.is_running = False
        self.frame_count = 0
        self.fps_counter = 0
        self.last_fps_time = time.time()
        self.current_risk_level = RiskLevel.BR_LOW

        # 🛣️ 항공기별 경로 매핑 (방법 1: 위치 기반 추정)
        self.airplane_route_mapping = {}  # {track_id: route_name}
        self.route_assignment_cache = {}  # 성능 최적화용 캐시
        
        # 🚀 성능 최적화 설정
        self.frame_skip = self.config.get('frame_skip', 2)  # 설정에서 읽어오기
        self.skip_counter = 0
        
        # 🔄 위험도 레벨 안정화 (히스테리시스)
        self.last_risk_level = 'BR_LOW'
        self.risk_level_downgrade_counter = 0
        self.downgrade_threshold = 5  # 하향 시 필요한 연속 프레임 수
        
        # 성능 모니터링
        self.processing_times = {
            'detection': [],
            'triangulation': [],
            'tracking': [],
            'risk_calculation': [],
            'total': []
        }
        
        # 🐛 디버깅용 항공기 위치 로깅
        self.airplane_positions_log = []
        self.debug_output_dir = Path("data/debug")
        self.debug_output_dir.mkdir(parents=True, exist_ok=True)
        
        print("🚀 실시간 BDS 파이프라인 초기화 완료")
        print(f"⚡ 성능 최적화: 프레임 스킵 {self.frame_skip}프레임마다 1프레임 처리")
        print(f"🐛 디버깅 모드: 항공기 위치 자동 저장 → {self.debug_output_dir}")
    
    def load_config(self, config_path: Optional[str]) -> Dict:
        """설정 로드"""
        default_config = {
            'unity_capture_dir': 'unity_capture',
            'camera_count': 2,
            'camera_letters': ['A', 'B'],
            'model_path': 'auto',  # 자동으로 최신 모델 탐지
            'confidence_threshold': 0.4,  # 🚀 NMS 최적화: 0.25 → 0.4
            'fps_target': 30,
            'max_queue_size': 10,
            'output_dir': 'data/realtime_results',
            'enable_visualization': True,
            'enable_risk_calculation': True,
            'distance_threshold': 100,  # 근접 무리 병합 임계값
            'session_timeout': 30,  # 세션 타임아웃 (프레임)
            'tcp_host': 'localhost',  # Main Server 호스트
            'tcp_port': 5200,  # Main Server 포트
            'enable_tcp': True,  # TCP 통신 활성화
            
            # 🚀 성능 최적화 설정
            'frame_skip': 2,  # 프레임 스킵 (2프레임마다 1프레임 처리)
            
            # 🔥 새로운 트래킹 설정
            'tracking_mode': 'realtime',  # 'realtime' or 'episode'
            'tracking_config': {
                'position_jump_threshold': 50.0,  # 실시간용으로 더 민감하게
                'jump_duration_threshold': 3,     # 실시간용으로 더 짧게
                'min_episode_length': 10,         # 실시간용으로 더 짧게
                'enable_data_cleaning': True,     # 데이터 정제 활성화
                'realtime_mode': True             # 실시간 모드 플래그
            }
        }
        
        if config_path and Path(config_path).exists():
            with open(config_path, 'r') as f:
                user_config = json.load(f)
            default_config.update(user_config)
        
        return default_config
    
    def initialize_models(self) -> bool:
        """모델 및 카메라 파라미터 초기화"""
        try:
            # 1. 🎯 항공 감지 시스템 초기화 (통합 모듈 사용)
            model_path = None if self.config['model_path'] == 'auto' else self.config['model_path']
            
            self.aviation_detector = AviationDetector(
                model_path=model_path,
                confidence_threshold=self.config['confidence_threshold']
            )
            
            if self.aviation_detector.model is None:
                print("❌ 항공 감지 시스템 초기화 실패")
                return False
            
            # 2. 카메라 파라미터 로드 (최신 캡처 폴더에서, 사용 가능한 카메라 자동 감지)
            sync_capture_dir = self.project_root / "data/sync_capture"
            if sync_capture_dir.exists():
                latest_folder = max(sync_capture_dir.glob("Recording_*"), 
                                  key=lambda p: p.stat().st_mtime, default=None)
                
                if latest_folder:
                    available_cameras = []
                    
                    # 가능한 모든 카메라 문자 확인 (Camera_* 및 Fixed_Camera_* 패턴 지원)
                    camera_patterns = ["Camera_{}", "Fixed_Camera_{}"]
                    
                    for letter in self.config['camera_letters']:
                        camera_found = False
                        
                        for pattern in camera_patterns:
                            params_path = latest_folder / f"{pattern.format(letter)}_parameters.json"
                            if params_path.exists():
                                try:
                                    # 🔧 삼각측량 모듈의 함수 사용
                                    params = load_camera_parameters(params_path)
                                    self.camera_params.append(params)
                                    
                                    # 🔧 삼각측량 모듈의 함수 사용 (Unity 원본 파라미터용)
                                    P = get_projection_matrix(params)
                                    self.projection_matrices.append(P)
                                    
                                    available_cameras.append(letter)
                                    print(f"  ✅ {pattern.format(letter)} 파라미터 로드 완료")
                                    camera_found = True
                                    break
                                except Exception as e:
                                    print(f"  ⚠️ {pattern.format(letter)} 파라미터 로드 실패: {e}")
                        
                        if not camera_found:
                            print(f"  ⚠️ Camera_{letter} 파라미터 파일 없음")
                    
                    if len(available_cameras) < 2:
                        print(f"❌ 최소 2개 이상의 카메라가 필요합니다. 현재 {len(available_cameras)}개 발견")
                        return False
                    
                    # 설정 업데이트
                    self.config['camera_count'] = len(available_cameras)
                    self.config['camera_letters'] = available_cameras
                    
                    print(f"✅ {len(self.camera_params)}개 카메라 파라미터 로드 완료")
                    print(f"📷 사용 카메라: {', '.join([f'Camera_{c}' for c in available_cameras])}")
                else:
                    print("❌ sync_capture 폴더에서 Recording_ 폴더를 찾을 수 없습니다")
                    return False
            else:
                print("❌ sync_capture 폴더를 찾을 수 없습니다")
                return False
            
            # 3. 🔥 세션 트래킹 시스템 초기화 (Episode → Session 변경 반영)
            tracking_config = self.config['tracking_config']
            self.tracker = SessionTracker(
                position_jump_threshold=tracking_config['position_jump_threshold'],
                jump_duration_threshold=tracking_config['jump_duration_threshold'],
                min_session_length=tracking_config.get('min_episode_length', 10)  # 호환성 유지
            )
            print(f"✅ 세션 트래킹 시스템 초기화 완료")
            print(f"   - 모드: {self.config['tracking_mode']}")
            print(f"   - 위치 점프 임계값: {tracking_config['position_jump_threshold']}m")
            print(f"   - 최소 세션 길이: {tracking_config.get('min_episode_length', 10)}프레임")
            
            # 4. 🛣️ 경로 기반 위험도 계산기 초기화
            try:
                # 프로젝트 루트 기준으로 절대 경로 사용
                routes_dir = self.project_root / "data/routes"
                self.route_calculator = RouteBasedRiskCalculator(str(routes_dir))
                available_routes = self.route_calculator.get_available_routes()
                if available_routes:
                    print(f"✅ 경로 기반 위험도 계산기 초기화 완료")
                    print(f"   - 로드된 경로: {', '.join(available_routes)}")
                    for route_name in available_routes:
                        info = self.route_calculator.get_route_info(route_name)
                        print(f"   - {route_name}: {info['total_route_points']}개 경로점")
                else:
                    print("⚠️ 경로 기반 위험도 계산기: 경로 데이터 없음 (실시간 계산만 사용)")
            except Exception as e:
                print(f"⚠️ 경로 기반 위험도 계산기 초기화 실패: {e}")
                print("   실시간 계산만 사용합니다.")
                self.route_calculator = None
            
            # 5. TCP 클라이언트 초기화
            if self.config['enable_tcp']:
                self.tcp_client = BDSTCPClient(
                    host=self.config['tcp_host'],
                    port=self.config['tcp_port']
                )
                print(f"✅ TCP 클라이언트 초기화 완료 ({self.config['tcp_host']}:{self.config['tcp_port']})")
            
            return True
            
        except Exception as e:
            print(f"❌ 모델 초기화 실패: {e}")
            return False
    
    def watch_unity_frames(self):
        """Unity 프레임 감시 및 큐에 추가 (data/sync_capture 기반)"""
        sync_capture_dir = self.project_root / "data/sync_capture"
        
        if not sync_capture_dir.exists():
            print(f"❌ sync_capture 디렉토리를 찾을 수 없습니다: {sync_capture_dir}")
            return
        
        # 최신 Recording 폴더 찾기 및 감시
        current_recording_dir = None
        last_processed = {}
        
        print(f"👁️ Unity 프레임 감시 시작: {sync_capture_dir}")
        print(f"📁 Recording_* 폴더에서 실시간 프레임 감지 중...")
        
        while self.is_running:
            try:
                # 1. 최신 Recording 폴더 확인 (새로운 녹화 세션 감지)
                recording_folders = list(sync_capture_dir.glob("Recording_*"))
                if not recording_folders:
                    time.sleep(2.0)  # Recording 폴더가 생성될 때까지 대기
                    continue
                
                latest_recording = max(recording_folders, key=lambda p: p.stat().st_mtime)
                
                # 새로운 Recording 폴더 감지시 초기화
                if latest_recording != current_recording_dir:
                    current_recording_dir = latest_recording
                    last_processed = {letter: None for letter in self.config["camera_letters"]}
                    print(f"🔄 새로운 녹화 세션 감지: {latest_recording.name}")
                
                # 2. 현재 Recording 폴더에서 새로운 프레임 확인
                new_frames = {}
                all_cameras_ready = True
                
                for letter in self.config["camera_letters"]:
                    # Fixed_Camera_* 패턴 지원
                    camera_patterns = [f"Camera_{letter}", f"Fixed_Camera_{letter}"]
                    camera_dir = None
                    
                    for pattern in camera_patterns:
                        potential_dir = current_recording_dir / pattern
                        if potential_dir.exists():
                            camera_dir = potential_dir
                            break
                    
                    if camera_dir and camera_dir.exists():
                        # JPG 및 PNG 파일 모두 지원
                        image_files = sorted(list(camera_dir.glob("*.jpg")) + list(camera_dir.glob("*.png")))
                        
                        if image_files:
                            latest_file = image_files[-1]
                            
                            # 새로운 파일인지 확인
                            if latest_file != last_processed.get(letter):
                                new_frames[letter] = latest_file
                                last_processed[letter] = latest_file
                            else:
                                all_cameras_ready = False
                        else:
                            all_cameras_ready = False
                    else:
                        all_cameras_ready = False
                
                # 3. 모든 카메라에서 새 프레임이 준비되면 큐에 추가
                if all_cameras_ready and new_frames and len(new_frames) >= 2:  # 최소 2개 카메라
                    frame_data = {
                        "timestamp": time.time(),
                        "frame_id": self.frame_count,
                        "images": new_frames,
                        "recording_session": current_recording_dir.name
                    }
                    
                    try:
                        self.frame_queue.put(frame_data, timeout=0.1)
                        self.frame_count += 1
                        
                        # 진행 상황 로그 (5초마다)
                        if self.frame_count % (self.config["fps_target"] * 5) == 0:
                            print(f"📹 실시간 처리 중: {self.frame_count}프레임 ({len(new_frames)}개 카메라)")
                            
                    except queue.Full:
                        print("⚠️ 프레임 큐가 가득함 - 프레임 건너뜀")
                
                time.sleep(1.0 / self.config["fps_target"])  # FPS 제어
                
            except Exception as e:
                print(f"❌ 프레임 감시 오류: {e}")
                time.sleep(1.0)
    
    def process_frame(self, frame_data: Dict) -> Optional[Dict]:
        """단일 프레임 처리"""
        start_time = time.time()
        
        try:
            frame_id = frame_data['frame_id']
            images = frame_data['images']
            
            # 🚀 프레임 스킵 적용 (성능 최적화)
            self.skip_counter += 1
            if self.skip_counter % self.frame_skip != 0:
                return None  # 프레임 건너뛰기
            
            # 1. YOLO 감지
            detection_start = time.time()
            detections = self.detect_objects(images)
            detection_time = time.time() - detection_start
            
            if not detections:
                return None
            
            # 실제 처리할 내용이 있을 때만 구분자 출력
            print(f"{'='*50}")
            print(f"📹 프레임 {frame_id} 처리 중")
            print(f"{'='*50}")
            
            # 2. 🔧 삼각측량 (모듈 함수 사용)
            triangulation_start = time.time()
            triangulated_points = triangulate_objects_realtime(
                detections=detections,
                projection_matrices=self.projection_matrices,
                camera_letters=self.config['camera_letters'],
                frame_id=frame_id,
                distance_threshold=self.config['distance_threshold']
            )
            triangulation_time = time.time() - triangulation_start
            
            if not triangulated_points:
                return None
            
            # 🐛 디버깅: 항공기 위치 로깅
            self.log_airplane_positions(frame_id, triangulated_points)
            
            # 3. 🔥 세션 트래킹 업데이트 (Episode → Session 변경 반영)
            tracking_start = time.time()
            self.tracker.update(frame_id, triangulated_points)
            
            # 현재 활성 트랙 가져오기 (세션에서 변환)
            active_tracks = self.get_active_tracks_from_sessions()
            tracking_time = time.time() - tracking_start
            
            # 4. 위험도 계산 (선택사항)
            risk_calculation_time = 0
            risk_data = None
            if self.config['enable_risk_calculation']:
                risk_start = time.time()
                risk_data = self.calculate_risk(active_tracks, frame_id)
                risk_calculation_time = time.time() - risk_start
                
                # 위험도 계산은 calculate_risk에서 출력하므로 여기서는 생략
            
            total_time = time.time() - start_time
            
            # 성능 모니터링
            self.processing_times['detection'].append(detection_time)
            self.processing_times['triangulation'].append(triangulation_time)
            self.processing_times['tracking'].append(tracking_time)
            self.processing_times['risk_calculation'].append(risk_calculation_time)
            self.processing_times['total'].append(total_time)
            
            # 결과 구성
            result = {
                'frame_id': frame_id,
                'timestamp': frame_data['timestamp'],
                'detections': detections,
                'triangulated_points': triangulated_points,
                'active_tracks': [self.track_to_dict(track) for track in active_tracks],
                'risk_data': risk_data,
                'processing_times': {
                    'detection': detection_time,
                    'triangulation': triangulation_time,
                    'tracking': tracking_time,
                    'risk_calculation': risk_calculation_time,
                    'total': total_time
                }
            }
            
            # 🚀 메모리 관리 최적화: 주기적 가비지 컬렉션
            if frame_id % 50 == 0:  # 50프레임마다 메모리 정리
                gc.collect()
            
            # 프레임 처리 완료 구분자
            print(f"{'='*50}")
            print(f"✅ 프레임 {frame_id} 처리 완료 ({total_time*1000:.1f}ms)")
            print(f"{'='*50}")
            
            return result
            
        except Exception as e:
            print(f"❌ 프레임 {frame_data.get('frame_id', '?')} 처리 오류: {e}")
            return None
    
    def detect_objects(self, images: Dict[str, Path]) -> List[Dict]:
        """🎯 항공 객체 감지 (배치 처리 최적화)"""
        try:
            # 🚀 배치 처리로 모든 카메라 이미지를 한 번에 처리
            detections = self.aviation_detector.detect_batch_images_realtime(images)
            return detections
                        
        except Exception as e:
            print(f"❌ 배치 객체 감지 오류: {e}")
            return []
    
    def estimate_airplane_route(self, airplane_track: Dict) -> Optional[str]:
        """
        🛣️ 항공기 위치 기반 경로 추정 (방법 1)
        
        Args:
            airplane_track: 항공기 트랙 정보
            
        Returns:
            추정된 경로명 또는 None
        """
        try:
            if not self.route_calculator:
                return None
                
            track_id = airplane_track.get('track_id')
            if not track_id:
                return None
            
            # 캐시에서 확인 (성능 최적화)
            if track_id in self.route_assignment_cache:
                return self.route_assignment_cache[track_id]
            
            # 현재 위치
            airplane_pos = airplane_track['positions'][-1] if airplane_track['positions'] else None
            if not airplane_pos:
                return None
    
            # 3D 위치로 변환 (고도 100m 가정)
            airplane_3d_pos = np.array([airplane_pos[0], 100.0, airplane_pos[1]])
            
            # 모든 항공기를 Path_A로 강제 할당
            self.route_assignment_cache[track_id] = "Path_A"
            self.airplane_route_mapping[track_id] = "Path_A"
            
            print(f"✈️ 항공기 {track_id} → Path_A 강제 할당")
            return "Path_A"
                
        except Exception as e:
            print(f"❌ 항공기 경로 추정 오류: {e}")
            return "Path_A"  # 오류가 나도 Path_A 반환

    
    def calculate_risk(self, active_tracks: List, frame_id: int) -> Optional[Dict]:
        """🚀 하이브리드 위험도 계산 (경로 기반 + 실시간 동적 계산)"""
        try:
            # 비행기와 새떼 트랙 찾기
            airplane_track = None
            flock_track = None
            
            # 디버깅용: 현재 활성 트랙 정보 출력
            if active_tracks:
                track_info = []
                for track in active_tracks:
                    class_name = track.get('class_name', 'Unknown')
                    track_id = track.get('track_id', '?')
                    track_info.append(f"{class_name}({track_id})")
                print(f"🔍 활성 트랙: {', '.join(track_info)}")
            else:
                print("🔍 활성 트랙: 없음")
            
            for track in active_tracks:
                if track.get('class_name') == 'Airplane':
                    airplane_track = track
                elif track.get('class_name') == 'Flock':
                    flock_track = track
            
            # 항공기가 없으면 위험도 계산 불가
            if not airplane_track:
                print("❌ 항공기 미감지 - 위험도 계산 불가")
                return None
            
            # 새떼가 없으면 위험도 LOW로 설정
            if not flock_track:
                print("✅ 새떼 미감지 - 위험도 LOW로 설정")
                return {
                    'frame': frame_id,
                    'direct_distance': float('inf'),
                    'route_distance': float('inf'),
                    'hybrid_distance': float('inf'),
                    'distance_type': "새떼없음",
                    'assigned_route': None,
                    'relative_speed': 0.0,
                    'ttc': float('inf'),
                    'risk_score': 0.0,
                    'risk_level': 'BR_LOW',
                    'airplane_position': airplane_track['positions'][-1] if airplane_track['positions'] else [0, 0],
                    'flock_position': None,
                    'route_direction': None
                }
            
            # 최신 위치 정보
            airplane_pos = airplane_track['positions'][-1] if airplane_track['positions'] else None
            flock_pos = flock_track['positions'][-1] if flock_track['positions'] else None
            
            if not airplane_pos or not flock_pos:
                return None
            
            # 🛣️ 1. 항공기 경로 추정 및 경로 기반 위험도 계산
            route_distance = None
            assigned_route = None
            route_direction = None
            
            if self.route_calculator:
                try:
                    # 1-1. 항공기 경로 추정 (방법 1: 위치 기반)
                    assigned_route = self.estimate_airplane_route(airplane_track)
                    
                    if assigned_route:
                        # 1-2. 할당된 경로와 새떼 간의 거리 계산
                        flock_3d_pos = np.array([flock_pos[0], 50.0, flock_pos[1]])
                        route_distance = self.route_calculator.calculate_distance_to_route(assigned_route, flock_3d_pos)
                        
                        # 1-3. 경로 진행 방향 계산 (가장 가까운 점 기준)
                        _, _, closest_point = self.route_calculator.get_closest_point_on_route(assigned_route, flock_3d_pos)
                        if closest_point is not None:
                            route_direction = self.route_calculator.calculate_route_segment_direction(
                                assigned_route, closest_point
                            )
                        
                        print(f"🛣️ 경로 기반 계산: {assigned_route} 경로 사용 (거리: {route_distance:.1f}m)")
                    else:
                        print(f"⚠️ 항공기 경로 미할당 - 직선 거리만 사용")
                        
                except Exception as e:
                    print(f"⚠️ 경로 기반 계산 오류: {e}")
            
            # 🚀 2. 실시간 동적 계산
            # 2-1. 직선 거리 계산 (고도 차이 포함)
            direct_distance = self.calculate_3d_distance(airplane_pos, flock_pos)
            
            # 2-2. 상대속도 계산 (실제 트래킹 데이터 기반)
            relative_speed = self.calculate_relative_speed(airplane_track, flock_track)
            
            # 2-3. 실시간 TTC 계산
            ttc = self.calculate_realtime_ttc(airplane_track, flock_track)
            
            # 🔄 3. 하이브리드 거리 계산
            # 경로 기반 거리가 있으면 가중 평균 사용, 없으면 직선 거리만 사용
            if route_distance is not None and route_distance < float('inf'):
                # 경로 거리와 직선 거리의 가중 평균
                # 경로 거리에 더 높은 가중치 (70% vs 30%)
                hybrid_distance = 0.7 * route_distance + 0.3 * direct_distance
                distance_type = "하이브리드"
            else:
                hybrid_distance = direct_distance
                distance_type = "직선"
            
            # 🎯 4. 동적 위험도 레벨 계산 (하이브리드 거리 사용)
            risk_score, risk_level = self.calculate_dynamic_risk_level(hybrid_distance, relative_speed, ttc)
            
            # 🔄 5. 위험도 레벨 안정화 (플리커링 방지)
            stable_risk_score, stable_risk_level = self.get_stable_risk_level(risk_score, risk_level)
            
            # 📊 6. 결과 구성 (안정화된 값 사용)
            risk_result = {
                'frame': frame_id,
                'direct_distance': direct_distance,
                'route_distance': route_distance,
                'hybrid_distance': hybrid_distance,
                'distance_type': distance_type,
                'assigned_route': assigned_route,
                'relative_speed': relative_speed,
                'ttc': ttc,
                'risk_score': stable_risk_score,  # 안정화된 점수
                'risk_level': stable_risk_level,  # 안정화된 레벨
                'raw_risk_score': risk_score,     # 원본 점수 (디버깅용)
                'raw_risk_level': risk_level,     # 원본 레벨 (디버깅용)
                'airplane_position': airplane_pos,
                'flock_position': flock_pos,
                'route_direction': route_direction.tolist() if route_direction is not None else None
            }
            
            # 위험도 간단 요약 (안정화된 값으로 출력)
            print(f"📊 위험도: {stable_risk_level} (점수: {stable_risk_score:.1f}, 거리: {hybrid_distance:.1f}m)")
            if ttc != float('inf'):
                print(f"   ⏰ TTC: {ttc:.1f}초")
            
            # 🔍 상세 위험도 계산 과정 출력
            self.print_detailed_risk_calculation(
                hybrid_distance, relative_speed, ttc,
                risk_score, risk_level,
                stable_risk_score, stable_risk_level,
                hybrid_distance, direct_distance, route_distance, assigned_route
            )
            
            # TCP 클라이언트로 위험도 전송 (안정화된 레벨 사용)
            if self.tcp_client and self.config['enable_tcp']:
                try:
                    # 위험도가 변경되었을 때만 전송
                    if stable_risk_level != self.current_risk_level:
                        # 인터페이스 명세서에 맞는 메시지 형식
                        message = {
                            "type": "event",
                            "event": "BR_CHANGED",
                            "result": stable_risk_level
                        }
                        self.tcp_client.send_message(message)
                        self.current_risk_level = stable_risk_level
                        
                        print(f"📡 위험도 전송: {stable_risk_level}")
                        
                except Exception as e:
                    print(f"❌ TCP 전송 오류: {e}")
            
            return risk_result
            
        except Exception as e:
            print(f"❌ 위험도 계산 오류: {e}")
            return None
    
    def calculate_relative_speed(self, airplane_track: Dict, flock_track: Dict) -> float:
        """
        항공기와 새떼 간 상대속도 계산
        
        Args:
            airplane_track: 항공기 트랙 정보
            flock_track: 새떼 트랙 정보
            
        Returns:
            상대속도 (m/s) - 양수: 접근, 음수: 멀어짐
        """
        try:
            # 최신 속도 정보 가져오기
            airplane_velocities = airplane_track.get('velocities', [])
            flock_velocities = flock_track.get('velocities', [])
            
            if not airplane_velocities or not flock_velocities:
                return 0.0
            
            # 최신 속도 벡터
            airplane_vel = airplane_velocities[-1]  # (vx, vz)
            flock_vel = flock_velocities[-1]       # (vx, vz)
            
            # 현재 위치
            airplane_pos = airplane_track['positions'][-1]  # (x, z)
            flock_pos = flock_track['positions'][-1]        # (x, z)
            
            # 위치 벡터 (새떼에서 항공기로)
            dx = airplane_pos[0] - flock_pos[0]
            dz = airplane_pos[1] - flock_pos[1]
            distance = np.sqrt(dx**2 + dz**2)
            
            if distance < 1e-6:  # 너무 가까우면 0 반환
                return 0.0
            
            # 정규화된 방향 벡터
            unit_x = dx / distance
            unit_z = dz / distance
            
            # 상대속도 벡터 (항공기 속도 - 새떼 속도)
            rel_vx = airplane_vel[0] - flock_vel[0]
            rel_vz = airplane_vel[1] - flock_vel[1]
            
            # 상대속도의 방향성 성분 (양수: 접근, 음수: 멀어짐)
            relative_speed = rel_vx * unit_x + rel_vz * unit_z
            
            return relative_speed
            
        except Exception as e:
            print(f"❌ 상대속도 계산 오류: {e}")
            return 0.0
    
    def calculate_realtime_ttc(self, airplane_track: Dict, flock_track: Dict) -> float:
        """
        🚀 실시간 충돌 시간 계산 (Time-to-Collision)
        
        Args:
            airplane_track: 항공기 트랙 정보
            flock_track: 새떼 트랙 정보
            
        Returns:
            예상 충돌 시간 (초) - 무한대면 충돌하지 않음
        """
        try:
            # 위치와 속도 정보 가져오기
            airplane_pos = airplane_track['positions'][-1]
            flock_pos = flock_track['positions'][-1]
            airplane_velocities = airplane_track.get('velocities', [])
            flock_velocities = flock_track.get('velocities', [])
            
            if not airplane_velocities or not flock_velocities:
                return float('inf')
            
            # 최신 속도 벡터
            airplane_vel = airplane_velocities[-1]  # (vx, vz)
            flock_vel = flock_velocities[-1]       # (vx, vz)
            
            # 현재 거리
            dx = airplane_pos[0] - flock_pos[0]
            dz = airplane_pos[1] - flock_pos[1]
            current_distance = np.sqrt(dx**2 + dz**2)
            
            # 상대속도 벡터 (항공기 - 새떼)
            rel_vx = airplane_vel[0] - flock_vel[0]
            rel_vz = airplane_vel[1] - flock_vel[1]
            rel_speed_magnitude = np.sqrt(rel_vx**2 + rel_vz**2)
            
            # 접근 방향인지 확인
            if current_distance < 1e-6 or rel_speed_magnitude < 1e-6:
                return float('inf')
            
            # 정규화된 방향 벡터 (새떼에서 항공기로)
            unit_x = dx / current_distance
            unit_z = dz / current_distance
            
            # 접근 속도 계산 (양수면 접근 중)
            closing_speed = -(rel_vx * unit_x + rel_vz * unit_z)
            
            if closing_speed <= 0:
                # 멀어지고 있거나 평행하게 움직임
                return float('inf')
            
            # TTC 계산
            ttc = current_distance / closing_speed
            
            # 합리적인 범위로 제한 (0.1초 ~ 300초)
            ttc = max(0.1, min(300.0, ttc))
            
            return ttc
            
        except Exception as e:
            print(f"❌ 실시간 TTC 계산 오류: {e}")
            return float('inf')
    
    def calculate_dynamic_risk_level(self, distance: float, relative_speed: float, ttc: float) -> Tuple[float, str]:
        """
        🚀 개선된 동적 위험도 레벨 계산 (거리/TTC 하한선 + 2배 스케일)
        
        Args:
            distance: 3D 거리 (m)
            relative_speed: 상대속도 (m/s) - 양수: 접근, 음수: 멀어짐
            ttc: 충돌예상시간 (초)
            
        Returns:
            (위험도 점수, 위험도 레벨)
        """
        try:
            # 1. 거리 기반 하한선 (즉각적 위험)
            if distance < 50:
                return 180.0, "BR_HIGH"  # 50m 이하는 무조건 HIGH
            elif distance < 100:
                return 120.0, "BR_MEDIUM"  # 50-100m는 무조건 MEDIUM 이상
            
            # 2. TTC 기반 하한선 (충돌 임박)
            if ttc != float('inf'):
                if ttc < 5:
                    return 180.0, "BR_HIGH"  # 5초 이하는 무조건 HIGH
                elif ttc < 12:
                    return 120.0, "BR_MEDIUM"  # 5-12초는 무조건 MEDIUM 이상
            
            # 3. 점수 기반 계산 (기존 로직)
            # 거리 점수 (40% 가중치) - 가까울수록 위험
            if distance <= 50:
                distance_score = 100
            elif distance <= 100:
                distance_score = 80 - (distance - 50) * 0.6  # 50-100m: 80-50점
            elif distance <= 200:
                distance_score = 50 - (distance - 100) * 0.3  # 100-200m: 50-20점
            else:
                distance_score = max(0, 20 - (distance - 200) * 0.05)  # 200m+: 20점 이하
            
            # 상대속도 점수 (30% 가중치) - 빠르게 접근할수록 위험
            if relative_speed <= 0:
                # 멀어지고 있음
                speed_score = 0
            elif relative_speed <= 10:
                speed_score = relative_speed * 3  # 0-10 m/s: 0-30점
            elif relative_speed <= 30:
                speed_score = 30 + (relative_speed - 10) * 2.5  # 10-30 m/s: 30-80점
            else:
                speed_score = min(100, 80 + (relative_speed - 30) * 1)  # 30+ m/s: 80-100점
            
            # TTC 점수 (30% 가중치) - 충돌시간이 짧을수록 위험
            if ttc == float('inf'):
                ttc_score = 0
            elif ttc <= 5:
                ttc_score = 100
            elif ttc <= 15:
                ttc_score = 100 - (ttc - 5) * 5  # 5-15초: 100-50점
            elif ttc <= 30:
                ttc_score = 50 - (ttc - 15) * 2  # 15-30초: 50-20점
            else:
                ttc_score = max(0, 20 - (ttc - 30) * 0.5)  # 30초+: 20점 이하
            
            # 가중 평균 계산 후 2배 스케일업
            risk_score = (distance_score * 0.4 + speed_score * 0.3 + ttc_score * 0.3) * 2.0
            
            # 4. 위험도 레벨 결정 (2배 스케일된 기준)
            if risk_score >= 80:  # 기존 40 * 2
                risk_level = 'BR_HIGH'
            elif risk_score >= 60:  # 기존 30 * 2
                risk_level = 'BR_MEDIUM'
            else:
                risk_level = 'BR_LOW'
            
            return risk_score, risk_level
            
        except Exception as e:
            print(f"❌ 동적 위험도 계산 오류: {e}")
            return 0.0, 'BR_LOW'
    
    def print_detailed_risk_calculation(self, distance: float, relative_speed: float, ttc: float, 
                                       risk_score: float, risk_level: str, 
                                       stable_risk_score: float, stable_risk_level: str,
                                       hybrid_distance: float, direct_distance: float, 
                                       route_distance: float, assigned_route: str) -> None:
        """
        🔍 위험도 계산 과정 상세 출력
        """
        try:
            print(f"🔍 위험도 계산 상세 분석:")
            
            # 1. 거리 정보
            print(f"   📏 거리 정보:")
            print(f"      • 직선 거리: {direct_distance:.1f}m")
            if route_distance and route_distance != float('inf'):
                print(f"      • 경로 거리: {route_distance:.1f}m ({assigned_route})")
                print(f"      • 하이브리드 거리: {hybrid_distance:.1f}m (경로70% + 직선30%)")
            else:
                print(f"      • 하이브리드 거리: {hybrid_distance:.1f}m (직선거리 사용)")
            
            # 2. 하한선 체크
            print(f"   ⚠️ 하한선 체크:")
            if distance < 50:
                print(f"      • 거리 {distance:.1f}m < 50m → 무조건 BR_HIGH")
                return
            elif distance < 100:
                print(f"      • 거리 {distance:.1f}m < 100m → 무조건 BR_MEDIUM 이상")
                return
            else:
                print(f"      • 거리 {distance:.1f}m ≥ 100m → 점수 계산 진행")
            
            if ttc != float('inf'):
                if ttc < 5:
                    print(f"      • TTC {ttc:.1f}초 < 5초 → 무조건 BR_HIGH")
                    return
                elif ttc < 12:
                    print(f"      • TTC {ttc:.1f}초 < 12초 → 무조건 BR_MEDIUM 이상")
                    return
                else:
                    print(f"      • TTC {ttc:.1f}초 ≥ 12초 → 점수 계산 진행")
            else:
                print(f"      • TTC 무한대 (충돌 안함) → 점수 계산 진행")
            
            # 3. 점수 계산 과정
            print(f"   🧮 점수 계산 과정:")
            
            # 거리 점수 계산
            if distance <= 50:
                distance_score = 100
            elif distance <= 100:
                distance_score = 80 - (distance - 50) * 0.6
            elif distance <= 200:
                distance_score = 50 - (distance - 100) * 0.3
            else:
                distance_score = max(0, 20 - (distance - 200) * 0.05)
            print(f"      • 거리 점수: {distance_score:.1f}/100 (가중치 40%)")
            
            # 상대속도 점수 계산
            if relative_speed <= 0:
                speed_score = 0
            elif relative_speed <= 10:
                speed_score = relative_speed * 3
            elif relative_speed <= 30:
                speed_score = 30 + (relative_speed - 10) * 2.5
            else:
                speed_score = min(100, 80 + (relative_speed - 30) * 1)
            
            speed_direction = "접근" if relative_speed > 0 else "멀어짐"
            print(f"      • 상대속도: {relative_speed:.1f}m/s ({speed_direction})")
            print(f"      • 속도 점수: {speed_score:.1f}/100 (가중치 30%)")
            
            # TTC 점수 계산
            if ttc == float('inf'):
                ttc_score = 0
                ttc_display = "무한대"
            elif ttc <= 5:
                ttc_score = 100
                ttc_display = f"{ttc:.1f}초"
            elif ttc <= 15:
                ttc_score = 100 - (ttc - 5) * 5
                ttc_display = f"{ttc:.1f}초"
            elif ttc <= 30:
                ttc_score = 50 - (ttc - 15) * 2
                ttc_display = f"{ttc:.1f}초"
            else:
                ttc_score = max(0, 20 - (ttc - 30) * 0.5)
                ttc_display = f"{ttc:.1f}초"
            print(f"      • TTC: {ttc_display}")
            print(f"      • TTC 점수: {ttc_score:.1f}/100 (가중치 30%)")
            
            # 최종 점수 계산
            base_score = distance_score * 0.4 + speed_score * 0.3 + ttc_score * 0.3
            final_score = base_score * 2.0
            print(f"      • 기본 점수: {base_score:.1f} = {distance_score:.1f}×0.4 + {speed_score:.1f}×0.3 + {ttc_score:.1f}×0.3")
            print(f"      • 최종 점수: {final_score:.1f} (2배 스케일)")
            
            # 4. 레벨 결정
            print(f"   🎯 레벨 결정:")
            if final_score >= 80:
                calculated_level = "BR_HIGH"
            elif final_score >= 60:
                calculated_level = "BR_MEDIUM"
            else:
                calculated_level = "BR_LOW"
            print(f"      • 계산된 레벨: {calculated_level} (점수 {final_score:.1f})")
            
            # 5. 안정화 적용
            if stable_risk_level != risk_level:
                print(f"   🔄 안정화 적용:")
                print(f"      • 원본: {risk_level} (점수 {risk_score:.1f})")
                print(f"      • 안정화: {stable_risk_level} (점수 {stable_risk_score:.1f})")
            else:
                print(f"   ✅ 최종 결과: {stable_risk_level} (점수 {stable_risk_score:.1f})")
                
        except Exception as e:
            print(f"❌ 상세 분석 출력 오류: {e}")

    def get_stable_risk_level(self, new_risk_score: float, new_risk_level: str) -> Tuple[float, str]:
        """
        🔄 위험도 레벨 안정화 (히스테리시스 적용)
        - 상향(위험 증가): 즉시 반영
        - 하향(위험 감소): 연속 N프레임 유지 시에만 반영
        
        Args:
            new_risk_score: 새로 계산된 위험도 점수
            new_risk_level: 새로 계산된 위험도 레벨
            
        Returns:
            (안정화된 위험도 점수, 안정화된 위험도 레벨)
        """
        try:
            # 위험도 등급 우선순위 (숫자가 높을수록 위험)
            level_priority = {'BR_LOW': 0, 'BR_MEDIUM': 1, 'BR_HIGH': 2}
            
            prev_level = self.last_risk_level
            curr_level = new_risk_level
            
            # 1. 상향(위험 증가)은 즉시 반영
            if level_priority[curr_level] > level_priority[prev_level]:
                self.last_risk_level = curr_level
                self.risk_level_downgrade_counter = 0
                print(f"⚠️ 위험도 상향: {prev_level} → {curr_level} (즉시 반영)")
                return new_risk_score, curr_level
            
            # 2. 하향(위험 감소)은 연속 N프레임 유지 시에만 반영
            elif level_priority[curr_level] < level_priority[prev_level]:
                self.risk_level_downgrade_counter += 1
                
                if self.risk_level_downgrade_counter >= self.downgrade_threshold:
                    # 충분히 유지되었으므로 하향 승인
                    self.last_risk_level = curr_level
                    self.risk_level_downgrade_counter = 0
                    print(f"✅ 위험도 하향: {prev_level} → {curr_level} ({self.downgrade_threshold}프레임 유지 후 반영)")
                    return new_risk_score, curr_level
                else:
                    # 아직 하향 보류, 이전 레벨 유지
                    print(f"🔄 위험도 하향 대기: {prev_level} 유지 ({self.risk_level_downgrade_counter}/{self.downgrade_threshold})")
                    # 이전 레벨에 해당하는 점수 반환 (시각적 일관성)
                    prev_score = 120.0 if prev_level == 'BR_MEDIUM' else (180.0 if prev_level == 'BR_HIGH' else new_risk_score)
                    return prev_score, prev_level
            
            # 3. 등급 유지 (같은 레벨)
            else:
                self.risk_level_downgrade_counter = 0
                return new_risk_score, curr_level
                
        except Exception as e:
            print(f"❌ 위험도 안정화 오류: {e}")
            return new_risk_score, new_risk_level
    
    def calculate_3d_distance(self, airplane_pos: Tuple[float, float], flock_pos: Tuple[float, float]) -> float:
        """
        🚀 3D 거리 계산 (고도 차이 포함)
        
        Args:
            airplane_pos: 항공기 위치 (x, z)
            flock_pos: 새떼 위치 (x, z)
            
        Returns:
            3D 거리 (미터)
        """
        try:
            # XZ 평면 거리
            dx = airplane_pos[0] - flock_pos[0]
            dz = airplane_pos[1] - flock_pos[1]
            horizontal_distance = np.sqrt(dx**2 + dz**2)
            
            # 고도 차이 (항공기는 보통 50m 높이에서 비행한다고 가정)
            altitude_diff = 50.0  # 미터
            
            # 3D 거리 계산
            distance_3d = np.sqrt(horizontal_distance**2 + altitude_diff**2)
            
            return distance_3d
            
        except Exception as e:
            print(f"❌ 3D 거리 계산 오류: {e}")
            return 100.0  # 기본값
    
    def track_to_dict(self, track) -> Dict:
        """트랙 객체를 딕셔너리로 변환"""
        return {
            'track_id': track.get('track_id', 0),
            'class_name': track.get('class_name', 'Unknown'),
            'current_position': track['positions'][-1] if track.get('positions') else None,
            'current_velocity': track['velocities'][-1] if track.get('velocities') else None,
            'session_id': track.get('session_id', 0),
            'frame_count': len(track.get('frames', []))
        }
    
    def get_active_tracks_from_sessions(self) -> List[Dict]:
        """현재 활성 세션에서 트랙 정보 추출 (Episode → Session 변경 반영)"""
        active_tracks = []
        
        # 현재 진행중인 세션이 있다면
        if self.tracker.in_session and self.tracker.current_session_data:
            session_data = self.tracker.current_session_data
            
            # 항공기 트랙
            if session_data.get('airplane_positions'):
                airplane_track = {
                    'track_id': 1,
                    'class_name': 'Airplane',
                    'positions': [(x, z) for _, x, z in session_data['airplane_positions']],
                    'velocities': [(vx, vz) for _, vx, vz in session_data.get('airplane_velocities', [])],
                    'frames': [f for f, _, _ in session_data['airplane_positions']],
                    'session_id': self.tracker.current_session_id,
                    'last_update': session_data.get('last_frame', 0)
                }
                active_tracks.append(airplane_track)
            
            # 새떼 트랙
            if session_data.get('flock_positions'):
                flock_track = {
                    'track_id': 2,
                    'class_name': 'Flock',
                    'positions': [(x, z) for _, x, z in session_data['flock_positions']],
                    'velocities': [(vx, vz) for _, vx, vz in session_data.get('flock_velocities', [])],
                    'frames': [f for f, _, _ in session_data['flock_positions']],
                    'session_id': self.tracker.current_session_id,
                    'last_update': session_data.get('last_frame', 0)
                }
                active_tracks.append(flock_track)
        
        return active_tracks
    
    def process_frames_worker(self):
        """프레임 처리 워커 스레드"""
        print("🔄 프레임 처리 워커 시작")
        
        while self.is_running:
            try:
                # 큐에서 프레임 가져오기
                frame_data = self.frame_queue.get(timeout=1.0)
                
                # 프레임 처리
                result = self.process_frame(frame_data)
                
                # FPS 계산
                self.fps_counter += 1
                current_time = time.time()
                if current_time - self.last_fps_time >= 1.0:
                    fps = self.fps_counter / (current_time - self.last_fps_time)
                    print(f"📊 처리 FPS: {fps:.1f}")
                    self.fps_counter = 0
                    self.last_fps_time = current_time
                
            except queue.Empty:
                continue
            except Exception as e:
                print(f"❌ 프레임 처리 워커 오류: {e}")
    
    def start(self):
        """파이프라인 시작"""
        print("🚀 실시간 BDS 파이프라인 시작...")
        
        # 모델 초기화
        if not self.initialize_models():
            print("❌ 모델 초기화 실패")
            return False
        
        self.is_running = True
        
        # TCP 클라이언트 시작
        if self.tcp_client:
            if self.tcp_client.start():
                print("✅ TCP 클라이언트 시작됨")
            else:
                print("⚠️ TCP 클라이언트 시작 실패 (재연결 시도 중)")
        
        # 워커 스레드 시작 (🚀 저장 워커 제거로 성능 최적화)
        threads = [
            threading.Thread(target=self.watch_unity_frames, daemon=True),
            threading.Thread(target=self.process_frames_worker, daemon=True),
        ]
        
        for thread in threads:
            thread.start()
        
        print("✅ 모든 워커 스레드 시작됨")
        print("📡 Unity 프레임 대기 중...")
        print("Press Ctrl+C to stop")
        
        try:
            # 메인 루프 (모니터링)
            while True:
                time.sleep(5.0)
                
                # 큐 상태 출력 (🚀 저장 제거로 결과 큐 모니터링 제거)
                frame_queue_size = self.frame_queue.qsize()
                
                # TCP 상태 확인
                tcp_status = ""
                if self.tcp_client:
                    status = self.tcp_client.get_status()
                    tcp_status = f", TCP: {'연결됨' if status['connected'] else '연결 안됨'}"
                
                print(f"📊 큐 상태 - 프레임: {frame_queue_size}{tcp_status}")  # 🚀 결과 큐 제거
                
                # 성능 통계 출력 (30초마다)
                if self.frame_count > 0 and self.frame_count % 150 == 0:
                    self.print_performance_stats()
                
        except KeyboardInterrupt:
            print("\n🛑 사용자 중단 요청")
            self.stop()
            return True
    
    def stop(self):
        """파이프라인 중지"""
        print("🛑 실시간 BDS 파이프라인 중지 중...")
        
        self.is_running = False
        
        # 🐛 프로그램 종료 시 마지막 디버깅 데이터 저장
        if self.airplane_positions_log:
            print("🐛 프로그램 종료 - 마지막 디버깅 데이터 저장 중...")
            self.save_airplane_debug_data()
        
        # TCP 클라이언트 중지
        if self.tcp_client:
            self.tcp_client.stop()
            print("✅ TCP 클라이언트 중지됨")
        
        # 잠시 대기하여 워커 스레드들이 정리되도록 함
        time.sleep(2.0)
        
        # 최종 성능 통계 출력
        self.print_performance_stats()
        
        print("✅ 파이프라인 중지 완료")
    
    def print_performance_stats(self):
        """성능 통계 출력"""
        if not self.processing_times['total']:
            return
        
        print("\n📊 성능 통계:")
        print(f"  🚀 최적화 적용:")
        print(f"    - 프레임 스킵     : {self.frame_skip}프레임마다 1프레임 처리")
        print(f"    - 배치 처리       : 활성화 (다중 카메라 동시 처리)")
        print(f"    - GPU 메모리 최적화: 활성화")
        print(f"    - NMS 최적화      : confidence {self.config['confidence_threshold']}")
        print(f"    - 메모리 관리     : 50프레임마다 가비지 컬렉션")
        print(f"  처리된 프레임   : {len(self.processing_times.get('total', []))}개")
        for stage, times in self.processing_times.items():
            if times:
                avg_time = np.mean(times) * 1000  # ms로 변환
                max_time = np.max(times) * 1000
                print(f"  {stage:15}: 평균 {avg_time:6.1f}ms, 최대 {max_time:6.1f}ms")

    def log_airplane_positions(self, frame_id: int, triangulated_points: List[Dict]):
        """🐛 디버깅용: 항공기 위치 로깅"""
        try:
            for point in triangulated_points:
                if point.get('class', '').lower() == 'airplane':
                    log_entry = {
                        'frame_id': frame_id,
                        'timestamp': time.time(),
                        'x': float(point['x']),
                        'y': float(point['y']),
                        'z': float(point['z']),
                        'confidence': point.get('confidence', 0.0)
                    }
                    self.airplane_positions_log.append(log_entry)
                    
                    # 실시간 출력
                    print(f"🛩️ 항공기 위치: Frame {frame_id} → Unity({point['x']:.1f}, {point['y']:.1f}, {point['z']:.1f})")
            
            # 5프레임마다 파일 저장 (홀수 프레임에서도 저장됨)
            if frame_id % 5 == 0 and self.airplane_positions_log:
                self.save_airplane_debug_data()
                
        except Exception as e:
            print(f"❌ 항공기 위치 로깅 오류: {e}")
    
    def save_airplane_debug_data(self):
        """🐛 디버깅용: 항공기 위치 데이터 저장"""
        try:
            if not self.airplane_positions_log:
                return
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            debug_file = self.debug_output_dir / f"airplane_positions_{timestamp}.json"
            
            debug_data = {
                'session_start': datetime.now().isoformat(),
                'total_positions': len(self.airplane_positions_log),
                'frame_range': {
                    'start': self.airplane_positions_log[0]['frame_id'] if self.airplane_positions_log else 0,
                    'end': self.airplane_positions_log[-1]['frame_id'] if self.airplane_positions_log else 0
                },
                'coordinate_range': self.calculate_coordinate_range(),
                'positions': self.airplane_positions_log
            }
            
            with open(debug_file, 'w', encoding='utf-8') as f:
                json.dump(debug_data, f, indent=2, ensure_ascii=False)
            
            print(f"🐛 디버깅 데이터 저장: {debug_file.name} ({len(self.airplane_positions_log)}개 위치)")
            
            # 기존 로그 초기화 (메모리 절약)
            self.airplane_positions_log = []
            
        except Exception as e:
            print(f"❌ 디버깅 데이터 저장 실패: {e}")
    
    def calculate_coordinate_range(self) -> Dict:
        """좌표 범위 계산"""
        if not self.airplane_positions_log:
            return {}
        
        x_coords = [p['x'] for p in self.airplane_positions_log]
        y_coords = [p['y'] for p in self.airplane_positions_log]
        z_coords = [p['z'] for p in self.airplane_positions_log]
        
        return {
            'x': {'min': min(x_coords), 'max': max(x_coords)},
            'y': {'min': min(y_coords), 'max': max(y_coords)},
            'z': {'min': min(z_coords), 'max': max(z_coords)}
        }

def main():
    """메인 실행 함수"""
    print("🚀 BirdRiskSim 실시간 파이프라인 시작")
    print("=" * 60)
    
    # 파이프라인 생성 및 시작
    pipeline = RealTimePipeline()
    
    try:
        success = pipeline.start()
        if success:
            print("✅ 파이프라인이 정상적으로 종료되었습니다")
        else:
            print("❌ 파이프라인 시작 실패")
    except Exception as e:
        print(f"❌ 파이프라인 오류: {e}")
        pipeline.stop()

if __name__ == "__main__":
    main() 