#!/usr/bin/env python3
"""
BirdRiskSim 3D Triangulation Module
- Unity 카메라 파라미터 처리
- YOLO 결과 삼각측량
- 실시간 및 배치 처리 지원
"""

import sys
import os
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
script_path = Path(__file__).resolve()
project_root = script_path.parent.parent  # scripts/ -> BirdRiskSim_v2/
sys.path.insert(0, str(project_root))

import cv2
import numpy as np
import json
from typing import List, Dict, Optional, Tuple, Union
# 🎯 항공 감지 통합 모듈 import
from aviation_detector import AviationDetector
import pandas as pd
from datetime import datetime
import glob

# =========================
# 🔧 카메라 파라미터 처리
# =========================

def load_camera_parameters(json_path: Union[str, Path]) -> Dict:
    """JSON 파일에서 카메라 파라미터를 로드"""
    with open(json_path, 'r') as f:
        params = json.load(f)
    return params

def calculate_stereo_calibration(params1: Dict, params2: Dict) -> Dict:
    """
    두 카메라 간의 정확한 스테레오 캘리브레이션 계산
    
    Args:
        params1, params2: 카메라 파라미터 딕셔너리
    
    Returns:
        스테레오 캘리브레이션 결과 (R, T, 스케일 팩터 등)
    """
    # 카메라 내부 파라미터 추출
    def extract_intrinsic_matrix(params):
        # Unity projectionMatrix에서 내부 파라미터 추출
        proj = params['projectionMatrix']
        width = params['imageWidth']
        height = params['imageHeight']
        
        # Unity projection matrix를 OpenCV 내부 파라미터로 변환
        fx = proj['m00'] * width / 2
        fy = proj['m11'] * height / 2
        cx = width / 2
        cy = height / 2
        
        K = np.array([
            [fx, 0, cx],
            [0, fy, cy],
            [0, 0, 1]
        ], dtype=np.float32)
        
        return K
    
    # 카메라 외부 파라미터 추출 (Unity 월드 좌표계)
    def extract_extrinsic_params(params):
        pos = params['position_UnityWorld']
        rot = params['rotation_UnityWorld']
        
        # Unity 카메라 위치 (월드 좌표계)
        t_world = np.array([pos['x'], pos['y'], pos['z']], dtype=np.float32)
        
        # Unity 쿼터니언을 회전 행렬로 변환 (카메라 → 월드)
        q = [rot['x'], rot['y'], rot['z'], rot['w']]
        R_cam_to_world = quaternion_to_rotation_matrix_corrected(q)
        
        # 월드 → 카메라 변환
        R_world_to_cam = R_cam_to_world.T
        t_world_to_cam = -R_world_to_cam @ t_world
        
        return R_world_to_cam, t_world_to_cam
    
    # 내부 파라미터
    K1 = extract_intrinsic_matrix(params1)
    K2 = extract_intrinsic_matrix(params2)
    
    # 외부 파라미터
    R1, t1 = extract_extrinsic_params(params1)
    R2, t2 = extract_extrinsic_params(params2)
    
    # 상대적 회전과 평행이동 계산
    R_rel = R2 @ R1.T  # 카메라1에서 카메라2로의 회전
    t_rel = t2 - R_rel @ t1  # 상대적 평행이동
    
    # 베이스라인 거리 계산
    baseline = np.linalg.norm(t2 - t1)
    
    # 스케일 팩터 계산 (Unity 단위 기준)
    unity_scale = 1.0  # Unity는 미터 단위 사용
    
    return {
        'K1': K1, 'K2': K2,
        'R': R_rel, 'T': t_rel,
        'baseline': baseline,
        'scale_factor': unity_scale,
        'camera1_pos': t1,
        'camera2_pos': t2,
        'camera1_rot': R1,
        'camera2_rot': R2
    }

def quaternion_to_rotation_matrix(q):
    """쿼터니언을 회전 행렬로 변환 (기존 호환성 유지)"""
    x, y, z, w = q
    
    # Unity 쿼터니언을 회전 행렬로 변환
    R = np.array([
        [1 - 2*(y*y + z*z), 2*(x*y - z*w), 2*(x*z + y*w)],
        [2*(x*y + z*w), 1 - 2*(x*x + z*z), 2*(y*z - x*w)],
        [2*(x*z - y*w), 2*(y*z + x*w), 1 - 2*(x*x + y*y)]
    ], dtype=np.float32)
    
    return R

