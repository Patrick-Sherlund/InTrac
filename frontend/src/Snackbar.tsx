import { useEffect, useEffectEvent, useState } from 'react'

export type SnackbarAction = { label: string; href: string; download?: string } | { label: string; onClick: () => void }
export type SnackbarTone = 'success' | 'info' | 'error'

export default function Snackbar({ message, onDismiss, action, tone = 'success' }: {
  message: string
  onDismiss: () => void
  action?: SnackbarAction
  tone?: SnackbarTone
}) {
  const [fading, setFading] = useState(false)
  const dismiss = useEffectEvent(onDismiss)

  useEffect(() => {
    setFading(false)
    const fadeTimer = window.setTimeout(() => setFading(true), 4750)
    const dismissTimer = window.setTimeout(() => dismiss(), 5000)
    return () => {
      window.clearTimeout(fadeTimer)
      window.clearTimeout(dismissTimer)
    }
  }, [message])

  return <div className={`snackbar snackbar-${tone}${fading ? ' snackbar-fading' : ''}`} role={tone === 'error' ? 'alert' : 'status'} aria-live={tone === 'error' ? 'assertive' : 'polite'} aria-atomic="true">
    <span>{message}</span>
    {action ? 'href' in action
      ? <a className="snackbar-action" href={action.href} download={action.download}>{action.label}</a>
      : <button className="snackbar-action" type="button" onClick={action.onClick}>{action.label}</button>
      : null}
  </div>
}
