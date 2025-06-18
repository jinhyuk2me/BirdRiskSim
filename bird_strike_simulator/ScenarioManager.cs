using UnityEngine;
using UnityEngine.InputSystem; // 새 Input System 추가
using System.Collections;
using System.Collections.Generic;

public class ScenarioManager : MonoBehaviour
{
    [Header("Control Settings")]
    [Tooltip("체크하면 개별 매니저의 무작위 생성을 끄고, 이 매니저가 통제하는 시나리오를 실행합니다.")]
    public bool enableScenarioMode = true;

    [Header("🎯 Independent Control Settings")]
    [Tooltip("비행기 생성 활성화/비활성화")]
    public bool enableAirplaneSpawn = true;
    [Tooltip("새 무리 생성 활성화/비활성화")]
    public bool enableFlockSpawn = true;
    [Tooltip("경로 추적 모드 (새 무리 비활성화, 비행기만 생성)")]
    public bool routeTrackingMode = false;

    [Header("Manager References")]
    [Tooltip("Scene에 있는 AirplaneManager를 여기에 드래그하세요")]
    public AirplaneManager airplaneManager;
    [Tooltip("Scene에 있는 FlockManager를 여기에 드래그하세요")]
    public FlockManager flockManager;

    [Header("Scenario Settings")]
    [Tooltip("시나리오 시작 전 대기 시간")]
    [SerializeField] private float airplaneSpawnDelay = 2f;
    [Tooltip("시나리오 간 대기 시간")]
    [SerializeField] private float cooldownBetweenScenarios = 5f;
    [Tooltip("비행기 경로 근처에 새 무리를 생성할 때의 최대 거리")]
    [SerializeField] private float maxDistanceFromPath = 20f;

    [Header("🔧 Runtime Controls")]
    [Tooltip("런타임에서 비행기 생성을 토글할 수 있습니다 (키: A)")]
    public bool enableRuntimeAirplaneToggle = true;
    [Tooltip("런타임에서 새 무리 생성을 토글할 수 있습니다 (키: F)")]
    public bool enableRuntimeFlockToggle = true;

    // 현재 활성화된 객체들
    private GameObject currentAirplane;
    private GameObject currentFlock;

    void Awake()
    {
        if (!enableScenarioMode) return;
        
        if (airplaneManager == null || flockManager == null)
        {
            Debug.LogError("[ScenarioManager] AirplaneManager 또는 FlockManager를 찾을 수 없습니다!");
            Debug.LogError($"[ScenarioManager] AirplaneManager: {(airplaneManager != null ? "OK" : "NULL")}");
            Debug.LogError($"[ScenarioManager] FlockManager: {(flockManager != null ? "OK" : "NULL")}");
            enabled = false; // 이 스크립트를 비활성화
            return;
        }

        // 경로 추적 모드 자동 설정
        if (routeTrackingMode)
        {
            enableAirplaneSpawn = true;
            enableFlockSpawn = false;
            Debug.Log("[ScenarioManager] 🎯 경로 추적 모드 활성화: 비행기만 생성, 새 무리 비활성화");
        }

        // 각 매니저에게 시나리오 모드임을 알림 (Start()보다 먼저 실행됨)
        airplaneManager.isScenarioControlled = true;
        flockManager.isScenarioControlled = true;
        Debug.Log("[ScenarioManager] 각 매니저를 시나리오 제어 모드로 설정했습니다.");
        Debug.Log($"[ScenarioManager] 제어 설정 - 비행기: {enableAirplaneSpawn}, 새 무리: {enableFlockSpawn}");
    }

    void Start()
    {
        if (!enableScenarioMode)
        {
            Debug.Log("[ScenarioManager] 시나리오 모드가 비활성화되어 있습니다. 각 Manager가 자체적으로 동작합니다.");
            return;
        }

        if (airplaneManager == null || flockManager == null)
        {
            Debug.LogError("[ScenarioManager] AirplaneManager 또는 FlockManager가 연결되지 않았습니다!");
            return;
        }

        Debug.Log("[ScenarioManager] 시나리오 모드 시작. 선택된 객체 생성을 통제합니다.");
        StartCoroutine(RunScenarios());
    }

    void Update()
    {
        // Input System 안전성 체크
        if (Keyboard.current == null) return;

        // 런타임 토글 컨트롤
        if (enableRuntimeAirplaneToggle && Keyboard.current.aKey.wasPressedThisFrame)
        {
            enableAirplaneSpawn = !enableAirplaneSpawn;
            Debug.Log($"[ScenarioManager] 🔄 비행기 생성 토글: {enableAirplaneSpawn}");
        }

        if (enableRuntimeFlockToggle && Keyboard.current.fKey.wasPressedThisFrame)
        {
            enableFlockSpawn = !enableFlockSpawn;
            Debug.Log($"[ScenarioManager] 🔄 새 무리 생성 토글: {enableFlockSpawn}");
            
            // 새 무리 비활성화 시 기존 새 무리 제거
            if (!enableFlockSpawn && currentFlock != null)
            {
                flockManager.DeregisterFlock(currentFlock);
                Destroy(currentFlock);
                currentFlock = null;
                Debug.Log("[ScenarioManager] 기존 새 무리 제거됨");
            }
        }

        // 경로 추적 모드 토글 (키: P)
        if (Keyboard.current.pKey.wasPressedThisFrame)
        {
            routeTrackingMode = !routeTrackingMode;
            if (routeTrackingMode)
            {
                enableAirplaneSpawn = true;
                enableFlockSpawn = false;
                // 기존 새 무리 제거
                if (currentFlock != null)
                {
                    flockManager.DeregisterFlock(currentFlock);
                    Destroy(currentFlock);
                    currentFlock = null;
                }
                Debug.Log("[ScenarioManager] 🎯 경로 추적 모드 ON: 새 무리 비활성화");
            }
            else
            {
                enableFlockSpawn = true;
                Debug.Log("[ScenarioManager] 🎯 경로 추적 모드 OFF: 새 무리 활성화");
            }
        }
    }

