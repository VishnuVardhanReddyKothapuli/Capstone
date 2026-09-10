import { useEffect, useState } from 'react'

import type { CheckResult, ExplanationBlock } from '../types'
import styles from './ExplainBox.module.css'

interface Props {
  result: CheckResult
  compact?: boolean
}

export function ExplainBox({ result }: Props) {
  const [explanation, setExplanation] = useState<ExplanationBlock | null>(result.explanation)

  useEffect(() => {
    setExplanation(result.explanation)
  }, [result.explanation])

  if (!explanation) {
    return null
  }

  return (
    <section className={styles.box} data-tier={result.overall_color}>
      <p className={styles.body}>{explanation.description}</p>
      <p className={styles.body}>{explanation.explanation}</p>
    </section>
  )
}
