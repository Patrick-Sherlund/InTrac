import { useCallback, useEffect, useId, useRef, useState } from 'react'
import type { ChangeEvent, FormEvent } from 'react'
import { api, ApiError } from './api'
import type { User } from './api'
import ReportDialog from './ReportDialog'
import type { SnackbarAction } from './Snackbar'
import './verifier.css'

type Weapon = {
  id: number
  log_id: number
  item_type: string
  name_model: string | null
  serial_numbers: string[]
  quantity: number
  created_at: string
  photo_url: string | null
}

type LogSummary = {
  id: number
  operation_name: string
  occurred_at: string
  created_at: string
  operator_name: string
  location_name: string
  latitude: number | null
  longitude: number | null
  location_accuracy: number | null
  weapon_count: number
  total_quantity: number
  status: 'OPEN' | 'REVIEWED'
  reviewed_at: string | null
  reviewed_by_name: string | null
}

type LogDetail = LogSummary & { weapons: Weapon[] }
type Coordinates = { latitude: number; longitude: number; location_accuracy: number }
type FormProps = { onCancel: () => void; onExpired: () => void; onDirty: (dirty: boolean) => void }

const dateFormat = new Intl.DateTimeFormat(undefined, { day: 'numeric', month: 'short', year: 'numeric' })
const timeFormat = new Intl.DateTimeFormat(undefined, { hour: 'numeric', minute: '2-digit', timeZoneName: 'short' })
const fullDate = (value: string) => `${dateFormat.format(new Date(value))}, ${timeFormat.format(new Date(value))}`
const currentRoute = () => /^#logs(?:\/new|\/[1-9]\d*(?:\/weapons\/new|\/review)?)?$/.test(window.location.hash) ? window.location.hash : '#logs'

export function DiscardChangesDialog({ onCancel, onDiscard }: { onCancel: () => void; onDiscard: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null)
  const titleId = useId()
  const descriptionId = useId()

  useEffect(() => {
    const element = dialog.current
    element?.showModal()
    return () => element?.close()
  }, [])

  return <dialog ref={dialog} className="discard-dialog" aria-labelledby={titleId} aria-describedby={descriptionId} onCancel={event => { event.preventDefault(); onCancel() }}>
    <h2 id={titleId}>Discard unsaved changes?</h2>
    <p id={descriptionId}>Your entries have not been saved. Go back to keep them, or discard them to continue.</p>
    <div className="discard-dialog-actions"><button className="secondary-button" type="button" autoFocus onClick={onCancel}>Go back</button><button className="discard-button" type="button" onClick={onDiscard}>Discard changes</button></div>
  </dialog>
}

