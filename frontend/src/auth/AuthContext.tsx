import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'

import { api, getToken, setToken, setUnauthorizedHandler } from '../api/client'
import type { User } from '../types'

interface AuthState {
  user: User | null
  /** False until the stored token has been checked against /api/auth/me. */
  ready: boolean
  signIn: (username: string, password: string) => Promise<void>
  signUp: (username: string, password: string, email?: string) => Promise<void>
  signOut: () => void
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [ready, setReady] = useState(false)

  const signOut = useCallback(() => {
    setToken(null)
    setUser(null)
  }, [])

  // Any 401 from anywhere in the app drops the session, not just this one call.
  useEffect(() => {
    setUnauthorizedHandler(signOut)
    return () => setUnauthorizedHandler(null)
  }, [signOut])

  // Restore a session from the token in localStorage on first load.
  useEffect(() => {
    if (!getToken()) {
      setReady(true)
      return
    }
    let cancelled = false
    api
      .me()
      .then((me) => {
        if (!cancelled) setUser(me)
      })
      .catch(() => setToken(null))
      .finally(() => {
        if (!cancelled) setReady(true)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const value = useMemo<AuthState>(
    () => ({
      user,
      ready,
      signIn: async (username, password) => {
        const response = await api.login(username, password)
        setToken(response.access_token)
        setUser(response.user)
      },
      signUp: async (username, password, email) => {
        const response = await api.register(username, password, email)
        setToken(response.access_token)
        setUser(response.user)
      },
      signOut,
    }),
    [user, ready, signOut],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used inside <AuthProvider>')
  return context
}
