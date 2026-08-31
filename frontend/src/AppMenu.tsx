import { useEffect, useRef, useState } from 'react'
import { BarChart3, Ellipsis, ShieldCheck } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { apiFetch } from './api'
import { activeLanguage, changeLanguage } from './i18n'

type AppMenuProps = {
  onAnalyticsSettings: () => void
  onNavigate: (path: string) => void
}

/** Keep secondary application destinations behind one consistent global control. */
export function AppMenu({ onAnalyticsSettings, onNavigate }: AppMenuProps) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const [isAdmin, setIsAdmin] = useState(false)
  const buttonRef = useRef<HTMLButtonElement>(null)
  const menuRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key !== 'Escape') return
      setOpen(false)
      buttonRef.current?.focus()
    }
    function handlePointerDown(event: PointerEvent) {
      const target = event.target
      if (target instanceof Node && !menuRef.current?.contains(target)) setOpen(false)
    }
    document.addEventListener('keydown', handleKeyDown)
    document.addEventListener('pointerdown', handlePointerDown)
    return () => {
      document.removeEventListener('keydown', handleKeyDown)
      document.removeEventListener('pointerdown', handlePointerDown)
    }
  }, [open])

  function toggleMenu() {
    const nextOpen = !open
    setOpen(nextOpen)
    if (!nextOpen) return
    apiFetch<{ is_admin: boolean }>('/api/admin/access')
      .then(() => setIsAdmin(true))
      .catch(() => setIsAdmin(false))
  }

  function choose(action: () => void) {
    setOpen(false)
    action()
  }

  const language = activeLanguage()
  return (
    <div className="app-menu" ref={menuRef}>
      <button ref={buttonRef} className="app-menu__trigger" type="button" aria-label={t('menu.moreOptions')} aria-haspopup="menu" aria-expanded={open} onClick={toggleMenu}>
        <Ellipsis size={21} aria-hidden="true" />
        <span>{t('menu.more')}</span>
      </button>
      {open ? (
        <div className="app-menu__popover" role="menu">
          <p>{t('menu.moreOptions')}</p>
          <div className="language-switch" role="group" aria-label={t('menu.language')}>
            <button type="button" aria-pressed={language === 'de'} title={t('menu.german')} onClick={() => void changeLanguage('de')}>
              <span aria-hidden="true">🇩🇪</span><span className="sr-only">{t('menu.german')}</span>
            </button>
            <button type="button" aria-pressed={language === 'en'} title={t('menu.english')} onClick={() => void changeLanguage('en')}>
              <span aria-hidden="true">🇬🇧</span><span className="sr-only">{t('menu.english')}</span>
            </button>
          </div>
          <button type="button" role="menuitem" onClick={() => choose(onAnalyticsSettings)}>
            <ShieldCheck size={18} aria-hidden="true" />
            <span><strong>{t('menu.privacy')}</strong><small>{t('menu.privacyHelp')}</small></span>
          </button>
          {isAdmin ? (
            <button type="button" role="menuitem" onClick={() => choose(() => onNavigate('/admin'))}>
              <BarChart3 size={18} aria-hidden="true" />
              <span><strong>{t('menu.admin')}</strong><small>{t('menu.adminHelp')}</small></span>
            </button>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}
