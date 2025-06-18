#!/usr/bin/env python3
"""
BirdRiskSim 간소화된 세션 기반 트래킹 시스템
- 핵심 기능만 유지: 데이터 정제, 자동 세션 감지, 기본 궤적 분석
- LSTM 특화 기능 및 복잡한 통계 제거
"""

import numpy as np
from pathlib import Path
import json
from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional
import pandas as pd
from datetime import datetime

@dataclass
class Session:
    """세션 정보 (기존 Episode에서 간소화)"""
    session_id: int
    start_frame: int
    end_frame: int
    airplane_positions: List[Tuple[int, float, float]]  # (frame, x, z)
    flock_positions: List[Tuple[int, float, float]]     # (frame, x, z)
    airplane_velocities: List[Tuple[int, float, float]]  # (frame, vx, vz)
    flock_velocities: List[Tuple[int, float, float]]     # (frame, vx, vz)
    
    def get_session_length(self) -> int:
        """세션 길이 반환"""
        return self.end_frame - self.start_frame + 1
    
    def clean_data(self, position_jump_threshold: float = 150.0, smoothing_window: int = 3) -> 'Session':
        """데이터 정제 - 이상치 제거 및 스무딩"""
        import copy
        
        cleaned_session = copy.deepcopy(self)
        
        # 항공기 데이터 정제
        cleaned_session.airplane_positions = self._remove_position_outliers(
            self.airplane_positions, position_jump_threshold)
        cleaned_session.airplane_positions = self._smooth_positions(
            cleaned_session.airplane_positions, smoothing_window)
        cleaned_session.airplane_velocities = self._recalculate_velocities(
            cleaned_session.airplane_positions)
        
        # 새 데이터 정제
        cleaned_session.flock_positions = self._remove_position_outliers(
            self.flock_positions, position_jump_threshold)
        cleaned_session.flock_positions = self._smooth_positions(
            cleaned_session.flock_positions, smoothing_window)
        cleaned_session.flock_velocities = self._recalculate_velocities(
            cleaned_session.flock_positions)
        
        return cleaned_session
    
    def _remove_position_outliers(self, positions: List[Tuple[int, float, float]], 
                                 threshold: float) -> List[Tuple[int, float, float]]:
        """위치 이상치 제거"""
        if len(positions) < 3:
            return positions
        
        cleaned = []
        
        for i in range(len(positions)):
            if i == 0 or i == len(positions) - 1:
                # 첫 번째와 마지막 점은 유지
                cleaned.append(positions[i])
            else:
                prev_frame, prev_x, prev_z = positions[i-1]
                curr_frame, curr_x, curr_z = positions[i]
                next_frame, next_x, next_z = positions[i+1]
                
                # 이전 점과의 거리
                dist_prev = np.sqrt((curr_x - prev_x)**2 + (curr_z - prev_z)**2)
                # 다음 점과의 거리
                dist_next = np.sqrt((next_x - curr_x)**2 + (next_z - curr_z)**2)
                
                # 프레임 간격 고려한 속도
                frame_gap_prev = max(1, curr_frame - prev_frame)
                frame_gap_next = max(1, next_frame - curr_frame)
                
                speed_prev = dist_prev / frame_gap_prev
                speed_next = dist_next / frame_gap_next
                
                # 임계값을 넘지 않으면 유지
                if speed_prev <= threshold and speed_next <= threshold:
                    cleaned.append(positions[i])
        
        return cleaned
    
    def _smooth_positions(self, positions: List[Tuple[int, float, float]], 
                         window_size: int) -> List[Tuple[int, float, float]]:
        """위치 데이터 스무딩"""
        if len(positions) < window_size:
            return positions
        
        smoothed = []
        half_window = window_size // 2
        
        for i in range(len(positions)):
            frame = positions[i][0]
            
            # 윈도우 범위 계산
            start_idx = max(0, i - half_window)
            end_idx = min(len(positions), i + half_window + 1)
            
            # 평균 계산
            x_values = [positions[j][1] for j in range(start_idx, end_idx)]
            z_values = [positions[j][2] for j in range(start_idx, end_idx)]
            
            avg_x = np.mean(x_values)
            avg_z = np.mean(z_values)
            
            smoothed.append((frame, avg_x, avg_z))
        
        return smoothed
    
    def _recalculate_velocities(self, positions: List[Tuple[int, float, float]]) -> List[Tuple[int, float, float]]:
        """위치 데이터로부터 속도 재계산"""
        if len(positions) < 2:
            return []
        
        velocities = []
        
        for i in range(1, len(positions)):
            prev_frame, prev_x, prev_z = positions[i-1]
            curr_frame, curr_x, curr_z = positions[i]
            
            # 시간 간격 (프레임 -> 초, 30fps 가정)
            dt = (curr_frame - prev_frame) / 30.0
            
            if dt > 0:
                vx = (curr_x - prev_x) / dt
                vz = (curr_z - prev_z) / dt
                velocities.append((curr_frame, vx, vz))
        
        return velocities

