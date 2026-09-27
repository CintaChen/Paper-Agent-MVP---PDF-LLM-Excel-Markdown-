"""分块策略"""
from typing import Optional
from core.document import Chunk


def fixed_size_chunks(
    text: str,
    chunk_size: int = None,
    chunk_overlap: int = None,
    page: int = None,
    metadata: dict = None,
) -> list[Chunk]:
    """固定大小分块"""
    from config.settings import settings
    chunk_size = chunk_size or settings.chunk_size
    chunk_overlap = chunk_overlap or settings.chunk_overlap
    metadata = metadata or {}

    chunks = []
    start = 0
    chunk_id = 0

    while start < len(text):
        end = start + chunk_size
        chunk_text = text[start:end]

        if len(chunk_text.strip()) >= 50:
            chunks.append(
                Chunk(
                    id=f"chunk_{chunk_id}",
                    text=chunk_text.strip(),
                    page=page,
                    start_pos=start,
                    end_pos=end,
                    metadata=metadata,
                )
            )
            chunk_id += 1

        start += chunk_size - chunk_overlap

    return chunks


def paragraph_chunks(
    text: str,
    min_length: int = 50,
    page: int = None,
    metadata: dict = None,
) -> list[Chunk]:
    """按段落分块"""
    metadata = metadata or {}
    paragraphs = text.split("\n\n")

    chunks = []
    for i, para in enumerate(paragraphs):
        para = para.strip()
        if len(para) >= min_length:
            chunks.append(
                Chunk(
                    id=f"para_{i}",
                    text=para,
                    page=page,
                    metadata=metadata,
                )
            )

    return chunks


def sliding_window_chunks(
    text: str,
    window_size: int = 500,
    step: int = 250,
    page: int = None,
    metadata: dict = None,
) -> list[Chunk]:
    """滑动窗口分块"""
    metadata = metadata or {}
    chunks = []

    for i, start in enumerate(range(0, len(text), step)):
        end = start + window_size
        chunk_text = text[start:end]

        if len(chunk_text.strip()) >= 50:
            chunks.append(
                Chunk(
                    id=f"slide_{i}",
                    text=chunk_text.strip(),
                    page=page,
                    start_pos=start,
                    end_pos=end,
                    metadata=metadata,
                )
            )

        if end >= len(text):
            break

    return chunks


def parent_child_chunking(
    doc,
    parent_size: int = 1000,
    child_size: int = 200,
    overlap: int = 50,
) -> tuple[list[Chunk], list[Chunk]]:
    """
    父子分块策略

    Returns:
        parents: 大块（语义完整，喂给 LLM）
        children: 小块（用于检索）
    """
    parents = []
    children = []

    # 1. 按章节切分 Parent
    sections = split_by_sections(doc)

    for section in sections:
        # 每个 section 是一个 Parent
        parent_id = f"{doc.id}_parent_{len(parents)}"
        parent = Chunk(
            id=parent_id,
            text=section["text"],
            page=section["page"],
            metadata={
                "doc_id": doc.id,
                "doc_title": doc.title,
                "section_title": section.get("title", ""),
                "type": "parent",
            }
        )
        parents.append(parent)

        # 2. 将 Parent 切成 Child
        section_children = split_into_children(
            section["text"],
            parent_id=parent_id,
            doc_id=doc.id,
            doc_title=doc.title,
            page=section["page"],
            child_size=child_size,
            overlap=overlap,
        )
        children.extend(section_children)

    return parents, children


def split_by_sections(doc) -> list[dict]:
    """按章节标题切分"""
    import re

    full_text = "\n\n".join(c.text for c in doc.chunks)

    # 匹配章节标题（数字编号 或 英文编号）
    section_pattern = r'(?m)^(\d+\.?\s+[A-Z][^\n]+|[A-Z][A-Z\s]{2,})$'

    sections = []
    current_title = ""
    current_text = []
    current_page = 1

    for line in full_text.split('\n'):
        if re.match(section_pattern, line.strip()):
            # 保存上一个 section
            if current_text:
                sections.append({
                    "title": current_title,
                    "text": "\n".join(current_text),
                    "page": current_page,
                })
            current_title = line.strip()
            current_text = []
        else:
            current_text.append(line)

    # 保存最后一个 section
    if current_text:
        sections.append({
            "title": current_title,
            "text": "\n".join(current_text),
            "page": current_page,
        })

    return sections


def split_into_children(
    text: str,
    parent_id: str,
    doc_id: str,
    doc_title: str,
    page: int,
    child_size: int = 200,
    overlap: int = 50,
) -> list[Chunk]:
    """将 Parent 文本切成小块"""
    children = []
    start = 0
    child_id = 0

    while start < len(text):
        end = start + child_size
        chunk_text = text[start:end]

        if len(chunk_text.strip()) >= 30:
            children.append(Chunk(
                id=f"{parent_id}_child_{child_id}",
                text=chunk_text.strip(),
                page=page,
                metadata={
                    "doc_id": doc_id,
                    "doc_title": doc_title,
                    "parent_id": parent_id,
                    "type": "child",
                }
            ))
            child_id += 1

        start += child_size - overlap

    return children
