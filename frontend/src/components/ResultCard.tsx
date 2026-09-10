import { useState } from 'react'
import { dateTime } from '../format'
import type { CheckResult, Tier } from '../types'
import { AuthedImage } from './AuthedImage'
import { ExplainBox } from './ExplainBox'
import styles from './ResultCard.module.css'

const VERDICT: Record<Tier, string> = { safe: 'Safe', suggestive: 'Unclear', explicit: 'Not safe' }
function reason(result: CheckResult): string {
  if (result.nsfw?.tier === 'explicit') return 'This image may contain explicit content.'
  if (result.nsfw?.tier === 'suggestive') return 'The content result needs a closer look.'
  if (result.similarity?.tier === 'Identical' || result.similarity?.tier === 'Near-Duplicate') return 'A very similar image already exists in the database.'
  if (result.similarity?.tier === 'Similar') return 'A similar image was found in the database.'
  return 'No concerns were found by this check.'
}
export function ResultCard({ result, compact = false }: { result: CheckResult; compact?: boolean }) {
  const [showOriginal, setShowOriginal] = useState(false)
  return (
    <article className={`${styles.card} ${compact ? styles.compact : ''}`} data-tier={result.overall_color}>
      <header className={styles.header}>
        <AuthedImage path={result.thumbnail_url} alt={result.filename} className={styles.thumb} />
        <div className={styles.identity}>
          <h3 className={styles.filename} title={result.filename}>{result.filename}</h3>
          <p className={styles.meta}>{dateTime(result.created_at)}</p>
        </div>
        <strong className={styles.verdict}>{VERDICT[result.overall_tier]}</strong>
      </header>
      <p className={styles.simpleReason}>{reason(result)}</p>
      {!compact && (
        <>
          <div className={styles.actions}>
            <button type="button" className={styles.reveal} onClick={() => setShowOriginal((shown) => !shown)}>
              {showOriginal ? 'Hide image' : 'View image'}
            </button>
          </div>
          {showOriginal && <AuthedImage path={result.image_url} alt={result.filename} className={styles.original} />}
          <ExplainBox result={result} />
        </>
      )}
    </article>
  )
}
