import styles from './Metric.module.css'

interface Props {
  label: string
  value: string
  /** Optional 0-1 fraction; draws a fill bar underneath the value. */
  bar?: number | null
  /** Tints the value and bar with the tier colour of the enclosing card. */
  tinted?: boolean
  hint?: string
}

/**
 * One labelled number in a result card. Deliberately dumb — the caller decides
 * what is worth showing, so the same tile serves NSFW and similarity blocks.
 */
export function Metric({ label, value, bar = null, tinted = false, hint }: Props) {
  return (
    <div className={styles.metric} title={hint}>
      <span className={styles.label}>{label}</span>
      <span className={`${styles.value} ${tinted ? styles.tinted : ''}`}>{value}</span>
      {bar !== null && (
        <span className={styles.track}>
          <span
            className={`${styles.fill} ${tinted ? styles.tintedFill : ''}`}
            style={{ width: `${Math.min(Math.max(bar, 0), 1) * 100}%` }}
          />
        </span>
      )}
    </div>
  )
}
