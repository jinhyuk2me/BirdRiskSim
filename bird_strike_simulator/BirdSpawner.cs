using UnityEngine;

public class BirdSpawner : MonoBehaviour
{
    [Header("Prefabs")]
    public GameObject[] birdPrefabs;

    [Header("Flock Settings - Performance Optimized")]
    [Range(3, 10)]
    public int minBirdCount = 5;
    [Range(10, 40)]
    public int maxBirdCount = 25;  // 60마리에서 25마리로 줄임
    
    [Range(5f, 20f)]
    public float minSpawnRadius = 8f;
    [Range(5f, 20f)]
    public float maxSpawnRadius = 15f;  // 20에서 15로 줄임

    [Header("Spawn Area")]
    public Vector3 spawnAreaCenter = new Vector3(90, 20, 41);
    public Vector3 spawnAreaSize = new Vector3(60, 20, 60);

    [Header("Movement Diversity")]
    [Range(5f, 25f)]
    public float minMoveSpeed = 8f;
    [Range(5f, 25f)]
    public float maxMoveSpeed = 20f;  // 25에서 20으로 줄임
    
    [Range(0f, 1f)]
    public float groundFlockProbability = 0.1f; // 10% 확률로 지상 근처 이동

    [Header("Formation Patterns")]
    public bool enableFormationVariation = true;
    public enum FlockFormation { Random, Tight, Spread, Line, VShape }

    // ✅ 새로운 설정 추가
    [Header("Flock Spread Control")]
    [Tooltip("포메이션 타입을 직접 선택 (Random이면 자동으로 랜덤 선택)")]
    public FlockFormation preferredFormation = FlockFormation.Random;
    
    [Range(0.2f, 3.0f)]
    [Tooltip("전체적인 새들 퍼짐 정도 (1.0 = 기본, 낮을수록 촘촘, 높을수록 넓게)")]
    public float globalSpreadMultiplier = 1.0f;
    
    [Range(0.1f, 2.0f)]
    [Tooltip("Tight 포메이션 크기 조절")]
    public float tightFormationScale = 0.4f;
    
    [Range(0.5f, 3.0f)]
    [Tooltip("Spread 포메이션 크기 조절")]
    public float spreadFormationScale = 1.2f;
    
    [Range(0.8f, 2.5f)]
    [Tooltip("Line/VShape 포메이션 크기 조절")]
    public float lineFormationScale = 1.5f;

    [Header("Performance Settings")]
    public bool enablePerformanceMode = true;
    [Range(5, 20)]
    public int maxBirdsInPerformanceMode = 15;  // 성능 모드시 최대 새 수 제한

