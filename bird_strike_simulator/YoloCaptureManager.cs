using UnityEngine;
using UnityEngine.InputSystem;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text;

public class YoloCaptureManager : MonoBehaviour
{
    [Header("YOLO Capture Cameras")]
    public Camera[] yoloCameras;

    [Header("3D Pipeline Fixed Cameras")]
    public Camera[] pipelineCameras;

    [Header("✅ Simple Labeling System")]
    // 간단한 FindGameObjectsWithTag 방식 사용

    [Header("Image Settings")]
    public int imageWidth = 1920;
    public int imageHeight = 1080;

    public enum CaptureMode { YOLO, Pipeline }

    [Header("Capture Settings - Performance Optimized")]
    public CaptureMode captureMode = CaptureMode.YOLO;
    
    [Range(0.3f, 3f)]
    public float captureInterval = 1f; // 0.5초에서 1초로 늘림 (성능 고려)
    
    public bool captureEnabled = true;
    
    [Header("Data Collection Goals")]
    public int targetImageCount = 5000; // 8000에서 5000으로 줄임 (현실적 목표)
    public bool stopAtTarget = false; // 목표 달성시 자동 중지

    [Header("Performance Settings")]
    public bool enablePerformanceMode = true;
    [Range(0.5f, 2f)]
    public float performanceModeMultiplier = 1.5f; // 성능 모드시 캡처 간격 배수 (더 보수적으로)

    [Header("Auto Resume Settings")]
    public bool enableAutoResume = true; // 자동 이어받기 활성화
    
    [Header("Dataset Generation Options")]
    public bool generateCSRNetData = false; // 🔧 CSRNet 데이터 생성 On/Off
    
    [Header("Debug Options")]
    public bool useManualCoordinateTransform = false; // 수동 좌표 변환 테스트용
    
    [Header("Bounding Box Limits")]
    [Range(0.05f, 0.25f)]
    public float maxBoundingBoxWidth = 0.15f;  // 최대 폭 15%
    [Range(0.05f, 0.20f)]
    public float maxBoundingBoxHeight = 0.12f; // 최대 높이 12%

    [Header("🎮 Capture Controls")]
    [Space(5)]
    public KeyCode toggleCaptureKey = KeyCode.C;
    public KeyCode pauseResumeKey = KeyCode.P;
    public bool showCaptureGUI = true;

    private int frameIndex = 0;
    private int totalCapturedImages = 0;
    private int resumedFromFrame = 0;
    private bool isPaused = false;
    private Coroutine captureCoroutine;

    void Start()
    {
        if (enablePerformanceMode)
        {
            captureInterval *= performanceModeMultiplier;
            Debug.Log($"[CaptureManager] 성능 최적화 모드: 캡처 간격 {captureInterval}초로 조정");
        }
        
        // 자동 이어받기 설정
        if (enableAutoResume)
        {
            frameIndex = FindLastFrameIndex();
            resumedFromFrame = frameIndex;
            if (frameIndex > 0)
            {
                Debug.Log($"[CaptureManager] 자동 이어받기: frame_{frameIndex:D5}부터 시작");
                totalCapturedImages = CountExistingImages();
            }
        }
        
        Debug.Log($"[CaptureManager] Starting data collection. Target: {targetImageCount} images");
        Debug.Log($"[CaptureManager] Capture interval: {captureInterval}s, Cameras: {yoloCameras.Length}");
        Debug.Log($"[CaptureManager] Bounding box limits: W≤{maxBoundingBoxWidth*100:F0}%, H≤{maxBoundingBoxHeight*100:F0}%");
        Debug.Log($"[CaptureManager] CSRNet data generation: {(generateCSRNetData ? "Enabled" : "Disabled")}");
        
        if (captureEnabled)
            StartCapture();
    }

    void Update()
    {
        // 새로운 Input System 사용
        if (Keyboard.current != null)
        {
            // C 키로 캡처 토글
            if (Keyboard.current.cKey.wasPressedThisFrame)
            {
                ToggleCapture();
            }
            // P 키로 일시정지 토글
            else if (Keyboard.current.pKey.wasPressedThisFrame)
            {
                TogglePause();
            }
        }
    }

    void OnGUI()
    {
        if (!showCaptureGUI) return;

        // 🎯 하단 중앙으로 위치 이동 (가독성 개선)
        float panelWidth = 450f;  // 320 → 450으로 확대
        float panelHeight = 110f; // 90 → 110으로 확대
        float bottomMargin = 20f;
        
        float panelX = (Screen.width - panelWidth) / 2f; // 중앙 정렬
        float panelY = Screen.height - panelHeight - bottomMargin; // 하단
        
        // 반투명 배경
        Color originalColor = GUI.backgroundColor;
        GUI.backgroundColor = new Color(0.1f, 0.1f, 0.1f, 0.85f); // 조금 더 진하게
        GUI.Box(new Rect(panelX, panelY, panelWidth, panelHeight), "");
        GUI.backgroundColor = originalColor;
        
        // 가독성 좋은 스타일
        GUIStyle titleStyle = new GUIStyle(GUI.skin.label);
        titleStyle.fontSize = 16;  // 14 → 16으로 확대
        titleStyle.fontStyle = FontStyle.Bold;
        titleStyle.normal.textColor = Color.white;
        titleStyle.alignment = TextAnchor.MiddleCenter;
        
        GUIStyle infoStyle = new GUIStyle(GUI.skin.label);
        infoStyle.fontSize = 12;  // 11 → 12로 확대
        infoStyle.normal.textColor = Color.white;
        infoStyle.alignment = TextAnchor.MiddleCenter;
        
        // 상태와 제목을 한 줄로
        string status = "";
        Color statusColor = Color.white;
        
        if (!captureEnabled)
        {
            status = "⚪ YOLO Capture: Stopped";
            statusColor = Color.gray;
        }
        else if (isPaused)
        {
            status = "⏸️ YOLO Capture: Paused";
            statusColor = Color.yellow;
        }
        else
        {
            status = "🔴 YOLO Capture: Recording";
            statusColor = Color.green;
        }
        
        titleStyle.normal.textColor = statusColor;
        GUI.Label(new Rect(panelX + 5, panelY + 8, panelWidth - 10, 20), status, titleStyle);
        
        // 진행률 (두 줄로 분리해서 가독성 향상)
        float progress = (float)totalCapturedImages / targetImageCount * 100f;
        string progressText = $"Frame {frameIndex} | Progress: {totalCapturedImages}/{targetImageCount} ({progress:F1}%)";
        string controlsText = $"[{toggleCaptureKey}] Start/Stop | [{pauseResumeKey}] Pause/Resume";
        
        infoStyle.normal.textColor = Color.white;
        GUI.Label(new Rect(panelX + 10, panelY + 35, panelWidth - 20, 18), progressText, infoStyle);
        
        // 컨트롤 안내 (별도 줄)
        infoStyle.normal.textColor = Color.cyan; // 컨트롤은 청록색으로 강조
        GUI.Label(new Rect(panelX + 10, panelY + 55, panelWidth - 20, 18), controlsText, infoStyle);
        
        // 프로그레스 바 (더 크게)
        if (captureEnabled)
        {
            float progressBar = (float)totalCapturedImages / targetImageCount;
            GUI.HorizontalScrollbar(new Rect(panelX + 15, panelY + 80, panelWidth - 30, 15), 0, progressBar, 0, 1);
        }
        
        // 빠른 상태 체크용 간단한 우상단 인디케이터
        if (captureEnabled && !isPaused)
        {
            GUI.backgroundColor = new Color(1f, 0f, 0f, 0.7f); // 빨간색
            GUI.Box(new Rect(Screen.width - 25, 10, 15, 15), "");
            GUI.backgroundColor = originalColor;
        }
    }

