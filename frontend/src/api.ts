export type User = {
  id: number
  first_name: string
  last_name: string
  username: string
  role: 'ADMINISTRATOR' | 'VERIFIER'
}

export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers)
  if (options.body && !(options.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  let response: Response
  try {
    response = await fetch(`/api${path}`, {
      ...options,
      credentials: 'same-origin',
      headers,
    })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new Error('Unable to connect. Check your connection and try again.')
  }

  if (!response.ok) {
    const body = await response.json().catch(() => null)
    const detail: unknown = body?.detail
    const message = typeof detail === 'string'
      ? detail
      : response.status === 422
        ? 'Check the details you entered and try again.'
        : 'The request could not be completed. Please try again.'
    throw new ApiError(message, response.status)
  }
  return response.status === 204 ? undefined as T : response.json() as Promise<T>
}