class SessionTracker:
    """간소화된 세션 기반 트래킹 (기존 EpisodeTracker)"""
    
    def __init__(self, position_jump_threshold: float = 50.0, jump_duration_threshold: int = 5, min_session_length: int = 50):
        """
        Args:
            position_jump_threshold: 항공기 위치 점프 임계값 (미터)
            jump_duration_threshold: 위치 점프가 몇 프레임 동안 지속되어야 분리할지
            min_session_length: 최소 세션 길이 (프레임)
        """
        self.position_jump_threshold = position_jump_threshold
        self.jump_duration_threshold = jump_duration_threshold
        self.min_session_length = min_session_length
        
        self.sessions = []
        self.current_session_id = 0
        self.in_session = False
        self.current_session_data = {}
        
        # 이전 프레임의 항공기 위치 저장
        self.last_airplane_position = None
        self.last_frame_number = None
        
        # 위치 점프 지속 추적
        self.jump_start_frame = None
        self.jump_frames_count = 0
    
    def update(self, frame_number: int, detections: List[Dict]) -> None:
        """프레임별 검출 결과 처리"""
        
        # 현재 프레임의 객체들 분류
        airplane_detections = [d for d in detections if d['class'] == 'Airplane']
        flock_detections = [d for d in detections if d['class'] == 'Flock']
        
        # 항공기가 있는 경우만 처리
        if airplane_detections:
            airplane = airplane_detections[0]  # 첫 번째 항공기 사용
            current_airplane_pos = (airplane['x'], airplane['z'])
            
            # 항공기 위치 점프 감지
            position_jumped = False
            if self.last_airplane_position is not None:
                distance = np.sqrt((current_airplane_pos[0] - self.last_airplane_position[0])**2 + 
                                 (current_airplane_pos[1] - self.last_airplane_position[1])**2)
                if distance > self.position_jump_threshold:
                    position_jumped = True
                    
                    # 점프 지속 시간 추적
                    if self.jump_start_frame is None:
                        self.jump_start_frame = frame_number
                        self.jump_frames_count = 1
                    else:
                        self.jump_frames_count += 1
                else:
                    # 점프가 끝남 - 리셋
                    self.jump_start_frame = None
                    self.jump_frames_count = 0
            
            # 지속적인 위치 점프 확인
            sustained_jump = (self.jump_frames_count >= self.jump_duration_threshold)
            
            # 세션 상태 관리
            if not self.in_session:
                # 새 세션 시작 (항공기만 있으면 시작)
                if airplane_detections:
                    self._start_new_session(frame_number)
            else:
                # 현재 세션 중
                if sustained_jump:
                    # 지속적인 위치 점프로 인한 세션 종료
                    self._end_current_session()
                    # 새 세션 시작 (항공기가 있는 경우)
                    if airplane_detections:
                        self._start_new_session(frame_number)
                # 항공기가 사라진 경우에만 세션 종료 (새는 상관없음)
                elif not airplane_detections:
                    self._end_current_session()
            
            # 현재 세션에 데이터 추가
            if self.in_session:
                self.current_session_data['last_frame'] = frame_number
                
                # 항공기 데이터 추가
                self.current_session_data['airplane_positions'].append((frame_number, airplane['x'], airplane['z']))
                
                # 속도 계산 (이전 위치가 있는 경우)
                if (self.last_airplane_position is not None and 
                    self.last_frame_number is not None and 
                    frame_number > self.last_frame_number):
                    dt = frame_number - self.last_frame_number
                    vx = (airplane['x'] - self.last_airplane_position[0]) / dt
                    vz = (airplane['z'] - self.last_airplane_position[1]) / dt
                    self.current_session_data['airplane_velocities'].append((frame_number, vx, vz))
                
                # 새 데이터 추가
                if flock_detections:
                    flock = flock_detections[0]  # 첫 번째 새 사용
                    self.current_session_data['flock_positions'].append((frame_number, flock['x'], flock['z']))
                    
                    # 새 속도 계산 (이전 새 위치가 있는 경우)
                    if len(self.current_session_data['flock_positions']) > 1:
                        prev_flock = self.current_session_data['flock_positions'][-2]
                        dt = frame_number - prev_flock[0]
                        if dt > 0:
                            vx = (flock['x'] - prev_flock[1]) / dt
                            vz = (flock['z'] - prev_flock[2]) / dt
                            self.current_session_data['flock_velocities'].append((frame_number, vx, vz))
            
            # 현재 항공기 위치 저장
            self.last_airplane_position = current_airplane_pos
            self.last_frame_number = frame_number
        
        else:
            # 항공기가 없는 경우 세션 종료
            if self.in_session:
                self._end_current_session()
            # 점프 추적도 리셋
            self.jump_start_frame = None
            self.jump_frames_count = 0
    
    def _start_new_session(self, start_frame: int) -> None:
        """새 세션 시작"""
        self.current_session_id += 1
        self.in_session = True
        
        self.current_session_data = {
            'start_frame': start_frame,
            'last_frame': start_frame,
            'airplane_positions': [],
            'flock_positions': [],
            'airplane_velocities': [],
            'flock_velocities': []
        }
        
        # 점프 추적 리셋
        self.jump_start_frame = None
        self.jump_frames_count = 0
    
    def _end_current_session(self) -> None:
        """현재 세션 종료"""
        if not self.in_session:
            return
        
        session_length = self.current_session_data['last_frame'] - self.current_session_data['start_frame'] + 1
        
        # 최소 길이 체크
        if session_length < self.min_session_length:
            self.in_session = False
            return
        
        # 세션 생성
        session = Session(
            session_id=self.current_session_id,
            start_frame=self.current_session_data['start_frame'],
            end_frame=self.current_session_data['last_frame'],
            airplane_positions=self.current_session_data['airplane_positions'],
            flock_positions=self.current_session_data['flock_positions'],
            airplane_velocities=self.current_session_data['airplane_velocities'],
            flock_velocities=self.current_session_data['flock_velocities']
        )
        
        self.sessions.append(session)
        self.in_session = False

    def finalize(self) -> None:
        """마지막 세션 처리"""
        if self.in_session:
            self._end_current_session()

