/**
 * 主 Agent 流式对话 hook
 *
 * 后端事件协议（见 api/routes/agent.py）：
 *   tool_call / tool_result / token / done / error
 *
 * 每次 send 建立一条 WebSocket，收到 done 或 error 后关闭。
 * 之所以不用长连接：会话续接由 session_id 承载，短连接更简单也更稳。
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { agentSocketUrl } from '../api/client'
import type { AgentSocketEvent, AgentStep } from '../types'

export interface SendPayload {
  message: string
  session_id?: string | null
  context?: Record<string, unknown>
  max_iterations?: number
}

interface SendOptions {
  onDone?: (sessionId: string) => void
}

const initialState = {
  running: false,
  text: '',
  steps: [] as AgentStep[],
  error: null as string | null,
  sessionId: null as string | null,
  stoppedReason: null as string | null,
  iterations: null as number | null,
  durationMs: null as number | null,
}

export function useAgentSocket() {
  const [state, setState] = useState(initialState)
  const socketRef = useRef<WebSocket | null>(null)
  const doneCallbackRef = useRef<((sessionId: string) => void) | undefined>(undefined)

  useEffect(() => {
    return () => {
      socketRef.current?.close()
    }
  }, [])

  const reset = useCallback(() => setState(initialState), [])

  const cancel = useCallback(() => {
    socketRef.current?.close()
    setState((prev) => ({ ...prev, running: false, stoppedReason: 'cancelled' }))
  }, [])

  const send = useCallback((payload: SendPayload, options: SendOptions = {}) => {
    doneCallbackRef.current = options.onDone
    socketRef.current?.close()
    setState({ ...initialState, running: true })

    let ws: WebSocket
    try {
      ws = new WebSocket(agentSocketUrl())
    } catch {
      setState((prev) => ({ ...prev, running: false, error: '无法建立 WebSocket 连接' }))
      return
    }
    socketRef.current = ws

    ws.onopen = () => ws.send(JSON.stringify(payload))

    ws.onmessage = (event) => {
      let parsed: AgentSocketEvent
      try {
        parsed = JSON.parse(event.data) as AgentSocketEvent
      } catch {
        return
      }

      if (parsed.type === 'tool_call') {
        setState((prev) => ({
          ...prev,
          steps: [
            ...prev.steps,
            {
              iteration: parsed.iteration,
              tool: parsed.tool,
              arguments: parsed.arguments,
              output: '',
            },
          ],
        }))
        return
      }

      if (parsed.type === 'tool_result') {
        setState((prev) => {
          const steps = [...prev.steps]
          for (let i = steps.length - 1; i >= 0; i -= 1) {
            if (steps[i].tool === parsed.tool && !steps[i].output) {
              steps[i] = { ...steps[i], output: parsed.output }
              break
            }
          }
          return { ...prev, steps }
        })
        return
      }

      if (parsed.type === 'token') {
        setState((prev) => ({ ...prev, text: prev.text + parsed.content }))
        return
      }

      if (parsed.type === 'done') {
        setState((prev) => ({
          ...prev,
          running: false,
          text: parsed.content || prev.text,
          sessionId: parsed.session_id,
          steps: parsed.steps?.length ? parsed.steps : prev.steps,
          iterations: parsed.iterations,
          stoppedReason: parsed.stopped_reason,
          durationMs: parsed.duration_ms,
        }))
        doneCallbackRef.current?.(parsed.session_id)
        ws.close()
        return
      }

      if (parsed.type === 'error') {
        setState((prev) => ({ ...prev, running: false, error: parsed.message }))
        ws.close()
      }
    }

    ws.onerror = () => {
      setState((prev) =>
        prev.error
          ? prev
          : { ...prev, running: false, error: 'WebSocket 连接失败，请确认后端已启动' },
      )
    }

    ws.onclose = () => {
      setState((prev) => (prev.running ? { ...prev, running: false } : prev))
    }
  }, [])

  return { ...state, send, cancel, reset }
}
