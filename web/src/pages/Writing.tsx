/**
 * 写作助手（核心页）
 *
 * 左：写作会话列表（落库在 SQLite，凭 session_id 续写）
 * 中：对话区 + 主 Agent 工具轨迹（WebSocket 流式）
 * 右：写作上下文（框架 / 思路 / 要求），随消息一并落库
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/endpoints'
import { AgentSteps } from '../components/AgentSteps'
import { Markdown } from '../components/Markdown'
import { Badge, Button, ErrorState, Field, Loading, Textarea } from '../components/ui'
import { useAgentSocket } from '../hooks/useAgentSocket'
import type { ChatMessage, WritingContextPayload } from '../types'

const EMPTY_CONTEXT: WritingContextPayload = {
  topic: '',
  framework: '',
  ideas: '',
  requirements: '',
  sections: [],
}

const TOOL_LABELS: Record<string, string> = {
  rag_search: '检索文献',
  draft_expand: '按思路扩写',
  style_polish: '风格润色',
  self_critique: '自评',
}

export default function Writing() {
  const location = useLocation()
  const queryClient = useQueryClient()
  const socket = useAgentSocket()

  const [selected, setSelected] = useState<string | null>(
    (location.state as { sessionId?: string } | null)?.sessionId ?? null,
  )
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [context, setContext] = useState<WritingContextPayload>(EMPTY_CONTEXT)
  const [input, setInput] = useState('')
  const scrollRef = useRef<HTMLDivElement>(null)

  const sessions = useQuery({ queryKey: ['sessions', 100], queryFn: () => api.sessions(100) })
  const detail = useQuery({
    queryKey: ['session', selected],
    queryFn: () => api.session(selected as string),
    enabled: Boolean(selected),
  })

  // 服务端是权威来源：切换会话或提交后刷新，都以服务端消息为准
  useEffect(() => {
    const data = detail.data?.data
    if (!data) return
    setMessages(data.messages)
    setContext({
      ...EMPTY_CONTEXT,
      ...data.context,
      sections: data.context.sections ?? [],
    })
  }, [detail.data])

  useEffect(() => {
    const node = scrollRef.current
    if (node) node.scrollTop = node.scrollHeight
  }, [messages, socket.text, socket.steps.length])

  const lastAssistant = useMemo(
    () => [...messages].reverse().find((item) => item.role === 'assistant')?.content,
    [messages],
  )
  // 流式过程与「提交后详情刷新完成前」都展示实时正文，避免闪烁
  const showLiveText = socket.text.length > 0 && socket.text !== lastAssistant

  const handleSelect = (sessionId: string) => {
    socket.reset()
    setSelected(sessionId)
  }

  const handleNew = () => {
    socket.reset()
    setSelected(null)
    setMessages([])
    setContext(EMPTY_CONTEXT)
  }

  const handleSend = () => {
    const text = input.trim()
    if (!text || socket.running) return
    setInput('')
    setMessages((prev) => [...prev, { role: 'user', content: text }])

    socket.send(
      {
        message: text,
        session_id: selected,
        context: {
          topic: context.topic,
          framework: context.framework,
          ideas: context.ideas,
          requirements: context.requirements,
          sections: context.sections,
        },
      },
      {
        onDone: (sessionId) => {
          setSelected(sessionId)
          queryClient.invalidateQueries({ queryKey: ['sessions'] })
          queryClient.invalidateQueries({ queryKey: ['session', sessionId] })
        },
      },
    )
  }

  const handleDelete = async (sessionId: string) => {
    if (!window.confirm('确认删除该会话及其全部消息？')) return
    await api.deleteSession(sessionId)
    if (selected === sessionId) handleNew()
    queryClient.invalidateQueries({ queryKey: ['sessions'] })
  }

  return (
    <div className="flex h-full">
      {/* 会话列表 */}
      <aside className="flex w-60 shrink-0 flex-col border-r border-ink-200 bg-white">
        <div className="flex items-center justify-between border-b border-ink-100 px-4 py-3.5">
          <span className="text-xs font-semibold text-ink-700">写作会话</span>
          <button onClick={handleNew} className="text-xs font-medium text-ink-600 hover:underline">
            + 新建
          </button>
        </div>

        <div className="flex-1 overflow-y-auto">
          {sessions.isPending && <Loading text="加载会话…" />}
          {sessions.isError && <ErrorState error={sessions.error} onRetry={() => sessions.refetch()} />}
          {sessions.data?.data.sessions.length === 0 && (
            <p className="px-4 py-6 text-xs leading-relaxed text-ink-400">
              还没有会话。在右侧填写框架与思路，直接发消息即可自动创建。
            </p>
          )}
          <ul className="divide-y divide-ink-100">
            {sessions.data?.data.sessions.map((session) => (
              <li
                key={session.id}
                className={`group flex items-start gap-2 px-4 py-3 ${
                  selected === session.id ? 'bg-ink-100' : 'hover:bg-ink-50'
                }`}
              >
                <button onClick={() => handleSelect(session.id)} className="min-w-0 flex-1 text-left">
                  <p className="truncate text-xs font-medium text-ink-800">
                    {session.title || '（未命名会话）'}
                  </p>
                  <p className="mt-0.5 text-[10px] text-ink-400">{session.message_count} 条消息</p>
                </button>
                <button
                  onClick={() => handleDelete(session.id)}
                  className="shrink-0 text-[10px] text-ink-300 opacity-0 transition group-hover:opacity-100 hover:text-red-600"
                >
                  删除
                </button>
              </li>
            ))}
          </ul>
        </div>
      </aside>

      {/* 对话区 */}
      <section className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between gap-4 border-b border-ink-200 bg-white px-6 py-3.5">
          <div className="min-w-0">
            <h1 className="truncate text-sm font-semibold text-ink-900">
              {selected
                ? sessions.data?.data.sessions.find((item) => item.id === selected)?.title ||
                  '写作会话'
                : '新建写作会话'}
            </h1>
            <p className="mt-0.5 text-[11px] text-ink-500">
              {selected ? `session_id: ${selected}` : '发送第一条消息后自动创建并落库'}
            </p>
          </div>
          {socket.stoppedReason && (
            <div className="flex shrink-0 items-center gap-2">
              <Badge tone={socket.stoppedReason === 'completed' ? 'accent' : 'warn'}>
                {socket.stoppedReason === 'completed'
                  ? '已收敛'
                  : socket.stoppedReason === 'max_iterations'
                    ? '达到迭代上限'
                    : socket.stoppedReason}
              </Badge>
              {socket.iterations != null && (
                <span className="text-[11px] text-ink-400">{socket.iterations} 轮迭代</span>
              )}
              {socket.durationMs != null && (
                <span className="text-[11px] text-ink-400">{(socket.durationMs / 1000).toFixed(1)}s</span>
              )}
            </div>
          )}
        </header>

        <div ref={scrollRef} className="flex-1 space-y-4 overflow-y-auto px-6 py-5">
          {detail.isPending && selected && <Loading text="加载会话…" />}
          {detail.isError && <ErrorState error={detail.error} onRetry={() => detail.refetch()} />}

          {!selected && messages.length === 0 && !socket.running && (
            <div className="mx-auto max-w-lg rounded-xl border border-dashed border-ink-300 px-6 py-8 text-center">
              <p className="text-sm font-medium text-ink-700">描述你想写什么</p>
              <p className="mt-1.5 text-xs leading-relaxed text-ink-500">
                右侧先填好论文框架与你的思路，Agent 会自主决定是否检索文献、按你的思路扩写，
                并在生成后自评；不达标会自动重写。
              </p>
            </div>
          )}

          {messages.map((message, index) => (
            <MessageBubble key={`${message.role}-${index}`} message={message} />
          ))}

          {(socket.running || socket.steps.length > 0) && (
            <AgentSteps steps={socket.steps} running={socket.running} />
          )}

          {showLiveText && <MessageBubble message={{ role: 'assistant', content: socket.text }} live />}

          {socket.error && (
            <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-xs text-red-700">
              {socket.error}
            </div>
          )}
        </div>

        <footer className="border-t border-ink-200 bg-white px-6 py-4">
          <div className="flex items-end gap-3">
            <Textarea
              rows={3}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  handleSend()
                }
              }}
              placeholder="例如：请按我的思路扩写《相关工作》，重点对比已有方法的两点不足。（Enter 发送，Shift+Enter 换行）"
            />
            <div className="flex shrink-0 flex-col gap-2">
              <Button onClick={handleSend} disabled={!input.trim() || socket.running}>
                {socket.running ? '生成中…' : '发送'}
              </Button>
              {socket.running && (
                <Button variant="ghost" onClick={socket.cancel}>
                  取消
                </Button>
              )}
            </div>
          </div>
          {socket.steps.length > 0 && !socket.running && (
            <p className="mt-2 text-[11px] text-ink-400">
              本轮工具：{socket.steps.map((step) => TOOL_LABELS[step.tool] ?? step.tool).join(' → ')}
            </p>
          )}
        </footer>
      </section>

      {/* 写作上下文 */}
      <aside className="w-80 shrink-0 space-y-4 overflow-y-auto border-l border-ink-200 bg-white p-5">
        <div>
          <h2 className="text-xs font-semibold text-ink-700">写作上下文</h2>
          <p className="mt-1 text-[11px] leading-relaxed text-ink-500">
            随消息一并保存到会话。填得越具体，扩写越不跑偏；下次继续写时无需重新填写。
          </p>
        </div>

        <Field label="论文主题">
          <Textarea
            rows={2}
            value={context.topic}
            onChange={(e) => setContext({ ...context, topic: e.target.value })}
            placeholder="例如：AI 赋能个性化学习"
          />
        </Field>

        <Field label="整体框架" hint="章节结构，越清楚越好">
          <Textarea
            rows={4}
            value={context.framework}
            onChange={(e) => setContext({ ...context, framework: e.target.value })}
            placeholder={'1 引言\n2 相关工作\n3 方法\n4 实验\n5 结论'}
          />
        </Field>

        <Field label="我的思路" hint="本节想表达什么、强调什么，Agent 会严格遵循">
          <Textarea
            rows={5}
            value={context.ideas}
            onChange={(e) => setContext({ ...context, ideas: e.target.value })}
            placeholder="例如：引言要突出个性化学习的两个痛点，并说明本文的两点贡献"
          />
        </Field>

        <Field label="写作要求" hint="字数、要点清单、风格约束等">
          <Textarea
            rows={3}
            value={context.requirements}
            onChange={(e) => setContext({ ...context, requirements: e.target.value })}
            placeholder="例如：400 字左右，必须包含对已有工作的批评性分析"
          />
        </Field>

        {context.sections.length > 0 && (
          <div>
            <p className="mb-1.5 text-xs font-medium text-ink-600">
              已完成章节（{context.sections.length}）
            </p>
            <ul className="space-y-1">
              {context.sections.map((section, index) => (
                <li key={`${section.title}-${index}`} className="truncate text-[11px] text-ink-500">
                  · {section.title}
                </li>
              ))}
            </ul>
          </div>
        )}
      </aside>
    </div>
  )
}

function MessageBubble({
  message,
  live,
}: {
  message: ChatMessage
  live?: boolean
}) {
  if (message.role === 'user') {
    return (
      <div className="flex justify-end">
        <div className="max-w-2xl rounded-xl rounded-br-sm bg-ink-900 px-4 py-2.5 text-sm leading-relaxed text-white">
          {message.content}
        </div>
      </div>
    )
  }

  return (
    <div className="flex justify-start">
      <div className="max-w-3xl rounded-xl rounded-bl-sm border border-ink-200 bg-white px-4 py-3">
        {live && <span className="mb-1 block text-[10px] text-ink-400">生成中…</span>}
        <Markdown>{message.content}</Markdown>
      </div>
    </div>
  )
}
