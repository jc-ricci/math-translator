# 数学文献 PDF 翻译系统 — 阶段汇报

> 更新时间：2026-03-24

---

## 一、项目概况

将德语 / 法语 / 英语数学 PDF（含扫描件）翻译为中文，完整保留 LaTeX 数学公式，输出可在浏览器直接阅读的网页。

| 项目地址 | https://github.com/jc-ricci/math-translator |
|---------|---------------------------------------------|
| 本地访问 | http://127.0.0.1:8000 |
| 快捷启动 | 双击 `打开翻译系统.webloc` |

---

## 二、技术架构

### 2.1 系统总览

```
┌─────────────────────────────────────────────────────────────┐
│                     浏览器前端                               │
│  HTML + CSS + 原生 JS（无框架）                              │
│                                                             │
│  用户操作：拖拽上传 PDF → 选语言 → 点击开始翻译              │
│                   │                                         │
│  每 2.5s 轮询进度  ←── setInterval(pollJob, 2500)           │
└──────────────┬──────────────────────────────────────────────┘
               │  HTTP REST API
               ▼
┌─────────────────────────────────────────────────────────────┐
│                   FastAPI 后端                               │
│                                                             │
│  POST /api/upload  ──→  存文件 + 写 DB + 启动后台任务        │
│  GET  /api/jobs/id ──→  读 DB 返回进度                      │
│  DELETE /api/jobs/id →  标记 cancelled                      │
│  GET  /api/download  →  读 storage/ 返回文件                │
└──────────────┬──────────────────────────────────────────────┘
               │  asyncio.create_task（不阻塞请求）
               ▼
┌─────────────────────────────────────────────────────────────┐
│               后台翻译流水线 _pipeline()                     │
│   实时写 DB（status / progress / current_chunk）            │
│   前端通过轮询感知进度                                       │
└─────────────────────────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────────┐
│                      存储层                                  │
│  storage/uploads/{job_id}/source.pdf   原始文件              │
│  storage/images/{job_id}/page_*.png    渲染图片（扫描型）    │
│  storage/translated/{job_id}/chunk_*.mmd  翻译中间文件      │
│  storage/output/{job_id}/              最终输出              │
│    ├── *_translated.html               MathJax 网页          │
│    ├── *_translated.md                 Markdown              │
│    └── latex/main.tex + *.pdf          LaTeX 源码 + PDF      │
│  storage/jobs.db                       SQLite 任务状态       │
└─────────────────────────────────────────────────────────────┘
```

---

### 2.2 翻译流水线详细流程

