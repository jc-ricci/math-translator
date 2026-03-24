import anthropic
import asyncio
import base64
import httpx
import os
from pathlib import Path

LANG_NAMES = {
    "de": "德语",
    "fr": "法语",
    "en": "英语",
    "zh": "中文",
}

SYSTEM_PROMPT = r"""你是世界顶级的数学文献OCR专家和翻译专家，专门处理扫描版数学书籍和论文。

## 第一步：精确OCR识别

### 文字识别
- 逐行、逐字提取页面所有文字，包括正文、脚注、页眉页脚、边注、图题、表格
- 识别不同字体含义：斜体通常是变量（$x$, $f$），粗体通常是向量（$\mathbf{{v}}$），花体是集合（$\mathcal{{F}}$）
- 严禁跳过、压缩或省略任何段落，哪怕内容密集

### 数学公式识别（最高精度要求）
- 行内公式用 $...$ 包裹，独立成行的公式用 $$...$$ 或 \begin{{equation}}...\end{{equation}}
- 精确识别每个符号：
  - 求和 $\sum$、积分 $\int$、极限 $\lim$、偏导 $\partial$
  - 上下标：$x_{{i}}^{{2}}$、$\sum_{{i=1}}^{{n}}$
  - 分式：$\frac{{a}}{{b}}$、矩阵：\begin{{pmatrix}}...\end{{pmatrix}}
  - 希腊字母：α→\alpha, β→\beta, ε→\varepsilon, φ→\varphi 等
  - 特殊符号：∞→\infty, ∈→\in, ⊂→\subset, ∀→\forall, ∃→\exists
- 公式识别有疑义时，以最忠实原文的方式处理，不猜测、不简化

### 图片和图表处理
- 遇到图表/插图：输出占位符 `[图\{{编号\}}: \{{图题文字\}}]`，提取图题和说明文字
- 遇到表格：用 Markdown 表格格式重建，保留所有数据

## 第二步：忠实翻译

- 将{source_lang}文字翻译为流畅准确的现代{target_lang}数学语言
- **$...$、$$...$$、\begin{{}}...\end{{}} 内的所有内容绝对不翻译，原样输出**
- 术语统一：定理/引理/命题/推论/定义/注记/证明/□
- 专业术语首次出现括注原文：连续统(Kontinuum)、流形(Mannigfaltigkeit)
- 旧式表达现代化：infinitely small → 趋近于零（$\varepsilon$-$\delta$ 语言）
- 严格忠实原文逻辑和结构，不增不减，不调换段落顺序

## 输出格式
- 章节标题：# 一级  ## 二级  ### 三级  #### 四级
- 定理环境：**定理 X.X**、**引理**、**命题**、**推论**、**定义**、**注记**
- 证明：**证明** ... $\square$
- 直接输出译文正文，不加任何前言、说明或注释"""

MAX_RETRIES = 5
RETRY_DELAY = 15  # seconds


def _make_client() -> anthropic.AsyncAnthropic:
    api_key = os.environ.get("ANTHROPIC_AUTH_TOKEN") or os.environ.get("ANTHROPIC_API_KEY")
    base_url = os.environ.get("ANTHROPIC_BASE_URL")
    # Bypass system proxy to avoid SSL proxy interference
    http_client = httpx.AsyncClient(trust_env=True, timeout=120.0)
    return anthropic.AsyncAnthropic(
        api_key=api_key,
        base_url=base_url,
        default_headers={"Authorization": f"Bearer {api_key}"},
        http_client=http_client,
    )


async def process_batch(
    image_paths: list[Path],
    source_lang: str,
    target_lang: str = "zh",
) -> str:
    """Send a batch of page images to Claude for OCR + translation, with retries."""
    content: list[dict] = []
    for img_path in image_paths:
        img_data = base64.standard_b64encode(img_path.read_bytes()).decode()
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": img_data,
            },
        })

    src_name = LANG_NAMES.get(source_lang, source_lang)
    tgt_name = LANG_NAMES.get(target_lang, target_lang)
    content.append({
        "type": "text",
        "text": (
            f"请对以上 {len(image_paths)} 页扫描数学文献进行精确OCR识别，"
            f"并从{src_name}完整翻译为{tgt_name}。\n\n"
            "注意事项：\n"
            "1. 逐行提取每个字、每个公式符号，输出篇幅应与原页内容相当\n"
            "2. 数学符号必须转为对应LaTeX命令，不得用文字描述代替\n"
            "3. 遇到图表：输出 [图N: 图题文字] 占位，不描述图形内容\n"
            "4. 各页之间用 --- 分隔\n"
            "5. 直接输出译文，不加任何前言"
        ),
    })

    system = SYSTEM_PROMPT.format(source_lang=src_name, target_lang=tgt_name)

    img_sizes = [f"{p.stat().st_size//1024}KB" for p in image_paths]
    print(f"  [vision] 发送 {len(image_paths)} 张图片到Claude，大小：{img_sizes}")

    last_exc = None
    for attempt in range(MAX_RETRIES):
        try:
            client = _make_client()
            print(f"  [vision] 第{attempt+1}次尝试，调用API...")
            message = await client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=16000,
                temperature=0.1,
                system=system,
                messages=[{"role": "user", "content": content}],
            )
            result = message.content[0].text
            print(f"  [vision] 完成，输出 {len(result)} 字符")
            return result
        except Exception as exc:
            last_exc = exc
            if attempt < MAX_RETRIES - 1:
                # 503 需要等更长时间
                wait = RETRY_DELAY * (attempt + 1) * (3 if "503" in str(exc) else 1)
                await asyncio.sleep(wait)

    raise last_exc


async def process_all_batches(
    batches: list[list[Path]],
    source_lang: str,
    target_lang: str = "zh",
    progress_callback=None,
) -> list[str]:
    """Process all batches sequentially and return list of translated texts."""
    results = []
    total = len(batches)

    for idx, batch in enumerate(batches):
        text = await process_batch(batch, source_lang, target_lang)
        results.append(text)
        if progress_callback:
            await progress_callback(idx + 1, total)

    return results