def quaternion_to_rotation_matrix_corrected(q):
    """올바른 쿼터니언 → 회전 행렬 변환"""
    x, y, z, w = q
    
    # 정규화
    norm = np.sqrt(x*x + y*y + z*z + w*w)
    if norm > 0:
        x, y, z, w = x/norm, y/norm, z/norm, w/norm
    
    # 회전 행렬 계산
    R = np.array([
        [1 - 2*(y*y + z*z), 2*(x*y - z*w), 2*(x*z + y*w)],
        [2*(x*y + z*w), 1 - 2*(x*x + z*z), 2*(y*z - x*w)],
        [2*(x*z - y*w), 2*(y*z + x*w), 1 - 2*(x*x + y*y)]
    ], dtype=np.float32)
    
    return R

def triangulate_point_stereo(point1: List[float], point2: List[float], 
                           stereo_calib: Dict) -> Optional[np.ndarray]:
    """
    스테레오 캘리브레이션 정보를 사용한 정확한 삼각측량
    
    Args:
        point1, point2: 이미지 좌표 [x, y]
        stereo_calib: calculate_stereo_calibration 결과
    
    Returns:
        Unity 월드 좌표 3D 위치 [x, y, z] 또는 None (실패시)
    """
    try:
        # 이미지 좌표를 정규화된 좌표로 변환
        K1, K2 = stereo_calib['K1'], stereo_calib['K2']
        
        # 정규화된 좌표 계산
        point1_norm = np.linalg.inv(K1) @ np.array([point1[0], point1[1], 1])
        point2_norm = np.linalg.inv(K2) @ np.array([point2[0], point2[1], 1])
        
        # 삼각측량 (DLT 방법)
        R, T = stereo_calib['R'], stereo_calib['T']
        
        # 투영 행렬 구성
        P1 = K1 @ np.hstack([np.eye(3), np.zeros((3, 1))])  # 첫 번째 카메라 (기준)
        P2 = K2 @ np.hstack([R, T.reshape(-1, 1)])  # 두 번째 카메라
        
        # OpenCV 삼각측량
        points1 = np.array([[point1[0]], [point1[1]]], dtype=np.float32)
        points2 = np.array([[point2[0]], [point2[1]]], dtype=np.float32)
        
        points_4d_hom = cv2.triangulatePoints(P1, P2, points1, points2)
        points_3d = (points_4d_hom[:3] / points_4d_hom[3]).flatten()
        
        # 결과는 이미 첫 번째 카메라 기준 좌표계에서 계산됨
        # 월드 좌표계로 변환하려면 첫 번째 카메라의 역변환 적용
        R1, t1 = stereo_calib['camera1_rot'], stereo_calib['camera1_pos']
        
        # 카메라 좌표계 → Unity 월드 좌표계 (R1은 이미 world_to_cam이므로 역변환)
        point_3d_unity = R1.T @ (points_3d - t1)
        
        # 스케일 팩터 적용
        point_3d_unity *= stereo_calib['scale_factor']
        
        print(f"🔄 스테레오 삼각측량: 카메라({points_3d[0]:.1f}, {points_3d[1]:.1f}, {points_3d[2]:.1f}) → Unity({point_3d_unity[0]:.1f}, {point_3d_unity[1]:.1f}, {point_3d_unity[2]:.1f})")
        
        return point_3d_unity
        
    except Exception as e:
        print(f"❌ 스테레오 삼각측량 오류: {e}")
        return None

