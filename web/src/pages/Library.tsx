/** 文档库：上传（带实时进度）、筛选、删除 */
import { useCallback, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/endpoints'
import { PageHeader } from '../components/Layout'
import { ImportRow } from '../components/ImportProgress'
import { Button, Card, CardHeader, EmptyState, ErrorState, Input, Loading } from '../components/ui'

const PAGE_SIZE = 20
const MAX_IMPORT_ROWS = 5

interface ImportEntry {
  taskId: string
  filename: string
}

export default function Library() {
  const queryClient = useQueryClient()
  const [page, setPage] = useState(1)
  const [keyword, setKeyword] = useState('')
  const [search, setSearch] = useState('')
  const [notice, setNotice] = useState<string | null>(null)
  const [imports, setImports] = useState<ImportEntry[]>([])
  const fileRef = useRef<HTMLInputElement>(null)

  const list = useQuery({
    queryKey: ['documents', page, search],
    queryFn: () => api.documents({ page, page_size: PAGE_SIZE, search }),
  })

  const upload = useMutation({
    mutationFn: (file: File) => api.upload(file),
    onSuccess: (res) => {
      const { task_id, filename } = res.data
      setNotice(null)
      setImports((prev) =>
        [{ taskId: task_id, filename }, ...prev.filter((item) => item.taskId !== task_id)].slice(
          0,
          MAX_IMPORT_ROWS,
        ),
      )
    },
    onError: (error: unknown) => {
      setNotice(error instanceof Error ? error.message : '上传失败')
    },
  })

  const remove = useMutation({
    mutationFn: (docId: string) => api.deleteDocument(docId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['documents'] })
      queryClient.invalidateQueries({ queryKey: ['stats'] })
    },
  })

  // 导入结束（成功 / 失败 / 跳过）都刷新列表
  const handleImportFinished = useCallback(
    (status: string) => {
      queryClient.invalidateQueries({ queryKey: ['documents'] })
      queryClient.invalidateQueries({ queryKey: ['stats'] })
      if (status === 'completed') setNotice('导入完成，列表已刷新')
    },
    [queryClient],
  )

  const dismissImport = useCallback((taskId: string) => {
    setImports((prev) => prev.filter((item) => item.taskId !== taskId))
  }, [])

  const data = list.data?.data
  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1

  return (
    <>
      <PageHeader
        title="文档库"
        description="上传后会依次完成解析、标签提取、父子分块与向量化。导入在后台执行，下面会实时显示进度与日志。"
        actions={
          <>
            <input
              ref={fileRef}
              type="file"
              accept="application/pdf"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0]
                if (file) upload.mutate(file)
                e.target.value = ''
              }}
            />
            <Button onClick={() => fileRef.current?.click()} disabled={upload.isPending}>
              {upload.isPending ? '上传中…' : '上传 PDF'}
            </Button>
          </>
        }
      />

      <div className="space-y-5 p-8">
        {imports.length > 0 && (
          <div className="space-y-2">
            <p className="text-xs font-medium text-ink-600">导入任务</p>
            {imports.map((item) => (
              <ImportRow
                key={item.taskId}
                taskId={item.taskId}
                filename={item.filename}
                onFinished={handleImportFinished}
                onDismiss={() => dismissImport(item.taskId)}
              />
            ))}
          </div>
        )}

        {notice && (
          <div className="rounded-lg border border-ink-200 bg-white px-4 py-2.5 text-xs text-ink-700">
            {notice}
          </div>
        )}

        <div className="flex items-center gap-3">
          <Input
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                setPage(1)
                setSearch(keyword.trim())
              }
            }}
            placeholder="按标题筛选…"
            className="max-w-sm"
          />
          <Button
            variant="subtle"
            onClick={() => {
              setPage(1)
              setSearch(keyword.trim())
            }}
          >
            筛选
          </Button>
          {search && (
            <Button
              variant="ghost"
              onClick={() => {
                setKeyword('')
                setSearch('')
                setPage(1)
              }}
            >
              清除
            </Button>
          )}
        </div>

        <Card>
          <CardHeader
            title={`共 ${data?.total ?? 0} 篇`}
            subtitle={data ? `第 ${data.page} / ${totalPages} 页` : undefined}
            actions={
              <div className="flex gap-1">
                <Button variant="ghost" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
                  上一页
                </Button>
                <Button
                  variant="ghost"
                  disabled={page >= totalPages}
                  onClick={() => setPage((p) => p + 1)}
                >
                  下一页
                </Button>
              </div>
            }
          />

          {list.isPending && <Loading />}
          {list.isError && <ErrorState error={list.error} onRetry={() => list.refetch()} />}

          {data && data.documents.length === 0 && (
            <EmptyState
              title="还没有论文"
              hint="点右上角「上传 PDF」加入第一篇，或把 PDF 放进 input/papers 后用 CLI 导入。"
            />
          )}

          {data && data.documents.length > 0 && (
            <table className="w-full text-sm">
              <thead className="bg-ink-50 text-left text-[11px] uppercase tracking-wide text-ink-500">
                <tr>
                  <th className="px-5 py-2 font-medium">标题</th>
                  <th className="px-3 py-2 font-medium">年份</th>
                  <th className="px-3 py-2 font-medium">页数</th>
                  <th className="px-3 py-2 font-medium">块数</th>
                  <th className="px-5 py-2" />
                </tr>
              </thead>
              <tbody className="divide-y divide-ink-100">
                {data.documents.map((doc) => (
                  <tr key={doc.id} className="hover:bg-ink-50/60">
                    <td className="max-w-md px-5 py-3">
                      <Link
                        to={`/library/${doc.id}`}
                        className="line-clamp-2 text-ink-900 hover:underline"
                      >
                        {doc.title}
                      </Link>
                    </td>
                    <td className="px-3 py-3 text-ink-500">{doc.year || '—'}</td>
                    <td className="px-3 py-3 text-ink-500">{doc.total_pages}</td>
                    <td className="px-3 py-3 text-ink-500">{doc.chunk_count}</td>
                    <td className="px-5 py-3 text-right">
                      <button
                        className="text-xs text-ink-400 hover:text-red-600"
                        onClick={() => {
                          if (window.confirm(`确认删除《${doc.title}》？`)) remove.mutate(doc.id)
                        }}
                      >
                        删除
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
      </div>
    </>
  )
}
