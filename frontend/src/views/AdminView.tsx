import { useEffect, useState } from 'react'
import { api } from '../api/client'
import page from './Page.module.css'
import styles from './StaticPage.module.css'

export function AdminView() {
  const [summary, setSummary] = useState<{ users: number; checks: number } | null>(null)
  const [failed, setFailed] = useState(false)
  useEffect(() => { api.adminSummary().then(setSummary).catch(() => setFailed(true)) }, [])
  return <div className={page.page}>
    <header className={page.header}><span className={page.eyebrow}>Restricted</span><h1 className={page.title}>Admin</h1><p className={page.subtitle}>Operational totals only. Individual user data is not shown here.</p></header>
    {failed && <p className={styles.body} role="alert">This information is unavailable right now.</p>}
    {!failed && !summary && <p className={styles.body}>Loading…</p>}
    {summary && <div className={styles.grid}><div className={styles.row}><span className={styles.rowLabel}>Accounts</span><span className={styles.rowValue}>{summary.users}</span></div><div className={styles.row}><span className={styles.rowLabel}>Checks</span><span className={styles.rowValue}>{summary.checks}</span></div></div>}
  </div>
}
