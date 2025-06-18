#!/usr/bin/env python3
"""
YOLO 라벨링 시각화 스크립트
BirdRiskSim 프로젝트의 yolo_capture 데이터의 라벨링을 시각화합니다.
"""

import os
import cv2
import numpy as np
import argparse
import glob
from pathlib import Path

# 프로젝트 루트 디렉토리 찾기
project_root = Path(__file__).parent.parent  # scripts/ -> BirdRiskSim_v2/

class YOLOLabelVisualizer:
    def __init__(self):
        # 클래스 정보 (YoloCaptureManager.cs에서 확인)
        self.class_names = {
            0: "Flock",    # 새 떼
            1: "Airplane"  # 비행기
        }
        
        # 클래스별 색상 (BGR 형식)
        self.class_colors = {
            0: (0, 255, 0),    # 초록색 - Flock
            1: (0, 0, 255),    # 빨간색 - Airplane
        }
    
    def parse_yolo_label(self, label_path):
        """
        YOLO 라벨 파일을 파싱합니다.
        Returns: list of (class_id, center_x, center_y, width, height)
        """
        detections = []
        
        if not os.path.exists(label_path):
            print(f"⚠️  라벨 파일이 없습니다: {label_path}")
            return detections
            
        try:
            with open(label_path, 'r') as f:
                lines = f.readlines()
                
            print(f"🔍 라벨 파일 내용 ({label_path}):")
            for i, line in enumerate(lines):
                line = line.strip()
                if not line:  # 빈 줄 건너뛰기
                    continue
                    
                print(f"   라인 {i+1}: '{line}'")
                parts = line.split()
                if len(parts) == 5:
                    class_id = int(parts[0])
                    center_x = float(parts[1])
                    center_y = float(parts[2])
                    width = float(parts[3])
                    height = float(parts[4])
                    
                    class_name = self.class_names.get(class_id, f"Class_{class_id}")
                    print(f"      → {class_name}: 중심({center_x:.6f}, {center_y:.6f}) 크기({width:.6f}x{height:.6f})")
                    
                    detections.append((class_id, center_x, center_y, width, height))
                else:
                    print(f"      ⚠️  잘못된 형식: {len(parts)}개 값 (5개 필요)")
                    
        except Exception as e:
            print(f"⚠️  라벨 파일 파싱 오류 {label_path}: {e}")
            
        return detections
    
    def draw_detection(self, image, detection, img_width, img_height):
        """
        이미지에 detection 박스를 그립니다.
        """
        class_id, center_x, center_y, width, height = detection
        
        # 정규화된 좌표를 실제 픽셀 좌표로 변환
        center_x_px = int(center_x * img_width)
        center_y_px = int(center_y * img_height)
        width_px = int(width * img_width)
        height_px = int(height * img_height)
        
        # 바운딩 박스 좌표 계산
        x1 = int(center_x_px - width_px / 2)
        y1 = int(center_y_px - height_px / 2)
        x2 = int(center_x_px + width_px / 2)
        y2 = int(center_y_px + height_px / 2)
        
        # 🔍 상세 디버깅 출력
        class_name = self.class_names.get(class_id, f"Class_{class_id}")
        print(f"🎯 {class_name} 좌표 변환:")
        print(f"   YOLO 좌표: 중심({center_x:.6f}, {center_y:.6f}) 크기({width:.6f}x{height:.6f})")
        print(f"   이미지 크기: {img_width}x{img_height}")
        print(f"   픽셀 중심: ({center_x_px}, {center_y_px})")
        print(f"   픽셀 크기: {width_px}x{height_px}")
        print(f"   바운딩 박스: ({x1}, {y1}) → ({x2}, {y2})")
        print(f"   바운딩 박스 크기 검증: {x2-x1}x{y2-y1}")
        
        # 좌표 유효성 검사
        if x1 < 0 or y1 < 0 or x2 >= img_width or y2 >= img_height:
            print(f"   ⚠️  바운딩 박스가 이미지 경계를 벗어남!")
            print(f"   이미지 범위: (0,0) → ({img_width-1},{img_height-1})")
        
        # 중심점 유효성 검사
        if center_x_px < 0 or center_x_px >= img_width or center_y_px < 0 or center_y_px >= img_height:
            print(f"   ⚠️  중심점이 이미지 경계를 벗어남!")
            print(f"   중심점: ({center_x_px}, {center_y_px})")
            print(f"   이미지 범위: (0,0) → ({img_width-1},{img_height-1})")
        
        # 색상 선택
        color = self.class_colors.get(class_id, (0, 255, 255))  # 기본: 노란색
        class_name = self.class_names.get(class_id, f"Class_{class_id}")
        
        # 바운딩 박스 그리기
        cv2.rectangle(image, (x1, y1), (x2, y2), color, 2)
        
        # 중심점 그리기
        cv2.circle(image, (center_x_px, center_y_px), 3, color, -1)
        
        # 라벨 텍스트
        label_text = f"{class_name} ({center_x:.3f}, {center_y:.3f})"
        
        # 텍스트 배경
        (text_width, text_height), _ = cv2.getTextSize(label_text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        cv2.rectangle(image, (x1, y1 - text_height - 5), (x1 + text_width, y1), color, -1)
        
        # 텍스트 그리기
        cv2.putText(image, label_text, (x1, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        
        return image
    
    def visualize_single_image(self, image_path, label_path, output_path=None, show=False):
        """
        단일 이미지와 라벨을 시각화합니다.
        """
        if not os.path.exists(image_path):
            print(f"❌ 이미지 파일이 없습니다: {image_path}")
            return None
            
        # 이미지 읽기
        image = cv2.imread(image_path)
        if image is None:
            print(f"❌ 이미지를 읽을 수 없습니다: {image_path}")
            return None
            
        img_height, img_width = image.shape[:2]
        
        # 라벨 파싱
        detections = self.parse_yolo_label(label_path)
        
        # 정보 출력
        print(f"📸 이미지: {os.path.basename(image_path)} ({img_width}x{img_height})")
        print(f"🏷️  라벨: {len(detections)}개 객체 발견")
        
        # 각 detection 그리기
        for detection in detections:
            image = self.draw_detection(image, detection, img_width, img_height)
        
        # 이미지 정보 텍스트 추가
        info_text = f"Objects: {len(detections)} | Size: {img_width}x{img_height} | File: {os.path.basename(image_path)}"
        cv2.putText(image, info_text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        cv2.putText(image, info_text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 1)
        
        # 출력 처리
        if output_path:
            cv2.imwrite(output_path, image)
            print(f"💾 저장됨: {output_path}")
            
        if show:
            cv2.imshow('YOLO Label Visualization', image)
            cv2.waitKey(0)
            cv2.destroyAllWindows()
            
        return image
    
    def visualize_camera_batch(self, camera_path, output_dir=None, max_images=10):
        """
        카메라 폴더의 여러 이미지를 배치로 시각화합니다.
        """
        camera_name = os.path.basename(camera_path)
        print(f"\n🎥 카메라 {camera_name} 처리 중...")
        
        # 이미지 파일 찾기
        image_files = sorted(glob.glob(os.path.join(camera_path, "*.png")))
        
        if not image_files:
            print(f"❌ {camera_path}에 이미지 파일이 없습니다")
            return
            
        # 최대 개수 제한
        if len(image_files) > max_images:
            image_files = image_files[:max_images]
            print(f"📊 {len(image_files)}개 이미지로 제한 (최대 {max_images}개)")
        
        # 출력 디렉토리 생성
        if output_dir:
            camera_output_dir = os.path.join(output_dir, camera_name)
            os.makedirs(camera_output_dir, exist_ok=True)
        
        stats = {"total": 0, "with_objects": 0, "empty": 0}
        
        for image_path in image_files:
            # 대응하는 라벨 파일 경로
            label_path = image_path.replace('.png', '.txt')
            
            # 출력 파일 경로
            output_path = None
            if output_dir:
                output_filename = f"labeled_{os.path.basename(image_path)}"
                output_path = os.path.join(camera_output_dir, output_filename)
            
            # 시각화
            result_image = self.visualize_single_image(image_path, label_path, output_path)
            
            # 통계 업데이트
            if result_image is not None:
                stats["total"] += 1
                detections = self.parse_yolo_label(label_path)
                if detections:
                    stats["with_objects"] += 1
                else:
                    stats["empty"] += 1
        
        # 통계 출력
        print(f"\n📈 {camera_name} 처리 완료:")
        print(f"   - 총 이미지: {stats['total']}개")
        print(f"   - 객체 포함: {stats['with_objects']}개")
        print(f"   - 빈 프레임: {stats['empty']}개")
        print(f"   - 객체 검출률: {stats['with_objects']/stats['total']*100:.1f}%")
    
    def analyze_dataset(self, yolo_capture_path):
        """
        전체 데이터셋을 분석합니다.
        """
        print("🔍 데이터셋 분석 중...")
        
        camera_dirs = [d for d in os.listdir(yolo_capture_path) 
                      if os.path.isdir(os.path.join(yolo_capture_path, d)) and 
                      (d.startswith('Fixed_Camera_') or d.startswith('Movable_Camera_'))]
        
        total_stats = {"images": 0, "labels": 0, "objects": 0, "empty_frames": 0}
        class_stats = {}
        
        for camera_dir in sorted(camera_dirs):
            camera_path = os.path.join(yolo_capture_path, camera_dir)
            
            # 이미지와 라벨 파일 개수
            images = glob.glob(os.path.join(camera_path, "*.png"))
            labels = glob.glob(os.path.join(camera_path, "*.txt"))
            
            camera_objects = 0
            camera_empty = 0
            
            # 각 라벨 파일 분석
            for label_path in labels:
                detections = self.parse_yolo_label(label_path)
                if detections:
                    camera_objects += len(detections)
                    for detection in detections:
                        class_id = detection[0]
                        class_stats[class_id] = class_stats.get(class_id, 0) + 1
                else:
                    camera_empty += 1
            
            print(f"📹 {camera_dir}: {len(images)}개 이미지, {len(labels)}개 라벨, {camera_objects}개 객체")
            
            total_stats["images"] += len(images)
            total_stats["labels"] += len(labels)
            total_stats["objects"] += camera_objects
            total_stats["empty_frames"] += camera_empty
        
        print(f"\n📊 전체 데이터셋 통계:")
        print(f"   - 총 이미지: {total_stats['images']}개")
        print(f"   - 총 라벨: {total_stats['labels']}개")
        print(f"   - 총 객체: {total_stats['objects']}개")
        print(f"   - 빈 프레임: {total_stats['empty_frames']}개")
        print(f"   - 객체 검출률: {(total_stats['labels']-total_stats['empty_frames'])/total_stats['labels']*100:.1f}%")
        
        print(f"\n🏷️  클래스별 분포:")
        for class_id, count in sorted(class_stats.items()):
            class_name = self.class_names.get(class_id, f"Class_{class_id}")
            percentage = count / total_stats['objects'] * 100
            print(f"   - {class_name}: {count}개 ({percentage:.1f}%)")

def main():
    parser = argparse.ArgumentParser(description='YOLO 라벨링 시각화 도구')
    parser.add_argument('--input', '-i', default='data/yolo_capture', help='yolo_capture 디렉토리 경로')
    parser.add_argument('--output', '-o', default='data/yolo_capture_visualization', help='시각화된 이미지 출력 디렉토리')
    parser.add_argument('--camera', '-c', help='특정 카메라만 처리 (예: Fixed_Camera_A)')
    parser.add_argument('--max-images', '-m', type=int, default=100, help='카메라당 최대 처리 이미지 수')
    parser.add_argument('--analyze-only', '-a', action='store_true', help='분석만 수행 (시각화 안함)')
    parser.add_argument('--show', '-s', action='store_true', help='시각화 결과를 화면에 표시')
    
    args = parser.parse_args()
    
    visualizer = YOLOLabelVisualizer()
    
    # 입력 경로 확인
    if not os.path.exists(args.input):
        print(f"❌ 입력 디렉토리가 없습니다: {args.input}")
        return
    
    # 데이터셋 분석
    visualizer.analyze_dataset(args.input)
    
    if args.analyze_only:
        return
    
    # 출력 디렉토리 생성
    if args.output:
        os.makedirs(args.output, exist_ok=True)
        print(f"📁 출력 디렉토리: {args.output}")
    
    # 특정 카메라 처리
    if args.camera:
        camera_path = os.path.join(args.input, args.camera)
        if os.path.exists(camera_path):
            visualizer.visualize_camera_batch(camera_path, args.output, args.max_images)
        else:
            print(f"❌ 카메라 디렉토리가 없습니다: {camera_path}")
    else:
        # 모든 카메라 처리
        camera_dirs = [d for d in os.listdir(args.input) 
                      if os.path.isdir(os.path.join(args.input, d)) and 
                      (d.startswith('Fixed_Camera_') or d.startswith('Movable_Camera_'))]
        
        for camera_dir in sorted(camera_dirs):
            camera_path = os.path.join(args.input, camera_dir)
            visualizer.visualize_camera_batch(camera_path, args.output, args.max_images)

if __name__ == "__main__":
    main() 