import React, { useEffect, useMemo, useRef, useState } from 'react'
import {
  Bot,
  Database,
  FileText,
  History,
  MessageSquare,
  RefreshCcw,
  Send,
  ShieldCheck,
  UploadCloud,
} from 'lucide-react'
import {
  getDocuments,
  getHealth,
  getHistory,
  rebuildIndex,
  streamChat,
  uploadDocument,
} from './api'

export default function App() {
  const [view, setView] = useState('chat')
  const [documents, setDocuments] = useState([])
  const [history, setHistory] = useState([])
  const [health, setHealth] = useState(null)
  const [question, setQuestion] = useState('')
  const [messages, setMessages] = useState([])
  const [loading, setLoading] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState('')
  const fileInputRef = useRef(null)
  const chatEndRef = useRef(null)

  const canSend = useMemo(() => question.trim() && !loading, [question, loading])

  async function refreshData() {
    const [docs, historyRows, healthInfo] = await Promise.all([
      getDocuments(),
      getHistory(),
      getHealth(),
    ])
    setDocuments(docs)
    setHistory(historyRows.slice(-8).reverse())
    setHealth(healthInfo)
  }

  useEffect(() => {
    refreshData().catch((err) => setError(err.message))
  }, [])

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  async function handleUpload(event) {
    const file = event.target.files?.[0]
    if (!file) return
    setUploading(true)
    setError('')
    try {
      await uploadDocument(file)
      await refreshData()
    } catch (err) {
      setError(err.message)
    } finally {
      setUploading(false)
      event.target.value = ''
    }
  }

  async function handleRebuild() {
    setUploading(true)
    setError('')
    try {
      await rebuildIndex()
      await refreshData()
    } catch (err) {
      setError(err.message)
    } finally {
      setUploading(false)
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
        done: async () => {
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

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">
            <Bot size={24} />
          </div>
          <div>
            <h1>企业知识库 RAG</h1>
            <p>员工问答端 + 管理员知识库端</p>
          </div>
          <span className="status-dot" title={health?.status === 'ok' ? '服务正常' : '服务未知'} />
        </div>

        <nav className="role-nav" aria-label="系统视图">
          <button className={view === 'chat' ? 'active' : ''} onClick={() => setView('chat')}>
            <MessageSquare size={18} />
            员工问答
          </button>
          <button className={view === 'admin' ? 'active' : ''} onClick={() => setView('admin')}>
            <ShieldCheck size={18} />
            知识库管理
          </button>
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

        {view === 'chat' ? (
          <section className="panel history-panel">
            <div className="panel-title">
              <History size={16} />
              最近提问
            </div>
            {history.length === 0 ? (
              <div className="empty">暂无历史问答</div>
            ) : (
              history.map((row, index) => (
                <button
                  className="history-item"
                  key={`${row.question}-${index}`}
                  onClick={() => setQuestion(row.question)}
                >
                  {row.question}
                </button>
              ))
            )}
          </section>
        ) : (
          <section className="panel admin-hint">
            <div className="panel-title">
              <Database size={16} />
              管理员工作台
            </div>
            <p>上传企业制度、产品手册、培训资料等文档后，员工问答端会自动基于最新索引检索回答。</p>
          </section>
        )}
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
            handleRebuild={handleRebuild}
            handleUpload={handleUpload}
            health={health}
            uploading={uploading}
          />
        )}
      </section>
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
                  {message.sources.map((source, index) => (
                    <div className="source-card" key={`${source.file_name}-${source.chunk_id}-${index}`}>
                      <div className="source-title">来源{index + 1} · {source.file_name} · chunk {source.chunk_id}</div>
                      <p>{source.content}</p>
                    </div>
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

function AdminView({ documents, fileInputRef, handleRebuild, handleUpload, health, uploading }) {
  return (
    <section className="workspace admin-workspace">
      <header className="workspace-header">
        <div>
          <span className="eyebrow">管理员入口</span>
          <h2>知识库文档管理</h2>
        </div>
        <p>管理员负责维护文档、重建索引和检查入库状态，普通员工无需看到这些操作。</p>
      </header>

      <div className="admin-grid">
        <section className="admin-card upload-card">
          <div className="admin-card-title">
            <UploadCloud size={20} />
            文档入库
          </div>
          <p>支持 PDF、DOCX、TXT、MD。上传后系统会解析文本、切分片段、生成向量并写入 FAISS。</p>
          <div className="admin-actions">
            <button className="primary-button" onClick={() => fileInputRef.current?.click()} disabled={uploading}>
              <UploadCloud size={18} />
              {uploading ? '处理中...' : '上传文档'}
            </button>
            <button className="ghost-button" onClick={handleRebuild} disabled={uploading}>
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
              <span>切分片段</span>
              <span>文件大小</span>
            </div>
            {documents.map((doc) => (
              <div className="table-row" key={doc.file_name}>
                <span className="file-name">{doc.file_name}</span>
                <span>{doc.chunks}</span>
                <span>{formatSize(doc.size)}</span>
              </div>
            ))}
          </div>
        )}
      </section>
    </section>
  )
}

function formatSize(size) {
  if (!size) return '0 B'
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}