    IEnumerator RunScenarios()
    {
        int scenarioCount = 1;
        while (true)
        {
            Debug.Log($"---< Scenario {scenarioCount} Start >---");
            Debug.Log($"[ScenarioManager] 활성 설정 - 비행기: {enableAirplaneSpawn}, 새 무리: {enableFlockSpawn}");

            // 1. 시나리오 시작 전 대기
            yield return new WaitForSeconds(airplaneSpawnDelay);
            
            // 2. 비행기 생성 (활성화된 경우만)
            if (enableAirplaneSpawn)
            {
                currentAirplane = airplaneManager.SpawnSingleAirplane();
                if (currentAirplane == null)
                {
                    Debug.LogError("[ScenarioManager] 비행기 생성에 실패했습니다.");
                    yield return new WaitForSeconds(cooldownBetweenScenarios);
                    continue;
                }

                // 시나리오 모드에서는 비행기의 자동 소멸 비활성화
                var airplaneMover = currentAirplane.GetComponent<AirplaneBezierMover>();
                if (airplaneMover != null)
                {
                    airplaneMover.disableAutoDestroy = true;
                }

                Debug.Log("✈️ 비행기 생성 완료");
            }
            else
            {
                Debug.Log("✈️ 비행기 생성 건너뜀 (비활성화됨)");
            }

            // 3. 새 무리 생성 (활성화된 경우만)
            if (enableFlockSpawn && currentAirplane != null)
            {
                Vector3 flockSpawnPos = GetPositionNearAirplanePath();
                currentFlock = flockManager.SpawnSingleFlock(flockSpawnPos);
                if (currentFlock == null)
                {
                    Debug.LogWarning("[ScenarioManager] 새 무리 생성에 실패했습니다.");
                }
                else
                {
                    // 시나리오 모드에서는 새 무리의 자동 소멸 비활성화
                    var flockMover = currentFlock.GetComponent<FlockMover>();
                    if (flockMover != null)
                    {
                        flockMover.disableAutoDestroy = true;
                    }
                    Debug.Log("🐦 새 무리 생성 완료");
                }
            }
            else if (enableFlockSpawn)
            {
                Debug.Log("🐦 새 무리 생성 건너뜀 (비행기가 없음)");
            }
            else
            {
                Debug.Log("🐦 새 무리 생성 건너뜀 (비활성화됨)");
            }

            // 4. 비행기가 있는 경우 경로 완주까지 대기
            if (currentAirplane != null)
            {
                var airplaneMover = currentAirplane.GetComponent<AirplaneBezierMover>();
                Debug.Log("시나리오 진행 중... 비행기가 경로를 마칠 때까지 대기합니다.");
                
                while (currentAirplane != null && airplaneMover != null)
                {
                    if (airplaneMover.GetProgress() >= 0.99f)
                    {
                        Debug.Log("비행기가 경로를 완주했습니다.");
                        break;
                    }
                    yield return null;
                }
            }
            else
            {
                // 비행기가 없으면 고정 시간 대기
                Debug.Log("비행기가 없으므로 고정 시간 대기합니다.");
                yield return new WaitForSeconds(10f);
            }

            // 5. 객체들 정리
            if (currentAirplane != null)
            {
                Destroy(currentAirplane);
                currentAirplane = null;
                Debug.Log("✈️ 비행기 제거 완료");
            }
            
            if (currentFlock != null)
            {
                flockManager.DeregisterFlock(currentFlock);
                Destroy(currentFlock);
                currentFlock = null;
                Debug.Log("🐦 새 무리 제거 완료");
            }

            Debug.Log($"---< Scenario {scenarioCount} End >---");

            // 6. 다음 시나리오까지 대기
            yield return new WaitForSeconds(cooldownBetweenScenarios);
            scenarioCount++;
        }
    }

    private Vector3 GetPositionNearAirplanePath()
    {
        if (currentAirplane == null) return Vector3.zero;

        var airplaneMover = currentAirplane.GetComponent<AirplaneBezierMover>();
        if (airplaneMover == null || airplaneMover.path == null) return Vector3.zero;

        // 비행기 경로 근처에 새 무리 생성 (카메라 의존성 제거)
        return GetFallbackPosition(airplaneMover);
    }

