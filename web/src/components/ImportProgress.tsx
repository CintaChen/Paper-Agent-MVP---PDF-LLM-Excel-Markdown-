/**
 * 导入进度：进度条 + 流式文字日志
 *
 * 上传成功后后端返回 task_id，这里订阅
 * WS /api/v1/ingest/ws/{task_id} 消费进度事件。
 */
import { useEffect, useRef, useState } from 'react'
import { ingestSocketUrl } from '../api/client'
import type { IngestEventItem } from '../types'

const STAGE_LABELS: Record<string, string> = {
  pending: '待开始',
  queued: '排队中',
  reading: '解析 PDF',
  tagging: '提取标签',
  chunking: '分块',
  embedding: '向量化',
  storing: '写入索引',
  completed: '已完成',
  failed: '失败',
  skipped: '已跳过',
}

export interface ImportRowProps {
  taskId: string
  filename: string
  onFinished: (status: string) => void
  onDismiss: () => void
}

export function ImportRow({ taskId, filename, onFinished, onDismiss }: ImportRowProps) {
  const [events, setEvents] = useState<IngestEventItem[]>([])
  const [percent, setPercent] = useState(0)
  const [stage, setStage] = useState('pending')
  const [status, setStatus] = useState('running')
  const [error, setError] = useState<string | null>(null)
  const [title, setTitle] = useState<string | null>(null)
  const [showLog, setShowLog] = useState(true)
  const [connected, setConnected] = useState(false)

  const logRef = useRef<HTMLDivElement>(null)
  const finishedRef = useRef(false)

  useEffect(() => {
    const ws = new WebSocket(ingestSocketUrl(taskId))

    ws.onopen = () => setConnected(true)

    ws.onmessage = (event) => {
      let payload: Record<string, any>
      try {
        payload = JSON.parse(event.data)
      } catch {
        return
      }

      if (payload.type === 'progress') {
        setEvents((prev) => [...prev, payload as IngestEventItem])
        setPercent(payload.percent ?? 0)
        setStage(payload.stage ?? '')
        return
      }

      if (payload.type === 'done') {
        setStatus(payload.status ?? 'completed')
        setPercent(payload.percent ?? 100)
        setStage(payload.stage ?? 'completed')
        setError(payload.error ?? null)
        setTitle(typeof payload.result?.title === 'string' ? payload.result.title : null)
        if (!finishedRef.current) {
          finishedRef.current = true
          onFinished(payload.status ?? 'completed')
        }
        ws.close()
      }
    }

    ws.onerror = () => setError('进度连接失败，可刷新页面查看结果')
    ws.onclose = () => setConnected(false)

    return () => ws.close()
  }, [taskId, onFinished])

  useEffect(() => {
    const node = logRef.current
    if (node) node.scrollTop = node.scrollHeight
  }, [events.length])

  const running = status === 'running'
  const tone = running
    ? 'text-ink-500'
    : status === 'failed'
      ? 'text-red-600'
      : status === 'skipped'
        ? 'text-amber-600'
        : 'text-emerald-600'
  const barTone =
    status === 'failed'
      ? 'bg-red-500'
      : status === 'completed'
        ? 'bg-emerald-500'
        : status === 'skipped'
          ? 'bg-amber-500'
          : 'bg-ink-900'

  return (
    <div className="rounded-lg border border-ink-200 bg-white px-4 py-3">
      <div className="flex items-center gap-3">
        <span className="min-w-0 flex-1 truncate text-xs font-medium text-ink-800">{filename}</span>
        {running && !connected && <span className="shrink-0 text-[10px] text-ink-400">连接中…</span>}
        <span className={`shrink-0 text-[11px] font-medium ${tone}`}>
          {STAGE_LABELS[stage] ?? stage} · {percent}%
        </span>
        {!running && (
          <button
            onClick={onDismiss}
            className="shrink-0 text-[11px] text-ink-400 hover:text-ink-700"
          >
            关闭
          </button>
        )}
      </div>

      <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-ink-100">
        <div
          className={`h-full rounded-full transition-all duration-300 ${barTone}`}
          style={{ width: `${percent}%` }}
        />
      </div>

      {error && <p className="mt-2 text-[11px] leading-relaxed text-red-600">{error}</p>}
      {!error && status === 'completed' && (
        <p className="mt-2 text-[11px] text-emerald-700">
          导入成功{title ? `：${title}` : ''}
        </p>
      )}

      {events.length > 0 && (
        <>
          <button
            onClick={() => setShowLog((value) => !value)}
            className="mt-2 text-[11px] text-ink-400 hover:text-ink-700"
          >
            {showLog ? '收起日志' : `查看日志（${events.length}）`}
          </button>

          {showLog && (
            <div
              ref={logRef}
              className="mt-1.5 max-h-32 overflow-y-auto rounded bg-ink-950 px-2.5 py-2 font-mono text-[11px] leading-relaxed text-ink-200"
            >
              {events.map((item) => (
                <div key={item.seq} className={item.level === 'error' ? 'text-red-300' : undefined}>
                  <span className="text-ink-500">{String(item.percent).padStart(3, ' ')}%</span>{' '}
                  {item.message}
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}
