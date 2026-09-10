import { useCallback, useEffect, useState } from 'react'

import { ApiError, api } from '../api/client'
import { ResultCard } from '../components/ResultCard'
import { MODE_LABEL } from '../format'
import type { CheckType, HistoryPage } from '../types'
import page from './Page.module.css'
import styles from './HistoryView.module.css'

const PAGE_SIZE = 12
const FILTERS: (CheckType | null)[] = [null, 'nsfw', 'similarity', 'both']

export function HistoryView() {
  const [filter, setFilter] = useState<CheckType | null>(null)
  const [offset, setOffset] = useState(0)
  const [data, setData] = useState<HistoryPage | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const load = useCallback(
    async (signal: { cancelled: boolean }) => {
      setLoading(true)
      setError(null)
      try {
        const next = await api.history({ checkType: filter, limit: PAGE_SIZE, offset })
        if (!signal.cancelled) setData(next)
      } catch (caught) {
        if (!signal.cancelled)
          setError(
            caught instanceof ApiError ? caught.message : 'Could not load history from the API.',
          )
      } finally {
        if (!signal.cancelled) setLoading(false)
      }
    },
    [filter, offset],
  )

  useEffect(() => {
    const signal = { cancelled: false }
    void load(signal)
    return () => {
      signal.cancelled = true
    }
  }, [load])

  const total = data?.total ?? 0
  const shownFrom = total === 0 ? 0 : offset + 1
  const shownTo = Math.min(offset + PAGE_SIZE, total)

  return (
    <div className={page.page}>
      <header className={page.header}>
        <span className={page.eyebrow}>Your account</span>
        <h1 className={page.title}>History</h1>
        <p className={page.subtitle}>
          Every check you have run, newest first. Only your own uploads appear here — the duplicate
          search looks across all accounts, but this list does not.
        </p>
      </header>

      <div className={styles.toolbar}>
        <div className={styles.filters} role="group" aria-label="Filter by check type">
          {FILTERS.map((value) => (
            <button
              key={value ?? 'all'}
              type="button"
              className={`${styles.chip} ${filter === value ? styles.chipActive : ''}`}
              aria-pressed={filter === value}
              onClick={() => {
                setFilter(value)
                setOffset(0)
              }}
            >
              {value === null ? 'All' : MODE_LABEL[value]}
            </button>
          ))}
        </div>
        <span className={styles.count}>
          {total === 0 ? 'No checks' : `${shownFrom}–${shownTo} of ${total}`}
        </span>
      </div>
      {error && (
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}

      {loading && !data && <p className={styles.muted}>Loading…</p>}

      {data && data.items.length === 0 && !error && (
        <p className={styles.muted}>
          Nothing here yet. Run a check from the home page and it will show up.
        </p>
      )}

      {data && data.items.length > 0 && (
        <>
          <div className={`${styles.list} ${loading ? styles.stale : ''}`}>
            {data.items.map((item) => (
              <ResultCard key={item.check_id} result={item} compact />
            ))}
          </div>

          <div className={styles.pager}>
            <button
              type="button"
              className={styles.pageButton}
              disabled={offset === 0 || loading}
              onClick={() => setOffset((current) => Math.max(0, current - PAGE_SIZE))}
            >
              ← Newer
            </button>
            <button
              type="button"
              className={styles.pageButton}
              disabled={shownTo >= total || loading}
              onClick={() => setOffset((current) => current + PAGE_SIZE)}
            >
              Older →
            </button>
          </div>
        </>
      )}
    </div>
  )
}
