/**
 * Minimal client-side router: real URLs via the History API, no dependency.
 * FastAPI serves index.html for any unknown path, so a refresh on /history works.
 */

import { useCallback, useEffect, useState } from 'react'

export const ROUTES = ['home', 'nsfw', 'similarity', 'history', 'about', 'stack', 'admin'] as const

export type Route = (typeof ROUTES)[number]

const PATH_BY_ROUTE: Record<Route, string> = {
  home: '/',
  nsfw: '/nsfw',
  similarity: '/similarity',
  history: '/history',
  about: '/about',
  stack: '/stack',
  admin: '/admin',
}

export function pathOf(route: Route): string {
  return PATH_BY_ROUTE[route]
}

function routeOf(pathname: string): Route {
  const normalised = pathname.replace(/\/+$/, '') || '/'
  const found = ROUTES.find((route) => PATH_BY_ROUTE[route] === normalised)
  return found ?? 'home'
}

export function useRoute(): { route: Route; navigate: (route: Route) => void } {
  const [route, setRoute] = useState<Route>(() => routeOf(window.location.pathname))

  useEffect(() => {
    const onPopState = () => setRoute(routeOf(window.location.pathname))
    window.addEventListener('popstate', onPopState)
    return () => window.removeEventListener('popstate', onPopState)
  }, [])

  const navigate = useCallback((next: Route) => {
    const path = pathOf(next)
    if (window.location.pathname !== path) window.history.pushState(null, '', path)
    setRoute(next)
    window.scrollTo({ top: 0 })
  }, [])

  return { route, navigate }
}
