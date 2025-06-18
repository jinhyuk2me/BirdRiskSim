#!/usr/bin/env python3
"""
BirdRiskSim 3D Triangulation Static Visualization Script
- 삼각측량으로 얻은 3D 좌표를 정적으로 시각화합니다.
- 모든 프레임의 데이터를 동시에 표시합니다.
"""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path
import webbrowser
import sys

def find_latest_folder(base_path, pattern):
    """지정된 패턴과 일치하는 가장 최신 폴더를 찾습니다."""
    folders = list(Path(base_path).glob(pattern))
    if not folders:
        return None
    return max(folders, key=lambda p: p.stat().st_mtime)

def main():
    """메인 실행 함수"""
    print("🚀 3D Triangulation 정적 시각화 시작...")

    # --- 1. 경로 설정 ---
    script_path = Path(__file__).resolve()
    project_root = script_path.parent.parent  # scripts/ -> BirdRiskSim_v2/

    # 가장 최신 삼각측량 결과 폴더를 찾기
    latest_results_folder = find_latest_folder(project_root / "data/triangulation_results", "results_*")
    if not latest_results_folder:
        print("❌ 'data/triangulation_results'에서 결과 폴더를 찾을 수 없습니다.")
        print("   먼저 'triangulate.py'를 실행해주세요.")
        return
    
    results_csv_path = latest_results_folder / "triangulation_results.csv"
    if not results_csv_path.exists():
        print(f"❌ CSV 파일을 찾을 수 없습니다: {results_csv_path}")
        return

    print(f"  - 시각화할 데이터: {results_csv_path}")

    # --- 2. 데이터 로드 ---
    try:
        df = pd.read_csv(results_csv_path)
    except Exception as e:
        print(f"❌ CSV 파일 로드 실패: {e}")
        return
        
    if df.empty:
        print("⚠️ 데이터가 비어있어 시각화를 진행할 수 없습니다.")
        return

    # 프레임 순서대로 정렬
    df = df.sort_values(by='frame')
    print(f"  - {len(df)}개의 3D 포인트 로드 완료.")
    
    # 클래스별 통계 출력
    print(f"  - 클래스별 포인트 수:")
    for cls in df['class'].unique():
        count = len(df[df['class'] == cls])
        print(f"    {cls}: {count}개")

    # --- 3. 궤적 시각화 생성 ---
    print("  - 궤적 시각화 생성 중...")
    
    # 색상 설정
    colors = {'Flock': 'blue', 'Airplane': 'red'}
    
    fig_trajectory = go.Figure()
    
    for cls in df['class'].unique():
        cls_data = df[df['class'] == cls].sort_values('frame')
        
        # 궤적 라인
        fig_trajectory.add_trace(go.Scatter3d(
            x=cls_data['x'],
            y=cls_data['y'],
            z=cls_data['z'],
            mode='lines+markers',
            line=dict(color=colors.get(cls, 'gray'), width=4),
            marker=dict(size=4, color=colors.get(cls, 'gray')),
            name=f'{cls} 궤적',
            text=[f'Frame: {row.frame}' for _, row in cls_data.iterrows()],
            hovertemplate='<b>%{fullData.name}</b><br>' +
                         'Frame: %{text}<br>' +
                         'X: %{x:.1f}<br>' +
                         'Y: %{y:.1f}<br>' +
                         'Z: %{z:.1f}<extra></extra>'
        ))

    fig_trajectory.update_layout(
        title='3D 객체 이동 궤적',
        scene=dict(
            xaxis_title='X (좌/우)',
            yaxis_title='Y (상/하)',
            zaxis_title='Z (앞/뒤)',
            camera=dict(
                eye=dict(x=1.5, y=1.5, z=1.5)
            )
        ),
        width=1200,
        height=800
    )

    # --- 4. 평면 시각화 생성 ---
    print("  - 평면 시각화 생성 중...")
    
    # 4.1 XY 평면 시각화 (Top View)
    fig_xy = go.Figure()
    for cls in df['class'].unique():
        cls_data = df[df['class'] == cls].sort_values('frame')
        
        # 정적 점들
        fig_xy.add_trace(go.Scatter(
            x=cls_data['x'],
            y=cls_data['y'],
            mode='markers',
            marker=dict(
                size=6,
                color=colors.get(cls, 'gray'),
                opacity=0.6
            ),
            name=f'{cls} 위치',
            text=[f'Frame: {row.frame}<br>Z: {row.z:.1f}' for _, row in cls_data.iterrows()],
            hovertemplate='<b>%{fullData.name}</b><br>' +
                         'X: %{x:.1f}<br>' +
                         'Y: %{y:.1f}<br>' +
                         '%{text}<extra></extra>'
        ))
        
        # 궤적 라인
        fig_xy.add_trace(go.Scatter(
            x=cls_data['x'],
            y=cls_data['y'],
            mode='lines',
            line=dict(color=colors.get(cls, 'gray'), width=2, dash='solid'),
            name=f'{cls} 궤적',
            opacity=0.8,
            showlegend=False
        ))
    
    fig_xy.update_layout(
        title='XY 평면 시각화 (위에서 본 뷰)',
        xaxis_title='X (좌/우)',
        yaxis_title='Y (상/하)',
        width=800,
        height=800
    )
    
    # 4.2 YZ 평면 시각화 (Side View - 왼쪽에서)
    fig_yz = go.Figure()
    for cls in df['class'].unique():
        cls_data = df[df['class'] == cls].sort_values('frame')
        
        # 정적 점들
        fig_yz.add_trace(go.Scatter(
            x=cls_data['y'],
            y=cls_data['z'],
            mode='markers',
            marker=dict(
                size=6,
                color=colors.get(cls, 'gray'),
                opacity=0.6
            ),
            name=f'{cls} 위치',
            text=[f'Frame: {row.frame}<br>X: {row.x:.1f}' for _, row in cls_data.iterrows()],
            hovertemplate='<b>%{fullData.name}</b><br>' +
                         'Y: %{x:.1f}<br>' +
                         'Z: %{y:.1f}<br>' +
                         '%{text}<extra></extra>'
        ))
        
        # 궤적 라인
        fig_yz.add_trace(go.Scatter(
            x=cls_data['y'],
            y=cls_data['z'],
            mode='lines',
            line=dict(color=colors.get(cls, 'gray'), width=2, dash='solid'),
            name=f'{cls} 궤적',
            opacity=0.8,
            showlegend=False
        ))
    
    fig_yz.update_layout(
        title='YZ 평면 시각화 (왼쪽에서 본 뷰)',
        xaxis_title='Y (상/하)',
        yaxis_title='Z (앞/뒤)',
        width=800,
        height=600
    )
    
    # 4.3 XZ 평면 시각화 (Side View - 앞에서)
    fig_xz = go.Figure()
    for cls in df['class'].unique():
        cls_data = df[df['class'] == cls].sort_values('frame')
        
        # 정적 점들
        fig_xz.add_trace(go.Scatter(
            x=cls_data['x'],
            y=cls_data['z'],
            mode='markers',
            marker=dict(
                size=6,
                color=colors.get(cls, 'gray'),
                opacity=0.6
            ),
            name=f'{cls} 위치',
            text=[f'Frame: {row.frame}<br>Y: {row.y:.1f}' for _, row in cls_data.iterrows()],
            hovertemplate='<b>%{fullData.name}</b><br>' +
                         'X: %{x:.1f}<br>' +
                         'Z: %{y:.1f}<br>' +
                         '%{text}<extra></extra>'
        ))
        
        # 궤적 라인
        fig_xz.add_trace(go.Scatter(
            x=cls_data['x'],
            y=cls_data['z'],
            mode='lines',
            line=dict(color=colors.get(cls, 'gray'), width=2, dash='solid'),
            name=f'{cls} 궤적',
            opacity=0.8,
            showlegend=False
        ))
    
    fig_xz.update_layout(
        title='XZ 평면 시각화 (앞에서 본 뷰)',
        xaxis_title='X (좌/우)',
        yaxis_title='Z (앞/뒤)',
        width=800,
        height=600
    )

    # --- 5. HTML 파일로 저장 ---
    output_trajectory_path = latest_results_folder / 'triangulation_trajectory.html'
    output_xy_path = latest_results_folder / 'triangulation_xy_plane.html'
    output_yz_path = latest_results_folder / 'triangulation_yz_plane.html'
    output_xz_path = latest_results_folder / 'triangulation_xz_plane.html'
    
    fig_trajectory.write_html(output_trajectory_path)
    fig_xy.write_html(output_xy_path)
    fig_yz.write_html(output_yz_path)
    fig_xz.write_html(output_xz_path)

    print(f"\n🎉 시각화 완료!")
    print(f"  - 궤적 시각화 (3D): {output_trajectory_path}")
    print(f"  - XY 평면 시각화: {output_xy_path}")
    print(f"  - YZ 평면 시각화: {output_yz_path}")
    print(f"  - XZ 평면 시각화: {output_xz_path}")
    
    # 자동으로 브라우저에서 열기
    try:
        webbrowser.open(f'file://{output_trajectory_path.resolve()}')
        print("  - 궤적 시각화를 웹 브라우저에서 열었습니다.")
    except Exception as e:
        print(f"  - 자동 열기 실패: {e}")


if __name__ == "__main__":
    try:
        import plotly
    except ImportError:
        print("="*60)
        print("오류: 'plotly' 라이브러리가 설치되지 않았습니다.")
        print("시각화 기능을 사용하려면 먼저 아래 명령어로 설치해주세요.")
        print("\n  pip install plotly kaleido\n")
        print("="*60)
        sys.exit(1)
        
    main() 