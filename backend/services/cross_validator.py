"""
Cross-validation: Claude reviews both translations and merges into a final version.
"""
import httpx
import os
import anthropic

LANG_NAMES = {
    "de": "德语", "fr": "法语", "en": "英语", "zh": "中文",
}

JUDGE_SYSTEM_PROMPT = r"""你是一位顶级数学文献翻译审校专家。你将收到同一段数学文献的两个翻译版本（分别来自 Claude 和 GPT），请综合两者的优点，产出最终最准确的译文。

## 审校优先级（从高到低）

1. **数学公式完整性**
   - 所有 $...$、$$...$$、\begin{{}}...\end{{}} 必须完全保留，一字不差
   - 哪个版本公式更完整，优先采用该版本的公式部分

2. **数学逻辑忠实度**
   - 严格忠实原文数学论证逻辑，不增不减
   - 如两个版本逻辑表述不同，选择更贴近原文结构的

3. **数学术语规范性**
   - 定理/引理/命题/推论/定义/注记/证明/□ 统一使用标准中文数学术语
   - 专业术语首次出现保留原文括注

4. **语言流畅性**
   - 在忠实原文的前提下，选择更流畅自然的现代数学中文表达

## 输出要求
- 直接输出最终译文，不添加任何比较说明、版本标注或注释
- 保持原有 Markdown 结构（标题层级、**粗体** 定理名等）
- 保持页分隔符 ---"""


def _make_client():
    api_key = os.environ.get("ANTHROPIC_AUTH_TOKEN") or os.environ.get("ANTHROPIC_API_KEY")
    base_url = os.environ.get("ANTHROPIC_BASE_URL")
    http_client = httpx.AsyncClient(trust_env=True, timeout=180.0)
    return anthropic.AsyncAnthropic(
        api_key=api_key,
        base_url=base_url,
        default_headers={"Authorization": f"Bearer {api_key}"},
        http_client=http_client,
    )


async def merge_translations(
    claude_translation: str,
    openai_translation: str,
    source_lang: str,
    target_lang: str = "zh",
    original_text: str | None = None,
) -> str:
    """
    Use Claude as judge to merge two translations into the final version.

    original_text is optional (available for text-mode PDFs, not for scanned ones).
    """
    src_name = LANG_NAMES.get(source_lang, source_lang)
    tgt_name = LANG_NAMES.get(target_lang, target_lang)

    sections = []
    if original_text:
        sections.append(f"## 原文（{src_name}）\n\n{original_text}")
    sections.append(f"## 翻译版本 A（Claude）\n\n{claude_translation}")
    sections.append(f"## 翻译版本 B（GPT）\n\n{openai_translation}")
    sections.append(f"请审校以上两个{tgt_name}翻译版本，综合产出最终最准确的译文：")

    user_msg = "\n\n---\n\n".join(sections)

    client = _make_client()
    message = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=16000,
        temperature=0.1,
        system=JUDGE_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )
    return message.content[0].text
