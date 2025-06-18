using UnityEngine;

public class FlockMover : MonoBehaviour
{
    [Header("Movement")]
    public Vector3 moveDirection = Vector3.forward;
    public float moveSpeed = 10f;
    
    [Header("Movement Variation")]
    public bool enableCurvedMovement = true;
    public float directionChangeInterval = 3f;  // 3초마다 방향 변경
    public float directionChangeStrength = 0.3f; // 방향 변경 강도
    public bool enableCircularMovement = false;  // 원형 이동 패턴
    
    [Header("Lifetime Management")]
    public float maxLifetime = 15f;        // 15초 후 자동 삭제
    public float maxDistance = 300f;       // 카메라에서 300m 떠나면 삭제
    public bool enableBoundaryCheck = true;
    public bool disableAutoDestroy = false; // 시나리오 모드에서 자동 소멸 비활성화
    
    [Header("Performance")]
    public bool enablePerformanceMode = true;
    public float updateInterval = 0.02f;   // 50fps 대신 업데이트 (성능 향상)
    
    private Camera mainCamera;
    private float spawnTime;
    private float lastUpdateTime;
    private Vector3 initialPosition;
    private Vector3 originalMoveDirection;
    private float lastDirectionChangeTime;
    private float circularTimer = 0f;
    
    void Start()
    {
        spawnTime = Time.time;
        mainCamera = Camera.main;
        initialPosition = transform.position;
        lastUpdateTime = Time.time;
        originalMoveDirection = moveDirection.normalized;
        lastDirectionChangeTime = Time.time;
        
        // 랜덤하게 이동 패턴 선택
        if (Random.value < 0.2f) // 20% 확률로 원형 이동
        {
            enableCircularMovement = true;
            circularTimer = Random.Range(0f, 2f * Mathf.PI); // 랜덤 시작점
        }
        
        // 성능 모드에서는 더 빨리 삭제
        if (enablePerformanceMode)
        {
            maxLifetime *= 0.8f;  // 20% 빨리 삭제
            maxDistance *= 0.9f;  // 10% 가까운 거리에서 삭제
        }
        
        string movementType = enableCircularMovement ? "circular" : (enableCurvedMovement ? "curved" : "straight");
        Debug.Log($"[FlockMover] Flock spawned. Movement: {movementType}, Lifetime: {maxLifetime}s, Max distance: {maxDistance}m");
    }

    void Update()
    {
        // 성능 최적화: 일정 간격으로만 업데이트
        if (enablePerformanceMode && Time.time - lastUpdateTime < updateInterval)
            return;
        
        lastUpdateTime = Time.time;
        
        // 다양한 이동 패턴
        Vector3 currentMoveDirection = moveDirection.normalized;
        
        if (enableCircularMovement)
        {
            // 원형/나선형 이동 패턴
            circularTimer += Time.deltaTime * 0.5f; // 원형 속도 조절
            Vector3 circularOffset = new Vector3(
                Mathf.Sin(circularTimer) * 20f,
                Mathf.Cos(circularTimer * 0.3f) * 5f, // 수직 변화
                Mathf.Cos(circularTimer) * 20f
            );
            currentMoveDirection = (originalMoveDirection + circularOffset.normalized * 0.4f).normalized;
        }
        else if (enableCurvedMovement)
        {
            // 곡선 이동 - 주기적으로 방향 변경
            if (Time.time - lastDirectionChangeTime > directionChangeInterval)
            {
                // 랜덤 방향 변화 추가
                Vector3 randomChange = new Vector3(
                    Random.Range(-1f, 1f),
                    Random.Range(-0.5f, 0.5f),
                    Random.Range(-1f, 1f)
                ).normalized * directionChangeStrength;
                
                moveDirection = (originalMoveDirection + randomChange).normalized;
                lastDirectionChangeTime = Time.time;
                
                // 가끔 새로운 기준 방향 설정
                if (Random.value < 0.3f)
                {
                    originalMoveDirection = moveDirection;
                }
            }
            
            // 부드러운 sine 파형 추가
            float waveOffset = Mathf.Sin(Time.time * 0.8f) * 0.2f;
            Vector3 perpendicular = Vector3.Cross(moveDirection, Vector3.up).normalized;
            currentMoveDirection = (moveDirection + perpendicular * waveOffset).normalized;
        }
        
        // 최종 이동 적용
        transform.position += currentMoveDirection * moveSpeed * Time.deltaTime;
        
        // 자동 삭제 조건 체크
        CheckForCleanup();
    }
    
    private void CheckForCleanup()
    {
        // 시나리오 모드에서는 자동 소멸 비활성화
        if (disableAutoDestroy)
        {
            return;
        }

        bool shouldDestroy = false;
        string reason = "";
        
        // 1. 시간 초과
        if (Time.time - spawnTime > maxLifetime)
        {
            shouldDestroy = true;
            reason = "lifetime expired";
        }
        
        // 2. 거리 초과 (카메라 기준)
        if (enableBoundaryCheck && mainCamera != null)
        {
            float distanceFromCamera = Vector3.Distance(transform.position, mainCamera.transform.position);
            if (distanceFromCamera > maxDistance)
            {
                shouldDestroy = true;
                reason = $"distance exceeded ({distanceFromCamera:F0}m)";
            }
        }
        
        // 3. 초기 위치에서 너무 멀어짐
        float distanceFromSpawn = Vector3.Distance(transform.position, initialPosition);
        if (distanceFromSpawn > maxDistance * 1.5f)
        {
            shouldDestroy = true;
            reason = $"moved too far from spawn ({distanceFromSpawn:F0}m)";
        }
        
        // 4. 카메라 뒤로 너무 멀리 가거나 지하로 가면 삭제
        if (transform.position.y < -10f || 
            (mainCamera != null && Vector3.Dot((transform.position - mainCamera.transform.position).normalized, mainCamera.transform.forward) < -0.8f))
        {
            shouldDestroy = true;
            reason = "out of bounds";
        }
        
        // 자동 삭제 실행
        if (shouldDestroy)
        {
            Debug.Log($"[FlockMover] Auto-destroying flock: {reason}");
            
            // Trail 정리 (메모리 절약)
            TrailRenderer[] trails = GetComponentsInChildren<TrailRenderer>();
            foreach (var trail in trails)
            {
                if (trail != null) trail.Clear();
            }
            
            Destroy(gameObject);
        }
    }
    
    /// <summary>
    /// 수동으로 즉시 삭제
    /// </summary>
    public void ForceDestroy()
    {
        Debug.Log("[FlockMover] Force destroying flock");
        Destroy(gameObject);
    }
    
    void OnDrawGizmosSelected()
    {
        // 현재 위치와 방향 표시
        Gizmos.color = Color.red;
        Gizmos.DrawWireSphere(transform.position, 5f);
        
        Gizmos.color = Color.blue;
        Gizmos.DrawRay(transform.position, moveDirection.normalized * 20f);
        
        // 최대 거리 범위 표시
        if (mainCamera != null)
        {
            Gizmos.color = Color.yellow;
            Gizmos.DrawWireSphere(mainCamera.transform.position, maxDistance);
        }
    }
}
