using UnityEngine;
using UnityEngine.InputSystem;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System;

// ===================================================================
// 📸 Camera Parameter Serialization Structures
// These structs are needed because Unity's JsonUtility cannot serialize
// native Vector or Matrix types directly.
// ===================================================================
[System.Serializable]
public struct SerializableVector2
{
    public float x, y;
    public SerializableVector2(Vector2 v) { x = v.x; y = v.y; }
}

[System.Serializable]
public struct SerializableVector3
{
    public float x, y, z;
    public SerializableVector3(Vector3 v) { x = v.x; y = v.y; z = v.z; }
}

[System.Serializable]
public struct SerializableQuaternion
{
    public float x, y, z, w;
    public SerializableQuaternion(Quaternion q) { x = q.x; y = q.y; z = q.z; w = q.w; }
}

[System.Serializable]
public struct SerializableMatrix4x4
{
    public float m00, m01, m02, m03;
    public float m10, m11, m12, m13;
    public float m20, m21, m22, m23;
    public float m30, m31, m32, m33;

    public SerializableMatrix4x4(Matrix4x4 m)
    {
        m00 = m.m00; m01 = m.m01; m02 = m.m02; m03 = m.m03;
        m10 = m.m10; m11 = m.m11; m12 = m.m12; m13 = m.m13;
        m20 = m.m20; m21 = m.m21; m22 = m.m22; m23 = m.m23;
        m30 = m.m30; m31 = m.m31; m32 = m.m32; m33 = m.m33;
    }
}

[System.Serializable]
public class CameraParameters
{
    public string cameraName;
    public int imageWidth;
    public int imageHeight;
    
    // --- Intrinsic Parameters ---
    public float fieldOfView_vertical; // Unity's FoV is vertical
    public SerializableVector2 sensorSize; // In millimeters
    
    // --- Extrinsic Parameters (Unity's Left-Handed World Space) ---
    public SerializableVector3 position_UnityWorld;
    public SerializableQuaternion rotation_UnityWorld;
    
    // --- Full Matrices (for advanced use) ---
    public string matrixCoordinateSystemNote = "All matrices below are in Unity's Left-Handed Coordinate System.";
    public SerializableMatrix4x4 worldToCameraMatrix; // View Matrix (V)
    public SerializableMatrix4x4 projectionMatrix;    // Projection Matrix (P)
    
    public string pythonConversionNote = "For Python/OpenCV, coordinate system conversion is required. Unity: LHS, Y-up. OpenCV: RHS, Y-down.";
}

public class SyncCaptureManager : MonoBehaviour
{
    [Header("🎬 Synchronized Video Recording System")]
    [Space(10)]
    
    [Header("Camera Configuration")]
    [Tooltip("두 대 이상의 카메라 (삼각측량용)")]
    public Camera[] recordingCameras;
    
    [Header("Recording Settings")]
    [Range(15, 60)]
    public int frameRate = 30;
    
    [Range(10, 300)]
    public int recordingDuration = 60; // 초
    
    [Header("Image Quality")]
    public int imageWidth = 1280;
    public int imageHeight = 720;
    
    [Range(50, 100)]
    public int jpegQuality = 90;
    
    [Header("Output Settings")]
    public bool saveAsSequence = true; // 프레임 시퀀스로 저장
    public bool generateVideoFiles = false; // FFmpeg 필요
    public bool saveTimestampFile = true; // 시간 동기화 정보
    
    [Header("Performance")]
    public bool enableMemoryOptimization = true;
    public bool showProgressInConsole = true;
    
    [Header("🎮 Recording Controls")]
    [Space(5)]
    public KeyCode startRecordingKey = KeyCode.R;
    public KeyCode stopRecordingKey = KeyCode.T;
    
    [Header("비행기 연동 자동 녹화")]
    [Tooltip("비행기 생성/소멸에 따라 자동으로 녹화 시작/종료")]
    public bool airplaneAutoRecording = false;
    [Tooltip("비행기 소멸 후 녹화 종료까지 대기 시간 (초)")]
    public float recordingStopDelay = 2f;
    
