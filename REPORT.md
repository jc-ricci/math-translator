# 数学文献PDF翻译系统 — 阶段汇报

> 更新时间：2026-03-23

---

## 一、项目概况

将德语 / 法语 / 英语数学PDF（含扫描件）翻译为中文，完整保留LaTeX数学公式，输出可在浏览器直接阅读的网页。

**核心特色：** Claude + GPT-4o 双模型并行翻译，Claude 交叉审核合并，质量优于单模型。

---

## 二、技术架构

### 整体结构

```
浏览器（原生 HTML / CSS / JS，无框架）
    │  REST API + 2.5s 轮询
    ▼
FastAPI 后端 ── SQLite（任务队列 + 状态持久化）
    │
    └── 后台异步 _pipeline()
            ├── 类型检测：文字型 vs 扫描型
            ├── Claude + GPT-4o 并行翻译 / 视觉OCR
            ├── Claude 交叉审核合并
            └── 输出：HTML(MathJax) / Markdown / LaTeX → PDF
```

### 翻译流水线

```
上传 PDF
  │
  ├─[文字型 >100字/页]─→ PyMuPDF 提取文本（每批10页）
  │                          │
  └─[扫描型]─────────→ PyMuPDF 渲染PNG（200DPI，每批3页）
                             │
                    ┌────────┴────────┐
                    ▼                 ▼
             Claude 翻译/OCR    GPT-4o 翻译/OCR
                    └────────┬────────┘
                             ▼
                      Claude 交叉审核合并
                             │
                    ┌────────┼────────┐
                    ▼        ▼        ▼
                  HTML    Markdown  LaTeX → PDF
               (MathJax)
```

### 后端 API 一览

| 方法 | 路径 | 功能 |
|------|------|------|
| POST | `/api/upload` | 接收PDF，启动翻译流程 |
| GET | `/api/jobs` | 历史任务列表（最近50条）|
| GET | `/api/jobs/{id}` | 单任务实时状态查询 |
| DELETE | `/api/jobs/{id}` | 取消任务 |
| GET | `/api/preview/{id}` | 浏览器内嵌预览 |
| GET | `/api/download/{id}/{fmt}` | 下载 html / md / tex / pdf |

### 数据库字段

```sql
jobs (
  id           TEXT PRIMARY KEY,
  status       TEXT,   -- pending / ocr / translating / validating / compiling / done / error / cancelled
  progress     INTEGER,
  total_chunks INTEGER,
  current_chunk INTEGER,
  source_lang  TEXT,
  target_lang  TEXT,
  filename     TEXT,   -- 原始文件名
  has_pdf      INTEGER,-- PDF编译是否成功
  error_msg    TEXT,   -- "摘要\n\n---\n完整traceback"
  created_at   TIMESTAMP,
  updated_at   TIMESTAMP
)
```

---

## 三、前端架构

### 页面结构

```
┌─────────────────────────────────────────┐
│  header：标题 + 说明                     │
├─────────────────────────────────────────┤
│  #upload-section     ← 初始状态          │
│  ├─ 拖拽区域 / 文件选择                  │
│  ├─ 源语言 / 目标语言选择                │
│  └─ "开始翻译"按钮                      │
├─────────────────────────────────────────┤
│  #progress-section   ← 翻译中           │
│  ├─ 文件名                              │
│  ├─ 进度条 + 百分比                     │
│  ├─ 状态标签 + 第X/Y批                  │
│  └─ 取消任务按钮                        │
├─────────────────────────────────────────┤
│  #result-section     ← 完成             │
│  └─ 预览 / HTML / MD / .tex / PDF 按钮  │
├─────────────────────────────────────────┤
│  #error-section      ← 出错             │
│  ├─ 错误摘要（一行）                    │
│  ├─ <details> 完整traceback（可折叠）   │
│  └─ "重新上传"按钮                      │
├─────────────────────────────────────────┤
│  历史任务列表         ← 常驻显示         │
│  每项：文件名 · 时间 · 状态 · 操作按钮   │
└─────────────────────────────────────────┘
```

**设计原则：** 四个主区域同一时间只显示一个（`showSection(name)`），历史区常驻。无路由、无框架，纯 ES6 IIFE。

### 状态机

```
  [upload] ──POST /api/upload──→ [progress] ──done──→ [result]
     ▲                               │
     │                             error
     │                               │
     └──────────────────────────── [error]
     │
     └── 取消 / 重试 均回到 upload
```

### 进度心跳算法

真实进度（后端推送）直接使用；进度停滞时每次轮询 +0.3%，最高爬到 `min(当前+20, 85%)`，制造"正在工作"的视觉反馈，防止进度条冻结。

---

## 四、翻译任务完成情况

