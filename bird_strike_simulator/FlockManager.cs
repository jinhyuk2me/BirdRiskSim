using UnityEngine;
using System.Collections;
using System.Collections.Generic;

public class FlockManager : MonoBehaviour
{
    [Header("References")]
    public BirdSpawner birdSpawner;

    [Header("Flock Control - Performance Optimized")]
    [Range(1, 4)]
    public int minFlockCountPerCycle = 2;
    [Range(1, 4)] 
    public int maxFlockCountPerCycle = 3;  // 최대 생성 수 증가
    
    [Range(5f, 15f)]
    public float minSpreadDelay = 8f;     // 더 긴 간격
    [Range(5f, 15f)]
    public float maxSpreadDelay = 12f;
    
    [Range(8f, 20f)]
    public float minHoldDuration = 10f;    // 더 긴 지속시간
    [Range(8f, 20f)]
    public float maxHoldDuration = 15f;

    [Header("Spawn Pattern Variation")]
    public bool enableRandomSpawnAreas = true;
    public bool enableDynamicSpawnGeneration = true; // 동적 스폰 위치 생성
    
    // ✅ 새로운 스프레드 컨트롤 설정 추가
    [Header("Global Flock Spread Control")]
    [Range(0.1f, 5.0f)]
    [Tooltip("전체 flock들의 퍼짐 범위 배율 (1.0 = 기본, 높을수록 더 넓은 지역에 퍼짐)")]
    public float globalFlockSpreadMultiplier = 1.0f;
    
    [Tooltip("BirdSpawner의 포메이션 설정을 오버라이드할지 여부")]
    public bool overrideBirdSpawnerSettings = false;
    
    [Tooltip("오버라이드 시 사용할 포메이션")]
    public BirdSpawner.FlockFormation forceFormation = BirdSpawner.FlockFormation.Random;
    
    [Range(0.2f, 3.0f)]
    [Tooltip("오버라이드 시 사용할 스프레드 배율")]
    public float forceSpreadMultiplier = 1.0f;
    
    public Vector3[] alternativeSpawnCenters = {
        new Vector3(50, 40, 150),   // 왼쪽 앞
        new Vector3(120, 60, 250),  // 오른쪽 뒤
        new Vector3(200, 30, 180),  // 오른쪽 중간
        new Vector3(-20, 50, 100),  // 왼쪽 뒤
        new Vector3(150, 80, 50),   // 오른쪽 앞 높이
        new Vector3(80, 25, 300),   // 중간 멀리
        new Vector3(30, 70, 120),   // 왼쪽 중간 높이
        new Vector3(180, 40, 80)    // 오른쪽 가까이
    };

    [Header("Background Data Generation")]
    [Range(0f, 0.4f)]
    public float emptyFrameProbability = 0.25f; // 25% 빈 프레임 (성능 여유)

    [Header("Performance Settings")]
    [Range(0.5f, 3f)]
    public float cycleRestTime = 1.5f;    // 사이클 간 휴식 시간 추가
    public bool enablePerformanceMode = true;

    [Header("Safety Limits")]
    public int maxConcurrentFlocks = 5;     // 동시 최대 flock 수 증가
    public bool enableFlockCountLimit = true;
    [HideInInspector]
    public bool isScenarioControlled = false;
    
    [Header("Enhanced Monitoring")]
    public bool enableDetailedLogging = false;  // 상세 로그 토글
    public float memoryCheckInterval = 30f;     // 메모리 체크 간격

    // 🔧 성능 최적화: 활성 flock 추적 시스템
    private HashSet<GameObject> activeFlocks = new HashSet<GameObject>();
    private List<GameObject> currentFlocks = new List<GameObject>();
    private int cycleCount = 0;
    private Coroutine flockRoutine;

    void Start()
    {
        if (isScenarioControlled)
        {
            Debug.Log("[FlockManager] ScenarioManager가 활성화되어 자체 스폰 및 모니터링 루틴을 시작하지 않습니다.");
        }
        else
        {
            Debug.Log("[FlockManager] 시나리오 모드가 아니므로 자체 스폰 루틴을 시작합니다.");
            flockRoutine = StartCoroutine(FlockRoutine());
            if (enablePerformanceMode)
            {
                StartCoroutine(PerformanceMonitor());
            }
        }

        if (enablePerformanceMode)
        {
            Debug.Log("[FlockManager] 성능 최적화 모드 활성화됨");
            maxFlockCountPerCycle = Mathf.Min(maxFlockCountPerCycle, 2);
            maxConcurrentFlocks = Mathf.Min(maxConcurrentFlocks, 2); // 더 엄격한 제한
        }
        
        Debug.Log($"[FlockManager] 초기 설정 - 최대 동시 flock: {maxConcurrentFlocks}, 사이클당 최대: {maxFlockCountPerCycle}");
    }