def get_projection_matrix(params: Dict) -> np.ndarray:
    """
    Unity 카메라 파라미터로부터 올바른 OpenCV 호환 투영 행렬 계산
    """
    # 1. Unity 내부 파라미터 추출
    proj = params['projectionMatrix']
    width = params['imageWidth']
    height = params['imageHeight']
    
    # Unity projection matrix에서 내부 파라미터 추출
    fx = proj['m00'] * width / 2.0
    fy = proj['m11'] * height / 2.0
    cx = width / 2.0
    cy = height / 2.0
    
    # 내부 파라미터 행렬
    K = np.array([
        [fx, 0, cx],
        [0, fy, cy],
        [0, 0, 1]
    ], dtype=np.float32)
    
    # 2. Unity 외부 파라미터 추출 (카메라 → 월드)
    pos = params['position_UnityWorld']
    rot = params['rotation_UnityWorld']
    
    # Unity 카메라 위치 (월드 좌표계)
    t_world = np.array([pos['x'], pos['y'], pos['z']], dtype=np.float32)
    
    # Unity 쿼터니언을 회전 행렬로 변환 (카메라 → 월드)
    q = [rot['x'], rot['y'], rot['z'], rot['w']]
    R_cam_to_world = quaternion_to_rotation_matrix_corrected(q)
    
    # 3. 월드 → 카메라 변환 계산
    R_world_to_cam = R_cam_to_world.T  # 역회전
    t_world_to_cam = -R_world_to_cam @ t_world  # 역변환
    
    # 4. Unity → OpenCV 좌표계 변환
    # Unity: Y-up, Z-forward (LHS)
    # OpenCV: Y-up, Z-forward (RHS) - Y축 반전 제거
    unity_to_opencv = np.array([
        [1,  0,  0],   # X축 그대로
        [0,  1,  0],   # Y축 그대로 (반전 제거)
        [0,  0,  1]    # Z축 그대로
    ], dtype=np.float32)
    
    # OpenCV 좌표계로 변환
    R_opencv = unity_to_opencv @ R_world_to_cam @ unity_to_opencv.T
    t_opencv = unity_to_opencv @ t_world_to_cam
    
    # 5. 투영 행렬 P = K[R|t]
    Rt = np.hstack([R_opencv, t_opencv.reshape(3, 1)])
    P = K @ Rt
    
    return P

def get_projection_matrix_simple(params: Dict) -> np.ndarray:
    """
    실시간 파이프라인용 간단한 투영 행렬 계산
    (기존 real_time_pipeline.py의 방식과 호환)
    """
    # 내부 파라미터 행렬
    K = np.array([
        [params['fx'], 0, params['cx']],
        [0, params['fy'], params['cy']],
        [0, 0, 1]
    ])
    
    # 회전 행렬
    R = np.array(params['rotation_matrix'])
    
    # 이동 벡터
    t = np.array(params['translation_vector']).reshape(3, 1)
    
    # 외부 파라미터 행렬 [R|t]
    Rt = np.hstack([R, t])
    
    # 투영 행렬 P = K[R|t]
    P = K @ Rt
    
    return P

# =========================
# 🎯 객체 매칭 및 병합
# =========================

def merge_nearby_flocks_2d(flocks: List[Tuple], distance_threshold: float = 100) -> List[Tuple]:
    """
    2D 이미지에서 가까운 거리에 있는 flock들을 통합 (배치 처리용)
    
    Args:
        flocks: [(box, conf), ...] 형태의 flock 리스트
        distance_threshold: 통합할 최대 거리 (픽셀 단위)
    
    Returns:
        통합된 flock 리스트
    """
    if not flocks:
        return []
        
    # 중심점 기준으로 거리 계산
    centers = np.array([box[:2] for box, _ in flocks])
    confidences = np.array([conf for _, conf in flocks])
    
    # 거리 행렬 계산
    distances = np.zeros((len(flocks), len(flocks)))
    for i in range(len(flocks)):
        for j in range(i+1, len(flocks)):
            dist = np.linalg.norm(centers[i] - centers[j])
            distances[i,j] = distances[j,i] = dist
    
    # 통합할 그룹 찾기
    merged_groups = []
    used = set()
    
    for i in range(len(flocks)):
        if i in used:
            continue
            
        # 현재 flock과 가까운 flock들 찾기
        nearby = [j for j in range(len(flocks)) 
                 if distances[i,j] < distance_threshold and j not in used]
        
        if nearby:
            group = [i] + nearby
            merged_groups.append(group)
            used.update(group)
        else:
            merged_groups.append([i])
            used.add(i)
    
    # 각 그룹 통합
    merged_flocks = []
    for group in merged_groups:
        if len(group) == 1:
            # 단일 flock은 그대로 유지
            merged_flocks.append(flocks[group[0]])
        else:
            # 여러 flock 통합
            group_boxes = np.array([flocks[i][0] for i in group])
            group_confs = np.array([flocks[i][1] for i in group])
            
            # 가중 평균으로 중심점 계산
            weights = group_confs / np.sum(group_confs)
            merged_center = np.sum(group_boxes[:, :2] * weights[:, None], axis=0)
            
            # 크기는 최대값 사용
            merged_size = np.max(group_boxes[:, 2:], axis=0)
            
            # 신뢰도는 평균 사용
            merged_conf = np.mean(group_confs)
            
            merged_box = np.concatenate([merged_center, merged_size])
            merged_flocks.append((merged_box, merged_conf))
    
    return merged_flocks