function NewLogForm({ onCancel, onExpired, onDirty, onCreated }: FormProps & { onCreated: (log: LogDetail) => void }) {
  const [operationName, setOperationName] = useState('')
  const [operatorName, setOperatorName] = useState('')
  const [initialDateTime] = useState(() => {
    const now = new Date()
    return {
      date: `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`,
      time: `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`,
    }
  })
  const [occurredDate, setOccurredDate] = useState(initialDateTime.date)
  const occurredTime = initialDateTime.time
  const [locationName, setLocationName] = useState('')
  const [coordinates, setCoordinates] = useState<Coordinates | null>(null)
  const [locating, setLocating] = useState(false)
  const [tryingApproximate, setTryingApproximate] = useState(false)
  const [locationError, setLocationError] = useState('')
  const [manual, setManual] = useState(false)
  const [manualEdited, setManualEdited] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const locationRequest = useRef(0)
  const browserLocationAvailable = window.isSecureContext && Boolean(navigator.geolocation)

  const locate = useCallback(() => {
    const request = ++locationRequest.current
    setLocationError('')
    setTryingApproximate(false)
    if (!window.isSecureContext) {
      setLocating(false)
      setLocationError('Automatic location needs a trusted HTTPS connection. Open InTrac using its HTTPS address on this device, or enter the location below.')
      setManual(true)
      return
    }
    if (!navigator.geolocation) {
      setLocating(false)
      setLocationError('This browser does not support location access. Enter the operation location below.')
      setManual(true)
      return
    }

    function failed(code: number) {
      if (request !== locationRequest.current) return
      setLocating(false)
      setManual(true)
      setLocationError(code === 1
        ? 'Location permission is blocked. Allow location for this site and enable Location Services for your browser in device settings, then try again. You can also enter the location below.'
        : code === 3
          ? 'Finding your location timed out. Try again with a clearer signal, or enter the location below.'
          : 'Your device could not provide a location. Check that Location Services are on, then try again or enter the location below.')
    }

    function requestPosition(highAccuracy: boolean) {
      try {
        navigator.geolocation.getCurrentPosition(position => {
          if (request !== locationRequest.current) return
          const { latitude, longitude, accuracy } = position.coords
          setCoordinates({ latitude, longitude, location_accuracy: accuracy })
          setLocationName(`${latitude.toFixed(6)}, ${longitude.toFixed(6)}`)
          setManual(false)
          setManualEdited(false)
          setLocating(false)
        }, cause => {
          if (request !== locationRequest.current) return
          if (highAccuracy && cause.code !== 1) {
            setTryingApproximate(true)
            requestPosition(false)
          } else failed(cause.code)
        }, { enableHighAccuracy: highAccuracy, timeout: highAccuracy ? 15000 : 10000, maximumAge: 0 })
      } catch (cause) {
        failed(cause instanceof DOMException && cause.name === 'SecurityError' ? 1 : 2)
      }
    }

    setLocating(true)
    requestPosition(true)
  }, [])

  useEffect(() => {
    locate()
    return () => { locationRequest.current += 1 }
  }, [locate])

  const dateTimeChanged = occurredDate !== initialDateTime.date
  useEffect(() => { onDirty(Boolean(operationName || operatorName || manualEdited || dateTimeChanged)) }, [operationName, operatorName, manualEdited, dateTimeChanged, onDirty])

  function enterManually() {
    locationRequest.current += 1
    setLocating(false)
    setManual(true)
    setLocationError('')
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!operationName.trim() || !locationName.trim()) {
      setError('Enter an operation name and location to create this log.')
      return
    }
    const occurredAt = new Date(`${occurredDate}T${occurredTime}`)
    const [year, month, day] = occurredDate.split('-').map(Number)
    if (!Number.isFinite(occurredAt.getTime()) || occurredAt.getFullYear() !== year
      || occurredAt.getMonth() + 1 !== month || occurredAt.getDate() !== day) {
      setError('Enter a valid operation date.')
      return
    }
    setBusy(true)
    setError('')
    try {
      const log = await api<LogDetail>('/logs', {
        method: 'POST',
        body: JSON.stringify({ operation_name: operationName.trim(), operator_name: operatorName.trim(), occurred_at: occurredAt.toISOString(),
          location_name: locationName.trim(), latitude: coordinates?.latitude ?? null,
          longitude: coordinates?.longitude ?? null, location_accuracy: coordinates?.location_accuracy ?? null }),
      })
      onDirty(false)
      onCreated(log)
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 401) onExpired()
      else setError(cause instanceof Error ? cause.message : 'Unable to create the log. Please try again.')
    } finally { setBusy(false) }
  }

  return <>
    <button className="back-link" type="button" onClick={onCancel} disabled={busy}><span aria-hidden="true">‹</span> Logs</button>
    <div className="page-heading"><h1 tabIndex={-1}>Create log</h1><p>Start an operation, then record its weapons.</p></div>
    <form className="verifier-panel verifier-form" onSubmit={save} aria-label="Create log" aria-busy={busy}>
      <div className="field"><label htmlFor="operation-name">Operation name</label><input id="operation-name" name="operation_name" value={operationName} onChange={event => setOperationName(event.target.value)} required maxLength={160} autoComplete="off" disabled={busy} placeholder="Enter the operation name" /></div>
      <div className="field"><label htmlFor="operator-name">LAF Soldier Name <span className="optional-label">Optional</span></label><input id="operator-name" name="operator_name" value={operatorName} onChange={event => setOperatorName(event.target.value)} maxLength={160} autoComplete="off" disabled={busy} placeholder="Enter the LAF soldier’s name" /></div>
      <div className="field location-field">
        <div className="field-label-row"><label htmlFor="log-location">Location</label>{coordinates ? <span className="capture-tag">Browser location</span> : null}</div>
        {locating ? <div className="location-status" role="status"><span className="location-dot" aria-hidden="true" /><div><strong>{tryingApproximate ? 'Trying an approximate location…' : 'Finding your location…'}</strong><p>{tryingApproximate ? 'A precise fix is unavailable. Your device may still provide a broader location.' : 'Allow location access when your browser asks. You can also enter it manually.'}</p></div></div> : null}
        {locationError ? <p className="location-warning" role="status">{locationError}</p> : null}
        <input id="log-location" name="location_name" value={locationName} onChange={event => { locationRequest.current += 1; setLocating(false); setCoordinates(null); setLocationName(event.target.value); setManualEdited(true) }} required maxLength={250} readOnly={!manual} disabled={busy} autoComplete="off" placeholder={manual ? 'Enter the address, site, or coordinates' : 'Waiting for browser location'} />
        <div className="location-actions">{browserLocationAvailable && !locating ? <button type="button" className="text-button" onClick={locate} disabled={busy}>{coordinates ? 'Refresh browser location' : 'Use browser location'}</button> : null}{!manual || locating ? <button type="button" className="text-button" onClick={enterManually} disabled={busy}>{manual ? 'Keep entered location' : 'Enter location manually'}</button> : null}</div>
      </div>
      <div className="date-time-fields">
        <div className="field"><label htmlFor="log-date">Date</label><input id="log-date" name="occurred_date" type="date" value={occurredDate} onInput={event => setOccurredDate(event.currentTarget.value)} required disabled={busy} /></div>
      </div>
      {error ? <p className="error-message" role="alert">{error}</p> : null}
      <div className="verifier-form-actions create-log-actions"><button className="primary-button" type="submit" disabled={busy || locating || !locationName.trim()}>{busy ? 'Creating log…' : 'Create log'}</button><button className="secondary-button" type="button" onClick={onCancel} disabled={busy}>Cancel</button></div>
    </form>
  </>
}

