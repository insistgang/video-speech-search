import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, getFrameImageUrl, KeywordScanResult, KeywordSet } from "../lib/api";
import { parseKeywordTermsInput } from "../lib/keywords";
import {
  formatAiDetectionLabel,
  formatApplicationLabel,
  formatErrorMessage,
  formatMatchedSourceLabel,
  formatRiskLabel
} from "../lib/presentation";

export function KeywordsPage() {
  const [items, setItems] = useState<KeywordSet[]>([]);
  const [name, setName] = useState("");
  const [category, setCategory] = useState("");
  const [terms, setTerms] = useState("");
  const [editingId, setEditingId] = useState<number | null>(null);
  const [scanResults, setScanResults] = useState<KeywordScanResult[]>([]);
  const [activeScanName, setActiveScanName] = useState("");
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState<number | null>(null);

  function load() {
    api.listKeywords().then(setItems).catch(() => setItems([]));
  }

  useEffect(() => {
    load();
  }, []);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError("");
    try {
      const payload = {
        name,
        category,
        terms: parseKeywordTermsInput(terms)
      };
      if (editingId === null) {
        await api.createKeywordSet(payload);
      } else {
        await api.updateKeywordSet(editingId, payload);
      }
      setName("");
      setCategory("");
      setTerms("");
      setEditingId(null);
      load();
    } catch (saveError) {
      setError(saveError instanceof Error ? formatErrorMessage(saveError.message) : "词库保存失败");
    }
  }

  function onEdit(item: KeywordSet) {
    setEditingId(item.id);
    setName(item.name);
    setCategory(item.category);
    setTerms(item.terms.join("，"));
    setError("");
  }

  function onCancelEdit() {
    setEditingId(null);
    setName("");
    setCategory("");
    setTerms("");
    setError("");
  }

  async function onScan(item: KeywordSet) {
    setBusyId(item.id);
    setError("");
    try {
      const response = await api.scanKeywordSet(item.id);
      setScanResults(response.results);
      setActiveScanName(item.name);
    } catch (scanError) {
      setError(scanError instanceof Error ? formatErrorMessage(scanError.message) : "词库扫描失败");
    } finally {
      setBusyId(null);
    }
  }

  async function onDelete(item: KeywordSet) {
    setBusyId(item.id);
    setError("");
    try {
      await api.deleteKeywordSet(item.id);
      if (activeScanName === item.name) {
        setScanResults([]);
        setActiveScanName("");
      }
      load();
    } catch (deleteError) {
      setError(deleteError instanceof Error ? formatErrorMessage(deleteError.message) : "删除失败");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <section className="panel-grid">
      <div className="panel">
        <p className="eyebrow">规则词库</p>
        <h2>{editingId === null ? "创建关键词集" : "编辑关键词集"}</h2>
        <form onSubmit={onSubmit} className="form-stack">
          <label>
            名称
            <input value={name} onChange={(event) => setName(event.target.value)} />
          </label>
          <label>
            分类
            <input value={category} onChange={(event) => setCategory(event.target.value)} />
          </label>
          <label>
            关键词
            <input value={terms} onChange={(event) => setTerms(event.target.value)} placeholder="ChatGPT，Bedrock，Copilot" />
          </label>
          <button type="submit">保存关键词集</button>
          {editingId !== null ? (
            <button type="button" className="button-secondary" onClick={onCancelEdit}>
              取消编辑
            </button>
          ) : null}
        </form>
        {error ? <p className="error">{error}</p> : null}
      </div>
      <div className="panel panel-wide">
        <p className="eyebrow">词库列表</p>
        <h2>已有关键词集</h2>
        <div className="keyword-list">
          {items.map((item) => (
            <div key={item.id} className="keyword-card">
              <h3>{item.name}</h3>
              <p>{item.category}</p>
              <p>{item.terms.join(", ")}</p>
              <div className="action-row">
                <button type="button" className="button-secondary" onClick={() => onEdit(item)} disabled={busyId === item.id}>
                  编辑
                </button>
                <button type="button" onClick={() => onScan(item)} disabled={busyId === item.id}>
                  {busyId === item.id ? "扫描中..." : "立即扫描"}
                </button>
                <button type="button" className="button-secondary" onClick={() => onDelete(item)} disabled={busyId === item.id}>
                  删除
                </button>
              </div>
            </div>
          ))}
          {items.length === 0 ? <p className="empty">当前还没有关键词集。</p> : null}
        </div>
      </div>
      <div className="panel panel-wide">
        <p className="eyebrow">扫描结果</p>
        <h2>{activeScanName ? `${activeScanName} 的命中结果` : "请选择一个关键词集进行扫描"}</h2>
        <div className="results">
          {scanResults.map((result) => (
            <Link key={result.frame_id} to={`/results/${result.frame_id}`} className="result-card">
              <img
                src={getFrameImageUrl(result.frame_id)}
                alt={`${result.video_name} 在 ${result.timestamp.toFixed(1)} 秒处的画面`}
                className="result-thumb"
                loading="lazy"
              />
              <div>
                <p className="eyebrow">词库命中 <span className="badge badge-source">{formatMatchedSourceLabel(result.matched_source)}</span></p>
                <h3>{result.video_name}</h3>
                <p>{result.analysis_summary || result.matched_text}</p>
                <p className="muted">命中词：{result.matched_terms.join("，")}</p>
              </div>
              <div className="meta">
                <span>{formatApplicationLabel(result.application)}</span>
                <span>{result.timestamp.toFixed(1)} 秒</span>
                <span>{formatAiDetectionLabel(result.ai_tool_detected, result.ai_tool_name)}</span>
                <span>{formatRiskLabel(result.risk_indicators)}</span>
              </div>
            </Link>
          ))}
          {scanResults.length === 0 ? <p className="empty">当前还没有扫描结果。</p> : null}
        </div>
      </div>
    </section>
  );
}