def merge_nearby_flocks_3d(points: List[Dict], distance_threshold: float = 100) -> List[Dict]:
    """
    3D 공간에서 근접한 무리 병합 (실시간 파이프라인용)
    
    Args:
        points: 3D 위치 정보가 있는 객체 리스트
        distance_threshold: 통합할 최대 거리 (미터 단위)
    
    Returns:
        통합된 점 리스트
    """
    if not points:
        return points
    
    # Flock만 필터링
    flocks = [p for p in points if p['class'] == 'Flock']
    others = [p for p in points if p['class'] != 'Flock']
    
    if len(flocks) <= 1:
        return points
    
    # 거리 기반 병합
    merged_flocks = []
    used_indices = set()
    
    for i, flock1 in enumerate(flocks):
        if i in used_indices:
            continue
        
        # 현재 무리와 병합할 무리들 찾기
        merge_group = [flock1]
        used_indices.add(i)
        
        for j, flock2 in enumerate(flocks):
            if j in used_indices:
                continue
            
            # 거리 계산 (XZ 평면)
            dist = np.sqrt(
                (flock1['x'] - flock2['x'])**2 + 
                (flock1['z'] - flock2['z'])**2
            )
            
            if dist < distance_threshold:
                merge_group.append(flock2)
                used_indices.add(j)
        
        # 병합된 무리의 평균 위치 계산
        if len(merge_group) > 1:
            avg_x = np.mean([f['x'] for f in merge_group])
            avg_y = np.mean([f['y'] for f in merge_group])
            avg_z = np.mean([f['z'] for f in merge_group])
            avg_conf = np.mean([f['confidence'] for f in merge_group])
            
            merged_flock = {
                'frame': flock1['frame'],
                'class': 'Flock',
                'x': avg_x,
                'y': avg_y,
                'z': avg_z,
                'confidence': avg_conf,
                'cameras': f"merged_{len(merge_group)}_flocks"
            }
            merged_flocks.append(merged_flock)
        else:
            merged_flocks.append(flock1)
    
    return merged_flocks + others

def match_objects_yolo(results1, results2) -> List[Dict]:
    """
    두 YOLO 결과에서 클래스별로 객체를 매칭 (배치 처리용)
    Flock의 경우 가까운 것들끼리 통합 후 매칭
    """
    matches = []
    
    # Flock과 다른 클래스 분리
    flocks1 = []
    others1 = {}
    for b, c, conf in zip(results1.boxes.xywh.cpu(), results1.boxes.cls.cpu(), results1.boxes.conf.cpu()):
        cls_name = results1.names[int(c)]
        if cls_name == "Flock":
            flocks1.append((b, conf))
        else:
            others1[cls_name] = (b, conf)
    
    flocks2 = []
    others2 = {}
    for b, c, conf in zip(results2.boxes.xywh.cpu(), results2.boxes.cls.cpu(), results2.boxes.conf.cpu()):
        cls_name = results2.names[int(c)]
        if cls_name == "Flock":
            flocks2.append((b, conf))
        else:
            others2[cls_name] = (b, conf)
    
    # Flock 통합
    merged_flocks1 = merge_nearby_flocks_2d(flocks1)
    merged_flocks2 = merge_nearby_flocks_2d(flocks2)
    
    # 통합된 Flock 매칭
    for box1, conf1 in merged_flocks1:
        for box2, conf2 in merged_flocks2:
            pt1 = np.array([box1[0], box1[1]], dtype=np.float32)
            pt2 = np.array([box2[0], box2[1]], dtype=np.float32)
            
            matches.append({
                'class': "Flock",
                'pt1': pt1,
                'pt2': pt2,
                'conf1': conf1,
                'conf2': conf2
            })
    
    # 다른 클래스 매칭
    common_classes = set(others1.keys()) & set(others2.keys())
    for cls_name in common_classes:
        box1, conf1 = others1[cls_name]
        box2, conf2 = others2[cls_name]
        
        pt1 = np.array([box1[0], box1[1]], dtype=np.float32)
        pt2 = np.array([box2[0], box2[1]], dtype=np.float32)
        
        matches.append({
            'class': cls_name,
            'pt1': pt1,
            'pt2': pt2,
            'conf1': conf1,
            'conf2': conf2
        })
    
    return matches