    private string GetCaptureBasePath()
    {
        // 프로젝트 루트 디렉토리 찾기
        string projectRoot = Path.GetDirectoryName(Application.dataPath);
        return Path.Combine(projectRoot, "data", "yolo_capture");
    }

    private string GetCameraCapturePath(Camera cam)
    {
        return Path.Combine(GetCaptureBasePath(), cam.name);
    }

    void CaptureImage(Camera cam, int index)
    {
        string dir = GetCameraCapturePath(cam);
        Directory.CreateDirectory(dir);
        
        string filename = $"frame_{index:D5}.png";
        string path = Path.Combine(dir, filename);
        
        RenderTexture rt = new RenderTexture(imageWidth, imageHeight, 24);
        cam.targetTexture = rt;
        Texture2D image = new Texture2D(imageWidth, imageHeight, TextureFormat.RGB24, false);

        cam.Render();
        RenderTexture.active = rt;
        image.ReadPixels(new Rect(0, 0, imageWidth, imageHeight), 0, 0);
        image.Apply();

        cam.targetTexture = null;
        RenderTexture.active = null;
        Destroy(rt);

        File.WriteAllBytes(path, image.EncodeToPNG());

        Debug.Log($"[Capture] Saved image frame {index} for {cam.name}");
    }

    void GenerateYOLOLabel(Camera cam, int index)
    {
        string dir = GetCameraCapturePath(cam);
        Directory.CreateDirectory(dir);
        
        string filename = $"frame_{index:D5}.txt";
        string path = Path.Combine(dir, filename);
        
        StringBuilder labels = new StringBuilder();
        
        // 🎯 라벨링할 때도 캡처와 동일한 1920x1080 RenderTexture 사용
        RenderTexture rt = new RenderTexture(1920, 1080, 24);
        RenderTexture originalTarget = cam.targetTexture;
        
        cam.targetTexture = rt;
        
        // 간단한 FindGameObjectsWithTag 방식
        labels.AppendLine(GenerateClassLabels(cam, "Flock", index));
        labels.AppendLine(GenerateClassLabels(cam, "Airplane", index));
        
        // 원래 상태로 복원
        cam.targetTexture = originalTarget;
        Destroy(rt);

        File.WriteAllText(path, labels.ToString());
        
        // 디버그 로그
        if (index % 100 == 0)
        {
            Debug.Log($"[Label] {cam.name} Frame {index}: {labels.Length} labels");
        }
    }

