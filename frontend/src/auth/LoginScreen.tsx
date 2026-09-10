import { useState } from 'react'
import type { FormEvent } from 'react'

import { ApiError } from '../api/client'
import { useAuth } from './AuthContext'
import styles from './LoginScreen.module.css'

const USERNAME_PATTERN = /^[A-Za-z0-9_.\-]+$/

/** Mirrors backend/app/schemas.py so mistakes surface before a round trip. */
function validate(mode: 'in' | 'up', username: string, password: string): string | null {
  if (mode === 'in') return username && password ? null : 'Enter your username and password.'
  if (username.length < 3 || username.length > 64) return 'Username must be 3-64 characters.'
  if (!USERNAME_PATTERN.test(username))
    return 'Username may only contain letters, digits, dot, dash and underscore.'
  if (password.length < 8) return 'Password must be at least 8 characters.'
  return null
}

export function LoginScreen() {
  const { signIn, signUp } = useAuth()
  const [mode, setMode] = useState<'in' | 'up'>('in')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [email, setEmail] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    const problem = validate(mode, username, password)
    if (problem) {
      setError(problem)
      return
    }
    setBusy(true)
    setError(null)
    try {
      if (mode === 'in') await signIn(username, password)
      else await signUp(username, password, email)
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : 'Could not reach the API. Is the backend running?',
      )
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className={styles.screen}>
      <form className={styles.card} onSubmit={submit}>
        <div className={styles.brand}>
          <span className={styles.mark} aria-hidden="true">
            S
          </span>
          <div>
            <h1 className={styles.title}>Sentinal</h1>
            <p className={styles.tagline}>NSFW classification and duplicate detection.</p>
          </div>
        </div>

        <div className={styles.tabs} role="tablist" aria-label="Authentication mode">
          {(['in', 'up'] as const).map((value) => (
            <button
              key={value}
              type="button"
              role="tab"
              aria-selected={mode === value}
              className={`${styles.tab} ${mode === value ? styles.tabActive : ''}`}
              onClick={() => {
                setMode(value)
                setError(null)
              }}
            >
              {value === 'in' ? 'Sign in' : 'Create account'}
            </button>
          ))}
        </div>

        <label className={styles.field}>
          <span className={styles.label}>Username</span>
          <input
            className={styles.input}
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            autoComplete="username"
            autoCapitalize="none"
            spellCheck={false}
            maxLength={64}
            required
          />
        </label>

        {mode === 'up' && (
          <label className={styles.field}>
            <span className={styles.label}>Email <span className={styles.help}>(optional; needed for configured admin access)</span></span>
            <input className={styles.input} type="email" value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="email" maxLength={254} />
          </label>
        )}

        <label className={styles.field}>
          <span className={styles.label}>Password</span>
          <input
            className={styles.input}
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete={mode === 'in' ? 'current-password' : 'new-password'}
            maxLength={256}
            required
          />
          {mode === 'up' && <span className={styles.help}>At least 8 characters.</span>}
        </label>

        {error && (
          <p className={styles.error} role="alert">
            {error}
          </p>
        )}

        <button type="submit" className={styles.submit} disabled={busy}>
          {busy ? 'Please wait…' : mode === 'in' ? 'Sign in' : 'Create account'}
        </button>

        <p className={styles.note}>
          History is private to your account. Uploads are stored so you can review them later.
        </p>
      </form>
    </main>
  )
}