# 기존 호환성을 위한 별칭
Episode = Session
EpisodeTracker = SessionTracker

def process_triangulation_results(results_path: Path) -> List[Dict]:
    """삼각측량 결과 파일 로드"""
    with open(results_path, 'r') as f:
        results = json.load(f)
    
    # 프레임별 결과를 리스트로 변환
    detections = []
    for frame, objects in results.items():
        for obj in objects:
            detections.append({
                'frame': int(frame),
                'class': obj['class'],
                'x': obj['position'][0],
                'z': obj['position'][2],
                'confidence': obj['confidence']
            })
    
    return detections

def save_session_results(sessions: List[Session], output_path: Path):
    """세션 결과를 간단한 CSV로 저장"""
    print(f"\n💾 세션 데이터 저장 중... (총 {len(sessions)}개 세션)")
    
    # 전체 트래킹 데이터 (기존 호환성)
    all_tracking_data = []
    
    for session in sessions:
        # 항공기 데이터 추가
        for frame, x, z in session.airplane_positions:
            # 해당 프레임의 속도 찾기
            vel = next(((vx, vz) for f, vx, vz in session.airplane_velocities if f == frame), (0.0, 0.0))
            all_tracking_data.append({
                'frame': frame,
                'track_id': 1,  # 항공기는 항상 ID 1
                'class': 'Airplane',
                'x': x,
                'z': z,
                'vx': vel[0],
                'vz': vel[1],
                'session_id': session.session_id,
                'session_phase': 'active'
            })
        
        # 새 데이터 추가
        for frame, x, z in session.flock_positions:
            vel = next(((vx, vz) for f, vx, vz in session.flock_velocities if f == frame), (0.0, 0.0))
            all_tracking_data.append({
                'frame': frame,
                'track_id': 2,  # 새는 항상 ID 2
                'class': 'Flock',
                'x': x,
                'z': z,
                'vx': vel[0],
                'vz': vel[1],
                'session_id': session.session_id,
                'session_phase': 'active'
            })
    
    # CSV 저장 (기존 호환성)
    df = pd.DataFrame(all_tracking_data)
    df = df.sort_values(['session_id', 'frame'])
    csv_path = output_path / 'tracking_results.csv'
    df.to_csv(csv_path, index=False)
    print(f"✅ 트래킹 결과 CSV 저장: {csv_path}")
    
    # 간단한 요약 정보
    summary = {
        'total_sessions': len(sessions),
        'total_frames': sum(s.get_session_length() for s in sessions),
        'avg_session_length': np.mean([s.get_session_length() for s in sessions]) if sessions else 0,
    }
    
    summary_file = output_path / 'session_summary.json'
    with open(summary_file, 'w') as f:
        json.dump(summary, f, indent=2)
    print(f"✅ 세션 요약 저장: {summary_file}")
    
    print(f"\n📊 세션 통계:")
    print(f"  - 총 세션 수: {summary['total_sessions']}")
    print(f"  - 평균 길이: {summary['avg_session_length']:.1f} 프레임")

