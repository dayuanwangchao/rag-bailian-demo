import React, { useEffect, useMemo, useRef, useState } from 'react'
import {
  Bot,
  Database,
  FileText,
  History,
  LogOut,
  MessageSquare,
  RefreshCcw,
  RotateCcw,
  Send,
  ShieldCheck,
  Trash2,
  UploadCloud,
} from 'lucide-react'
import {
  deleteDocument,
  getAccessToken,
  getDocuments,
  getHealth,
  getHistory,
  getMe,
  login,
  rebuildIndex,
  retryDocument,
  setAccessToken,
  streamChat,
  uploadDocument,
} from './api'

export default function App() {
  const [user, setUser] = useState(null)
  const [view, setView] = useState('chat')
  const [documents, setDocuments] = useState([])
  const [history, setHistory] = useState([])
  const [health, setHealth] = useState(null)
  const [question, setQuestion] = useState('')
  const [messages, setMessages] = useState([])
  const [loading, setLoading] = useState(false)
  const [working, setWorking] = useState(false)
  const [booting, setBooting] = useState(true)
  const [error, setError] = useState('')
  const fileInputRef = useRef(null)
  const chatEndRef = useRef(null)

  const isAdmin = user?.role === 'admin'
  const canSend = useMemo(() => question.trim() && !loading, [question, loading])

  async function refreshData(currentUser = user) {
    const [docs, healthInfo] = await Promise.all([getDocuments(), getHealth()])
    setDocuments(docs)
    setHealth(healthInfo)
    if (currentUser) {
      const historyRows = await getHistory()
      setHistory(historyRows.slice(0, 8))
    }
  }

  useEffect(() => {
    async function boot() {
      if (!getAccessToken()) {
        setBooting(false)
        return
      }
      try {
        const me = await getMe()
        setUser(me)
        setView(me.role === 'admin' ? 'admin' : 'chat')
        await refreshData(me)
      } catch {
        setAccessToken('')
      } finally {
        setBooting(false)
      }
    }
    boot()
  }, [])

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  async function handleLogin(username, password) {
    setError('')
    const data = await login(username, password)
    setAccessToken(data.access_token)
    setUser(data.user)
    setView(data.user.role === 'admin' ? 'admin' : 'chat')
    await refreshData(data.user)
  }

  function handleLogout() {
    setAccessToken('')
    setUser(null)
    setView('chat')
    setMessages([])
    setHistory([])
    setDocuments([])
    setHealth(null)
    setError('')
  }

  async function handleUpload(event) {
    const file = event.target.files?.[0]
    if (!file) return
    setWorking(true)
    setError('')
    try {
      await uploadDocument(file)
      await refreshData()
    } catch (err) {
      setError(err.message)
    } finally {
      setWorking(false)
      event.target.value = ''
    }
  }

  async function handleRebuild() {
    setWorking(true)
    setError('')
    try {
      await rebuildIndex()
      await refreshData()
    } catch (err) {
      setError(err.message)
    } finally {
      setWorking(false)
    }
  }

  async function handleDelete(documentId) {
    setWorking(true)
    setError('')
    try {
      await deleteDocument(documentId)
      await refreshData()
    } catch (err) {
      setError(err.message)
    } finally {
      setWorking(false)
    }
  }

  async function handleRetry(documentId) {
    setWorking(true)
    setError('')
    try {
      await retryDocument(documentId)
      await refreshData()
    } catch (err) {
      setError(err.message)
    } finally {
      setWorking(false)
    }
  }

  async function handleSubmit(event) {
    event.preventDefault()
    const text = question.trim()
    if (!text || loading) return

    const assistantId = crypto.randomUUID()
    setQuestion('')
    setLoading(true)
    setError('')
    setMessages((items) => [
      ...items,
      { id: crypto.randomUUID(), role: 'user', content: text },
      { id: assistantId, role: 'assistant', content: '', sources: [] },
    ])

    try {
      await streamChat(text, {
        sources: (sources) => {
          setMessages((items) =>
            items.map((item) => (item.id === assistantId ? { ...item, sources } : item)),
          )
        },
        token: (token) => {
          setMessages((items) =>
            items.map((item) =>
              item.id === assistantId ? { ...item, content: item.content + token } : item,
            ),
          )
        },
        done: async (data) => {
          if (data?.sources) {
            setMessages((items) =>
              items.map((item) => (item.id === assistantId ? { ...item, sources: data.sources } : item)),
            )
          }
          await refreshData()
        },
      })
    } catch (err) {
      setError(err.message)
      setMessages((items) =>
        items.map((item) =>
          item.id === assistantId
            ? { ...item, content: item.content || '回答生成失败，请检查后端日志或 API Key。' }
            : item,
        ),
      )
    } finally {
      setLoading(false)
    }
  }

  if (booting) {
    return <div className="boot-screen">正在进入企业知识库...</div>
  }

  if (!user) {
    return <LoginView error={error} onLogin={handleLogin} setError={setError} />
  }

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">
            <Bot size={24} />
          </div>
          <div>
            <h1>企业知识库 RAG</h1>
            <p>{isAdmin ? '管理员知识库端' : '员工智能问答端'}</p>
          </div>
          <span className="status-dot" title={health?.status === 'ok' ? '服务正常' : '服务未知'} />
        </div>

        <div className="user-strip">
          <div>
            <strong>{user.username}</strong>
            <span>{isAdmin ? '管理员' : '普通员工'}</span>
          </div>
          <button className="icon-button" onClick={handleLogout} title="退出登录">
            <LogOut size={17} />
          </button>
        </div>

        <nav className="role-nav" aria-label="系统视图">
          <button className={view === 'chat' ? 'active' : ''} onClick={() => setView('chat')}>
            <MessageSquare size={18} />
            员工问答
          </button>
          {isAdmin && (
            <button className={view === 'admin' ? 'active' : ''} onClick={() => setView('admin')}>
              <ShieldCheck size={18} />
              知识库管理
            </button>
          )}
        </nav>

        <section className="panel status-panel">
          <div className="panel-title">知识库状态</div>
          <div className="metric-grid">
            <div>
              <strong>{documents.length}</strong>
              <span>文档</span>
            </div>
            <div>
              <strong>{health?.indexed_chunks ?? 0}</strong>
              <span>片段</span>
            </div>
          </div>
        </section>

        <section className="panel history-panel">
          <div className="panel-title">
            <History size={16} />
            最近提问
          </div>
          {history.length === 0 ? (
            <div className="empty">暂无历史问答</div>
          ) : (
            history.map((row) => (
              <button className="history-item" key={row.id} onClick={() => setQuestion(row.question)}>
                {row.question}
              </button>
            ))
          )}
        </section>
      </aside>

      <section className="main-area">
        {error && <div className="error-banner">{error}</div>}
        {view === 'chat' ? (
          <ChatView
            canSend={canSend}
            chatEndRef={chatEndRef}
            handleSubmit={handleSubmit}
            loading={loading}
            messages={messages}
            question={question}
            setQuestion={setQuestion}
          />
        ) : (
          <AdminView
            documents={documents}
            fileInputRef={fileInputRef}
            handleDelete={handleDelete}
            handleRebuild={handleRebuild}
            handleRetry={handleRetry}
            handleUpload={handleUpload}
            health={health}
            working={working}
          />
        )}
      </section>
    </main>
  )
}