    /// <summary>
    /// 성능 모니터링 코루틴
    /// </summary>
    IEnumerator PerformanceMonitor()
    {
        while (true)
        {
            yield return new WaitForSeconds(memoryCheckInterval);
            
            // 죽은 flock 정리
            CleanupDeadFlocks();
            
            // 메모리 상태 체크
            if (enableDetailedLogging)
            {
                long memoryUsage = System.GC.GetTotalMemory(false) / (1024 * 1024); // MB
                Debug.Log($"[FlockManager] 메모리 사용량: {memoryUsage}MB, 활성 flock: {activeFlocks.Count}");
            }
            
            // 극한 상황에서만 강제 정리
            if (activeFlocks.Count > maxConcurrentFlocks * 2)
            {
                Debug.LogWarning("[FlockManager] 🚨 긴급 flock 정리 실행");
                ForceCleanupExcessFlocks();
            }
        }
    }

    IEnumerator FlockRoutine()
    {
        while (true)
        {
            CleanupDeadFlocks();
            
            if (Random.value < emptyFrameProbability)
            {
                if (enableDetailedLogging)
                    Debug.Log($"[FlockManager] Cycle {cycleCount}: Empty frame for background data");
                yield return new WaitForSeconds(Random.Range(5f, 10f)); // 더 긴 대기
                cycleCount++;
                continue;
            }

            int flockCount = Random.Range(minFlockCountPerCycle, maxFlockCountPerCycle + 1);
            float spreadDelay = Random.Range(minSpreadDelay, maxSpreadDelay);
            float holdDuration = Random.Range(minHoldDuration, maxHoldDuration);

            // 성능 모드에서도 더 많은 무리 허용
            if (enablePerformanceMode)
            {
                flockCount = Mathf.Min(flockCount, 2); // 한 번에 2개까지 허용
                spreadDelay *= 0.8f; // 약간 더 짧게
            }

            yield return StartCoroutine(SpawnFlocks(flockCount));
            yield return new WaitForSeconds(spreadDelay);

            yield return new WaitForSeconds(holdDuration);
            HandleFlockCleanup();

            cycleCount++;
            
            // 사이클 간 휴식 시간 조정
            yield return new WaitForSeconds(cycleRestTime * 1.5f);
        }
    }

