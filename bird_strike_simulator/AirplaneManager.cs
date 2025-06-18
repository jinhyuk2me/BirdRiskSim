using UnityEngine;
using System.Collections;
using System.Collections.Generic;

public class AirplaneManager : MonoBehaviour
{
    [Header("Prefabs")]
    public GameObject[] airplanePrefabs;

    [Header("Flight Paths")]
    [Tooltip("비행기가 따라갈 경로 리스트. 비어있으면 Scene에서 자동으로 찾습니다.")]
    [SerializeField] private List<WaypointBezierPath> flightPaths;

    [Header("Spawn Settings - Performance Optimized")]
    [Range(1, 2)]
    public int maxSimultaneousAirplanes = 1;  // 2대에서 1대로 줄임
    
    [Range(5f, 20f)]
    public float minSpawnInterval = 10f;  // 8초에서 10초로 늘림
    [Range(5f, 20f)]
    public float maxSpawnInterval = 25f;  // 18초에서 25초로 늘림
    
    [Range(0f, 30f)]
    public float minSpeed = 15f;
    [Range(0f, 30f)]
    public float maxSpeed = 22f;  // 25에서 22로 약간 줄임
    
    public bool loop = false;

    [Header("Spawn Variation")]
    [Range(0f, 0.5f)]
    public float multipleAirplaneProbability = 0.1f; // 30%에서 10%로 줄임
    
    [Range(0f, 0.5f)]
    public float emptySkiesProbability = 0.35f; // 20%에서 35%로 늘림 (성능 여유)

    [Range(1f, 8f)]
    public float formationSpacing = 4f; // 편대 간격 약간 늘림

    [Header("Performance Settings")]
    public bool enablePerformanceMode = true;
    [HideInInspector]
    public bool isScenarioControlled = false;

    private List<GameObject> activeAirplanes = new List<GameObject>();
    private int airplaneIndex = 0;
    private Coroutine spawnCoroutine;

    void Start()
    {
        Debug.Log($"[AirplaneManager] Start() 호출됨");
        Debug.Log($"[AirplaneManager] flightPaths null 체크: {flightPaths == null}");
        
        // flightPaths 초기화 및 검증
        InitializeFlightPaths();
        
        Debug.Log($"[AirplaneManager] 초기화 후 flightPaths 개수: {(flightPaths != null ? flightPaths.Count : -1)}");
        
        if (flightPaths.Count == 0)
        {
            Debug.LogError("[AirplaneManager] 유효한 비행 경로가 없습니다!");
            return;
        }
        
        // 최종 상태 요약 로그
        Debug.Log($"[AirplaneManager] ✅ 초기화 완료! 사용 가능한 경로: {flightPaths.Count}개");

        if (isScenarioControlled)
        {
            Debug.Log("[AirplaneManager] ScenarioManager가 활성화되어 자체 스폰 루틴을 시작하지 않습니다.");
        }
        else
        {
            Debug.Log("[AirplaneManager] 시나리오 모드가 아니므로 자체 스폰 루틴을 시작합니다.");
            spawnCoroutine = StartCoroutine(AirplaneSpawnRoutine());
        }
        
        if (enablePerformanceMode)
        {
            Debug.Log("[AirplaneManager] 성능 최적화 모드: 비행기 1대로 제한");
            maxSimultaneousAirplanes = 1;
            multipleAirplaneProbability = 0f; // 성능 모드에서는 편대 비행 비활성화
        }
    }

    public void StopSpawning()
    {
        if (spawnCoroutine != null)
        {
            StopCoroutine(spawnCoroutine);
            spawnCoroutine = null;
            Debug.Log("[AirplaneManager] 자체 스폰 루틴이 외부 매니저에 의해 중지되었습니다.");
        }
    }