    [Header("경로 구분")]
    [Tooltip("녹화할 경로 이름 (폴더명에 포함됨)")]
    public string routeName = "Path_A";
    [Tooltip("경로별 폴더 구분 활성화")]
    public bool enableRouteBasedFolders = true;
    [Tooltip("사용 가능한 경로 목록")]
    public string[] availableRoutes = {"Path_A", "Path_B", "Path_C", "Path_D"};
    
    // Private variables
    private RenderTexture[] renderTextures;
    private Texture2D[] texture2Ds;
    private bool isRecording = false;
    private int currentFrame = 0;
    private string outputFolder;
    private List<double> frameTimestamps;
    private Coroutine recordingCoroutine;
    
    // UI Display
    private GUIStyle labelStyle;
    private bool showGUI = true;

    // 비행기 자동 녹화 관련
    private List<GameObject> trackedAirplanes = new List<GameObject>();
    private Coroutine stopRecordingCoroutine;

    void Start()
    {
        InitializeCapture();
        SetupGUIStyle();
        
        // 비행기 자동 녹화 모드 초기화
        if (airplaneAutoRecording)
        {
            StartCoroutine(MonitorAirplanes());
        }
    }

    void SetupGUIStyle()
    {
        labelStyle = new GUIStyle();
        labelStyle.fontSize = 16;
        labelStyle.normal.textColor = Color.white;
        labelStyle.fontStyle = FontStyle.Bold;
    }

    void InitializeCapture()
    {
        if (recordingCameras == null || recordingCameras.Length < 2)
        {
            Debug.LogError("❌ [SyncCapture] 삼각측량을 위해 최소 2대의 카메라가 필요합니다!");
            enabled = false;
            return;
        }

        // RenderTexture 및 Texture2D 배열 초기화
        renderTextures = new RenderTexture[recordingCameras.Length];
        texture2Ds = new Texture2D[recordingCameras.Length];
        frameTimestamps = new List<double>();

        for (int i = 0; i < recordingCameras.Length; i++)
        {
            if (recordingCameras[i] == null)
            {
                Debug.LogError($"❌ [SyncCapture] Camera {i}가 null입니다!");
                enabled = false;
                return;
            }

            renderTextures[i] = new RenderTexture(imageWidth, imageHeight, 24, RenderTextureFormat.ARGB32);
            texture2Ds[i] = new Texture2D(imageWidth, imageHeight, TextureFormat.RGB24, false);
        }

        Debug.Log($"✅ [SyncCapture] {recordingCameras.Length}대 카메라 동기화 캡처 시스템 초기화 완료");
        Debug.Log($"📊 [SyncCapture] 해상도: {imageWidth}x{imageHeight}, FPS: {frameRate}, 녹화시간: {recordingDuration}초");
    }

    // 🛩️ 비행기 모니터링 코루틴
    IEnumerator MonitorAirplanes()
    {
        Debug.Log("✈️ [SyncCapture] 비행기 자동 녹화 모니터링 시작");
        
        while (airplaneAutoRecording)
        {
            // 현재 씬의 모든 비행기 찾기
            GameObject[] currentAirplanes = GameObject.FindGameObjectsWithTag("Airplane");
            
            // 새로운 비행기 감지
            foreach (GameObject airplane in currentAirplanes)
            {
                if (!trackedAirplanes.Contains(airplane))
                {
                    OnAirplaneSpawned(airplane);
                }
            }
            
            // 소멸된 비행기 감지
            for (int i = trackedAirplanes.Count - 1; i >= 0; i--)
            {
                if (trackedAirplanes[i] == null)
                {
                    OnAirplaneDestroyed();
                    trackedAirplanes.RemoveAt(i);
                }
            }
            
            yield return new WaitForSeconds(0.5f); // 0.5초마다 체크
        }
    }
    