    private string GenerateClassLabels(Camera cam, string tag, int frameNumber)
    {
        StringBuilder labels = new StringBuilder();
        
        GameObject[] objects = GameObject.FindGameObjectsWithTag(tag);
        int validBoxes = 0;
        int invalidBoxes = 0;
        int outOfFrustumBoxes = 0;
        int tooSmallBoxes = 0;
        
        // 디버그: 찾은 객체들 정보 출력
        string objectNames = "";
        for (int i = 0; i < objects.Length; i++)
        {
            objectNames += $"'{objects[i].name}'";
            if (i < objects.Length - 1) objectNames += ", ";
        }
        Debug.Log($"[DETECTION] {tag} - Found {objects.Length} objects: [{objectNames}]");

        foreach (GameObject obj in objects)
        {
            // 🚫 관리 객체들 필터링 (실제 게임 객체만 감지)
            if (IsManagerObject(obj.name))
            {
                continue; // 관리 객체는 건너뛰기
            }
            
            // 🎯 중심점 계산: Flock은 Transform, 나머지는 Bounds 사용
            Vector3 centerWorld;
            
            // 🔧 수정: 모든 객체에 대해 Transform position을 우선 사용
            // (GameObject의 Transform이 일반적으로 가장 정확한 중심점)
            centerWorld = obj.transform.position;
            
            // Bounds와 Transform 위치 비교 로깅
            Bounds centerBounds = GetCombinedBounds(obj);
            if (centerBounds.size != Vector3.zero)
            {
                Vector3 boundsCenter = centerBounds.center;
                float distance = Vector3.Distance(centerWorld, boundsCenter);
                Debug.Log($"[{tag.ToUpper()}-CENTER-COMPARE] '{obj.name}' - Transform({centerWorld.x:F1}, {centerWorld.y:F1}, {centerWorld.z:F1}) vs Bounds({boundsCenter.x:F1}, {boundsCenter.y:F1}, {boundsCenter.z:F1}) Distance: {distance:F1}m");
                
                // Transform과 Bounds 중심이 많이 다르면 경고
                if (distance > 10f)
                {
                    Debug.LogWarning($"[{tag.ToUpper()}-CENTER-WARNING] '{obj.name}' - Large difference between Transform and Bounds center: {distance:F1}m");
                }
            }
            else
            {
                Debug.Log($"[{tag.ToUpper()}-CENTER-TRANSFORM-ONLY] '{obj.name}' - Using transform position (no bounds): ({centerWorld.x:F1}, {centerWorld.y:F1}, {centerWorld.z:F1})");
            }
            
            // 카메라 좌절도 체크 (간단한 거리 기반) - 비행기는 더 멀리서도 감지
            float distanceToCamera = Vector3.Distance(cam.transform.position, centerWorld);
            float maxDistance = (tag == "Airplane") ? 3000f : 1000f; // 비행기는 3km까지 감지
            if (distanceToCamera > maxDistance)
            {
                outOfFrustumBoxes++;
                Debug.Log($"[DISTANCE-SKIP] {tag} '{obj.name}' - Distance({distanceToCamera:F1}m) > Max({maxDistance:F1}m)");
                continue;
            }

            // 🚨 새로운 접근법: WorldToScreenPoint 사용
            Vector3 screenPoint = cam.WorldToScreenPoint(centerWorld);
            
            // 🔍 스크린 좌표 디버깅
            Debug.Log($"[SCREEN-DEBUG-1] {tag} '{obj.name}' - World Position: ({centerWorld.x:F2}, {centerWorld.y:F2}, {centerWorld.z:F2})");
            Debug.Log($"[SCREEN-DEBUG-2] {tag} '{obj.name}' - Screen Point: ({screenPoint.x:F1}, {screenPoint.y:F1}, {screenPoint.z:F1})");
            Debug.Log($"[SCREEN-DEBUG-3] {tag} '{obj.name}' - Camera Resolution: {cam.pixelWidth}x{cam.pixelHeight}");
            
            // 화면 뒤에 있으면 건너뛰기
            if (screenPoint.z <= 0)
            {
                Debug.Log($"[SCREEN-SKIP-BEHIND] {tag} '{obj.name}' - Behind camera (z={screenPoint.z:F2})");
                outOfFrustumBoxes++;
                continue;
            }
            
            // 🎯 스크린 좌표를 정규화 (RenderTexture 설정으로 자동으로 1920x1080)
            float normalizedX = screenPoint.x / cam.pixelWidth;
            float normalizedY = screenPoint.y / cam.pixelHeight;
            
            Debug.Log($"[SCREEN-DEBUG-4] {tag} '{obj.name}' - Normalized Screen: ({normalizedX:F6}, {normalizedY:F6}) [RenderTexture: {cam.pixelWidth}x{cam.pixelHeight}]");
            
            // 화면 밖 체크 (약간의 여유 허용)
            if (normalizedX < -0.2f || normalizedX > 1.2f || normalizedY < -0.2f || normalizedY > 1.2f)
            {
                Debug.Log($"[SCREEN-SKIP-OUT] {tag} '{obj.name}' - Outside screen bounds: ({normalizedX:F3}, {normalizedY:F3})");
                outOfFrustumBoxes++;
                continue;
            }
            
            // 🔧 YOLO 좌표 변환
            // Screen: (0,0)=왼쪽아래, (1,1)=오른쪽위  
            // YOLO: (0,0)=왼쪽위, (1,1)=오른쪽아래
            float x = normalizedX;              // X축은 그대로
            float y = 1f - normalizedY;         // Y축만 뒤집기
            
            // 🔍 최종 변환 결과 로그
            Debug.Log($"[SCREEN-FINAL] {tag} '{obj.name}' - Screen({normalizedX:F6}, {normalizedY:F6}) → YOLO({x:F6}, {y:F6}) [Camera: {cam.name}]");
            
            // 🎯 실제 크기 기반 바운딩 박스 계산 (WorldToScreenPoint 사용)
            float boxWidth, boxHeight;
            
            // 🎯 새떼의 실제 최상단/최하단 Y좌표를 사용한 정확한 바운딩 박스
            if (tag == "Flock")
            {
                Bounds flockBounds = GetCombinedBounds(obj);
                if (flockBounds.size != Vector3.zero)
                {
                    // 새떼의 최상단과 최하단 월드 좌표
                    Vector3 topWorldPoint = new Vector3(flockBounds.center.x, flockBounds.max.y, flockBounds.center.z);
                    Vector3 bottomWorldPoint = new Vector3(flockBounds.center.x, flockBounds.min.y, flockBounds.center.z);
                    
                    // 스크린 좌표로 변환
                    Vector3 topScreenPoint = cam.WorldToScreenPoint(topWorldPoint);
                    Vector3 bottomScreenPoint = cam.WorldToScreenPoint(bottomWorldPoint);
                    
                    if (topScreenPoint.z > 0 && bottomScreenPoint.z > 0) // 둘 다 카메라 앞에 있으면
                    {
                        // 🔍 상세한 디버깅
                        Debug.Log($"[FLOCK-Y-RANGE] '{obj.name}' - TopWorld({topWorldPoint.x:F1}, {topWorldPoint.y:F1}, {topWorldPoint.z:F1}) → TopScreen({topScreenPoint.x:F1}, {topScreenPoint.y:F1})");
                        Debug.Log($"[FLOCK-Y-RANGE] '{obj.name}' - BottomWorld({bottomWorldPoint.x:F1}, {bottomWorldPoint.y:F1}, {bottomWorldPoint.z:F1}) → BottomScreen({bottomScreenPoint.x:F1}, {bottomScreenPoint.y:F1})");
                        
                        // 🎯 실제 새떼의 Y 범위를 정규화
                        float topY = topScreenPoint.y / cam.pixelHeight;
                        float bottomY = bottomScreenPoint.y / cam.pixelHeight;
                        
                        // YOLO 좌표계로 변환 (Y축 뒤집기)
                        float yoloTopY = 1f - topY;      // 스크린 상단 → YOLO 상단
                        float yoloBottomY = 1f - bottomY; // 스크린 하단 → YOLO 하단
                        
                        // 바운딩 박스 Y축 중심과 높이 계산
                        float boxCenterY = (yoloTopY + yoloBottomY) / 2f;
                        float actualHeight = Mathf.Abs(yoloBottomY - yoloTopY);
                        
                        // X축 개선: flockBounds의 8개 꼭짓점 중에서 x축이 가장 작은/큰 꼭짓점 사용
                        Vector3[] corners = GetBoundsCorners(flockBounds);
                        
                        // x축이 가장 작은/큰 꼭짓점 찾기
                        Vector3 leftWorldPoint = corners[0];
                        Vector3 rightWorldPoint = corners[0];
                        
                        for (int i = 1; i < corners.Length; i++)
                        {
                            if (corners[i].x < leftWorldPoint.x)
                                leftWorldPoint = corners[i];
                            if (corners[i].x > rightWorldPoint.x)
                                rightWorldPoint = corners[i];
                        }
                        
                        // 스크린 좌표로 변환
                        Vector3 leftScreenPoint = cam.WorldToScreenPoint(leftWorldPoint);
                        Vector3 rightScreenPoint = cam.WorldToScreenPoint(rightWorldPoint);
                        
                        Debug.Log($"[FLOCK-X-RANGE-IMPROVED] '{obj.name}' - LeftWorld({leftWorldPoint.x:F1}, {leftWorldPoint.y:F1}, {leftWorldPoint.z:F1}) → LeftScreen({leftScreenPoint.x:F1}, {leftScreenPoint.y:F1})");
                        Debug.Log($"[FLOCK-X-RANGE-IMPROVED] '{obj.name}' - RightWorld({rightWorldPoint.x:F1}, {rightWorldPoint.y:F1}, {rightWorldPoint.z:F1}) → RightScreen({rightScreenPoint.x:F1}, {rightScreenPoint.y:F1})");
                        
                        // 🎯 실제 새떼의 X 범위를 정규화 (너비 계산용)
                        float leftX = leftScreenPoint.x / cam.pixelWidth;
                        float rightX = rightScreenPoint.x / cam.pixelWidth;
                        
                        // YOLO 좌표계로 변환 (X축은 그대로)
                        float yoloLeftX = leftX;
                        float yoloRightX = rightX;
                        
                        // 바운딩 박스 X축 너비 계산 (개선된 로직)
                        float actualWidth = Mathf.Abs(yoloRightX - yoloLeftX);
                        
                        // 바운딩 박스 X축 중심은 기존 로직 사용 (flockBounds.center 기반)
                        Vector3 centerScreenPoint = cam.WorldToScreenPoint(flockBounds.center);
                        float boxCenterX = centerScreenPoint.x / cam.pixelWidth;
                        
                        float distance = screenPoint.z;
                        
                        // 너비 패딩 (전체적으로 살짝 증가)
                        float widthPaddingFactor;
                        if (distance > 500f)      widthPaddingFactor = 2.5f; // 80% 너비 패딩 (살짝 증가)
                        else if (distance > 200f) widthPaddingFactor = 3.0f; // 100% 너비 패딩 (살짝 증가)
                        else if (distance > 100f) widthPaddingFactor = 3.5f; // 170% 너비 패딩 (살짝 증가)
                        else                      widthPaddingFactor = 4.0f; // 170% 너비 패딩 (살짝 증가)
                         
                        boxWidth = actualWidth * widthPaddingFactor;
                        
                        // 높이 패딩 (전체적으로 살짝 증가)
                        float heightPaddingFactor;
                        if (distance > 500f)      heightPaddingFactor = 3.5f; // 50% 높이 패딩 (살짝 증가)
                        else if (distance > 200f) heightPaddingFactor = 4.0f; // 70% 높이 패딩 (살짝 증가)
                        else if (distance > 100f) heightPaddingFactor = 4.5f; // 140% 높이 패딩 (살짝 증가)
                        else                      heightPaddingFactor = 5.0f; // 140% 높이 패딩 (살짝 증가)
                        
                        boxHeight = actualHeight * heightPaddingFactor;
                        
                        // X, Y 중심점을 실제 계산된 값으로 교체
                        x = boxCenterX;
                        y = boxCenterY;
                        
                        // 🚨 최소 크기 보장
                        float minWidth = distance > 500f ? 0.04f : distance > 200f ? 0.07f : 0.12f;
                        float minHeight = distance > 500f ? 0.03f : distance > 200f ? 0.05f : 0.08f;
                        
                        boxWidth = Mathf.Max(boxWidth, minWidth);
                        boxHeight = Mathf.Max(boxHeight, minHeight);
                        
                        Debug.Log($"[FLOCK-X-PRECISE] '{obj.name}' - X range: {yoloLeftX:F6} to {yoloRightX:F6} → Center: {boxCenterX:F6}, Width: {boxWidth:F6} [Padding: X{widthPaddingFactor:F1}]");
                        Debug.Log($"[FLOCK-Y-PRECISE] '{obj.name}' - Y range: {yoloTopY:F6} to {yoloBottomY:F6} → Center: {boxCenterY:F6}, Height: {boxHeight:F6} [Padding: Y{heightPaddingFactor:F1}]");
                        Debug.Log($"[FLOCK-FINAL-PRECISE] '{obj.name}' - Final bbox: ({x:F6}, {y:F6}) size: ({boxWidth:F6}, {boxHeight:F6}) [Distance: {distance:F1}m]");
                    }
                    else
                    {
                        // 카메라 뒤에 있으면 거리별 기본 크기
                        float distance = screenPoint.z;
                        boxWidth = distance > 500f ? 0.06f : distance > 200f ? 0.10f : 0.15f;
                        boxHeight = distance > 500f ? 0.045f : distance > 200f ? 0.075f : 0.12f;
                        Debug.Log($"[FLOCK-BEHIND-CAM] '{obj.name}' - Behind camera, using default size: {boxWidth:F6}x{boxHeight:F6}");
                    }
                }
                else
                {
                    // 바운드 없으면 거리별 기본 크기
                    float distance = screenPoint.z;
                    boxWidth = distance > 500f ? 0.06f : distance > 200f ? 0.10f : 0.15f;
                    boxHeight = distance > 500f ? 0.045f : distance > 200f ? 0.075f : 0.12f;
                    Debug.Log($"[FLOCK-NO-BOUNDS] '{obj.name}' - No bounds, using default size: {boxWidth:F6}x{boxHeight:F6}");
                }
            }
            else
            {
                // 🎯 비행기도 새떼와 동일한 정확한 바운딩 박스 계산 방식 적용
                if (tag == "Airplane")
                {
                    float distance = screenPoint.z;
                        Bounds objBounds = GetCombinedBounds(obj);
                    
                        if (objBounds.size != Vector3.zero)
                        {
                        // 🎯 비행기의 실제 최좌/우단, 최상/하단 월드 좌표 계산
                        Vector3 leftWorldPoint = new Vector3(objBounds.min.x, objBounds.center.y, objBounds.center.z);
                        Vector3 rightWorldPoint = new Vector3(objBounds.max.x, objBounds.center.y, objBounds.center.z);
                        Vector3 topWorldPoint = new Vector3(objBounds.center.x, objBounds.max.y, objBounds.center.z);
                        Vector3 bottomWorldPoint = new Vector3(objBounds.center.x, objBounds.min.y, objBounds.center.z);
                        
                        // 스크린 좌표로 변환
                        Vector3 leftScreenPoint = cam.WorldToScreenPoint(leftWorldPoint);
                        Vector3 rightScreenPoint = cam.WorldToScreenPoint(rightWorldPoint);
                        Vector3 topScreenPoint = cam.WorldToScreenPoint(topWorldPoint);
                        Vector3 bottomScreenPoint = cam.WorldToScreenPoint(bottomWorldPoint);
                        
                        Debug.Log($"[AIRPLANE-PRECISE-DEBUG] '{obj.name}' - LeftWorld({leftWorldPoint.x:F1}, {leftWorldPoint.y:F1}, {leftWorldPoint.z:F1}) → LeftScreen({leftScreenPoint.x:F1}, {leftScreenPoint.y:F1})");
                        Debug.Log($"[AIRPLANE-PRECISE-DEBUG] '{obj.name}' - RightWorld({rightWorldPoint.x:F1}, {rightWorldPoint.y:F1}, {rightWorldPoint.z:F1}) → RightScreen({rightScreenPoint.x:F1}, {rightScreenPoint.y:F1})");
                        Debug.Log($"[AIRPLANE-PRECISE-DEBUG] '{obj.name}' - TopWorld({topWorldPoint.x:F1}, {topWorldPoint.y:F1}, {topWorldPoint.z:F1}) → TopScreen({topScreenPoint.x:F1}, {topScreenPoint.y:F1})");
                        Debug.Log($"[AIRPLANE-PRECISE-DEBUG] '{obj.name}' - BottomWorld({bottomWorldPoint.x:F1}, {bottomWorldPoint.y:F1}, {bottomWorldPoint.z:F1}) → BottomScreen({bottomScreenPoint.x:F1}, {bottomScreenPoint.y:F1})");
                        
                        if (leftScreenPoint.z > 0 && rightScreenPoint.z > 0 && topScreenPoint.z > 0 && bottomScreenPoint.z > 0)
                        {
                            // 🎯 실제 비행기의 X, Y 범위를 정규화
                            float leftX = leftScreenPoint.x / cam.pixelWidth;
                            float rightX = rightScreenPoint.x / cam.pixelWidth;
                            float topY = topScreenPoint.y / cam.pixelHeight;
                            float bottomY = bottomScreenPoint.y / cam.pixelHeight;
                            
                            // YOLO 좌표계로 변환 (Y축 뒤집기)
                            float yoloLeftX = leftX;
                            float yoloRightX = rightX;
                            float yoloTopY = 1f - topY;      // 스크린 상단 → YOLO 상단
                            float yoloBottomY = 1f - bottomY; // 스크린 하단 → YOLO 하단
                            
                            // 바운딩 박스 중심과 크기 계산
                            float boxCenterX = (yoloLeftX + yoloRightX) / 2f;
                            float boxCenterY = (yoloTopY + yoloBottomY) / 2f;
                            float actualWidth = Mathf.Abs(yoloRightX - yoloLeftX);
                            float actualHeight = Mathf.Abs(yoloBottomY - yoloTopY);
                            
                            Debug.Log($"[AIRPLANE-PRECISE-RANGE] '{obj.name}' - X range: {yoloLeftX:F6} to {yoloRightX:F6} → Center: {boxCenterX:F6}, Width: {actualWidth:F6}");
                            Debug.Log($"[AIRPLANE-PRECISE-RANGE] '{obj.name}' - Y range: {yoloTopY:F6} to {yoloBottomY:F6} → Center: {boxCenterY:F6}, Height: {actualHeight:F6}");
                            
                            // 거리별 패딩 적용
                            float airplaneWidthPadding, airplaneHeightPadding;
                            if (distance > 500f) // 원거리
                            {
                                airplaneWidthPadding = 3f;  
                                airplaneHeightPadding = 3f; 
                            }
                            else if (distance > 200f) // 중거리
                            {
                                airplaneWidthPadding = 3.5f;  
                                airplaneHeightPadding = 3.5f; 
                            }
                            else if (distance > 100f) // 근거리
                            {
                                airplaneWidthPadding = 4f;  
                                airplaneHeightPadding = 4f; 
                            }
                            else // 초근거리
                            {
                                airplaneWidthPadding = 6f;  
                                airplaneHeightPadding = 6f; 
                            }
                            
                            boxWidth = actualWidth * airplaneWidthPadding;
                            boxHeight = actualHeight * airplaneHeightPadding;
                            
                            // X, Y 중심점을 실제 계산된 값으로 교체
                            x = boxCenterX;
                            y = boxCenterY;
                            
                            // 🚨 비행기 최소 크기 강제 보장
                            float minWidth = distance > 500f ? 0.03f : distance > 200f ? 0.05f : 0.08f;
                            float minHeight = distance > 500f ? 0.02f : distance > 200f ? 0.03f : 0.05f;
                            
                            boxWidth = Mathf.Max(boxWidth, minWidth);
                            boxHeight = Mathf.Max(boxHeight, minHeight);
                            
                            // 비행기는 너비:높이 비율 유지
                            if (boxHeight < boxWidth * 0.4f)
                            {
                                boxHeight = boxWidth * 0.5f;
                                Debug.Log($"[AIRPLANE-HEIGHT-FIX] '{obj.name}' - Height adjusted to {boxHeight:F6}");
                            }
                            
                            Debug.Log($"[AIRPLANE-PRECISE-FINAL] '{obj.name}' - Final bbox: ({x:F6}, {y:F6}) size: ({boxWidth:F6}, {boxHeight:F6}) [Distance: {distance:F1}m, Padding: X{airplaneWidthPadding:F1} Y{airplaneHeightPadding:F1}]");
                        }
                        else
                        {
                            // 일부 포인트가 카메라 뒤에 있으면 거리별 기본 크기 사용
                            boxWidth = distance > 500f ? 0.04f : distance > 200f ? 0.06f : 0.08f;
                            boxHeight = distance > 500f ? 0.025f : distance > 200f ? 0.04f : 0.05f;
                            Debug.Log($"[AIRPLANE-BEHIND-CAM] '{obj.name}' - Some points behind camera, using default size: {boxWidth:F6}x{boxHeight:F6} [Distance: {distance:F1}m]");
                        }
                    }
                    else
                    {
                        // 바운드 없으면 거리별 기본 크기
                        boxWidth = distance > 500f ? 0.04f : distance > 200f ? 0.06f : 0.08f;
                        boxHeight = distance > 500f ? 0.025f : distance > 200f ? 0.04f : 0.05f;
                        Debug.Log($"[AIRPLANE-NO-BOUNDS] '{obj.name}' - No bounds, using default size: {boxWidth:F6}x{boxHeight:F6} [Distance: {distance:F1}m]");
                    }
                }
                else
                {
                    // 다른 객체들은 실제 바운드 사용
                    Bounds objBounds = GetCombinedBounds(obj);
                    if (objBounds.size != Vector3.zero)
                    {
                        // 실제 객체 범위를 스크린 좌표로 변환 후 정규화
                        Vector3 boundsMinScreen = cam.WorldToScreenPoint(objBounds.min);
                        Vector3 boundsMaxScreen = cam.WorldToScreenPoint(objBounds.max);
                        
                        if (boundsMinScreen.z > 0 && boundsMaxScreen.z > 0) // 둘 다 카메라 앞에 있으면
                        {
                            float actualWidth = Mathf.Abs(boundsMaxScreen.x - boundsMinScreen.x) / cam.pixelWidth;
                            float actualHeight = Mathf.Abs(boundsMaxScreen.y - boundsMinScreen.y) / cam.pixelHeight;
                            
                            boxWidth = actualWidth * 1.2f; // 20% 패딩
                            boxHeight = actualHeight * 1.2f;
                            
                            // 최소 크기 보장
                            float minSize = GetBaseSize(tag) * 0.3f; // 기본 크기의 30%
                            boxWidth = Mathf.Max(boxWidth, minSize);
                            boxHeight = Mathf.Max(boxHeight, minSize * 0.75f);
                            
                            Debug.Log($"[{tag.ToUpper()}-ACTUAL] '{obj.name}' - Raw({actualWidth:F3}x{actualHeight:F3}) → Final({boxWidth:F3}x{boxHeight:F3}) [Distance: {screenPoint.z:F1}m]");
                        }
                        else
                        {
                            // 거리 문제가 있으면 기본 크기 사용
                            boxWidth = GetBaseSize(tag);
                            boxHeight = boxWidth * 0.75f;
                            Debug.Log($"[{tag.ToUpper()}-FALLBACK] '{obj.name}' - Using default size: {boxWidth:F3}x{boxHeight:F3}");
                        }
                    }
                    else
                    {
                        // 바운드를 찾을 수 없으면 기본 크기 사용
                        boxWidth = GetBaseSize(tag);
                        boxHeight = boxWidth * 0.75f;
                        Debug.Log($"[{tag.ToUpper()}-NO-BOUNDS] '{obj.name}' - No bounds found, using default: {boxWidth:F3}x{boxHeight:F3}");
                    }
                }
            }
            
            // 최소/최대 크기 제한
            boxWidth = Mathf.Clamp(boxWidth, 0.02f, maxBoundingBoxWidth);
            boxHeight = Mathf.Clamp(boxHeight, 0.015f, maxBoundingBoxHeight);
            
            // 🎯 새떼는 이제 실제 Y 범위 기반으로 정확히 계산되므로 추가 조정 불필요
            if (tag == "Flock")
            {
                Debug.Log($"[FLOCK-PRECISE-POSITIONING] '{obj.name}' - Using actual bird Y-range, no artificial adjustment needed");
            }
            
                         Debug.Log($"[DYNAMIC-SIZE] {tag} '{obj.name}' - Size({boxWidth:F3}x{boxHeight:F3}) Distance({screenPoint.z:F1}m)");
             
             // 🎯 화면 외곽 새떼 처리 개선: 실제 새떼 위치 기반 정확한 라벨링
             float boxLeft = x - boxWidth/2;
             float boxRight = x + boxWidth/2;
             float boxTop = y - boxHeight/2;
             float boxBottom = y + boxHeight/2;
             
             // 바운딩 박스가 완전히 화면 밖에 있는 경우만 제외
             if (boxRight <= 0 || boxLeft >= 1 || boxBottom <= 0 || boxTop >= 1)
             {
                 outOfFrustumBoxes++;
                 Debug.Log($"[SKIP-OUT-OF-BOUNDS] {tag} '{obj.name}' - Completely outside screen bounds");
                 continue;
             }
             
             // 🔧 외곽 새떼 문제 해결: 중심점과 크기 모두 실제 값 유지
             // (화면 밖에 있는 새떼도 정확한 위치와 크기로 라벨링)
             
             // 화면과 교차하는 부분이 있는지만 확인 (최소 10% 이상 겹쳐야 함)
             float visibleLeft = Mathf.Max(boxLeft, 0);
             float visibleRight = Mathf.Min(boxRight, 1);
             float visibleTop = Mathf.Max(boxTop, 0);
             float visibleBottom = Mathf.Min(boxBottom, 1);
             
             float visibleWidth = visibleRight - visibleLeft;
             float visibleHeight = visibleBottom - visibleTop;
             float visibleArea = visibleWidth * visibleHeight;
             float totalArea = boxWidth * boxHeight;
             
             // 보이는 영역이 전체 박스의 10% 미만이면 제외
             if (totalArea > 0 && visibleArea / totalArea < 0.1f)
             {
                 tooSmallBoxes++;
                 Debug.Log($"[SKIP-TINY-VISIBLE] {tag} '{obj.name}' - Visible area too small: {visibleArea:F4}/{totalArea:F4} = {(visibleArea/totalArea*100):F1}%");
                 continue;
             }
             
             // 🎯 중심점과 크기는 실제 계산된 값 그대로 사용 (클램핑/클리핑 없음)
             // → 이렇게 해야 화면 외곽 새떼도 정확한 위치에 라벨링됨
             
             Debug.Log($"[FINAL-BBOX-ACCURATE] {tag} '{obj.name}' - Center({x:F6}, {y:F6}) Size({boxWidth:F6}x{boxHeight:F6}) [Visible: {(visibleArea/totalArea*100):F1}%]");
             
             // YOLO 포맷으로 라벨 추가
            int classId = tag == "Flock" ? 0 : 1;
            labels.AppendLine($"{classId} {x:F6} {y:F6} {boxWidth:F6} {boxHeight:F6}");
            validBoxes++;
        }
        
        // 통계 로그
        Debug.Log($"[YOLO] {tag} - Valid: {validBoxes}, Invalid: {invalidBoxes}, OutOfFrustum: {outOfFrustumBoxes}, TooSmall: {tooSmallBoxes}");
        
        return labels.ToString();
    }

