/**
 * HTTP 客户端
 *
 * 默认走同源相对路径 `/api/...`：
 * - 开发期由 Vite proxy 转发到 localhost:8000（见 vite.config.ts）
 * - 生产构建产物由 FastAPI 托管时同样同源
 * 如需直连其它地址，设置 VITE_API_BASE_URL。
 */
const RAW_BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? ''
export const API_BASE = RAW_BASE.replace(/\/$/, '')
export const API_V1 = `${API_BASE}/api/v1`
export const API_V2 = `${API_BASE}/api/v2`

export class ApiError extends Error {
  status: number
  code?: string

  constructor(message: string, status: number, code?: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
  }
}

async function readBody(res: Response): Promise<unknown> {
  const text = await res.text()
  if (!text) return null
  try {
    return JSON.parse(text)
  } catch {
    return null
  }
}

/** 从 FastAPI 的两种错误格式里取出可读信息 */
function extractDetail(body: unknown, fallback: string): { message: string; code?: string } {
  const anyBody = body as Record<string, any> | null
  const detail = anyBody?.detail
  if (typeof detail === 'string') return { message: detail, code: anyBody?.error?.code }

  // FastAPI 校验错误：detail 是数组
  if (Array.isArray(detail)) {
    const first = detail[0]
    const field = Array.isArray(first?.loc) ? first.loc.slice(1).join('.') : ''
    return {
      message: field ? `${field}: ${first?.msg ?? '参数不合法'}` : String(first?.msg ?? '参数不合法'),
    }
  }

  const errorMessage = anyBody?.error?.message
  if (typeof errorMessage === 'string') return { message: errorMessage, code: anyBody?.error?.code }

  return { message: fallback }
}

export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let res: Response
  try {
    res = await fetch(path, init)
  } catch {
    throw new ApiError('无法连接后端服务，请确认已启动 uvicorn（默认 8000 端口）', 0)
  }

  const body = await readBody(res)

  if (!res.ok) {
    const { message, code } = extractDetail(body, res.statusText || `HTTP ${res.status}`)
    throw new ApiError(message, res.status, code)
  }

  return body as T
}

export function jsonRequest<T>(path: string, payload: unknown, method = 'POST'): Promise<T> {
  return request<T>(path, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

/** 主 Agent 流式对话的 WebSocket 地址 */
export function agentSocketUrl(): string {
  return socketUrl('/api/v1/agent/chat/ws')
}

/** 导入进度事件流的 WebSocket 地址 */
export function ingestSocketUrl(taskId: string): string {
  return socketUrl(`/api/v1/ingest/ws/${taskId}`)
}

function socketUrl(path: string): string {
  if (API_BASE) {
    return `${API_BASE.replace(/^http/, 'ws')}${path}`
  }
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${proto}//${window.location.host}${path}`
}
