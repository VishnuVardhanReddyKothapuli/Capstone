import { useEffect, useState } from 'react'

import { api } from '../api/client'
import styles from './AuthedImage.module.css'

interface Props {
  /** API path, e.g. /api/checks/12/thumbnail. */
  path: string
  alt: string
  className?: string
}

/**
 * <img> for an endpoint that requires a Bearer token. The browser never sends
 * Authorization for a plain src, so the bytes are fetched here and turned into
 * an object URL, which is revoked as soon as the path changes or we unmount.
 */
export function AuthedImage({ path, alt, className }: Props) {
  const [url, setUrl] = useState<string | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let revoked = false
    let objectUrl: string | null = null

    setUrl(null)
    setFailed(false)

    api
      .objectUrl(path)
      .then((next) => {
        // Unmounted while in flight: release immediately, never call setState.
        if (revoked) {
          URL.revokeObjectURL(next)
          return
        }
        objectUrl = next
        setUrl(next)
      })
      .catch(() => {
        if (!revoked) setFailed(true)
      })

    return () => {
      revoked = true
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [path])

  if (failed) {
    return (
      <div className={`${styles.frame} ${className ?? ''}`}>
        <span className={styles.fallback}>unavailable</span>
      </div>
    )
  }

  return (
    <div className={`${styles.frame} ${className ?? ''}`}>
      {url ? (
        <img className={styles.image} src={url} alt={alt} />
      ) : (
        <span className={styles.shimmer} aria-hidden="true" />
      )}
    </div>
  )
}