    /// <summary>
    /// 관리 객체인지 확인하는 함수
    /// </summary>
    private bool IsManagerObject(string objectName)
    {
        // 관리 객체 이름들 (실제 게임 객체가 아님)
        string[] managerNames = {
            "FlockManager",
            "BirdSpawner", 
            "AirplaneManager",
            "AIrplaneManager"  // 오타가 있을 수도 있어서 둘 다 포함
        };
        
        foreach (string managerName in managerNames)
        {
            if (objectName.Equals(managerName, System.StringComparison.OrdinalIgnoreCase))
            {
                return true;
            }
        }
        
        return false;
    }

    /// <summary>
    /// 객체가 카메라 좌절도 내에 있는지 확인
    /// </summary>
    bool IsObjectInCameraFrustum(Camera cam, Bounds bounds)
    {
        // Frustum planes 가져오기
        Plane[] frustumPlanes = GeometryUtility.CalculateFrustumPlanes(cam);
        
        // 바운딩 박스가 좌절도와 교차하는지 확인
        return GeometryUtility.TestPlanesAABB(frustumPlanes, bounds);
    }

    /// <summary>
    /// 바운딩 박스의 8개 모서리 좌표 계산
    /// </summary>
    Vector3[] GetBoundsCorners(Bounds bounds)
    {
        Vector3[] corners = new Vector3[8];
        Vector3 center = bounds.center;
        Vector3 size = bounds.size * 0.5f;
        
        corners[0] = center + new Vector3(-size.x, -size.y, -size.z); // 000
        corners[1] = center + new Vector3(+size.x, -size.y, -size.z); // 100
        corners[2] = center + new Vector3(-size.x, +size.y, -size.z); // 010
        corners[3] = center + new Vector3(+size.x, +size.y, -size.z); // 110
        corners[4] = center + new Vector3(-size.x, -size.y, +size.z); // 001
        corners[5] = center + new Vector3(+size.x, -size.y, +size.z); // 101
        corners[6] = center + new Vector3(-size.x, +size.y, +size.z); // 011
        corners[7] = center + new Vector3(+size.x, +size.y, +size.z); // 111
        
        return corners;
    }

