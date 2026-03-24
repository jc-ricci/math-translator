import asyncio
import base64
import os
from pathlib import Path

try:
    from openai import AsyncOpenAI
except ImportError:
    AsyncOpenAI = None

LANG_NAMES = {
    "de": "德语", "fr": "法语", "en": "英语", "zh": "中文",
}

SYSTEM_PROMPT_TEXT = r"""你是一位顶级数学文献翻译专家，精通{source_lang}和{target_lang}数学语言。

## 翻译要求
- 逐段完整翻译，严禁跳过、省略或压缩任何段落
- **所有 $...$、$$...$$、\begin{{}}...\end{{}} 内容绝对不翻译，原样保留**
- 数学术语统一：定理/引理/命题/推论/定义/证明/□
- 专业术语首次出现保留原文括注：如 连续统(Kontinuum)
- 旧式表达现代化：infinitely small → 趋近于零（或 ε-δ 语言）
- 严格忠实原文逻辑，不增不减

## 输出格式
- 章节标题：# 一级  ## 二级  ### 三级
- 定理类：**定理**、**引理**、**命题**、**推论**、**定义**、**证明**
- 证明结束：$\square$
- 行内公式：$...$  独立公式：$$...$$
- 用 --- 分隔各页（对应输入的 %%PAGE_BREAK%%）
- 直接输出译文，不加任何前言或说明"""

MAX_RETRIES = 3
RETRY_DELAY = 10


def _get_model() -> str:
    return os.environ.get("OPENAI_MODEL", "gpt-4o")


def _make_client() -> "AsyncOpenAI":
    if AsyncOpenAI is None:
        raise ImportError("openai package not installed. Run: pip install openai")
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY not set in environment")
    return AsyncOpenAI(api_key=api_key)


async def translate_text_batch(
    batch_text: str,
    source_lang: str,
    target_lang: str = "zh",
) -> str:
    """Translate a text batch using OpenAI."""
    src_name = LANG_NAMES.get(source_lang, source_lang)
    tgt_name = LANG_NAMES.get(target_lang, target_lang)
    system = SYSTEM_PROMPT_TEXT.format(source_lang=src_name, target_lang=tgt_name)
    user_msg = (
        f"请将以下{src_name}数学文献完整翻译为{tgt_name}，"
        "逐段翻译，不得跳过任何内容，"
        "用 --- 分隔各页对应输入中的 %%PAGE_BREAK%%：\n\n" + batch_text
    )

    last_exc = None
    for attempt in range(MAX_RETRIES):
        try:
            client = _make_client()
            response = await client.chat.completions.create(
                model=_get_model(),
                max_tokens=16000,
                temperature=0.1,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_msg},
                ],
            )
            return response.choices[0].message.content
        except Exception as exc:
            last_exc = exc
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAY * (attempt + 1))
    raise last_exc


async def translate_vision_batch(
    image_paths: list[Path],
    source_lang: str,
    target_lang: str = "zh",
) -> str:
    """OCR + translate a batch of page images using OpenAI vision."""
    src_name = LANG_NAMES.get(source_lang, source_lang)
    tgt_name = LANG_NAMES.get(target_lang, target_lang)

    content: list[dict] = []
    for img_path in image_paths:
        img_data = base64.standard_b64encode(img_path.read_bytes()).decode()
        content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/png;base64,{img_data}",
                "detail": "high",
            },
        })
    content.append({
        "type": "text",
        "text": (
            f"请对以上 {len(image_paths)} 页扫描数学文献进行精确OCR识别，"
            f"并从{src_name}完整翻译为{tgt_name}。\n\n"
            "要求：\n"
            "1. 逐行提取每个字、每个公式符号，输出篇幅应与原页内容相当\n"
            "2. 数学符号必须转为对应LaTeX命令，不得用文字描述代替\n"
            "3. 所有 $...$、$$...$$、\\begin{...}...\\end{...} 内容绝对不翻译\n"
            "4. 遇到图表：输出 [图N: 图题文字] 占位\n"
            "5. 各页之间用 --- 分隔\n"
            "6. 直接输出译文，不加任何前言"
        ),
    })

    last_exc = None
    for attempt in range(MAX_RETRIES):
        try:
            client = _make_client()
            response = await client.chat.completions.create(
                model=_get_model(),
                max_tokens=16000,
                temperature=0.1,
                messages=[{"role": "user", "content": content}],
            )
            return response.choices[0].message.content
        except Exception as exc:
            last_exc = exc
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAY * (attempt + 1))
    raise last_exc
