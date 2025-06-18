using UnityEngine;
using System.Collections.Generic;

public class WaypointBezierPath : MonoBehaviour
{
    [Header("Path Configuration")]
    public List<Transform> waypoints = new List<Transform>();
    
    [Header("Visualization")]
    [Range(10, 100)] 
    public int gizmoResolution = 50; // 100에서 50으로 줄여서 성능 최적화

    public Vector3 GetPosition(float t)
    {
        if (waypoints.Count < 2) return Vector3.zero;

        // t 값을 0-1 범위로 클램프
        t = Mathf.Clamp01(t);

        int segmentCount = waypoints.Count - 1;
        float scaledT = t * segmentCount;
        int index = Mathf.FloorToInt(scaledT);
        index = Mathf.Clamp(index, 0, segmentCount - 1);

        float localT = scaledT - index;

        // 인덱스 계산 최적화
        int i0 = Mathf.Max(0, index - 1);
        int i1 = index;
        int i2 = Mathf.Min(waypoints.Count - 1, index + 1);
        int i3 = Mathf.Min(waypoints.Count - 1, index + 2);

        Vector3 p0 = waypoints[i0].transform.position; // World Position 사용
        Vector3 p1 = waypoints[i1].transform.position; // World Position 사용
        Vector3 p2 = waypoints[i2].transform.position; // World Position 사용
        Vector3 p3 = waypoints[i3].transform.position; // World Position 사용

        // Catmull-Rom 스플라인 계산
        return 0.5f * (
            2f * p1 +
            (-p0 + p2) * localT +
            (2f * p0 - 5f * p1 + 4f * p2 - p3) * localT * localT +
            (-p0 + 3f * p1 - 3f * p2 + p3) * localT * localT * localT
        );
    }

    /// <summary>
    /// 경로의 방향 벡터를 가져옴
    /// </summary>
    public Vector3 GetDirection(float t)
    {
        float delta = 0.01f;
        Vector3 pos1 = GetPosition(t);
        Vector3 pos2 = GetPosition(Mathf.Clamp01(t + delta));
        return (pos2 - pos1).normalized;
    }

    /// <summary>
    /// 웨이포인트가 유효한지 확인
    /// </summary>
    public bool IsValid()
    {
        if (waypoints.Count < 2) return false;
        
        foreach (var wp in waypoints)
        {
            if (wp == null) return false;
        }
        return true;
    }

    /// <summary>
    /// 웨이포인트 데이터를 JSON으로 내보내기
    /// </summary>
    [ContextMenu("Export Route to JSON")]
    public void ExportRouteToJSON()
    {
        if (!IsValid())
        {
            Debug.LogError("❌ 유효하지 않은 경로입니다. 최소 2개의 웨이포인트가 필요합니다.");
            return;
        }

        try
        {
            // 웨이포인트 데이터 수집
            var routeData = new RouteExportData
            {
                pathName = gameObject.name,
                waypoints = new System.Collections.Generic.List<Vector3Data>(),
                routePoints = new System.Collections.Generic.List<Vector3Data>(),
                exportTime = System.DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss"),
                totalWaypoints = waypoints.Count
            };

            // 웨이포인트 추가 (World Position 사용)
            foreach (var wp in waypoints)
            {
                if (wp != null)
                {
                    Vector3 worldPos = wp.transform.position; // Local이 아닌 World Position 사용
                    routeData.waypoints.Add(new Vector3Data
                    {
                        x = worldPos.x,
                        y = worldPos.y,
                        z = worldPos.z
                    });
                }
            }

            // 경로 포인트 생성 (1% 간격으로 샘플링)
            for (int i = 0; i <= 100; i++)
            {
                float t = i / 100f;
                Vector3 pos = GetPosition(t);
                routeData.routePoints.Add(new Vector3Data
                {
                    x = pos.x,
                    y = pos.y,
                    z = pos.z
                });
            }

            // JSON 직렬화
            string json = JsonUtility.ToJson(routeData, true);
            
            // 파일 저장 경로
            string fileName = $"route_{gameObject.name}_{System.DateTime.Now:yyyyMMdd_HHmmss}.json";
            string filePath = System.IO.Path.Combine(Application.dataPath, "..", "data", "routes", fileName);
            
            // 디렉토리 생성
            System.IO.Directory.CreateDirectory(System.IO.Path.GetDirectoryName(filePath));
            
            // 파일 저장
            System.IO.File.WriteAllText(filePath, json);
            
            Debug.Log($"✅ 경로 데이터 내보내기 완료!");
            Debug.Log($"📁 파일 경로: {filePath}");
            Debug.Log($"📊 웨이포인트: {routeData.waypoints.Count}개");
            Debug.Log($"📍 경로 포인트: {routeData.routePoints.Count}개");
            
        }
        catch (System.Exception e)
        {
            Debug.LogError($"❌ 경로 내보내기 실패: {e.Message}");
        }
    }

    [System.Serializable]
    public class RouteExportData
    {
        public string pathName;
        public System.Collections.Generic.List<Vector3Data> waypoints;
        public System.Collections.Generic.List<Vector3Data> routePoints;
        public string exportTime;
        public int totalWaypoints;
    }

    [System.Serializable]
    public class Vector3Data
    {
        public float x;
        public float y;
        public float z;
    }

    private void OnDrawGizmos()
    {
        if (!IsValid()) return;

        // 경로 라인 그리기
        Gizmos.color = Color.cyan;
        Vector3 prev = GetPosition(0f);

        for (int i = 1; i <= gizmoResolution; i++)
        {
            float t = i / (float)gizmoResolution;
            Vector3 curr = GetPosition(t);
            Gizmos.DrawLine(prev, curr);
            prev = curr;
        }

        // 웨이포인트 그리기 (색상 한 번만 설정)
        Gizmos.color = Color.yellow;
        for (int i = 0; i < waypoints.Count; i++)
        {
            if (waypoints[i] != null)
            {
                Gizmos.DrawSphere(waypoints[i].transform.position, 0.8f); // World Position 사용
                
                // 시작점과 끝점 구분
                if (i == 0)
                {
                    Gizmos.color = Color.green; // 시작점
                    Gizmos.DrawSphere(waypoints[i].transform.position, 1.2f); // World Position 사용
                    Gizmos.color = Color.yellow;
                }
                else if (i == waypoints.Count - 1)
                {
                    Gizmos.color = Color.red; // 끝점
                    Gizmos.DrawSphere(waypoints[i].transform.position, 1.2f); // World Position 사용
                    Gizmos.color = Color.yellow;
                }
            }
        }
    }

    private void OnDrawGizmosSelected()
    {
        if (!IsValid()) return;

        // 선택됐을 때 더 자세한 정보 표시
        Gizmos.color = Color.white;
        for (int i = 0; i < waypoints.Count; i++)
        {
            if (waypoints[i] != null)
            {
                // 웨이포인트 번호 표시 (에디터에서만)
                #if UNITY_EDITOR
                UnityEditor.Handles.Label(waypoints[i].transform.position + Vector3.up * 2f, $"WP {i}"); // World Position 사용
                #endif
            }
        }
    }
}