    Bounds GetCombinedBounds(GameObject go)
    {
        Renderer[] renderers = go.GetComponentsInChildren<Renderer>();
        if (renderers.Length == 0) return new Bounds();

        Bounds bounds = renderers[0].bounds;
        for (int i = 1; i < renderers.Length; i++)
        {
            bounds.Encapsulate(renderers[i].bounds);
        }

        return bounds;
    }

    public void GenerateCSRNetCSV(Camera cam, int frameIndex)
    {
        // 옵션이 꺼져있으면 실행하지 않음
        if (!generateCSRNetData) return;
        
        string dir = Path.Combine("Captures", "csrnet", cam.name);
        if (!Directory.Exists(dir)) Directory.CreateDirectory(dir);

        // Flock만 포함
        List<Vector2> flockCenters = GetObjectCenters(cam, "Flock");

        List<string> lines = new();
        foreach (var pt in flockCenters)
        {
            lines.Add($"{pt.x:F2},{pt.y:F2}");
        }

        File.WriteAllLines(Path.Combine(dir, $"frame_{frameIndex:D5}.csv"), lines.ToArray());
        Debug.Log($"[CSRNet] Saved center CSV for frame {frameIndex} - {cam.name}");
    }
        
    List<Vector2> GetObjectCenters(Camera cam, string tag)
    {
        List<Vector2> result = new();
        GameObject[] objects = GameObject.FindGameObjectsWithTag(tag);

        foreach (GameObject obj in objects)
        {
            Bounds bounds = GetCombinedBounds(obj);
            if (bounds.size == Vector3.zero) continue;

            Vector3 center = cam.WorldToViewportPoint(bounds.center);
            if (float.IsNaN(center.x) || float.IsNaN(center.y)) continue;

            // Viewport (0~1) → Pixel 변환
            float px = center.x * imageWidth;
            float py = (1f - center.y) * imageHeight;

            if (px >= 0 && px <= imageWidth && py >= 0 && py <= imageHeight)
                result.Add(new Vector2(px, py));
        }

        return result;
    }

