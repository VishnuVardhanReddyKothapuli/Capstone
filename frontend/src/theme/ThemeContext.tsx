import { createContext, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'

type Theme = 'light' | 'dark'
interface ThemeState { theme: Theme; toggle: () => void }
const ThemeContext = createContext<ThemeState | null>(null)
const KEY = 'sentinal.theme'
function initialTheme(): Theme { const saved = localStorage.getItem(KEY); return saved === 'light' || saved === 'dark' ? saved : window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light' }
export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>(initialTheme)
  useEffect(() => { document.documentElement.dataset.theme = theme; localStorage.setItem(KEY, theme) }, [theme])
  const value = useMemo(() => ({ theme, toggle: () => setTheme((current) => current === 'light' ? 'dark' : 'light') }), [theme])
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}
export function useTheme(): ThemeState { const context = useContext(ThemeContext); if (!context) throw new Error('Theme provider is missing'); return context }
