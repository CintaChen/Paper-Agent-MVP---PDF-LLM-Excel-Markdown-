# 前端架构方案（scholarAgent Web UI）

> 面向 `docs/API_DESIGN.md` 的前端实现方案。目标：后端尚未实现的情况下，前端可以独立开发、独立验证，后端就绪后零改动切换。
>
> 版本：v0.1 ｜ 日期：2026-09-03

---

## 1. Skill 调研结论

在 SkillHub（lightmake.site）用 `frontend web app scaffold react vite`、`UI design system components styling`、`shadcn ui tailwind react components`、`frontend design landing page` 等多组关键词检索，**返回的都是同一批泛热门结果，相关性分数全部卡在 0.045–0.05**，不存在真正可用的「前端脚手架 / 前端架构」类 skill。结论：不依赖外部 skill 兜底，改由「通用工具 skill + 项目自建 skill」组合。

| Skill | 来源 | 用途 | 建议 |
|-------|------|------|------|
| `agent-browser` | 本机已装（codebuddy 插件）| 页面截图、点击、表单填写，用于 UI 冒烟验证 | **用起来**，第 4 阶段验收靠它 |
| `cloudstudio-deploy` | 内置 | 把 build 产物部署成可分享链接，给他人预览 | 需要演示时再用 |
| `dev-expert`（编程专家）| SkillHub 远程，68 万下载 | 通用编程专家，覆盖前端设计 / API 设计 / 技术选型 | **不装**。覆盖面太宽，会跟你的技术决策抢方向盘；真需要时单次搜索调用即可 |
| `scholaragent-frontend` | **建议自建** | 固化本项目 API 契约、目录约定、组件规范 | **强烈建议建**，理由见下 |

### 1.1 为什么建议自建一个项目 skill

前端开发的真实风险不是「不会写 React」，而是**多次会话之间的一致性漂移**：目录放哪、类型怎么来、错误怎么兜、loading 态长什么样，隔几天再让 agent 写就会换一套写法。

自建 skill 后，把下面这些固化进去，后续每次对话自动生效：

- API 契约来源：永远是 `openapi.yaml`，类型由 `openapi-typescript` 生成，禁止手写 interface
- 目录约定与文件命名
- 统一的错误处理链路（`ApiError` → toast）
- 统一的异步状态组件（`Loading` / `Empty` / `ErrorState`）
- 检索结果高亮、Markdown 渲染的固定写法

建法：`~/.workbuddy/skills/scholaragent-frontend/SKILL.md`，frontmatter 加 `agent_created: true`。

---

## 2. 技术选型

| 层 | 选型 | 理由 |
|----|------|------|
| 构建 | Vite + TypeScript | API 文档 9.1 节已按 `VITE_*` 约定写死，等于指定了 Vite |
| 框架 | React 19 | 生态最全，Markdown / 流式 / 表单组件都成熟 |
| 路由 | React Router v7 | 页面数少（6 个），不需要 Next.js 的 SSR |
| 数据请求 | TanStack Query v5 | 天然支持**取消、重试、缓存失效**，正好对应 API 文档 9.3 节的三条要求 |
| 全局状态 | Zustand v5 | 只放「文档列表缓存 + 当前会话 + API 地址」，其余全交给 Query |
| 样式 | Tailwind CSS v4 + shadcn/ui | 学术工具类界面组件密度高，shadcn 的 Dialog/Table/Tabs 直接可用 |
| Markdown | react-markdown + remark-gfm | `/agents/writing/outline` 返回 markdown 字符串 |
| Mock | MSW v2 | 拦截网络层，后端就绪后删掉 `worker.start()` 即可，业务代码零改动 |
| 类型生成 | openapi-typescript | 从契约生成类型，杜绝前后端字段漂移 |
| 测试 | Vitest + Testing Library | 至少覆盖 MSW handler 与关键 hook |

不引入的：Redux（过度设计）、Next.js（纯本地工具，无 SEO / SSR 需求）、GraphQL（后端是 REST）。

---

## 3. 核心策略：契约先行 + Mock 并行

后端 `api/` 目录在 README 里还标着「预留」，开发计划中「API 服务（FastAPI）」未打勾。所以顺序必须是：

```
手写 openapi.yaml  →  生成 TS 类型  →  MSW 起 Mock  →  前端全量开发  →  后端实现  →  切环境变量收工
```