function WeaponForm({ log, onCancel, onExpired, onDirty, onSaved }: FormProps & { log: LogDetail; onSaved: (weapon: Weapon) => void }) {
  const [itemType, setItemType] = useState('')
  const [customType, setCustomType] = useState('')
  const customTypeInput = useRef<HTMLInputElement>(null)
  const [model, setModel] = useState('')
  const [serialRows, setSerialRows] = useState([{ id: 0, value: '' }])
  const nextSerialId = useRef(1)
  const serialInputs = useRef(new Map<number, HTMLInputElement>())
  const pendingSerialFocus = useRef<number | null>(null)
  const [quantity, setQuantity] = useState('1')
  const [photo, setPhoto] = useState<File | null>(null)
  const [preview, setPreview] = useState('')
  const [photoError, setPhotoError] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [closed, setClosed] = useState(false)
  const locked = busy || closed
  const photoInput = useRef<HTMLInputElement>(null)
  const serialNumbers = serialRows.map(row => row.value.trim()).filter(Boolean)
  const seenSerials = new Set<string>()
  let duplicateSerial = ''
  for (const serial of serialNumbers) {
    const normalized = serial.toLowerCase()
    if (seenSerials.has(normalized)) { duplicateSerial = normalized; break }
    seenSerials.add(normalized)
  }
  const validQuantity = Number.isInteger(Number(quantity)) && Number(quantity) >= 1 && Number(quantity) <= 100000
  const tooManySerials = validQuantity && serialNumbers.length > Number(quantity)
  const serialError = duplicateSerial ? 'Each serial number must be unique within this entry.'
    : tooManySerials ? 'There are more serial numbers than units. Increase the quantity or remove extra serial numbers.' : ''
  const dirty = Boolean(itemType || model || serialRows.some(row => row.value) || quantity !== '1' || photo)

  useEffect(() => { onDirty(dirty) }, [dirty, onDirty])
  useEffect(() => {
    if (pendingSerialFocus.current !== null) {
      serialInputs.current.get(pendingSerialFocus.current)?.focus()
      pendingSerialFocus.current = null
    }
  }, [serialRows])
  useEffect(() => {
    if (!photo) { setPreview(''); return }
    const url = URL.createObjectURL(photo)
    setPreview(url)
    return () => URL.revokeObjectURL(url)
  }, [photo])

  function addSerial() {
    const id = nextSerialId.current++
    pendingSerialFocus.current = id
    setSerialRows(rows => [...rows, { id, value: '' }])
  }

  function removeSerial(id: number) {
    const index = serialRows.findIndex(row => row.id === id)
    const remaining = serialRows.filter(row => row.id !== id)
    pendingSerialFocus.current = remaining[Math.min(index, remaining.length - 1)]?.id ?? id
    setSerialRows(remaining.length ? remaining : [{ id, value: '' }])
  }

  function choosePhoto(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    if (!file) return
    setPhotoError('')
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) {
      setPhotoError('Choose a JPEG, PNG, or WebP image.')
      event.target.value = ''
      return
    }
    if (file.size > 8 * 1024 * 1024) {
      setPhotoError('This photo is too large. Choose an image smaller than 8 MB.')
      event.target.value = ''
      return
    }
    setPhoto(file)
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (locked) return
    if (!itemType.trim()) { setError('Select an item type.'); return }
    const savedItemType = (itemType === 'Other' ? customType : itemType).trim()
    if (!savedItemType) {
      setError('Enter a custom weapon type.')
      customTypeInput.current?.focus()
      return
    }
    if (!validQuantity) {
      setError('Enter a whole-number quantity between 1 and 100,000.')
      return
    }
    if (serialError) {
      const invalidRow = duplicateSerial
        ? serialRows.find(row => row.value.trim().toLowerCase() === duplicateSerial)
        : serialRows.find(row => row.value.trim())
      if (invalidRow) serialInputs.current.get(invalidRow.id)?.focus()
      return
    }
    const data = new FormData()
    data.set('item_type', savedItemType)
    data.set('name_model', model.trim())
    data.set('serial_numbers', JSON.stringify(serialNumbers))
    data.set('quantity', String(Number(quantity)))
    if (photo) data.set('photo', photo)
    setBusy(true)
    setError('')
    try {
      const weapon = await api<Weapon>(`/logs/${log.id}/weapons`, { method: 'POST', body: data })
      onDirty(false)
      onSaved(weapon)
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 401) onExpired()
      else {
        setError(cause instanceof Error ? cause.message : 'Unable to save this weapon. Your entries are still here; please try again.')
        if (cause instanceof ApiError && cause.status === 409) setClosed(true)
      }
    } finally { setBusy(false) }
  }

  return <>
    <button className="back-link" type="button" onClick={onCancel} disabled={busy}><span aria-hidden="true">‹</span> Back to log</button>
    <div className="page-heading weapon-page-heading"><p className="operation-context">{log.operation_name}</p><h1 tabIndex={-1}>Add weapon</h1></div>
    <form className="verifier-panel verifier-form" onSubmit={save} aria-label="Add weapon" aria-busy={busy}>
      <div className="field"><label htmlFor="weapon-type">Item type</label><select id="weapon-type" name="item_type" value={itemType} onChange={event => setItemType(event.target.value)} required disabled={locked}><option value="" disabled>Select a category</option><option value="Handgun">Handgun</option><option value="Rifle">Rifle</option><option value="Shotgun">Shotgun</option><option value="Machine gun">Machine gun</option><option value="Ammunition">Ammunition</option><option value="Other">Other / custom</option></select></div>
      {itemType === 'Other' ? <div className="field"><label htmlFor="weapon-custom-type">Custom weapon type</label><input ref={customTypeInput} id="weapon-custom-type" name="custom_item_type" value={customType} onChange={event => setCustomType(event.target.value)} required maxLength={80} autoComplete="off" disabled={locked} /></div> : null}
      <div className="field"><label htmlFor="weapon-model">Item name / model <span className="optional-label">Optional</span></label><input id="weapon-model" name="name_model" value={model} onChange={event => setModel(event.target.value)} maxLength={160} disabled={locked} autoComplete="off" /></div>
      <div className="field"><label htmlFor="weapon-quantity">Quantity</label><input id="weapon-quantity" name="quantity" type="number" inputMode="numeric" value={quantity} onChange={event => setQuantity(event.target.value)} min={1} max={100000} step={1} required disabled={locked} /></div>
      <fieldset className="serial-fields" disabled={locked}>
        <legend>Serial numbers <span className="optional-label">Optional</span></legend>
        <div className="serial-rows">{serialRows.map((row, index) => <div className="serial-row" key={row.id}>
          <div className="field"><label htmlFor={`weapon-serial-${row.id}`}>Serial number {index + 1}</label><input ref={element => { if (element) serialInputs.current.set(row.id, element); else serialInputs.current.delete(row.id) }} id={`weapon-serial-${row.id}`} name="serial_numbers" value={row.value} onChange={event => setSerialRows(rows => rows.map(current => current.id === row.id ? { ...current, value: event.target.value } : current))} maxLength={160} autoComplete="off" autoCapitalize="none" spellCheck={false} aria-invalid={Boolean(duplicateSerial && row.value.trim().toLowerCase() === duplicateSerial) || tooManySerials} aria-describedby={serialError ? 'serial-error' : undefined} /></div>
          <button className="secondary-button serial-remove" type="button" onClick={() => removeSerial(row.id)} disabled={serialRows.length === 1 && !row.value} aria-label={`Remove serial number ${index + 1}`}>Remove</button>
        </div>)}</div>
        <button className="text-button serial-add" type="button" onClick={addSerial} disabled={serialRows.length >= 100000}><span aria-hidden="true">＋ </span>Add serial number</button>
        {serialError ? <p className="serial-error" id="serial-error" role="alert">{serialError}</p> : null}
      </fieldset>
      <div className="field photo-field"><label htmlFor="weapon-photo">Photo <span className="optional-label">Optional</span></label><input ref={photoInput} id="weapon-photo" name="photo" type="file" accept="image/jpeg,image/png,image/webp" onChange={choosePhoto} disabled={locked} />{photoError ? <p className="photo-error" role="alert">{photoError}</p> : null}{photo && preview ? <div className="photo-preview"><img src={preview} alt="Selected weapon photo preview" /><div><p>{photo.name}</p><button className="text-button" type="button" disabled={locked} onClick={() => { setPhoto(null); setPhotoError(''); if (photoInput.current) photoInput.current.value = '' }}>Remove photo</button></div></div> : null}</div>
      {error ? <div><p className="error-message" role="alert">{error}</p>{closed ? <><p className="field-hint">Your unsaved entries have not been added.</p><button className="text-button" type="button" onClick={onCancel}>View verified log</button></> : null}</div> : null}
      <div className="verifier-form-actions weapon-form-actions"><button className="primary-button" type="submit" disabled={locked}>{busy ? 'Saving weapon…' : 'Save weapon'}</button><button className="secondary-button" type="button" onClick={onCancel} disabled={busy}>Cancel</button></div>
    </form>
  </>
}

