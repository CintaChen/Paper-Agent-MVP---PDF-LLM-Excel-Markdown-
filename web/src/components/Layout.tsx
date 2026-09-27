/** 应用外壳：侧边导航 + 顶部状态栏 */
import type { ReactNode } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api/endpoints'

const NAV = [
  { to: '/', label: '仪表盘', end: true },
  { to: '/writing', label: '写作助手' },
  { to: '/search', label: '文献检索' },
  { to: '/library', label: '文档库' },
  { to: '/style', label: '风格优化' },
]

export function Layout() {
  const health = useQuery({ queryKey: ['health'], queryFn: api.health, refetchInterval: 30_000 })

  const online = health.isSuccess && health.data?.data?.status === 'ok'

  return (
    <div className="flex h-full">
      <aside className="flex w-56 shrink-0 flex-col border-r border-ink-200 bg-ink-950 text-ink-100">
        <div className="px-5 py-5">
          <p className="text-sm font-semibold tracking-tight text-white">scholarAgent</p>
          <p className="mt-0.5 text-[11px] text-ink-400">论文写作 Agent</p>
        </div>

        <nav className="flex-1 space-y-0.5 px-2">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                `block rounded-lg px-3 py-2 text-sm transition ${
                  isActive
                    ? 'bg-ink-800 font-medium text-white'
                    : 'text-ink-300 hover:bg-ink-900 hover:text-white'
                }`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="border-t border-ink-800 px-5 py-3.5">
          <div className="flex items-center gap-2">
            <span
              className={`h-1.5 w-1.5 rounded-full ${
                health.isLoading ? 'bg-ink-500' : online ? 'bg-emerald-400' : 'bg-red-400'
              }`}
            />
            <span className="text-[11px] text-ink-400">
              {health.isLoading ? '检测中…' : online ? `后端在线 · v${health.data?.data?.version ?? '?'}` : '后端未连接'}
            </span>
          </div>
        </div>
      </aside>

      <main className="min-w-0 flex-1 overflow-y-auto">
        <Outlet />
      </main>
    </div>
  )
}

export function PageHeader({ title, description, actions }: { title: string; description?: string; actions?: ReactNode }) {
  return (
    <header className="flex items-start justify-between gap-6 border-b border-ink-200 bg-white px-8 py-5">
      <div>
        <h1 className="text-lg font-semibold tracking-tight text-ink-900">{title}</h1>
        {description && <p className="mt-1 max-w-2xl text-xs leading-relaxed text-ink-500">{description}</p>}
      </div>
      {actions}
    </header>
  )
}
