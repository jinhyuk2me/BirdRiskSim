#!/usr/bin/env python3
"""
경로 시각화 도구
Unity에서 수집된 경로 데이터를 3D로 시각화합니다.
"""

import json
import numpy as np
import matplotlib.pyplot as plt
import koreanize_matplotlib
from mpl_toolkits.mplot3d import Axes3D
from pathlib import Path
import argparse

def load_route_data(route_file: str):
    """경로 데이터 로드"""
    route_path = Path(route_file)
    
    if not route_path.exists():
        print(f"❌ 경로 파일을 찾을 수 없습니다: {route_file}")
        return None
    
    try:
        with open(route_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        print(f"✅ 경로 데이터 로드 완료: {route_file}")
        print(f"   📊 총 경로점: {data.get('totalWaypoints', len(data.get('waypoints', data.get('points', []))))}개")
        print(f"   📅 생성 시간: {data.get('exportTime', data.get('collection_time', 'Unknown'))}")
        
        return data
    
    except Exception as e:
        print(f"❌ 경로 데이터 로드 실패: {e}")
        return None

def extract_coordinates(route_data):
    """경로 데이터에서 좌표 추출"""
    # 다양한 형식의 데이터 지원
    waypoints = route_data.get('waypoints', [])
    route_points = route_data.get('routePoints', [])
    points = route_data.get('points', [])
    
    # 가장 많은 데이터가 있는 것 사용
    data_source = waypoints
    if len(route_points) > len(data_source):
        data_source = route_points
    if len(points) > len(data_source):
        data_source = points
    
    if not data_source:
        print("❌ 경로점 데이터가 없습니다.")
        return None, None, None
    
    # 좌표 추출 (다양한 형식 지원)
    x_coords, y_coords, z_coords = [], [], []
    
    for p in data_source:
        if isinstance(p, dict):
            # 일반적인 x, y, z 형식
            if 'x' in p and 'y' in p and 'z' in p:
                x_coords.append(p['x'])
                y_coords.append(p['y'])
                z_coords.append(p['z'])
            # position 리스트 형식
            elif 'position' in p and len(p['position']) >= 3:
                x_coords.append(p['position'][0])
                y_coords.append(p['position'][1])
                z_coords.append(p['position'][2])
    
    if not x_coords:
        print("❌ 좌표 데이터를 추출할 수 없습니다.")
        return None, None, None
    
    return np.array(x_coords), np.array(y_coords), np.array(z_coords)

def create_3d_visualization(x, y, z, route_name="Path", save_path=None):
    """3D 경로 시각화"""
    fig = plt.figure(figsize=(15, 10))
    ax = fig.add_subplot(111, projection='3d')
    
    # 경로 선 그리기
    ax.plot(x, y, z, 'b-', linewidth=2, alpha=0.8, label=f'{route_name} Route')
    
    # 시작점과 끝점 표시
    ax.scatter(x[0], y[0], z[0], color='green', s=100, label='Start', marker='o')
    ax.scatter(x[-1], y[-1], z[-1], color='red', s=100, label='End', marker='s')
    
    # 중간 점들 표시 (10개마다)
    step = max(1, len(x) // 10)
    ax.scatter(x[::step], y[::step], z[::step], color='blue', s=20, alpha=0.6)
    
    # 축 레이블 및 제목
    ax.set_xlabel('X (Unity Units)', fontsize=12)
    ax.set_ylabel('Y (Unity Units)', fontsize=12)
    ax.set_zlabel('Z (Unity Units)', fontsize=12)
    ax.set_title(f'3D Flight Path Visualization: {route_name}', fontsize=14, fontweight='bold')
    
    # 범례
    ax.legend()
    
    # 격자 표시
    ax.grid(True, alpha=0.3)
    
    # 축 비율 조정
    ax.set_box_aspect([1,1,1])
    
    # 통계 정보 표시
    stats_text = f"""
    📊 경로 통계:
    • 총 점 수: {len(x)}
    • X 범위: {x.min():.1f} ~ {x.max():.1f}
    • Y 범위: {y.min():.1f} ~ {y.max():.1f}
    • Z 범위: {z.min():.1f} ~ {z.max():.1f}
    • 총 거리: {calculate_total_distance(x, y, z):.1f} units
    """
    
    plt.figtext(0.02, 0.02, stats_text, fontsize=10, 
                bbox=dict(boxstyle="round,pad=0.3", facecolor="lightgray", alpha=0.8))
    
    # 저장
    if save_path:
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        print(f"💾 시각화 저장 완료: {save_path}")
    
    plt.tight_layout()
    plt.show()

def create_2d_projections(x, y, z, route_name="Path", save_path=None):
    """2D 투영 시각화 (XY, XZ, YZ 평면)"""
    fig, axes = plt.subplots(2, 2, figsize=(15, 12))
    fig.suptitle(f'2D Projections: {route_name}', fontsize=16, fontweight='bold')
    
    # XY 평면 (Top View)
    axes[0, 0].plot(x, y, 'b-', linewidth=2, alpha=0.8)
    axes[0, 0].scatter(x[0], y[0], color='green', s=100, label='Start', zorder=5)
    axes[0, 0].scatter(x[-1], y[-1], color='red', s=100, label='End', zorder=5)
    axes[0, 0].set_xlabel('X (Unity Units)')
    axes[0, 0].set_ylabel('Y (Unity Units)')
    axes[0, 0].set_title('Top View (XY Plane)')
    axes[0, 0].grid(True, alpha=0.3)
    axes[0, 0].legend()
    axes[0, 0].set_aspect('equal', adjustable='box')
    
    # XZ 평면 (Side View)
    axes[0, 1].plot(x, z, 'r-', linewidth=2, alpha=0.8)
    axes[0, 1].scatter(x[0], z[0], color='green', s=100, label='Start', zorder=5)
    axes[0, 1].scatter(x[-1], z[-1], color='red', s=100, label='End', zorder=5)
    axes[0, 1].set_xlabel('X (Unity Units)')
    axes[0, 1].set_ylabel('Z (Unity Units)')
    axes[0, 1].set_title('Side View (XZ Plane)')
    axes[0, 1].grid(True, alpha=0.3)
    axes[0, 1].legend()
    
    # YZ 평면 (Front View)
    axes[1, 0].plot(y, z, 'g-', linewidth=2, alpha=0.8)
    axes[1, 0].scatter(y[0], z[0], color='green', s=100, label='Start', zorder=5)
    axes[1, 0].scatter(y[-1], z[-1], color='red', s=100, label='End', zorder=5)
    axes[1, 0].set_xlabel('Y (Unity Units)')
    axes[1, 0].set_ylabel('Z (Unity Units)')
    axes[1, 0].set_title('Front View (YZ Plane)')
    axes[1, 0].grid(True, alpha=0.3)
    axes[1, 0].legend()
    
    # 고도 프로필
    distance = np.cumsum(np.sqrt(np.diff(x)**2 + np.diff(y)**2 + np.diff(z)**2))
    distance = np.insert(distance, 0, 0)  # 시작점 거리 0 추가
    
    axes[1, 1].plot(distance, y, 'purple', linewidth=2, alpha=0.8)
    axes[1, 1].set_xlabel('Distance along path')
    axes[1, 1].set_ylabel('Altitude (Y)')
    axes[1, 1].set_title('Altitude Profile')
    axes[1, 1].grid(True, alpha=0.3)
    
    # 저장
    if save_path:
        save_path_2d = save_path.replace('.png', '_2d_projections.png')
        plt.savefig(save_path_2d, dpi=300, bbox_inches='tight')
        print(f"💾 2D 투영 저장 완료: {save_path_2d}")
    
    plt.tight_layout()
    plt.show()

def calculate_total_distance(x, y, z):
    """경로의 총 거리 계산"""
    distances = np.sqrt(np.diff(x)**2 + np.diff(y)**2 + np.diff(z)**2)
    return np.sum(distances)

def analyze_route_statistics(x, y, z, route_name="Path"):
    """경로 통계 분석"""
    print(f"\n📊 {route_name} 경로 분석 결과:")
    print("=" * 50)
    
    # 기본 통계
    print(f"📍 총 경로점 수: {len(x)}")
    print(f"📏 총 거리: {calculate_total_distance(x, y, z):.2f} units")
    
    # 좌표 범위
    print(f"\n📐 좌표 범위:")
    print(f"   X: {x.min():.2f} ~ {x.max():.2f} (범위: {x.max()-x.min():.2f})")
    print(f"   Y: {y.min():.2f} ~ {y.max():.2f} (범위: {y.max()-y.min():.2f})")
    print(f"   Z: {z.min():.2f} ~ {z.max():.2f} (범위: {z.max()-z.min():.2f})")
    
    # 속도 분석 (연속 점 간 거리)
    distances = np.sqrt(np.diff(x)**2 + np.diff(y)**2 + np.diff(z)**2)
    print(f"\n🚀 이동 속도 분석:")
    print(f"   평균 속도: {np.mean(distances):.2f} units/frame")
    print(f"   최대 속도: {np.max(distances):.2f} units/frame")
    print(f"   최소 속도: {np.min(distances):.2f} units/frame")
    
    # 방향 변화 분석
    direction_changes = []
    for i in range(1, len(x)-1):
        v1 = np.array([x[i]-x[i-1], y[i]-y[i-1], z[i]-z[i-1]])
        v2 = np.array([x[i+1]-x[i], y[i+1]-y[i], z[i+1]-z[i]])
        
        if np.linalg.norm(v1) > 0 and np.linalg.norm(v2) > 0:
            cos_angle = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2))
            cos_angle = np.clip(cos_angle, -1, 1)  # 수치 오차 방지
            angle = np.arccos(cos_angle) * 180 / np.pi
            direction_changes.append(angle)
    
    if direction_changes:
        print(f"\n🔄 방향 변화 분석:")
        print(f"   평균 방향 변화: {np.mean(direction_changes):.2f}°")
        print(f"   최대 방향 변화: {np.max(direction_changes):.2f}°")

