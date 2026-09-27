/** 与后端 api/ 路由逐一对应的类型定义 */

export interface Envelope<T> {
  status: 'success' | 'error'
  data: T
  message?: string
  duration_ms?: number
}

export interface HealthData {
  status: string
  version: string
}

/* ---------------- 文档 ---------------- */

export interface DocumentSummary {
  id: string
  title: string
  authors: string[]
  year: string | null
  journal: string | null
  doi: string | null
  total_pages: number
  chunk_count: number
  created_at: string | null
}

export interface DocumentListData {
  total: number
  page: number
  page_size: number
  documents: DocumentSummary[]
}

export interface DocumentStats {
  total_documents: number
  total_chunks: number
  total_pages: number
}

export interface Chunk {
  id: string
  text: string
  page: number | null
}

export interface DocumentDetail {
  id: string
  title: string
  authors: string[]
  year: string | null
  journal: string | null
  doi: string | null
  file_path: string | null
  total_pages: number
  chunks: Chunk[]
}

/* ---------------- 标签 ---------------- */

export interface TagItem {
  value: string
  confidence: number
  evidence: string
  source: string
  needs_review: boolean
}

export interface DocumentTagsData {
  doc_id: string
  title: string
  tags: Record<string, TagItem[]>
  total: number
}

/* ---------------- 导入 ---------------- */

export interface IngestUploadData {
  task_id: string
  filename: string
  file_size: number
  file_path: string
}

export interface IngestEventItem {
  seq: number
  stage: string
  percent: number
  message: string
  level: string
}

export interface IngestTaskSnapshot {
  task_id: string
  filename: string
  file_path: string
  status: 'running' | 'completed' | 'failed' | 'skipped'
  stage: string
  percent: number
  error: string | null
  result: Record<string, unknown> | null
  created_at: number
  finished_at: number | null
  events: IngestEventItem[]
}

/* ---------------- 检索 ---------------- */

export interface SearchResultItem {
  chunk: {
    id: string
    text: string
    page: number | null
    metadata?: Record<string, unknown>
  }
  score: number
  source: string
  rank: number
}

export interface SearchData {
  query: string
  results: SearchResultItem[]
  total_found: number
  duration_ms: number
}

export interface SearchParams {
  query: string
  top_k: number
  use_bm25: boolean
  use_vector: boolean
  use_rerank: boolean
}

/* ---------------- 写作 Agent（同步接口） ---------------- */

export interface OutlineData {
  topic: string
  outline: string
}

export interface ParagraphData {
  original: string
  polished: string
}

/* ---------------- 风格 ---------------- */

export interface StyleData {
  original: string
  optimized: string
  mode: string
}

export type StyleMode = 'polish' | 'simplify' | 'academic'

/* ---------------- 论文分析 ---------------- */

export interface EvidenceText {
  text: string
  evidence_pages: number[]
}

export interface AnalysisResult {
  title: string
  authors: string[]
  year: string
  journal: string
  research_method: { text: string; evidence_pages: number[] }
  key_findings: EvidenceText[]
  limitations: string[]
}

export interface AnalysisData {
  doc_id: string
  analysis: AnalysisResult
}

export type AnalysisType = 'full' | 'method' | 'results' | 'limitations'

/* ---------------- 主 Agent 会话 ---------------- */

export interface AgentStep {
  iteration: number
  tool: string
  arguments: Record<string, unknown>
  output: string
}

export interface AgentChatData {
  session_id: string
  content: string
  iterations: number
  stopped_reason: string
  steps: AgentStep[]
}

export interface SessionSummary {
  id: string
  title: string
  created_at: string | null
  updated_at: string | null
  message_count: number
}

export interface SessionListData {
  total: number
  sessions: SessionSummary[]
}

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

export interface WritingContextPayload {
  topic: string
  framework: string
  ideas: string
  requirements: string
  sections: { title: string; content: string }[]
}

export interface SessionDetailData {
  session_id: string
  message_count: number
  messages: ChatMessage[]
  context: Partial<WritingContextPayload>
}

/* ---------------- WebSocket 事件 ---------------- */

export type AgentSocketEvent =
  | { type: 'tool_call'; iteration: number; tool: string; arguments: Record<string, unknown> }
  | { type: 'tool_result'; iteration: number; tool: string; output: string }
  | { type: 'token'; content: string; done: false }
  | {
      type: 'done'
      session_id: string
      content: string
      iterations: number
      stopped_reason: string
      steps: AgentStep[]
      duration_ms: number
    }
  | { type: 'error'; message: string }
