// @vitest-environment jsdom
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { AccountProvider } from './Account'
import { useAccount } from './accountContext'

function Probe() {
  const { account, status, signOut } = useAccount()
  return (
    <div>
      <span data-testid="status">{status}</span>
      <span data-testid="username">{account?.username ?? ''}</span>
      <button type="button" onClick={() => void signOut()}>sign out</button>
    </div>
  )
}

async function settle() {
  await act(async () => {
    await Promise.resolve()
    await Promise.resolve()
  })
}

describe('AccountProvider', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    document.body.replaceChildren()
  })

  it('loads Account state once and clears every consumer on sign out', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ id: 7, username: 'alster' }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: 'ok' }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      }))
    vi.stubGlobal('fetch', fetchMock)

    const container = document.createElement('div')
    document.body.append(container)
    const root = createRoot(container)
    await act(async () => root.render(<AccountProvider><Probe /><Probe /></AccountProvider>))
    await settle()

    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect([...container.querySelectorAll('[data-testid="status"]')].map((node) => node.textContent))
      .toEqual(['authenticated', 'authenticated'])
    expect(container.querySelectorAll('[data-testid="username"]')[1]?.textContent).toBe('alster')

    await act(async () => {
      ;(container.querySelector('button') as HTMLButtonElement).click()
      await Promise.resolve()
    })
    await settle()

    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(container.querySelector('[data-testid="status"]')?.textContent).toBe('anonymous')
    expect(container.querySelector('[data-testid="username"]')?.textContent).toBe('')
    await act(async () => root.unmount())
  })

  it('treats an unauthenticated status response as normal anonymous state', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: 'no session' }), {
      status: 401,
      headers: { 'content-type': 'application/json' },
    })))

    const container = document.createElement('div')
    document.body.append(container)
    const root = createRoot(container)
    await act(async () => root.render(<AccountProvider><Probe /></AccountProvider>))
    await settle()

    expect(container.querySelector('[data-testid="status"]')?.textContent).toBe('anonymous')
    await act(async () => root.unmount())
  })
})