| 文件 | 类型 | 大小 | 状态 | 完成时间 |
|------|------|------|------|---------|
| VISE_Endbericht（德文报告） | 文字型 | 2.3 MB | ✅ 完成 | 2026-03-19 |
| Chapter2_MinimalSurfaces | 文字型 | — | ✅ 完成 | 2026-03-15 |
| Chapter3_MinimalSurfaces | 文字型 | 7 MB | ✅ 完成 | 2026-03-06 |
| MA_14_1_slides（数分B3） | 文字型 | — | ✅ 完成 | 2026-03-18 |
| **数学分析讲义（第三册）** | 扫描型 | **32 MB** | ❌ 未完成 | — |

---

## 五、本阶段改动记录

### 后端

| 文件 | 改动内容 |
|------|---------|
| `database.py` | 新增 `filename`、`has_pdf` 字段；`init_db` 自动 migrate 旧库 |
| `routers/upload.py` | 存储文件名；PDF 编译成功才标 `has_pdf=1`；错误信息分层（摘要 + traceback）；fallback 降级时先更新进度状态 |
| `routers/jobs.py` | 新增 `DELETE /api/jobs/{id}` 取消接口；响应新增 `filename`、`has_pdf`、`error_summary`、`error_detail` |

### 前端

| 文件 | 改动内容 |
|------|---------|
| `index.html` | 进度区加文件名 + 取消按钮；错误区改为摘要 + 可折叠日志 |
| `style.css` | 新增 `.btn-danger`、`.progress-filename`、`.error-summary`、`.error-details` |
| `app.js` | 历史列表显示文件名；`has_pdf=false` 隐藏PDF按钮；错误分层展示；取消任务逻辑；刷新后状态恢复修复 |

### 清理

删除废弃服务（旧 Nougat 流程遗留，已被新流程替代）：
- `services/ocr_service.py`
- `services/pdf_splitter.py`
- `services/translation_service.py`

---

## 六、已知问题

### P0 — 阻塞性

**1. Claude API 403 / proxy 冲突**
- `claude_processor.py` 设置 `trust_env=False` 绕过系统 proxy，在需要 proxy 的网络下 Claude 请求直接被拒
- 影响：所有扫描型任务（含数学分析讲义）无法完成
- 修复：检查 `.env` 中 `ANTHROPIC_BASE_URL`，确认是否需要去掉 `trust_env=False`

**2. OpenAI 配额已耗尽（429）**
- 所有任务强制降级为 Claude 单独处理，失去双模型优势
- 修复：充值配额，或 `.env` 中留空 `OPENAI_API_KEY` 明确跳过 GPT

### P1 — 功能缺陷

**3. 取消任务仅标记 DB，后台协程仍在运行**
- `DELETE /api/jobs/{id}` 只改数据库状态，`_pipeline` 协程不会中止，API 费用持续产生
- 修复：引入 `asyncio.Task` + `task.cancel()` 机制

**4. 无并发任务限制**
- 多标签页同时提交可启动无数 pipeline，并发调用 API
- 修复：上传路由加全局并发信号量

**5. 无任务总超时**
- 单批次有 120s 超时，但整个 pipeline 无总时限，理论上可永久阻塞

### P2 — 体验优化

**6. 历史列表无文件大小**（DB 未存储）

**7. 无预计剩余时间**（`total_chunks` 和 `current_chunk` 已有，可计算）

**8. 错误任务无法一键重试**（需重新选文件，原PDF路径已保留但未利用）

**9. 移动端布局未优化**（结果按钮区和历史操作区在窄屏溢出）

---

## 七、系统能力边界

| 能力 | 状态 |
|------|------|
| 文字型 PDF 翻译（含公式） | ✅ 稳定 |
| 扫描型 PDF 视觉 OCR + 翻译 | ⚠️ 依赖 API 网络正常 |
| GPT 不可用时降级 Claude | ✅ 已实现 |
| HTML 输出（MathJax 实时渲染） | ✅ 稳定 |
| LaTeX / Markdown 输出 | ✅ 稳定 |
| PDF 输出（XeLaTeX 编译） | ⚠️ 依赖本地 XeLaTeX 环境 |
| 任务取消（DB层） | ✅ 本阶段新增 |
| 大文件（>30MB 扫描件） | ❌ 当前受 API 限制阻塞 |
| 生产就绪度 | ⚠️ 个人工具级别 |

---

## 八、近期行动项

| 优先级 | 任务 | 说明 |
|--------|------|------|
| P0 | 排查 Claude 403 | 检查 `.env` + proxy 设置，解决后重试数学分析讲义 |
| P0 | 处理 OpenAI 配额 | 充值或明确禁用 GPT 步骤 |
| P1 | 实现真正的任务取消 | `asyncio.Task.cancel()` |
| P1 | 加并发限制 | 上传路由 `asyncio.Semaphore` |
| P2 | 历史列表加文件大小 | DB 存储 + 前端展示 |
| P2 | 移动端适配 | 结果按钮 + 历史操作区响应式 |