function LogStatus({ status }: { status: LogSummary['status'] }) {
  return <span className={`log-status ${status === 'REVIEWED' ? 'log-status-reviewed' : ''}`}>{status === 'REVIEWED' ? 'Verified' : 'Unverified'}</span>
}

function LogView({ log, onAdd, onReview, reviewing = false }: { log: LogDetail; onAdd?: () => void; onReview?: () => void; reviewing?: boolean }) {
  const canAdd = log.status === 'OPEN' && onAdd
  return <>
    <div className="page-heading log-heading">
      <div>
        <div className="log-title-row"><h1 tabIndex={-1}>{reviewing ? 'Verify log' : log.operation_name}</h1><LogStatus status={log.status} /></div>
        {reviewing ? <p className="review-operation-name">{log.operation_name}</p> : null}
        <dl className="operation-summary" aria-label="Operation details">
          <div><dt>Date and time</dt><dd><time dateTime={log.occurred_at}>{fullDate(log.occurred_at)}</time></dd></div>
          <div><dt>Location</dt><dd>{log.location_name}</dd></div>
          <div><dt>LAF Soldier Name</dt><dd>{log.operator_name || 'Not recorded'}</dd></div>
        </dl>
        {log.status === 'REVIEWED' ? <p className="verification-details">Verified by <strong>{log.reviewed_by_name}</strong>{log.reviewed_at ? <> on <time dateTime={log.reviewed_at}>{fullDate(log.reviewed_at)}</time></> : null}. Closed and read-only.</p> : null}
      </div>
      {onReview && log.status === 'OPEN' ? <button className="secondary-button verify-log-button" type="button" onClick={onReview}>Verify log</button> : null}
    </div>
    {reviewing ? <p className="review-intro">Check the operation details and every weapon below, then confirm the log is accurate to close it.</p> : null}
    <section className="weapons-section" aria-labelledby="weapons-title"><div className="weapons-heading"><div><h2 id="weapons-title">Weapons <span className="count-badge">{log.weapon_count}</span></h2>{log.weapon_count > 0 ? <p>{log.total_quantity.toLocaleString()} total {log.total_quantity === 1 ? 'unit' : 'units'}</p> : null}</div></div>
      {log.weapons.length === 0 ? <div className="empty-state weapon-empty"><h3>No weapons recorded</h3><p>{canAdd ? 'Use the green + button to add a weapon.' : 'This log contains no weapon records.'}</p></div> : <ol className="weapon-list">{log.weapons.map((weapon, index) => <li key={weapon.id} className="weapon-record"><div className="weapon-record-heading"><span className="weapon-index" aria-label={`Weapon ${index + 1}`}>{String(index + 1).padStart(2, '0')}</span><div><h3>{weapon.item_type}</h3>{weapon.name_model ? <p>{weapon.name_model}</p> : null}</div><span className="weapon-quantity">Qty {weapon.quantity.toLocaleString()}</span></div><div className="weapon-record-body"><dl><div><dt>Serial numbers</dt><dd>{weapon.serial_numbers.length ? <ul className="saved-serials">{weapon.serial_numbers.map((serial, serialIndex) => <li key={serialIndex}>{serial}</li>)}</ul> : 'Not recorded'}<p className="serial-coverage">{weapon.serial_numbers.length.toLocaleString()} of {weapon.quantity.toLocaleString()} recorded</p></dd></div></dl>{weapon.photo_url ? <a className="weapon-photo-link" href={weapon.photo_url} target="_blank" rel="noreferrer" aria-label={`Open photo of ${weapon.name_model || weapon.item_type} in a new tab`}><img src={weapon.photo_url} loading="lazy" alt={weapon.name_model || weapon.item_type} /><span>View photo</span></a> : null}</div></li>)}</ol>}
    </section>
    {canAdd ? <button className="primary-button add-weapon-button" type="button" onClick={onAdd} aria-label="Add weapon" title="Add weapon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><path d="M12 5v14M5 12h14" /></svg></button> : null}
  </>
}

function ReviewLogForm({ log, user, onCancel, onExpired, onReload, onReviewed }: { log: LogDetail; user: User; onCancel: () => void; onExpired: () => void; onReload: () => void; onReviewed: () => void }) {
  const [confirmed, setConfirmed] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [needsReload, setNeedsReload] = useState(false)

  async function review(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!confirmed || busy || needsReload) return
    setBusy(true)
    setError('')
    try {
      await api<LogDetail>(`/logs/${log.id}/review`, { method: 'POST', body: JSON.stringify({ confirmed: true, expected_weapon_count: log.weapon_count }) })
      onReviewed()
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 401) onExpired()
      else {
        setError(cause instanceof Error ? cause.message : 'Unable to verify this log. Please try again.')
        if (cause instanceof ApiError && cause.status === 409) {
          setConfirmed(false)
          setNeedsReload(true)
        }
      }
    } finally { setBusy(false) }
  }

  return <>
    <button className="back-link" type="button" onClick={onCancel} disabled={busy}><span aria-hidden="true">‹</span> Back to log</button>
    <LogView log={log} reviewing />
    <form className="verifier-panel review-confirmation" onSubmit={review} aria-label="Confirm log verification" aria-busy={busy}>
      <h2>Confirm and close</h2>
      <p id="review-consequence">Verifying this log closes it. You will still be able to view the log and photos, but cannot add more weapons.</p>
      <label className="review-attestation" htmlFor="review-confirmed"><input id="review-confirmed" type="checkbox" checked={confirmed} onChange={event => setConfirmed(event.target.checked)} disabled={busy || needsReload} required aria-describedby="review-consequence" /><span>I, <strong>{user.first_name} {user.last_name}</strong>, verify that this log is accurate.</span></label>
      {error ? <div className="review-error"><p className="error-message" role="alert">{error}</p>{needsReload ? <button className="secondary-button" type="button" onClick={onReload}>Reload log</button> : null}</div> : null}
      <div className="verifier-form-actions"><button className="primary-button review-submit" type="submit" disabled={!confirmed || busy || needsReload}>{busy ? 'Verifying log…' : 'Verify and close log'}</button><button className="secondary-button" type="button" onClick={onCancel} disabled={busy}>Cancel</button></div>
    </form>
  </>
}