function LoginView({ error, onLogin, setError }) {
  const [username, setUsername] = useState('admin')
  const [password, setPassword] = useState('admin123')
  const [submitting, setSubmitting] = useState(false)

  async function submit(event) {
    event.preventDefault()
    setSubmitting(true)
    setError('')
    try {
      await onLogin(username, password)
    } catch (err) {
      setError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="login-shell">
      <form className="login-card" onSubmit={submit}>
        <div className="brand-mark">
          <Bot size={26} />
        </div>
        <h1>企业知识库 RAG</h1>
        <p>使用演示账号登录，体验员工问答端和管理员知识库端。</p>
        {error && <div className="error-banner">{error}</div>}
        <label>
          账号
          <input value={username} onChange={(event) => setUsername(event.target.value)} />
        </label>
        <label>
          密码
          <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} />
        </label>
        <button type="submit" disabled={submitting}>
          {submitting ? '登录中...' : '登录'}
        </button>
        <div className="demo-accounts">
          <span>管理员：admin / admin123</span>
          <span>员工：user / user123</span>
        </div>
      </form>
    </main>
  )
}

function ChatView({ canSend, chatEndRef, handleSubmit, loading, messages, question, setQuestion }) {
  return (
    <section className="workspace chat-workspace">
      <header className="workspace-header">
        <div>
          <span className="eyebrow">员工入口</span>
          <h2>知识库智能问答</h2>
        </div>
        <p>普通员工只需要提问，系统会检索企业知识库并给出带引用来源的回答。</p>
      </header>

      <div className="chat-window">
        {messages.length === 0 ? (
          <div className="welcome">
            <h3>今天想查什么？</h3>
            <p>例如：报销流程是什么？试用期转正需要哪些材料？产品售后政策有哪些？</p>
          </div>
        ) : (
          messages.map((message) => (
            <article className={`message ${message.role}`} key={message.id}>
              <div className="bubble">{message.content || (loading ? '正在检索与生成...' : '')}</div>
              {message.sources?.length > 0 && (
                <div className="sources">
                  <div className="sources-label">
                    {loading && !message.content ? '候选来源' : '答案引用来源'}
                  </div>
                  {message.sources.map((source, index) => (
                    <details className="source-card" key={`${source.file_name}-${source.chunk_id}-${index}`}>
                      <summary>
                        来源{index + 1} · {source.file_name} · chunk {source.chunk_id}
                        {typeof source.score === 'number' ? ` · ${(source.score * 100).toFixed(1)}%` : ''}
                      </summary>
                      <p>{source.content}</p>
                    </details>
                  ))}
                </div>
              )}
            </article>
          ))
        )}
        <div ref={chatEndRef} />
      </div>

      <form className="composer" onSubmit={handleSubmit}>
        <textarea
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder="输入你的问题，例如：公司报销流程是什么？"
          rows={2}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault()
              handleSubmit(event)
            }
          }}
        />
        <button type="submit" disabled={!canSend}>
          <Send size={18} />
          发送
        </button>
      </form>
    </section>
  )
}

