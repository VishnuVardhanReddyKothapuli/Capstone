import { Dropzone } from '../components/Dropzone'
import { ResultPanel } from '../components/ResultPanel'
import { bytes } from '../format'
import { useModeration } from '../useModeration'
import type { CheckType } from '../types'
import page from './Page.module.css'
import styles from './HomeView.module.css'

const MAX_BYTES = 10 * 1024 * 1024

const CARDS: { mode: CheckType; title: string; description: string }[] = [
  {
    mode: 'nsfw',
    title: 'NSFW Check',
    description: 'Score the image with Falconsai and place it on the traffic light.',
  },
  {
    mode: 'similarity',
    title: 'Similarity Check',
    description: 'Embed with CLIP and find the closest image already stored.',
  },
  {
    mode: 'both',
    title: 'Both',
    description: 'Run the classifier and the duplicate search in one pass.',
  },
]

export function HomeView() {
  const moderation = useModeration()

  return (
    <div className={page.page}>
      <header className={page.header}>
        <span className={page.eyebrow}>Sentinal</span>
        <h1 className={page.title}>Check an image</h1>
        <p className={page.subtitle}>
          Drop a file on a card or click to browse. JPEG, PNG, WebP, BMP and animated GIF are
          accepted, up to {bytes(MAX_BYTES)}. Animations are sampled and scored on their worst
          keyframe.
        </p>
      </header>

      <div className={styles.cards}>
        {CARDS.map((card) => (
          <Dropzone
            key={card.mode}
            mode={card.mode}
            title={card.title}
            description={card.description}
            hint={card.mode === 'both' ? 'recommended' : undefined}
            busy={moderation.status === 'busy'}
            onFile={moderation.run}
          />
        ))}
      </div>

      <ResultPanel moderation={moderation} />
    </div>
  )
}