def match_objects_simple(detections1: List[Dict], detections2: List[Dict]) -> List[Dict]:
    """
    두 카메라의 감지 결과 매칭 (실시간 파이프라인용) - 개선된 버전
    
    Args:
        detections1, detections2: [{'class': str, 'center': [x,y], 'confidence': float}, ...]
    
    Returns:
        매칭된 결과 리스트
    """
    matches = []
    used_det2_indices = set()  # 이미 매칭된 det2 인덱스 추적
    
    for det1 in detections1:
        for i, det2 in enumerate(detections2):
            # 이미 매칭된 det2는 건너뛰기
            if i in used_det2_indices:
                continue
                
            if det1['class'] == det2['class']:
                matches.append({
                    'class': det1['class'],
                    'det1': det1,
                    'det2': det2
                })
                used_det2_indices.add(i)  # 매칭된 det2 인덱스 기록
                break  # 이 det1에 대한 매칭 완료
    
    return matches

# =========================
# 🔺 삼각측량 핵심 함수
# =========================

def triangulate_point(point1: List[float], point2: List[float], 
                     P1: np.ndarray, P2: np.ndarray,
                     camera_positions: List[np.ndarray] = None) -> Optional[np.ndarray]:
    """
    올바른 삼각측량 (좌표계 변환 없이 직접 계산)
    
    Args:
        point1, point2: 이미지 좌표 [x, y]
        P1, P2: 카메라 투영 행렬
        camera_positions: 카메라 Unity 월드 위치 리스트 (사용하지 않음)
    
    Returns:
        Unity 월드 좌표 3D 위치 [x, y, z] 또는 None (실패시)
    """
    try:
        # 이미지 좌표를 homogeneous 형태로 변환
        points1 = np.array([[point1[0]], [point1[1]]], dtype=np.float32)
        points2 = np.array([[point2[0]], [point2[1]]], dtype=np.float32)
        
        # OpenCV 삼각측량
        points_4d_hom = cv2.triangulatePoints(P1, P2, points1, points2)
        
        # Homogeneous → 3D 좌표 변환
        if points_4d_hom[3, 0] != 0:
            points_3d = points_4d_hom[:3, 0] / points_4d_hom[3, 0]
        else:
            return None
        
        # 결과는 이미 올바른 Unity 월드 좌표계
        print(f"🔄 삼각측량 결과: Unity({points_3d[0]:.1f}, {points_3d[1]:.1f}, {points_3d[2]:.1f})")
        
        return points_3d
        
    except Exception as e:
        print(f"❌ 삼각측량 오류: {e}")
        return None

def triangulate_objects_realtime(detections: List[Dict], 
                                projection_matrices: List[np.ndarray],
                                camera_letters: List[str],
                                frame_id: int,
                                distance_threshold: float = 100) -> List[Dict]:
    """
    실시간 파이프라인용 객체 삼각측량
    
    Args:
        detections: [{'camera': str, 'class': str, 'center': [x,y], 'confidence': float}, ...]
        projection_matrices: 카메라 투영 행렬 리스트
        camera_letters: 카메라 문자 리스트 ['A', 'B', 'C', 'D']
        frame_id: 프레임 ID
        distance_threshold: 근접 무리 병합 임계값
    
    Returns:
        삼각측량된 3D 위치 리스트
    """
    if len(projection_matrices) < 2:
        return []
    
    # 카메라별로 감지 결과 그룹화
    camera_detections = {}
    for det in detections:
        camera = det['camera']
        if camera not in camera_detections:
            camera_detections[camera] = []
        camera_detections[camera].append(det)
    
    triangulated_points = []
    
    # 카메라 쌍별로 삼각측량 수행
    available_cameras = list(camera_detections.keys())
    for i in range(len(available_cameras)):
        for j in range(i + 1, len(available_cameras)):
            cam1, cam2 = available_cameras[i], available_cameras[j]
            cam1_idx = camera_letters.index(cam1)
            cam2_idx = camera_letters.index(cam2)
            
            # 객체 매칭
            matches = match_objects_simple(
                camera_detections[cam1], 
                camera_detections[cam2]
            )
            
            for match in matches:
                # 삼각측량 수행
                point_3d = triangulate_point(
                    match['det1']['center'],
                    match['det2']['center'],
                    projection_matrices[cam1_idx],
                    projection_matrices[cam2_idx]
                )
                
                if point_3d is not None:
                    triangulated_points.append({
                        'frame': frame_id,
                        'class': match['class'],
                        'x': point_3d[0],
                        'y': point_3d[1],
                        'z': point_3d[2],
                        'confidence': (match['det1']['confidence'] + match['det2']['confidence']) / 2,
                        'cameras': f'Camera_{cam1}-Camera_{cam2}'
                    })
    
    # 근접한 무리 병합
    if triangulated_points:
        triangulated_points = merge_nearby_flocks_3d(triangulated_points, distance_threshold)
    
    return triangulated_points

