import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

import { App } from './App'
import { AuthProvider } from './auth/AuthContext'
import { ThemeProvider } from './theme/ThemeContext'
import './styles/tokens.css'
import './styles/global.css'

const container = document.getElementById('root')
if (!container) throw new Error('#root is missing from index.html')

createRoot(container).render(
  <StrictMode>
    <ThemeProvider><AuthProvider><App /></AuthProvider></ThemeProvider>
  </StrictMode>,
)
