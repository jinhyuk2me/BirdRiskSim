using UnityEngine;
using System.Collections;

public class CameraRandomizer : MonoBehaviour
{
    [Header("🎯 Camera Position Randomizer")]
    [Space(10)]
    
    [Header("Target Cameras")]
    [Tooltip("랜덤 위치로 이동할 카메라들")]
    public Camera[] managedCameras;

    [Header("Look Target")]
    [Tooltip("카메라들이 바라볼 타겟 (선택사항)")]
    public Transform lookTarget;
    
    [Tooltip("타겟 위치에서의 오프셋")]
    public Vector3 lookOffset = new Vector3(0, 50f, 0);

    [Header("Randomization Area")]
    [Tooltip("랜덤 위치의 중심점")]
    public Vector3 center = new Vector3(90, 10, 41);
    
    [Tooltip("중심점으로부터의 랜덤 범위 (±값)")]
    public Vector3 range = new Vector3(30, 10, 30);

    [Header("Timing Settings")]
    [Tooltip("위치 변경 간격 (초)")]
    [Range(1f, 30f)]
    public float changeInterval = 5f;
    
    [Tooltip("시작 시 즉시 랜덤화 여부")]
    public bool randomizeOnStart = true;

    [Header("Advanced Options")]
    [Tooltip("부드러운 이동 사용")]
    public bool useSmoothMovement = false;
    
    [Range(0.5f, 5f)]
    [Tooltip("부드러운 이동 속도")]
    public float smoothMoveSpeed = 2f;

    // 상태 관리
    private bool isRandomizing = false;
    private Vector3[] targetPositions;
    private Coroutine smoothMoveCoroutine;

    void Start()
    {
        ValidateSetup();
        
        if (managedCameras.Length > 0)
        {
            targetPositions = new Vector3[managedCameras.Length];
            
            if (randomizeOnStart)
            {
                if (useSmoothMovement)
                {
                    RandomizeAllSmooth();
                }
                else
                {
                    RandomizeAllInstant();
                }
            }
            
            // 주기적 랜덤화 시작
            InvokeRepeating(nameof(ScheduledRandomize), changeInterval, changeInterval);
            isRandomizing = true;
        }
    }

    /// <summary>
    /// 초기 설정 검증
    /// </summary>
    void ValidateSetup()
    {
        if (managedCameras == null || managedCameras.Length == 0)
        {
            Debug.LogWarning("[CameraRandomizer] 관리할 카메라가 설정되지 않았습니다!");
            enabled = false;
            return;
        }

        for (int i = 0; i < managedCameras.Length; i++)
        {
            if (managedCameras[i] == null)
            {
                Debug.LogWarning($"[CameraRandomizer] Camera {i}가 null입니다!");
            }
        }

        Debug.Log($"[CameraRandomizer] {managedCameras.Length}개 카메라 랜덤화 시스템 초기화 완료");
    }

    /// <summary>
    /// 주기적 랜덤화 (InvokeRepeating용)
    /// </summary>
    void ScheduledRandomize()
    {
        if (useSmoothMovement)
        {
            RandomizeAllSmooth();
        }
        else
        {
            RandomizeAllInstant();
        }
    }

    /// <summary>
    /// 즉시 모든 카메라 위치 랜덤화
    /// </summary>
    [ContextMenu("🎲 Randomize All Cameras")]
    public void RandomizeAllInstant()
    {
        for (int i = 0; i < managedCameras.Length; i++)
        {
            if (managedCameras[i] == null) continue;
            
            Vector3 randomPos = GetRandomPosition();
            managedCameras[i].transform.position = randomPos;
            
            // 타겟 바라보기
            if (lookTarget != null)
            {
                Vector3 lookAtPos = lookTarget.position + lookOffset;
                managedCameras[i].transform.LookAt(lookAtPos);
            }
        }
        
        Debug.Log($"[CameraRandomizer] {managedCameras.Length}개 카메라 위치를 즉시 랜덤화했습니다");
    }

    /// <summary>
    /// 부드럽게 모든 카메라 위치 랜덤화
    /// </summary>
    public void RandomizeAllSmooth()
    {
        // 새 타겟 위치 계산
        for (int i = 0; i < managedCameras.Length; i++)
        {
            targetPositions[i] = GetRandomPosition();
        }
        
        // 기존 코루틴 중지
        if (smoothMoveCoroutine != null)
        {
            StopCoroutine(smoothMoveCoroutine);
        }
        
        // 부드러운 이동 시작
        smoothMoveCoroutine = StartCoroutine(SmoothMoveToTargets());
    }

