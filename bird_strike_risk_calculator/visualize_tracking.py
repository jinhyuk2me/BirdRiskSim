#!/usr/bin/env python3
"""
BirdRiskSim 세션 기반 트래킹 시각화 스크립트
- 세션 기반 트래킹 결과를 시각화합니다.
- 세션별로 색상을 구분하여 궤적을 표시합니다.
- 세션 갭과 시작/끝점을 명확히 보여줍니다.
"""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path
import numpy as np
import json

def find_latest_folder(base_path, pattern):
    """지정된 패턴과 일치하는 가장 최신 폴더를 찾습니다."""
    folders = list(Path(base_path).glob(pattern))
    if not folders:
        return None
    return max(folders, key=lambda p: p.stat().st_mtime)

def create_session_trajectory_plot(df):
    """세션별 궤적 시각화 (2D 평면도)"""
    # 세션별 색상 생성 (호환성을 위해 session_id/episode_id 둘 다 지원)
    id_column = 'session_id' if 'session_id' in df.columns else 'episode_id'
    sessions = sorted(df[id_column].unique())
    colors = px.colors.qualitative.Set3 + px.colors.qualitative.Pastel + px.colors.qualitative.Dark2
    session_colors = {ep: colors[i % len(colors)] for i, ep in enumerate(sessions)}
    
    fig = go.Figure()
    
    # 세션별로 궤적 그리기
    for session_id in sessions:
        session_data = df[df[id_column] == session_id].sort_values('frame')
        
        # 비행기와 새 각각 처리
        for class_name in ['Airplane', 'Flock']:
            class_data = session_data[session_data['class'] == class_name]
            if len(class_data) == 0:
                continue
                
            # 궤적 선
            symbol = 'circle' if class_name == 'Airplane' else 'triangle-up'
            line_style = dict(width=3) if class_name == 'Airplane' else dict(width=2, dash='dash')
            
            fig.add_trace(go.Scatter(
                x=class_data['x'],
                y=class_data['z'],
                mode='lines+markers',
                name=f'세션 {session_id} - {class_name}',
                line=dict(color=session_colors[session_id], **line_style),
                marker=dict(
                    symbol=symbol,
                    size=6 if class_name == 'Airplane' else 4,
                    color=session_colors[session_id]
                ),
                hovertemplate=f'<b>세션 {session_id} - {class_name}</b><br>' +
                             'Frame: %{customdata[0]}<br>' +
                             'X: %{x:.1f}<br>' +
                             'Z: %{y:.1f}<br>' +
                             'VX: %{customdata[1]:.2f}<br>' +
                             'VZ: %{customdata[2]:.2f}<extra></extra>',
                customdata=np.column_stack((class_data['frame'], class_data['vx'], class_data['vz']))
            ))
            
            # 시작점과 끝점 강조
            if len(class_data) > 0:
                start_point = class_data.iloc[0]
                end_point = class_data.iloc[-1]
                
                # 시작점 (초록 큰 원)
                fig.add_trace(go.Scatter(
                    x=[start_point['x']], y=[start_point['z']],
                    mode='markers',
                    marker=dict(
                        symbol='star',
                        size=15,
                        color='green',
                        line=dict(width=2, color='darkgreen')
                    ),
                    name=f'세션 {session_id} 시작',
                    hovertemplate=f'<b>세션 {session_id} 시작</b><br>' +
                                 f'Frame: {start_point["frame"]}<br>' +
                                 f'{class_name}<extra></extra>',
                    showlegend=False
                ))
                
                # 끝점 (빨간 X)
        fig.add_trace(go.Scatter(
                    x=[end_point['x']], y=[end_point['z']],
                    mode='markers',
                    marker=dict(
                        symbol='x',
                        size=15,
                        color='red',
                        line=dict(width=3)
                    ),
                    name=f'세션 {session_id} 끝',
                    hovertemplate=f'<b>세션 {session_id} 끝</b><br>' +
                                 f'Frame: {end_point["frame"]}<br>' +
                                 f'{class_name}<extra></extra>',
                    showlegend=False
        ))
    
    fig.update_layout(
        title=f'세션별 궤적 시각화<br><sub>총 {len(sessions)}개 세션 | 시작점: ⭐, 끝점: ❌</sub>',
        xaxis_title='X 좌표 (좌/우)',
        yaxis_title='Z 좌표 (앞/뒤)',
        legend_title_text='세션별 궤적',
        width=1200,
        height=800,
        hovermode='closest'
    )
    
    # 축 범위 설정
    margin = 100
    fig.update_xaxes(range=[df['x'].min() - margin, df['x'].max() + margin])
    fig.update_yaxes(range=[df['z'].min() - margin, df['z'].max() + margin])
    
    return fig

