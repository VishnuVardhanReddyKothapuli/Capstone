/** Mirrors backend/app/schemas.py. Keep the two in step. */

export type CheckType = 'nsfw' | 'similarity' | 'both'
export type Tier = 'safe' | 'suggestive' | 'explicit'
export type TierColor = 'green' | 'amber' | 'red'

/**
 * The explainer's own vocabulary, deliberately wider than `Tier`: Gemini can
 * name violence or hate, which a two-class NSFW model cannot see.
 */
export type ExplainClass = 'safe' | 'suggestive' | 'nsfw' | 'violent' | 'hate'

export type SimilarityTier =
  | 'Identical'
  | 'Near-Duplicate'
  | 'Similar'
  | 'Slightly Similar'
  | 'Unique'

export interface User {
  id: number
  username: string
  created_at: string
  is_admin: boolean
}

export interface TokenResponse {
  access_token: string
  token_type: 'bearer'
  expires_in: number
  user: User
}

/** Five values, all from Falconsai's two-class output. */
export interface NsfwBlock {
  nsfw_score: number
  safe_score: number
  tier: Tier
  threshold: number
  frames_analyzed: number
  frame_count: number
  color: TierColor
}

export interface SimilarityMatch {
  check_id: number
  filename: string
  created_at: string
  thumbnail_url: string
  uploaded_by?: string
}

/** Five values: score, band, original uploader, original date, match count. */
export interface SimilarityBlock {
  top_score: number | null
  tier: SimilarityTier
  match_count: number
  match: SimilarityMatch | null
  color: TierColor
}

/**
 * Gemini's written second opinion, normalised server-side. A cross-check rather
 * than an input: it never moves `overall_tier`, so the card can show the two
 * verdicts side by side and disagree visibly.
 */
export interface ExplanationBlock {
  classification: ExplainClass
  confidence: number
  scores: Record<ExplainClass, number>
  detected_text: string | null
  text_toxicity: number
  description: string
  explanation: string
  /** True only for `safe` — the one class allowed to publish. */
  publish_allowed: boolean
  model: string
  frame_index: number
  frames_total: number
  /** The model's own scores were inconsistent and were repaired server-side. */
  repaired: boolean
}

export interface CheckResult {
  check_id: number
  check_type: CheckType
  filename: string
  content_type: string
  created_at: string
  overall_tier: Tier
  overall_color: TierColor
  image_url: string
  thumbnail_url: string
  uploaded_by?: string
  nsfw: NsfwBlock | null
  similarity: SimilarityBlock | null
  explanation: ExplanationBlock | null
  explained_at: string | null
}

export interface HistoryPage {
  items: CheckResult[]
  total: number
  limit: number
  offset: number
}

export interface ModelInfo {
  nsfw_model: string
  nsfw_labels: string[]
  nsfw_explicit_threshold: number
  nsfw_suggestive_threshold: number
  nsfw_model_loaded: boolean
  embedding_model: string
  embedding_dim: number
  embedding_model_loaded: boolean
  vector_store: string
  vector_store_collection: string
  vector_store_count: number
  relational_store: string
  backend: string
  max_gif_frames: number
  max_upload_bytes: number
  similarity_bands: Record<string, number>
  explainer_model: string
  /** Whether GEMINI_API_KEY is set. The key itself never leaves the server. */
  explainer_configured: boolean
  app_version: string
  environment: string
  deployment: string
}
