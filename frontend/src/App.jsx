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
  UserPlus,
  Users,
} from 'lucide-react'
import {
  archiveDocument,
  createUser,
  deleteDocument,
  getAuditLogs,
  getAccessToken,
  getDepartments,
  getDocuments,
  getHealth,
  getHistory,
  getIngestionJobs,
  getKnowledgeBases,
  getMe,
  getUsers,
  login,
  rebuildIndex,
  retryDocument,
  sendFeedback,
  setAccessToken,
  streamChat,
  updateUser,
  uploadDocument,
} from './api'

export default function App() {
  const [user, setUser] = useState(null)
  const [view, setView] = useState('chat')
  const [documents, setDocuments] = useState([])
  const [knowledgeBases, setKnowledgeBases] = useState([])
  const [selectedKbId, setSelectedKbId] = useState(1)
  const [jobs, setJobs] = useState([])
  const [auditLogs, setAuditLogs] = useState([])
  const [users, setUsers] = useState([])
  const [departments, setDepartments] = useState([])
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

  const isAdmin = ['system_admin', 'kb_admin', 'editor', 'admin'].includes(user?.role)
  const isSystemAdmin = user?.role === 'system_admin'
  const canSend = useMemo(() => question.trim() && !loading, [question, loading])

  async function refreshData(currentUser = user) {
    const [docs, healthInfo, kbs] = await Promise.all([getDocuments(), getHealth(), getKnowledgeBases()])
    setDocuments(docs)
    setHealth(healthInfo)
    setKnowledgeBases(kbs)
    if (!selectedKbId && kbs[0]?.id) setSelectedKbId(kbs[0].id)
    if (currentUser) {
      const historyRows = await getHistory()
      setHistory(historyRows.slice(0, 8))
    }
    if (currentUser?.role !== 'reader') {
      const [jobRows, auditRows] = await Promise.all([
        getIngestionJobs().catch(() => []),
        currentUser?.role === 'system_admin' ? getAuditLogs().catch(() => []) : Promise.resolve([]),
      ])
      setJobs(jobRows.slice(0, 8))
      setAuditLogs(auditRows.slice(0, 8))
    }
    if (currentUser?.role === 'system_admin') {
      const [userRows, departmentRows] = await Promise.all([
        getUsers().catch(() => []),
        getDepartments().catch(() => []),
      ])
      setUsers(userRows)
      setDepartments(departmentRows)
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
        setView(['system_admin', 'kb_admin', 'editor', 'admin'].includes(me.role) ? 'admin' : 'chat')
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

  useEffect(() => {
    if (!user || !isAdmin) return undefined
    const hasActiveJobs = jobs.some((job) => !['completed', 'failed'].includes(job.status))
    const hasActiveDocuments = documents.some((doc) =>
      ['pending', 'indexing'].includes(doc.status),
    )
    if (!hasActiveJobs && !hasActiveDocuments) return undefined

    const timer = window.setInterval(() => {
      refreshData().catch(() => {})
    }, 2000)
    return () => window.clearInterval(timer)
  }, [documents, isAdmin, jobs, user])

  async function handleLogin(username, password) {
    setError('')
    const data = await login(username, password)
    setAccessToken(data.access_token)
    setUser(data.user)
    setView(['system_admin', 'kb_admin', 'editor', 'admin'].includes(data.user.role) ? 'admin' : 'chat')
    await refreshData(data.user)
  }

  function handleLogout() {
    setAccessToken('')
    setUser(null)
    setView('chat')
    setMessages([])
    setHistory([])
    setDocuments([])
    setKnowledgeBases([])
    setJobs([])
    setAuditLogs([])
    setUsers([])
    setDepartments([])
    setHealth(null)
    setError('')
  }

  async function handleUpload(event) {
    const file = event.target.files?.[0]
    if (!file) return
    setWorking(true)
    setError('')
    try {
      await uploadDocument(file, selectedKbId)
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

  async function handleArchive(documentId) {
    setWorking(true)
    setError('')
    try {
      await archiveDocument(documentId)
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

  async function handleCreateUser(payload) {
    setWorking(true)
    setError('')
    try {
      await createUser(payload)
      await refreshData()
    } catch (err) {
      setError(err.message)
    } finally {
      setWorking(false)
    }
  }

  async function handleUpdateUser(userId, updates) {
    setWorking(true)
    setError('')
    try {
      await updateUser(userId, updates)
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
              items.map((item) =>
                item.id === assistantId
                  ? { ...item, sources: data.sources, messageId: data.message_id, refused: data.refused }
                  : item,
              ),
            )
          }
          await refreshData()
        },
      }, selectedKbId)
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
            <span>{roleText(user.role)}</span>
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
            knowledgeBases={knowledgeBases}
            selectedKbId={selectedKbId}
            setSelectedKbId={setSelectedKbId}
            onFeedback={sendFeedback}
            setQuestion={setQuestion}
          />
        ) : (
          <AdminView
            auditLogs={auditLogs}
            currentUserId={user.id}
            departments={departments}
            documents={documents}
            fileInputRef={fileInputRef}
            handleArchive={handleArchive}
            handleDelete={handleDelete}
            handleRebuild={handleRebuild}
            handleRetry={handleRetry}
            handleUpload={handleUpload}
            health={health}
            jobs={jobs}
            knowledgeBases={knowledgeBases}
            isSystemAdmin={isSystemAdmin}
            onCreateUser={handleCreateUser}
            onUpdateUser={handleUpdateUser}
            selectedKbId={selectedKbId}
            setSelectedKbId={setSelectedKbId}
            users={users}
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
          <span>系统管理员：admin / admin123</span>
          <span>知识库管理员：kbadmin / kbadmin123</span>
          <span>编辑者：editor / editor123</span>
          <span>普通员工：user / user123</span>
        </div>
      </form>
    </main>
  )
}

function ChatView({
  canSend,
  chatEndRef,
  handleSubmit,
  knowledgeBases,
  loading,
  messages,
  onFeedback,
  question,
  selectedKbId,
  setQuestion,
  setSelectedKbId,
}) {
  return (
    <section className="workspace chat-workspace">
      <header className="workspace-header">
        <div>
          <span className="eyebrow">员工入口</span>
          <h2>知识库智能问答</h2>
        </div>
        <div className="header-tools">
          <select value={selectedKbId} onChange={(event) => setSelectedKbId(Number(event.target.value))}>
            {knowledgeBases.map((kb) => (
              <option value={kb.id} key={kb.id}>
                {kb.name}
              </option>
            ))}
          </select>
        </div>
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
              {message.role === 'assistant' && message.messageId && (
                <div className="feedback-row">
                  <button onClick={() => onFeedback(message.messageId, 'helpful')}>有帮助</button>
                  <button onClick={() => onFeedback(message.messageId, 'not_helpful')}>无帮助</button>
                  <button onClick={() => onFeedback(message.messageId, 'citation_error')}>引用有误</button>
                  <button onClick={() => onFeedback(message.messageId, 'incomplete')}>不完整</button>
                </div>
              )}
              {message.sources?.length > 0 && (
                <div className="sources">
                  <div className="sources-label">
                    {loading && !message.content ? '候选来源' : '答案引用来源'}
                  </div>
                  {message.sources.map((source, index) => (
                    <details className="source-card" key={`${source.file_name}-${source.chunk_id}-${index}`}>
                      <summary>
                        来源{index + 1} · {source.file_name} · v{source.document_version || 1} · chunk {source.chunk_id}
                        {source.section_title ? ` · ${source.section_title}` : ''}
                        {source.page_start ? ` · 页 ${source.page_start}` : ''}
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
  auditLogs,
  currentUserId,
  departments,
  documents,
  fileInputRef,
  handleArchive,
  handleDelete,
  handleRebuild,
  handleRetry,
  handleUpload,
  health,
  isSystemAdmin,
  jobs,
  knowledgeBases,
  onCreateUser,
  onUpdateUser,
  selectedKbId,
  setSelectedKbId,
  users,
  working,
}) {
  return (
    <section className="workspace admin-workspace">
      <header className="workspace-header">
        <div>
          <span className="eyebrow">管理员入口</span>
          <h2>知识库文档管理</h2>
        </div>
        <div className="header-tools">
          <select value={selectedKbId} onChange={(event) => setSelectedKbId(Number(event.target.value))}>
            {knowledgeBases.map((kb) => (
              <option value={kb.id} key={kb.id}>
                {kb.name}
              </option>
            ))}
          </select>
        </div>
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

      <div className="admin-grid">
        <section className="admin-card">
          <div className="admin-card-title">
            <RefreshCcw size={20} />
            入库任务
          </div>
          {jobs.length === 0 ? (
            <div className="empty">暂无任务</div>
          ) : (
            <div className="job-list">
              {jobs.map((job) => (
                <div className="job-item" key={job.id}>
                  <strong>{job.file_name || `文档 ${job.document_id}`}</strong>
                  <span>{job.status} · {job.progress}% · {job.log_summary || '等待处理'}</span>
                  {job.error_message && <em>{job.error_message}</em>}
                </div>
              ))}
            </div>
          )}
        </section>

        <section className="admin-card">
          <div className="admin-card-title">
            <ShieldCheck size={20} />
            审计摘要
          </div>
          {auditLogs.length === 0 ? (
            <div className="empty">暂无审计记录或无权限查看</div>
          ) : (
            <div className="job-list">
              {auditLogs.map((log) => (
                <div className="job-item" key={log.id}>
                  <strong>{log.action}</strong>
                  <span>{log.username || 'system'} · {log.target_type} {log.target_id}</span>
                </div>
              ))}
            </div>
          )}
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
                  <button className="icon-button" onClick={() => handleArchive(doc.id)} disabled={working} title="归档文档">
                    <FileText size={16} />
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

      {isSystemAdmin && (
        <section className="admin-card document-table-card">
          <div className="admin-card-title">
            <Users size={20} />
            权限与账号
          </div>
          <UserCreateForm departments={departments} onCreateUser={onCreateUser} working={working} />
          <div className="user-table">
            <div className="user-row user-head">
              <span>账号</span>
              <span>角色</span>
              <span>部门</span>
              <span>岗位</span>
              <span>状态</span>
            </div>
            {users.map((item) => (
              <div className="user-row" key={item.id}>
                <span className="file-name">{item.username}</span>
                <select
                  value={item.role}
                  disabled={working || item.id === currentUserId}
                  title={item.id === currentUserId ? '不能修改当前登录账号角色' : '修改角色'}
                  onChange={(event) => onUpdateUser(item.id, { role: event.target.value })}
                >
                  {ROLE_OPTIONS.map((role) => (
                    <option value={role.value} key={role.value}>
                      {role.label}
                    </option>
                  ))}
                </select>
                <select
                  value={item.department_id || ''}
                  disabled={working}
                  onChange={(event) =>
                    onUpdateUser(item.id, {
                      department_id: event.target.value ? Number(event.target.value) : null,
                    })
                  }
                >
                  <option value="">未分配</option>
                  {departments.map((department) => (
                    <option value={department.id} key={department.id}>
                      {department.name}
                    </option>
                  ))}
                </select>
                <span>{item.position || '-'}</span>
                <select
                  value={item.status}
                  disabled={working || item.id === currentUserId}
                  title={item.id === currentUserId ? '不能停用当前登录账号' : '修改状态'}
                  onChange={(event) => onUpdateUser(item.id, { status: event.target.value })}
                >
                  <option value="active">启用</option>
                  <option value="disabled">停用</option>
                </select>
              </div>
            ))}
          </div>
        </section>
      )}
    </section>
  )
}

const ROLE_OPTIONS = [
  { value: 'system_admin', label: '系统管理员' },
  { value: 'kb_admin', label: '知识库管理员' },
  { value: 'editor', label: '编辑者' },
  { value: 'reader', label: '普通员工' },
]

function UserCreateForm({ departments, onCreateUser, working }) {
  const [form, setForm] = useState({
    username: '',
    password: '',
    role: 'reader',
    department_id: '',
    position: '',
  })

  function update(field, value) {
    setForm((current) => ({ ...current, [field]: value }))
  }

  async function submit(event) {
    event.preventDefault()
    await onCreateUser({
      username: form.username.trim(),
      password: form.password,
      role: form.role,
      department_id: form.department_id ? Number(form.department_id) : null,
      position: form.position.trim(),
    })
    setForm({ username: '', password: '', role: 'reader', department_id: '', position: '' })
  }

  return (
    <form className="user-create-form" onSubmit={submit}>
      <input
        value={form.username}
        onChange={(event) => update('username', event.target.value)}
        placeholder="账号"
        required
      />
      <input
        type="password"
        value={form.password}
        onChange={(event) => update('password', event.target.value)}
        placeholder="初始密码"
        required
        minLength={6}
      />
      <select value={form.role} onChange={(event) => update('role', event.target.value)}>
        {ROLE_OPTIONS.map((role) => (
          <option value={role.value} key={role.value}>
            {role.label}
          </option>
        ))}
      </select>
      <select value={form.department_id} onChange={(event) => update('department_id', event.target.value)}>
        <option value="">未分配部门</option>
        {departments.map((department) => (
          <option value={department.id} key={department.id}>
            {department.name}
          </option>
        ))}
      </select>
      <input
        value={form.position}
        onChange={(event) => update('position', event.target.value)}
        placeholder="岗位"
      />
      <button type="submit" className="primary-button" disabled={working || !form.username.trim() || !form.password}>
        <UserPlus size={17} />
        创建账号
      </button>
    </form>
  )
}

function statusText(status) {
  const map = {
    pending: '等待中',
    indexing: '入库中',
    indexed: '已入库',
    failed: '失败',
    archived: '已归档',
  }
  return map[status] || status
}

function formatSize(size) {
  if (!size) return '0 B'
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}

function roleText(role) {
  const map = {
    system_admin: '系统管理员',
    kb_admin: '知识库管理员',
    editor: '编辑者',
    reader: '普通员工',
    admin: '系统管理员',
    user: '普通员工',
  }
  return map[role] || role
}
