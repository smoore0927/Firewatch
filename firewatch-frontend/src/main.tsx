/**
 * Vite entry point — replaces the CRA-style index.tsx.
 *
 * Three providers wrap the whole app here (outermost first):
 *   1. BrowserRouter — gives React Router access to the URL
 *   2. AuthProvider — fetches the current user on mount and exposes
 *      login / logout to every component via useAuth()
 *
 * Keeping the providers at the root means every route, including
 * ProtectedRoute, can read auth state without prop drilling.
 */
import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { AuthProvider } from '@/context/AuthContext'
import App from '@/App'
import '@/index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <App />
      </AuthProvider>
    </BrowserRouter>
  </React.StrictMode>,
)
