import type { TaskRecord } from "./api";

export function getLatestTasks(tasks: TaskRecord[]): TaskRecord[] {
  const latestByVideo = new Map<string, TaskRecord>();

  for (const task of tasks) {
    const key = `${task.task_type}:${task.video_id}`;
    const existing = latestByVideo.get(key);
    if (!existing || task.id > existing.id) {
      latestByVideo.set(key, task);
    }
  }

  return Array.from(latestByVideo.values()).sort((left, right) => right.id - left.id);
}