def process_frame_multicam(img_paths: List[Path], 
                          aviation_detector: AviationDetector, 
                          projection_matrices: List[np.ndarray],
                          camera_positions: List[np.ndarray] = None) -> List[Dict]:
    """
    여러 카메라의 프레임을 처리하여 3D 위치를 추정 (배치 처리용)
    2개 이상의 카메라에서 작동
    
    Args:
        img_paths: 카메라 이미지 경로 리스트 (2개 이상)
        aviation_detector: 항공 감지기 (통합 모듈)
        projection_matrices: 카메라 투영 행렬 리스트
    
    Returns:
        삼각측량된 3D 위치 리스트
    """
    num_cameras = len(img_paths)
    if num_cameras < 2:
        print("❌ 최소 2개 이상의 카메라가 필요합니다.")
        return []
    
    # 1. 각 카메라에서 객체 감지
    detections = []
    valid_cameras = []  # 감지가 성공한 카메라 인덱스 저장
    
    for i, img_path in enumerate(img_paths):
        try:
            # 🎯 AviationDetector로 객체 감지
            detected_objects = aviation_detector.detect_single_image(img_path, return_raw=True)
            if detected_objects['detections']:  # 객체가 감지된 경우
                detections.append(detected_objects['raw_results'][0])  # YOLO 원시 결과 사용
                valid_cameras.append(i)
            else:
                print(f"⚠️ Camera_{chr(65+i)}에서 객체가 감지되지 않음")
                detections.append(None)
        except Exception as e:
            print(f"❌ Camera_{chr(65+i)} 처리 중 오류: {e}")
            detections.append(None)
    
    if len(valid_cameras) < 2:
        print("⚠️ 최소 2개 이상의 카메라에서 객체가 감지되어야 합니다.")
        return []
    
    # 2. 감지된 카메라들 간의 조합으로 삼각측량 수행
    triangulated_points = []
    for i in range(len(valid_cameras)):
        for j in range(i+1, len(valid_cameras)):
            cam1_idx = valid_cameras[i]
            cam2_idx = valid_cameras[j]
            
            matches = match_objects_yolo(detections[cam1_idx], detections[cam2_idx])
            if not matches:
                continue
                
            for match in matches:
                # 올바른 삼각측량 함수 사용
                point_3d_unity = triangulate_point(
                    match['pt1'].flatten().tolist(),
                    match['pt2'].flatten().tolist(),
                    projection_matrices[cam1_idx],
                    projection_matrices[cam2_idx]
                )
                
                if point_3d_unity is None:
                    continue
                
                # 이상값 필터링 (비정상적으로 큰 좌표값 제거)
                max_coord = 10000  # 최대 허용 좌표값
                if (abs(point_3d_unity[0]) > max_coord or 
                    abs(point_3d_unity[1]) > max_coord or 
                    abs(point_3d_unity[2]) > max_coord):
                    print(f"⚠️ 이상값 제거: {match['class']} at ({point_3d_unity[0]:.1f}, {point_3d_unity[1]:.1f}, {point_3d_unity[2]:.1f})")
                    continue
                
                triangulated_points.append({
                    'frame': int(img_paths[0].stem.split('_')[1]),
                    'class': match['class'],
                    'x': point_3d_unity[0],
                    'y': point_3d_unity[1],
                    'z': point_3d_unity[2],
                    'confidence': (match['conf1'].item() + match['conf2'].item()) / 2,
                    'cameras': f'Camera_{chr(65+cam1_idx)}-Camera_{chr(65+cam2_idx)}',
                    'num_detected_cameras': len(valid_cameras),
                    'total_cameras': num_cameras
                })
    
    # 3. 중복 제거 및 평균화
    merged_points = []
    frame_class_groups = {}
    
    for point in triangulated_points:
        key = (point['frame'], point['class'])
        if key not in frame_class_groups:
            frame_class_groups[key] = []
        frame_class_groups[key].append(point)
    
    for points in frame_class_groups.values():
        if len(points) > 0:
            # 위치 평균화
            avg_x = np.mean([p['x'] for p in points])
            avg_y = np.mean([p['y'] for p in points])
            avg_z = np.mean([p['z'] for p in points])
            avg_conf = np.mean([p['confidence'] for p in points])
            
            # 신뢰도 계산 (감지된 카메라 수에 따라 가중치 부여)
            max_detected_cameras = max(p['num_detected_cameras'] for p in points)
            confidence_weight = max_detected_cameras / num_cameras
            
            merged_points.append({
                'frame': points[0]['frame'],
                'class': points[0]['class'],
                'x': avg_x,
                'y': avg_y,
                'z': avg_z,
                'confidence': avg_conf * confidence_weight,
                'num_detected_cameras': max_detected_cameras,
                'total_cameras': num_cameras,
                'num_camera_pairs': len(points)
            })
    
    return merged_points