    private IEnumerator SpawnFlocks(int flockCount)
    {
        // 🔧 성능 최적화: HashSet 사용으로 빠른 카운트 체크
        CleanupDeadFlocks(); // 먼저 죽은 것들 정리
        
        if (enableFlockCountLimit && activeFlocks.Count >= maxConcurrentFlocks)
        {
            Debug.LogWarning($"[FlockManager] 최대 flock 수 도달 ({activeFlocks.Count}/{maxConcurrentFlocks}). 생성 건너뜀");
            yield break; // ✅ 수정: return → yield break
        }
        
        // 실제 생성할 수를 제한
        int allowedCount = maxConcurrentFlocks - activeFlocks.Count;
        flockCount = Mathf.Min(flockCount, allowedCount);
        
        if (flockCount <= 0)
        {
            Debug.Log("[FlockManager] 생성 가능한 flock 수가 0개. 건너뜀");
            yield break;
        }
        
        currentFlocks.Clear();

        // 다양한 스폰 지역 사용
        Vector3 baseSpawnCenter = birdSpawner.spawnAreaCenter;
        
        if (enableRandomSpawnAreas && Random.value < 0.7f) // 70% 확률로 다양한 위치 사용
        {
            if (enableDynamicSpawnGeneration && Random.value < 0.6f) // 60% 확률로 동적 생성
            {
                // 카메라 주변의 무작위 위치 생성
                Camera mainCamera = Camera.main;
                if (mainCamera != null)
                {
                    Vector3 cameraPos = mainCamera.transform.position;
                    Vector3 cameraForward = mainCamera.transform.forward;
                    Vector3 cameraRight = mainCamera.transform.right;
                    
                    // 카메라 주변 원형으로 스폰 위치 생성
                    float angle = Random.Range(0f, 360f) * Mathf.Deg2Rad;
                    float distance = Random.Range(100f, 400f);
                    float height = Random.Range(20f, 100f);
                    
                    baseSpawnCenter = cameraPos + 
                        new Vector3(
                            Mathf.Cos(angle) * distance,
                            height,
                            Mathf.Sin(angle) * distance
                        );
                    
                    Debug.Log($"[FlockManager] Dynamic spawn at angle {angle * Mathf.Rad2Deg:F0}°, distance {distance:F0}m, height {height:F0}m");
                }
            }
            else if (alternativeSpawnCenters.Length > 0)
        {
                // 기존 고정 위치 사용
            baseSpawnCenter = alternativeSpawnCenters[Random.Range(0, alternativeSpawnCenters.Length)];
            }
        }

        for (int i = 0; i < flockCount; i++)
        {
            // ✅ 전역 스프레드 배율 적용하여 더 넓은 범위에서 스폰
            Vector3 center = baseSpawnCenter + new Vector3(
                Random.Range(-birdSpawner.spawnAreaSize.x * 0.8f * globalFlockSpreadMultiplier, 
                            birdSpawner.spawnAreaSize.x * 0.8f * globalFlockSpreadMultiplier),
                Random.Range(-birdSpawner.spawnAreaSize.y * 0.6f, birdSpawner.spawnAreaSize.y * 0.6f),
                Random.Range(-birdSpawner.spawnAreaSize.z * 0.8f * globalFlockSpreadMultiplier, 
                            birdSpawner.spawnAreaSize.z * 0.8f * globalFlockSpreadMultiplier)
            );

            // ✅ BirdSpawner 설정 임시 오버라이드
            if (overrideBirdSpawnerSettings)
            {
                var originalFormation = birdSpawner.preferredFormation;
                var originalSpread = birdSpawner.globalSpreadMultiplier;
                
                birdSpawner.preferredFormation = forceFormation;
                birdSpawner.globalSpreadMultiplier = forceSpreadMultiplier;
                
                GameObject flock = birdSpawner.SpawnFlock(center);
                
                // 설정 복원
                birdSpawner.preferredFormation = originalFormation;
                birdSpawner.globalSpreadMultiplier = originalSpread;
                
                if (flock != null)
                {
                    currentFlocks.Add(flock);
                    activeFlocks.Add(flock);
                }
            }
            else
            {
            GameObject flock = birdSpawner.SpawnFlock(center);
            if (flock != null)
            {
                currentFlocks.Add(flock);
                activeFlocks.Add(flock); // 🔧 추적 시스템에 추가
                }
            }

            // 플록 간 더 긴 지연 (시스템 부하 분산)
            if (i < flockCount - 1)
            {
                float delay = enablePerformanceMode ? 
                    Random.Range(0.8f, 1.8f) :  // 성능 모드: 더 긴 지연
                    Random.Range(0.1f, 0.5f);   // 일반 모드
                yield return new WaitForSeconds(delay);
            }
        }

        string performanceInfo = enablePerformanceMode ? " (성능 모드)" : "";
        string spreadInfo = globalFlockSpreadMultiplier != 1.0f ? $" (스프레드: {globalFlockSpreadMultiplier:F1}x)" : "";
        string overrideInfo = overrideBirdSpawnerSettings ? $" (오버라이드: {forceFormation}, {forceSpreadMultiplier:F1}x)" : "";
        Debug.Log($"[FlockManager] Cycle {cycleCount}: {flockCount}개 flock 생성 완료 (총 활성: {activeFlocks.Count}/{maxConcurrentFlocks}){performanceInfo}{spreadInfo}{overrideInfo}");
    }

