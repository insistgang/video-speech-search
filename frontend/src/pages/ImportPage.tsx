import { FormEvent, useEffect, useMemo, useState } from "react";
import { api, ProcessMode, TaskRecord, VideoRecord } from "../lib/api";
import { deriveImportProgressSummary, mergeTaskRecords } from "../lib/importProgress";
import { formatErrorMessage, formatTaskStage, formatTaskStatus } from "../lib/presentation";

export function ImportPage() {
  const [videos, setVideos] = useState<VideoRecord[]>([]);
  const [tasks, setTasks] = useState<TaskRecord[]>([]);
  const [trackedTaskIds, setTrackedTaskIds] = useState<number[]>([]);
  const [videoPath, setVideoPath] = useState("");
  const [folderPath, setFolderPath] = useState("");
  const [processMode, setProcessMode] = useState<ProcessMode>("two_stage");
  const [busy, setBusy] = useState(false);
  const [pendingRequestLabel, setPendingRequestLabel] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("支持导入单个视频或整个文件夹，系统会自动排队处理。");

  function loadVideos() {
    api.listVideos().then(setVideos).catch(() => setVideos([]));
  }

  function loadTasks(limit = 50) {
    api.listTasks({ limit }).then(setTasks).catch(() => setTasks([]));
  }

  useEffect(() => {
    loadVideos();
    loadTasks();
  }, []);

  useEffect(() => {
    const trackedTaskIdsRef = { current: trackedTaskIds };

    const refresh = () => {
      api.listTasks({ limit: trackedTaskIdsRef.current.length > 0 ? 50 : 20 }).then((items) => {
        setTasks(items);
        const activeTrackedTask = items.some(
          (task) => trackedTaskIdsRef.current.includes(task.id) && (task.status === "pending" || task.status === "running")
        );
        if (activeTrackedTask) {
          loadVideos();
        }
      }).catch(() => setTasks([]));
    };

    refresh();
    const timer = window.setInterval(refresh, trackedTaskIds.length > 0 ? 1000 : 3000);
    return () => window.clearInterval(timer);
  }, [trackedTaskIds]);

  const trackedTasks = useMemo(
    () => tasks.filter((task) => trackedTaskIds.includes(task.id)).sort((left, right) => right.id - left.id),
    [tasks, trackedTaskIds]
  );
  const progressSummary = useMemo(
    () => deriveImportProgressSummary(trackedTasks, pendingRequestLabel),
    [trackedTasks, pendingRequestLabel]
  );

  async function onImportVideo(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setPendingRequestLabel("正在提交单视频导入请求");
    setError("");
    try {
      const result = await api.importVideo(videoPath, processMode);
      setMessage(`已加入队列：${result.video.filename}，任务编号 #${result.task.id}，处理模式：${processMode === "quick" ? "快速扫描" : processMode === "two_stage" ? "标准扫描" : "深度扫描"}。`);
      setTrackedTaskIds((current) => Array.from(new Set([result.task.id, ...current])));
      setTasks((current) => mergeTaskRecords(current, [result.task]));
      setVideoPath("");
      loadVideos();
      loadTasks();
    } catch (importError) {
      setError(importError instanceof Error ? formatErrorMessage(importError.message) : "导入失败");
    } finally {
      setBusy(false);
      setPendingRequestLabel(null);
    }
  }

  async function onImportFolder(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setPendingRequestLabel("正在提交批量导入请求");
    setError("");
    try {
      const result = await api.importFolder(folderPath);
      setMessage(`文件夹导入完成，已加入队列 ${result.count} 个视频。`);
      setTrackedTaskIds((current) => Array.from(new Set([...result.tasks.map((task) => task.id), ...current])));
      setTasks((current) => mergeTaskRecords(current, result.tasks));
      setFolderPath("");
      loadVideos();
      loadTasks();
    } catch (importError) {
      setError(importError instanceof Error ? formatErrorMessage(importError.message) : "文件夹导入失败");
    } finally {
      setBusy(false);
      setPendingRequestLabel(null);
    }
  }

  return (
    <section className="panel-grid">
      <div className="panel">
        <p className="eyebrow">单视频导入</p>
        <h2>导入本地视频</h2>
        <form onSubmit={onImportVideo} className="form-stack">
          <label>
            视频路径
            <input value={videoPath} onChange={(event) => setVideoPath(event.target.value)} placeholder="E:\\证据视频\\sample.mp4" />
          </label>
          <label>
            处理模式
            <select value={processMode} onChange={(event) => setProcessMode(event.target.value as ProcessMode)}>
              <option value="quick">快速扫描（仅粗扫，零 API 调用）</option>
              <option value="two_stage">标准扫描（默认推荐）</option>
              <option value="deep">深度扫描（全帧精扫）</option>
            </select>
          </label>
          <button type="submit" disabled={busy || !videoPath.trim()}>
            {busy ? "正在加入队列..." : "导入并排队"}
          </button>
        </form>
      </div>
      <div className="panel">
        <p className="eyebrow">批量导入</p>
        <h2>导入文件夹</h2>
        <form onSubmit={onImportFolder} className="form-stack">
          <label>
            文件夹路径
            <input value={folderPath} onChange={(event) => setFolderPath(event.target.value)} placeholder="E:\\证据视频\\batch-01" />
          </label>
          <button type="submit" disabled={busy || !folderPath.trim()}>
            {busy ? "正在加入队列..." : "批量导入"}
          </button>
        </form>
      </div>
      <div className="panel panel-wide">
        <p className="eyebrow">导入状态</p>
        <p>{message}</p>
        {progressSummary ? (
          <div className="import-progress-card">
            <div className="task-progress-head">
              <strong>{progressSummary.title}</strong>
              <span>{progressSummary.indeterminate ? "提交中" : `${progressSummary.progress}%`}</span>
            </div>
            <div className={`progress-track${progressSummary.indeterminate ? " progress-track-indeterminate" : ""}`} aria-hidden="true">
              <div
                className={`progress-fill${progressSummary.indeterminate ? " progress-fill-indeterminate" : ""}`}
                style={progressSummary.indeterminate ? undefined : { width: `${progressSummary.progress}%` }}
              />
            </div>
            <div className="task-progress-meta">
              <span>{progressSummary.detail}</span>
              <span>活跃：{progressSummary.activeCount}</span>
              <span>完成：{progressSummary.completedCount}</span>
              <span>失败：{progressSummary.failedCount}</span>
            </div>
          </div>
        ) : null}
        {error ? <p className="error">{error}</p> : null}
      </div>
      <div className="panel panel-wide">
        <p className="eyebrow">处理进度</p>
        <h2>当前导入任务</h2>
        <div className="task-progress-list">
          {trackedTasks.map((task) => (
            <div key={task.id} className="task-progress-card">
              <div className="task-progress-head">
                <strong>{task.video_filename || `视频 #${task.video_id}`}</strong>
                <span>{formatTaskStatus(task.status)}</span>
              </div>
              <div className="progress-track" aria-hidden="true">
                <div className="progress-fill" style={{ width: `${Math.round(task.progress * 100)}%` }} />
              </div>
              <div className="task-progress-meta">
                <span>进度：{Math.round(task.progress * 100)}%</span>
                <span>阶段：{formatTaskStage(String(task.details.stage ?? ""))}</span>
                <span>
                  帧处理：{String(task.details.processed_frames ?? 0)}
                  {task.details.frame_count ? ` / ${String(task.details.frame_count)}` : ""}
                </span>
                {task.error_message ? <span className="error">{formatErrorMessage(task.error_message)}</span> : null}
              </div>
            </div>
          ))}
          {trackedTasks.length === 0 ? <p className="empty">导入后这里会实时显示任务进度。</p> : null}
        </div>
      </div>
      <div className="panel panel-wide">
        <p className="eyebrow">视频库</p>
        <h2>当前已导入视频</h2>
        <div className="table">
          <div className="table-row table-head table-row-videos">
            <span>文件名</span>
            <span>状态</span>
            <span>时长</span>
            <span>分辨率</span>
          </div>
          {videos.map((video) => (
            <div key={video.id} className="table-row table-row-videos">
              <span>{video.filename}</span>
              <span>{formatTaskStatus(video.status)}</span>
              <span>{video.duration.toFixed(1)} 秒</span>
              <span>{video.resolution || "-"}</span>
            </div>
          ))}
          {videos.length === 0 ? <p className="empty">当前还没有导入任何视频。</p> : null}
        </div>
      </div>
    </section>
  );
}