    // 🛩️ 비행기 생성 감지
    void OnAirplaneSpawned(GameObject airplane)
    {
        trackedAirplanes.Add(airplane);
        Debug.Log($"✈️ [SyncCapture] 비행기 생성 감지: {airplane.name}");
        
        // 🎯 새 비행기가 생성되면 항상 새로운 녹화 시작
        if (isRecording)
        {
            Debug.Log("🔄 [SyncCapture] 새 비행기 생성으로 이전 녹화 종료 후 새 녹화 시작");
            StopRecording();
            // 잠시 대기 후 새 녹화 시작 (파일 저장 완료 대기)
            StartCoroutine(StartNewRecordingAfterDelay());
        }
        else
        {
            Debug.Log("🎬 [SyncCapture] 비행기 생성으로 자동 녹화 시작");
            StartSynchronizedRecording();
        }
        
        // 녹화 종료 코루틴이 실행 중이면 취소
        if (stopRecordingCoroutine != null)
        {
            StopCoroutine(stopRecordingCoroutine);
            stopRecordingCoroutine = null;
            Debug.Log("⏸️ [SyncCapture] 녹화 종료 예약 취소");
        }
    }
    
    // 🎬 지연된 새 녹화 시작
    IEnumerator StartNewRecordingAfterDelay()
    {
        yield return new WaitForSeconds(0.5f); // 파일 저장 완료 대기
        if (!isRecording) // 다시 한 번 확인
        {
            Debug.Log("🎬 [SyncCapture] 새 녹화 시작");
            StartSynchronizedRecording();
        }
    }
    
    // 🛩️ 비행기 소멸 감지
    void OnAirplaneDestroyed()
    {
        Debug.Log($"✈️ [SyncCapture] 비행기 소멸 감지 (남은 비행기: {trackedAirplanes.Count - 1}개)");
        
        // 모든 비행기가 소멸되면 녹화 종료 예약
        if (trackedAirplanes.Count <= 1 && isRecording) // <= 1 because we haven't removed it yet
        {
            if (stopRecordingCoroutine != null)
            {
                StopCoroutine(stopRecordingCoroutine);
            }
            stopRecordingCoroutine = StartCoroutine(DelayedStopRecording());
        }
    }
    
    // 🛩️ 지연된 녹화 종료
    IEnumerator DelayedStopRecording()
    {
        Debug.Log($"⏰ [SyncCapture] {recordingStopDelay}초 후 녹화 종료 예정");
        yield return new WaitForSeconds(recordingStopDelay);
        
        // 다시 한 번 확인 (새 비행기가 생성되지 않았는지)
        if (trackedAirplanes.Count == 0 && isRecording)
        {
            Debug.Log("🛑 [SyncCapture] 모든 비행기 소멸로 자동 녹화 종료");
            StopRecording();
        }
        
        stopRecordingCoroutine = null;
    }
    
    // 🛩️ 외부에서 호출 가능한 메서드들
    public void EnableAirplaneAutoRecording()
    {
        if (!airplaneAutoRecording)
        {
            airplaneAutoRecording = true;
            StartCoroutine(MonitorAirplanes());
            Debug.Log("✅ [SyncCapture] 비행기 자동 녹화 모드 활성화");
        }
    }
    
    public void DisableAirplaneAutoRecording()
    {
        airplaneAutoRecording = false;
        trackedAirplanes.Clear();
        if (stopRecordingCoroutine != null)
        {
            StopCoroutine(stopRecordingCoroutine);
            stopRecordingCoroutine = null;
        }
        Debug.Log("❌ [SyncCapture] 비행기 자동 녹화 모드 비활성화");
    }

    void Update()
    {
        // 새로운 Input System 사용
        if (Keyboard.current != null)
        {
            // R 키로 녹화 시작
            if (Keyboard.current.rKey.wasPressedThisFrame && !isRecording)
            {
                StartSynchronizedRecording();
            }
            // T 키로 녹화 중지
            else if (Keyboard.current.tKey.wasPressedThisFrame && isRecording)
            {
                StopRecording();
            }
        }
    }

