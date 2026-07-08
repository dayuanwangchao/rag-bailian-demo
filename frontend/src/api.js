const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

let accessToken = localStorage.getItem('rag_access_token') || ''

export function setAccessToken(token) {
  accessToken = token || ''
  if (accessToken) {
    localStorage.setItem('rag_access_token', accessToken)
  } else {
    localStorage.removeItem('rag_access_token')
  }
}

export function getAccessToken() {
  return accessToken
}

async function request(path, options = {}) {
  const headers = new Headers(options.headers || {})
  if (accessToken) {
    headers.set('Authorization', `Bearer ${accessToken}`)
  }
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  })
  if (!response.ok) {
    const data = await response.json().catch(() => ({}))
    throw new Error(data.detail || `请求失败：${response.status}`)
  }
  return response.json()
}

export function login(username, password) {
  return request('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })
}

export function getMe() {
  return request('/api/auth/me')
}

export function getHealth() {
  return request('/api/health')
}

export function getDocuments() {
  return request('/api/documents')
}

export function getHistory() {
  return request('/api/history')
}

export function uploadDocument(file) {
  const formData = new FormData()
  formData.append('file', file)
  return request('/api/upload', {
    method: 'POST',
    body: formData,
  })
}

export function rebuildIndex() {
  return request('/api/rebuild', { method: 'POST' })
}

export function deleteDocument(documentId) {
  return request(`/api/documents/${documentId}`, { method: 'DELETE' })
}

export function retryDocument(documentId) {
  return request(`/api/documents/${documentId}/retry`, { method: 'POST' })
}

export async function streamChat(question, callbacks) {
  const response = await fetch(`${API_BASE}/api/chat/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
    },
    body: JSON.stringify({ question }),
  })

  if (!response.ok || !response.body) {
    const data = await response.json().catch(() => ({}))
    throw new Error(data.detail || '流式问答请求失败')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const events = buffer.split('\n\n')
    buffer = events.pop() || ''
    for (const eventText of events) {
      const event = parseSseEvent(eventText)
      if (!event) continue
      callbacks[event.event]?.(event.data)
      if (event.event === 'error') {
        throw new Error(event.data)
      }
    }
  }
}

function parseSseEvent(text) {
  const eventLine = text.split('\n').find((line) => line.startsWith('event:'))
  const dataLine = text.split('\n').find((line) => line.startsWith('data:'))
  if (!eventLine || !dataLine) return null
  return {
    event: eventLine.replace('event:', '').trim(),
    data: JSON.parse(dataLine.replace('data:', '').trim()),
  }
}