def main():
    """메인 실행 함수"""
    print("🚀 간소화된 세션 기반 트래킹 시스템 시작...")
    
    # 경로 설정
    script_path = Path(__file__).resolve()
    project_root = script_path.parent.parent  # scripts/ -> BirdRiskSim_v2/
    
    # 삼각측량 결과 파일 (최신 결과 자동 탐지)
    triangulation_dir = project_root / "data/triangulation_results"
    if not triangulation_dir.exists():
        print(f"❌ 삼각측량 결과 디렉토리를 찾을 수 없습니다: {triangulation_dir}")
        return
    
    result_dirs = list(triangulation_dir.glob("results_*"))
    if not result_dirs:
        print("❌ 삼각측량 결과를 찾을 수 없습니다.")
        return
    
    # 가장 최신 결과 폴더 선택 (수정 시간 기준)
    latest_results = max(result_dirs, key=lambda d: d.stat().st_mtime)
    results_path = latest_results / "triangulation_results.json"
    
    if not results_path.exists():
        print(f"❌ 삼각측량 결과 파일을 찾을 수 없습니다: {results_path}")
        return
    
    # 출력 디렉토리 (간소화: latest만 유지)
    latest_dir = project_root / "data/tracking_results/latest"
    latest_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"  - 입력: {results_path}")
    print(f"  - 출력: {latest_dir}")
    
    # 삼각측량 결과 로드
    detections = process_triangulation_results(results_path)
    print(f"  - {len(detections)}개 검출 결과 로드 완료")
    
    # 세션 트래커 초기화
    tracker = SessionTracker(position_jump_threshold=200.0, jump_duration_threshold=15, min_session_length=50)
    
    # 프레임별 세션 처리
    print("\n📊 세션 기반 트래킹 시작...")
    
    # 프레임 번호로 정렬
    detections.sort(key=lambda x: x['frame'])
    
    # 프레임별로 그룹화
    frame_detections = {}
    for det in detections:
        frame = det['frame']
        if frame not in frame_detections:
            frame_detections[frame] = []
        frame_detections[frame].append(det)
    
    # 연속된 모든 프레임 처리
    if frame_detections:
        min_frame = min(frame_detections.keys())
        max_frame = max(frame_detections.keys())
        
        for frame in range(min_frame, max_frame + 1):
            # 해당 프레임에 검출된 객체들 (없으면 빈 리스트)
            detections_in_frame = frame_detections.get(frame, [])
            
            # 세션 트래커 업데이트
            tracker.update(frame, detections_in_frame)
    
    # 마지막 세션 처리
    tracker.finalize()
    
    # 데이터 정제 및 저장
    print("\n🧹 데이터 정제 적용 중...")
    cleaned_sessions = []
    for session in tracker.sessions:
        cleaned = session.clean_data(position_jump_threshold=120.0, smoothing_window=3)
        # 정제 후 최소 길이 체크
        if len(cleaned.airplane_positions) >= 20 and len(cleaned.flock_positions) >= 20:
            cleaned_sessions.append(cleaned)
    
    print(f"✅ 정제 완료: {len(cleaned_sessions)}개 세션 유지")
    
    # 정제된 데이터 저장
    save_session_results(cleaned_sessions, latest_dir)
    
    print("\n🎉 처리 완료!")
    print(f"📁 결과: {latest_dir}")

if __name__ == "__main__":
    main() 