    private void InitializeFlightPaths()
    {
        Debug.Log("[AirplaneManager] InitializeFlightPaths() 시작");
        
        // flightPaths가 null이면 초기화
        if (flightPaths == null)
        {
            Debug.Log("[AirplaneManager] flightPaths가 null이므로 새 리스트를 생성합니다.");
            flightPaths = new List<WaypointBezierPath>();
        }
        
        // Inspector에서 설정된 경로들 검증
        if (flightPaths.Count > 0)
        {
            Debug.Log($"[AirplaneManager] Inspector에서 설정된 경로 {flightPaths.Count}개를 검증합니다...");
            
            // null이거나 유효하지 않은 경로들을 찾아서 로그 출력
            for (int i = 0; i < flightPaths.Count; i++)
            {
                if (flightPaths[i] == null)
                {
                    Debug.LogWarning($"[AirplaneManager] flightPaths[{i}]가 null입니다! Inspector에서 경로를 다시 설정해주세요.");
                }
                else if (!flightPaths[i].IsValid())
                {
                    Debug.LogWarning($"[AirplaneManager] flightPaths[{i}] '{flightPaths[i].name}'가 유효하지 않습니다! (웨이포인트: {flightPaths[i].waypoints.Count}개)");
                }
                else
                {
                    Debug.Log($"[AirplaneManager] flightPaths[{i}] '{flightPaths[i].name}' 유효함 (웨이포인트: {flightPaths[i].waypoints.Count}개)");
                }
            }
            
            // null 항목 제거
            int originalCount = flightPaths.Count;
            flightPaths.RemoveAll(path => path == null || !path.IsValid());
            int removedCount = originalCount - flightPaths.Count;
            
            if (removedCount > 0)
            {
                Debug.LogWarning($"[AirplaneManager] {removedCount}개의 null/유효하지 않은 경로를 제거했습니다.");
            }
        }
        
        // 유효한 경로가 없으면 Scene에서 자동 검색
        if (flightPaths.Count == 0)
        {
            Debug.LogWarning("[AirplaneManager] 유효한 경로가 없습니다. Scene에서 자동으로 경로를 찾습니다...");
            FindAndValidatePaths();
        }
        
        Debug.Log($"[AirplaneManager] 최종 유효한 경로 개수: {flightPaths.Count}");
    }

    private void FindAndValidatePaths()
    {
        Debug.Log("[AirplaneManager] FindAndValidatePaths() 시작");
        
        // Scene에서 모든 WaypointBezierPath 컴포넌트 찾기
        WaypointBezierPath[] foundPaths = FindObjectsByType<WaypointBezierPath>(FindObjectsSortMode.None);
        Debug.Log($"[AirplaneManager] Scene에서 {foundPaths.Length}개의 WaypointBezierPath를 찾았습니다.");
        
        if (foundPaths.Length > 0)
        {
            // 기존 리스트 초기화 (Inspector 설정이 잘못된 경우를 대비)
            flightPaths.Clear();
            
            foreach (var path in foundPaths)
            {
                if (path == null)
                {
                    Debug.LogWarning("[AirplaneManager] 찾은 경로 중 null인 것이 있습니다. 건너뜁니다.");
                    continue;
                }
                
                if (path.IsValid()) // 유효한 경로만 추가
                {
                    flightPaths.Add(path);
                    Debug.Log($"[AirplaneManager] 유효한 경로 추가: {path.name} (웨이포인트: {path.waypoints.Count}개)");
                }
                else
                {
                    Debug.LogWarning($"[AirplaneManager] 유효하지 않은 경로 건너뜀: {path.name} (웨이포인트: {(path.waypoints != null ? path.waypoints.Count : 0)}개)");
                }
            }
            
            Debug.Log($"[AirplaneManager] 총 {flightPaths.Count}개의 유효한 경로를 찾았습니다.");
        }
        else
        {
            Debug.LogError("[AirplaneManager] Scene에서 WaypointBezierPath를 찾을 수 없습니다!");
            Debug.LogError("[AirplaneManager] 해결 방법:");
            Debug.LogError("1. Scene에 WaypointBezierPath 컴포넌트가 있는 GameObject를 생성하세요.");
            Debug.LogError("2. 또는 Inspector에서 Flight Paths 리스트에 수동으로 경로를 추가하세요.");
            Debug.LogError("3. 기존 경로 GameObject가 비활성화되어 있지 않은지 확인하세요.");
        }
    }

    private WaypointBezierPath GetRandomFlightPath()
    {
        // 경로가 없으면 에러 로그만 출력
        if (flightPaths == null || flightPaths.Count == 0)
        {
            Debug.LogError("[AirplaneManager] GetRandomFlightPath: flightPaths가 비어있습니다! Start()에서 경로를 찾지 못했습니다.");
            return null;
        }
            
        // 랜덤으로 경로 선택
        int randomIndex = Random.Range(0, flightPaths.Count);
        WaypointBezierPath selectedPath = flightPaths[randomIndex];
        
        if (selectedPath == null)
        {
            Debug.LogError($"[AirplaneManager] 선택된 경로가 null입니다! 인덱스: {randomIndex}. 경로 리스트를 다시 확인합니다.");
            // 문제가 있는 null 경로를 제거하고 다시 시도
            flightPaths.RemoveAt(randomIndex);
            return GetRandomFlightPath(); // 재귀 호출로 다른 경로 선택
        }
        
        Debug.Log($"[AirplaneManager] 선택된 경로: {selectedPath.name}");
        return selectedPath;
    }

