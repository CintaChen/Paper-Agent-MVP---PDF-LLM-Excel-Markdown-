"""Prompt templates for paper analysis."""

SYSTEM_PROMPT = """你是一名严谨的学术论文分析助手。
你的任务是根据用户提供的论文内容，提取并总结论文的关键信息。

绝对红线：
1. 所有回答必须使用中文（标题保留原文语言）。
2. 不要编造论文中没有的信息。
3. 如果某项信息无法从正文中判断，请写"未识别"或"文中未明确说明"。
4. 必须按照 JSON 格式输出，不要输出 JSON 以外的任何内容，不要输出 Markdown 代码块标记。
"""

ANALYSIS_PROMPT = """请分析以下论文内容，输出结构化总结。

论文题目：{title}
论文内容：
{content}

===== 分步执行指令 =====
请严格按照以下步骤进行分析，不要跳步：

Step 1【基础信息】：识别标题、作者、年份、期刊。作者按正文出现顺序排列；无法识别则返回空列表或 null。
Step 2【方法与设计】：区分"宏观研究方法"和"微观实验设计"。
  - research_method：回答"用什么范式/工具做研究"（如：定量回归、问卷调查、案例研究、深度学习、SEM）。
  - experimental_design：回答"具体怎么操作/验证"（如：自变量/因变量设置、实验组/对照组、评价指标、稳健性检验、交叉验证）。
  - 如果论文不是实验类，experimental_design 填写其研究设计或分析设计。
Step 3【证据定位】：为 research_method、data_source、key_findings 匹配证据。
  - 页码只能来自正文中的 "===== PAGE X =====" 标记，禁止推算或估计。
  - evidence_excerpt 必须是原文中逐字复制的片段（不超过 80 字），不能改写。
  - 如果无法可靠定位，evidence_pages 返回 []，evidence_excerpt 返回 ""，不要编造。
Step 4【局限区分】：
  - limitations_reported：只填作者在原文中明确写出的局限（通常在"研究不足""局限性""未来展望"段落）。如果作者没写，返回 []。
  - limitations_inferred：由你根据样本、数据、方法合理推断，必须使用谨慎语言（如"可能""外部适用性可能有限"）。
Step 5【相关性评分】：以 '{evaluation_topic}' 为唯一参照主题，给出 1-10 分及简要理由。

===== 字段边界说明（关键）=====
- research_method ✅：问卷调查、深度访谈、面板数据回归、结构方程模型、CNN-LSTM、扎根理论
- research_method ❌：Likert 5 点量表、控制变量选择、F1 值、消融实验（这些属于 experimental_design）
- experimental_design ✅：自变量为 X，因变量为 Y，控制变量为 Z；实验组/对照组设置；使用准确率/召回率评价；稳健性检验
- experimental_design ❌：使用了 Python、使用了 SPSS（这些属于工具/方法）
- data_source：必须使用原文专有名词（如"中国A股上市公司2015-2022年数据""某三甲医院320例患者"），不得概括为"企业数据""患者数据"。

===== 输出 JSON 格式 =====
请严格按照以下结构输出，不要增减字段：
{{
  "extracted_title": "从论文正文中提取的完整标题",
  "authors": ["作者1", "作者2"],
  "year": "2024",
  "journal": "期刊名称",
  "research_background": "研究背景、问题来源或研究动机",
  "research_question": "核心研究问题",
  "research_objective": "研究目标或拟达成的研究任务",
  "research_method": {{
    "text": "总体研究方法",
    "evidence_pages": [1, 3],
    "evidence_excerpt": "原文片段"
  }},
  "model_or_framework": "理论框架、分析模型、算法模型、指标体系或技术路线；无则写'未明确提及'",
  "data_source": {{
    "text": "数据来源、样本对象（使用原文专有名词）",
    "evidence_pages": [2],
    "evidence_excerpt": "原文片段"
  }},
  "experimental_design": "实验设计、变量设置、分组方式、对照方案、评价指标或验证方式；非实验类写研究设计/分析设计",
  "analysis_process": "主要研究步骤、分析流程或实现过程",
  "key_findings": [
    {{
      "text": "结论1",
      "evidence_pages": [5, 6],
      "evidence_excerpt": "原文片段"
    }},
    {{
      "text": "结论2",
      "evidence_pages": [7],
      "evidence_excerpt": "原文片段"
    }}
  ],
  "contributions": "创新点、理论贡献、方法贡献或实践价值",
  "limitations_reported": ["作者明确提出的局限1", "作者明确提出的局限2"],
  "limitations_inferred": ["模型推断的潜在局限1", "模型推断的潜在局限2"],
  "relevance_score": "1-10 分评分及简要理由（参照主题：{evaluation_topic}）"
}}

===== 最终检查（输出前必须确认）=====
1. 是否只输出了 JSON？没有 ```json 标记？
2. limitations_reported 是否全部来自作者原文？没有混入推断？
3. evidence_pages 是否全部来自 PAGE 标记？没有编造页码？
4. research_method 和 experimental_design 是否按边界说明区分？
5. 所有无法识别的字段是否写了"未明确提及"或返回了空值？
"""