    private void HandleFlockCleanup()
    {
        int cleanedCount = 0;
        foreach (GameObject flock in currentFlocks)
        {
            if (flock != null) 
            {
                activeFlocks.Remove(flock); // 🔧 추적에서 제거
                Destroy(flock);
                cleanedCount++;
            }
        }
        currentFlocks.Clear();
        
        if (enableDetailedLogging && cleanedCount > 0)
        {
            Debug.Log($"[FlockManager] {cleanedCount}개 flock 정리 완료. 남은 활성 flock: {activeFlocks.Count}");
        }
        
        // 🔧 최적화: 조건부 가비지 컬렉션 (더 신중하게)
        if (enablePerformanceMode && cycleCount % 10 == 0) // 10사이클마다만
        {
            System.GC.Collect();
        }
    }

    /// <summary>
    /// 죽은 flock 오브젝트들을 추적에서 제거
    /// </summary>
    private void CleanupDeadFlocks()
    {
        // 🔧 null이 된 GameObject들을 HashSet에서 제거
        activeFlocks.RemoveWhere(flock => flock == null);
    }

    /// <summary>
    /// 긴급 상황에서 과도한 flock들을 강제 정리
    /// </summary>
    private void ForceCleanupExcessFlocks()
    {
        var flocksToRemove = new List<GameObject>();
        int removeCount = activeFlocks.Count - maxConcurrentFlocks;
        
        foreach (GameObject flock in activeFlocks)
        {
            if (flock != null && flocksToRemove.Count < removeCount)
            {
                flocksToRemove.Add(flock);
            }
        }
        
        foreach (GameObject flock in flocksToRemove)
        {
            activeFlocks.Remove(flock);
            if (flock != null) Destroy(flock);
        }
        
        Debug.LogWarning($"[FlockManager] 긴급 정리: {flocksToRemove.Count}개 flock 제거됨");
    }

    /// <summary>
    /// Inspector에서 현재 상태 확인용
    /// </summary>
    [ContextMenu("Show Flock Status")]
    void ShowFlockStatus()
    {
        CleanupDeadFlocks();
        Debug.Log($"[FlockManager] 현재 상태:");
        Debug.Log($"  - 활성 flock: {activeFlocks.Count}/{maxConcurrentFlocks}");
        Debug.Log($"  - 사이클 수: {cycleCount}");
        Debug.Log($"  - 성능 모드: {enablePerformanceMode}");
        Debug.Log($"  - 상세 로깅: {enableDetailedLogging}");
        Debug.Log($"  - 전역 스프레드 배율: {globalFlockSpreadMultiplier:F1}x");
        Debug.Log($"  - 설정 오버라이드: {overrideBirdSpawnerSettings}");
        if (overrideBirdSpawnerSettings)
        {
            Debug.Log($"    → 강제 포메이션: {forceFormation}");
            Debug.Log($"    → 강제 스프레드: {forceSpreadMultiplier:F1}x");
        }
    }

    void OnDrawGizmosSelected()
    {
        if (alternativeSpawnCenters != null && birdSpawner != null)
        {
            Gizmos.color = Color.red;
            foreach (Vector3 center in alternativeSpawnCenters)
            {
                Gizmos.DrawWireCube(center, birdSpawner.spawnAreaSize);
            }
            
            // 성능 정보 표시
            if (enablePerformanceMode)
            {
                Gizmos.color = Color.green;
                Gizmos.DrawWireSphere(birdSpawner.spawnAreaCenter + Vector3.up * 10f, 5f);
            }
        }
    }

    // 외부에서 스포닝을 중지시킬 함수
    public void StopSpawning()
    {
        if (flockRoutine != null)
        {
            StopCoroutine(flockRoutine);
            flockRoutine = null;
            Debug.Log("[FlockManager] 자체 스폰 루틴이 외부 매니저에 의해 중지되었습니다.");
        }
    }

    // 외부에서 단일 새 무리를 생성할 함수
    public GameObject SpawnSingleFlock(Vector3 position)
    {
        if (birdSpawner == null) return null;
        
        GameObject flock = birdSpawner.SpawnFlock(position);
        if (flock != null)
        {
            activeFlocks.Add(flock);
            Debug.Log($"[FlockManager] 외부 제어에 의해 단일 새 무리 생성: {flock.name}");
        }
        return flock;
    }

    public void DeregisterFlock(GameObject flock)
    {
        if (flock != null && activeFlocks.Contains(flock))
        {
            activeFlocks.Remove(flock);
            Debug.Log($"[FlockManager] 외부 제어에 의해 비활성화된 flock: {flock.name}. 현재 활성: {activeFlocks.Count}");
        }
    }
}