**第一步不是建 React 项目，是把 `API_DESIGN.md` 翻译成 `openapi.yaml`。** 这件事做好了，后面前端所有代码都有类型保护；做不好，前后端联调时会陷入无止境的字段对齐。

产物位置建议：`web/openapi.yaml`，生成到 `web/src/api/schema.d.ts`。

---

## 4. 目录结构

```
web/
├── openapi.yaml              # 单一契约源（手写，与后端共同维护）
├── .env.development          # VITE_API_BASE_URL / VITE_WS_URL / VITE_USE_MOCK=true
├── src/
│   ├── main.tsx
│   ├── App.tsx               # 只放 Router + QueryClientProvider + 布局壳
│   ├── api/
│   │   ├── schema.d.ts       # 生成物，不要手改
│   │   ├── client.ts         # fetch 封装：baseURL / 超时 / ApiError 归一化
│   │   └── endpoints.ts      # 按资源分组的函数：ingest / documents / search / agents
│   ├── hooks/
│   │   ├── useDocuments.ts   # TanStack Query 封装
│   │   ├── useSearch.ts
│   │   ├── useAgents.ts      # outline / paragraph / style / analysis
│   │   └── useChatSocket.ts  # WebSocket：连接、断线重连、取消
│   ├── components/
│   │   ├── layout/           # AppShell、Sidebar、TopBar
│   │   ├── common/           # Loading、Empty、ErrorState、Highlight、MarkdownView
│   │   └── domain/           # DocumentCard、SearchResultItem、ChunkList、OutlineEditor
│   ├── pages/
│   │   ├── Dashboard.tsx     # /          health + stats
│   │   ├── Library.tsx       # /library   文档列表 / 上传 / 删除
│   │   ├── DocumentDetail.tsx# /library/:id
│   │   ├── Search.tsx        # /search
│   │   ├── Writing.tsx       # /writing   outline + paragraph
│   │   ├── Style.tsx         # /style
│   │   └── Analysis.tsx      # /analysis
│   ├── mocks/
│   │   ├── browser.ts        # MSW worker
│   │   ├── handlers/         # 按资源拆
│   │   └── fixtures/         # 假论文数据
│   └── store/
│       └── useAppStore.ts
└── package.json
```

---

## 5. 页面与 API 映射

| 路由 | 页面 | 主要 API | 优先级 |
|------|------|----------|--------|
| `/` | 仪表盘 | `GET /health`、`GET /documents/stats` | P0 |
| `/library` | 文档库 | `GET /documents`、`POST /ingest/upload`、`DELETE /documents/{id}` | P0 |
| `/library/:id` | 文档详情 | `GET /documents/{id}` | P1 |
| `/search` | 混合检索 | `POST /search`、`/search/vector`、`/search/keyword` | P0 |
| `/writing` | 写作助手 | `POST /agents/writing/outline`、`/agents/writing/paragraph` | P1 |
| `/style` | 风格优化 | `POST /agents/style/polish` | P1 |
| `/analysis` | 论文分析 | `POST /agents/analysis/analyze` | P2 |

P2 的 `WS /ws/chat` 流式输出建议**提前到 P1**——Agent 调用动辄 3 秒以上，同步等待的交互体验很差，而这个 hook 写一次就全场复用。

---

## 6. 六个关键设计决策

### 6.1 类型由契约生成，禁止手写

```json
{ "scripts": { "gen": "openapi-typescript ./openapi.yaml -o ./src/api/schema.d.ts" } }
```

后端字段一改，重跑 `npm run gen`，TypeScript 会直接告诉你哪些页面挂了。手写 interface 做不到这点。

### 6.2 错误解析必须兼容两套格式

API 文档 5.1 节定义了 `{status:"error", error:{code,message}}`，但 FastAPI 抛 `HTTPException` 时默认返回 `{"detail": "..."}`。**在 `client.ts` 里统一归一化成 `ApiError`**，否则每个页面都得写两遍分支。

```ts
class ApiError extends Error {
  constructor(public code: string, message: string, public status: number) { super(message) }
}
```

### 6.3 Agent 调用一律支持取消

`useAgents.ts` 里暴露 `mutate` 与 `cancel`；同步接口用 `AbortController`，流式走 WebSocket 时直接 `socket.close()`。对应文档 9.3 节「支持取消、重试」。

### 6.4 检索高亮自己做，注意转义

后端不返回高亮位置，前端按 query 分词匹配 `chunk.text`。**必须做 HTML 转义再替换**，否则论文摘要里的 `<` `>` 会变成 XSS 入口。抽成 `<Highlight text={} query={} />` 组件。

