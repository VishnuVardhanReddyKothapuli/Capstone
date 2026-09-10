import { useAuth } from '../auth/AuthContext'
import { useTheme } from '../theme/ThemeContext'
import { pathOf } from '../router'
import type { Route } from '../router'
import styles from './Sidebar.module.css'

interface Item {
  route: Route
  label: string
  glyph: string
}

const ITEMS: Item[] = [
  { route: 'nsfw', label: 'NSFW Check', glyph: '◎' },
  { route: 'similarity', label: 'Similarity Check', glyph: '⧉' },
  { route: 'history', label: 'History', glyph: '☰' },
  { route: 'about', label: 'About', glyph: 'i' },
  { route: 'stack', label: 'Models & Tech Stack', glyph: '⚙' },
]

interface Props {
  route: Route
  onNavigate: (route: Route) => void
}

export function Sidebar({ route, onNavigate }: Props) {
  const { user, signOut } = useAuth()
  const { theme, toggle } = useTheme()
  const items = user?.is_admin ? [...ITEMS, { route: 'admin' as const, label: 'Admin', glyph: 'A' }] : ITEMS

  return (
    <nav className={styles.sidebar} aria-label="Main">
      <a
        className={styles.brand}
        href={pathOf('home')}
        onClick={(event) => {
          event.preventDefault()
          onNavigate('home')
        }}
      >
        <span className={styles.mark} aria-hidden="true">
          S
        </span>
        <span className={styles.wordmark}>Sentinal</span>
      </a>

      <ul className={styles.list}>
        {items.map((item) => (
          <li key={item.route}>
            {/* A real href so middle-click and copy-link behave; the click is
                intercepted for pushState navigation. */}
            <a
              className={`${styles.link} ${route === item.route ? styles.active : ''}`}
              href={pathOf(item.route)}
              aria-current={route === item.route ? 'page' : undefined}
              onClick={(event) => {
                event.preventDefault()
                onNavigate(item.route)
              }}
            >
              <span className={styles.glyph} aria-hidden="true">
                {item.glyph}
              </span>
              {item.label}
            </a>
          </li>
        ))}
      </ul>

      <div className={styles.footer}>
        {user && (
          <>
            <div className={styles.account}>
              <span className={styles.avatar} aria-hidden="true">
                {user.username.slice(0, 1).toUpperCase()}
              </span>
              <span className={styles.username} title={user.username}>
                {user.username}
              </span>
            </div>
            <button type="button" className={styles.signOut} onClick={signOut}>
              Sign out
            </button>
            <button type="button" className={styles.themeToggle} onClick={toggle}>
              {theme === 'light' ? '☾ Dark Mode' : '☀ Light Mode'}
            </button>
          </>
        )}
      </div>
    </nav>
  )
}
