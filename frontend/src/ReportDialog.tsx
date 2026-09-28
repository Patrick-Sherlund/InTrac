import { useEffect, useId, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { ApiError } from './api'

type ReportLog = {
  id: number
  operation_name: string
  occurred_at: string
  status: 'OPEN' | 'REVIEWED'
  weapon_count: number
}

type ReportFile = { url: string; filename: string }
type ReportDates = { fromDate: string; toDate: string }
const dateFormat = new Intl.DateTimeFormat(undefined, { day: 'numeric', month: 'short', year: 'numeric' })
const localDate = (value: string) => {
  const date = new Date(value)
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}

function fullDateRange(logs: ReportLog[]): ReportDates {
  return logs.reduce((range, log) => {
    const date = localDate(log.occurred_at)
    return {
      fromDate: !range.fromDate || date < range.fromDate ? date : range.fromDate,
      toDate: !range.toDate || date > range.toDate ? date : range.toDate,
    }
  }, { fromDate: '', toDate: '' })
}

function validDate(value: unknown): value is string {
  if (value === '') return true
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false
  const date = new Date(`${value}T00:00:00Z`)
  return Number.isFinite(date.getTime()) && date.toISOString().slice(0, 10) === value
}

function initialDates(logs: ReportLog[], storageKey: string): ReportDates {
  try {
    const saved = JSON.parse(localStorage.getItem(storageKey) ?? 'null')
    if (validDate(saved?.fromDate) && validDate(saved?.toDate) && (!saved.fromDate || !saved.toDate || saved.fromDate <= saved.toDate)) {
      return { fromDate: saved.fromDate, toDate: saved.toDate }
    }
  } catch { /* Unavailable storage should not prevent report generation. */ }
  return fullDateRange(logs)
}

export default function ReportDialog({ logs, username, onCancel, onExpired, onGenerated }: {
  logs: ReportLog[]
  username: string
  onCancel: () => void
  onExpired: () => void
  onGenerated: (file: ReportFile) => void
}) {
  const storageKey = `intrac:report-dates:v1:${username.toLowerCase()}`
  const [{ fromDate, toDate }, setDates] = useState(() => initialDates(logs, storageKey))
  const [excludedLogIds, setExcludedLogIds] = useState<Set<number>>(() => new Set())
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const dialog = useRef<HTMLDialogElement>(null)
  const heading = useRef<HTMLHeadingElement>(null)
  const request = useRef<AbortController | null>(null)
  const titleId = useId()
  const descriptionId = useId()
  const fromId = useId()
  const toId = useId()
  const invalidDates = Boolean(fromDate && toDate && fromDate > toDate)
  const matchingLogs = invalidDates ? [] : logs.filter(log => {
    const date = localDate(log.occurred_at)
    return (!fromDate || date >= fromDate) && (!toDate || date <= toDate)
  })
  const selectedLogs = matchingLogs.filter(log => !excludedLogIds.has(log.id))
  const selectedRecords = selectedLogs.reduce((sum, log) => sum + log.weapon_count, 0)

  useEffect(() => {
    const element = dialog.current
    // Native autofocus must be set before opening to avoid activating the date picker.
    heading.current?.setAttribute('autofocus', '')
    element?.showModal()
    return () => { request.current?.abort(); element?.close() }
  }, [])

  function changeDates(dates: ReportDates) {
    setDates(dates)
    if (!validDate(dates.fromDate) || !validDate(dates.toDate) || (dates.fromDate && dates.toDate && dates.fromDate > dates.toDate)) return
    try { localStorage.setItem(storageKey, JSON.stringify(dates)) } catch { /* Keep the chosen dates usable when storage is unavailable. */ }
  }

  function useEntireDuration() {
    setDates(fullDateRange(logs))
    try { localStorage.removeItem(storageKey) } catch { /* The current dialog still resets without storage access. */ }
  }

  function selectLog(logId: number, selected: boolean) {
    setExcludedLogIds(previous => {
      const next = new Set(previous)
      if (selected) next.delete(logId)
      else next.add(logId)
      return next
    })
  }

  async function generate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (request.current || invalidDates || selectedLogs.length === 0) return
    const controller = new AbortController()
    request.current = controller
    setBusy(true)
    setError('')
    try {
      const response = await fetch('/api/logs/report.pdf', {
        method: 'POST', credentials: 'same-origin', signal: controller.signal,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ log_ids: selectedLogs.map(log => log.id) }),
      })
      if (!response.ok) {
        const body = await response.json().catch(() => null)
        throw new ApiError(typeof body?.detail === 'string' ? body.detail : 'Unable to generate the report. Please try again.', response.status)
      }
      if (!response.headers.get('Content-Type')?.includes('application/pdf')) throw new Error('Unable to generate the report. Please try again.')
      const blob = await response.blob()
      if (controller.signal.aborted) return
      const filename = /filename="?([^";]+)"?/.exec(response.headers.get('Content-Disposition') ?? '')?.[1] ?? 'intrac-operation-summary.pdf'
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = filename
      document.body.append(link)
      link.click()
      link.remove()
      onGenerated({ url, filename })
    } catch (cause) {
      if (controller.signal.aborted) return
      if (cause instanceof ApiError && cause.status === 401) onExpired()
      else setError(cause instanceof Error && !(cause instanceof TypeError) ? cause.message : 'Unable to generate the report. Check your connection and try again.')
    } finally {
      if (!controller.signal.aborted) setBusy(false)
      request.current = null
    }
  }

  return <dialog ref={dialog} className="report-dialog" aria-labelledby={titleId} aria-describedby={descriptionId} onCancel={event => { event.preventDefault(); if (!busy) onCancel() }}>
    <form onSubmit={generate} aria-busy={busy}>
      <div className="report-dialog-heading"><h2 ref={heading} id={titleId} tabIndex={-1}>Generate report</h2><p id={descriptionId}>Choose a date range and the operations to include. The PDF includes a summary followed by photos and their recorded details.</p></div>
      <div className="report-dialog-body">
        <div className="report-date-fields">
          <div className="field"><label htmlFor={fromId}>From date</label><input id={fromId} type="date" value={fromDate} max={toDate || undefined} onInput={event => changeDates({ fromDate: event.currentTarget.value, toDate })} disabled={busy} /></div>
          <div className="field"><label htmlFor={toId}>To date</label><input id={toId} type="date" value={toDate} min={fromDate || undefined} onInput={event => changeDates({ fromDate, toDate: event.currentTarget.value })} disabled={busy} /></div>
        </div>
        <div className="report-date-help"><button className="text-button" type="button" onClick={useEntireDuration} disabled={busy || logs.length === 0}>Entire duration</button></div>
        {invalidDates ? <p className="error-message" role="alert">The end date must be on or after the start date.</p> : null}
        {matchingLogs.length > 0 ? <ul className="report-log-list" aria-label="Operations to include">{matchingLogs.map(log => <li key={log.id}>
          <label className="report-log-entry">
            <input type="checkbox" checked={!excludedLogIds.has(log.id)} onChange={event => selectLog(log.id, event.currentTarget.checked)} disabled={busy} />
            <span><strong>{log.operation_name}</strong><span className="report-log-meta">{dateFormat.format(new Date(log.occurred_at))} · {log.weapon_count} {log.weapon_count === 1 ? 'record' : 'records'} · {log.status === 'REVIEWED' ? 'Verified' : 'Unverified'}</span></span>
          </label>
        </li>)}</ul> : <div className="report-selection-empty">{invalidDates ? 'Adjust the date range to include logs.' : logs.length === 0 ? 'Create a log before generating a report.' : 'No logs match these dates. Try a wider date range.'}</div>}
      </div>
      <div className="report-dialog-footer">
        {error ? <p className="error-message" role="alert">{error}</p> : null}
        <p className="report-selection-summary" role="status">{matchingLogs.length === 0 ? 'Choose a date range containing logs to continue.' : selectedLogs.length === 0 ? 'Select at least one operation to generate a report.' : `${selectedLogs.length} of ${matchingLogs.length} ${matchingLogs.length === 1 ? 'log' : 'logs'} selected · ${selectedRecords.toLocaleString()} weapon ${selectedRecords === 1 ? 'record' : 'records'}`}</p>
        <div className="report-dialog-actions"><button className="primary-button" type="submit" disabled={busy || invalidDates || selectedLogs.length === 0}>{busy ? 'Generating…' : 'Generate PDF'}</button><button className="secondary-button" type="button" onClick={onCancel} disabled={busy}>Cancel</button></div>
      </div>
    </form>
  </dialog>
}
