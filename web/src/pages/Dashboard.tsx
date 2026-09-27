/** 仪表盘：论文库规模 + 写作会话概览 */
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api/endpoints'
import { PageHeader } from '../components/Layout'
import { Card, CardHeader, ErrorState, Loading, Stat } from '../components/ui'

export default function Dashboard() {
  const stats = useQuery({ queryKey: ['stats'], queryFn: api.stats })
  const sessions = useQuery({ queryKey: ['sessions', 5], queryFn: () => api.sessions(5) })

  const data = stats.data?.data

  return (
    <>
      <PageHeader
        title="仪表盘"
        description="论文库规模与最近的写作会话。左侧进入「写作助手」开始按你的框架扩写。"
      />

      <div className="space-y-6 p-8">
        {stats.isPending && <Loading />}
        {stats.isError && <ErrorState error={stats.error} onRetry={() => stats.refetch()} />}

        {data && (
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <Stat label="论文" value={data.total_documents} />
            <Stat label="文本块（chunks）" value={data.total_chunks} />
            <Stat label="总页数" value={data.total_pages} />
            <Stat label="写作会话" value={sessions.data?.data.total ?? '—'} />
          </div>
        )}

        <div className="grid gap-6 lg:grid-cols-2">
          <Card>
            <CardHeader
              title="最近写作会话"
              subtitle="凭 session_id 可随时续写"
              actions={
                <Link to="/writing" className="text-xs font-medium text-ink-600 underline">
                  去写作
                </Link>
              }
            />
            {sessions.isPending ? (
              <Loading />
            ) : sessions.data?.data.sessions.length ? (
              <ul className="divide-y divide-ink-100">
                {sessions.data.data.sessions.map((session) => (
                  <li key={session.id} className="flex items-center justify-between px-5 py-3">
                    <Link
                      to="/writing"
                      state={{ sessionId: session.id }}
                      className="min-w-0 flex-1 truncate text-sm text-ink-800 hover:underline"
                    >
                      {session.title || '（未命名会话）'}
                    </Link>
                    <span className="ml-3 shrink-0 text-[11px] text-ink-400">
                      {session.message_count} 条
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="px-5 py-8 text-center text-xs text-ink-500">还没有写作会话</p>
            )}
          </Card>

          <Card>
            <CardHeader title="常用入口" />
            <div className="grid grid-cols-2 gap-3 p-5">
              <QuickLink to="/search" title="文献检索" hint="混合检索：BM25 + 向量 + 重排" />
              <QuickLink to="/library" title="文档库" hint="上传 PDF、查看标签、论文分析" />
              <QuickLink to="/writing" title="写作助手" hint="按框架与思路扩写，自评重写" />
              <QuickLink to="/style" title="风格优化" hint="润色 / 简化 / 学术化，不查文献" />
            </div>
          </Card>
        </div>
      </div>
    </>
  )
}

function QuickLink({ to, title, hint }: { to: string; title: string; hint: string }) {
  return (
    <Link
      to={to}
      className="rounded-lg border border-ink-200 px-4 py-3 transition hover:border-ink-300 hover:bg-ink-50"
    >
      <p className="text-sm font-medium text-ink-900">{title}</p>
      <p className="mt-0.5 text-[11px] leading-relaxed text-ink-500">{hint}</p>
    </Link>
  )
}
