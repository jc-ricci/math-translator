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

```
浏览器（原生 HTML / CSS / JS）
    │  REST API + 2.5s 轮询
    ▼
FastAPI 后端 ── SQLite 任务队列
    └── 后台异步 _pipeline()
            ├── 类型检测：文字型 vs 扫描型
            ├── Claude + GPT-4o 并行翻译 / 视觉 OCR
            ├── Claude 交叉审核合并
            └── 输出：HTML(MathJax) / Markdown / LaTeX → PDF
```

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
