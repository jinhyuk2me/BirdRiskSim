using UnityEngine;

public class AirplaneBezierMover : MonoBehaviour
{
    [Header("Path Settings")]
    public WaypointBezierPath path;
    public bool loop = false;
    
    [Header("Movement Settings")]
    [Range(5f, 50f)]
    public float speed = 10f;
    
    [Header("Rotation Settings")]
    [Range(1f, 10f)]
    public float rotationSpeed = 5f;
    
    [Header("Advanced Settings")]
    [Range(0.001f, 0.1f)]
    public float movementThreshold = 0.01f; // 이동 임계값
    public bool disableAutoDestroy = false; // 시나리오 모드에서 자동 소멸 비활성화
    
    // 상수 정의
    private const float SPEED_DIVISOR = 100f; // 속도 나누기 값
    
    // 상태 변수
    private float t = 0f;
    private bool isDestroying = false;

    void Start()
    {
        ValidateSetup();
    }

    void Update()
    {
        if (isDestroying || !ValidateMovement()) return;

        UpdatePosition();
        UpdateRotation();
    }

    /// <summary>
    /// 초기 설정 검증
    /// </summary>
    private void ValidateSetup()
    {
        if (path == null)
        {
            Debug.LogError($"[AirplaneBezierMover] {gameObject.name}: WaypointBezierPath가 설정되지 않았습니다!");
            enabled = false;
            return;
        }

        if (!path.IsValid())
        {
            Debug.LogError($"[AirplaneBezierMover] {gameObject.name}: WaypointBezierPath가 유효하지 않습니다! (웨이포인트 2개 이상 필요)");
            enabled = false;
            return;
        }
    }

    /// <summary>
    /// 이동 가능 여부 확인
    /// </summary>
    private bool ValidateMovement()
    {
        return path != null && path.IsValid();
    }

    /// <summary>
    /// 위치 업데이트
    /// </summary>
    private void UpdatePosition()
    {
        // t 값 증가 (정규화된 속도 사용)
        t += (speed * Time.deltaTime) / SPEED_DIVISOR;

        // 경로 끝에 도달했을 때 처리
        if (t >= 1f)
        {
            HandlePathEnd();
            return;
        }

        // 새 위치로 이동
        Vector3 newPosition = path.GetPosition(t);
        transform.position = newPosition;
    }

    /// <summary>
    /// 회전 업데이트
    /// </summary>
    private void UpdateRotation()
    {
        // WaypointBezierPath의 GetDirection 메서드 활용
        Vector3 direction = path.GetDirection(t);
        
        if (direction.magnitude > movementThreshold)
        {
            Quaternion targetRotation = Quaternion.LookRotation(direction);
            transform.rotation = Quaternion.Slerp(
                transform.rotation, 
                targetRotation, 
                Time.deltaTime * rotationSpeed
            );
        }
    }

    /// <summary>
    /// 경로 끝 처리
    /// </summary>
    private void HandlePathEnd()
    {
        if (loop)
        {
            t = 0f; // 루프 시작
            Debug.Log($"[AirplaneBezierMover] {gameObject.name}: 경로 루프 재시작");
        }
        else
        {
            // 최종 위치 설정
            transform.position = path.GetPosition(1f);
            
            // 시나리오 모드에서는 자동 소멸하지 않음
            if (!disableAutoDestroy)
            {
            DestroyAirplane();
            }
            else
            {
                Debug.Log($"[AirplaneBezierMover] {gameObject.name}: 경로 완주 (자동 소멸 비활성화됨)");
            }
        }
    }

    /// <summary>
    /// 비행기 제거
    /// </summary>
    private void DestroyAirplane()
    {
        if (isDestroying) return;
        
        isDestroying = true;
        Debug.Log($"[AirplaneBezierMover] {gameObject.name}: 경로 완주 후 제거됨");
        Destroy(gameObject);
    }

    /// <summary>
    /// 현재 진행률 반환 (0-1)
    /// </summary>
    public float GetProgress()
    {
        return Mathf.Clamp01(t);
    }

    /// <summary>
    /// 남은 거리 비율 반환
    /// </summary>
    public float GetRemainingProgress()
    {
        return 1f - GetProgress();
    }

    /// <summary>
    /// 디버그 정보 표시
    /// </summary>
    private void OnDrawGizmosSelected()
    {
        if (path == null || !path.IsValid()) return;

        // 현재 위치 표시
        Gizmos.color = Color.magenta;
        Gizmos.DrawSphere(transform.position, 1f);

        // 진행 방향 표시
        Vector3 direction = path.GetDirection(t);
        if (direction.magnitude > 0.01f)
        {
            Gizmos.color = Color.blue;
            Gizmos.DrawRay(transform.position, direction * 5f);
        }

        // 다음 위치 미리보기
        float nextT = Mathf.Clamp01(t + 0.05f);
        Vector3 nextPos = path.GetPosition(nextT);
        Gizmos.color = Color.white;
        Gizmos.DrawLine(transform.position, nextPos);
    }
}