function AdminView({
  documents,
  fileInputRef,
  handleDelete,
  handleRebuild,
  handleRetry,
  handleUpload,
  health,
  working,
}) {
  return (
    <section className="workspace admin-workspace">
      <header className="workspace-header">
        <div>
          <span className="eyebrow">管理员入口</span>
          <h2>知识库文档管理</h2>
        </div>
        <p>管理员负责维护文档、重建索引和检查入库状态，普通员工不会看到这些操作。</p>
      </header>

      <div className="admin-grid">
        <section className="admin-card upload-card">
          <div className="admin-card-title">
            <UploadCloud size={20} />
            文档入库
          </div>
          <p>支持 PDF、DOCX、TXT、MD。上传后进入后台入库任务，管理员可查看状态和失败原因。</p>
          <div className="admin-actions">
            <button className="primary-button" onClick={() => fileInputRef.current?.click()} disabled={working}>
              <UploadCloud size={18} />
              {working ? '处理中...' : '上传文档'}
            </button>
            <button className="ghost-button" onClick={handleRebuild} disabled={working}>
              <RefreshCcw size={17} />
              重新构建索引
            </button>
          </div>
          <input
            ref={fileInputRef}
            className="hidden-input"
            type="file"
            accept=".pdf,.docx,.txt,.md"
            onChange={handleUpload}
          />
        </section>

        <section className="admin-card">
          <div className="admin-card-title">
            <Database size={20} />
            索引概览
          </div>
          <div className="index-summary">
            <div>
              <strong>{documents.length}</strong>
              <span>已上传文档</span>
            </div>
            <div>
              <strong>{health?.indexed_chunks ?? 0}</strong>
              <span>向量片段</span>
            </div>
            <div>
              <strong>{health?.status === 'ok' ? '正常' : '未知'}</strong>
              <span>后端服务</span>
            </div>
          </div>
        </section>
      </div>

      <section className="admin-card document-table-card">
        <div className="admin-card-title">
          <FileText size={20} />
          已入库文档
        </div>
        {documents.length === 0 ? (
          <div className="empty large-empty">暂无文档，请先上传企业资料。</div>
        ) : (
          <div className="document-table">
            <div className="table-row table-head">
              <span>文件名</span>
              <span>状态</span>
              <span>片段</span>
              <span>大小</span>
              <span>操作</span>
            </div>
            {documents.map((doc) => (
              <div className="table-row" key={doc.id}>
                <span className="file-name">
                  {doc.file_name}
                  {doc.error_message && <em>{doc.error_message}</em>}
                </span>
                <span className={`status-pill ${doc.status}`}>{statusText(doc.status)}</span>
                <span>{doc.chunks}</span>
                <span>{formatSize(doc.size)}</span>
                <span className="row-actions">
                  <button className="icon-button" onClick={() => handleRetry(doc.id)} disabled={working} title="重新入库">
                    <RotateCcw size={16} />
                  </button>
                  <button className="icon-button danger" onClick={() => handleDelete(doc.id)} disabled={working} title="删除文档">
                    <Trash2 size={16} />
                  </button>
                </span>
              </div>
            ))}
          </div>
        )}
      </section>
    </section>
  )
}

function statusText(status) {
  const map = {
    pending: '等待中',
    indexing: '入库中',
    indexed: '已入库',
    failed: '失败',
  }
  return map[status] || status
}

function formatSize(size) {
  if (!size) return '0 B'
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}
