import { useEffect, useRef, useState } from "react";
import { api, HealthStatus, TaskRecord } from "../lib/api";
import { formatErrorMessage, formatTaskStage, formatTaskStatus, formatTokenUsage } from "../lib/presentation";
import { getLatestTasks } from "../lib/tasks";

export function TasksPage() {
  const [tasks, setTasks] = useState<TaskRecord[]>([]);
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [error, setError] = useState("");
  const [showHistory, setShowHistory] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const showHistoryRef = { current: showHistory };

    const load = async () => {
      try {
        const items = await api.listTasks(showHistoryRef.current ? undefined : { limit: 100 });
        if (!cancelled) {
          setTasks(items);
          setError("");
        }
      } catch (taskError) {
        if (!cancelled) {
          setTasks([]);
          setError(taskError instanceof Error ? formatErrorMessage(taskError.message) : "任务加载失败");
        }
      }
    };

    load();
    api.health().then((payload) => {
      if (!cancelled) {
        setHealth(payload);
      }
    }).catch(() => {
      if (!cancelled) {
        setHealth(null);
      }
    });
    const timer = window.setInterval(load, 3000);

    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [showHistory]);

  const visibleTasks = showHistory ? tasks : getLatestTasks(tasks);

  async function retryTask(task: TaskRecord) {
    try {
      await api.retryTask(task.id);
      setError("");
    } catch (retryError) {
      setError(retryError instanceof Error ? formatErrorMessage(retryError.message) : "重试失败");
    }
  }

  return (
    <section className="panel">
      <p className="eyebrow">处理队列</p>
      <h2>任务列表</h2>
      <div className="action-row">
        <button type="button" className="button-secondary" onClick={() => setShowHistory((current) => !current)}>
          {showHistory ? "仅看最新任务" : "显示历史任务"}
        </button>
        <span className="muted">
          {showHistory ? `当前展示全部 ${tasks.length} 条任务记录` : `当前仅展示每个视频的最新任务，共 ${visibleTasks.length} 条`}
        </span>
      </div>
      {health?.vision_analyzer_mode === "mock" ? (
        <p className="muted">当前为 mock 模式，分析结果来自本地模拟，Token 用量固定为 0。</p>
      ) : null}
      {error ? <p className="error">{error}</p> : null}
      <div className="table">
        <div className="table-row table-head table-row-tasks">
          <span>ID</span>
          <span>视频</span>
          <span>状态</span>
          <span>阶段</span>
          <span>进度</span>
          <span>帧数</span>
          <span>跳过帧数</span>
          <span>Token 用量</span>
          <span>错误</span>
          <span>操作</span>
        </div>
        {visibleTasks.map((task) => (
          <div className="table-row table-row-tasks" key={task.id}>
            <span>{task.id}</span>
            <span>{task.video_filename || `视频 #${task.video_id}`}</span>
            <span>{formatTaskStatus(task.status)}{task.video_status ? ` / ${formatTaskStatus(task.video_status)}` : ""}</span>
            <span>{formatTaskStage(String(task.details.stage ?? task.stage ?? ""))}</span>
            <span>{Math.round(task.progress * 100)}%</span>
            <span>
              {String(task.details.processed_frames ?? 0)}
              {task.details.frame_count ? ` / ${String(task.details.frame_count)}` : ""}
            </span>
            <span>{task.skipped_frames ?? task.details.skipped_frames ?? 0}</span>
            <span>{formatTokenUsage((task.details.token_usage as { total_tokens?: number } | undefined)?.total_tokens ?? 0, health?.vision_analyzer_mode)}</span>
            {task.error_message ? <span className="error">{formatErrorMessage(task.error_message)}</span> : <span>无</span>}
            <span>
              <button
                type="button"
                className="button-secondary"
                onClick={() => retryTask(task)}
                disabled={task.status === "running" || task.status === "pending"}
              >
                重试
              </button>
            </span>
          </div>
        ))}
        {visibleTasks.length === 0 ? <p className="empty">当前还没有任务。</p> : null}
      </div>
    </section>
  );
}