    void OnGUI()
    {
        if (!showGUI) return;

        // 🎯 상단 오른쪽으로 위치 이동
        float panelWidth = 350f;
        float panelHeight = 120f;
        float rightMargin = 10f;
        float topMargin = 10f;
        
        float panelX = Screen.width - panelWidth - rightMargin;
        float panelY = topMargin;

        // 녹화 상태 표시
        GUI.Box(new Rect(panelX, panelY, panelWidth, panelHeight), "");
        
        GUI.Label(new Rect(panelX + 10, panelY + 10, panelWidth - 20, 25), "🎬 Synchronized Video Capture", labelStyle);
        
        string status = isRecording ? $"🔴 Recording: {currentFrame}/{frameRate * recordingDuration}" 
                                    : "⚪ Ready to Record";
        
        // 비행기 자동 녹화 모드 표시
        if (airplaneAutoRecording)
        {
            status += $" | ✈️ Auto ({trackedAirplanes.Count})";
        }
        
        GUI.Label(new Rect(panelX + 10, panelY + 35, panelWidth - 20, 20), status);
        
        GUI.Label(new Rect(panelX + 10, panelY + 55, panelWidth - 20, 20), $"Cameras: {recordingCameras.Length} | Resolution: {imageWidth}x{imageHeight}");
        
        string controls = $"[{startRecordingKey}] Start | [{stopRecordingKey}] Stop";
        GUI.Label(new Rect(panelX + 10, panelY + 75, panelWidth - 20, 20), controls);
        
        if (isRecording)
        {
            float progress = (float)currentFrame / (frameRate * recordingDuration);
            GUI.HorizontalScrollbar(new Rect(panelX + 10, panelY + 95, panelWidth - 20, 20), 0, progress, 0, 1);
        }
    }

    private string GetCaptureBasePath()
    {
        // 프로젝트 루트 디렉토리 찾기
        string projectRoot = Path.GetDirectoryName(Application.dataPath);
        return Path.Combine(projectRoot, "data", "sync_capture");
    }

    [ContextMenu("🎬 Start Synchronized Recording")]
    public void StartSynchronizedRecording()
    {
        if (isRecording)
        {
            Debug.LogWarning("⚠️ [SyncCapture] 이미 녹화 중입니다!");
            return;
        }

        // 출력 폴더 생성 (밀리초 포함으로 더 정밀한 구분)
        string timestamp = DateTime.Now.ToString("yyyyMMdd_HHmmss_fff");
        string folderName;
        
        if (enableRouteBasedFolders && !string.IsNullOrEmpty(routeName))
        {
            folderName = $"Recording_{routeName}_{timestamp}";
        }
        else
        {
            folderName = $"Recording_{timestamp}";
        }
        
        outputFolder = Path.Combine(GetCaptureBasePath(), folderName);
        Directory.CreateDirectory(outputFolder);

        // 각 카메라별 폴더 생성 및 파라미터 저장
        for (int i = 0; i < recordingCameras.Length; i++)
        {
            string cameraName = recordingCameras[i].name;
            string cameraFolder = Path.Combine(outputFolder, cameraName);
            Directory.CreateDirectory(cameraFolder);
            
            // 🎯 카메라 파라미터 저장 로직 호출
            SaveCameraParameters(recordingCameras[i], outputFolder);
        }

        // 녹화 시작
        isRecording = true;
        currentFrame = 0;
        frameTimestamps.Clear();

        recordingCoroutine = StartCoroutine(RecordingLoop());
        
        Debug.Log($"🎬 [SyncCapture] 동기화 녹화 시작!");
        Debug.Log($"📁 [SyncCapture] 출력 폴더: {outputFolder}");
    }

    [ContextMenu("🛑 Stop Recording")]
    public void StopRecording()
    {
        if (!isRecording) return;

        isRecording = false;
        
        if (recordingCoroutine != null)
        {
            StopCoroutine(recordingCoroutine);
            recordingCoroutine = null;
        }

        // 타임스탬프 파일 저장
        if (saveTimestampFile)
        {
            SaveTimestampFile();
        }

        Debug.Log($"🛑 [SyncCapture] 녹화 중지! 총 {currentFrame} 프레임 저장");
        Debug.Log($"📁 [SyncCapture] 저장 위치: {outputFolder}");

        // 메모리 정리
        if (enableMemoryOptimization)
        {
            System.GC.Collect();
        }
    }