    public GameObject SpawnFlock(Vector3 center)
    {
        int birdCount = Random.Range(minBirdCount, maxBirdCount + 1);
        
        // 성능 모드에서는 새 수를 제한
        if (enablePerformanceMode)
        {
            birdCount = Mathf.Min(birdCount, maxBirdsInPerformanceMode);
        }
        
        float spawnRadius = Random.Range(minSpawnRadius, maxSpawnRadius);
        GameObject selectedPrefab = birdPrefabs[Random.Range(0, birdPrefabs.Length)];

        GameObject flockGroup = new GameObject($"FlockGroup_{Time.frameCount}");
        flockGroup.transform.position = center;
        flockGroup.tag = "Flock";

        // ✅ FlockMover 추가 with enhanced movement
        FlockMover mover = flockGroup.AddComponent<FlockMover>();
        
        // 다양한 이동 방향 설정 - 모든 각도에서 자연스럽게
        Vector3 moveDirection;
        float directionType = Random.value;
        
        if (directionType < groundFlockProbability) // 지상 근처 이동
        {
            moveDirection = new Vector3(Random.Range(-1f, 1f), Random.Range(-0.2f, 0.1f), Random.Range(-1f, 1f));
            center.y = Mathf.Max(5f, center.y * 0.3f); // 낮은 고도
        }
        else if (directionType < 0.25f) // 하강 패턴 (25%)
        {
            moveDirection = new Vector3(Random.Range(-1f, 1f), Random.Range(-0.8f, -0.2f), Random.Range(-1f, 1f));
        }
        else if (directionType < 0.45f) // 수평 이동 (20%)
        {
            moveDirection = new Vector3(Random.Range(-1f, 1f), Random.Range(-0.1f, 0.1f), Random.Range(-1f, 1f));
        }
        else if (directionType < 0.65f) // 상승 패턴 (20%)
        {
            moveDirection = new Vector3(Random.Range(-1f, 1f), Random.Range(0.2f, 0.8f), Random.Range(-1f, 1f));
        }
        else // 완전 무작위 방향 (35%)
        {
            moveDirection = Random.onUnitSphere;
            // Y값을 자연스럽게 조정 (너무 급격한 상승/하강 방지)
            moveDirection.y = Mathf.Clamp(moveDirection.y, -0.6f, 0.8f);
        }
        
        mover.moveDirection = moveDirection.normalized;
        mover.moveSpeed = Random.Range(minMoveSpeed, maxMoveSpeed);

        // ✅ 포메이션 패턴 선택 (Inspector 설정 우선)
        FlockFormation formation;
        
        // 1. 먼저 preferredFormation 설정 확인
        if (preferredFormation != FlockFormation.Random)
        {
            formation = preferredFormation;
            Debug.Log($"[BirdSpawner] Using preferred formation: {formation}");
        }
        // 2. Random 설정인 경우 기존 로직 사용
        else if (enablePerformanceMode && Random.value < 0.6f)
        {
            // 성능 모드에서는 60% 확률로 단순한 패턴 사용
            formation = Random.value < 0.5f ? FlockFormation.Tight : FlockFormation.Spread;
        }
        else
        {
            formation = enableFormationVariation ? 
                (FlockFormation)Random.Range(1, System.Enum.GetValues(typeof(FlockFormation)).Length) : // Random 제외
                FlockFormation.Tight;
        }

        // 새 개체 생성 (성능 최적화)
        for (int i = 0; i < birdCount; i++)
        {
            Vector3 offset = GetFormationOffset(formation, i, birdCount, spawnRadius);
            Vector3 spawnPos = center + offset;

            GameObject bird = Instantiate(selectedPrefab, spawnPos, Quaternion.identity, flockGroup.transform);
            bird.name = $"Bird_{i:D2}";
            // 개별 새는 태그 없음 - FlockGroup만 "Flock" 태그 사용

            // 개별 새에 약간의 랜덤 회전 추가
            bird.transform.rotation = Quaternion.Euler(
                Random.Range(-15f, 15f),
                Random.Range(0f, 360f),
                Random.Range(-10f, 10f)
            );
            
            // 성능 모드에서는 LOD 시스템 고려 (나중에 추가 가능)
        }

        // 이동 방향 분류
        string movementPattern;
        if (directionType < groundFlockProbability)
            movementPattern = "Ground-level";
        else if (directionType < 0.25f)
            movementPattern = "Descending";
        else if (directionType < 0.45f)
            movementPattern = "Horizontal";
        else if (directionType < 0.65f)
            movementPattern = "Ascending";
        else
            movementPattern = "Random-sphere";

        string performanceNote = enablePerformanceMode ? $" (Performance Mode: {birdCount}/{maxBirdsInPerformanceMode})" : "";
        Debug.Log($"[BirdSpawner] Created {birdCount} birds in {formation} formation at {center}");
        Debug.Log($"[BirdSpawner] Movement: {movementPattern} direction ({moveDirection.x:F2}, {moveDirection.y:F2}, {moveDirection.z:F2}) at speed {mover.moveSpeed:F1}{performanceNote}");
        
        return flockGroup;
    }

    private Vector3 GetFormationOffset(FlockFormation formation, int index, int totalBirds, float radius)
    {
        Vector3 offset;
        
        switch (formation)
        {
            case FlockFormation.Tight:
                // 촘촘한 구형 배치 (성능 친화적)
                offset = Random.insideUnitSphere * (radius * tightFormationScale);
                break;
                
            case FlockFormation.Spread:
                // 넓게 퍼진 배치
                offset = Random.insideUnitSphere * (radius * spreadFormationScale);
                break;
                
            case FlockFormation.Line:
                // 선형 배치
                float t = (float)index / (totalBirds - 1);
                offset = new Vector3(
                    (t - 0.5f) * radius * lineFormationScale,
                    Random.Range(-radius * 0.15f, radius * 0.15f),
                    Random.Range(-radius * 0.2f, radius * 0.2f)
                );
                break;
                
            case FlockFormation.VShape:
                // V자 형태 배치
                float side = index % 2 == 0 ? 1f : -1f;
                float distance = (index / 2) * radius * (lineFormationScale * 0.17f); // lineFormationScale 기반
                offset = new Vector3(
                    side * distance,
                    Random.Range(-radius * 0.08f, radius * 0.08f),
                    -distance * 0.4f + Random.Range(-radius * 0.15f, radius * 0.15f)
                );
                break;
                
            default: // Random (가장 성능 친화적)
                offset = Random.insideUnitSphere * radius * 0.8f;
                break;
        }
        
        // ✅ 전체적인 스프레드 배율 적용
        offset *= globalSpreadMultiplier;
        
        // Y값을 항상 양수로 유지 (공중 비행)
        offset.y = Mathf.Abs(offset.y);
        return offset;
    }

    void OnDrawGizmosSelected()
    {
        Gizmos.color = Color.cyan;
        Gizmos.DrawWireCube(spawnAreaCenter, spawnAreaSize);
        
        // 스폰 반경 표시
        Gizmos.color = Color.yellow;
        Gizmos.DrawWireSphere(spawnAreaCenter, maxSpawnRadius);
        
        // 성능 모드 표시
        if (enablePerformanceMode)
        {
            Gizmos.color = Color.green;
            Gizmos.DrawWireSphere(spawnAreaCenter + Vector3.up * 5f, 2f);
        }
    }
}