# =========================
# 💾 결과 저장 및 유틸리티
# =========================

def save_results(results: List[Dict], output_dir: Path):
    """결과를 CSV와 JSON으로 저장"""
    if not results:
        print("⚠️ 저장할 결과가 없습니다.")
        return

    # CSV 저장을 위해 데이터프레임 생성
    df = pd.DataFrame(results)
    
    # CSV 저장
    csv_path = output_dir / 'triangulation_results.csv'
    df.to_csv(csv_path, index=False)
    print(f"✅ CSV 결과 저장: {csv_path}")
    
    # JSON 저장을 위해 NumPy/Tensor 타입을 Python 기본 타입으로 변환
    json_serializable_results = []
    for res in results:
        serializable_res = {}
        for k, v in res.items():
            if isinstance(v, (np.ndarray, np.generic)):
                serializable_res[k] = v.tolist()
            elif hasattr(v, 'item'): # PyTorch Tensor
                serializable_res[k] = v.item()
            else:
                serializable_res[k] = v
        json_serializable_results.append(serializable_res)

    # JSON 저장 (프레임별로 구조화)
    json_results = {}
    for result in json_serializable_results:
        frame = result['frame']
        if frame not in json_results:
            json_results[frame] = []
        json_results[frame].append({
            'class': result['class'],
            'position': [result['x'], result['y'], result['z']],
            'confidence': result['confidence']
        })
    
    json_path = output_dir / 'triangulation_results.json'
    with open(json_path, 'w') as f:
        json.dump(json_results, f, indent=2)
    print(f"✅ JSON 결과 저장: {json_path}")

def find_latest_folder(base_path: Path, pattern: str) -> Optional[Path]:
    """지정된 패턴과 일치하는 가장 최신 폴더를 찾습니다."""
    folders = list(Path(base_path).glob(pattern))
    if not folders:
        return None
    return max(folders, key=lambda p: p.stat().st_mtime)

# =========================
# 📡 메인 실행 (배치 처리)
# =========================