    IEnumerator RecordingLoop()
    {
        float frameInterval = 1f / frameRate;
        int totalFrames = recordingDuration * frameRate;

        while (isRecording && currentFrame < totalFrames)
        {
            double captureTime = Time.realtimeSinceStartupAsDouble;
            
            // 🎯 핵심: 모든 카메라 동시 캡처
            yield return StartCoroutine(CaptureAllCamerasSimultaneously(captureTime));
            
            currentFrame++;
            
            // 진행 상황 로그
            if (showProgressInConsole && currentFrame % (frameRate * 5) == 0) // 5초마다
            {
                float progress = (float)currentFrame / totalFrames * 100f;
                float elapsedTime = currentFrame / (float)frameRate;
                Debug.Log($"📹 [SyncCapture] Progress: {progress:F1}% ({elapsedTime:F1}s / {recordingDuration}s)");
            }
            
            // 메모리 최적화
            if (enableMemoryOptimization && currentFrame % (frameRate * 10) == 0) // 10초마다
            {
                Resources.UnloadUnusedAssets();
            }
            
            yield return new WaitForSeconds(frameInterval);
        }

        // 자동 중지
        StopRecording();
    }

    IEnumerator CaptureAllCamerasSimultaneously(double timestamp)
    {
        frameTimestamps.Add(timestamp);

        // Step 1: 모든 카메라의 원본 targetTexture 백업
        RenderTexture[] originalTargets = new RenderTexture[recordingCameras.Length];
        for (int i = 0; i < recordingCameras.Length; i++)
        {
            originalTargets[i] = recordingCameras[i].targetTexture;
            recordingCameras[i].targetTexture = renderTextures[i];
        }

        // Step 2: 동시에 모든 카메라 렌더링
        for (int i = 0; i < recordingCameras.Length; i++)
        {
            recordingCameras[i].Render();
        }

        // Step 3: 동시에 모든 텍스처 읽기 및 저장
        for (int i = 0; i < recordingCameras.Length; i++)
        {
            RenderTexture.active = renderTextures[i];
            texture2Ds[i].ReadPixels(new Rect(0, 0, imageWidth, imageHeight), 0, 0);
            texture2Ds[i].Apply();

            // 파일 저장
            byte[] imageData = texture2Ds[i].EncodeToJPG(jpegQuality);
            string cameraName = recordingCameras[i].name;
            
            // 🎯 Defensive Coding: Check if directory exists before writing
            string cameraFolder = Path.Combine(outputFolder, cameraName);
            if (!Directory.Exists(cameraFolder))
            {
                Debug.LogWarning($"[SyncCapture] Directory not found, recreating: {cameraFolder}");
                Directory.CreateDirectory(cameraFolder);
            }

            string filename = Path.Combine(cameraFolder, $"frame_{currentFrame:D6}.jpg");
            
            File.WriteAllBytes(filename, imageData);
        }

        RenderTexture.active = null;

        // Step 4: 원본 targetTexture 복원
        for (int i = 0; i < recordingCameras.Length; i++)
        {
            recordingCameras[i].targetTexture = originalTargets[i];
        }

        yield return null; // 한 프레임 대기
    }

    private void SaveCameraParameters(Camera cam, string folderPath)
    {
        CameraParameters parameters = new CameraParameters();

        // Populate the parameters
        parameters.cameraName = cam.name;
        parameters.imageWidth = imageWidth;
        parameters.imageHeight = imageHeight;
        
        parameters.fieldOfView_vertical = cam.fieldOfView;
        parameters.sensorSize = new SerializableVector2(cam.sensorSize);
        
        parameters.position_UnityWorld = new SerializableVector3(cam.transform.position);
        parameters.rotation_UnityWorld = new SerializableQuaternion(cam.transform.rotation);
        
        parameters.worldToCameraMatrix = new SerializableMatrix4x4(cam.worldToCameraMatrix);
        parameters.projectionMatrix = new SerializableMatrix4x4(cam.projectionMatrix);

        // Serialize to JSON and save
        string json = JsonUtility.ToJson(parameters, true);
        string filePath = Path.Combine(folderPath, $"{cam.name}_parameters.json");
        
        try
        {
            File.WriteAllText(filePath, json);
            Debug.Log($"💾 [SyncCapture] Camera parameters saved for '{cam.name}' to {filePath}");
        }
        catch (Exception e)
        {
            Debug.LogError($"❌ [SyncCapture] Failed to save camera parameters for '{cam.name}': {e.Message}");
        }
    }

