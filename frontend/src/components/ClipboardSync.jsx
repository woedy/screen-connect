import { useState, useEffect, useCallback } from 'react'

/**
 * Clipboard sync — read/write remote clipboard.
 */
export default function ClipboardSync({ sendMessage, lastMessage }) {
  const [content, setContent] = useState('')
  const [loading, setLoading] = useState(false)
  const [toast, setToast] = useState(null)

  const pullClipboard = useCallback(() => {
    setLoading(true)
    sendMessage({ type: 'clipboard_get' })
  }, [sendMessage])

  useEffect(() => {
    pullClipboard()
  }, [pullClipboard])

  useEffect(() => {
    if (!lastMessage) return

    if (lastMessage.type === 'clipboard_content') {
      setContent(lastMessage.content || '')
      setLoading(false)
      if (lastMessage.error) {
        showToast(`Clipboard error: ${lastMessage.error}`, 'error')
      }
    }

    if (lastMessage.type === 'clipboard_set_response') {
      if (lastMessage.success) {
        showToast('Clipboard updated on remote machine', 'success')
      } else {
        showToast(`Failed: ${lastMessage.error}`, 'error')
      }
    }
  }, [lastMessage])

  const pushClipboard = () => {
    sendMessage({ type: 'clipboard_set', content })
  }

  const copyToLocal = () => {
    navigator.clipboard.writeText(content).then(() => {
      showToast('Copied to your local clipboard', 'success')
    }).catch(() => {
      showToast('Failed to copy locally', 'error')
    })
  }

  const showToast = (message, type) => {
    setToast({ message, type })
    setTimeout(() => setToast(null), 3000)
  }

  return (
    <div style={{ padding: 20, display: 'flex', flexDirection: 'column', height: '100%', gap: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h3 style={{ fontSize: 16, fontWeight: 600 }}>📋 Remote Clipboard</h3>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn btn-secondary btn-sm" onClick={pullClipboard} disabled={loading}>
            {loading ? '...' : '↓ Pull from Client'}
          </button>
          <button className="btn btn-primary btn-sm" onClick={pushClipboard}>
            ↑ Push to Client
          </button>
          <button className="btn btn-secondary btn-sm" onClick={copyToLocal}>
            📋 Copy Locally
          </button>
        </div>
      </div>

      <textarea
        value={content}
        onChange={(e) => setContent(e.target.value)}
        placeholder="Remote clipboard content will appear here..."
        style={{
          flex: 1,
          resize: 'none',
          padding: 16,
          fontSize: 13,
          fontFamily: "'JetBrains Mono', monospace",
          color: 'var(--sc-text-primary)',
          background: 'var(--sc-bg-primary)',
          border: '1px solid var(--sc-border)',
          borderRadius: 'var(--sc-radius-sm)',
          outline: 'none',
          transition: 'border-color var(--sc-transition)',
        }}
        onFocus={(e) => e.target.style.borderColor = 'var(--sc-accent)'}
        onBlur={(e) => e.target.style.borderColor = 'var(--sc-border)'}
      />

      {toast && (
        <div className={`toast toast-${toast.type}`}>{toast.message}</div>
      )}
    </div>
  )
}
