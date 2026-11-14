import React, { useEffect, useState } from 'react'
import ReactDOM from 'react-dom/client'
import { AuthProvider, useAuth } from 'react-oidc-context'
import App from './App'
import { api, setAccessToken } from './api'
import './styles.css'

const authEnabled = import.meta.env.VITE_AUTH_MODE === 'oidc'
function LoginGate() {
  const auth = useAuth()
  const [role, setRole] = useState<'admin' | 'viewer' | null>(null)
  const [error, setError] = useState('')
  useEffect(() => {
    if (!auth.isAuthenticated || !auth.user?.access_token) { setAccessToken(null); setRole(null); return }
    setAccessToken(auth.user.access_token)
    api.me().then(user => { if (!user.roles.includes('launchpilot_admin') && !user.roles.includes('launchpilot_viewer')) throw new Error('No LaunchPilot role assigned to this account'); setRole(user.roles.includes('launchpilot_admin') ? 'admin' : 'viewer') }).catch(e => setError(e instanceof Error ? e.message : String(e)))
  }, [auth.isAuthenticated, auth.user?.access_token])
  if (auth.isLoading) return <div className="login-panel"><h1>LaunchPilot</h1><p>Completing secure sign-in…</p></div>
  if (auth.error || error) return <div className="login-panel"><h1>Sign-in failed</h1><p role="alert">{auth.error?.message || error}</p><button onClick={() => void auth.signinRedirect()}>Try again</button></div>
  if (!auth.isAuthenticated) return <div className="login-panel"><h1>LaunchPilot</h1><p>Sign in with your organization to manage progressive delivery.</p><button onClick={() => void auth.signinRedirect()}>Sign in with OIDC</button></div>
  if (!role) return <div className="login-panel"><p>Checking access permissions…</p></div>
  return <App canEdit={role === 'admin'} authMode="oidc" onLogout={() => void auth.signoutRedirect()} />
}
const oidc = {
  authority: import.meta.env.VITE_OIDC_AUTHORITY as string,
  client_id: import.meta.env.VITE_OIDC_CLIENT_ID as string,
  redirect_uri: window.location.origin + '/',
  post_logout_redirect_uri: window.location.origin + '/',
  scope: 'openid profile email',
  automaticSilentRenew: false,
  onSigninCallback: () => { window.history.replaceState({}, document.title, window.location.pathname) },
}
ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>{authEnabled ? <AuthProvider {...oidc}><LoginGate /></AuthProvider> : <App canEdit authMode="demo" />}</React.StrictMode>,
)