def create_session_timeline_plot(df):
    """세션별 시간축 시각화"""
    # 호환성을 위해 session_id/episode_id 둘 다 지원
    id_column = 'session_id' if 'session_id' in df.columns else 'episode_id'
    sessions = sorted(df[id_column].unique())
    colors = px.colors.qualitative.Set3 + px.colors.qualitative.Pastel
    session_colors = {ep: colors[i % len(colors)] for i, ep in enumerate(sessions)}
    
    fig = go.Figure()
    
    # 각 세션을 시간축에 표시
    for i, session_id in enumerate(sessions):
        session_data = df[df[id_column] == session_id]
        start_frame = session_data['frame'].min()
        end_frame = session_data['frame'].max()
        duration = end_frame - start_frame + 1
        
        # 세션 막대
        fig.add_trace(go.Scatter(
            x=[start_frame, end_frame],
            y=[i, i],
            mode='lines+markers+text',
            line=dict(color=session_colors[session_id], width=8),
            marker=dict(size=10, symbol=['circle', 'square']),
            name=f'세션 {session_id}',
            text=[f'시작 {start_frame}', f'끝 {end_frame}'],
            textposition=['middle left', 'middle right'],
            hovertemplate=f'<b>세션 {session_id}</b><br>' +
                         f'시작: {start_frame}<br>' +
                         f'끝: {end_frame}<br>' +
                         f'길이: {duration} 프레임<extra></extra>'
        ))
    
    # 갭 영역 표시
    if len(sessions) > 1:
        for i in range(len(sessions) - 1):
            curr_data = df[df[id_column] == sessions[i]]
            next_data = df[df[id_column] == sessions[i + 1]]
            
            curr_end = curr_data['frame'].max()
            next_start = next_data['frame'].min()
            
            if next_start > curr_end + 1:
                # 갭 구간 회색으로 표시
                fig.add_vrect(
                    x0=curr_end, x1=next_start,
                    fillcolor="lightgray", opacity=0.3,
                    layer="below", line_width=0,
                    annotation_text=f"갭 ({next_start - curr_end - 1}프레임)",
                    annotation_position="top"
                )
    
    fig.update_layout(
        title='세션별 시간축 분포<br><sub>회색 영역: 객체가 감지되지 않은 갭</sub>',
        xaxis_title='프레임 번호',
        yaxis_title='세션',
        height=max(400, len(sessions) * 40 + 200),
        yaxis=dict(
            tickmode='array',
            tickvals=list(range(len(sessions))),
            ticktext=[f'S {ep}' for ep in sessions]
        ),
        showlegend=True
    )
    
    return fig

# 복잡한 통계 함수들은 핵심 기능만 유지하기 위해 제거됨

def create_distance_analysis(df):
    """객체 간 거리 분석"""
    # 비행기와 새 무리 데이터 분리
    airplane_data = df[df['class'] == 'Airplane'].set_index('frame')[['x', 'z']]
    flock_data = df[df['class'] == 'Flock'].set_index('frame')[['x', 'z']]
    
    # 공통 프레임 찾기
    common_frames = airplane_data.index.intersection(flock_data.index)
    
    if len(common_frames) == 0:
        return None
    
    # 거리 계산
    distances = []
    for frame in common_frames:
        airplane_pos = airplane_data.loc[frame]
        flock_pos = flock_data.loc[frame]
        distance = np.sqrt((airplane_pos['x'] - flock_pos['x'])**2 + 
                          (airplane_pos['z'] - flock_pos['z'])**2)
        distances.append({'frame': frame, 'distance': distance})
    
    distance_df = pd.DataFrame(distances)
    
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=distance_df['frame'],
        y=distance_df['distance'],
        mode='lines+markers',
        name='비행기-새무리 거리',
        line=dict(color='purple', width=3),
        marker=dict(size=6)
    ))
    
    # 위험 임계값 표시 (예: 100 단위)
    min_distance = distance_df['distance'].min()
    fig.add_hline(y=100, line_dash="dash", line_color="red", 
                  annotation_text="위험 임계값 (100)")
    
    fig.update_layout(
        title=f'비행기와 새 무리 간 거리 변화<br><sub>최소 거리: {min_distance:.1f}</sub>',
        xaxis_title='프레임',
        yaxis_title='거리',
        height=400
    )
    
    return fig