def main():
    """메인 실행 함수 (독립 실행용)"""
    print("🚀 3D Triangulation 시작...")
    
    # 경로 설정
    script_path = Path(__file__).resolve()
    project_root = script_path.parent.parent  # scripts/ -> BirdRiskSim_v2/

    # 가장 최신 데이터 폴더 찾기
    latest_data_folder = find_latest_folder(project_root / "data/sync_capture", "Recording_*")
    if not latest_data_folder:
        print("❌ 'data/sync_capture'에서 녹화 폴더를 찾을 수 없습니다.")
        return
    data_folder = latest_data_folder

    # 사용 가능한 카메라 자동 감지
    available_cameras = []
    camera_params = []
    projection_matrices = []
    camera_positions = []  # 🎯 카메라 Unity 월드 위치 저장
    stereo_calibrations = {}  # 🎯 스테레오 캘리브레이션 저장
    
    # 가능한 모든 카메라 문자 확인 (Camera_* 및 Fixed_Camera_* 패턴 지원)
    camera_patterns = ["Camera_{}", "Fixed_Camera_{}", "Fixed_Camera_{}_2"]
    
    for letter in ['A', 'B', 'C', 'D', 'G', 'H']:
        camera_found = False
        
        for pattern in camera_patterns:
            params_path = data_folder / f"{pattern.format(letter)}_parameters.json"
            if params_path.exists():
                try:
                    params = load_camera_parameters(params_path)
                    P = get_projection_matrix(params)
                    
                    # 🎯 카메라 Unity 월드 위치 추출
                    camera_pos = np.array([
                        params['position_UnityWorld']['x'],
                        params['position_UnityWorld']['y'],
                        params['position_UnityWorld']['z']
                    ])
                    
                    available_cameras.append(letter)
                    camera_params.append(params)
                    projection_matrices.append(P)
                    camera_positions.append(camera_pos)
                    print(f"  ✅ {pattern.format(letter)} 파라미터 로드 완료 - 위치: ({camera_pos[0]:.1f}, {camera_pos[1]:.1f}, {camera_pos[2]:.1f})")
                    camera_found = True
                    break
                except Exception as e:
                    print(f"  ⚠️ {pattern.format(letter)} 파라미터 로드 실패: {e}")
        
        if not camera_found:
            print(f"  ⚠️ Camera_{letter} 파라미터 파일 없음")
    
    # 🎯 스테레오 캘리브레이션 계산
    if len(available_cameras) >= 2:
        print("\n🔧 스테레오 캘리브레이션 계산 중...")
        for i in range(len(available_cameras)):
            for j in range(i + 1, len(available_cameras)):
                cam1_letter = available_cameras[i]
                cam2_letter = available_cameras[j]
                
                stereo_calib = calculate_stereo_calibration(camera_params[i], camera_params[j])
                stereo_calibrations[f"{cam1_letter}-{cam2_letter}"] = stereo_calib
                
                baseline = stereo_calib['baseline']
                print(f"  📏 Camera_{cam1_letter}-Camera_{cam2_letter}: 베이스라인 {baseline:.1f}m")
    else:
        print("⚠️ 스테레오 캘리브레이션을 위한 충분한 카메라가 없습니다.")
    
    if len(available_cameras) < 2:
        print(f"❌ 최소 2개 이상의 카메라가 필요합니다. 현재 {len(available_cameras)}개 발견")
        return
    
    print(f"📷 사용 가능한 카메라: {', '.join([f'Camera_{c}' for c in available_cameras])} ({len(available_cameras)}개)")
    
    # 🎯 항공 감지 시스템 초기화 (통합 모듈 사용)
    print("🤖 항공 감지 시스템 초기화 중...")
    aviation_detector = AviationDetector()
    
    if aviation_detector.model is None:
        print("❌ 항공 감지 시스템 초기화 실패")
        return
    
    print("✅ 항공 감지 시스템 준비 완료")

    # 모든 프레임 처리
    all_results = []
    
    # 첫 번째 카메라의 실제 폴더명 찾기
    first_camera_letter = available_cameras[0]
    camera_folder_name = None
    
    for pattern in camera_patterns:
        folder_name = pattern.format(first_camera_letter)
        if (data_folder / folder_name).exists():
            camera_folder_name = folder_name
            break
    
    if not camera_folder_name:
        print(f"❌ 첫 번째 카메라 폴더를 찾을 수 없습니다: Camera_{first_camera_letter}")
        return
    
    frame_files = sorted(glob.glob(str(data_folder / f"{camera_folder_name}/*.jpg")))
    total_frames = len(frame_files)
    
    print(f"\n📊 총 {total_frames}개 프레임 처리 시작...")
    print(f"  - 사용 카메라: {', '.join([f'Camera_{c}' for c in available_cameras])}")
    
    for i, frame_path in enumerate(frame_files):
        if (i + 1) % 10 == 0:
            print(f"  처리 중: {i+1}/{total_frames}")
        
        frame_name = Path(frame_path).name
        
        # 각 카메라의 실제 폴더명으로 이미지 경로 구성
        img_paths = []
        for letter in available_cameras:
            for pattern in camera_patterns:
                folder_name = pattern.format(letter)
                img_path = data_folder / folder_name / frame_name
                if img_path.exists():
                    img_paths.append(img_path)
                    break
            else:
                # 해당 카메라의 이미지를 찾을 수 없음
                img_paths = []
                break
        
        # 모든 이미지가 존재하는지 확인
        if len(img_paths) != len(available_cameras):
            print(f"⚠️  일부 카메라의 프레임을 찾을 수 없음: {frame_name}")
            continue
        
        frame_results = process_frame_multicam(img_paths, aviation_detector, projection_matrices, camera_positions)
        all_results.extend(frame_results)
    

        
    # 결과 저장
    print("\n💾 결과 저장 중...")
    output_dir = project_root / "data" / "triangulation_results" / f"results_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    output_dir.mkdir(parents=True, exist_ok=True)
    save_results(all_results, output_dir)
    
    print("\n🎉 처리 완료!")
    print(f"📊 총 {len(all_results)}개의 3D 위치 추정 완료")
    print(f"📁 결과 저장 위치: {output_dir}")







if __name__ == "__main__":
    main() 