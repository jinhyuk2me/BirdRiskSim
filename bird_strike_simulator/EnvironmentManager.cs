using UnityEngine;

public class EnvironmentManager : MonoBehaviour
{
    [Header("Performance Optimization")]
    public bool enablePerformanceMode = true;  // 🔧 성능 최적화 모드
    public bool enableLightCycle = true;       // 조명 변화 On/Off
    public bool enableFogEffects = false;     // 안개 효과 On/Off (리소스 절약)
    public bool enableAutoCycle = false;      // 자동 시간 변화 Off (성능 절약)
    
    [Header("Time Settings")]
    public Light directionalLight;
    public Gradient ambientLightColor; // 시간대별 환경광 색
    public Gradient directionalLightColor;
    public AnimationCurve lightAngleOverTime; // 0~1을 시간대라 가정 (곡선: 각도 변화)

    [Range(0f, 1f)]
    public float timeOfDay = 0.5f; // 0 = 새벽, 0.5 = 정오, 1 = 밤 (고정값으로 변경)

    [Header("Fog Settings")]
    public bool enableFog = false;  // 🔧 기본값 false로 변경
    public Color fogColorDay = new Color(0.7f, 0.8f, 0.9f);
    public Color fogColorNight = new Color(0.1f, 0.1f, 0.15f);
    public float fogDensityDay = 0.002f;
    public float fogDensityNight = 0.01f;

    [Header("Auto Cycle")]
    public bool autoCycle = false;  // 🔧 기본값 false로 변경 (성능 절약)
    public float cycleSpeed = 0.05f; // per second
    
    [Header("Performance Settings")]
    [Range(0.1f, 5f)]
    public float updateInterval = 2f;    // 업데이트 간격 (초) - 기본값 증가
    private float lastUpdateTime = 0f;

    void Start()
    {
        // 성능 모드 설정 적용
        if (enablePerformanceMode)
        {
            autoCycle = enableAutoCycle;
            enableFog = enableFogEffects;
            updateInterval = 1f;  // 더 긴 업데이트 간격
            Debug.Log("[EnvironmentManager] 성능 최적화 모드 활성화됨");
        }
        
        if (enableFog && enableFogEffects)
        {
            RenderSettings.fog = true;
            Debug.Log("[EnvironmentManager] Fog 효과 활성화됨");
        }
        else
        {
            RenderSettings.fog = false;
            Debug.Log("[EnvironmentManager] Fog 효과 비활성화됨 (성능 절약)");
        }
        
        // 초기 설정 적용 (한 번만)
        ApplyLighting(timeOfDay);
        if (enableFogEffects) ApplyFog(timeOfDay);
    }

    void Update()
    {
        // 🔧 성능 최적화: 일정 간격으로만 업데이트
        if (Time.time - lastUpdateTime < updateInterval) return;
        lastUpdateTime = Time.time;
        
        // 자동 사이클이 활성화된 경우에만 시간 변화
        if (autoCycle && enableAutoCycle)
        {
            timeOfDay += Time.deltaTime * cycleSpeed;
            if (timeOfDay > 1f) timeOfDay -= 1f;
        }

        // 조명 변화가 활성화된 경우에만 적용
        if (enableLightCycle)
        {
            ApplyLighting(timeOfDay);
        }
        
        // 안개 효과가 활성화된 경우에만 적용
        if (enableFogEffects && enableFog)
        {
            ApplyFog(timeOfDay);
        }
    }

    void ApplyLighting(float t)
    {
        if (directionalLight != null)
        {
            // 성능 모드에서는 더 간단한 계산
            if (enablePerformanceMode)
            {
                // 고정된 조명 설정 (계산 최소화)
                directionalLight.color = Color.white;
                directionalLight.transform.rotation = Quaternion.Euler(50f, 30f, 0f);
            }
            else
            {
                // 원래 복잡한 계산
                directionalLight.color = directionalLightColor.Evaluate(t);
                float angle = Mathf.Lerp(0f, 360f, lightAngleOverTime.Evaluate(t));
                directionalLight.transform.rotation = Quaternion.Euler(new Vector3(angle, 30f, 0f));
            }
        }

        // 환경광도 성능 모드에 따라 조정
        if (enablePerformanceMode)
        {
            RenderSettings.ambientLight = Color.gray; // 고정값
        }
        else
        {
            RenderSettings.ambientLight = ambientLightColor.Evaluate(t);
        }
    }

    void ApplyFog(float t)
    {
        if (!enableFogEffects) return;
        
        Color fogColor = Color.Lerp(fogColorNight, fogColorDay, Mathf.Sin(t * Mathf.PI));
        float fogDensity = Mathf.Lerp(fogDensityNight, fogDensityDay, Mathf.Sin(t * Mathf.PI));

        RenderSettings.fogColor = fogColor;
        RenderSettings.fogDensity = fogDensity;
    }
    
    /// <summary>
    /// 완전히 Environment를 비활성화 (극한 성능 모드)
    /// </summary>
    [ContextMenu("Disable All Environment Effects")]
    public void DisableAllEnvironment()
    {
        enableLightCycle = false;
        enableFogEffects = false;
        enableAutoCycle = false;
        RenderSettings.fog = false;
        
        // 최소한의 조명만 유지
        if (directionalLight != null)
        {
            directionalLight.color = Color.white;
            directionalLight.intensity = 1f;
            directionalLight.transform.rotation = Quaternion.Euler(50f, 30f, 0f);
        }
        
        RenderSettings.ambientLight = Color.gray;
        Debug.Log("[EnvironmentManager] 🔧 모든 Environment 효과 비활성화됨 (극한 성능 모드)");
    }
    
    /// <summary>
    /// 최소한의 Environment 효과만 활성화
    /// </summary>
    [ContextMenu("Enable Minimal Environment")]
    public void EnableMinimalEnvironment()
    {
        enableLightCycle = false;  // 조명 변화 없음
        enableFogEffects = false;  // 안개 없음
        enableAutoCycle = false;   // 시간 변화 없음
        timeOfDay = 0.5f;         // 정오로 고정
        
        ApplyLighting(timeOfDay);
        Debug.Log("[EnvironmentManager] ✅ 최소한의 Environment 효과만 활성화됨");
    }
}
