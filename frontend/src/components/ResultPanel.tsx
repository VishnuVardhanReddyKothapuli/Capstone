import { MODE_LABEL } from '../format'
import type { Moderation } from '../useModeration'
import { ResultCard } from './ResultCard'
import styles from './ResultPanel.module.css'

/**
 * Busy / error / verdict for one upload. Shared by Home and the single-mode
 * views so the three states look the same wherever a check is started.
 */
export function ResultPanel({ moderation }: { moderation: Moderation }) {
  const { status, result, pending, reset } = moderation

  if (status === 'idle') return null

  if (status === 'busy') {
    return (
      <div className={styles.panel}>
        <div className={styles.busy}>
          <span className={styles.spinner} aria-hidden="true" />
          <div>
            <p className={styles.busyTitle}>
              Running the {pending ? MODE_LABEL[pending.mode].toLowerCase() : ''} check…
            </p>
            <p className={styles.busyMeta}>
              {pending?.name}
              {' — the first run downloads the models, which can take a minute.'}
            </p>
          </div>
        </div>
      </div>
    )
  }

  if (status === 'error') {
    return (
      <div className={styles.panel}>
        <div className={styles.error} role="alert">
          <p className={styles.errorTitle}>Check failed</p>
          <p className={styles.errorBody}>Something went wrong while checking this image. Please try again later.</p>
          <button type="button" className={styles.again} onClick={reset}>
            Dismiss
          </button>
        </div>
      </div>
    )
  }

  if (!result) return null

  return (
    <div className={styles.panel}>
      <div className={styles.head}>
        <h2 className={styles.heading}>Result</h2>
        <button type="button" className={styles.again} onClick={reset}>
          Check another
        </button>
      </div>
      <ResultCard result={result} />
    </div>
  )
}
