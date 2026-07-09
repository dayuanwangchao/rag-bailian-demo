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

export function getKnowledgeBases() {
  return request('/api/knowledge-bases')
}

export function getDepartments() {
  return request('/api/departments')
}

export function getUsers() {
  return request('/api/users')
}

export function createUser(user) {
  return request('/api/users', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(user),
  })
}

export function updateUser(userId, updates) {
  return request(`/api/users/${userId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(updates),
  })
}

export function createKnowledgeBase(name, description = '') {
  return request('/api/knowledge-bases', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, description }),
  })
}

export function getDocuments() {
  return request('/api/documents')
}

export function getIngestionJobs() {
  return request('/api/ingestion-jobs')
}

export function getAuditLogs() {
  return request('/api/audit-logs')
}

export function getHistory() {
  return request('/api/history')
}

export function uploadDocument(file, knowledgeBaseId = 1) {
  const formData = new FormData()
  formData.append('file', file)
  return request(`/api/documents/upload?knowledge_base_id=${knowledgeBaseId}`, {
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
  return request(`/api/documents/${documentId}/reindex`, { method: 'POST' })
}

export function archiveDocument(documentId) {
  return request(`/api/documents/${documentId}/archive`, { method: 'POST' })
}

export function sendFeedback(messageId, rating, comment = '') {
  return request('/api/feedback', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message_id: messageId, rating, comment }),
  })
}

export async function streamChat(question, callbacks, knowledgeBaseId = null) {
  const response = await fetch(`${API_BASE}/api/chat/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
    },
    body: JSON.stringify({ question, knowledge_base_id: knowledgeBaseId }),
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
