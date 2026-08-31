const CONSENT_KEY = 'whereabouts:analytics-consent'
const VISITOR_KEY = 'whereabouts:analytics-visitor'
const CREATED_KEY = 'whereabouts:analytics-created'
const THIRTEEN_MONTHS_MS = 397 * 24 * 60 * 60 * 1000

export type AnalyticsConsent = 'granted' | 'denied' | 'unset'

type EventProperties = Record<string, string | number | boolean>

function privacySignalEnabled() {
  const navigatorWithPrivacy = navigator as Navigator & {
    globalPrivacyControl?: boolean
    doNotTrack?: string | null
  }
  return navigatorWithPrivacy.globalPrivacyControl === true
    || navigatorWithPrivacy.doNotTrack === '1'
}

export function analyticsConsent(): AnalyticsConsent {
  const stored = localStorage.getItem(CONSENT_KEY)
  if (stored === 'granted' || stored === 'denied') return stored
  return privacySignalEnabled() ? 'denied' : 'unset'
}

function visitorId() {
  const created = Number(localStorage.getItem(CREATED_KEY) ?? 0)
  if (created && Date.now() - created >= THIRTEEN_MONTHS_MS) {
    localStorage.removeItem(VISITOR_KEY)
    localStorage.removeItem(CREATED_KEY)
  }
  const existing = localStorage.getItem(VISITOR_KEY)
  if (existing) return existing
  const createdId = crypto.randomUUID()
  localStorage.setItem(VISITOR_KEY, createdId)
  localStorage.setItem(CREATED_KEY, String(Date.now()))
  return createdId
}

function deviceClass() {
  if (window.matchMedia('(max-width: 700px)').matches) return 'mobile'
  if (window.matchMedia('(max-width: 1100px)').matches) return 'tablet'
  return 'desktop'
}

export function firstTouchContext(): EventProperties {
  const search = new URLSearchParams(window.location.search)
  return {
    device_class: deviceClass(),
    browser_language: navigator.language.slice(0, 16),
    referrer_domain: document.referrer ? new URL(document.referrer).hostname : '',
    ...(search.get('utm_source') ? { utm_source: search.get('utm_source')! } : {}),
    ...(search.get('utm_medium') ? { utm_medium: search.get('utm_medium')! } : {}),
    ...(search.get('utm_campaign') ? { utm_campaign: search.get('utm_campaign')! } : {}),
  }
}

export function track(eventType: string, properties: EventProperties = {}) {
  if (analyticsConsent() !== 'granted') return
  const body = JSON.stringify({
    event_id: crypto.randomUUID(),
    visitor_id: visitorId(),
    event_type: eventType,
    properties,
  })
  void fetch('/api/analytics/events', {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body,
    keepalive: true,
  }).catch(() => undefined)
}

export function grantAnalytics() {
  localStorage.setItem(CONSENT_KEY, 'granted')
  track('app_opened', firstTouchContext())
}

export async function denyAnalytics() {
  const currentVisitor = localStorage.getItem(VISITOR_KEY)
  localStorage.setItem(CONSENT_KEY, 'denied')
  localStorage.removeItem(VISITOR_KEY)
  localStorage.removeItem(CREATED_KEY)
  if (!currentVisitor) return
  try {
    await fetch('/api/analytics/forget', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ visitor_id: currentVisitor }),
      keepalive: true,
    })
  } catch {
    // Analytics preferences never interfere with gameplay.
  }
}
