import { useEffect, useState } from 'react'

import { ApiError, api } from './api/client'
import type { ModelInfo } from './types'

/**
 * /api/models on mount. Used by the stack page and by the band legends, so the
 * thresholds shown in the UI always come from the running config.
 */
export function useModelInfo(): { info: ModelInfo | null; error: string | null } {
  const [info, setInfo] = useState<ModelInfo | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    api
      .models()
      .then((loaded) => {
        if (!cancelled) setInfo(loaded)
      })
      .catch((caught: unknown) => {
        if (cancelled) return
        setError(
          caught instanceof ApiError ? caught.message : 'Could not load the model configuration.',
        )
      })
    return () => {
      cancelled = true
    }
  }, [])

  return { info, error }
}