def find_latest_files(route_name: str = "Path_A"):
    """최신 파일들 찾기"""
    base_dir = Path("data")
    
    # Raw 파일 (가장 최신) - 경로 수정
    raw_dir = base_dir / "routes" / "raw_runs"
    raw_files = list(raw_dir.glob(f"{route_name}_*.json"))
    raw_file = max(raw_files, key=lambda x: x.stat().st_mtime) if raw_files else None
    
    # Filtered 파일 (가장 최신) - 경로 수정
    filtered_dir = base_dir / "routes" / "averaged_routes"
    filtered_files = list(filtered_dir.glob(f"{route_name}_*.json"))
    filtered_file = max(filtered_files, key=lambda x: x.stat().st_mtime) if filtered_files else None
    
    # Final 파일
    final_file = base_dir / "routes" / f"{route_name}.json"
    final_file = final_file if final_file.exists() else None
    
    return raw_file, filtered_file, final_file

def compare_routes(raw_file, filtered_file, final_file, route_name="Path_A", save_path=None):
    """3단계 경로 비교 시각화"""
    print(f"\n🔍 {route_name} 경로 비교 분석")
    print("=" * 60)
    
    # 데이터 로드
    routes_data = {}
    colors = ['red', 'orange', 'blue']
    labels = ['Raw (원시)', 'Filtered (필터링)', 'Final (최종)']
    files = [raw_file, filtered_file, final_file]
    
    for i, (file, label) in enumerate(zip(files, labels)):
        if file and file.exists():
            data = load_route_data(str(file))
            if data:
                x, y, z = extract_coordinates(data)
                if x is not None:
                    routes_data[label] = {
                        'x': x, 'y': y, 'z': z,
                        'color': colors[i],
                        'count': len(x)
                    }
                    print(f"   ✅ {label}: {len(x)}개 점")
                else:
                    print(f"   ❌ {label}: 좌표 추출 실패")
            else:
                print(f"   ❌ {label}: 파일 로드 실패")
        else:
            print(f"   ⚠️ {label}: 파일 없음")
    
    if not routes_data:
        print("❌ 비교할 경로 데이터가 없습니다.")
        return
    
    # 3D 비교 시각화
    fig = plt.figure(figsize=(20, 12))
    
    # 3D 전체 비교
    ax1 = fig.add_subplot(221, projection='3d')
    
    for label, data in routes_data.items():
        x, y, z = data['x'], data['y'], data['z']
        ax1.plot(x, y, z, color=data['color'], linewidth=2, alpha=0.7, label=f"{label} ({data['count']}개)")
        ax1.scatter(x[0], y[0], z[0], color=data['color'], s=100, marker='o', alpha=0.8)
        ax1.scatter(x[-1], y[-1], z[-1], color=data['color'], s=100, marker='s', alpha=0.8)
    
    ax1.set_xlabel('X (Unity Units)')
    ax1.set_ylabel('Y (Unity Units)')
    ax1.set_zlabel('Z (Unity Units)')
    ax1.set_title(f'3D 경로 비교: {route_name}')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    
    # XY 평면 비교
    ax2 = fig.add_subplot(222)
    for label, data in routes_data.items():
        x, y = data['x'], data['y']
        ax2.plot(x, y, color=data['color'], linewidth=2, alpha=0.7, label=f"{label}")
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
    
    stats_text = f"📊 {route_name} 경로 비교 통계\n" + "="*30 + "\n\n"
    
    for label, data in routes_data.items():
        x, y, z = data['x'], data['y'], data['z']
        total_dist = calculate_total_distance(x, y, z)
        
        stats_text += f"🔸 {label}:\n"
        stats_text += f"   • 점 개수: {len(x)}개\n"
        stats_text += f"   • 총 거리: {total_dist:.1f} units\n"
        stats_text += f"   • X 범위: {x.min():.1f} ~ {x.max():.1f}\n"
        stats_text += f"   • Y 범위: {y.min():.1f} ~ {y.max():.1f}\n"
        stats_text += f"   • Z 범위: {z.min():.1f} ~ {z.max():.1f}\n\n"
    
    ax4.text(0, 1, stats_text, transform=ax4.transAxes, fontsize=10,
             verticalalignment='top', fontfamily='monospace',
             bbox=dict(boxstyle="round,pad=0.5", facecolor="lightgray", alpha=0.8))
    
    plt.suptitle(f'경로 처리 단계별 비교: {route_name}', fontsize=16, fontweight='bold')
    
    # 저장
    if save_path:
        comparison_path = save_path.replace('.png', '_comparison.png')
        plt.savefig(comparison_path, dpi=300, bbox_inches='tight')
        print(f"💾 비교 시각화 저장 완료: {comparison_path}")
    
    plt.tight_layout()
    plt.show()

