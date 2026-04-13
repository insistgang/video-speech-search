# understand_mov 项目状态总报告

**审计日期**: 2026-04-12
**审计范围**: E:\understand_mov_v2
**综合**: project-auditor + v2-gap-analyzer + tech-debt-scanner

---

## 1. 项目总览

### 1.1 当前阶段

| 维度 | 状态 |
|------|------|
| V1 功能 | ✅ 完成 |
| V2 MVP | 🚧 进行中（约 85%） |
| V2.1 扩展 | ❌ 未开始 |
| V2.2 向量搜索 | ❌ 未开始 |

**判定**: 项目处于 **V2 MVP 收尾阶段**，核心架构和功能已稳定，剩余工作为填充缺口和修复安全债务。

### 1.2 代码规模统计

| 模块 | 规模 | 完成度 |
|------|------|--------|
| Backend 核心 + 服务 | ~3,107 行 | ~99% |
| Backend API 路由 | ~452 行 | ~99% |
| Frontend (React/TypeScript) | ~1,240 行 | ~99% |
| Tests (25 个文件) | ~2,722 行 | ~90% |
| **总计** | **~7,521 行** | **~97%** |

- **零 TODO/FIXME/HACK** 注释存在于任何后端/前端源码
- Docker + nginx 生产级基础设施已完成
- 完整文档（用户手册、部署指南、PRD、技术栈报告）齐全

---

## 2. V2 实施进度

### 2.1 V2 MVP 完成率：~85%

#### ✅ 已完成（核心 MVP）

| 功能 | 状态 | 说明 |
|------|------|------|
| 单视频 + 文件夹批量导入 | DONE | `POST /api/videos/import`, `POST /api/videos/import-folder` |
| FFmpeg 固定间隔抽帧 | DONE | 默认 10s（粗粒度）+ 3s（细粒度）两阶段 |
| 多模态画面理解 | DONE | 结构化 JSON 存储（screen_text, AI tool, risk_indicators 等） |
| SQLite FTS5 全文搜索 | DONE | BM25 排名，关键词精确搜索 |
| 搜索结果展示 | DONE | 视频名 + 命中文本 + 时间戳 + 帧截图 |
| 关键词库管理 | DONE | CRUD + 扫描（`/api/keywords`） |
| API 认证 | DONE | `secrets.compare_digest` 时序安全比较 |
| 任务队列（持久化 SQLite） | DONE | 带 worker 恢复能力 |
| 帧去重（pHash） | DONE | 感知哈希去重 |
| 重试 + 指数退避 | DONE | VisionAnalyzer `max_retries=6` |
| Docker Compose 部署 | DONE | 资源限制、健康检查、nginx 反代 |

#### ⚠️ 部分完成 / 缺口

| 功能 | 状态 | 说明 |
|------|------|------|
| 视觉 Provider 与 PRD 不符 | PARTIAL | 代码默认 Zhipu GLM-4.6v-flash；PRD 要求 Kimi K2.5（可通过 `VISION_PROVIDER=moonshot` 切换但未告知用户） |
| 费用估算 | PARTIAL | `estimate_cost()` 返回帧数但 `estimated_cost = 0`，无实际 API 定价 |
| Prompt 配置化 | MISSING | `prompts/screen_analysis.py` 中 Prompt 硬编码，PRD Section 8.3.1 P0 要求支持自定义 Prompt |
| 拖拽上传 | MISSING | ImportPage 需手动输入文件路径，无拖拽 UI |
| 搜索结果排序 | PARTIAL | 仅支持 BM25 相关性排序；PRD 要求按命中次数、导入时间排序 |
| 临近帧上下文展示 | MISSIAL | ResultDetailPage 时间轴显示所有帧，但缺少明确的"前/后帧"上下文标注 |
| 搜索结果导出 CSV/Excel | MISSING | V2.1 规划，未在 MVP 范围 |

#### ❌ V2.1/V2.2 功能（未计划实现）