    public GameObject SpawnSingleAirplane()
    {
        Debug.Log("[AirplaneManager] SpawnSingleAirplane 시작");
        
        // 1. 비행 경로 확인
        WaypointBezierPath selectedPath = GetRandomFlightPath();
        if (selectedPath == null)
        {
            Debug.LogError("[AirplaneManager] 비행 경로를 찾을 수 없습니다! flightPaths가 비어있거나 null입니다.");
            return null;
        }
        
        if (selectedPath.waypoints.Count < 2)
        {
            Debug.LogError($"[AirplaneManager] 선택된 경로의 웨이포인트가 부족합니다! 현재: {selectedPath.waypoints.Count}개, 필요: 2개 이상");
            return null;
        }
        
        Debug.Log($"[AirplaneManager] 비행 경로 선택 완료: {selectedPath.waypoints.Count}개 웨이포인트");

        // 2. 비행기 프리팹 확인
        if (airplanePrefabs == null || airplanePrefabs.Length == 0)
        {
            Debug.LogError("[AirplaneManager] 비행기 프리팹이 설정되지 않았습니다! Inspector에서 airplanePrefabs를 할당해주세요.");
            return null;
        }
        
        int prefabIndex = Random.Range(0, airplanePrefabs.Length);
        GameObject selectedPrefab = airplanePrefabs[prefabIndex];
        
        if (selectedPrefab == null)
        {
            Debug.LogError($"[AirplaneManager] 선택된 프리팹이 null입니다! 인덱스: {prefabIndex}");
            return null;
        }
        
        Debug.Log($"[AirplaneManager] 비행기 프리팹 선택 완료: {selectedPrefab.name}");

        // 3. 위치 및 회전 계산
        try
        {
            float startProgress = 0f;
            Vector3 startPos = selectedPath.GetPosition(startProgress);
            Vector3 nextPos = selectedPath.GetPosition(0.02f);
            Vector3 dir = (nextPos - startPos).normalized;

            Quaternion rot = Quaternion.LookRotation(dir);
            
            Debug.Log($"[AirplaneManager] 시작 위치: {startPos}, 방향: {dir}");

            // 4. 비행기 생성
            GameObject airplane = Instantiate(selectedPrefab, startPos, rot);
            airplane.name = $"Airplane_Scenario_{airplaneIndex++}";
            airplane.tag = "Airplane";

            // 5. 이동 컴포넌트 추가
            var mover = airplane.AddComponent<AirplaneBezierMover>();
            mover.path = selectedPath;
            mover.speed = Random.Range(minSpeed, maxSpeed);
            mover.loop = loop;

            activeAirplanes.Add(airplane);
            Debug.Log($"[AirplaneManager] 비행기 생성 성공: {airplane.name} (속도: {mover.speed:F1})");
            return airplane;
        }
        catch (System.Exception e)
        {
            Debug.LogError($"[AirplaneManager] 비행기 생성 중 예외 발생: {e.Message}\n{e.StackTrace}");
            return null;
        }
    }

    IEnumerator AirplaneSpawnRoutine()
    {
        while (true)
        {
            // 빈 하늘 상태를 더 자주 유지 (시스템 여유)
            if (Random.value < emptySkiesProbability)
            {
                Debug.Log("[AirplaneManager] Empty skies period (Performance optimization)");
                float emptyDuration = enablePerformanceMode ? 
                    Random.Range(minSpawnInterval * 1.5f, maxSpawnInterval * 1.5f) :
                    Random.Range(minSpawnInterval, maxSpawnInterval);
                yield return new WaitForSeconds(emptyDuration);
                continue;
            }

            // 현재 활성 비행기 수 확인
            CleanupDestroyedAirplanes();
            
            if (activeAirplanes.Count < maxSimultaneousAirplanes)
            {
                int airplanesToSpawn = 1;
                
                // 성능 모드가 아닐 때만 편대 비행 고려
                if (!enablePerformanceMode && activeAirplanes.Count == 0 && Random.value < multipleAirplaneProbability)
                {
                    airplanesToSpawn = Random.Range(2, Mathf.Min(3, maxSimultaneousAirplanes + 1)); // 4에서 3으로 줄임
                }

                for (int i = 0; i < airplanesToSpawn && activeAirplanes.Count < maxSimultaneousAirplanes; i++)
                {
                    SpawnAirplaneAlongPath(i);
                    
                    // 편대 비행시 더 긴 지연
                    if (i < airplanesToSpawn - 1)
                    {
                        yield return new WaitForSeconds(Random.Range(1f, 3f)); // 0.5-2초에서 1-3초로 늘림
                    }
                }
            }

            float waitTime = Random.Range(minSpawnInterval, maxSpawnInterval);
            if (enablePerformanceMode)
            {
                waitTime *= 1.2f; // 성능 모드에서는 20% 더 긴 간격
            }
            
            yield return new WaitForSeconds(waitTime);
        }
    }

