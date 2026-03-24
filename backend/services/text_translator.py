import anthropic
import asyncio
import httpx
import os

LANG_NAMES = {
    "de": "德语",
    "fr": "法语",
    "en": "英语",
    "zh": "中文",
}

SYSTEM_PROMPT = r"""你是一位顶级数学文献翻译专家，精通{source_lang}和{target_lang}数学语言。

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

MAX_RETRIES = 5
RETRY_DELAY = 15


def _make_client() -> anthropic.AsyncAnthropic:
    api_key = os.environ.get("ANTHROPIC_AUTH_TOKEN") or os.environ.get("ANTHROPIC_API_KEY")
    base_url = os.environ.get("ANTHROPIC_BASE_URL")
    http_client = httpx.AsyncClient(trust_env=True, timeout=180.0)
    return anthropic.AsyncAnthropic(
        api_key=api_key,
        base_url=base_url,
        default_headers={"Authorization": f"Bearer {api_key}"},
        http_client=http_client,
    )


async def translate_text_batch(
    batch_text: str,
    source_lang: str,
    target_lang: str = "zh",
) -> str:
    src_name = LANG_NAMES.get(source_lang, source_lang)
    tgt_name = LANG_NAMES.get(target_lang, target_lang)
    system = SYSTEM_PROMPT.format(source_lang=src_name, target_lang=tgt_name)

    user_msg = (
        f"请将以下{src_name}数学文献完整翻译为{tgt_name}，"
        "逐段翻译，不得跳过任何内容，"
        "用 --- 分隔各页对应输入中的 %%PAGE_BREAK%%：\n\n" + batch_text
    )

    last_exc = None
    for attempt in range(MAX_RETRIES):
        try:
            client = _make_client()
            message = await client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=16000,
                temperature=0.1,
                system=system,
                messages=[{"role": "user", "content": user_msg}],
            )
            return message.content[0].text
        except Exception as exc:
            last_exc = exc
            if attempt < MAX_RETRIES - 1:
                wait = RETRY_DELAY * (attempt + 1) * (3 if "503" in str(exc) else 1)
                await asyncio.sleep(wait)
    raise last_exc


async def translate_all_text_batches(
    batches: list[str],
    source_lang: str,
    target_lang: str = "zh",
    progress_callback=None,
) -> list[str]:
    results = []
    total = len(batches)
    for idx, batch in enumerate(batches):
        text = await translate_text_batch(batch, source_lang, target_lang)
        results.append(text)
        if progress_callback:
            await progress_callback(idx + 1, total)
    return results
