/** 与后端路由一一对应的调用封装 */
import { API_V1, API_V2, jsonRequest, request } from './client'
import type {
  AnalysisData,
  AnalysisType,
  AgentChatData,
  DocumentDetail,
  DocumentListData,
  DocumentStats,
  DocumentTagsData,
  Envelope,
  HealthData,
  IngestTaskSnapshot,
  IngestUploadData,
  OutlineData,
  ParagraphData,
  SearchData,
  SearchParams,
  SessionDetailData,
  SessionListData,
  StyleData,
  StyleMode,
} from '../types'

function qs(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== '') search.set(key, String(value))
  })
  const text = search.toString()
  return text ? `?${text}` : ''
}

export const api = {
  /* 系统 */
  health: () => request<Envelope<HealthData>>(`${API_V1}/health`),
  stats: () => request<Envelope<DocumentStats>>(`${API_V1}/documents/stats`),

  /* 文档 */
  documents: (params: { page?: number; page_size?: number; search?: string } = {}) =>
    request<Envelope<DocumentListData>>(`${API_V1}/documents${qs(params)}`),
  document: (docId: string) => request<Envelope<DocumentDetail>>(`${API_V1}/documents/${docId}`),
  deleteDocument: (docId: string) =>
    request<Envelope<null>>(`${API_V1}/documents/${docId}`, { method: 'DELETE' }),
  tags: (docId: string) => request<Envelope<DocumentTagsData>>(`${API_V2}/tags/${docId}`),

  /* 导入 */
  upload: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<Envelope<IngestUploadData>>(`${API_V1}/ingest/upload`, {
      method: 'POST',
      body: form,
    })
  },
  ingestTask: (taskId: string) =>
    request<Envelope<IngestTaskSnapshot>>(`${API_V1}/ingest/tasks/${taskId}`),

  /* 检索 */
  search: (params: SearchParams) => jsonRequest<Envelope<SearchData>>(`${API_V1}/search`, params),

  /* 写作 Agent（同步） */
  outline: (body: { topic: string; context_query?: string; top_k?: number }) =>
    jsonRequest<Envelope<OutlineData>>(`${API_V1}/agents/writing/outline`, body),
  paragraph: (body: { topic: string; draft?: string; context_query?: string; top_k?: number }) =>
    jsonRequest<Envelope<ParagraphData>>(`${API_V1}/agents/writing/paragraph`, body),

  /* 风格 */
  style: (body: { text: string; mode: StyleMode }) =>
    jsonRequest<Envelope<StyleData>>(`${API_V1}/agents/style/polish`, body),

  /* 论文分析 */
  analyze: (body: { doc_id: string; analysis_type: AnalysisType }) =>
    jsonRequest<Envelope<AnalysisData>>(`${API_V1}/agents/analysis/analyze`, body),

  /* 主 Agent 会话 */
  chat: (body: {
    message: string
    session_id?: string | null
    context?: Record<string, unknown>
    context_text?: string
    max_iterations?: number
  }) => jsonRequest<Envelope<AgentChatData>>(`${API_V1}/agent/chat`, body),
  sessions: (limit = 50) =>
    request<Envelope<SessionListData>>(`${API_V1}/agent/sessions${qs({ limit })}`),
  session: (sessionId: string) =>
    request<Envelope<SessionDetailData>>(`${API_V1}/agent/sessions/${sessionId}`),
  deleteSession: (sessionId: string) =>
    request<Envelope<{ session_id: string }>>(`${API_V1}/agent/sessions/${sessionId}`, {
      method: 'DELETE',
    }),
}
