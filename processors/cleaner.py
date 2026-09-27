"""文本清洗"""
import re
from config.logging import setup_logging

logger = setup_logging(__name__)


def clean_text(text: str) -> str:
    """清洗文本"""
    # 去除多余空行
    text = re.sub(r"\n{3,}", "\n\n", text)
    # 去除行首行尾空白
    lines = [line.strip() for line in text.split("\n")]
    # 去除空行
    lines = [line for line in lines if line]
    return "\n".join(lines)


def remove_header_footer(text: str, header: str = "", footer: str = "") -> str:
    """去除页眉页脚"""
    if header:
        text = text.replace(header, "")
    if footer:
        text = text.replace(footer, "")
    return text


def normalize_whitespace(text: str) -> str:
    """规范化空白字符"""
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_evidence(text: str, keyword: str, window: int = 80) -> str:
    """
    按句子边界截取 evidence，避免长句被截断

    Args:
        text: 原文
        keyword: 需要证据的关键词
        window: 前后窗口大小（字符数）

    Returns:
        包含完整句子的 evidence
    """
    if not text or not keyword:
        return ""

    # 1. 找到关键词位置（不区分大小写）
    pos = text.lower().find(keyword.lower())
    if pos == -1:
        return keyword  # fallback：返回关键词本身

    # 2. 向前找句子开头（取最近的边界）
    start = max(0, pos - window)
    sentence_starts = []
    for sep in ['。', '；', '\n', '. ', '; ']:
        idx = text.rfind(sep, start, pos)
        if idx != -1:
            sentence_starts.append(idx + len(sep))

    if sentence_starts:
        start = max(sentence_starts)  # 取最近的（离 pos 最近的 = 最大的索引）

    # 3. 向后找句子结尾（取最近的边界，而非最远的）
    end = min(len(text), pos + len(keyword) + window)
    sentence_ends = []
    for sep in ['。', '；', '\n', '. ', '; ']:
        idx = text.find(sep, pos, end)
        if idx != -1:
            sentence_ends.append(idx + len(sep))

    if sentence_ends:
        end = min(sentence_ends)  # 取最近的（离 pos 最近的 = 最小的索引）

    evidence = text[start:end].strip()

    return evidence