```
用户上传 PDF
      │
      ▼
┌─────────────────────────────────────────────────┐
│  Step 0：PDF 类型检测                            │
│                                                 │
│  PyMuPDF 提取前 10 页文本                        │
│  计算平均字符数 avg_chars                        │
│                                                 │
│  avg_chars ≥ 100  ──→  文字型（可直接提取文本）  │
│  avg_chars < 100  ──→  扫描型（需视觉 OCR）      │
│                                                 │
│  DB：status=ocr, progress=3%                    │
└──────────┬──────────────────┬───────────────────┘
           │                  │
    ┌──────▼──────┐    ┌──────▼──────┐
    │  文字型路径  │    │  扫描型路径  │
    └──────┬──────┘    └──────┬──────┘
           │                  │
           ▼                  ▼
  PyMuPDF 提取每页文字      PyMuPDF 渲染每页为 PNG
  按 10 页一批分组           分辨率 200 DPI
  加页码标记                按 3 页一批分组
  %%PAGE_BREAK%% 分隔
           │                  │
           └────────┬─────────┘
                    │  （每批循环处理）
                    ▼
┌─────────────────────────────────────────────────┐
│  Step 1：Claude + GPT-4o 并行翻译（每批）        │
│                                                 │
│  asyncio.gather(                                │
│    translate_text_claude(batch),    ←─ 文字型   │
│    translate_text_openai(batch),                │
│  )                                              │
│  或                                             │
│  asyncio.gather(                                │
│    vision_ocr_claude(images),       ←─ 扫描型   │
│    translate_vision_openai(images),             │
│  )                                              │
│                                                 │
│  Claude 调用：claude-sonnet-4-6                  │
│    · 系统提示词：OCR 规则 + 翻译规则（r-string）  │
│    · max_tokens=16000, temperature=0.1          │
│    · 失败重试最多 5 次，间隔 15s（503 则 3倍延迟）│
│                                                 │
│  GPT-4o 调用：gpt-4o                            │
│    · 独立客户端并发请求                          │
│    · 失败重试最多 3 次                           │
│                                                 │
│  若 GPT 失败（429/503/网络）→ 降级：             │
│    跳过 gather，单独调用 Claude                  │
│                                                 │
│  DB：status=translating, progress=8~76%         │
└────────────────────┬────────────────────────────┘
                     │  claude_result + openai_result
                     ▼
┌─────────────────────────────────────────────────┐
│  Step 2：Claude 交叉审核合并（每批）              │
│                                                 │
│  输入：Claude 译文 + GPT 译文 + 原文（可选）     │
│  模型：claude-sonnet-4-6                         │
│  任务：评审两份译文，按优先级合并：               │
│    1. 公式完整性（$...$ 不得改动）               │
│    2. 数学逻辑忠实度                             │
│    3. 术语规范性（定理/引理/证明/□）             │
│    4. 语言流畅性                                 │
│  输出：一份最终中文译文                          │
│                                                 │
│  DB：status=validating, progress≈批次中间值      │
└────────────────────┬────────────────────────────┘
                     │  translated_chunks[]
                     ▼
┌─────────────────────────────────────────────────┐
│  Step 3：提取 PDF 嵌入图片                       │
│                                                 │
│  PyMuPDF 遍历所有页面                           │
│  按内容 MD5 去重                                 │
│  跳过 < 50×50px 的小图标                        │
│  保存至 output/{job_id}/images/                  │
│  记录页号、尺寸、文件名                          │
│                                                 │
│  DB：status=compiling, progress=88%             │
└────────────────────┬────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────┐
│  Step 4：生成三种格式输出                        │
│                                                 │
│  ① Markdown                                     │
│     translated_chunks 用 \n\n---\n\n 连接       │
│     写入 *_translated.md                        │
│                                                 │
│  ② HTML（html_renderer.py）                     │
│     · 保护 $...$ / $$...$$ 不被 Markdown 解析   │
│     · 标题 # → <h1>，**粗体** → <strong>        │
│     · 正则识别「定理/引理/证明」→ 加样式框       │
│     · 嵌入提取的图片（Base64 内联）             │
│     · 写入 MathJax 3.0 CDN 加载代码             │
│     · 写入 *_translated.html                    │
│                                                 │
│  ③ LaTeX（latex_merger.py）                     │
│     · 读取 templates/base.tex（ctex 中文模板）  │
│     · Markdown 标题 → \section / \subsection   │
│     · 插入 \includegraphics 图片引用             │
│     · \clearpage 分页                           │
│     · 写入 output/{job_id}/latex/main.tex       │
│                                                 │
│  DB：status=compiling, progress=92%             │
└────────────────────┬────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────┐
│  Step 5：XeLaTeX 编译 PDF（compiler.py）         │
│                                                 │
│  运行 xelatex 两次（第二次处理交叉引用）         │
│  工作目录：output/{job_id}/latex/               │
│  输出：*_translated.pdf                         │
│                                                 │
│  编译失败 → 仅打印警告，has_pdf=0               │
│  编译成功 → has_pdf=1                           │
│                                                 │
│  DB：status=done, progress=100%                 │
└─────────────────────────────────────────────────┘
```

---

### 2.3 前端状态机

```
页面加载
  └─ localStorage 有 lastJobId？
       ├─ done      → 直接展示结果区
       ├─ error     → 直接展示错误区
       └─ 进行中    → 继续轮询

用户上传文件
  └─ POST /api/upload
       └─ 返回 job_id
            └─ startJob(jobId)
                 ├─ showSection('progress')
                 └─ setInterval(pollJob, 2500ms)
                          │
                          ▼
                   GET /api/jobs/{id}
                          │
              ┌───────────┼───────────┐
           done          error     进行中
              │            │          │
         showResult    showError  updateProgress
              │                       │
         设置下载链接            进度条动画
         has_pdf=false             心跳爬行
         隐藏 PDF 按钮          （停滞时 +0.3%/次）
```

---

### 2.4 进度与状态对应关系

| DB status | 前端显示 | 进度范围 |
|-----------|---------|---------|
| `pending` | 等待处理… | 0% |
| `ocr` | 页面渲染中 | 3–5% |
| `translating` | Claude+GPT 并行翻译中 | 8–76% |
| `validating` | Claude 交叉审核合并中 | 批次中间值 |
| `compiling` | 生成网页中 | 88–95% |
| `done` | 完成 | 100% |
| `error` | 出错 | — |
| `cancelled` | 已取消 | — |

