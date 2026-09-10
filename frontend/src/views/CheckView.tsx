import { Dropzone } from '../components/Dropzone'
import { ResultPanel } from '../components/ResultPanel'
import { TierBadge } from '../components/TierBadge'
import type { TierColor } from '../types'
import { useModelInfo } from '../useModelInfo'
import { useModeration } from '../useModeration'
import page from './Page.module.css'
import styles from './CheckView.module.css'

interface Band {
  color: TierColor
  label: string
  range: string
  note: string
}

const COPY = {
  nsfw: {
    title: 'NSFW Check',
    subtitle:
      'Falconsai/nsfw_image_detection is a two-class vision transformer: it returns one nsfw probability and its complement. Everything on the card is derived from that pair — nothing is invented.',
    dropTitle: 'Classify an image',
    dropDescription: 'Only the classifier runs. The image is not added to the similarity corpus.',
  },
  similarity: {
    title: 'Similarity Check',
    subtitle:
      'CLIP turns the image into a 512-dimension unit vector, Chroma finds the nearest stored vectors by cosine distance, and the closest one becomes the match. The new vector joins the corpus so later uploads can match it.',
    dropTitle: 'Find duplicates',
    dropDescription: 'Only the embedding runs. No NSFW score is produced for this check.',
  },
} as const

function nsfwBands(suggestive: number, explicit: number): Band[] {
  return [
    { color: 'green', label: 'Safe', range: `< ${suggestive.toFixed(2)}`, note: 'Cleared.' },
    {
      color: 'amber',
      label: 'Suggestive',
      range: `${suggestive.toFixed(2)} – ${explicit.toFixed(2)}`,
      note: 'The model is not confident either way. Flagged for a human.',
    },
    {
      color: 'red',
      label: 'Explicit',
      range: `≥ ${explicit.toFixed(2)}`,
      note: 'Above the block threshold.',
    },
  ]
}

function similarityBands(bands: Record<string, number>): Band[] {
  const at = (key: string, fallback: number) => bands[key] ?? fallback
  return [
    {
      color: 'red',
      label: 'Identical',
      range: `≥ ${at('identical', 0.98).toFixed(2)}`,
      note: 'Effectively the same image.',
    },
    {
      color: 'red',
      label: 'Near-Duplicate',
      range: `≥ ${at('near_duplicate', 0.92).toFixed(2)}`,
      note: 'A crop, a re-encode or a light edit.',
    },
    {
      color: 'amber',
      label: 'Similar',
      range: `≥ ${at('similar', 0.8).toFixed(2)}`,
      note: 'Same subject or scene.',
    },
    {
      color: 'green',
      label: 'Slightly Similar',
      range: `≥ ${at('match_floor', 0.6).toFixed(2)}`,
      note: 'Loosely related. Still reported as a match.',
    },
    {
      color: 'green',
      label: 'Unique',
      range: `< ${at('match_floor', 0.6).toFixed(2)}`,
      note: 'Nothing close enough to report.',
    },
  ]
}

export function CheckView({ mode }: { mode: 'nsfw' | 'similarity' }) {
  const moderation = useModeration()
  const { info } = useModelInfo()
  const copy = COPY[mode]

  const bands: Band[] | null = !info
    ? null
    : mode === 'nsfw'
      ? nsfwBands(info.nsfw_suggestive_threshold, info.nsfw_explicit_threshold)
      : similarityBands(info.similarity_bands)

  return (
    <div className={page.page}>
      <header className={page.header}>
        <span className={page.eyebrow}>{mode === 'nsfw' ? 'Classifier' : 'Vector search'}</span>
        <h1 className={page.title}>{copy.title}</h1>
        <p className={page.subtitle}>{copy.subtitle}</p>
      </header>

      <div className={styles.layout}>
        <Dropzone
          mode={mode}
          title={copy.dropTitle}
          description={copy.dropDescription}
          busy={moderation.status === 'busy'}
          onFile={moderation.run}
        />

        <section className={styles.legend} aria-label="Bands">
          <h2 className={styles.legendTitle}>Bands</h2>
          {bands ? (
            <ul className={styles.bands}>
              {bands.map((band) => (
                <li key={band.label} className={styles.band}>
                  <TierBadge size="sm" color={band.color} label={band.label} detail={band.range} />
                  <span className={styles.note}>{band.note}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className={styles.note}>Loading thresholds…</p>
          )}
        </section>
      </div>

      <ResultPanel moderation={moderation} />
    </div>
  )
}
