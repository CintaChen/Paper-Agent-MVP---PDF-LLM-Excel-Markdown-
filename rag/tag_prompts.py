"""内容标签提取 Prompt"""

CONTENT_TAG_SYSTEM_PROMPT = """你是一名专业的学术文献分析专家。
你的任务是从论文中提取结构化的「内容标签」，包括：领域、主题、方法论。

【绝对红线】
1. 所有标签必须基于论文原文，禁止推断或编造
2. 每个标签必须附带原文证据（evidence），截取完整句子（可以跨句），不超过 200 字
3. 如果论文中找不到明确依据，该字段留空列表，不要猜测
4. 置信度反映标签与论文的相关程度，0.0-1.0
5. 如果论文内容模糊或证据不足，needs_review 设为 true
6. 必须严格输出 JSON，不输出任何其他内容，不输出 Markdown 代码块
"""

CONTENT_TAG_USER_PROMPT = """请从以下论文中提取内容标签。

【论文信息】
标题：{title}
摘要：{abstract}
引言（前 2000 字）：{introduction}
{keywords_info}

【提取规则】
1. domain（领域）：论文所属的学科领域，选择最贴切的一个
2. topics（主题）：论文研究的核心主题/关键词，2-5 个
   - 优先使用 PDF 中的 Keywords
   - 如果 Keywords 为空或不足，从摘要中提取
3. methodologies（方法论）：论文采用的研究方法，1-3 个
4. confidence（置信度）：0.0-1.0
5. evidence（证据）：每个标签的原文依据，截取完整句子，不超过 200 字
6. needs_review：证据不足时设为 true

【输出 JSON 格式】
{{
  "domain": "领域名称",
  "topics": ["主题1", "主题2"],
  "methodologies": ["方法1"],
  "confidence": 0.85,
  "evidence": {{
    "domain": "原文摘录",
    "topics": ["原文摘录1"],
    "methodologies": ["原文摘录1"]
  }},
  "needs_review": false
}}

【最终检查】
1. 是否只输出了 JSON？
2. 每个标签是否有对应的 evidence？
3. topics 数量是否 >= 2？
4. needs_review 是否在证据不足时标记为 true？

论文内容：
{content}
"""

TITLE_EXTRACTION_PROMPT = """请从以下学术论文首页文本中提取论文标题。

【规则】
1. 标题通常是首页中最长的完整句子，位于作者信息和摘要之间
2. 过滤以下噪音行：Available online at、Academic Editor、ORIGINAL ARTICLE、Received:、Accepted:、DOI:、期刊名、页码、版权声明
3. 如果找不到明确标题，返回空字符串
4. 只输出标题文本，不要引号，不要解释，不要换行

【首页文本】
{text}

标题："""