    /// <summary>
    /// 부드러운 이동 코루틴
    /// </summary>
    IEnumerator SmoothMoveToTargets()
    {
        Vector3[] startPositions = new Vector3[managedCameras.Length];
        
        // 시작 위치 저장
        for (int i = 0; i < managedCameras.Length; i++)
        {
            if (managedCameras[i] != null)
            {
                startPositions[i] = managedCameras[i].transform.position;
            }
        }
        
        float elapsedTime = 0f;
        float duration = 1f / smoothMoveSpeed;
        
        while (elapsedTime < duration)
        {
            float progress = elapsedTime / duration;
            float smoothProgress = Mathf.SmoothStep(0f, 1f, progress);
            
            // 모든 카메라 이동
            for (int i = 0; i < managedCameras.Length; i++)
            {
                if (managedCameras[i] == null) continue;
                
                Vector3 currentPos = Vector3.Lerp(startPositions[i], targetPositions[i], smoothProgress);
                managedCameras[i].transform.position = currentPos;
                
                // 타겟 바라보기
                if (lookTarget != null)
                {
                    Vector3 lookAtPos = lookTarget.position + lookOffset;
                    managedCameras[i].transform.LookAt(lookAtPos);
                }
            }
            
            elapsedTime += Time.deltaTime;
            yield return null;
        }
        
        // 최종 위치 정확히 설정
        for (int i = 0; i < managedCameras.Length; i++)
        {
            if (managedCameras[i] != null)
            {
                managedCameras[i].transform.position = targetPositions[i];
                
                if (lookTarget != null)
                {
                    Vector3 lookAtPos = lookTarget.position + lookOffset;
                    managedCameras[i].transform.LookAt(lookAtPos);
                }
            }
        }
        
        Debug.Log($"[CameraRandomizer] {managedCameras.Length}개 카메라가 부드럽게 이동 완료");
    }

    /// <summary>
    /// 랜덤 위치 생성
    /// </summary>
    Vector3 GetRandomPosition()
    {
        return center + new Vector3(
            Random.Range(-range.x, range.x),
            Random.Range(-range.y, range.y),
            Random.Range(-range.z, range.z)
        );
    }

    /// <summary>
    /// 랜덤화 시작/중지 토글
    /// </summary>
    [ContextMenu("⏯️ Toggle Randomization")]
    public void ToggleRandomization()
    {
        if (isRandomizing)
        {
            StopRandomization();
        }
        else
        {
            StartRandomization();
        }
    }

    /// <summary>
    /// 랜덤화 시작
    /// </summary>
    public void StartRandomization()
    {
        if (!isRandomizing)
        {
            InvokeRepeating(nameof(ScheduledRandomize), 0f, changeInterval);
            isRandomizing = true;
            Debug.Log("[CameraRandomizer] 랜덤화 시작됨");
        }
    }

    /// <summary>
    /// 랜덤화 중지
    /// </summary>
    public void StopRandomization()
    {
        if (isRandomizing)
        {
            CancelInvoke(nameof(ScheduledRandomize));
            isRandomizing = false;
            
            if (smoothMoveCoroutine != null)
            {
                StopCoroutine(smoothMoveCoroutine);
                smoothMoveCoroutine = null;
            }
            
            Debug.Log("[CameraRandomizer] 랜덤화 중지됨");
        }
    }

    /// <summary>
    /// 현재 상태 정보 표시
    /// </summary>
    [ContextMenu("📊 Show Status")]
    public void ShowStatus()
    {
        string status = isRandomizing ? "활성" : "비활성";
        Debug.Log($"[CameraRandomizer] 상태: {status}");
        Debug.Log($"[CameraRandomizer] 관리 카메라: {managedCameras.Length}개");
        Debug.Log($"[CameraRandomizer] 변경 간격: {changeInterval}초");
        Debug.Log($"[CameraRandomizer] 부드러운 이동: {(useSmoothMovement ? "사용" : "사용 안함")}");
        Debug.Log($"[CameraRandomizer] 중심점: {center}");
        Debug.Log($"[CameraRandomizer] 범위: ±{range}");
    }

    void OnDestroy()
    {
        // 정리 작업
        if (smoothMoveCoroutine != null)
        {
            StopCoroutine(smoothMoveCoroutine);
        }
        CancelInvoke();
    }

    // 기즈모로 랜덤화 영역 표시
    void OnDrawGizmosSelected()
    {
        // 중심점
        Gizmos.color = Color.yellow;
        Gizmos.DrawSphere(center, 1f);

        // 랜덤 범위 박스
        Gizmos.color = new Color(0, 1, 0, 0.3f);
        Gizmos.DrawCube(center, range * 2);

        // 경계선
        Gizmos.color = Color.green;
        Gizmos.DrawWireCube(center, range * 2);

        // 현재 카메라 위치들
        if (managedCameras != null)
        {
            Gizmos.color = Color.red;
            foreach (Camera cam in managedCameras)
            {
                if (cam != null)
                {
                    Gizmos.DrawSphere(cam.transform.position, 0.5f);
                }
            }
        }

        // 타겟 표시
        if (lookTarget != null)
        {
            Gizmos.color = Color.blue;
            Vector3 targetPos = lookTarget.position + lookOffset;
            Gizmos.DrawSphere(targetPos, 1.5f);
            
            // 타겟으로의 선
            if (managedCameras != null)
            {
                Gizmos.color = Color.cyan;
                foreach (Camera cam in managedCameras)
                {
                    if (cam != null)
                    {
                        Gizmos.DrawLine(cam.transform.position, targetPos);
                    }
                }
            }
        }
    }
}
