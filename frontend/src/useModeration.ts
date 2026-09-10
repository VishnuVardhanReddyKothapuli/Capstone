import { useCallback, useState } from 'react'

import { ApiError, api } from './api/client'
import type { CheckResult, CheckType } from './types'

export type ModerationStatus = 'idle' | 'busy' | 'done' | 'error'

export interface Moderation {
  status: ModerationStatus
  result: CheckResult | null
  error: string | null
  /** The file currently being checked, kept so the busy state can name it. */
  pending: { name: string; mode: CheckType } | null
  run: (file: File, mode: CheckType) => Promise<void>
  reset: () => void
}

/**
 * Upload-and-check state, shared by the home cards and the single-mode views so
 * the dropzone logic exists in exactly one place.
 */
export function useModeration(): Moderation {
  const [status, setStatus] = useState<ModerationStatus>('idle')
  const [result, setResult] = useState<CheckResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState<{ name: string; mode: CheckType } | null>(null)

  const run = useCallback(async (file: File, mode: CheckType) => {
    setStatus('busy')
    setError(null)
    setResult(null)
    setPending({ name: file.name, mode })
    try {
      const res = await api.moderate(file, mode)
      setResult(res)
      setStatus('done')
      if (!res.explanation) {
        api.explain(res.check_id).then((updated) => {
          setResult(updated)
        }).catch(() => {})
      }
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : 'Could not reach the API. Is the backend running?',
      )
      setStatus('error')
    }
  }, [])

  const reset = useCallback(() => {
    setStatus('idle')
    setResult(null)
    setError(null)
    setPending(null)
  }, [])

  return { status, result, error, pending, run, reset }
}