    private Vector3 GetFallbackPosition(AirplaneBezierMover airplaneMover)
    {
        // 비행기 경로의 중간 지점 근처에 생성
        Vector3 pathCenter = airplaneMover.path.GetPosition(0.5f);
        
        Vector3 randomDirection = new Vector3(
            Random.Range(-1f, 1f),
            Random.Range(-0.5f, 0.5f), // Y축은 작은 범위로 제한
            Random.Range(-1f, 1f)
        ).normalized;
        
        return pathCenter + randomDirection * Random.Range(0f, maxDistanceFromPath * 0.5f);
    }

    // 🔧 유틸리티 함수들
    
    /// <summary>
    /// 경로 추적 모드를 프로그래밍 방식으로 설정
    /// </summary>
    public void SetRouteTrackingMode(bool enabled)
    {
        routeTrackingMode = enabled;
        if (enabled)
        {
            enableAirplaneSpawn = true;
            enableFlockSpawn = false;
            // 기존 새 무리 제거
            if (currentFlock != null)
            {
                flockManager.DeregisterFlock(currentFlock);
                Destroy(currentFlock);
                currentFlock = null;
            }
            Debug.Log("[ScenarioManager] 🎯 경로 추적 모드 설정됨 (프로그래밍)");
        }
        else
        {
            enableFlockSpawn = true;
            Debug.Log("[ScenarioManager] 🎯 경로 추적 모드 해제됨 (프로그래밍)");
        }
    }

    /// <summary>
    /// 비행기 생성 활성화/비활성화
    /// </summary>
    public void SetAirplaneSpawn(bool enabled)
    {
        enableAirplaneSpawn = enabled;
        Debug.Log($"[ScenarioManager] ✈️ 비행기 생성 설정: {enabled}");
    }

    /// <summary>
    /// 새 무리 생성 활성화/비활성화
    /// </summary>
    public void SetFlockSpawn(bool enabled)
    {
        enableFlockSpawn = enabled;
        if (!enabled && currentFlock != null)
        {
            flockManager.DeregisterFlock(currentFlock);
            Destroy(currentFlock);
            currentFlock = null;
            Debug.Log("[ScenarioManager] 기존 새 무리 제거됨 (프로그래밍)");
        }
        Debug.Log($"[ScenarioManager] 🐦 새 무리 생성 설정: {enabled}");
    }

    /// <summary>
    /// 현재 활성 객체들을 즉시 제거
    /// </summary>
    public void ClearCurrentObjects()
    {
        if (currentAirplane != null)
        {
            Destroy(currentAirplane);
            currentAirplane = null;
            Debug.Log("[ScenarioManager] ✈️ 현재 비행기 제거됨");
        }
        
        if (currentFlock != null)
        {
            flockManager.DeregisterFlock(currentFlock);
            Destroy(currentFlock);
            currentFlock = null;
            Debug.Log("[ScenarioManager] 🐦 현재 새 무리 제거됨");
        }
    }

    /// <summary>
    /// 현재 상태 정보 출력
    /// </summary>
    [ContextMenu("Show Current Status")]
    public void ShowCurrentStatus()
    {
        Debug.Log("=== ScenarioManager 현재 상태 ===");
        Debug.Log($"시나리오 모드: {enableScenarioMode}");
        Debug.Log($"경로 추적 모드: {routeTrackingMode}");
        Debug.Log($"비행기 생성: {enableAirplaneSpawn}");
        Debug.Log($"새 무리 생성: {enableFlockSpawn}");
        Debug.Log($"현재 비행기: {(currentAirplane != null ? currentAirplane.name : "없음")}");
        Debug.Log($"현재 새 무리: {(currentFlock != null ? currentFlock.name : "없음")}");
        Debug.Log("=== 컨트롤 키 ===");
        Debug.Log("A: 비행기 생성 토글");
        Debug.Log("F: 새 무리 생성 토글");
        Debug.Log("P: 경로 추적 모드 토글");
        Debug.Log("===============================");
    }

    void OnGUI()
    {
        if (!enableScenarioMode) return;

        // 화면 왼쪽 상단에 상태 표시
        GUILayout.BeginArea(new Rect(10, 10, 280, 150));
        GUILayout.BeginVertical("box");
        
        // 안전한 스타일 사용
        GUIStyle titleStyle = GUI.skin.label;
        titleStyle.fontStyle = FontStyle.Bold;
        
        GUILayout.Label("🎮 ScenarioManager 상태", titleStyle);
        GUILayout.Label($"경로 추적 모드: {(routeTrackingMode ? "ON" : "OFF")}");
        GUILayout.Label($"비행기 생성: {(enableAirplaneSpawn ? "ON" : "OFF")}");
        GUILayout.Label($"새 무리 생성: {(enableFlockSpawn ? "ON" : "OFF")}");
        
        GUILayout.Space(5);
        GUILayout.Label("컨트롤 키:", titleStyle);
        GUILayout.Label("A: 비행기 토글, F: 새 무리 토글");
        GUILayout.Label("P: 경로 추적 모드 토글");
        
        GUILayout.EndVertical();
        GUILayout.EndArea();
    }
} 