    void SaveTimestampFile()
    {
        if (frameTimestamps.Count == 0) return;

        // 🎯 Defensive Coding: Check if directory exists before writing
        if (!Directory.Exists(outputFolder))
        {
            Debug.LogWarning($"[SyncCapture] Output folder not found, recreating: {outputFolder}");
            Directory.CreateDirectory(outputFolder);
        }

        string timestampFile = Path.Combine(outputFolder, "frame_timestamps.txt");
        List<string> lines = new List<string>();
        
        lines.Add("# Synchronized Frame Timestamps");
        lines.Add($"# Recording started at: {DateTime.Now:yyyy-MM-dd HH:mm:ss}");
        lines.Add($"# Total frames: {frameTimestamps.Count}");
        lines.Add($"# Frame rate: {frameRate} fps");
        lines.Add($"# Cameras: {string.Join(", ", System.Array.ConvertAll(recordingCameras, c => c.name))}");
        lines.Add("#");
        lines.Add("# Format: frame_number,timestamp_seconds");

        for (int i = 0; i < frameTimestamps.Count; i++)
        {
            lines.Add($"{i:D6},{frameTimestamps[i]:F6}");
        }

        File.WriteAllLines(timestampFile, lines);
        Debug.Log($"💾 [SyncCapture] 타임스탬프 파일 저장: {timestampFile}");
    }

    // 유틸리티 메소드들
    [ContextMenu("📊 Show Recording Info")]
    public void ShowRecordingInfo()
    {
        int totalFrames = recordingDuration * frameRate;
        float estimatedSize = (imageWidth * imageHeight * 3 * totalFrames * recordingCameras.Length) / (1024f * 1024f); // MB
        
        Debug.Log("📊 [SyncCapture] Recording Information:");
        Debug.Log($"  📷 Cameras: {recordingCameras.Length}");
        Debug.Log($"  🎞️ Total Frames: {totalFrames}");
        Debug.Log($"  📏 Resolution: {imageWidth} x {imageHeight}");
        Debug.Log($"  ⏱️ Duration: {recordingDuration} seconds @ {frameRate} fps");
        Debug.Log($"  💾 Estimated Size: ~{estimatedSize:F1} MB");
    }

    [ContextMenu("🔧 Validate Setup")]
    public void ValidateSetup()
    {
        bool isValid = true;
        
        if (recordingCameras == null || recordingCameras.Length < 2)
        {
            Debug.LogError("❌ [SyncCapture] 삼각측량을 위해 최소 2대의 카메라가 필요합니다!");
            isValid = false;
        }

        for (int i = 0; i < recordingCameras.Length; i++)
        {
            if (recordingCameras[i] == null)
            {
                Debug.LogError($"❌ [SyncCapture] Camera {i}가 null입니다!");
                isValid = false;
            }
        }

        if (frameRate < 15 || frameRate > 60)
        {
            Debug.LogWarning("⚠️ [SyncCapture] 권장 프레임 레이트: 15-60 fps");
        }

        if (isValid)
        {
            Debug.Log("✅ [SyncCapture] 설정 검증 완료! 녹화 준비됨");
        }
    }

    void OnDestroy()
    {
        // 리소스 정리
        if (renderTextures != null)
        {
            for (int i = 0; i < renderTextures.Length; i++)
            {
                if (renderTextures[i] != null)
                {
                    renderTextures[i].Release();
                }
            }
        }

        if (isRecording)
        {
            StopRecording();
        }
        
        // 비행기 자동 녹화 정리
        if (stopRecordingCoroutine != null)
        {
            StopCoroutine(stopRecordingCoroutine);
        }
    }

    // 디버그용 기즈모
    void OnDrawGizmos()
    {
        if (recordingCameras == null) return;

        // 카메라 위치와 방향 표시
        Gizmos.color = isRecording ? Color.red : Color.green;
        
        for (int i = 0; i < recordingCameras.Length; i++)
        {
            if (recordingCameras[i] != null)
            {
                Vector3 pos = recordingCameras[i].transform.position;
                Vector3 forward = recordingCameras[i].transform.forward * 2f;
                
                Gizmos.DrawWireSphere(pos, 0.5f);
                Gizmos.DrawRay(pos, forward);
                
                #if UNITY_EDITOR
                UnityEditor.Handles.Label(pos + Vector3.up * 1f, recordingCameras[i].name);
                #endif
            }
        }
    }
} 