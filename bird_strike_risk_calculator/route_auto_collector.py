#!/usr/bin/env python3
"""
자동 경로 처리기 (Auto Route Processor)
Unity SyncCaptureManager에서 생성되는 Recording 폴더들을 자동으로 모니터링하고
삼각측량 → 경로 수집 → 평균 계산을 완전 자동화합니다.
"""

import sys
import time
import json
from pathlib import Path
from datetime import datetime
from typing import Set, List
import logging
import numpy as np
import argparse
import threading
import signal

# 프로젝트 루트를 sys.path에 추가
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from route_triangulation_core import (
    initialize_route_collector, 
    start_route_collection, 
    stop_route_collection,
    generate_average_route,
    get_last_saved_run_path,
    add_triangulation_data
)

class AutoRouteProcessor:
    """Unity Recording 폴더 자동 모니터링 및 처리 - 단순화 버전"""
    
    def __init__(self, route_name: str = "Path_A", update_mode: str = "batch"):
        self.route_name = route_name
        self.update_mode = update_mode  # "batch", "immediate", "cumulative"
        
        # 경로 설정 (triangulation_routes를 routes로 통합)
        self.sync_capture_dir = Path("data/sync_capture")
        self.route_dir = Path("data/routes")
        self.raw_runs_dir = Path("data/routes/raw_runs")
        self.averaged_routes_dir = Path("data/routes/averaged_routes")
        self.visualization_dir = Path("data/routes/visualizations")
        self.state_file = Path("data/routes/auto_processor_state.json")
        
        # 상태 관리
        self.processed_folders: Set[str] = set()
        self.is_running = False
        self.stop_requested = False
        
        # 로깅 설정
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s: %(message)s')
        self.logger = logging.getLogger(__name__)
        
        # 디렉토리 생성
        self.sync_capture_dir.mkdir(parents=True, exist_ok=True)
        self.route_dir.mkdir(parents=True, exist_ok=True)
        self.raw_runs_dir.mkdir(parents=True, exist_ok=True)
        self.averaged_routes_dir.mkdir(parents=True, exist_ok=True)
        self.visualization_dir.mkdir(parents=True, exist_ok=True)
        
        # 경로 수집기 초기화
        self.route_collector = initialize_route_collector()
        
        self.logger.info("🤖 자동 경로 처리기 초기화 완료")
        self.logger.info(f"   - 경로 이름: {self.route_name}")
        self.logger.info(f"   - 업데이트 모드: {self.update_mode}")
        self.logger.info(f"   - 통합 경로: {self.route_dir}")
    
    def load_state(self):
        """이전 처리 상태 로드"""
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r') as f:
                    state = json.load(f)
                self.processed_folders = set(state.get('processed_folders', []))
                self.logger.info(f"📂 이전 상태 복구: {len(self.processed_folders)}개 폴더 처리됨")
            except Exception as e:
                self.logger.warning(f"상태 파일 로드 실패: {e}")
    
    def save_state(self):
        """현재 처리 상태 저장"""
        try:
            state = {
                'processed_folders': list(self.processed_folders),
                'last_update': datetime.now().isoformat()
            }
            with open(self.state_file, 'w') as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            self.logger.error(f"상태 파일 저장 실패: {e}")
    
    def find_new_folders(self) -> List[Path]:
        """새로운 Recording 폴더 찾기"""
        if not self.sync_capture_dir.exists():
            return []
        
        new_folders = []
        for folder in self.sync_capture_dir.glob(f"Recording_{self.route_name}*"):
            if (folder.is_dir() and 
                folder.name not in self.processed_folders and
                self.is_recording_complete(folder)):
                new_folders.append(folder)
        
        return new_folders
    
    def is_recording_complete(self, folder: Path) -> bool:
        """녹화가 완료되었는지 확인"""
        try:
            # 기본 파일 확인
            if not (folder / "frame_timestamps.txt").exists():
                return False
            
            # 카메라 폴더 확인
            camera_folders = [d for d in folder.iterdir() if d.is_dir() and 'Camera' in d.name]
            if len(camera_folders) < 2:
                return False
            
            # 이미지 파일 확인
            for cam_folder in camera_folders:
                images = list(cam_folder.glob("*.jpg")) + list(cam_folder.glob("*.png"))
                if len(images) < 10:
                    return False
            
            # 파일 쓰기 완료 확인 (10초 대기)
            latest_time = max(f.stat().st_mtime for f in folder.rglob("*") if f.is_file())
            if time.time() - latest_time < 10:
                return False
            
            return True
        except:
            return False
    
    def process_folder(self, folder: Path) -> bool:
        """개별 Recording 폴더 처리"""
        self.logger.info(f"🔄 처리 시작: {folder.name}")
        
        try:
            # 경로 수집 시작
            run_id = start_route_collection(self.route_name)
            self.logger.info(f"   -> 경로 수집 시작: {run_id}")
            
            # 삼각측량 처리
            processor = SimpleTriangulationProcessor(folder)
            success = processor.process()
            
            # 경로 수집 종료
            saved_run_id = stop_route_collection()
            
            if not success or not saved_run_id:
                self.logger.warning("   -> ⚠️ 처리 실패")
                return False
            
            self.logger.info(f"   -> ✅ 처리 완료: {saved_run_id}")
            
            # 후처리 및 업데이트
            individual_path = get_last_saved_run_path()
            if individual_path and individual_path.exists():
                self.post_process_route(individual_path)
                self.update_final_route()
            
            # 상태 업데이트
            self.processed_folders.add(folder.name)
            self.save_state()
            
            # 🎨 3단계 경로 비교 시각화 생성
            self.generate_comparison_visualization()
            
            return True
            
        except Exception as e:
            self.logger.error(f"   -> ❌ 처리 중 오류: {e}")
            stop_route_collection()
            return False
    
    def post_process_route(self, raw_path: Path):
        """원시 경로 데이터 후처리"""
        try:
            with open(raw_path, 'r') as f:
                raw_data = json.load(f)
            
            if not raw_data.get('points'):
                return
            
            # 필터링 적용
            filtered_points = self.filter_points(raw_data['points'])
            
            if not filtered_points:
                self.logger.warning("   -> ⚠️ 필터링 후 데이터 없음")
                return
            
            # 필터링된 데이터 저장 (경로 수정)
            filtered_data = {
                'run_id': raw_data['run_id'],
                'collection_time': raw_data['collection_time'],
                'total_points': len(filtered_points),
                'points': filtered_points,
                'filtered': True
            }
            
            # averaged_routes에 저장 (경로 수정)
            filtered_path = self.averaged_routes_dir / raw_path.name
            with open(filtered_path, 'w') as f:
                json.dump(filtered_data, f, indent=2, ensure_ascii=False)
            
            self.logger.info(f"   -> ✨ 필터링 완료: {len(filtered_points)}개 점")
            
        except Exception as e:
            self.logger.error(f"   -> ❌ 후처리 실패: {e}")
    
    def filter_points(self, points: List[dict]) -> List[dict]:
        """포인트 필터링 - 극단적인 값만 제거 (최소 필터링)"""
        if len(points) < 1:
            return points
        
        # 프레임별 정렬
        sorted_points = sorted(points, key=lambda p: p.get('frame', 0))
        
        # 극단적인 값만 제거
        filtered = []
        for point in sorted_points:
            # NaN/Inf 체크
            x, y, z = point.get('x', 0), point.get('y', 0), point.get('z', 0)
            
            # 숫자가 아니거나 무한대인 경우 제외
            if (not isinstance(x, (int, float)) or not isinstance(y, (int, float)) or not isinstance(z, (int, float)) or
                np.isnan(x) or np.isnan(y) or np.isnan(z) or
                np.isinf(x) or np.isinf(y) or np.isinf(z)):
                continue
            
            # 극단적으로 큰 값만 제외 (Unity 환경에서 비현실적인 값)
            if abs(x) > 10000 or abs(y) > 10000 or abs(z) > 10000:
                continue
            
            filtered.append(point)
        
        self.logger.info(f"   -> 🔍 극단값 필터링: {len(points)} -> {len(filtered)}개 (제거: {len(points) - len(filtered)}개)")
        return filtered
    
    def update_final_route(self):
        """최종 경로 업데이트"""
        try:
            if self.update_mode == "immediate":
                self.update_immediate()
            elif self.update_mode == "cumulative":
                self.update_cumulative()
            else:
                self.update_batch()
        except Exception as e:
            self.logger.error(f"   -> ❌ 경로 업데이트 실패: {e}")
    
    def update_immediate(self):
        """즉시 업데이트 - 최신 데이터로 교체"""
        averaged_dir = self.averaged_routes_dir
        latest_file = max(averaged_dir.glob("*.json"), key=lambda x: x.stat().st_mtime, default=None)
        
        if not latest_file:
            return
        
        with open(latest_file, 'r') as f:
            data = json.load(f)
        
        # 항공기 데이터만 추출
        airplane_points = [p for p in data.get('points', []) if p.get('object_type') == 'airplane']
        
        if not airplane_points:
            return
        
        # 경로 데이터 생성
        route_data = self.create_route_data(airplane_points)
        
        # 저장
        final_path = self.route_dir / f"{self.route_name}.json"
        with open(final_path, 'w') as f:
            json.dump(route_data, f, indent=2, ensure_ascii=False)
        
        self.logger.info(f"   -> 🚀 즉시 업데이트: {len(airplane_points)}개 waypoint")
    
    def update_cumulative(self):
        """누적 업데이트 - 평균 계산"""
        success = generate_average_route(self.route_name, min_runs=1)
        if success:
            self.logger.info("   -> 📈 누적 평균 업데이트 완료")
            # 실시간 시각화 업데이트
            self.generate_realtime_visualization()
        else:
            self.logger.error("   -> ❌ 누적 평균 업데이트 실패")
    
    def update_batch(self):
        """배치 업데이트 - 3개씩 평균"""
        success = generate_average_route(self.route_name, min_runs=3)
        if success:
            self.logger.info("   -> 📊 배치 평균 업데이트 완료")
            # 실시간 시각화 업데이트
            self.generate_realtime_visualization()
    
    def create_route_data(self, points: List[dict]) -> dict:
        """경로 데이터 생성"""
        sorted_points = sorted(points, key=lambda p: p.get('frame_id', 0))
        
        waypoints = []
        for point in sorted_points:
            waypoints.append({
                'x': float(point['x']),
                'y': float(point['y']),
                'z': float(point['z'])
            })
        
        return {
            'pathName': self.route_name,
            'exportTime': datetime.now().isoformat(),
            'totalWaypoints': len(waypoints),
            'waypoints': waypoints,
            'routePoints': waypoints
        }
    
    def run_batch(self):
        """배치 모드 - 모든 폴더 처리 후 종료"""
        self.logger.info("🚀 배치 모드 시작")
        
        folders = self.find_new_folders()
        if not folders:
            self.logger.info("📂 처리할 폴더가 없습니다")
            return
        
        success_count = 0
        for i, folder in enumerate(folders, 1):
            self.logger.info(f"📊 진행률: {i}/{len(folders)} - {folder.name}")
            if self.process_folder(folder):
                success_count += 1
        
        self.logger.info(f"🎉 배치 처리 완료: {success_count}/{len(folders)}개 성공")
    
    def run_monitor(self):
        """모니터링 모드 - 실시간 감시"""
        self.logger.info("🚀 실시간 모니터링 시작")
        self.is_running = True
        
        while not self.stop_requested:
            try:
                folders = self.find_new_folders()
                if folders:
                    self.logger.info(f"📁 새로운 폴더 {len(folders)}개 발견")
                    for folder in folders:
                        if self.stop_requested:
                            break
                        self.process_folder(folder)
                else:
                    self.logger.info("📂 새로운 폴더 없음, 대기 중...")
                
                # 5초 대기
                for _ in range(50):  # 0.1초씩 50번 = 5초
                    if self.stop_requested:
                        break
                    time.sleep(0.1)
                    
            except KeyboardInterrupt:
                break
            except Exception as e:
                self.logger.error(f"❌ 모니터링 중 오류: {e}")
                time.sleep(5)
        
        self.is_running = False
        self.logger.info("✅ 모니터링 종료")
    
    def stop(self):
        """중지 요청"""
        self.stop_requested = True
        self.logger.info("🛑 중지 요청됨")
    
    def generate_comparison_visualization(self):
        """3단계 경로 비교 시각화 생성"""
        try:
            self.logger.info("   -> 🎨 경로 비교 시각화 생성 중...")
            
            # 최신 파일들 찾기
            raw_file, filtered_file, final_file = self.find_latest_files()
            
            if not any([raw_file, filtered_file, final_file]):
                self.logger.warning("   -> ⚠️ 시각화할 파일이 없습니다")
                return
            
            # 시각화 생성
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            save_path = self.visualization_dir / f"{self.route_name}_{timestamp}_comparison.png"
            
            # route_visualizer의 함수들을 직접 호출
            self.create_comparison_visualization(raw_file, filtered_file, final_file, str(save_path))
            
            self.logger.info(f"   -> 💾 시각화 저장 완료: {save_path.name}")
            
        except Exception as e:
            self.logger.error(f"   -> ❌ 시각화 생성 실패: {e}")
    
    def generate_realtime_visualization(self):
        """실시간 경로 시각화 생성 (최종 경로만)"""
        try:
            self.logger.info("   -> 🔄 실시간 경로 시각화 업데이트 중...")
            
            final_file = self.route_dir / f"{self.route_name}.json"
            if not final_file.exists():
                self.logger.warning("   -> ⚠️ 최종 경로 파일이 없습니다")
                return
            
            # 간단한 시각화 생성
            save_path = self.visualization_dir / f"{self.route_name}_current.png"
            self.create_simple_visualization(final_file, str(save_path))
            
            self.logger.info(f"   -> 🎯 현재 경로 시각화 업데이트 완료: {save_path.name}")
            
        except Exception as e:
            self.logger.error(f"   -> ❌ 실시간 시각화 실패: {e}")
    
    def create_simple_visualization(self, route_file, save_path):
        """간단한 경로 시각화 생성"""
        try:
            import matplotlib.pyplot as plt
            import koreanize_matplotlib
            from mpl_toolkits.mplot3d import Axes3D
            
            # 데이터 로드
            with open(route_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            x, y, z = self.extract_coordinates_from_data(data)
            if x is None or len(x) == 0:
                self.logger.warning("      좌표 데이터가 없습니다")
                return
            
            # 시각화 생성
            fig = plt.figure(figsize=(15, 10))
            
            # 3D 경로
            ax1 = fig.add_subplot(221, projection='3d')
            ax1.plot(x, y, z, 'b-', linewidth=2, alpha=0.8, label=f'{self.route_name} ({len(x)}개 점)')
            ax1.scatter(x[0], y[0], z[0], color='green', s=100, label='Start', marker='o')
            ax1.scatter(x[-1], y[-1], z[-1], color='red', s=100, label='End', marker='s')
            
            ax1.set_xlabel('X (Unity Units)')
            ax1.set_ylabel('Y (Unity Units)')
            ax1.set_zlabel('Z (Unity Units)')
            ax1.set_title(f'현재 경로: {self.route_name}')
            ax1.legend()
            ax1.grid(True, alpha=0.3)
            
            # XY 평면
            ax2 = fig.add_subplot(222)
            ax2.plot(x, y, 'b-', linewidth=2, alpha=0.8)
            ax2.scatter(x[0], y[0], color='green', s=100, marker='o')
            ax2.scatter(x[-1], y[-1], color='red', s=100, marker='s')
            ax2.set_xlabel('X (Unity Units)')
            ax2.set_ylabel('Y (Unity Units)')
            ax2.set_title('Top View (XY)')
            ax2.grid(True, alpha=0.3)
            ax2.set_aspect('equal', adjustable='box')
            
            # XZ 평면
            ax3 = fig.add_subplot(223)
            ax3.plot(x, z, 'b-', linewidth=2, alpha=0.8)
            ax3.scatter(x[0], z[0], color='green', s=100, marker='o')
            ax3.scatter(x[-1], z[-1], color='red', s=100, marker='s')
            ax3.set_xlabel('X (Unity Units)')
            ax3.set_ylabel('Z (Unity Units)')
            ax3.set_title('Side View (XZ)')
            ax3.grid(True, alpha=0.3)
            
            # 통계 정보
            ax4 = fig.add_subplot(224)
            ax4.axis('off')
            
            total_dist = self.calculate_total_distance(x, y, z)
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            stats_text = f"""📊 {self.route_name} 경로 정보
🕒 업데이트: {timestamp}

📍 총 경로점: {len(x)}개
📏 총 거리: {total_dist:.1f} units

📐 좌표 범위:
   X: {x.min():.1f} ~ {x.max():.1f}
   Y: {y.min():.1f} ~ {y.max():.1f}
   Z: {z.min():.1f} ~ {z.max():.1f}
            """
            
            ax4.text(0, 1, stats_text, transform=ax4.transAxes, fontsize=12,
                    verticalalignment='top', fontfamily='monospace',
                    bbox=dict(boxstyle="round,pad=0.5", facecolor="lightblue", alpha=0.8))
            
            plt.suptitle(f'실시간 경로 모니터링: {self.route_name}', fontsize=16, fontweight='bold')
            plt.tight_layout()
            
            # 저장
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            plt.close()
            
        except Exception as e:
            self.logger.error(f"      간단 시각화 생성 오류: {e}")
    
    def find_latest_files(self):
        """최신 파일들 찾기 (경로 수정)"""
        # Raw 파일 (가장 최신)
        raw_files = list(self.raw_runs_dir.glob(f"{self.route_name}_*.json"))
        raw_file = max(raw_files, key=lambda x: x.stat().st_mtime) if raw_files else None
        
        # Filtered 파일 (가장 최신)
        filtered_files = list(self.averaged_routes_dir.glob(f"{self.route_name}_*.json"))
        filtered_file = max(filtered_files, key=lambda x: x.stat().st_mtime) if filtered_files else None
        
        # Final 파일
        final_file = self.route_dir / f"{self.route_name}.json"
        final_file = final_file if final_file.exists() else None
        
        return raw_file, filtered_file, final_file
    
    def create_comparison_visualization(self, raw_file, filtered_file, final_file, save_path):
        """3단계 경로 비교 시각화 생성"""
        try:
            import matplotlib.pyplot as plt
            import koreanize_matplotlib
            from mpl_toolkits.mplot3d import Axes3D
            
            # 데이터 로드 및 좌표 추출
            routes_data = {}
            colors = ['red', 'orange', 'blue']
            labels = ['Raw (원시)', 'Filtered (필터링)', 'Final (최종)']
            files = [raw_file, filtered_file, final_file]
            
            for i, (file, label) in enumerate(zip(files, labels)):
                if file and file.exists():
                    try:
                        with open(file, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        
                        x, y, z = self.extract_coordinates_from_data(data)
                        if x is not None and len(x) > 0:
                            routes_data[label] = {
                                'x': x, 'y': y, 'z': z,
                                'color': colors[i],
                                'count': len(x)
                            }
                    except Exception as e:
                        self.logger.warning(f"      파일 로드 실패 ({label}): {e}")
            
            if not routes_data:
                self.logger.warning("      비교할 경로 데이터가 없습니다")
                return
            
            # 시각화 생성
            fig = plt.figure(figsize=(20, 12))
            
            # 3D 전체 비교
            ax1 = fig.add_subplot(221, projection='3d')
            
            for label, data in routes_data.items():
                x, y, z = data['x'], data['y'], data['z']
                ax1.plot(x, y, z, color=data['color'], linewidth=2, alpha=0.7, 
                        label=f"{label} ({data['count']}개)")
                if len(x) > 0:
                    ax1.scatter(x[0], y[0], z[0], color=data['color'], s=100, marker='o', alpha=0.8)
                    ax1.scatter(x[-1], y[-1], z[-1], color=data['color'], s=100, marker='s', alpha=0.8)
            
            ax1.set_xlabel('X (Unity Units)')
            ax1.set_ylabel('Y (Unity Units)')
            ax1.set_zlabel('Z (Unity Units)')
            ax1.set_title(f'3D 경로 비교: {self.route_name}')
            ax1.legend()
            ax1.grid(True, alpha=0.3)
            
            # XY 평면 비교
            ax2 = fig.add_subplot(222)
            for label, data in routes_data.items():
                x, y = data['x'], data['y']
                ax2.plot(x, y, color=data['color'], linewidth=2, alpha=0.7, label=f"{label}")
                if len(x) > 0:
                    ax2.scatter(x[0], y[0], color=data['color'], s=80, marker='o', alpha=0.8)
                    ax2.scatter(x[-1], y[-1], color=data['color'], s=80, marker='s', alpha=0.8)
            
            ax2.set_xlabel('X (Unity Units)')
            ax2.set_ylabel('Y (Unity Units)')
            ax2.set_title('Top View (XY 평면)')
            ax2.grid(True, alpha=0.3)
            ax2.legend()
            ax2.set_aspect('equal', adjustable='box')
            
            # XZ 평면 비교
            ax3 = fig.add_subplot(223)
            for label, data in routes_data.items():
                x, z = data['x'], data['z']
                ax3.plot(x, z, color=data['color'], linewidth=2, alpha=0.7, label=f"{label}")
                if len(x) > 0:
                    ax3.scatter(x[0], z[0], color=data['color'], s=80, marker='o', alpha=0.8)
                    ax3.scatter(x[-1], z[-1], color=data['color'], s=80, marker='s', alpha=0.8)
            
            ax3.set_xlabel('X (Unity Units)')
            ax3.set_ylabel('Z (Unity Units)')
            ax3.set_title('Side View (XZ 평면)')
            ax3.grid(True, alpha=0.3)
            ax3.legend()
            
            # 통계 비교
            ax4 = fig.add_subplot(224)
            ax4.axis('off')
            
            stats_text = f"📊 {self.route_name} 경로 비교 통계\n" + "="*30 + "\n\n"
            
            for label, data in routes_data.items():
                x, y, z = data['x'], data['y'], data['z']
                total_dist = self.calculate_total_distance(x, y, z)
                
                stats_text += f"🔸 {label}:\n"
                stats_text += f"   • 점 개수: {len(x)}개\n"
                stats_text += f"   • 총 거리: {total_dist:.1f} units\n"
                stats_text += f"   • X 범위: {x.min():.1f} ~ {x.max():.1f}\n"
                stats_text += f"   • Y 범위: {y.min():.1f} ~ {y.max():.1f}\n"
                stats_text += f"   • Z 범위: {z.min():.1f} ~ {z.max():.1f}\n\n"
            
            ax4.text(0, 1, stats_text, transform=ax4.transAxes, fontsize=10,
                    verticalalignment='top', fontfamily='monospace',
                    bbox=dict(boxstyle="round,pad=0.5", facecolor="lightgray", alpha=0.8))
            
            plt.suptitle(f'경로 처리 단계별 비교: {self.route_name}', fontsize=16, fontweight='bold')
            plt.tight_layout()
            
            # 저장
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            plt.close()  # 메모리 절약
            
        except Exception as e:
            self.logger.error(f"      시각화 생성 오류: {e}")
    
    def extract_coordinates_from_data(self, data):
        """데이터에서 좌표 추출 (다양한 형식 지원)"""
        try:
            # 다양한 형식의 데이터 지원
            waypoints = data.get('waypoints', [])
            route_points = data.get('routePoints', [])
            points = data.get('points', [])
            
            # 가장 많은 데이터가 있는 것 사용
            data_source = waypoints
            if len(route_points) > len(data_source):
                data_source = route_points
            if len(points) > len(data_source):
                data_source = points
            
            if not data_source:
                return None, None, None
            
            # 좌표 추출 (다양한 형식 지원)
            x_coords, y_coords, z_coords = [], [], []
            
            for p in data_source:
                if isinstance(p, dict):
                    # 일반적인 x, y, z 형식
                    if 'x' in p and 'y' in p and 'z' in p:
                        x_coords.append(float(p['x']))
                        y_coords.append(float(p['y']))
                        z_coords.append(float(p['z']))
                    # position 리스트 형식
                    elif 'position' in p and len(p['position']) >= 3:
                        x_coords.append(float(p['position'][0]))
                        y_coords.append(float(p['position'][1]))
                        z_coords.append(float(p['position'][2]))
            
            if not x_coords:
                return None, None, None
            
            return np.array(x_coords), np.array(y_coords), np.array(z_coords)
            
        except Exception as e:
            self.logger.warning(f"좌표 추출 실패: {e}")
            return None, None, None
    
    def calculate_total_distance(self, x, y, z):
        """경로의 총 거리 계산"""
        if len(x) < 2:
            return 0.0
        distances = np.sqrt(np.diff(x)**2 + np.diff(y)**2 + np.diff(z)**2)
        return float(np.sum(distances))


class SimpleTriangulationProcessor:
    """단순화된 삼각측량 처리기"""
    
    def __init__(self, folder: Path):
        self.folder = folder
        self.logger = logging.getLogger(__name__)
    
    def process(self) -> bool:
        """삼각측량 처리"""
        try:
            # 필요한 모듈 import
            from aviation_detector import AviationDetector
            from triangulate import triangulate_objects_realtime, load_camera_parameters, get_projection_matrix
            
            # 감지기 초기화
            detector = AviationDetector()
            if not detector.model:
                self.logger.error("항공 감지기 초기화 실패")
                return False
            
            # 카메라 파라미터 로드
            params, matrices, letters = self.load_camera_params()
            if len(params) < 2:
                self.logger.error("카메라 파라미터 부족")
                return False
            
            # 이미지 시퀀스 수집
            sequences = self.collect_images(letters)
            if len(sequences) < 2:
                self.logger.error("이미지 시퀀스 부족")
                return False
            
            # 프레임별 처리
            max_frames = min(len(seq) for seq in sequences.values())
            successful_frames = 0
            
            self.logger.info(f"   -> 처리할 프레임: {max_frames}개")
            
            for frame_idx in range(max_frames):
                try:
                    # 프레임별 이미지 수집
                    frame_images = {}
                    for cam in letters:
                        if frame_idx < len(sequences[cam]):
                            frame_images[cam] = sequences[cam][frame_idx]
                    
                    if len(frame_images) < 2:
                        continue
                    
                    # 객체 감지
                    detections = []
                    for cam, img_path in frame_images.items():
                        cam_detections = detector.detect_single_image(img_path, camera_id=cam)
                        detections.extend(AviationDetector.format_detection_for_realtime(cam_detections, cam))
                    
                    if not detections:
                        continue
                    
                    # 삼각측량
                    triangulated = triangulate_objects_realtime(
                        detections=detections,
                        projection_matrices=matrices,
                        camera_letters=letters,
                        frame_id=frame_idx,
                        distance_threshold=100.0
                    )
                    
                    if triangulated:
                        # 데이터 변환 및 저장
                        converted = []
                        for p in triangulated:
                            converted.append({
                                'position': [float(p['x']), float(p['y']), float(p['z'])],
                                'class_name': str(p['class'])
                            })
                        
                        add_triangulation_data(frame_idx, converted)
                        successful_frames += 1
                
                except Exception as e:
                    self.logger.warning(f"프레임 {frame_idx} 처리 오류: {e}")
            
            self.logger.info(f"   -> 완료: {successful_frames}개 프레임 성공")
            return successful_frames > 10
            
        except Exception as e:
            self.logger.error(f"삼각측량 처리 오류: {e}")
            return False
    
    def load_camera_params(self):
        """카메라 파라미터 로드"""
        from triangulate import load_camera_parameters, get_projection_matrix
        
        params, matrices, letters = [], [], []
        
        for param_file in self.folder.glob("*_parameters.json"):
            try:
                p = load_camera_parameters(param_file)
                matrices.append(get_projection_matrix(p))
                params.append(p)
                
                # 카메라 문자 추출
                letter = param_file.stem.replace('_parameters', '').split('Camera_')[-1]
                letters.append(letter)
                
            except Exception as e:
                self.logger.warning(f"파라미터 로드 실패 ({param_file.name}): {e}")
        
        return params, matrices, letters
    
    def collect_images(self, letters: List[str]) -> dict:
        """이미지 시퀀스 수집"""
        sequences = {}
        
        for letter in letters:
            cam_folder = None
            for folder in self.folder.iterdir():
                if folder.is_dir() and f"Camera_{letter}" in folder.name:
                    cam_folder = folder
                    break
            
            if cam_folder:
                images = sorted(list(cam_folder.glob("*.jpg")) + list(cam_folder.glob("*.png")))
                sequences[letter] = images
            else:
                self.logger.warning(f"카메라 폴더 없음: Camera_{letter}")
        
        return sequences


def signal_handler(signum, frame):
    """시그널 핸들러"""
    print("\n🛑 중단 신호 수신")
    global processor
    if 'processor' in globals():
        processor.stop()


def main():
    """메인 함수"""
    global processor
    
    parser = argparse.ArgumentParser(description='Unity 경로 데이터 자동 수집기')
    parser.add_argument('route_name', nargs='?', default='Path_A', help='경로 이름')
    parser.add_argument('--batch', action='store_true', help='배치 모드')
    parser.add_argument('--immediate', action='store_true', help='즉시 업데이트')
    parser.add_argument('--cumulative', action='store_true', help='누적 업데이트')
    
    args = parser.parse_args()
    
    # 업데이트 모드 결정
    if args.immediate:
        update_mode = "immediate"
    elif args.cumulative:
        update_mode = "cumulative"
    else:
        update_mode = "batch"
    
    print("🤖 자동 경로 처리기 시작")
    print("=" * 60)
    print(f"🔄 업데이트 모드: {update_mode}")
    
    # 시그널 핸들러 등록
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # 프로세서 생성 및 실행
    processor = AutoRouteProcessor(args.route_name, update_mode)
    
    try:
        processor.load_state()
        
        if args.batch:
            processor.run_batch()
        else:
            processor.run_monitor()
            
    except KeyboardInterrupt:
        print("\n🛑 사용자 중단 요청. 정리 후 종료합니다...")
    finally:
        if processor.is_running:
            processor.stop()
        print("✅ 자동 처리기 종료")


if __name__ == "__main__":
    main() 