    void SpawnAirplaneAlongPath(int formationIndex = 0)
    {
        WaypointBezierPath selectedPath = GetRandomFlightPath();
        if (selectedPath == null || selectedPath.waypoints.Count < 2) return;

        int prefabIndex = Random.Range(0, airplanePrefabs.Length);
        GameObject selectedPrefab = airplanePrefabs[prefabIndex];

        // 시작 위치 계산 (편대 비행 고려)
        float startProgress = 0f;
        Vector3 startPos = selectedPath.GetPosition(startProgress);
        Vector3 nextPos = selectedPath.GetPosition(0.02f);
        Vector3 dir = (nextPos - startPos).normalized;
        
        // 편대 오프셋 적용 (성능 모드에서는 단순화)
        if (formationIndex > 0 && !enablePerformanceMode)
        {
            Vector3 rightVector = Vector3.Cross(dir, Vector3.up).normalized;
            Vector3 formationOffset = rightVector * (formationIndex * formationSpacing);
            // 높이도 약간 다르게
            formationOffset.y += (formationIndex % 2 == 0 ? 1f : -1f) * formationIndex * 0.5f;
            startPos += formationOffset;
        }

        Quaternion rot = Quaternion.LookRotation(dir);

        GameObject airplane = Instantiate(selectedPrefab, startPos, rot);
        string nameFormat = enablePerformanceMode ? "Solo" : (formationIndex > 0 ? "Formation" : "Solo");
        airplane.name = $"Airplane_{airplaneIndex++}_{nameFormat}";
        airplane.tag = "Airplane";

        var mover = airplane.AddComponent<AirplaneBezierMover>();
        mover.path = selectedPath;
        mover.speed = Random.Range(minSpeed, maxSpeed);
        mover.loop = loop;

        // 편대 비행시 속도 약간 조정 (성능 모드에서는 생략)
        if (formationIndex > 0 && !enablePerformanceMode)
        {
            mover.speed *= Random.Range(0.95f, 1.05f); // ±5% 속도 변화
        }

        activeAirplanes.Add(airplane);
        
        string performanceNote = enablePerformanceMode ? " (Performance Mode)" : "";
        Debug.Log($"[AirplaneManager] Spawned airplane {airplane.name} (Speed: {mover.speed:F1}, Formation: {formationIndex}){performanceNote}");
    }

    void CleanupDestroyedAirplanes()
    {
        for (int i = activeAirplanes.Count - 1; i >= 0; i--)
        {
            if (activeAirplanes[i] == null)
            {
                activeAirplanes.RemoveAt(i);
            }
        }
        
        // 성능 모드에서는 정리 후 잠시 대기
        if (enablePerformanceMode && activeAirplanes.Count == 0)
        {
            System.GC.Collect();
        }
    }

    void OnDrawGizmosSelected()
    {
        if (flightPaths == null || flightPaths.Count == 0) return;

        foreach (var path in flightPaths)
        {
            if (path != null && path.waypoints.Count > 1)
            {
                Gizmos.color = Color.green;
                for (int i = 0; i < path.waypoints.Count - 1; i++)
                {
                    if (path.waypoints[i] != null && path.waypoints[i + 1] != null)
                    {
                        Gizmos.DrawLine(path.waypoints[i].position, path.waypoints[i + 1].position);
                    }
                }
                
                // 편대 스폰 위치 표시 (성능 모드에서는 단순화)
                if (!enablePerformanceMode)
                {
                    Vector3 startPos = path.GetPosition(0f);
                    Vector3 dir = (path.GetPosition(0.02f) - startPos).normalized;
                    Vector3 rightVector = Vector3.Cross(dir, Vector3.up).normalized;
                    
                    Gizmos.color = Color.yellow;
                    for (int i = 1; i <= maxSimultaneousAirplanes; i++)
                    {
                        Vector3 formationPos = startPos + rightVector * (i * formationSpacing);
                        Gizmos.DrawSphere(formationPos, 1.5f);
                    }
                }
            }
        }
    }

    // 경로 초기화를 위한 public 메서드
    public bool InitializePaths()
    {
        if (flightPaths == null || flightPaths.Count == 0)
        {
            FindAndValidatePaths();
            return flightPaths != null && flightPaths.Count > 0;
        }
        return true;
    }

    // 경로 상태 확인을 위한 public 메서드
    public bool HasValidPaths()
    {
        return flightPaths != null && flightPaths.Count > 0;
    }
}