### 后端 API

| 方法 | 路径 | 功能 |
|------|------|------|
| POST | `/api/upload` | 接收 PDF，启动翻译 |
| GET | `/api/jobs/{id}` | 实时进度查询 |
| DELETE | `/api/jobs/{id}` | 取消任务 |
| GET | `/api/preview/{id}` | 浏览器预览 |
| GET | `/api/download/{id}/{fmt}` | 下载 html / md / tex / pdf |

### 数据库字段

```
id · status · progress · total_chunks · current_chunk
source_lang · target_lang · filename · has_pdf · error_msg
created_at · updated_at
```

---

## 三、前端结构

```
header          渐变标题 + 双模型标签
upload-section  拖拽上传 · 语言选择 · 开始翻译
progress-section 文件名 · 流光进度条 · 状态 · 取消按钮
result-section  预览 · HTML / MD / .tex / PDF 下载
error-section   错误摘要 + 可折叠完整日志
```

**设计特点：** 四区域互斥显示；进度条 shimmer 动画；CSS 变量设计系统；移动端响应式。

---

## 四、翻译任务完成情况

| 文件 | 类型 | 大小 | 状态 | 完成时间 |
|------|------|------|------|---------|
| VISE_Endbericht（德文报告） | 文字型 | 2.3 MB | ✅ 完成 | 03-19 |
| Chapter2_MinimalSurfaces | 文字型 | — | ✅ 完成 | 03-15 |
| Chapter3_MinimalSurfaces | 文字型 | 7 MB | ✅ 完成 | 03-06 |
| MA_14_1_slides（数分B3） | 文字型 | — | ✅ 完成 | 03-18 |
| **数学分析讲义（第三册）** | 扫描型 | **32 MB** | ❌ 未完成 | — |

---

## 五、本阶段全部改动

### 后端

| 文件 | 改动 |
|------|------|
| `database.py` | 新增 `filename`、`has_pdf` 字段；自动 migrate 旧库 |
| `routers/upload.py` | 存储文件名；PDF 编译成功才标 `has_pdf=1`；错误分层（摘要 + traceback） |
| `routers/jobs.py` | 新增 `DELETE` 取消接口；响应增加 `filename`、`has_pdf`、`error_summary`、`error_detail` |
| `services/*.py` | `trust_env=False` → `True`，修复 Claude API 403 / proxy 问题 |

### 前端

| 文件 | 改动 |
|------|------|
| `index.html` | 完全重构；SVG 图标；删除历史记录区块 |
| `style.css` | 全新设计系统（CSS 变量 · 渐变标题 · shimmer 进度条 · 响应式） |
| `app.js` | 文件名显示；`has_pdf` 控制 PDF 按钮；取消任务；错误分层展示 |

### 环境 & 部署

| 项目 | 处理 |
|------|------|
| GitHub 仓库 | 初始化并推送至 `jc-ricci/math-translator` |
| `.gitignore` | 排除 `.env`、`storage/`、`翻译任务/` |
| `.env.example` | 提供配置模板 |
| 代理修复 | `trust_env=True` 让 Claude SDK 走系统 proxy（解决 403）|
| 端口冲突 | 停止占用 8000 端口的旧进程，启动正确服务 |
| 快捷方式 | 创建 `打开翻译系统.webloc`，双击直接打开 |

### 清理

删除废弃服务（旧 Nougat 流程遗留）：`ocr_service.py` · `pdf_splitter.py` · `translation_service.py`

---

## 六、已知问题

| 优先级 | 问题 | 说明 |
|--------|------|------|
| P0 | **数学分析讲义翻译失败** | 32MB 扫描件，API 正常后直接重新上传即可 |
| P0 | **OpenAI 配额耗尽** | 充值或在 `.env` 留空 `OPENAI_API_KEY` 退化为 Claude 单独翻译 |
| P1 | 取消任务仅标记 DB | 后台协程仍在运行，需引入 `asyncio.Task.cancel()` |
| P1 | 无并发任务限制 | 需加 `asyncio.Semaphore` |
| P2 | 无预计剩余时间 | `total_chunks` 和 `current_chunk` 已有，可计算 |
| P2 | 移动端细节 | 结果按钮区在极窄屏下布局待优化 |

---

## 七、启动方式

```bash
# 启动服务
cd /Users/merciller/Claude/math-translator/backend
uvicorn main:app --port 8000 --log-level info

# 然后双击 打开翻译系统.webloc
# 或浏览器访问 http://127.0.0.1:8000
```