### 6.5 导入只用 upload，不用 directory

`POST /ingest/directory` 收的是**服务器本地路径**，浏览器端根本选不到服务器目录。前端唯一可用的是 `POST /ingest/upload`（multipart）。若要批量上传，循环调 upload 并做并发控制（建议 3），比等后端加批量接口更快见效。

### 6.6 环境变量切 Mock

```
VITE_USE_MOCK=true   # 主入口条件执行 worker.start()
```

后端就绪后改成 `false`，业务代码一行不动。

---

## 7. 需要跟后端对齐的 7 个缺口

按 `API_DESIGN.md` 现状，以下问题前端绕不过去，**建议在动手写页面前先跟后端（或你自己）敲定**：

| # | 问题 | 现状 | 建议 |
|---|------|------|------|
| 1 | **PDF 预览** | `file_path` 是服务器本地路径，浏览器访问不了 | 加 `GET /documents/{id}/file` 返回 PDF 流，或静态挂载 `/files/*` |
| 2 | **导入进度** | 6.1 节写「轮询或 WebSocket」，但只定义了 `WS /ws/chat` | 上传返回 `task_id`，加 `GET /tasks/{id}`；或复用 WS 增加 `type: "ingest_progress"` |
| 3 | **检索结果缺标题** | `chunk.metadata` 只有 `doc_id` 和 `source`，没有 `doc_title` | 后端在 metadata 补 `doc_title` / `year` / `journal`，否则每页 10 条结果要发 10 次额外请求 |
| 4 | **Agent 全同步** | outline 返回 `duration_ms: 3000`，同步等 3 秒+ | 统一走 WS，扩展 `ws/chat` 的 `type` 支持 `outline`/`paragraph`/`style`/`analysis` |
| 5 | **错误格式不统一** | 5.1 节的 `error.code` 与 FastAPI 默认 `detail` 并存 | 后端加统一 exception handler，或前端只认 `detail`（成本低但要确认） |
| 6 | **任务状态字段缺失** | 批量导入返回 `documents[].status`，但无整体任务态 | 明确是同步返回还是异步，前端据此决定要不要做进度条 |
| 7 | **CORS 与上传体积** | 只写了「允许所有来源」 | 确认 Nginx/uvicorn 层的 body 上限，PDF 单本 20MB 很常见 |

---

## 8. 执行步骤

### 阶段 0：地基（半天）

1. `npm create vite@latest web -- --template react-ts`
2. 把 `API_DESIGN.md` 翻译成 `openapi.yaml`（**这一步别偷懒，后面全靠它**）
3. `npm i -D openapi-typescript` 并配 `gen` 脚本，验证类型生成成功

### 阶段 1：Mock 打通（半天）

4. `npm i -D msw`，按资源写 handlers + fixtures
5. `main.tsx` 里按 `VITE_USE_MOCK` 条件启动 worker
6. 浏览器打开，确认 Network 面板能看到被拦截的请求

### 阶段 2：骨架与基础设施（1 天）

7. Tailwind + shadcn/ui 初始化
8. `AppShell` + `Sidebar` 布局，6 个路由先放占位页
9. `client.ts`（ApiError 归一化）+ `endpoints.ts`
10. `Loading` / `Empty` / `ErrorState` 三个通用态组件

### 阶段 3：P0 页面（1–2 天）

11. 仪表盘：`GET /health` + `GET /documents/stats`
12. 文档库：列表分页、搜索、删除、上传
13. 检索页：查询表单（top_k / bm25 / vector / rerank 开关）+ 结果列表 + 高亮

### 阶段 4：P1 页面与流式（1–2 天）

14. `useChatSocket.ts`：连接、断线重连、取消
15. 写作助手页、风格优化页，结果用 `MarkdownView` 渲染
16. 文档详情页 + PDF 预览（依赖第 7 节缺口 1）
17. 用 `agent-browser` skill 截图冒烟，逐页走一遍

### 阶段 5：自建 skill 与收尾（半天）

18. 把本文件的 2/4/6 节抽成 `scholaragent-frontend` skill
19. 后端就绪后 `VITE_USE_MOCK=false` 切真接口，跑通 P0 全链路
20. 补 P2 分析页

---

## 9. 一句话总结

**先写 `openapi.yaml`，别急着写 React。** 后端还是空的，契约和 Mock 才是让你能一直往前跑的两条腿。
