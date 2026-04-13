import { expect, test } from "vitest";

import type { TaskRecord } from "../api";
import { getLatestTasks } from "../tasks";

function buildTask(id: number, videoId: number, status: string): TaskRecord {
  return {
    id,
    video_id: videoId,
    task_type: "video_process",
    status,
    progress: 1,
    details: {},
    video_filename: `video-${videoId}.mp4`,
    video_filepath: `E:/videos/video-${videoId}.mp4`,
    video_status: status,
  };
}

test("keeps only the latest task for each video", () => {
  const tasks = [
    buildTask(1, 1, "completed"),
    buildTask(2, 1, "failed"),
    buildTask(3, 2, "completed"),
    buildTask(4, 2, "completed"),
  ];

  expect(getLatestTasks(tasks)).toEqual([buildTask(4, 2, "completed"), buildTask(2, 1, "failed")]);
});
