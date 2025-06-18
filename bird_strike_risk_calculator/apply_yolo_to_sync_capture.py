import os
import cv2
import torch
from pathlib import Path
import time
import argparse
import json
from datetime import datetime
import numpy as np
from tqdm import tqdm

# 🎯 항공 감지 통합 모듈 import
from aviation_detector import AviationDetector

def get_latest_recording_from_sync_capture(sync_capture_dir):
    """sync_capture 디렉토리에서 최신 녹화 폴더 찾기"""
    # Recording_으로 시작하는 폴더들 찾기
    recording_dirs = list(sync_capture_dir.glob("Recording_*"))
    
    if not recording_dirs:
        print("sync_capture 디렉토리에서 Recording 폴더를 찾을 수 없습니다.")
        return None
    
    # 폴더명의 타임스탬프 기준으로 정렬하여 최신 폴더 선택
    recording_dirs.sort(key=lambda d: d.name, reverse=True)
    latest_recording = recording_dirs[0]
    
    print(f"최신 녹화 폴더 발견: {latest_recording.name}")
    return latest_recording

def get_camera_folders(recording_dir):
    """녹화 폴더에서 카메라 폴더들 찾기"""
    camera_folders = []
    
    # Fixed_Camera_로 시작하는 폴더들 찾기
    for camera_dir in recording_dir.glob("Fixed_Camera_*"):
        if camera_dir.is_dir():
            camera_folders.append(camera_dir)
    
    # 카메라 이름으로 정렬
    camera_folders.sort(key=lambda d: d.name)
    
    print(f"발견된 카메라 폴더들:")
    for camera_dir in camera_folders:
        frame_count = len(list(camera_dir.glob("frame_*.jpg")))
        print(f"  - {camera_dir.name}: {frame_count}개 프레임")
    
    return camera_folders

def load_frame_timestamps(recording_dir):
    """프레임 타임스탬프 파일 로드"""
    timestamp_file = recording_dir / "frame_timestamps.txt"
    
    if not timestamp_file.exists():
        print(f"경고: 타임스탬프 파일을 찾을 수 없습니다: {timestamp_file}")
        return {}
    
    timestamps = {}
    try:
        with open(timestamp_file, 'r') as f:
            for line in f:
                line = line.strip()
                # 주석 라인 건너뛰기
                if line and not line.startswith('#') and ',' in line:
                    parts = line.split(',')
                    if len(parts) >= 2:
                        frame_num = int(parts[0])
                        timestamp = float(parts[1])
                        timestamps[frame_num] = timestamp
        
        print(f"타임스탬프 로드 완료: {len(timestamps)}개 프레임")
        return timestamps
    except Exception as e:
        print(f"타임스탬프 파일 로드 오류: {e}")
        return {}

def process_camera_frames(camera_dir, aviation_detector, output_dir, timestamps=None, save_images=False):
    """카메라 폴더의 모든 프레임에 YOLO 적용"""
    camera_name = camera_dir.name
    print(f"\n📷 {camera_name} 처리 시작...")
    
    # 출력 디렉토리 생성
    camera_output_dir = output_dir / camera_name
    camera_output_dir.mkdir(parents=True, exist_ok=True)
    
    # 프레임 파일들 찾기
    frame_files = list(camera_dir.glob("frame_*.jpg"))
    frame_files.sort(key=lambda f: int(f.stem.split('_')[1]))  # 프레임 번호로 정렬
    
    if not frame_files:
        print(f"  ❌ {camera_name}에서 프레임 파일을 찾을 수 없습니다.")
        return []
    
    print(f"  📊 총 {len(frame_files)}개 프레임 처리 예정")
    
    # 검출 결과 저장용
    detection_results = []
    total_time = 0
    
    # 프레임별 처리
    for frame_file in tqdm(frame_files, desc=f"  {camera_name} 처리"):
        # 프레임 번호 추출
        frame_num = int(frame_file.stem.split('_')[1])
        
        # 이미지 로드
        frame = cv2.imread(str(frame_file))
        if frame is None:
            print(f"    ⚠️ 프레임 로드 실패: {frame_file.name}")
            continue
        
        # 🎯 AviationDetector로 객체 감지
        start_time = time.time()
        detections = aviation_detector.detect_single_image(frame)
        process_time = time.time() - start_time
        total_time += process_time
        
        # 배치 처리 형식으로 변환
        frame_detections = AviationDetector.format_detection_for_batch(
            detections, frame_num, timestamps.get(frame_num, 0.0) if timestamps else 0.0
        )
        
        detection_results.extend(frame_detections)
        
        # 결과 시각화 및 저장 (선택적) - TODO: AviationDetector에 시각화 기능 추가 예정
        # if save_images and len(frame_detections) > 0:
        #     annotated_frame = ...  # 향후 구현
    
    # 검출 결과를 JSON으로 저장
    results_file = camera_output_dir / f"{camera_name}_detections.json"
    with open(results_file, 'w') as f:
        json.dump(detection_results, f, indent=2)
    
    # 처리 결과 요약
    avg_time = total_time / len(frame_files) * 1000 if len(frame_files) > 0 else 0  # 밀리초 단위
    total_detections = len(detection_results)
    
    print(f"  ✅ {camera_name} 처리 완료:")
    print(f"    - 총 프레임: {len(frame_files)}")
    print(f"    - 총 검출: {total_detections}개")
    print(f"    - 평균 처리 시간: {avg_time:.1f}ms/프레임")
    print(f"    - 결과 저장: {results_file}")
    
    return detection_results

