import type { TierColor } from '../types'
import styles from './TierBadge.module.css'

const GLYPH: Record<TierColor, string> = {
  green: '✓',
  amber: '!',
  red: '✕',
}

interface Props {
  color: TierColor
  label: string
  /** Optional trailing detail, e.g. the score that produced the verdict. */
  detail?: string
  size?: 'sm' | 'md'
}

/**
 * Colour-coded verdict pill. The label text and glyph carry the same meaning as
 * the colour, so the verdict is still readable without colour perception.
 */
export function TierBadge({ color, label, detail, size = 'md' }: Props) {
  return (
    <span
      className={`${styles.badge} ${size === 'sm' ? styles.small : ''}`}
      data-tier={color}
    >
      <span className={styles.glyph} aria-hidden="true">
        {GLYPH[color]}
      </span>
      <span className={styles.label}>{label}</span>
      {detail && <span className={styles.detail}>{detail}</span>}
    </span>
  )
}