    /// <summary>
    /// Unity Inspector에서 현재 프레임 정보 확인용
    /// </summary>
    [ContextMenu("📊 Show Current Status")]
    void ShowCurrentStatus()
    {
        string statusText = captureEnabled ? (isPaused ? "일시정지됨" : "실행 중") : "중지됨";
        Debug.Log($"📊 [CaptureManager] 상태: {statusText}");
        Debug.Log($"📊 [CaptureManager] Current Frame: {frameIndex}, Total Images: {totalCapturedImages}");
        Debug.Log($"📊 [CaptureManager] Progress: {(float)totalCapturedImages/targetImageCount*100:F1}%");
        if (resumedFromFrame > 0)
        {
            Debug.Log($"📊 [CaptureManager] Resumed from frame: {resumedFromFrame}");
        }
        Debug.Log($"📊 [CaptureManager] Controls: [{toggleCaptureKey}] Start/Stop, [{pauseResumeKey}] Pause/Resume");
    }

    void OnDestroy()
    {
        // 컴포넌트 삭제시 캡처 중지
        if (captureCoroutine != null)
        {
            StopCoroutine(captureCoroutine);
        }
    }

    /// <summary>
    /// 객체 타입별 기본 크기 반환
    /// </summary>
         private float GetBaseSize(string tag)
     {
         switch (tag)
         {
             case "Flock":
                 return 0.18f; // 새떼는 더 큰 크기 (뷰포트의 18%) - 넓게 퍼진 새떼 커버
             case "Airplane":
                 return 0.08f; // 비행기는 큰 크기 (뷰포트의 8%)
             default:
                 return 0.05f; // 기본 크기 (뷰포트의 5%)
         }
     }

