import { useAuth } from './auth/AuthContext'
import { LoginScreen } from './auth/LoginScreen'
import { Sidebar } from './components/Sidebar'
import { useRoute } from './router'
import type { Route } from './router'
import { AboutView } from './views/AboutView'
import { CheckView } from './views/CheckView'
import { HistoryView } from './views/HistoryView'
import { HomeView } from './views/HomeView'
import { StackView } from './views/StackView'
import { AdminView } from './views/AdminView'
import styles from './App.module.css'

/** The two check views share a component, so the key forces a clean remount. */
function renderRoute(route: Route) {
  switch (route) {
    case 'home':
      return <HomeView />
    case 'nsfw':
      return <CheckView key="nsfw" mode="nsfw" />
    case 'similarity':
      return <CheckView key="similarity" mode="similarity" />
    case 'history':
      return <HistoryView />
    case 'about':
      return <AboutView />
    case 'stack':
      return <StackView />
    case 'admin':
      return <AdminView />
  }
}

export function App() {
  const { user, ready } = useAuth()
  const { route, navigate } = useRoute()

  // Held until the stored token has been checked, so a refresh does not flash
  // the login screen at an already-signed-in user.
  if (!ready) {
    return (
      <div className={styles.boot}>
        <span className={styles.spinner} aria-label="Loading" />
      </div>
    )
  }

  if (!user) return <LoginScreen />

  if (route === 'admin' && !user.is_admin) {
    navigate('home')
    return null
  }

  return (
    <div className={styles.shell}>
      <Sidebar route={route} onNavigate={navigate} />
      <main className={styles.main}>{renderRoute(route)}</main>
    </div>
  )
}