| 功能 | 状态 | 说明 |
|------|------|------|
| 场景切换检测抽帧 | 未开始 | V2.1 规划，无任何代码 |
| 模糊匹配搜索 | 未开始 | V2.1 规划 |
| 向量语义搜索 | 未开始 | V2.2 规划（无 embedding 模型） |

### 2.2 V2 前端页面完成情况

| 页面 | 状态 |
|------|------|
| ImportPage（导入页） | ~90%（缺拖拽、缺费用估算显示） |
| TasksPage（任务页） | ✅ 完成 |
| SearchPage（搜索页） | ✅ 完成 |
| ResultDetailPage（结果详情页） | ~90%（缺前/后帧上下文） |
| KeywordsPage（关键词库页） | ✅ 完成 |

---

## 3. 安全修复状态

### 3.1 COMPLETE_FIXES.md 落地核查

| # | 修复项 | 文件 | 状态 |
|---|--------|------|------|
| 1 | 命令注入（shlex.quote） | `backend/services/frame_extractor.py:29` | **⚠️ PARTIAL** — 未使用 `shlex.quote`，video_path 直接拼接 |
| 2 | 路径穿越（ALLOWED_VIDEO_DIRECTORIES） | `backend/models.py:11-14,78-93` | ✅ YES |
| 3 | 路由冲突（/video/{video_id}） | `backend/api/frames.py:17` | ✅ YES |
| 4 | API 认证（secrets.compare_digest） | `backend/auth.py` | ⚠️ PARTIAL — 实现正确，但 dev mode 存在认证绕过 |
| 5 | CORS 配置（env-based origins） | `backend/main.py:249-270` | ✅ YES |
| 6 | FFmpeg 效率（start_time/duration） | `backend/services/frame_extractor.py:14-15,26-27,32-33` | ✅ YES |
| 7 | 文件句柄泄漏（with statement） | `backend/services/frame_dedup.py:33,37` | ✅ YES |
| 8 | 视频流错误（explicit filter） | `backend/services/video_import.py:76-80` | ✅ YES |
| 9 | 前端竞态条件（cancelled flag） | `frontend/src/pages/ResultDetailPage.tsx:11-18` | ✅ YES |
| 10 | 未使用导入清理 | `frontend/src/pages/ImportPage.tsx:1` | ✅ YES |
| 11 | 数据库索引 | `backend/db.py:131-141` | ✅ YES |
| 12 | FTS5 触发器 | `backend/db.py:145-190` | ✅ YES |
| 13 | 限流（slowapi） | `backend/main.py` + decorators | ✅ YES |
| 14 | Docker 资源限制 | `docker-compose.yml:20-27,49-56` | ✅ YES |

**核查结果**: 12/14 完全落地，2/14 存在遗留问题

---

## 4. 技术债务清单（按风险等级排序）

### 🔴 HIGH — 必须立即修复

| # | 问题 | 文件:行号 | 说明 |
|---|------|----------|------|
| H1 | **认证绕过（开发模式）** | `backend/auth.py:46-47` | 当 `API_KEY` 环境变量未设置时，返回空字符串，等效于**放行所有请求**。若误部署到生产环境将导致全量 API 裸奔 |
| H2 | **命令注入修复不完整** | `backend/services/frame_extractor.py:29` | 文档记录修复方案为 `shlex.quote(video_path)`，但代码中**未实际使用**。虽然使用了 list 而非 shell=True，但 ffmpeg 本身仍可解析路径中的 shell 特殊字符 |

### 🟡 MEDIUM — 应在近期修复

| # | 问题 | 文件:行号 | 说明 |
|---|------|----------|------|
| M1 | **SQL 查询使用 f-string 插值** | `backend/repositories.py:101,104,142` | 对 `limit` 等值使用 f-string 插值，虽有 `int()` 保护但模式危险，易被 copy-paste 引入 SQL 注入 |
| M2 | **同类 f-string SQL 问题** | `backend/services/task_queue.py:215-220` | 同上 |
| M3 | **redis 依赖未使用** | `requirements.txt` | 列出了 `redis>=4.0` 但实际使用 SQLiteTaskQueue，依赖未清理可能造成混淆 |