def create_summary_report(output_dir, all_detections, recording_name):
    """전체 처리 결과 요약 리포트 생성"""
    print(f"\n📊 전체 결과 요약 생성 중...")
    
    # 카메라별 통계
    camera_stats = {}
    class_stats = {}
    
    for camera_name, detections in all_detections.items():
        camera_stats[camera_name] = {
            'total_detections': len(detections),
            'frames_with_detections': len(set(d['frame_number'] for d in detections)),
            'classes': {}
        }
        
        for detection in detections:
            class_name = detection['class_name']
            if class_name not in camera_stats[camera_name]['classes']:
                camera_stats[camera_name]['classes'][class_name] = 0
            camera_stats[camera_name]['classes'][class_name] += 1
            
            if class_name not in class_stats:
                class_stats[class_name] = 0
            class_stats[class_name] += 1
    
    # 요약 리포트
    summary = {
        'recording_name': recording_name,
        'processing_timestamp': datetime.now().isoformat(),
        'total_cameras': len(all_detections),
        'total_detections': sum(len(detections) for detections in all_detections.values()),
        'class_statistics': class_stats,
        'camera_statistics': camera_stats
    }
    
    # JSON으로 저장
    summary_file = output_dir / "detection_summary.json"
    with open(summary_file, 'w') as f:
        json.dump(summary, f, indent=2)
    
    # 콘솔 출력
    print(f"📋 전체 처리 결과:")
    print(f"  - 녹화 세션: {recording_name}")
    print(f"  - 처리된 카메라: {len(all_detections)}개")
    print(f"  - 총 검출 수: {summary['total_detections']}개")
    print(f"  - 검출된 클래스:")
    for class_name, count in class_stats.items():
        print(f"    * {class_name}: {count}개")
    print(f"  - 요약 저장: {summary_file}")

def main():
    parser = argparse.ArgumentParser(description='sync_capture 데이터에 YOLO 모델 적용')
    parser.add_argument('--recording', type=str, help='처리할 특정 녹화 폴더명 (예: Recording_20250613_182928)')
    parser.add_argument('--camera', type=str, help='처리할 특정 카메라 (예: Fixed_Camera_A_2)')
    parser.add_argument('--save-images', action='store_true', help='검출 결과 이미지 저장 여부')
    args = parser.parse_args()
    
    # 프로젝트 루트 디렉토리 찾기
    project_root = Path(__file__).parent.parent  # scripts/ -> BirdRiskSim_v2/
    
    # 🎯 항공 감지 시스템 초기화 (통합 모듈 사용)
    print("🤖 항공 감지 시스템 초기화 중...")
    aviation_detector = AviationDetector()
    
    if aviation_detector.model is None:
        print("❌ 항공 감지 시스템 초기화 실패")
        return
    
    print("✅ 항공 감지 시스템 준비 완료")
    
    # sync_capture 디렉토리
    sync_capture_dir = project_root / "data" / "sync_capture"
    if not sync_capture_dir.exists():
        print(f"❌ sync_capture 디렉토리를 찾을 수 없습니다: {sync_capture_dir}")
        return
    
    # 처리할 녹화 폴더 결정
    if args.recording:
        recording_dir = sync_capture_dir / args.recording
        if not recording_dir.exists():
            print(f"❌ 지정된 녹화 폴더를 찾을 수 없습니다: {recording_dir}")
            return
    else:
        recording_dir = get_latest_recording_from_sync_capture(sync_capture_dir)
        if recording_dir is None:
            return
    
    print(f"🎬 처리할 녹화: {recording_dir.name}")
    
    # 출력 디렉토리 (타임스탬프 폴더 생성)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_dir = project_root / "data" / "sync_capture_yolo" / f"results_{timestamp}_{recording_dir.name}"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 타임스탬프 로드
    timestamps = load_frame_timestamps(recording_dir)
    
    # 카메라 폴더들 찾기
    camera_folders = get_camera_folders(recording_dir)
    if not camera_folders:
        print("❌ 카메라 폴더를 찾을 수 없습니다.")
        return
    
    # 특정 카메라만 처리하는 경우
    if args.camera:
        camera_folders = [folder for folder in camera_folders if folder.name == args.camera]
        if not camera_folders:
            print(f"❌ 지정된 카메라를 찾을 수 없습니다: {args.camera}")
            return
    
    # 각 카메라별 처리
    all_detections = {}
    
    for camera_dir in camera_folders:
        detections = process_camera_frames(camera_dir, aviation_detector, output_dir, timestamps, args.save_images)
        all_detections[camera_dir.name] = detections
    
    # 전체 요약 리포트 생성
    create_summary_report(output_dir, all_detections, recording_dir.name)
    
    print(f"\n🎉 모든 처리 완료!")
    print(f"📁 결과 저장 위치: {output_dir}")

if __name__ == "__main__":
    main() 