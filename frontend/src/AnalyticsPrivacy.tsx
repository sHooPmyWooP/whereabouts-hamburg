import { useEffect, useState } from 'react'
import { Trans, useTranslation } from 'react-i18next'
import { analyticsConsent, denyAnalytics, grantAnalytics } from './analytics'
import { apiFetch } from './api'

type AnalyticsPrivacyProps = {
  settingsOpen: boolean
  onSettingsClose: () => void
}

export function AnalyticsPrivacy({ settingsOpen, onSettingsClose }: AnalyticsPrivacyProps) {
  const { t } = useTranslation()
  const [consent, setConsent] = useState(analyticsConsent)
  const [privacyEmail, setPrivacyEmail] = useState('')

  useEffect(() => {
    apiFetch<{ privacy_contact_email: string }>('/api/analytics/config')
      .then((config) => setPrivacyEmail(config.privacy_contact_email))
      .catch(() => undefined)
  }, [])

  function allow() {
    grantAnalytics()
    setConsent('granted')
    onSettingsClose()
  }

  async function deny() {
    await denyAnalytics()
    setConsent('denied')
    onSettingsClose()
  }

  return (
    <>
      {consent === 'unset' ? (
        <aside className="analytics-consent" aria-label={t('privacy.choice')}>
          <strong>{t('privacy.helpTitle')}</strong>
          <p>{t('privacy.help')}</p>
          <div>
            <button type="button" onClick={allow}>{t('privacy.allowAnonymous')}</button>
            <button type="button" onClick={() => void deny()}>{t('privacy.noThanks')}</button>
          </div>
        </aside>
      ) : null}
      {settingsOpen ? (
        <div className="analytics-settings-backdrop" role="presentation" onMouseDown={onSettingsClose}>
          <section className="analytics-settings" role="dialog" aria-modal="true" aria-labelledby="analytics-settings-title" onMouseDown={(event) => event.stopPropagation()}>
            <h2 id="analytics-settings-title">{t('privacy.settings')}</h2>
            <p><Trans i18nKey="privacy.status" values={{ status: t(consent === 'granted' ? 'privacy.on' : 'privacy.off') }} components={{ strong: <strong /> }} /></p>
            <p>{t('privacy.retention')}</p>
            {privacyEmail ? <p>{t('privacy.requests')} <a href={`mailto:${privacyEmail}`}>{privacyEmail}</a></p> : null}
            <div>
              <button type="button" onClick={allow}>{t('privacy.allow')}</button>
              <button type="button" onClick={() => void deny()}>{t('privacy.turnOff')}</button>
              <button type="button" onClick={onSettingsClose}>{t('common.close')}</button>
            </div>
          </section>
        </div>
      ) : null}
    </>
  )
}
