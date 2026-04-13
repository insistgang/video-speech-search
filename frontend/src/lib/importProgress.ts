import type { TaskRecord } from "./api";

export type ImportProgressSummary = {
  progress: number;
  indeterminate: boolean;
  title: string;
  detail: string;
  totalCount: number;
  activeCount: number;
  completedCount: number;
  failedCount: number;
};

function clampProgress(value: number | undefined): number {
  if (!Number.isFinite(value)) {
    return 0;
  }
  return Math.max(0, Math.min(1, value ?? 0));
}

export function mergeTaskRecords(existing: TaskRecord[], incoming: TaskRecord[]): TaskRecord[] {
  const merged = new Map<number, TaskRecord>();
  for (const task of existing) {
    merged.set(task.id, task);
  }
  for (const task of incoming) {
    merged.set(task.id, task);
  }
  return Array.from(merged.values()).sort((left, right) => right.id - left.id);
}

export function deriveImportProgressSummary(
  trackedTasks: TaskRecord[],
  pendingRequestLabel: string | null,
): ImportProgressSummary | null {
  if (!pendingRequestLabel && trackedTasks.length === 0) {
    return null;
  }

  const totalCount = trackedTasks.length;
  const activeCount = trackedTasks.filter((task) => task.status === "pending" || task.status === "running").length;
  const completedCount = trackedTasks.filter((task) => task.status === "completed").length;
  const failedCount = trackedTasks.filter((task) => task.status === "failed").length;

  if (pendingRequestLabel && totalCount === 0) {
    return {
      progress: 20,
      indeterminate: true,
      title: pendingRequestLabel,
      detail: "正在校验路径并提交到后端队列。",
      totalCount,
      activeCount,
      completedCount,
      failedCount,
    };
  }

  const averageProgress = totalCount > 0
    ? Math.round((trackedTasks.reduce((sum, task) => sum + clampProgress(task.progress), 0) / totalCount) * 100)
    : 0;

  if (activeCount > 0) {
    return {
      progress: averageProgress,
      indeterminate: false,
      title: pendingRequestLabel ?? `正在处理 ${activeCount} 个任务`,
      detail: `已追踪 ${totalCount} 个任务，完成 ${completedCount} 个，失败 ${failedCount} 个。`,
      totalCount,
      activeCount,
      completedCount,
      failedCount,
    };
  }

  if (failedCount === totalCount) {
    return {
      progress: 100,
      indeterminate: false,
      title: "本轮导入任务均已失败",
      detail: `共 ${totalCount} 个任务，请查看下方错误详情后重试。`,
      totalCount,
      activeCount,
      completedCount,
      failedCount,
    };
  }

  if (completedCount === totalCount) {
    return {
      progress: 100,
      indeterminate: false,
      title: "本轮导入任务已全部完成",
      detail: `共完成 ${completedCount} 个任务。`,
      totalCount,
      activeCount,
      completedCount,
      failedCount,
    };
  }

  return {
    progress: averageProgress,
    indeterminate: false,
    title: "本轮导入任务已结束",
    detail: `共 ${totalCount} 个任务，完成 ${completedCount} 个，失败 ${failedCount} 个。`,
    totalCount,
    activeCount,
    completedCount,
    failedCount,
  };
}