### 🟢 LOW — 建议跟踪

| # | 问题 | 说明 |
|---|------|------|
| L1 | 限流使用内存存储 | slowapi 限流基于内存，无法跨多实例共享；当前适合单实例部署 |
| L2 | 无 E2E 测试 | 仅单元测试和 API 测试，缺少 Playwright/Cypress 端到端测试 |
| L3 | 前端 API_KEY 空值处理 | `VITE_API_KEY` 未设置时前端发送空字符串，后端正确返回 401，但前端无提示 |

---

## 5. 下一步行动计划

### 5.1 优先级排序（综合严重性 + V2 完成度）

| 优先级 | 动作项 | 工作量 | 负责人建议 |
|--------|--------|--------|------------|
| **P0 — 立即** | 修复 auth.py 认证绕过（H1） | < 30min | 安全红线，修复后才能部署 |
| **P0 — 立即** | 完成 frame_extractor.py 的 shlex.quote（H2） | < 15min | 配套 COMPLETE_FIXES.md 落地 |
| **P1 — 本周** | Prompt 配置化（M） | ~2h | V2 PRD P0 要求，阻碍用户体验定制 |
| **P1 — 本周** | 实现真实 estimate_cost()（M） | ~1h | V2 PRD P0 要求，缺少会导致用户无法预估成本 |
| **P2 — 下周** | 重构 repositories.py / task_queue.py 的 SQL f-string（M1-M2） | ~3h | 防止未来注入风险 |
| **P2 — 下周** | 添加拖拽上传 UI（P） | ~4h | V2 PRD Section 9.1 要求 |
| **P3 — V2.1** | 搜索结果排序：按命中次数 + 导入时间 | ~2h | MVP 扩展功能 |
| **P3 — V2.1** | 临近帧上下文展示 | ~3h | MVP 扩展功能 |
| **P4 — 未来** | CSV/Excel 导出 | ~3h | V2.1 规划 |
| **P4 — 未来** | 场景切换检测抽帧 | ~8h | V2.1 规划 |
| **P5 — 长期** | 向量语义搜索 | ~2d | V2.2 规划，需引入 embedding 模型 |

### 5.2 时间分配建议

```
P0 安全修复:        10%  (~4h)   ← 立即处理，不能带着上线
P1 V2 MVP 收尾:     25%  (~10h)  ← 本周完成，达成 MVP 交付
P2 代码质量加固:    20%  (~8h)   ← 下周完成，消除中期风险
P3 V2.1 基础功能:  30%  (~12h)  ← 下下周开始
P4/P5 扩展功能:     15%  (~6h)   ← 按需安排
```

### 5.3 部署前检查清单

在将代码部署到任何非本地环境之前，**必须**完成：

- [ ] `backend/auth.py` — 确保 `API_KEY` 环境变量在所有部署环境中已设置
- [ ] `backend/services/frame_extractor.py` — 确认 `shlex.quote(video_path)` 已添加
- [ ] 验证所有 14 项 COMPLETE_FIXES.md 修复真正落地（当前 2 项 partial）
- [ ] 配置真实的 API 费用估算（当前 estimate_cost 返回 0）

---

## 附录：文件级问题索引

| 文件 | 问题 |
|------|------|
| `backend/auth.py:46-47` | H1: 认证绕过 |
| `backend/services/frame_extractor.py:29` | H2: 命令注入修复不完整 |
| `backend/repositories.py:101,104,142` | M1: SQL f-string |
| `backend/services/task_queue.py:215-220` | M2: SQL f-string |
| `requirements.txt` | M3: redis 依赖未使用 |
| `prompts/screen_analysis.py` | V2: Prompt 硬编码 |
| `frontend/src/pages/ImportPage.tsx` | V2: 缺拖拽 UI |
| `frontend/src/pages/ResultDetailPage.tsx` | V2: 缺前/后帧上下文 |

---

*报告生成时间: 2026-04-12 | 由 project-audit team 综合 project-auditor、v2-gap-analyzer、tech-debt-scanner 三个子审计报告生成*
