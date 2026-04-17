export class ApiError extends Error {
  constructor(
    message: string,
    public statusCode: number,
    public isRetryable: boolean
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export type TaskRecord = {
  id: number;
  video_id: number;
  task_type: string;
  status: string;
  progress: number;
  video_filename?: string | null;
  video_filepath?: string | null;
  video_status?: string | null;
  error_message?: string | null;
  details: Record<string, unknown>;
  stage?: string;
  skipped_frames?: number;
};

export type VideoRecord = {
  id: number;
  filename: string;
  filepath: string;
  duration: number;
  format: string;
  resolution: string;
  status: string;
};

export type SearchResult = {
  frame_id: number;
  video_id: number;
  video_name: string;
  video_path: string;
  timestamp: number;
  matched_text: string;
  matched_source?: "ocr" | "summary" | "ai_tool_name" | "metadata";
  analysis_summary: string;
  frame_image_path: string;
  application: string;
  ai_tool_detected: boolean;
  ai_tool_name: string;
  risk_indicators: string[];
};

export type SearchSegment = {
  video_id: number;
  video_name: string;
  video_path: string;
  start_timestamp: number;
  end_timestamp: number;
  duration_seconds: number;
  first_frame_id: number;
  last_frame_id: number;
  frame_ids: number[];
  hit_count: number;
  ai_tool_detected: boolean;
  ai_tool_names: string[];
  matched_sources?: string[];
  risk_indicators: string[];
  summary: string;
};

export type HealthStatus = {
  status: string;
  vision_analyzer_mode: string;
};

export type KeywordSet = {
  id: number;
  name: string;
  category: string;
  terms: string[];
};

export type KeywordScanResult = SearchResult & {
  matched_terms: string[];
};

export type ResultDetail = {
  video?: { id: number; filename: string; filepath: string; status: string };
  frame?: { id: number; video_id: number; timestamp: number; image_path: string };
  analysis?: Record<string, unknown>;
  frames?: Array<{ id: number; timestamp: number }>;
  total_frames?: number;
};

export type SearchResponse = {
  query: string;
  count: number;
  segment_count: number;
  results: SearchResult[];
  segments: SearchSegment[];
};

export type ImportEstimate = {
  estimated_frames: number;
  estimated_cost: number;
};

export type ImportVideoResponse = {
  video: VideoRecord;
  task: TaskRecord;
  estimate: ImportEstimate;
};

export type ImportFolderResponse = {
  videos: VideoRecord[];
  tasks: TaskRecord[];
  count: number;
};

export type ProcessMode = "quick" | "two_stage" | "deep";
export type QueuedTaskResponse = { status: string; task: TaskRecord };
export type VideoSegment = {
  id: number;
  video_id: number;
  start_timestamp: number;
  end_timestamp: number;
  severity: string;
  reason: string;
};
export type Stats = {
  total_videos: number;
  total_frames: number;
  total_tasks: number;
  completed_tasks: number;
  failed_tasks: number;
};

export const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "/api";
export const MEDIA_BASE = "/media";
const API_KEY = import.meta.env.VITE_API_KEY || "";

export function getFrameImageUrl(frameId: number): string {
  return `${MEDIA_BASE}/frames/${frameId}/image`;
}

export function getVideoFileUrl(videoId: number): string {
  return `${MEDIA_BASE}/videos/${videoId}/file`;
}

async function readErrorMessage(response: Response): Promise<string> {
  const fallback = `${response.status} ${response.statusText}`;
  const contentType = response.headers.get("content-type") ?? "";

  try {
    if (contentType.includes("application/json")) {
      const payload = await response.json() as { detail?: unknown; message?: unknown };
      if (typeof payload.detail === "string" && payload.detail.trim()) {
        return `${response.status} ${payload.detail.trim()}`;
      }
      if (typeof payload.message === "string" && payload.message.trim()) {
        return `${response.status} ${payload.message.trim()}`;
      }
      return fallback;
    }

    const text = (await response.text()).trim();
    return text ? `${response.status} ${text}` : fallback;
  } catch {
    return fallback;
  }
}

async function request<T>(path: string, init?: RequestInit, retries = 3): Promise<T> {
  let lastError: Error | null = null;
  for (let attempt = 0; attempt <= retries; attempt++) {
    const response = await fetch(`${API_BASE}${path}`, {
      headers: {
        "Content-Type": "application/json",
        "X-API-Key": API_KEY,
        ...(init?.headers ?? {})
      },
      ...init
    });
    if (response.ok) {
      if (response.status === 204) {
        return undefined as T;
      }
      return (await response.json()) as T;
    }
    if (response.status === 429 && attempt < retries) {
      const delay = Math.pow(2, attempt) * 500;
      await new Promise((resolve) => window.setTimeout(resolve, delay));
      continue;
    }
    lastError = new Error(await readErrorMessage(response));
    throw new ApiError(lastError.message, response.status, response.status === 429);
  }
  throw lastError ?? new Error("Request failed");
}

function normalizeSearchResponse(payload: Partial<SearchResponse> | null | undefined): SearchResponse {
  return {
    query: payload?.query ?? "",
    count: payload?.count ?? (payload?.results?.length ?? 0),
    segment_count: payload?.segment_count ?? (payload?.segments?.length ?? 0),
    results: payload?.results ?? [],
    segments: payload?.segments ?? [],
  };
}

export const api = {
  health: () => request<HealthStatus>("/health"),
  listVideos: () => request<VideoRecord[]>("/videos"),
  listTasks: (options?: { activeOnly?: boolean; limit?: number }) => {
    const params = new URLSearchParams();
    if (options?.activeOnly) {
      params.set("active_only", "true");
    }
    if (options?.limit) {
      params.set("limit", String(options.limit));
    }
    const query = params.size > 0 ? `?${params.toString()}` : "";
    return request<TaskRecord[]>(`/tasks${query}`);
  },
  retryTask: (taskId: number) => request<{ status: string; task: TaskRecord }>(`/tasks/${taskId}/retry`, { method: "POST" }),
  listKeywords: () => request<KeywordSet[]>("/keywords"),
  createKeywordSet: (payload: { name: string; category: string; terms: string[] }) =>
    request("/keywords", { method: "POST", body: JSON.stringify(payload) }),
  updateKeywordSet: (keywordSetId: number, payload: { name: string; category: string; terms: string[] }) =>
    request<KeywordSet>(`/keywords/${keywordSetId}`, { method: "PUT", body: JSON.stringify(payload) }),
  deleteKeywordSet: (keywordSetId: number) => request(`/keywords/${keywordSetId}`, { method: "DELETE" }),
  scanKeywordSet: (keywordSetId: number) =>
    request<{ keyword_set_id: number; total_terms: number; total_hits: number; results: KeywordScanResult[] }>(
      `/keywords/${keywordSetId}/scan`,
      { method: "POST" }
    ),
  importVideo: (path: string, mode?: ProcessMode) =>
    request<ImportVideoResponse>("/videos/import", { method: "POST", body: JSON.stringify({ path, mode: mode || "two_stage" }) }),
  importFolder: (folderPath: string) =>
    request<ImportFolderResponse>("/videos/import-folder", { method: "POST", body: JSON.stringify({ folder_path: folderPath }) }),
  search: (payload: {
    query: string;
    video_id?: number;
    time_start?: number;
    time_end?: number;
    ai_tool_detected?: boolean;
  }) =>
    request<Partial<SearchResponse>>("/search", { method: "POST", body: JSON.stringify(payload) }).then(normalizeSearchResponse),
  getResult: (frameId: string) => request<ResultDetail>(`/search/results/${frameId}`),
  processVideo: (videoId: number, mode: ProcessMode) =>
    request<QueuedTaskResponse>(`/videos/${videoId}/process`, { method: "POST", body: JSON.stringify({ mode }) }),
  getVideoSegments: (videoId: number) => request<VideoSegment[]>(`/videos/${videoId}/segments`),
  rescanVideo: (videoId: number, stage: "coarse" | "fine") =>
    request<QueuedTaskResponse>(`/videos/${videoId}/rescan`, { method: "POST", body: JSON.stringify({ stage }) }),
  getStats: () => request<Stats>("/stats")
};
