/** 风格优化：润色 / 简化 / 学术化（纯改写，不查文献） */
import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { api } from '../api/endpoints'
import { PageHeader } from '../components/Layout'
import { Markdown } from '../components/Markdown'
import { Button, Card, CardHeader, ErrorState, Textarea } from '../components/ui'
import type { StyleData, StyleMode } from '../types'

const MODES: { value: StyleMode; label: string; hint: string }[] = [
  { value: 'polish', label: '润色', hint: '更正式的学术语言，保持原意' },
  { value: 'simplify', label: '简化', hint: '去除冗余，压缩到原文 70% 以内' },
  { value: 'academic', label: '学术化', hint: '去主观表述、规范术语与引用标注' },
]

export default function Style() {
  const [text, setText] = useState('')
  const [mode, setMode] = useState<StyleMode>('polish')

  const optimize = useMutation<StyleData, Error, void>({
    mutationFn: async () => (await api.style({ text, mode })).data,
  })

  return (
    <>
      <PageHeader
        title="风格优化"
        description="只做表达层面的改写，不引入新的事实或文献，因此不依赖论文库，速度也更快。"
      />

      <div className="grid gap-6 p-8 lg:grid-cols-2">
        <Card>
          <CardHeader
            title="原文"
            actions={
              <div className="flex gap-1">
                {MODES.map((item) => (
                  <button
                    key={item.value}
                    onClick={() => setMode(item.value)}
                    title={item.hint}
                    className={`rounded-lg px-2.5 py-1.5 text-xs font-medium transition ${
                      mode === item.value ? 'bg-ink-900 text-white' : 'text-ink-500 hover:bg-ink-100'
                    }`}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            }
          />
          <div className="space-y-3 p-5">
            <Textarea
              rows={18}
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="粘贴需要优化的段落…"
            />
            <div className="flex items-center justify-between">
              <span className="text-[11px] text-ink-400">
                {text.length} 字 · {MODES.find((m) => m.value === mode)?.hint}
              </span>
              <Button onClick={() => optimize.mutate()} disabled={!text.trim() || optimize.isPending}>
                {optimize.isPending ? '优化中…' : '开始优化'}
              </Button>
            </div>
          </div>
        </Card>

        <Card>
          <CardHeader title="优化结果" />
          <div className="p-5">
            {optimize.isPending && <p className="py-8 text-center text-xs text-ink-500">正在调用 LLM…</p>}
            {optimize.isError && <ErrorState error={optimize.error} onRetry={() => optimize.mutate()} />}
            {!optimize.data && !optimize.isPending && !optimize.isError && (
              <p className="py-8 text-center text-xs text-ink-400">左侧输入文本并选择模式后开始优化</p>
            )}
            {optimize.data && <Markdown>{optimize.data.optimized}</Markdown>}
          </div>
        </Card>
      </div>
    </>
  )
}
