import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, getFrameImageUrl, HealthStatus, SearchResult, SearchSegment, VideoRecord } from "../lib/api";
import {
  formatAiDetectionLabel,
  formatApplicationLabel,
  formatErrorMessage,
  formatMatchedSourceLabel,
  formatMatchedSourcesLabel,
  formatRiskLabel,
  formatSecondsAsClock,
  formatTimeRange
} from "../lib/presentation";

export function getAiToolDetectedParam(aiFilter: string): boolean | undefined {
  if (aiFilter === "any") return undefined;
  if (aiFilter === "yes") return true;
  return false;
}

export function SearchPage() {
  const [query, setQuery] = useState("");
  const [videos, setVideos] = useState<VideoRecord[]>([]);
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [videoId, setVideoId] = useState("");
  const [timeStart, setTimeStart] = useState("");
  const [timeEnd, setTimeEnd] = useState("");
  const [aiFilter, setAiFilter] = useState("any");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [segments, setSegments] = useState<SearchSegment[]>([]);
  const [error, setError] = useState("");
  const [hasSearched, setHasSearched] = useState(false);

  useEffect(() => {
    let cancelled = false;

    api.listVideos().then((payload) => {
      if (!cancelled) {
        setVideos(payload);
      }
    }).catch(() => {
      if (!cancelled) {
        setVideos([]);
      }
    });
    api.health().then((payload) => {
      if (!cancelled) {
        setHealth(payload);
      }
    }).catch(() => {
      if (!cancelled) {
        setHealth(null);
      }
    });

    return () => {
      cancelled = true;
    };
  }, []);

  async function onSearch(event: FormEvent) {
    event.preventDefault();
    setHasSearched(true);
    const normalizedQuery = query.trim();
    if (!normalizedQuery) {
      setError("请输入关键词后再检索");
      setResults([]);
      setSegments([]);
      return;
    }

    try {
      const response = await api.search({
        query: normalizedQuery,
        video_id: videoId ? Number(videoId) : undefined,
        time_start: timeStart ? Number(timeStart) : undefined,
        time_end: timeEnd ? Number(timeEnd) : undefined,
        ai_tool_detected: getAiToolDetectedParam(aiFilter)
      });
      setResults(response.results ?? []);
      setSegments(response.segments ?? []);
      setError("");
    } catch (searchError) {
      setError(searchError instanceof Error ? formatErrorMessage(searchError.message) : "检索失败");
    }
  }

  return (
    <section className="panel-grid">
      <div className="panel panel-wide">
        <p className="eyebrow">检索中心</p>
        <h2>搜索已索引的视频画面内容</h2>
        <form onSubmit={onSearch} className="search-form">
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="输入关键词、短语或平台名称；多个词需同时出现"
          />
          <div className="filter-grid">
            <label>
              视频
              <select value={videoId} onChange={(event) => setVideoId(event.target.value)}>
                <option value="">全部视频</option>
                {videos.map((video) => (
                  <option key={video.id} value={String(video.id)}>
                    {video.filename}
                  </option>
                ))}
              </select>
            </label>
            <label>
              AI 工具检测
              <select value={aiFilter} onChange={(event) => setAiFilter(event.target.value)}>
                <option value="any">全部</option>
                <option value="yes">仅看命中</option>
                <option value="no">仅看未命中</option>
              </select>
            </label>
            <label>
              起始时间
              <input value={timeStart} onChange={(event) => setTimeStart(event.target.value)} placeholder="0 秒" />
            </label>
            <label>
              结束时间
              <input value={timeEnd} onChange={(event) => setTimeEnd(event.target.value)} placeholder="120 秒" />
            </label>
          </div>
          <button type="submit" disabled={!query.trim()}>
            开始检索
          </button>
        </form>
        {error ? <p className="error">{error}</p> : null}
        <p className="muted">结果数：{results.length}</p>
        {health?.vision_analyzer_mode === "mock" ? (
          <p className="muted">当前为 mock 模式：可按文件名或路径关键词检索，画面内容与 token 消耗均为模拟值。</p>
        ) : null}
      </div>
      {segments.length > 0 ? (
        <div className="panel panel-wide">
          <p className="eyebrow">可疑时间段</p>
          <h2>聚合后的可疑片段</h2>
          <p className="muted">共识别出 {segments.length} 段可疑区间，点击可跳到该段首帧。</p>
          <div className="segment-list">
            {segments.map((segment) => (
              <Link key={`${segment.video_id}-${segment.first_frame_id}`} to={`/results/${segment.first_frame_id}`} className="segment-card">
                <div>
                  <p className="eyebrow">片段 {formatTimeRange(segment.start_timestamp, segment.end_timestamp)}</p>
                  <h3>{segment.video_name}</h3>
                  <p>{segment.summary}</p>
                </div>
                <div className="meta meta-segment">
                  <span className="badge badge-source">{formatMatchedSourcesLabel(segment.matched_sources)}</span>
                  <span>起止：{formatTimeRange(segment.start_timestamp, segment.end_timestamp)}</span>
                  <span>时长：{formatSecondsAsClock(segment.duration_seconds)}</span>
                  <span>证据帧：{segment.hit_count} 帧</span>
                  <span>{segment.ai_tool_detected ? `AI 工具：${(segment.ai_tool_names ?? []).join("，") || "已命中"}` : "未明确识别 AI 工具"}</span>
                  <span>{formatRiskLabel(segment.risk_indicators ?? [])}</span>
                </div>
              </Link>
            ))}
          </div>
        </div>
      ) : null}
      <div className="results">
        {results.map((result) => (
          <Link key={result.frame_id} to={`/results/${result.frame_id}`} className="result-card">
            <img
              src={getFrameImageUrl(result.frame_id)}
              alt={`${result.video_name} 在 ${result.timestamp.toFixed(1)} 秒处的画面`}
              className="result-thumb"
              loading="lazy"
            />
            <div>
              <p className="eyebrow">命中结果 <span className="badge badge-source">{formatMatchedSourceLabel(result.matched_source)}</span></p>
              <h3>{result.video_name}</h3>
              <p>{result.analysis_summary || result.matched_text}</p>
            </div>
            <div className="meta">
              <span>{formatApplicationLabel(result.application)}</span>
              <span>{result.timestamp.toFixed(1)} 秒</span>
              <span>{formatAiDetectionLabel(result.ai_tool_detected, result.ai_tool_name)}</span>
              <span>{formatRiskLabel(result.risk_indicators ?? [])}</span>
            </div>
          </Link>
        ))}
        {results.length === 0 ? (
          <div className="panel panel-wide">
            <p className="eyebrow">暂无结果</p>
            <p>
              {hasSearched
                ? "当前没有命中结果。mock 模式下可以先试试文件名或路径关键词，例如 AI、八段锦、作弊视频。"
                : "请先完成视频处理，再输入关键词进行检索。"}
            </p>
          </div>
        ) : null}
      </div>
    </section>
  );
}
