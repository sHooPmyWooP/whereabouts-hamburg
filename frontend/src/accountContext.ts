import { createContext, useContext } from 'react'

export type Account = {
  id: number
  username: string
}

export type AuthenticationOptions = {
  onAuthenticated?: (account: Account) => void
  onClose?: () => void
}

export type AccountState = {
  account: Account | null
  status: 'loading' | 'anonymous' | 'authenticated'
  error: string | null
  signingOut: boolean
  openLogin: (options?: AuthenticationOptions) => void
  openRegistration: (options?: AuthenticationOptions) => void
  clearError: () => void
  signOut: () => Promise<boolean>
  markAnonymous: () => void
}

export const AccountContext = createContext<AccountState | null>(null)

/** Access the single browser Account truth. */
export function useAccount() {
  const value = useContext(AccountContext)
  if (!value) throw new Error('useAccount must be used inside AccountProvider')
  return value
}
