import { useCallback, useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { api, ApiError } from './api'
import type { User } from './api'
import VerifierWorkspace, { DiscardChangesDialog } from './VerifierWorkspace'
import Snackbar from './Snackbar'
import type { SnackbarAction, SnackbarTone } from './Snackbar'

function PasswordField({ id, autoComplete, creating = false, disabled = false }: {
  id: string
  autoComplete: 'current-password' | 'new-password'
  creating?: boolean
  disabled?: boolean
}) {
  const [visible, setVisible] = useState(false)
  return <div className="field">
    <label htmlFor={id}>Password</label>
    <div className="password-input">
      <input id={id} name="password" type={visible ? 'text' : 'password'} required
        autoCapitalize="none" autoCorrect="off" spellCheck={false}
        minLength={creating ? 12 : undefined} maxLength={128} autoComplete={autoComplete}
        aria-describedby={creating ? `${id}-hint` : undefined} disabled={disabled} />
      <button className="password-toggle" type="button" onClick={() => setVisible(!visible)}
        aria-label={visible ? 'Hide password' : 'Show password'} aria-pressed={visible} disabled={disabled}>
        {visible ? 'Hide' : 'Show'}
      </button>
    </div>
    {creating ? <p className="field-hint" id={`${id}-hint`}>Use 12–128 characters.</p> : null}
  </div>
}

function Login({ onLogin }: { onLogin: (user: User) => void }) {
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function signIn(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const data = new FormData(event.currentTarget)
    setError('')
    setBusy(true)
    try {
      const user = await api<User>('/auth/login', {
        method: 'POST',
        body: JSON.stringify({ username: String(data.get('username')).trim(), password: data.get('password') }),
      })
      onLogin(user)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Unable to sign in. Please try again.')
    } finally {
      setBusy(false)
    }
  }

  return <div className="login-layout">
    <aside className="login-identity" aria-label="About InTrac">
      <div className="identity-content">
        <div className="trace-mark" aria-hidden="true"><span /><span /><span /></div>
        <h1>Weapon Seizure <br />Tracking</h1>
        <p>Access for the people responsible<br className="desktop-break" /> for every record.</p>
      </div>
      <p className="identity-footer">Authorized personnel only</p>
    </aside>
    <main className="login-main">
      <div className="login-form-wrap">
        <div className="section-icon" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"><rect x="5" y="10" width="14" height="11" rx="2" /><path d="M8 10V7a4 4 0 0 1 8 0v3" /><path d="M12 14v3" /></svg>
        </div>
        <h2>Sign in to InTrac</h2>
        <p className="intro">Enter your assigned username and password.</p>
        <form onSubmit={signIn} aria-label="Sign in" aria-busy={busy}>
          <div className="field">
            <label htmlFor="login-username">Username</label>
            <input id="login-username" name="username" autoComplete="username" autoCapitalize="none"
              spellCheck={false} required maxLength={64} disabled={busy} />
          </div>
          <PasswordField id="login-password" autoComplete="current-password" disabled={busy} />
          {error ? <p className="error-message" role="alert">{error}</p> : null}
          <button className="primary-button login-button" type="submit" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button>
        </form>
        <p className="account-help">Need an account? Contact your administrator.</p>
      </div>
      <p className="login-footer">InTrac <span aria-hidden="true">/</span> Weapon Seizure Tracking</p>
    </main>
  </div>
}

function CreateUser({ onExpired, onNotify }: { onExpired: () => void; onNotify: (message: string) => void }) {
  const [error, setError] = useState('')
  const [created, setCreated] = useState<User | null>(null)
  const [busy, setBusy] = useState(false)
  const firstName = useRef<HTMLInputElement>(null)

  async function createUser(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = event.currentTarget
    const data = new FormData(form)
    setError('')
    setCreated(null)
    setBusy(true)
    try {
      const user = await api<User>('/users', {
        method: 'POST',
        body: JSON.stringify({
          first_name: String(data.get('first_name')).trim(),
          last_name: String(data.get('last_name')).trim(),
          username: String(data.get('username')).trim(),
          password: data.get('password'),
          role: data.get('role'),
        }),
      })
      setCreated(user)
      onNotify(`${user.first_name} ${user.last_name} can now sign in as ${user.username} with the ${user.role === 'ADMINISTRATOR' ? 'Administrator' : 'Verifier'} role.`)
      form.reset()
    } catch (cause) {
      if (cause instanceof ApiError && (cause.status === 401 || cause.status === 403)) {
        onExpired()
      } else {
        setError(cause instanceof Error ? cause.message : 'Unable to create the user. Please try again.')
      }
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => {
    if (created) firstName.current?.focus()
  }, [created])

  return <>
    <div className="page-heading"><h1>Administrator settings</h1><p>Create accounts and assign access for your team.</p></div>
    <section className="create-user-panel" aria-labelledby="create-user-title">
      <div className="panel-heading"><div><h2 id="create-user-title">Create user</h2><p>All fields are required.</p></div></div>
      <form onSubmit={createUser} aria-label="Create user" aria-busy={busy}>
        <div className="name-fields">
          <div className="field"><label htmlFor="first-name">First name</label><input id="first-name" name="first_name" ref={firstName} required maxLength={80} autoComplete="off" disabled={busy} /></div>
          <div className="field"><label htmlFor="last-name">Last name</label><input id="last-name" name="last_name" required maxLength={80} autoComplete="off" disabled={busy} /></div>
        </div>
        <div className="field"><label htmlFor="new-username">Username</label><input id="new-username" name="username" required minLength={3} maxLength={64} pattern="[A-Za-z0-9._\-]+" autoComplete="off" autoCapitalize="none" spellCheck={false} aria-describedby="username-hint" disabled={busy} /><p className="field-hint" id="username-hint">3–64 characters. Letters, numbers, periods, hyphens, and underscores.</p></div>
        <PasswordField id="new-password" autoComplete="new-password" creating disabled={busy} />
        <div className="field"><label htmlFor="new-role">Role</label><select id="new-role" name="role" defaultValue="VERIFIER" disabled={busy} aria-describedby="role-hint"><option value="VERIFIER">Verifier</option><option value="ADMINISTRATOR">Administrator</option></select><p className="field-hint" id="role-hint">Administrators can create users. Verifiers cannot access administrator settings.</p></div>
        {error ? <p className="error-message" role="alert">{error}</p> : null}
        <div className="form-footer"><p>Share the credentials with the new user.</p><button className="primary-button" type="submit" disabled={busy}>{busy ? 'Creating user…' : 'Create user'}</button></div>
      </form>
    </section>
  </>
}

export default function App() {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [notification, setNotification] = useState<{ id: number; message: string; action?: SnackbarAction; tone: SnackbarTone; source: 'app' | 'workspace' }>({ id: 0, message: '', tone: 'success', source: 'app' })
  const [signingOut, setSigningOut] = useState(false)
  const [discardSignOut, setDiscardSignOut] = useState(false)
  const [retry, setRetry] = useState(0)
  const hasUnsavedDraft = useRef(false)
  const notify = useCallback((message: string, action?: SnackbarAction, tone: SnackbarTone = 'success') => {
    setNotification(current => ({ id: current.id + 1, message, action, tone, source: 'app' }))
  }, [])
  const notifyWorkspace = useCallback((message: string, action?: SnackbarAction) => {
    setNotification(current => ({ id: current.id + 1, message, action, tone: 'success', source: 'workspace' }))
  }, [])
  const dismissWorkspaceNotification = useCallback(() => {
    setNotification(current => current.source === 'workspace' ? { ...current, message: '', action: undefined } : current)
  }, [])
  const handleDraftChange = useCallback((dirty: boolean) => { hasUnsavedDraft.current = dirty }, [])
  const handleExpired = useCallback(() => {
    hasUnsavedDraft.current = false
    setUser(null)
    notify('Your session is no longer available. Please sign in again.', undefined, 'info')
  }, [notify])

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setLoadError('')
    api<User>('/auth/me', { signal: controller.signal })
      .then(setUser)
      .catch((cause: unknown) => {
        if (controller.signal.aborted) return
        if (cause instanceof ApiError && cause.status === 401) setUser(null)
        else setLoadError(cause instanceof Error ? cause.message : 'Unable to load your session.')
      })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [retry])

  useEffect(() => {
    document.title = `InTrac | ${user?.role === 'ADMINISTRATOR' ? 'Administrator settings' : user ? 'Verifier' : 'Sign in'}`
  }, [user])

  async function signOut() {
    setSigningOut(true)
    notify('')
    try {
      await api<void>('/auth/logout', { method: 'POST' })
      hasUnsavedDraft.current = false
      window.history.replaceState(null, '', window.location.pathname + window.location.search)
      setUser(null)
      notify('You have signed out.')
    } catch (cause) {
      notify(cause instanceof Error ? cause.message : 'Unable to sign out. Please try again.', undefined, 'error')
    } finally {
      setSigningOut(false)
    }
  }

  const snackbar = notification.message ? <Snackbar key={notification.id} message={notification.message} action={notification.action} tone={notification.tone} onDismiss={() => setNotification(current => ({ ...current, message: '', action: undefined }))} /> : null

  if (loading || loadError) return <main className="session-state">{loading ? <p role="status">Loading your session…</p> : <><p role="alert">{loadError}</p><button className="primary-button" onClick={() => setRetry(value => value + 1)}>Try again</button></>}</main>
  if (!user) return <><Login onLogin={(signedIn) => { setUser(signedIn); notify('') }} />{snackbar}</>

  return <div className="app-layout">
    <header className="app-header"><div className="account-menu"><div className="account-details"><span className="account-name">{user.first_name} {user.last_name}</span><span>{user.role === 'ADMINISTRATOR' ? 'Administrator' : 'Verifier'}</span></div><button className="sign-out-button" onClick={() => { if (hasUnsavedDraft.current) setDiscardSignOut(true); else void signOut() }} disabled={signingOut}>{signingOut ? 'Signing out…' : 'Sign out'}</button></div></header>
    <main className="workspace">
      {user.role === 'ADMINISTRATOR' ? <CreateUser onExpired={handleExpired} onNotify={notify} /> : <VerifierWorkspace user={user} onExpired={handleExpired} onDraftChange={handleDraftChange} onNotify={notifyWorkspace} onDismiss={dismissWorkspaceNotification} />}
    </main>
    {discardSignOut ? <DiscardChangesDialog onCancel={() => setDiscardSignOut(false)} onDiscard={() => { setDiscardSignOut(false); void signOut() }} /> : null}
    <footer className="app-footer">InTrac <span aria-hidden="true">/</span> Weapon Seizure Tracking</footer>
    {snackbar}
  </div>
}