    [ContextMenu("🎬 Start Capture")]
    public void StartCapture()
    {
        if (captureCoroutine != null)
        {
            Debug.LogWarning("⚠️ [CaptureManager] 캡처가 이미 실행 중입니다!");
            return;
        }

        captureEnabled = true;
        isPaused = false;
        captureCoroutine = StartCoroutine(CaptureLoop());
        Debug.Log("🎬 [CaptureManager] 캡처 시작!");
    }

    [ContextMenu("🛑 Stop Capture")]
    public void StopCapture()
    {
        captureEnabled = false;
        isPaused = false;
        
        if (captureCoroutine != null)
        {
            StopCoroutine(captureCoroutine);
            captureCoroutine = null;
        }
        
        Debug.Log("🛑 [CaptureManager] 캡처 중지!");
    }

    [ContextMenu("🎮 Toggle Capture")]
    public void ToggleCapture()
    {
        if (captureEnabled)
        {
            StopCapture();
        }
        else
        {
            StartCapture();
        }
    }

    [ContextMenu("⏸️ Toggle Pause")]
    public void TogglePause()
    {
        if (!captureEnabled)
        {
            Debug.LogWarning("⚠️ [CaptureManager] 캡처가 실행 중이 아닙니다!");
            return;
        }

        isPaused = !isPaused;
        string status = isPaused ? "일시정지" : "재개";
        Debug.Log($"⏸️ [CaptureManager] 캡처 {status}!");
    }

