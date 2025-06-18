import os
import cv2
import torch
from pathlib import Path
import time
import argparse

# 🎯 항공 감지 통합 모듈 import
from aviation_detector import AviationDetector

def get_latest_files_from_yolo_capture(yolo_capture_dir):
    """yolo_capture 디렉토리에서 각 카메라별 최신 파일 찾기"""
    latest_files = []
    
    # Camera_A, Camera_B, Camera_C, Camera_D 디렉토리 확인
    for camera_dir in ['Camera_A', 'Camera_B', 'Camera_C', 'Camera_D']:
        camera_path = yolo_capture_dir / camera_dir
        if camera_path.exists():
            # 각 카메라 디렉토리에서 가장 최신 mp4 파일 찾기
            mp4_files = list(camera_path.glob("*.mp4"))
            if mp4_files:
                # 파일 수정 시간 기준으로 정렬하여 최신 파일 선택
                latest_file = max(mp4_files, key=lambda f: f.stat().st_mtime)
                latest_files.append(latest_file)
                print(f"[{camera_dir}] 최신 파일: {latest_file.name}")
            else:
                print(f"[{camera_dir}] mp4 파일을 찾을 수 없습니다.")
        else:
            print(f"[{camera_dir}] 디렉토리를 찾을 수 없습니다.")
    
    return latest_files

def get_latest_files_from_sync_video(sync_video_dir):
    """sync_video 디렉토리에서 최신 비디오 파일들 찾기"""
    latest_files = []
    
    # sync_video 디렉토리의 모든 mp4 파일 찾기
    mp4_files = list(sync_video_dir.glob("*.mp4"))
    
    if mp4_files:
        # 파일 수정 시간 기준으로 정렬하여 최신 파일들 선택
        mp4_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
        
        print(f"sync_video 디렉토리에서 {len(mp4_files)}개의 mp4 파일을 발견했습니다:")
        for i, file_path in enumerate(mp4_files):
            print(f"  {i+1}. {file_path.name} (수정시간: {time.ctime(file_path.stat().st_mtime)})")
            latest_files.append(file_path)
    else:
        print("sync_video 디렉토리에서 mp4 파일을 찾을 수 없습니다.")
    
    return latest_files

def process_video(video_path, output_dir, aviation_detector):
    """비디오 파일을 처리하고 결과를 저장"""
    # 비디오 파일 이름 추출
    video_name = Path(video_path).stem
    
    # 출력 파일 경로
    output_file = output_dir / f"{video_name}_detected.mp4"
    
    # 비디오 캡처 객체 생성
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        print(f"오류: 비디오 파일을 열 수 없습니다: {video_path}")
        return
    
    # 비디오 정보
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    
    print(f"\n비디오 정보:")
    print(f"- 파일: {video_name}")
    print(f"- 총 프레임: {total_frames}")
    print(f"- FPS: {fps}")
    print(f"- 해상도: {width}x{height}")
    
    # 결과 저장을 위한 비디오 작성자 설정
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(
        str(output_file),
        fourcc,
        fps,
        (width, height)
    )
    
    # 프레임별 처리
    frame_count = 0
    total_time = 0
    
    while True:
        ret, frame = cap.read()
        if not ret:
            break
            
        # 🎯 AviationDetector로 객체 감지
        start_time = time.time()
        detections = aviation_detector.detect_video_frame(frame, frame_count, frame_count / fps)
        process_time = time.time() - start_time
        total_time += process_time
        
        # 결과 시각화 - TODO: AviationDetector에 시각화 기능 추가 예정
        # annotated_frame = ...  # 향후 구현
        annotated_frame = frame  # 임시로 원본 프레임 사용
        
        # 결과 저장
        out.write(annotated_frame)
        
        # 진행 상황 출력
        frame_count += 1
        if frame_count % 10 == 0:
            print(f"프레임 {frame_count}/{total_frames} 처리 중...")
    
    # 자원 해제
    cap.release()
    out.release()
    
    # 처리 결과 요약
    avg_time = total_time / total_frames * 1000  # 밀리초 단위로 변환
    print(f"\n처리 완료:")
    print(f"- 총 프레임: {total_frames}")
    print(f"- 평균 처리 시간: {avg_time:.1f}ms/프레임")
    print(f"- 결과 저장: {output_file}")

def main():
    parser = argparse.ArgumentParser(description='비디오에 YOLO 모델 적용')
    parser.add_argument('--video', type=str, help='처리할 비디오 파일 경로')
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
    
    # 출력 디렉토리 (타임스탬프 폴더 생성)
    from datetime import datetime
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_dir = project_root / "data" / "sync_yolo_video" / f"results_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    if args.video:
        # 단일 비디오 처리
        video_path = Path(args.video)
        if not video_path.exists():
            print(f"오류: 비디오 파일을 찾을 수 없습니다: {video_path}")
            return
        process_video(str(video_path), output_dir, aviation_detector)
    else:
        # sync_video 디렉토리의 최신 파일들 처리
        sync_video_dir = project_root / "data" / "sync_video"
        if not sync_video_dir.exists():
            print(f"오류: sync_video 디렉토리를 찾을 수 없습니다: {sync_video_dir}")
            return
        
        print("sync_video 디렉토리에서 최신 파일들을 찾는 중...")
        latest_files = get_latest_files_from_sync_video(sync_video_dir)
        
        if not latest_files:
            print("처리할 비디오 파일을 찾을 수 없습니다.")
            return
        
        print(f"\n총 {len(latest_files)}개의 최신 파일을 처리합니다:")
        for video_path in latest_files:
            process_video(str(video_path), output_dir, aviation_detector)

if __name__ == "__main__":
    main() 