import { useId, useRef, useState } from 'react'
import type { DragEvent } from 'react'

import type { CheckType } from '../types'
import styles from './Dropzone.module.css'

const GLYPH: Record<CheckType, string> = {
  nsfw: '◎',
  similarity: '⧉',
  both: '⊞',
}

interface Props {
  mode: CheckType
  title: string
  description: string
  hint?: string
  busy?: boolean
  onFile: (file: File, mode: CheckType) => void
}

/**
 * Drag-and-drop *and* click-to-browse, because a card that only accepts drags is
 * unusable on a touch screen and one that only accepts clicks ignores the
 * obvious gesture. Both paths land in the same onFile callback.
 */
export function Dropzone({ mode, title, description, hint, busy = false, onFile }: Props) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)
  const [rejected, setRejected] = useState<string | null>(null)
  const inputId = useId()

  const accept = (file: File | undefined) => {
    if (!file) return
    if (file.type && !file.type.startsWith('image/')) {
      setRejected(`${file.name} is not an image.`)
      return
    }
    setRejected(null)
    onFile(file, mode)
  }

  const onDrop = (event: DragEvent<HTMLButtonElement>) => {
    event.preventDefault()
    setDragging(false)
    if (busy) return
    accept(event.dataTransfer.files[0])
  }

  const onDragOver = (event: DragEvent<HTMLButtonElement>) => {
    event.preventDefault()
    if (!busy) setDragging(true)
  }

  return (
    <div className={styles.wrap}>
      <button
        type="button"
        className={`${styles.zone} ${dragging ? styles.dragging : ''}`}
        onClick={() => inputRef.current?.click()}
        onDragOver={onDragOver}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        disabled={busy}
        aria-describedby={inputId}
      >
        <span className={styles.glyph} aria-hidden="true">
          {GLYPH[mode]}
        </span>
        <span className={styles.title}>{title}</span>
        <span className={styles.description}>{description}</span>
        <span className={styles.cta} id={inputId}>
          {busy ? 'Working…' : 'Drop an image or click to browse'}
        </span>
        {hint && <span className={styles.hint}>{hint}</span>}
      </button>

      {/* Kept outside the button: interactive content cannot nest in a button. */}
      <input
        ref={inputRef}
        type="file"
        accept="image/*"
        className={styles.input}
        tabIndex={-1}
        onChange={(event) => {
          accept(event.target.files?.[0])
          // Clear it so re-picking the same file fires change again.
          event.target.value = ''
        }}
      />

      {rejected && <p className={styles.rejected}>{rejected}</p>}
    </div>
  )
}