def main():
    """메인 실행 함수"""
    print("🚀 세션 기반 트래킹 결과 시각화 시작...")

    # --- 1. 경로 설정 ---
    script_path = Path(__file__).resolve()
    project_root = script_path.parent.parent  # scripts/ -> BirdRiskSim_v2/

    # 세션 트래킹 결과 폴더
    latest_results_folder = project_root / "data/tracking_results/latest"
    
    if not latest_results_folder.exists():
        print("❌ 'data/tracking_results/latest' 폴더를 찾을 수 없습니다.")
        print("   먼저 세션 기반 'byte_track.py'를 실행해주세요.")
        return
    
    results_csv_path = latest_results_folder / "tracking_results.csv"
    session_summary_path = latest_results_folder / "session_summary.json"
    
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

    # 세션/에피소드 컬럼 확인 (호환성 지원)
    id_column = 'session_id' if 'session_id' in df.columns else 'episode_id'
    if id_column not in df.columns:
        print("❌ 세션/에피소드 정보가 없습니다. 트래킹을 먼저 실행해주세요.")
        return

    # 세션 요약 정보 로드
    session_summary = None
    if session_summary_path.exists():
        try:
            with open(session_summary_path, 'r') as f:
                session_summary = json.load(f)
        except Exception as e:
            print(f"⚠️ 세션 요약 로드 실패: {e}")

    # 프레임 순서대로 정렬
    df = df.sort_values(by='frame')
    sessions = sorted(df[id_column].unique())
    
    print(f"  - {len(df)}개의 트래킹 포인트 로드 완료.")
    print(f"  - 프레임 범위: {df['frame'].min()} ~ {df['frame'].max()}")
    print(f"  - 총 {len(sessions)}개 세션 감지")
    print(f"  - 추적 객체: {df['class'].unique()}")

    # --- 3. 세션 기반 시각화 생성 ---
    print("\n📊 세션 시각화 생성 중...")
    
    # 3.1 세션별 궤적 시각화
    print("  - 세션별 궤적 시각화 생성...")
    trajectory_fig = create_session_trajectory_plot(df)
    trajectory_path = latest_results_folder / 'session_trajectories.html'
    trajectory_fig.write_html(trajectory_path)
    
    # 3.2 세션 시간축 시각화
    print("  - 세션 시간축 시각화 생성...")
    timeline_fig = create_session_timeline_plot(df)
    timeline_path = latest_results_folder / 'session_timeline.html'
    timeline_fig.write_html(timeline_path)
    
    # 3.3 거리 분석
    print("  - 세션별 거리 분석...")
    distance_fig = create_distance_analysis(df)
    if distance_fig:
        distance_path = latest_results_folder / 'session_distance_analysis.html'
        distance_fig.write_html(distance_path)
    else:
        print("    ⚠️ 거리 분석: 공통 프레임이 없어 건너뜀")

    # --- 4. 결과 출력 ---
    print(f"\n🎉 세션 시각화 완료!")
    print(f"  📁 결과 폴더: {latest_results_folder}")
    print(f"  🎯 세션별 궤적: session_trajectories.html")
    print(f"  📅 세션 시간축: session_timeline.html")
    if distance_fig:
        print(f"  📏 거리 분석: session_distance_analysis.html")
    
    # 자동으로 브라우저에서 궤적 시각화 열기
    try:
        import webbrowser
        webbrowser.open(f'file://{trajectory_path.resolve()}')
        print(f"  - 세션별 궤적 시각화를 웹 브라우저에서 자동으로 열었습니다.")
    except Exception as e:
        print(f"  - 자동 열기 실패: {e}")
        print("  - 수동으로 HTML 파일들을 열어주세요.")

if __name__ == "__main__":
    try:
        import plotly
    except ImportError:
        print("="*60)
        print("오류: 'plotly' 라이브러리가 설치되지 않았습니다.")
        print("시각화 기능을 사용하려면 먼저 아래 명령어로 설치해주세요.")
        print("\n  pip install plotly kaleido\n")
        print("="*60)
        import sys
        sys.exit(1)
        
    main() 