def main():
    """메인 실행 함수"""
    parser = argparse.ArgumentParser(description='Unity 경로 데이터 시각화')
    parser.add_argument('route_file', nargs='?', default='data/routes/Path_A.json',
                       help='경로 파일 경로 (기본: data/routes/Path_A.json)')
    parser.add_argument('--save', '-s', help='시각화 이미지 저장 경로 (기본: 경로 파일과 같은 폴더)')
    parser.add_argument('--no-3d', action='store_true', help='3D 시각화 건너뛰기')
    parser.add_argument('--no-2d', action='store_true', help='2D 투영 건너뛰기')
    parser.add_argument('--stats-only', action='store_true', help='통계만 출력')
    parser.add_argument('--compare', '-c', help='경로 이름으로 3단계 비교 (예: Path_A)')
    
    args = parser.parse_args()
    
    print("🎨 Unity 경로 시각화 도구")
    print("=" * 50)
    
    # 비교 모드
    if args.compare:
        route_name = args.compare
        raw_file, filtered_file, final_file = find_latest_files(route_name)
        
        save_path = args.save
        if save_path is None:
            save_path = f"data/visualizations/{route_name.lower()}_comparison.png"
            Path("data/visualizations").mkdir(parents=True, exist_ok=True)
        
        compare_routes(raw_file, filtered_file, final_file, route_name, save_path)
        return
    
    # 단일 경로 모드
    route_data = load_route_data(args.route_file)
    if route_data is None:
        return
    
    # 좌표 추출
    x, y, z = extract_coordinates(route_data)
    if x is None:
        return
    
    route_name = route_data.get('pathName', 'Unknown')
    
    # 통계 분석
    analyze_route_statistics(x, y, z, route_name)
    
    if args.stats_only:
        return
    
    # 시각화 저장 경로 설정
    save_path = args.save
    if save_path is None and not args.stats_only:
        # 기본값: 경로 파일과 같은 폴더에 저장
        route_file_path = Path(args.route_file)
        save_path = str(route_file_path.parent / f"{route_name.lower()}_visualization.png")
    
    if not args.no_3d:
        print(f"\n🎨 3D 시각화 생성 중...")
        create_3d_visualization(x, y, z, route_name, save_path)
    
    if not args.no_2d:
        print(f"\n🎨 2D 투영 생성 중...")
        create_2d_projections(x, y, z, route_name, save_path)
    
    print(f"\n✅ 시각화 완료!")

if __name__ == "__main__":
    main() 