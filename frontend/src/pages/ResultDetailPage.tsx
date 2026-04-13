import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, getFrameImageUrl, getVideoFileUrl, ResultDetail } from "../lib/api";
import { formatAiDetectionLabel, formatApplicationLabel, formatRiskLabel } from "../lib/presentation";

export function ResultDetailPage() {
  const { frameId = "" } = useParams();
  const [detail, setDetail] = useState<ResultDetail>({});
  const videoRef = useRef<HTMLVideoElement | null>(null);

  useEffect(() => {
    let cancelled = false;
    api.getResult(frameId).then((data) => {
      if (!cancelled) setDetail(data);
    }).catch(() => {
      if (!cancelled) setDetail({});
    });
    return () => { cancelled = true; };
  }, [frameId]);

  useEffect(() => {
    const element = videoRef.current;
    if (!element || detail.frame?.timestamp === undefined) {
      return;
    }
    const targetTime = detail.frame.timestamp;
    const syncToTimestamp = () => {
      element.currentTime = targetTime;
    };
    element.addEventListener("loadedmetadata", syncToTimestamp);
    if (element.readyState >= 1) {
      syncToTimestamp();
    }
    return () => {
      element.removeEventListener("loadedmetadata", syncToTimestamp);
    };
  }, [detail.frame?.timestamp, detail.video?.id]);

  const analysis = detail.analysis as
    | {
        screen_text?: string;
        application?: string;
        url?: string;
        operation?: string;
        ai_tool_detected?: boolean;
        ai_tool_name?: string;
        code_visible?: boolean;
        code_content_summary?: string;
        risk_indicators?: string[];
        summary?: string;
        raw_json?: Record<string, unknown>;
      }
    | undefined;
  const rawJson = (analysis?.raw_json ?? {}) as Record<string, unknown>;
  const operationSequence = Array.isArray(rawJson.operation_sequence)
    ? rawJson.operation_sequence.map((item) => String(item).trim()).filter(Boolean)
    : typeof rawJson.operation_sequence === "string" && rawJson.operation_sequence.trim()
      ? [rawJson.operation_sequence.trim()]
      : [];
  const segmentStart = typeof rawJson._segment_start === "number" ? rawJson._segment_start : undefined;
  const segmentEnd = typeof rawJson._segment_end === "number" ? rawJson._segment_end : undefined;
  const fineScanMode = typeof rawJson._fine_scan_mode === "string" ? rawJson._fine_scan_mode : "";

  return (
    <section className="panel-grid">
      <div className="panel">
        <p className="eyebrow">视频信息</p>
        <h2>{detail.video?.filename ?? "结果详情"}</h2>
        <p>{detail.video?.filepath}</p>
        <p>命中时间：{detail.frame?.timestamp?.toFixed(1) ?? "0.0"} 秒</p>
        {fineScanMode === "video" && segmentStart !== undefined && segmentEnd !== undefined ? (
          <p>分析片段：{segmentStart.toFixed(1)} - {segmentEnd.toFixed(1)} 秒</p>
        ) : null}
        {detail.video?.id ? (
          <video
            key={detail.video.id}
            ref={videoRef}
            controls
            className="detail-video"
            src={getVideoFileUrl(detail.video.id)}
          />
        ) : null}
      </div>
      <div className="panel">
        <p className="eyebrow">命中画面</p>
        <h2>关键帧预览</h2>
        {detail.frame?.id ? (
          <img
            src={getFrameImageUrl(detail.frame.id)}
            alt={`关键帧 ${detail.frame.id}`}
            className="detail-frame"
          />
        ) : (
          <p>暂无画面。</p>
        )}
      </div>
      <div className="panel panel-wide">
        <p className="eyebrow">时间线</p>
        <div className="timeline">
          {(detail.frames ?? []).map((item) => (
            <Link
              key={item.id}
              to={`/results/${item.id}`}
              className={`timeline-chip ${item.id === detail.frame?.id ? "timeline-chip-active" : ""}`}
            >
              {item.timestamp.toFixed(1)} 秒
            </Link>
          ))}
        </div>
      </div>
      <div className="panel panel-wide">
        <p className="eyebrow">结构化分析</p>
        <div className="detail-grid">
          <div className="detail-item">
            <span className="detail-label">应用 / 网站</span>
            <span>{formatApplicationLabel(analysis?.application || "")}</span>
          </div>
          <div className="detail-item">
            <span className="detail-label">AI 工具识别</span>
            <span>{formatAiDetectionLabel(Boolean(analysis?.ai_tool_detected), analysis?.ai_tool_name)}</span>
          </div>
          <div className="detail-item">
            <span className="detail-label">页面链接</span>
            <span>{analysis?.url || "未识别到链接"}</span>
          </div>
          <div className="detail-item">
            <span className="detail-label">风险标签</span>
            <span>{formatRiskLabel(analysis?.risk_indicators || [])}</span>
          </div>
          <div className="detail-item detail-item-wide">
            <span className="detail-label">画面摘要</span>
            <span>{analysis?.summary || "暂无摘要"}</span>
          </div>
          <div className="detail-item detail-item-wide">
            <span className="detail-label">操作描述</span>
            <span>{analysis?.operation || "暂无操作描述"}</span>
          </div>
          <div className="detail-item detail-item-wide">
            <span className="detail-label">操作序列</span>
            <span>{operationSequence.length > 0 ? operationSequence.join(" -> ") : "暂无操作序列"}</span>
          </div>
          <div className="detail-item detail-item-wide">
            <span className="detail-label">可见文字</span>
            <span>{analysis?.screen_text || "暂无识别文字"}</span>
          </div>
          <div className="detail-item detail-item-wide">
            <span className="detail-label">代码摘要</span>
            <span>{analysis?.code_content_summary || "未检测到代码"}</span>
          </div>
        </div>
      </div>
    </section>
  );
}
