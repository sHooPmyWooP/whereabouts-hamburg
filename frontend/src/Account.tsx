import {
  useCallback,
  useEffect,
  useRef,
  useState,
} from 'react'
import type { ReactNode } from 'react'
import { AccountContext } from './accountContext'
import type { Account, AccountState, AuthenticationOptions } from './accountContext'
import { apiErrorMessage, ApiError, apiFetch } from './api'
import { track } from './analytics'
import i18n from './i18n'
import { LoginDialog } from './LoginDialog'
import { RegisterDialog } from './RegisterDialog'

type Credentials = {
  username: string
  password: string
}

/** Own the browser Account session, authentication transport, and dialogs. */
export function AccountProvider({ children }: { children: ReactNode }) {
  const [account, setAccount] = useState<Account | null>(null)
  const [status, setStatus] = useState<AccountState['status']>('loading')
  const [error, setError] = useState<string | null>(null)
  const [signingOut, setSigningOut] = useState(false)
  const [loginOpen, setLoginOpen] = useState(false)
  const [registrationOpen, setRegistrationOpen] = useState(false)
  const loginOptions = useRef<AuthenticationOptions>({})
  const registrationOptions = useRef<AuthenticationOptions>({})

  useEffect(() => {
    let cancelled = false
    apiFetch<Account>('/api/auth/me')
      .then((currentAccount) => {
        if (cancelled) return
        setAccount(currentAccount)
        setStatus('authenticated')
      })
      .catch((reason: unknown) => {
        if (cancelled) return
        setAccount(null)
        setStatus('anonymous')
        if (!(reason instanceof ApiError && reason.status === 401)) {
          setError(i18n.t('common.accountStatusError'))
        }
      })
    return () => {
      cancelled = true
    }
  }, [])

  function openLogin(options: AuthenticationOptions = {}) {
    loginOptions.current = options
    setError(null)
    setRegistrationOpen(false)
    setLoginOpen(true)
  }

  function openRegistration(options: AuthenticationOptions = {}) {
    registrationOptions.current = options
    setError(null)
    setLoginOpen(false)
    setRegistrationOpen(true)
  }

  function closeLogin() {
    setLoginOpen(false)
    const onClose = loginOptions.current.onClose
    loginOptions.current = {}
    onClose?.()
  }

  function closeRegistration() {
    setRegistrationOpen(false)
    const onClose = registrationOptions.current.onClose
    registrationOptions.current = {}
    onClose?.()
  }

  async function authenticate(
    mode: 'login' | 'registered',
    credentials: Credentials,
    options: AuthenticationOptions,
  ) {
    const authenticatedAccount = await apiFetch<Account>(
      mode === 'login' ? '/api/auth/login' : '/api/auth/register',
      {
        method: 'POST',
        body: JSON.stringify(credentials),
      },
    )
    setAccount(authenticatedAccount)
    setStatus('authenticated')
    setError(null)
    track('account_authenticated', { mode })
    options.onAuthenticated?.(authenticatedAccount)
  }

  async function signOut() {
    if (signingOut) return false
    setSigningOut(true)
    setError(null)
    try {
      await apiFetch<{ status: string }>('/api/auth/logout', { method: 'POST' })
      setAccount(null)
      setStatus('anonymous')
      return true
    } catch (reason) {
      setError(apiErrorMessage(reason, i18n.t.bind(i18n), 'common.logoutError'))
      return false
    } finally {
      setSigningOut(false)
    }
  }

  const markAnonymous = useCallback(() => {
    setAccount(null)
    setStatus('anonymous')
  }, [])

  return (
    <AccountContext.Provider
      value={{
        account,
        status,
        error,
        signingOut,
        openLogin,
        openRegistration,
        clearError: () => setError(null),
        signOut,
        markAnonymous,
      }}
    >
      {children}
      <LoginDialog
        open={loginOpen}
        onClose={closeLogin}
        onSubmit={(credentials) => authenticate('login', credentials, loginOptions.current)}
      />
      <RegisterDialog
        open={registrationOpen}
        onClose={closeRegistration}
        onSubmit={(credentials) => authenticate('registered', credentials, registrationOptions.current)}
      />
    </AccountContext.Provider>
  )
}
