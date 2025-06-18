#!/usr/bin/env python3
"""
BirdRiskSim Aviation Detection Manager
새떼-항공기 감지를 위한 통합 YOLO 관리 모듈

4개 파일에서 반복되던 YOLO 관련 로직을 통합:
- real_time_pipeline.py
- apply_yolo_to_sync_capture.py  
- apply_yolo_to_sync_video.py
- triangulate.py
"""

import cv2
import numpy as np
import time
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Union
from ultralytics import YOLO
import torch
import warnings

warnings.filterwarnings('ignore')

class AviationDetector:
    """항공 객체 감지 통합 관리자"""
    
    def __init__(self, model_path: Optional[str] = None, confidence_threshold: float = 0.25):
        """
        항공 감지기 초기화
        
        Args:
            model_path: YOLO 모델 경로 (None이면 자동 탐지)
            confidence_threshold: 감지 신뢰도 임계값
        """
        self.model_path = model_path
        self.confidence_threshold = confidence_threshold
        self.model = None
        
        # GPU 사용 가능 여부 확인
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        if self.device == 'cpu':
            print("⚠️ GPU를 사용할 수 없습니다. CPU로 실행됩니다.")
        else:
            print(f"✅ GPU 사용 가능: {torch.cuda.get_device_name()}")
            print(f"  GPU 메모리: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f}GB")
        
        # 클래스 정보 (BirdRiskSim 표준)
        self.class_names = {0: 'Flock', 1: 'Airplane'}
        self.class_colors = {
            0: (0, 255, 0),    # 초록색 - Flock
            1: (0, 0, 255),    # 빨간색 - Airplane
        }
        
        # 프로젝트 루트 경로
        self.project_root = Path(__file__).parent.parent
        
        # 모델 로드
        self._load_model()
        
    def _find_latest_model(self) -> Optional[Path]:
        """최신 YOLO 모델 자동 탐지 (4개 파일에서 중복되던 로직)"""
        try:
            train_runs_dir = self.project_root / "training/yolo/runs/train"
            
            if not train_runs_dir.exists():
                print(f"❌ 학습 결과 디렉토리를 찾을 수 없습니다: {train_runs_dir}")
                return None
            
            # bird_detection_으로 시작하는 폴더들 찾기
            bird_detection_dirs = list(train_runs_dir.glob("bird_detection_*"))
            if not bird_detection_dirs:
                print("❌ bird_detection 학습 결과를 찾을 수 없습니다.")
                return None
            
            # 가장 최신 폴더 선택 (수정 시간 기준)
            latest_dir = max(bird_detection_dirs, key=lambda d: d.stat().st_mtime)
            model_path = latest_dir / "weights/best.pt"
            
            if not model_path.exists():
                print(f"❌ 최신 모델 파일을 찾을 수 없습니다: {model_path}")
                return None
            
            print(f"🔍 최신 YOLO 모델 발견: {latest_dir.name}")
            return model_path
            
        except Exception as e:
            print(f"❌ 모델 탐지 오류: {e}")
            return None
    
    def _load_model(self) -> bool:
        """YOLO 모델 로드"""
        try:
            # 모델 경로 결정
            if self.model_path is None:
                model_path = self._find_latest_model()
                if model_path is None:
                    return False
            else:
                model_path = Path(self.model_path)
                if not model_path.exists():
                    print(f"❌ 지정된 모델 파일을 찾을 수 없습니다: {model_path}")
                    return False
            
            # 모델 로드 (device 명시적 지정)
            self.model = YOLO(model_path)
            self.model.to(self.device)  # GPU/CPU 설정
            self.model_path = model_path
            print(f"✅ YOLO 모델 로드 완료: {model_path.name} ({self.device} 사용)")
            return True
            
        except Exception as e:
            print(f"❌ 모델 로드 실패: {e}")
            return False
    
    def detect_single_image(self, image: Union[str, Path, np.ndarray], 
                           camera_id: Optional[str] = None,
                           return_raw: bool = False) -> List[Dict]:
        """
        단일 이미지에서 객체 감지 (3개 파일에서 중복되던 로직 통합)
        
        Args:
            image: 이미지 경로 또는 numpy 배열
            camera_id: 카메라 식별자 (선택사항)
            return_raw: 원시 YOLO 결과 반환 여부
            
        Returns:
            감지 결과 리스트
        """
        if self.model is None:
            print("❌ 모델이 로드되지 않았습니다.")
            return []
        
        try:
            # 이미지 로드
            if isinstance(image, (str, Path)):
                img = cv2.imread(str(image))
                if img is None:
                    print(f"❌ 이미지 로드 실패: {image}")
                    return []
            else:
                img = image
            
            # 🚀 GPU 메모리 최적화: 캐시 정리
            if self.device == 'cuda':
                torch.cuda.empty_cache()
            
            # YOLO 추론 (원본 이미지 크기 유지)
            start_time = time.time()
            results = self.model(img, conf=self.confidence_threshold, verbose=False)
            inference_time = time.time() - start_time
            
            result = results[0]
            detections = []
            
            if result.boxes is not None:
                boxes = result.boxes.xyxy.cpu().numpy()
                confidences = result.boxes.conf.cpu().numpy()
                classes = result.boxes.cls.cpu().numpy().astype(int)
                
                for box, conf, cls in zip(boxes, confidences, classes):
                    x1, y1, x2, y2 = box
                    
                    center_x = (x1 + x2) / 2
                    center_y = (y1 + y2) / 2
                    width = x2 - x1
                    height = y2 - y1
                    
                    detection = {
                        'class_id': int(cls),
                        'class_name': self.class_names.get(cls, 'Unknown'),
                        'confidence': float(conf),
                        'bbox': [float(x1), float(y1), float(x2), float(y2)],
                        'center': [float(center_x), float(center_y)],
                        'width': float(width),
                        'height': float(height),
                        'inference_time': inference_time
                    }
                    
                    # 카메라 ID 추가 (실시간 파이프라인용)
                    if camera_id:
                        detection['camera'] = camera_id
                    
                    # 실시간 파이프라인 호환성을 위한 별칭
                    detection['class'] = detection['class_name']
                    
                    detections.append(detection)
            
            # 🚀 GPU 메모리 최적화: 결과 처리 후 캐시 정리
            if self.device == 'cuda':
                torch.cuda.empty_cache()
            
            # 원시 결과 반환 옵션
            if return_raw:
                return {'detections': detections, 'raw_results': results}
            
            return detections
            
        except Exception as e:
            print(f"❌ 이미지 감지 오류: {e}")
            return []
    
    def detect_batch_images(self, image_paths: List[Union[str, Path]], 
                           progress_callback: Optional[callable] = None) -> Dict[str, List[Dict]]:
        """
        배치 이미지 감지 (apply_yolo_to_sync_capture.py 로직 기반)
        
        Args:
            image_paths: 이미지 경로 리스트
            progress_callback: 진행 상황 콜백 함수
            
        Returns:
            파일명별 감지 결과 딕셔너리
        """
        results = {}
        total_images = len(image_paths)
        
        print(f"📊 배치 감지 시작: {total_images}개 이미지")
        
        for i, image_path in enumerate(image_paths):
            image_path = Path(image_path)
            
            # 감지 수행
            detections = self.detect_single_image(image_path)
            results[image_path.name] = detections
            
            # 진행 상황 콜백
            if progress_callback:
                progress_callback(i + 1, total_images, image_path.name)
            elif (i + 1) % 10 == 0:
                print(f"  진행: {i + 1}/{total_images} ({(i + 1)/total_images*100:.1f}%)")
        
        print(f"✅ 배치 감지 완료: {len(results)}개 이미지 처리")
        return results
    
    def detect_video_frame(self, frame: np.ndarray, frame_number: int = 0, 
                          timestamp: float = 0.0) -> List[Dict]:
        """
        비디오 프레임 감지 (apply_yolo_to_sync_video.py 로직 기반)
        
        Args:
            frame: 비디오 프레임 (numpy 배열)
            frame_number: 프레임 번호
            timestamp: 타임스탬프
            
        Returns:
            감지 결과 리스트 (프레임 정보 포함)
        """
        detections = self.detect_single_image(frame)
        
        # 프레임 정보 추가
        for detection in detections:
            detection['frame_number'] = frame_number
            detection['timestamp'] = timestamp
        
        return detections
    
    def get_model_info(self) -> Dict:
        """모델 정보 반환"""
        if self.model is None:
            return {'loaded': False}
        
        return {
            'loaded': True,
            'model_path': str(self.model_path),
            'confidence_threshold': self.confidence_threshold,
            'class_names': self.class_names,
            'model_type': 'YOLOv8'
        }
    
    def set_confidence_threshold(self, threshold: float):
        """신뢰도 임계값 변경"""
        if 0.0 <= threshold <= 1.0:
            self.confidence_threshold = threshold
            print(f"✅ 신뢰도 임계값 변경: {threshold}")
        else:
            print(f"❌ 잘못된 임계값: {threshold} (0.0-1.0 범위)")
    
    def reload_model(self, model_path: Optional[str] = None):
        """모델 재로드"""
        self.model_path = model_path
        self.model = None
        return self._load_model()
    
    @staticmethod
    def format_detection_for_realtime(detections: List[Dict], camera_letter: str) -> List[Dict]:
        """실시간 파이프라인 형식으로 변환"""
        formatted = []
        for det in detections:
            formatted.append({
                'camera': camera_letter,
                'class': det['class_name'],
                'bbox': det['bbox'],
                'center': det['center'],
                'confidence': det['confidence']
            })
        return formatted
    
    @staticmethod
    def format_detection_for_batch(detections: List[Dict], frame_number: int, 
                                  timestamp: float = 0.0) -> List[Dict]:
        """배치 처리 형식으로 변환"""
        formatted = []
        for det in detections:
            formatted.append({
                'frame_number': frame_number,
                'timestamp': timestamp,
                'class_id': det['class_id'],
                'class_name': det['class_name'],
                'confidence': det['confidence'],
                'bbox': det['bbox'],
                'center': det['center'],
                'width': det['width'],
                'height': det['height']
            })
        return formatted

    def detect_batch_images_realtime(self, images: Dict[str, Union[str, Path, np.ndarray]]) -> List[Dict]:
        """
        실시간 파이프라인용 배치 이미지 감지 (성능 최적화)
        
        Args:
            images: {camera_id: image_path_or_array} 딕셔너리
            
        Returns:
            모든 카메라의 감지 결과 리스트
        """
        if self.model is None:
            print("❌ 모델이 로드되지 않았습니다.")
            return []
        
        try:
            # 🚀 GPU 메모리 최적화: 배치 처리 전 캐시 정리
            if self.device == 'cuda':
                torch.cuda.empty_cache()
            
            # 이미지 로드 및 전처리
            batch_images = []
            camera_ids = []
            
            for camera_id, image in images.items():
                if isinstance(image, (str, Path)):
                    img = cv2.imread(str(image))
                    if img is None:
                        print(f"❌ 이미지 로드 실패: {image}")
                        continue
                else:
                    img = image
                
                batch_images.append(img)
                camera_ids.append(camera_id)
            
            if not batch_images:
                return []
            
            # 🚀 배치 추론 (여러 이미지를 한 번에 처리)
            start_time = time.time()
            results = self.model(batch_images, conf=self.confidence_threshold, verbose=False)
            inference_time = time.time() - start_time
            
            # 결과 처리
            all_detections = []
            
            for i, (result, camera_id) in enumerate(zip(results, camera_ids)):
                if result.boxes is not None:
                    boxes = result.boxes.xyxy.cpu().numpy()
                    confidences = result.boxes.conf.cpu().numpy()
                    classes = result.boxes.cls.cpu().numpy().astype(int)
                    
                    for box, conf, cls in zip(boxes, confidences, classes):
                        x1, y1, x2, y2 = box
                        center_x = (x1 + x2) / 2
                        center_y = (y1 + y2) / 2
                        width = x2 - x1
                        height = y2 - y1
                        
                        detection = {
                            'class_id': int(cls),
                            'class_name': self.class_names.get(cls, 'Unknown'),
                            'confidence': float(conf),
                            'bbox': [float(x1), float(y1), float(x2), float(y2)],
                            'center': [float(center_x), float(center_y)],
                            'width': float(width),
                            'height': float(height),
                            'inference_time': inference_time / len(batch_images),  # 배치당 평균 시간
                            'camera': camera_id,
                            'class': self.class_names.get(cls, 'Unknown')  # 실시간 파이프라인 호환성
                        }
                        
                        all_detections.append(detection)
            
            # 🚀 GPU 메모리 최적화: 배치 처리 후 캐시 정리
            if self.device == 'cuda':
                torch.cuda.empty_cache()
            
            print(f"🚀 배치 처리 완료: {len(batch_images)}개 이미지, {len(all_detections)}개 객체 감지 ({inference_time*1000:.1f}ms)")
            
            return all_detections
            
        except Exception as e:
            print(f"❌ 배치 이미지 감지 오류: {e}")
            return []

# 편의 함수들 (기존 코드 호환성)
def load_latest_yolo_model(confidence_threshold: float = 0.25) -> Optional[AviationDetector]:
    """최신 YOLO 모델을 자동으로 로드하는 편의 함수"""
    detector = AviationDetector(confidence_threshold=confidence_threshold)
    if detector.model is None:
        return None
    return detector

def detect_objects_in_image(image_path: Union[str, Path], 
                          confidence_threshold: float = 0.25) -> List[Dict]:
    """단일 이미지 감지 편의 함수"""
    detector = load_latest_yolo_model(confidence_threshold)
    if detector is None:
        return []
    return detector.detect_single_image(image_path)

# 사용 예시
if __name__ == "__main__":
    print("🚀 AviationDetector 테스트")
    
    # 감지기 초기화
    detector = AviationDetector()
    
    if detector.model is not None:
        print("✅ 모델 로드 성공")
        print(f"📊 모델 정보: {detector.get_model_info()}")
    else:
        print("❌ 모델 로드 실패") 