import { describe, expect, it } from "vitest";

import type { TaskRecord } from "../api";
import { deriveImportProgressSummary, mergeTaskRecords } from "../importProgress";

function makeTask(id: number, status: TaskRecord["status"], progress: number): TaskRecord {
  return {
    id,
    video_id: id,
    task_type: "video_process",
    status,
    progress,
    details: {},
  };
}

describe("import progress summary", () => {
  it("shows indeterminate progress while request is being submitted", () => {
    const summary = deriveImportProgressSummary([], "正在提交单视频导入请求");

    expect(summary).toEqual(
      expect.objectContaining({
        indeterminate: true,
        title: "正在提交单视频导入请求",
      }),
    );
  });

  it("aggregates tracked task progress", () => {
    const summary = deriveImportProgressSummary(
      [makeTask(1, "running", 0.5), makeTask(2, "completed", 1)],
      null,
    );

    expect(summary).toEqual(
      expect.objectContaining({
        progress: 75,
        activeCount: 1,
        completedCount: 1,
        failedCount: 0,
      }),
    );
  });

  it("merges returned tasks by id without duplicating records", () => {
    const merged = mergeTaskRecords(
      [makeTask(1, "pending", 0), makeTask(2, "running", 0.3)],
      [makeTask(2, "completed", 1), makeTask(3, "pending", 0)],
    );

    expect(merged.map((task) => [task.id, task.status])).toEqual([
      [3, "pending"],
      [2, "completed"],
      [1, "pending"],
    ]);
  });
});
