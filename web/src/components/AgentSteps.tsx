/** 主 Agent 工具轨迹展示 */
import { useState } from 'react'
import type { AgentStep } from '../types'
import { Badge } from './ui'

const TOOL_LABELS: Record<string, string> = {
  rag_search: '检索文献',
  draft_expand: '按思路扩写',
  style_polish: '风格润色',
  self_critique: '自评',
}

export function AgentSteps({ steps, running }: { steps: AgentStep[]; running: boolean }) {
  const [expanded, setExpanded] = useState<number | null>(null)

  if (!steps.length) return null

  return (
    <div className="rounded-lg border border-ink-200 bg-ink-50/60 p-3">
      <div className="mb-2 flex items-center gap-2">
        <span className="text-xs font-medium text-ink-600">工具轨迹</span>
        <span className="text-[11px] text-ink-400">共 {steps.length} 次调用</span>
        {running && <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-indigo-500" />}
      </div>

      <ol className="space-y-1.5">
        {steps.map((step, index) => {
          const isOpen = expanded === index
          const label = TOOL_LABELS[step.tool] ?? step.tool
          return (
            <li key={`${step.iteration}-${step.tool}-${index}`} className="rounded-md bg-white px-2.5 py-2">
              <button
                type="button"
                onClick={() => setExpanded(isOpen ? null : index)}
                className="flex w-full items-center gap-2 text-left"
              >
                <span className="text-[11px] tabular-nums text-ink-400">#{step.iteration}</span>
                <Badge tone="accent">{label}</Badge>
                <span className="min-w-0 flex-1 truncate text-[11px] text-ink-500">
                  {describeArguments(step.arguments)}
                </span>
                <span className="text-[11px] text-ink-400">{isOpen ? '收起' : '详情'}</span>
              </button>

              {isOpen && (
                <div className="mt-2 space-y-2 border-t border-ink-100 pt-2">
                  <div>
                    <p className="text-[11px] font-medium text-ink-500">参数</p>
                    <pre className="mt-1 max-h-40 overflow-auto rounded bg-ink-100 p-2 text-[11px] leading-relaxed text-ink-700">
                      {JSON.stringify(step.arguments, null, 2)}
                    </pre>
                  </div>
                  <div>
                    <p className="text-[11px] font-medium text-ink-500">返回</p>
                    <pre className="mt-1 max-h-52 overflow-auto rounded bg-ink-100 p-2 text-[11px] leading-relaxed text-ink-700">
                      {step.output ? truncate(step.output, 4000) : '（执行中…）'}
                    </pre>
                  </div>
                </div>
              )}
            </li>
          )
        })}
      </ol>
    </div>
  )
}

function describeArguments(args: Record<string, unknown>): string {
  const query = args.query
  if (typeof query === 'string') return query
  const section = args.section_title
  if (typeof section === 'string') return section
  const text = args.text
  if (typeof text === 'string') return text.slice(0, 40)
  const content = args.content
  if (typeof content === 'string') return content.slice(0, 40)
  const keys = Object.keys(args)
  return keys.length ? keys.join(', ') : '无参数'
}

function truncate(text: string, max: number): string {
  return text.length > max ? `${text.slice(0, max)}\n…（已截断）` : text
}
