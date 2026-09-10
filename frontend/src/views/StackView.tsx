import { bytes } from '../format'
import type { ReactNode } from 'react'
import { useModelInfo } from '../useModelInfo'
import page from './Page.module.css'
import styles from './StaticPage.module.css'

function Row({ label, value }: { label: string; value: string }) { return <div className={styles.row}><span className={styles.rowLabel}>{label}</span><span className={styles.rowValue} title={value}>{value}</span></div> }
function Section({ title, children }: { title: string; children: ReactNode }) { return <section className={styles.section}><h2 className={styles.sectionTitle}>{title}</h2><div className={styles.grid}>{children}</div></section> }
export function StackView() {
  const { info, error } = useModelInfo()
  return <div className={page.page}>
    <header className={page.header}><span className={page.eyebrow}>Reference</span><h1 className={page.title}>Models &amp; Tech Stack</h1><p className={page.subtitle}>Configuration from the running service. Secrets and connection strings are never displayed.</p></header>
    {error && <p className={styles.body} role="alert">This information is unavailable right now.</p>}
    {!info && !error && <p className={styles.body}>Loading…</p>}
    {info && <>
      <Section title="Models"><Row label="Content classifier" value={info.nsfw_model} /><Row label="Purpose" value="Classifies image content as safe, unclear, or not safe." /><Row label="Model labels" value={info.nsfw_labels.join(' · ')} /><Row label="Embedding model" value={info.embedding_model} /><Row label="Purpose" value="Finds duplicate and near-duplicate images across the corpus." /><Row label="Embedding size" value={`${info.embedding_dim} dimensions`} /><Row label="Optional explainer" value={info.explainer_model} /><Row label="Purpose" value="Optional supporting explanation; it does not change the automatic verdict." /></Section>
      <Section title="Application"><Row label="Frontend" value="React 19, TypeScript, Vite, CSS Modules" /><Row label="Backend" value={`${info.backend} ${info.app_version}`} /><Row label="Database" value={info.relational_store} /><Row label="Vector database" value={info.vector_store} /><Row label="Authentication" value="bcrypt password hashing and signed JWT bearer sessions" /><Row label="Deployment" value={info.deployment} /><Row label="Environment" value={info.environment} /></Section>
      <Section title="Supporting services"><Row label="Image processing" value="Pillow" /><Row label="ML runtime" value="Transformers and PyTorch" /><Row label="Similarity" value="CLIP embeddings with cosine distance" /><Row label="Maximum upload" value={bytes(info.max_upload_bytes)} /><Row label="GIF sampling" value={`${info.max_gif_frames} keyframes maximum`} /></Section>
    </>}
  </div>
}
