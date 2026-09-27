/** 文献检索：混合检索 + 结果溯源 */
import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { api } from '../api/endpoints'
import { PageHeader } from '../components/Layout'
import { Badge, Button, Card, CardHeader, EmptyState, ErrorState, Field, Input, Toggle } from '../components/ui'
import type { SearchData } from '../types'

export default function Search() {
  const [query, setQuery] = useState('')
  const [topK, setTopK] = useState(10)
  const [useBm25, setUseBm25] = useState(true)
  const [useVector, setUseVector] = useState(true)
  const [useRerank, setUseRerank] = useState(true)

  const search = useMutation<SearchData>({
    mutationFn: async () =>
      (
        await api.search({
          query: query.trim(),
          top_k: topK,
          use_bm25: useBm25,
          use_vector: useVector,
          use_rerank: useRerank,
        })
      ).data,
  })

  const submit = () => {
    if (!query.trim() || search.isPending) return
    search.mutate()
  }

  return (
    <>
      <PageHeader
        title="文献检索"
        description="BM25 关键词 + 向量相似度 → RRF 融合 → 重排序。命中片段会带上来源文献与页码，便于核对原文。"
      />

      <div className="space-y-6 p-8">
        <Card>
          <div className="space-y-4 p-5">
            <Field label="检索词" hint="越具体越好：研究主题、方法名、专有术语">
              <div className="flex gap-3">
                <Input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && submit()}
                  placeholder="例如：retrieval augmented generation evaluation"
                />
                <Button onClick={submit} disabled={search.isPending || !query.trim()}>
                  {search.isPending ? '检索中…' : '检索'}
                </Button>
              </div>
            </Field>

            <div className="flex flex-wrap items-center gap-4">
              <div className="flex items-center gap-2">
                <span className="text-xs text-ink-500">召回通道</span>
                <Toggle checked={useBm25} onChange={setUseBm25} label="BM25" />
                <Toggle checked={useVector} onChange={setUseVector} label="向量" />
                <Toggle checked={useRerank} onChange={setUseRerank} label="重排序" />
              </div>
              <label className="flex items-center gap-2 text-xs text-ink-500">
                返回条数
                <input
                  type="number"
                  min={1}
                  max={50}
                  value={topK}
                  onChange={(e) => setTopK(Number(e.target.value) || 1)}
                  className="w-16 rounded-md border border-ink-200 px-2 py-1 text-xs"
                />
              </label>
            </div>
          </div>
        </Card>

        {search.isError && <ErrorState error={search.error} onRetry={submit} />}

        {search.data && (
          <Card>
            <CardHeader
              title={`命中 ${search.data.total_found} 条`}
              subtitle={`耗时 ${search.data.duration_ms} ms`}
            />
            {search.data.results.length ? (
              <ul className="divide-y divide-ink-100">
                {search.data.results.map((item) => (
                  <li key={item.chunk.id} className="px-5 py-4">
                    <div className="mb-2 flex flex-wrap items-center gap-2">
                      <Badge tone="accent">#{item.rank}</Badge>
                      <span className="text-xs font-medium text-ink-800">
                        {(item.chunk.metadata?.doc_title as string) || '未知文献'}
                      </span>
                      {item.chunk.page != null && (
                        <span className="text-[11px] text-ink-400">第 {item.chunk.page} 页</span>
                      )}
                      <span className="text-[11px] text-ink-400">score {item.score.toFixed(4)}</span>
                      <Badge>{item.source}</Badge>
                    </div>
                    <p className="text-sm leading-relaxed text-ink-700">{item.chunk.text}</p>
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyState
                title="没有命中任何片段"
                hint="确认论文已导入、Ollama 的 nomic-embed-text 可用；也可尝试关闭部分召回通道对比效果。"
              />
            )}
          </Card>
        )}

        {!search.data && !search.isPending && !search.isError && (
          <EmptyState title="输入检索词开始" hint="结果会标注来源文献与页码，方便你回到原文核对。" />
        )}
      </div>
    </>
  )
}
