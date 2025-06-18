import os
import cv2
import numpy as np
from pathlib import Path
import subprocess
import shutil

def convert_images_to_video(image_dir, output_dir, fps=30):
    """이미지 시퀀스를 비디오로 변환"""
    # 이미지 파일 목록 가져오기
    image_files = sorted([f for f in os.listdir(image_dir) if f.endswith('.jpg')])
    if not image_files:
        print(f"경고: {image_dir}에 이미지 파일이 없습니다.")
        return

    # 첫 번째 이미지로부터 비디오 속성 가져오기
    first_image = cv2.imread(os.path.join(image_dir, image_files[0]))
    height, width = first_image.shape[:2]

    # 출력 디렉토리 생성
    os.makedirs(output_dir, exist_ok=True)

    # 비디오 작성자 초기화
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    output_path = os.path.join(output_dir, f"{os.path.basename(image_dir)}.mp4")
    out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

    # 이미지 시퀀스 처리
    for image_file in image_files:
        image_path = os.path.join(image_dir, image_file)
        frame = cv2.imread(image_path)
        if frame is not None:
            out.write(frame)

    out.release()
    print(f"비디오 생성 완료: {output_path}")

def process_captures():
    """sync_capture 폴더의 최신 카메라 데이터 처리"""
    # 프로젝트 루트 디렉토리 찾기
    project_root = Path(__file__).parent.parent  # scripts/ -> BirdRiskSim_v2/
    sync_capture_dir = project_root / "data" / "sync_capture"
    processed_dir = project_root / "data" / "sync_video"

    # sync_capture 폴더가 없으면 종료
    if not sync_capture_dir.exists():
        print(f"오류: {sync_capture_dir} 폴더가 없습니다.")
        return

    # 최신 폴더 찾기
    latest_folder = max(sync_capture_dir.glob("*"), key=lambda x: x.stat().st_mtime)
    print(f"\n최신 캡처 폴더: {latest_folder.name}")

    # 각 카메라 폴더 처리 (Camera_* 또는 Fixed_Camera_* 패턴 모두 지원)
    camera_patterns = ["Camera_*", "Fixed_Camera_*"]
    camera_dirs = []
    
    for pattern in camera_patterns:
        camera_dirs.extend(latest_folder.glob(pattern))
    
    if not camera_dirs:
        print("❌ 카메라 폴더를 찾을 수 없습니다.")
        return
    
    for camera_dir in camera_dirs:
        if camera_dir.is_dir():
            print(f"\n카메라 {camera_dir.name} 처리 중...")
            
            # 이미지를 비디오로 변환
            convert_images_to_video(str(camera_dir), str(processed_dir))
            print(f"비디오 변환 완료: {camera_dir.name}")

if __name__ == "__main__":
    process_captures() 