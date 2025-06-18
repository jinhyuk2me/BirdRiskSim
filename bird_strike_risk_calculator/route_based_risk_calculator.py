import json
import numpy as np
import os
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
import logging

@dataclass
class RoutePoint:
    """항공기 경로의 한 점을 나타내는 클래스"""
    x: float
    y: float
    z: float
    
    def to_array(self) -> np.ndarray:
        return np.array([self.x, self.y, self.z])

@dataclass
class FlightRoute:
    """항공기 비행 경로를 나타내는 클래스"""
    path_name: str
    waypoints: List[RoutePoint]
    route_points: List[RoutePoint]
    export_time: str
    total_waypoints: int

class RouteBasedRiskCalculator:
    """경로 기반 위험도 계산기"""
    
    def __init__(self, routes_directory: str = "data/routes"):
        """
        Args:
            routes_directory: 경로 JSON 파일들이 저장된 디렉토리
        """
        self.routes_directory = routes_directory
        self.flight_routes: Dict[str, FlightRoute] = {}
        self.logger = logging.getLogger(__name__)
        
        # 경로 데이터 로드
        self._load_all_routes()
    
    def _load_all_routes(self):
        """모든 경로 JSON 파일을 로드"""
        if not os.path.exists(self.routes_directory):
            self.logger.warning(f"Routes directory not found: {self.routes_directory}")
            return
        
        json_files = [f for f in os.listdir(self.routes_directory) if f.endswith('.json')]
        
        for json_file in json_files:
            # auto_processor_state.json 같은 비경로 파일 제외
            if json_file.startswith('auto_processor_state'):
                continue
                
            try:
                route = self._load_route_from_json(os.path.join(self.routes_directory, json_file))
                if route:
                    self.flight_routes[route.path_name] = route
                    self.logger.info(f"Loaded route: {route.path_name} with {len(route.route_points)} points")
            except Exception as e:
                self.logger.error(f"Failed to load route from {json_file}: {e}")
    
    def _load_route_from_json(self, json_path: str) -> Optional[FlightRoute]:
        """JSON 파일에서 경로 데이터를 로드"""
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # waypoints 변환
            waypoints = [
                RoutePoint(wp['x'], wp['y'], wp['z']) 
                for wp in data['waypoints']
            ]
            
            # route_points 변환
            route_points = [
                RoutePoint(rp['x'], rp['y'], rp['z']) 
                for rp in data['routePoints']
            ]
            
            return FlightRoute(
                path_name=data['pathName'],
                waypoints=waypoints,
                route_points=route_points,
                export_time=data['exportTime'],
                total_waypoints=data['totalWaypoints']
            )
            
        except Exception as e:
            self.logger.error(f"Error loading route from {json_path}: {e}")
            return None
    
    def calculate_distance_to_route(self, route_name: str, flock_position: np.ndarray) -> float:
        """
        새 떼 위치에서 특정 항공기 경로까지의 최단 거리 계산
        
        Args:
            route_name: 경로 이름
            flock_position: 새 떼의 3D 위치 [x, y, z]
            
        Returns:
            최단거리
        """
        if route_name not in self.flight_routes:
            self.logger.warning(f"Route not found: {route_name}")
            return float('inf')
        
        route = self.flight_routes[route_name]
        min_distance = float('inf')
        
        # 모든 경로 점에 대해 거리 계산
        for route_point in route.route_points:
            route_pos = route_point.to_array()
            distance = np.linalg.norm(flock_position - route_pos)
            
            if distance < min_distance:
                min_distance = distance
        
        return min_distance
    
    def get_closest_point_on_route(self, route_name: str, flock_position: np.ndarray) -> Tuple[float, np.ndarray, int]:
        """
        새 떼 위치에서 특정 경로의 가장 가까운 점 찾기
        
        Args:
            route_name: 경로 이름
            flock_position: 새 떼의 3D 위치 [x, y, z]
            
        Returns:
            Tuple[최단거리, 가장_가까운_경로점, 경로점_인덱스]
        """
        if route_name not in self.flight_routes:
            self.logger.warning(f"Route not found: {route_name}")
            return float('inf'), np.array([0, 0, 0]), -1
        
        route = self.flight_routes[route_name]
        min_distance = float('inf')
        closest_point = None
        closest_idx = -1
        
        # 모든 경로 점에 대해 거리 계산
        for i, route_point in enumerate(route.route_points):
            route_pos = route_point.to_array()
            distance = np.linalg.norm(flock_position - route_pos)
            
            if distance < min_distance:
                min_distance = distance
                closest_point = route_pos
                closest_idx = i
        
        return min_distance, closest_point, closest_idx
    
    def calculate_distance_to_all_routes(self, flock_position: np.ndarray) -> Dict[str, Tuple[float, np.ndarray]]:
        """
        새 떼 위치에서 모든 항공기 경로까지의 최단 거리 계산
        
        Args:
            flock_position: 새 떼의 3D 위치 [x, y, z]
            
        Returns:
            Dict[경로명, (최단거리, 가장_가까운_경로점)]
        """
        results = {}
        
        for route_name in self.flight_routes:
            distance, closest_point, _ = self.get_closest_point_on_route(route_name, flock_position)
            results[route_name] = (distance, closest_point)
        
        return results
    
    def get_closest_route(self, flock_position: np.ndarray) -> Tuple[str, float, np.ndarray]:
        """
        새 떼 위치에서 가장 가까운 항공기 경로 찾기
        
        Args:
            flock_position: 새 떼의 3D 위치 [x, y, z]
            
        Returns:
            Tuple[가장_가까운_경로명, 최단거리, 가장_가까운_경로점]
        """
        all_distances = self.calculate_distance_to_all_routes(flock_position)
        
        if not all_distances:
            return "", float('inf'), np.array([0, 0, 0])
        
        closest_route = min(all_distances.items(), key=lambda x: x[1][0])
        route_name = closest_route[0]
        distance, closest_point = closest_route[1]
        
        return route_name, distance, closest_point
    
    def calculate_route_segment_direction(self, route_name: str, closest_point: np.ndarray, 
                                        segment_length: int = 5) -> np.ndarray:
        """
        경로의 특정 지점에서 항공기 진행 방향 계산
        
        Args:
            route_name: 경로 이름
            closest_point: 가장 가까운 경로 점
            segment_length: 방향 계산에 사용할 세그먼트 길이
            
        Returns:
            정규화된 방향 벡터
        """
        if route_name not in self.flight_routes:
            return np.array([0, 0, 0])
        
        route = self.flight_routes[route_name]
        route_points = [rp.to_array() for rp in route.route_points]
        
        # 가장 가까운 경로 점의 인덱스 찾기
        closest_idx = 0
        min_dist = float('inf')
        
        for i, point in enumerate(route_points):
            dist = np.linalg.norm(point - closest_point)
            if dist < min_dist:
                min_dist = dist
                closest_idx = i
        
        # 진행 방향 계산 (앞쪽 세그먼트 사용)
        start_idx = max(0, closest_idx - segment_length // 2)
        end_idx = min(len(route_points) - 1, closest_idx + segment_length // 2)
        
        if start_idx == end_idx:
            return np.array([0, 0, 0])
        
        direction = route_points[end_idx] - route_points[start_idx]
        direction_norm = np.linalg.norm(direction)
        
        if direction_norm > 0:
            return direction / direction_norm
        else:
            return np.array([0, 0, 0])
    
    def get_available_routes(self) -> List[str]:
        """사용 가능한 모든 경로 이름 반환"""
        return list(self.flight_routes.keys())
    
    def get_route_info(self, route_name: str) -> Optional[Dict]:
        """특정 경로의 정보 반환"""
        if route_name not in self.flight_routes:
            return None
        
        route = self.flight_routes[route_name]
        return {
            'path_name': route.path_name,
            'total_waypoints': route.total_waypoints,
            'total_route_points': len(route.route_points),
            'export_time': route.export_time
        }

# 테스트 함수
def test_route_calculator():
    """경로 기반 위험도 계산기 테스트"""
    calculator = RouteBasedRiskCalculator()
    
    print("=== 경로 기반 위험도 계산기 테스트 ===")
    print(f"로드된 경로 수: {len(calculator.get_available_routes())}")
    
    for route_name in calculator.get_available_routes():
        info = calculator.get_route_info(route_name)
        print(f"경로: {route_name}")
        print(f"  - 웨이포인트: {info['total_waypoints']}개")
        print(f"  - 경로 점: {info['total_route_points']}개")
        print(f"  - 내보낸 시간: {info['export_time']}")
    
    # 테스트 새 떼 위치
    test_flock_position = np.array([100.0, 50.0, 150.0])
    
    print(f"\n테스트 새 떼 위치: {test_flock_position}")
    
    # 가장 가까운 경로 찾기
    closest_route, distance, closest_point = calculator.get_closest_route(test_flock_position)
    print(f"가장 가까운 경로: {closest_route}")
    print(f"최단 거리: {distance:.2f}m")
    print(f"가장 가까운 경로 점: {closest_point}")
    
    # 경로 방향 계산
    if closest_route:
        direction = calculator.calculate_route_segment_direction(closest_route, closest_point)
        print(f"경로 진행 방향: {direction}")

if __name__ == "__main__":
    test_route_calculator()