#!/usr/bin/env python3
"""
삼각측량 기반 경로 수집기
- real_time_pipeline.py에서 삼각측량 결과를 수집
- 여러 번의 실행으로 평균 경로 생성
- route_based_risk_calculator.py가 사용할 수 있는 형태로 저장
"""

import json
import numpy as np
import os
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
import logging
from datetime import datetime
from pathlib import Path

# 스무딩을 위한 추가 import
try:
    from scipy import interpolate
    from scipy.ndimage import gaussian_filter1d
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False
    print("Warning: scipy not available, using simple smoothing")

# --- 전역 상태 변수 ---
_collector_instance: Optional['TriangulationRouteCollector'] = None
_last_saved_path: Optional[Path] = None
# ---------------------

@dataclass
class TriangulatedPoint:
    """삼각측량된 점"""
    frame_id: int
    x: float
    y: float
    z: float
    object_type: str  # 'airplane' or 'flock'
    timestamp: float

class TriangulationRouteCollector:
    """삼각측량 기반 경로 수집기"""
    
    def __init__(self, data_directory: str = "data/routes"):
        """
        Args:
            data_directory: 수집된 데이터를 저장할 디렉토리
        """
        self.data_directory = Path(data_directory)
        self.logger = logging.getLogger(__name__)
        
        # 데이터 저장 디렉토리 생성
        self.data_directory.mkdir(parents=True, exist_ok=True)
        (self.data_directory / "raw_runs").mkdir(exist_ok=True)
        (self.data_directory / "averaged_routes").mkdir(exist_ok=True)
        
        # 현재 수집 중인 데이터
        self.current_run_data = []
        self.collection_active = False
        self.current_run_id = None
        
        self.logger.info(f"[TriangulationRouteCollector] 초기화 완료: {self.data_directory}")
    
    def start_collection(self, route_name: str) -> str:
        """데이터 수집 시작"""
        run_id = f"{route_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        self.current_run_id = run_id
        self.current_run_data = []
        self.collection_active = True
        
        self.logger.info(f"[TriangulationRouteCollector] 수집 시작: {run_id}")
        return run_id
    
    def add_triangulation_result(self, frame_id: int, triangulated_points: List[Dict]):
        """real_time_pipeline.py에서 삼각측량 결과 추가"""
        if not self.collection_active:
            return
        
        timestamp = datetime.now().timestamp()
        
        for point_data in triangulated_points:
            triangulated_point = TriangulatedPoint(
                frame_id=frame_id,
                x=point_data['position'][0],
                y=point_data['position'][1], 
                z=point_data['position'][2],
                object_type=point_data['class_name'].lower(),
                timestamp=timestamp
            )
            self.current_run_data.append(triangulated_point)
    
    def stop_collection(self) -> Optional[str]:
        """데이터 수집 종료 및 저장"""
        if not self.collection_active or not self.current_run_id:
            return None
        
        self.collection_active = False
        
        # 데이터 저장
        filename = f"{self.current_run_id}.json"
        filepath = self.data_directory / "raw_runs" / filename
        
        # JSON 직렬화를 위한 데이터 변환
        run_data = {
            'run_id': self.current_run_id,
            'collection_time': datetime.now().isoformat(),
            'total_points': len(self.current_run_data),
            'points': []
        }
        
        for point in self.current_run_data:
            point_dict = {
                'frame_id': point.frame_id,
                'x': point.x,
                'y': point.y,
                'z': point.z,
                'object_type': point.object_type,
                'timestamp': point.timestamp
            }
            run_data['points'].append(point_dict)
        
        global _last_saved_path
        _last_saved_path = filepath
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(run_data, f, indent=2, ensure_ascii=False)
        
        self.logger.info(f"[TriangulationRouteCollector] 데이터 저장 완료: {filepath}")
        self.logger.info(f"[TriangulationRouteCollector] 총 포인트 수: {len(self.current_run_data)}")
        
        run_id = self.current_run_id
        self.current_run_id = None
        self.current_run_data = []
        return run_id
    
    def load_raw_runs(self, route_name: str = None) -> List[Dict]:
        """저장된 실행 데이터 로드 (필터링된 데이터 우선 사용)"""
        # 먼저 필터링된 데이터가 있는지 확인
        filtered_runs_dir = self.data_directory / "averaged_routes"
        raw_runs_dir = self.data_directory / "raw_runs"
        
        # 필터링된 데이터 로드 시도
        filtered_files = []
        if filtered_runs_dir.exists():
            filtered_files = [f for f in filtered_runs_dir.glob("*.json") 
                            if not f.name.endswith("_averaged.json")]  # 평균 파일 제외
        
        # 필터링된 데이터가 있으면 우선 사용
        if filtered_files:
            self.logger.info(f"[TriangulationRouteCollector] 필터링된 데이터 사용: {len(filtered_files)}개 파일")
            json_files = filtered_files
            source_dir = "averaged_routes (filtered)"
        else:
            self.logger.info(f"[TriangulationRouteCollector] 원시 데이터 사용")
            json_files = list(raw_runs_dir.glob("*.json"))
            source_dir = "raw_runs"
        
        loaded_runs = []
        for json_file in json_files:
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    run_data = json.load(f)
                
                # 필터링
                if route_name and not run_data['run_id'].startswith(route_name):
                    continue
                
                loaded_runs.append(run_data)
            except Exception as e:
                self.logger.error(f"Failed to load {json_file}: {e}")
        
        self.logger.info(f"[TriangulationRouteCollector] 로드 완료: {len(loaded_runs)}개 실행 ({source_dir})")
        return loaded_runs
    
    def calculate_average_route(self, route_name: str, min_runs: int = 3) -> Optional[Dict]:
        """여러 실행 데이터를 평균내어 평균 경로 생성"""
        runs = self.load_raw_runs(route_name)
        
        if len(runs) < min_runs:
            self.logger.warning(f"[TriangulationRouteCollector] 평균 계산을 위한 최소 실행 수({min_runs})가 부족합니다. 현재: {len(runs)}")
            return None
        
        self.logger.info(f"[TriangulationRouteCollector] {len(runs)}개 실행 데이터로 평균 경로 계산 중...")
        
        # 객체 타입별로 분리하여 처리
        airplane_points = []
        flock_points = []
        
        for run in runs:
            for point in run['points']:
                if point['object_type'] == 'airplane':
                    airplane_points.append(point)
                elif point['object_type'] == 'flock':
                    flock_points.append(point)
        
        # 항공기 경로 평균 계산
        airplane_route = self._calculate_object_average_route(airplane_points, 'airplane')
        
        if not airplane_route:
            self.logger.error("[TriangulationRouteCollector] 항공기 경로 계산 실패")
            return None
        
        # route_based_risk_calculator.py 호환 형식으로 변환
        route_data = {
            'pathName': route_name,
            'exportTime': datetime.now().isoformat(),
            'totalWaypoints': len(airplane_route),
            'waypoints': [],
            'routePoints': []
        }
        
        # waypoints와 routePoints를 동일하게 설정 (단순화)
        for i, point in enumerate(airplane_route):
            point_dict = {
                'x': point['x'],
                'y': point['y'], 
                'z': point['z']
            }
            route_data['waypoints'].append(point_dict)
            route_data['routePoints'].append(point_dict)
        
        # 저장
        filename = f"{route_name}_averaged.json"
        filepath = self.data_directory / "averaged_routes" / filename
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(route_data, f, indent=2, ensure_ascii=False)
        
        self.logger.info(f"[TriangulationRouteCollector] 평균 경로 저장 완료: {filepath}")
        self.logger.info(f"[TriangulationRouteCollector] 총 경로점: {len(airplane_route)}, 사용된 실행: {len(runs)}")
        
        return route_data
    
    def _calculate_object_average_route(self, points: List[Dict], object_type: str) -> List[Dict]:
        """특정 객체의 평균 경로 계산 - Raw 데이터 보존 우선"""
        if not points:
            return []
        
        # 프레임별로 그룹화
        frame_groups = {}
        for point in points:
            frame_id = point['frame_id']
            if frame_id not in frame_groups:
                frame_groups[frame_id] = []
            frame_groups[frame_id].append(point)
        
        # 각 프레임별 처리 - 과도한 평균화 방지
        averaged_route = []
        for frame_id in sorted(frame_groups.keys()):
            frame_points = frame_groups[frame_id]
            
            if len(frame_points) >= 1:
                if len(frame_points) == 1:
                    # 단일 점인 경우 그대로 사용 (평균화 불필요)
                    point = frame_points[0]
                    avg_x, avg_y, avg_z = point['x'], point['y'], point['z']
                elif len(frame_points) <= 3:
                    # 적은 수의 점들은 단순 평균
                    avg_x = np.mean([p['x'] for p in frame_points])
                    avg_y = np.mean([p['y'] for p in frame_points])
                    avg_z = np.mean([p['z'] for p in frame_points])
                else:
                    # 많은 점들이 있는 경우 중앙값과 평균의 가중 조합 (이상치 영향 최소화)
                    x_vals = [p['x'] for p in frame_points]
                    y_vals = [p['y'] for p in frame_points]
                    z_vals = [p['z'] for p in frame_points]
                    
                    # 중앙값 70% + 평균 30% (자연스러운 경로 보존)
                    avg_x = 0.7 * np.median(x_vals) + 0.3 * np.mean(x_vals)
                    avg_y = 0.7 * np.median(y_vals) + 0.3 * np.mean(y_vals)
                    avg_z = 0.7 * np.median(z_vals) + 0.3 * np.mean(z_vals)
                
                averaged_route.append({
                    'frame_id': frame_id,
                    'x': float(avg_x),
                    'y': float(avg_y),
                    'z': float(avg_z),
                    'sample_count': len(frame_points)
                })
        
        self.logger.info(f"[TriangulationRouteCollector] {object_type} 평균 경로 계산 완료: {len(averaged_route)}개 점")
        
        # 🎯 스무딩 적용
        smoothed_route = self._smooth_route(averaged_route, smoothing_factor=0.3)
        self.logger.info(f"[TriangulationRouteCollector] {object_type} 경로 스무딩 완료")
        
        return smoothed_route
    
    def _smooth_route(self, route_points: List[Dict], smoothing_factor: float = 0.3) -> List[Dict]:
        """경로 스무딩 - 급격한 변화를 부드럽게 만듦"""
        if len(route_points) < 3:
            return route_points
        
        # 좌표 추출
        x_coords = np.array([p['x'] for p in route_points])
        y_coords = np.array([p['y'] for p in route_points])
        z_coords = np.array([p['z'] for p in route_points])
        
        if SCIPY_AVAILABLE and len(route_points) >= 5:
            # scipy 사용한 정교한 스무딩
            try:
                # 가우시안 필터 적용 (sigma 값으로 스무딩 강도 조절)
                sigma = max(1.0, len(route_points) * 0.02)  # 동적 시그마
                
                x_smooth = gaussian_filter1d(x_coords, sigma=sigma)
                y_smooth = gaussian_filter1d(y_coords, sigma=sigma)
                z_smooth = gaussian_filter1d(z_coords, sigma=sigma)
                
                # 원래 데이터와 스무딩된 데이터의 가중 평균
                x_final = (1 - smoothing_factor) * x_coords + smoothing_factor * x_smooth
                y_final = (1 - smoothing_factor) * y_coords + smoothing_factor * y_smooth
                z_final = (1 - smoothing_factor) * z_coords + smoothing_factor * z_smooth
                
                self.logger.info(f"[TriangulationRouteCollector] scipy 가우시안 스무딩 적용 (sigma={sigma:.2f})")
                
            except Exception as e:
                self.logger.warning(f"[TriangulationRouteCollector] scipy 스무딩 실패, 단순 스무딩 사용: {e}")
                # 단순 스무딩으로 fallback
                x_final, y_final, z_final = self._simple_smoothing(x_coords, y_coords, z_coords, smoothing_factor)
        else:
            # 단순 이동 평균 스무딩
            x_final, y_final, z_final = self._simple_smoothing(x_coords, y_coords, z_coords, smoothing_factor)
        
        # 결과 생성
        smoothed_route = []
        for i, point in enumerate(route_points):
            smoothed_point = point.copy()
            smoothed_point['x'] = float(x_final[i])
            smoothed_point['y'] = float(y_final[i])
            smoothed_point['z'] = float(z_final[i])
            smoothed_route.append(smoothed_point)
        
        return smoothed_route
    
    def _simple_smoothing(self, x_coords: np.ndarray, y_coords: np.ndarray, z_coords: np.ndarray, 
                         smoothing_factor: float) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """단순 이동 평균 스무딩"""
        window_size = min(5, len(x_coords) // 3)
        if window_size >= 3:
            # 이동 평균 적용
            x_smooth = np.convolve(x_coords, np.ones(window_size)/window_size, mode='same')
            y_smooth = np.convolve(y_coords, np.ones(window_size)/window_size, mode='same')
            z_smooth = np.convolve(z_coords, np.ones(window_size)/window_size, mode='same')
            
            # 원래 데이터와 스무딩된 데이터의 가중 평균
            x_final = (1 - smoothing_factor) * x_coords + smoothing_factor * x_smooth
            y_final = (1 - smoothing_factor) * y_coords + smoothing_factor * y_smooth
            z_final = (1 - smoothing_factor) * z_coords + smoothing_factor * z_smooth
            
            self.logger.info(f"[TriangulationRouteCollector] 단순 이동평균 스무딩 적용 (window={window_size})")
        else:
            # 너무 적은 점들은 스무딩하지 않음
            x_final, y_final, z_final = x_coords, y_coords, z_coords
            self.logger.info(f"[TriangulationRouteCollector] 점이 너무 적어 스무딩 생략")
        
        return x_final, y_final, z_final
    
    def copy_to_routes_directory(self, route_name: str, target_dir: str = "data/routes"):
        """평균 경로를 route_based_risk_calculator.py가 사용하는 디렉토리로 복사"""
        source_file = self.data_directory / "averaged_routes" / f"{route_name}_averaged.json"
        target_dir_path = Path(target_dir)
        target_dir_path.mkdir(parents=True, exist_ok=True)
        target_file = target_dir_path / f"{route_name}.json"
        
        if source_file.exists():
            import shutil
            shutil.copy2(source_file, target_file)
            self.logger.info(f"[TriangulationRouteCollector] 경로 복사 완료: {target_file}")
            return True
        else:
            self.logger.error(f"[TriangulationRouteCollector] 소스 파일 없음: {source_file}")
            return False
    
    def get_collection_status(self) -> Dict:
        """현재 수집 상태 반환"""
        return {
            'active': self.collection_active,
            'current_run': self.current_run_id,
            'points_collected': len(self.current_run_data) if self.current_run_data else 0
        }
    
    def list_available_routes(self) -> List[str]:
        """사용 가능한 평균 경로 목록 반환"""
        averaged_dir = self.data_directory / "averaged_routes"
        json_files = list(averaged_dir.glob("*_averaged.json"))
        
        routes = []
        for json_file in json_files:
            route_name = json_file.stem.replace('_averaged', '')
            routes.append(route_name)
        
        return routes

# real_time_pipeline.py에서 사용할 전역 인스턴스
_route_collector = None

def initialize_route_collector(data_directory: str = "data/routes"):
    """경로 수집기 초기화"""
    global _route_collector
    _route_collector = TriangulationRouteCollector(data_directory)
    return _route_collector

def start_route_collection(route_name: str) -> str:
    """경로 수집 시작"""
    if _route_collector is None:
        initialize_route_collector()
    return _route_collector.start_collection(route_name)

def add_triangulation_data(frame_id: int, triangulated_points: List[Dict]):
    """삼각측량 데이터 추가"""
    if _route_collector is not None:
        _route_collector.add_triangulation_result(frame_id, triangulated_points)

def stop_route_collection() -> Optional[str]:
    """경로 수집 종료"""
    if _route_collector is not None:
        return _route_collector.stop_collection()
    return None

def generate_average_route(route_name: str, min_runs: int = 3) -> bool:
    """평균 경로 생성 및 routes 디렉토리로 복사"""
    if _route_collector is None:
        return False
    
    # 평균 경로 계산
    result = _route_collector.calculate_average_route(route_name, min_runs)
    if result is None:
        return False
    
    # routes 디렉토리로 복사
    return _route_collector.copy_to_routes_directory(route_name)

def get_last_saved_run_path() -> Optional[Path]:
    """가장 최근에 저장된 개별 실행 파일의 경로를 반환합니다."""
    return _last_saved_path

# 테스트 함수
def test_triangulation_route_collector():
    """삼각측량 경로 수집기 테스트"""
    collector = TriangulationRouteCollector()
    
    print("=== 삼각측량 경로 수집기 테스트 ===")
    
    # 가상의 데이터로 테스트
    run_id = collector.start_collection("test_route")
    print(f"수집 시작: {run_id}")
    
    # 가상의 삼각측량 결과 추가
    for i in range(100):
        # 가상의 항공기 궤적 (직선 경로)
        airplane_point = {
            'position': [100 + i*2, 50, 200 + i*1.5],
            'class_name': 'Airplane'
        }
        
        # 가상의 새떼 (랜덤 위치)
        flock_point = {
            'position': [np.random.randint(50, 300), 20, np.random.randint(150, 350)],
            'class_name': 'Flock'
        }
        
        collector.add_triangulation_result(i, [airplane_point, flock_point])
    
    # 수집 종료
    saved_run = collector.stop_collection()
    print(f"수집 완료: {saved_run}")
    
    # 평균 경로 생성 (최소 실행 수를 1로 설정하여 테스트)
    avg_result = collector.calculate_average_route("test_route", min_runs=1)
    if avg_result:
        print(f"평균 경로 생성 완료: {len(avg_result['routePoints'])}개 점")
        
        # routes 디렉토리로 복사
        copy_success = collector.copy_to_routes_directory("test_route")
        print(f"routes 디렉토리 복사: {'성공' if copy_success else '실패'}")
    
    # 상태 확인
    status = collector.get_collection_status()
    print(f"현재 상태: {status}")
    
    available_routes = collector.list_available_routes()
    print(f"사용 가능한 경로: {available_routes}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_triangulation_route_collector() 