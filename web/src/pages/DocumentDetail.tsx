/** 文档详情：元信息 + 内容标签 + 论文分析 */
import type { ReactNode } from 'react'
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useMutation, useQuery } from '@tanstack/react-query'
import { api } from '../api/endpoints'
import { PageHeader } from '../components/Layout'
import { Badge, Button, Card, CardHeader, ErrorState, Loading } from '../components/ui'
import type { AnalysisResult, AnalysisType } from '../types'

const ANALYSIS_TYPES: { value: AnalysisType; label: string }[] = [
  { value: 'full', label: '完整分析' },
  { value: 'method', label: '仅研究方法' },
  { value: 'results', label: '仅关键发现' },
  { value: 'limitations', label: '仅局限性' },
]

const TAG_LABELS: Record<string, string> = {
  domain: '领域',
  topic: '主题',
  methodology: '方法论',
}

export default function DocumentDetail() {
  const { docId = '' } = useParams()
  const [analysisType, setAnalysisType] = useState<AnalysisType>('full')

  const doc = useQuery({ queryKey: ['document', docId], queryFn: () => api.document(docId) })
  const tags = useQuery({
    queryKey: ['tags', docId],
    queryFn: () => api.tags(docId),
    retry: 0,
  })

  const analyze = useMutation<AnalysisResult>({
    mutationFn: async () => (await api.analyze({ doc_id: docId, analysis_type: analysisType })).data.analysis,
  })

  const detail = doc.data?.data

  return (
    <>
      <PageHeader
        title={detail?.title ?? '文档详情'}
        description={
          detail
            ? [detail.year, detail.journal, detail.doi].filter(Boolean).join(' · ') || undefined
            : undefined
        }
        actions={
          <Link to="/library" className="text-xs text-ink-500 underline">
            返回文档库
          </Link>
        }
      />

      <div className="space-y-6 p-8">
        {doc.isPending && <Loading />}
        {doc.isError && <ErrorState error={doc.error} onRetry={() => doc.refetch()} />}

        {detail && (
          <>
            <div className="grid grid-cols-3 gap-4">
              <Info label="作者" value={detail.authors?.length ? detail.authors.join(', ') : '—'} />
              <Info label="页数 / 文本块" value={`${detail.total_pages} 页 · ${detail.chunks.length} 块`} />
              <Info label="文件" value={detail.file_path ?? '—'} mono />
            </div>

            <Card>
              <CardHeader title="内容标签" subtitle="domain / topic / methodology，来自 PDF 关键词与 LLM 抽取" />
              {tags.isPending && <Loading />}
              {tags.isError && (
                <p className="px-5 py-6 text-xs text-ink-500">该论文暂无标签数据（导入时标签提取可能被跳过）。</p>
              )}
              {tags.data && (
                <div className="space-y-4 p-5">
                  {Object.entries(tags.data.data.tags).map(([type, items]) => (
                    <div key={type}>
                      <p className="mb-2 text-xs font-medium text-ink-600">{TAG_LABELS[type] ?? type}</p>
                      <div className="flex flex-wrap gap-1.5">
                        {items.map((item, index) => (
                          <Badge key={`${item.value}-${index}`} tone={item.needs_review ? 'warn' : 'neutral'}>
                            {item.value}
                          </Badge>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </Card>

            <Card>
              <CardHeader
                title="论文分析"
                subtitle="结构化抽取研究方法 / 关键发现 / 局限性，长文自动分片并发处理"
                actions={
                  <div className="flex items-center gap-2">
                    <select
                      value={analysisType}
                      onChange={(e) => setAnalysisType(e.target.value as AnalysisType)}
                      className="rounded-lg border border-ink-200 px-2.5 py-1.5 text-xs"
                    >
                      {ANALYSIS_TYPES.map((item) => (
                        <option key={item.value} value={item.value}>
                          {item.label}
                        </option>
                      ))}
                    </select>
                    <Button onClick={() => analyze.mutate()} disabled={analyze.isPending}>
                      {analyze.isPending ? '分析中…' : '开始分析'}
                    </Button>
                  </div>
                }
              />

              {analyze.isPending && <p className="px-5 py-4 text-xs text-ink-500">正在分片分析，整篇论文通常需要 1–3 分钟…</p>}
              {analyze.isError && <ErrorState error={analyze.error} />}

              {analyze.data && (
                <div className="space-y-5 p-5">
                  <Section title="研究方法" pages={analyze.data.research_method.evidence_pages}>
                    <p className="text-sm leading-relaxed text-ink-700">
                      {analyze.data.research_method.text || '文中未明确说明'}
                    </p>
                  </Section>

                  <Section title={`关键发现（${analyze.data.key_findings.length}）`}>
                    <ul className="space-y-2">
                      {analyze.data.key_findings.map((item, index) => (
                        <li key={index} className="text-sm leading-relaxed text-ink-700">
                          <span className="mr-1.5 text-ink-400">{index + 1}.</span>
                          {item.text}
                          <PageTags pages={item.evidence_pages} />
                        </li>
                      ))}
                      {!analyze.data.key_findings.length && <li className="text-sm text-ink-400">未提取到</li>}
                    </ul>
                  </Section>

                  <Section title={`局限性（${analyze.data.limitations.length}）`}>
                    <ul className="space-y-1.5">
                      {analyze.data.limitations.map((item, index) => (
                        <li key={index} className="text-sm leading-relaxed text-ink-700">
                          <span className="mr-1.5 text-ink-400">·</span>
                          {item}
                        </li>
                      ))}
                      {!analyze.data.limitations.length && <li className="text-sm text-ink-400">未提取到</li>}
                    </ul>
                  </Section>
                </div>
              )}
            </Card>

            <Card>
              <CardHeader title={`正文片段（${detail.chunks.length}）`} subtitle="导入时按页切分的原始段落" />
              <ul className="max-h-96 divide-y divide-ink-100 overflow-y-auto">
                {detail.chunks.slice(0, 80).map((chunk) => (
                  <li key={chunk.id} className="px-5 py-3">
                    <div className="mb-1 text-[11px] text-ink-400">
                      第 {chunk.page ?? '?'} 页 · {chunk.id}
                    </div>
                    <p className="line-clamp-4 text-xs leading-relaxed text-ink-600">{chunk.text}</p>
                  </li>
                ))}
              </ul>
              {detail.chunks.length > 80 && (
                <p className="border-t border-ink-100 px-5 py-2.5 text-[11px] text-ink-400">
                  仅显示前 80 条，共 {detail.chunks.length} 条
                </p>
              )}
            </Card>
          </>
        )}
      </div>
    </>
  )
}

function Info({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="rounded-xl border border-ink-200 bg-white px-4 py-3">
      <p className="text-[11px] text-ink-500">{label}</p>
      <p className={`mt-1 truncate text-xs ${mono ? 'font-mono text-[11px]' : ''} text-ink-800`} title={value}>
        {value}
      </p>
    </div>
  )
}

function Section({ title, pages, children }: { title: string; pages?: number[]; children: ReactNode }) {
  return (
    <div>
      <div className="mb-1.5 flex items-center gap-2">
        <h4 className="text-xs font-semibold text-ink-700">{title}</h4>
        {pages && <PageTags pages={pages} />}
      </div>
      {children}
    </div>
  )
}

function PageTags({ pages }: { pages: number[] }) {
  if (!pages?.length) return null
  return (
    <span className="ml-2 inline-flex gap-1 align-middle">
      {pages.map((page) => (
        <span key={page} className="rounded bg-ink-100 px-1.5 py-0.5 text-[10px] text-ink-500">
          p{page}
        </span>
      ))}
    </span>
  )
}