    IEnumerator CaptureLoop()
    {
        while (captureEnabled)
        {
            // 일시정지 상태 체크
            if (isPaused)
            {
                yield return new WaitForSeconds(0.1f); // 짧은 대기
                continue;
            }

            // 목표 달성시 중지
            if (stopAtTarget && totalCapturedImages >= targetImageCount)
            {
                Debug.Log($"[CaptureManager] Target of {targetImageCount} images reached! Stopping capture.");
                StopCapture();
                break;
            }

            switch (captureMode)
            {
                case CaptureMode.YOLO:
                    CaptureAndLabelForYOLO(frameIndex);
                    totalCapturedImages += yoloCameras.Length;
                    break;
                case CaptureMode.Pipeline:
                    CaptureFor3DPipeline(frameIndex);
                    totalCapturedImages += pipelineCameras.Length;
                    break;
            }

            frameIndex++;
            
            // 진행상황 로그 (성능 모드에서는 더 적게)
            int logInterval = enablePerformanceMode ? 150 : 100;
            if (frameIndex % logInterval == 0)
            {
                float progress = (float)totalCapturedImages / targetImageCount * 100f;
                string resumeInfo = resumedFromFrame > 0 ? $" (Resumed from frame {resumedFromFrame:D5})" : "";
                Debug.Log($"[CaptureManager] Progress: {totalCapturedImages}/{targetImageCount} images ({progress:F1}%){resumeInfo}");
                
                // 성능 모드에서는 중간에 가비지 컬렉션
                if (enablePerformanceMode && frameIndex % 300 == 0)
                {
                    System.GC.Collect();
                }
            }

            yield return new WaitForSeconds(captureInterval);
        }
        
        // 코루틴 정리
        captureCoroutine = null;
    }

    public void CaptureAndLabelForYOLO(int index)
    {
        foreach (Camera cam in yoloCameras)
        {
            CaptureImage(cam, index);
            GenerateYOLOLabel(cam, index);
            
            // CSRNet 데이터 생성
            if (generateCSRNetData)
            {
                GenerateCSRNetCSV(cam, index);
            }
        }
    }

    public void CaptureFor3DPipeline(int index)
    {
        foreach (Camera cam in pipelineCameras)
        {
            CaptureImage(cam, index);
            
            // CSRNet 데이터 생성
            if (generateCSRNetData)
            {
                GenerateCSRNetCSV(cam, index);
            }
        }
    }

    private int FindLastFrameIndex()
    {
        int maxFrameIndex = 0;
        string basePath = GetCaptureBasePath();
        
        foreach (Camera cam in yoloCameras)
        {
            string dir = Path.Combine(basePath, cam.name);
            if (Directory.Exists(dir))
            {
                var files = Directory.GetFiles(dir, "frame_*.png");
                foreach (var file in files)
                {
                    string fileName = Path.GetFileNameWithoutExtension(file);
                    if (fileName.StartsWith("frame_") && fileName.Length == 11)
                    {
                        if (int.TryParse(fileName.Substring(6), out int frameNum))
                        {
                            maxFrameIndex = Mathf.Max(maxFrameIndex, frameNum);
                        }
                    }
                }
            }
        }
        
        return maxFrameIndex + 1;
    }

    private int CountExistingImages()
    {
        int count = 0;
        string basePath = GetCaptureBasePath();
        
        foreach (Camera cam in yoloCameras)
        {
            string dir = Path.Combine(basePath, cam.name);
            if (Directory.Exists(dir))
            {
                count += Directory.GetFiles(dir, "frame_*.png").Length;
            }
        }
        return count;
    }

    Vector3 ManualWorldToViewportPoint(Camera cam, Vector3 worldPosition)
    {
        // 1. 월드 좌표를 카메라 로컬 좌표로 변환
        Vector3 localPosition = cam.transform.InverseTransformPoint(worldPosition);
        
        // 2. 카메라 뒤쪽에 있으면 처리
        if (localPosition.z <= 0)
        {
            return new Vector3(0, 0, localPosition.z);
        }
        
        // 3. 투영 변환 (원근 투영)
        float fov = cam.fieldOfView * Mathf.Deg2Rad;
        float aspect = cam.aspect;
        float near = cam.nearClipPlane;
        float far = cam.farClipPlane;
        
        // NDC (Normalized Device Coordinates) 계산
        float x_ndc = localPosition.x / (localPosition.z * Mathf.Tan(fov * 0.5f) * aspect);
        float y_ndc = localPosition.y / (localPosition.z * Mathf.Tan(fov * 0.5f));
        
        // 4. NDC를 뷰포트 좌표로 변환 (-1~1 → 0~1)
        float x_viewport = (x_ndc + 1f) * 0.5f;
        float y_viewport = (y_ndc + 1f) * 0.5f;
        
        return new Vector3(x_viewport, y_viewport, localPosition.z);
    }
}