export default function VerifierWorkspace({ user, onExpired, onDraftChange, onNotify: notify, onDismiss }: {
  user: User
  onExpired: () => void
  onDraftChange?: (dirty: boolean) => void
  onNotify: (message: string, action?: SnackbarAction) => void
  onDismiss: () => void
}) {
  const [route, setRoute] = useState(currentRoute)
  const [logs, setLogs] = useState<LogSummary[]>([])
  const [log, setLog] = useState<LogDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [retry, setRetry] = useState(0)
  const [pendingRoute, setPendingRoute] = useState<string | null>(null)
  const [showReportDialog, setShowReportDialog] = useState(false)
  const [reportFile, setReportFile] = useState<{ url: string; filename: string } | null>(null)
  const dirty = useRef(false)
  const routeRef = useRef(route)
  const container = useRef<HTMLDivElement>(null)
  const isCreate = route === '#logs/new'
  const isList = route === '#logs'
  const isAdd = route.endsWith('/weapons/new')
  const isReview = route.endsWith('/review')
  const logId = !isCreate && !isList ? Number(route.split('/')[1]) : null

  const changeDirty = useCallback((value: boolean) => {
    dirty.current = value
    onDraftChange?.(value)
  }, [onDraftChange])

  const navigate = useCallback((next: string, saved = false) => {
    if (!saved && dirty.current) { setPendingRoute(next); return }
    changeDirty(false)
    if (!saved) onDismiss()
    window.history.pushState(null, '', next)
    routeRef.current = next
    setRoute(next)
  }, [changeDirty, onDismiss])

  useEffect(() => { setShowReportDialog(false) }, [route])
  useEffect(() => {
    return () => { if (reportFile) URL.revokeObjectURL(reportFile.url) }
  }, [reportFile])

  useEffect(() => {
    if (window.location.hash !== routeRef.current) window.history.replaceState(null, '', routeRef.current)
    const onHashChange = () => {
      const next = currentRoute()
      if (next === routeRef.current) return
      if (dirty.current) {
        window.history.pushState(null, '', routeRef.current)
        setPendingRoute(next)
        return
      }
      changeDirty(false)
      onDismiss()
      routeRef.current = next
      setRoute(next)
    }
    const onUnload = (event: BeforeUnloadEvent) => {
      if (dirty.current) { event.preventDefault(); event.returnValue = '' }
    }
    window.addEventListener('hashchange', onHashChange)
    window.addEventListener('beforeunload', onUnload)
    return () => {
      window.removeEventListener('hashchange', onHashChange)
      window.removeEventListener('beforeunload', onUnload)
      onDraftChange?.(false)
    }
  }, [changeDirty, onDraftChange, onDismiss])

  useEffect(() => {
    const controller = new AbortController()
    setLoadError('')
    setLog(null)
    if (isCreate) { setLoading(false); return }
    setLoading(true)
    const request = isList
      ? api<LogSummary[]>('/logs', { signal: controller.signal }).then(setLogs)
      : api<LogDetail>(`/logs/${logId}`, { signal: controller.signal }).then(setLog)
    request.catch((cause: unknown) => {
      if (controller.signal.aborted) return
      if (cause instanceof ApiError && cause.status === 401) onExpired()
      else setLoadError(cause instanceof Error ? cause.message : 'Unable to load logs. Please try again.')
    }).finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [isCreate, isList, logId, retry, route, onExpired])

  useEffect(() => {
    window.scrollTo({ top: 0, behavior: 'instant' })
    if (!loading) container.current?.querySelector<HTMLHeadingElement>('h1')?.focus({ preventScroll: true })
  }, [route, loading])

  return <div className="verifier-workspace" ref={container}>
    {showReportDialog && isList ? <ReportDialog logs={logs} username={user.username} onCancel={() => setShowReportDialog(false)} onExpired={onExpired} onGenerated={file => { setReportFile(file); setShowReportDialog(false); notify('Your report is ready.', { label: 'Download PDF', href: file.url, download: file.filename }) }} /> : null}
    {pendingRoute ? <DiscardChangesDialog onCancel={() => setPendingRoute(null)} onDiscard={() => { changeDirty(false); navigate(pendingRoute); setPendingRoute(null) }} /> : null}
    {isCreate ? <NewLogForm onCancel={() => navigate('#logs')} onExpired={onExpired} onDirty={changeDirty} onCreated={created => { notify('Log created. You can now add weapons.'); navigate(`#logs/${created.id}`, true) }} /> : <>
      {!isList && ((!isAdd && !isReview) || log?.status === 'REVIEWED') ? <button className="back-link" type="button" onClick={() => navigate('#logs')}><span aria-hidden="true">‹</span> All logs</button> : null}
      {isList ? <div className="page-heading logs-page-heading"><div><h1 tabIndex={-1}>Operation logs</h1><p>Your seizure operations and recorded weapons.</p></div><div className="logs-page-actions"><button className="secondary-button report-button" type="button" onClick={() => setShowReportDialog(true)} disabled={loading || Boolean(loadError)} title="Choose a date range for a PDF report">Generate report</button><button className="primary-button" type="button" onClick={() => navigate('#logs/new')}><span aria-hidden="true">＋ </span>Create log</button></div></div> : null}
      {loading ? <div className="verifier-panel load-state" role="status">{isList ? 'Loading your logs…' : 'Loading operation…'}</div> : loadError ? <div className="verifier-panel load-state"><p className="error-message" role="alert">{loadError}</p><button className="secondary-button" type="button" onClick={() => setRetry(value => value + 1)}>Try again</button>{!isList ? <button className="text-button" type="button" onClick={() => navigate('#logs')}>Back to logs</button> : null}</div> : isList ? <>
        {logs.length === 0 ? <div className="empty-state logs-empty"><div className="log-empty-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"><rect x="5" y="3" width="14" height="18" rx="2" /><path d="M9 8h6M9 12h6M9 16h3" /></svg></div><h2>No operation logs yet</h2><p>Create your first log to record an operation and its weapons.</p><button className="primary-button" type="button" onClick={() => navigate('#logs/new')}>Create log</button></div> : <ul className="log-list">{logs.map(item => <li key={item.id}><a href={`#logs/${item.id}`} className="log-row" onClick={event => { if (!event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey && event.button === 0) { event.preventDefault(); navigate(`#logs/${item.id}`) } }}><div className="log-row-main"><div className="log-title-row"><h2>{item.operation_name}</h2><LogStatus status={item.status} /></div><p className="log-row-date">{fullDate(item.occurred_at)}</p><p className="log-row-location">{item.location_name}</p></div><div className="log-row-end"><span>{item.weapon_count} {item.weapon_count === 1 ? 'weapon' : 'weapons'}</span><span className="row-chevron" aria-hidden="true">›</span></div></a></li>)}</ul>}
      </> : log ? log.status === 'REVIEWED' ? <LogView log={log} /> : isAdd ? <WeaponForm key={route} log={log} onCancel={() => navigate(`#logs/${log.id}`)} onExpired={onExpired} onDirty={changeDirty} onSaved={() => { notify('Weapon saved.'); navigate(`#logs/${log.id}`, true) }} /> : isReview ? <ReviewLogForm key={route} log={log} user={user} onCancel={() => navigate(`#logs/${log.id}`)} onExpired={onExpired} onReload={() => setRetry(value => value + 1)} onReviewed={() => { notify('Log verified and closed.'); navigate(`#logs/${log.id}`, true) }} /> : <LogView log={log} onAdd={() => navigate(`#logs/${log.id}/weapons/new`)} onReview={() => navigate(`#logs/${log.id}/review`)} /> : null}
    </>}
  </div>
}
