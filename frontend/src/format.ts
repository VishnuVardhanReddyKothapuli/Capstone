/** Display helpers shared by the result card, history and stack views. */

import type { CheckType, ExplainClass, SimilarityTier, Tier, TierColor } from './types'

export const TIER_LABEL: Record<Tier, string> = {
  safe: 'Safe',
  suggestive: 'Suggestive',
  explicit: 'Explicit',
}

export const MODE_LABEL: Record<CheckType, string> = {
  nsfw: 'NSFW',
  similarity: 'Similarity',
  both: 'Both',
}

export const EXPLAIN_LABEL: Record<ExplainClass, string> = {
  safe: 'Safe',
  suggestive: 'Suggestive',
  nsfw: 'NSFW',
  violent: 'Violent',
  hate: 'Hateful',
}

/**
 * Only `safe` may publish, so every other class is red — the amber band is kept
 * for `suggestive`, where the model itself is signalling that it is unsure.
 */
export const EXPLAIN_COLOR: Record<ExplainClass, TierColor> = {
  safe: 'green',
  suggestive: 'amber',
  nsfw: 'red',
  violent: 'red',
  hate: 'red',
}

/** What each similarity band actually means, for tooltips and the stack page. */
export const SIM_TIER_HINT: Record<SimilarityTier, string> = {
  Identical: 'Cosine ≥ 0.98 — effectively the same image.',
  'Near-Duplicate': 'Cosine ≥ 0.92 — a crop, re-encode or light edit.',
  Similar: 'Cosine ≥ 0.80 — same subject or scene.',
  'Slightly Similar': 'Cosine ≥ 0.60 — loosely related.',
  Unique: 'Nothing in the corpus scored above 0.60.',
}

export function percent(value: number, digits = 1): string {
  return `${(value * 100).toFixed(digits)}%`
}

/** Cosine similarity to 4 places; null means nothing cleared the match floor. */
export function cosine(value: number | null): string {
  return value === null ? '—' : value.toFixed(4)
}

export function dateTime(iso: string): string {
  const date = new Date(iso)
  return Number.isNaN(date.getTime())
    ? iso
    : date.toLocaleString(undefined, {
        year: 'numeric',
        month: 'short',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
      })
}

export function bytes(count: number): string {
  if (count < 1024) return `${count} B`
  const units = ['KB', 'MB', 'GB']
  let value = count / 1024
  let unit = 0
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024
    unit += 1
  }
  return `${value >= 10 ? value.toFixed(0) : value.toFixed(1)} ${units[unit]}`
}
