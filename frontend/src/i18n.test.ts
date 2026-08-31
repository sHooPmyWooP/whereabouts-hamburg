import { afterEach, describe, expect, it } from 'vitest'
import i18n, { changeLanguage, detectLanguage, LANGUAGE_STORAGE_KEY, resources } from './i18n'
import { ApiError, apiErrorMessage } from './api'

const storage = (value: string | null): Pick<Storage, 'getItem'> => ({ getItem: () => value })

afterEach(async () => {
  localStorage.clear()
  await i18n.changeLanguage('en')
})

describe('language selection', () => {
  it('prefers a saved supported language', () => {
    expect(detectLanguage(storage('en'), ['de-DE'])).toBe('en')
    expect(detectLanguage(storage('de'), ['en-US'])).toBe('de')
  })

  it('uses German browser preferences and otherwise falls back to English', () => {
    expect(detectLanguage(storage(null), ['fr', 'de-AT'])).toBe('de')
    expect(detectLanguage(storage(null), ['fr-FR'])).toBe('en')
  })

  it('persists runtime changes and updates the document language', async () => {
    document.head.innerHTML = '<meta name="description" content="">'
    await changeLanguage('de')
    expect(localStorage.getItem(LANGUAGE_STORAGE_KEY)).toBe('de')
    expect(document.documentElement.lang).toBe('de')
    expect(document.querySelector('meta[name="description"]')?.getAttribute('content')).toBe(resources.de.translation['meta.description'])
  })
})

describe('translation resources', () => {
  it('keeps locale keys in parity', () => {
    expect(Object.keys(resources.de.translation).sort()).toEqual(Object.keys(resources.en.translation).sort())
  })

  it('pluralizes guesses and formats locale-sensitive numbers', async () => {
    await i18n.changeLanguage('en')
    expect(i18n.t('daily.foundInGuesses', { solved: 1, total: 5, count: 1 })).toContain('1 Guess')
    expect(new Intl.NumberFormat(i18n.language, { maximumFractionDigits: 1 }).format(1.5)).toBe('1.5')
    await i18n.changeLanguage('de')
    expect(i18n.t('daily.foundInGuesses', { solved: 1, total: 5, count: 2 })).toContain('2 Tipps')
    expect(i18n.t('daily.resultScoreGaveUp', {
      solved: 3,
      total: 5,
      spent: 8,
      budget: 10,
      count: 8,
    })).toBe('3/5 Pins · Aufgegeben nach 8/10 Tipps')
    expect(new Intl.NumberFormat(i18n.language, { maximumFractionDigits: 1 }).format(1.5)).toBe('1,5')
  })

  it('uses error codes and a localized fallback without exposing diagnostics', async () => {
    await i18n.changeLanguage('de')
    const known = new ApiError(401, 'English diagnostic', 'auth_invalid_credentials')
    const unknown = new ApiError(500, 'Secret English diagnostic', 'unknown.code')
    expect(apiErrorMessage(known, i18n.t.bind(i18n), 'auth.loginError')).toBe('Benutzername oder Passwort ist falsch.')
    expect(apiErrorMessage(unknown, i18n.t.bind(i18n), 'auth.loginError')).toBe('Anmelden fehlgeschlagen.')
  })
})
