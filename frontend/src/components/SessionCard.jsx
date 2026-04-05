import { useNavigate } from 'react-router-dom'
import './SessionCard.css'

export default function SessionCard({ session, onEnd, onRestart, onCopyLink }) {
  const navigate = useNavigate()

  const statusClass = {
    waiting: 'badge-waiting',
    active: 'badge-active',
    ended: 'badge-ended',
  }[session.status] || 'badge-ended'

  const dotClass = {
    waiting: 'pulse-dot-warning',
    active: 'pulse-dot-success',
    ended: '',
  }[session.status]

  const timeAgo = (dateStr) => {
    const diff = Date.now() - new Date(dateStr).getTime()
    const mins = Math.floor(diff / 60000)
    if (mins < 1) return 'Just now'
    if (mins < 60) return `${mins}m ago`
    const hrs = Math.floor(mins / 60)
    if (hrs < 24) return `${hrs}h ago`
    return `${Math.floor(hrs / 24)}d ago`
  }

  const handleView = () => {
    if (session.status !== 'ended') {
      navigate(`/session/${session.id}`)
    }
  }

  return (
    <div className="session-card glass-card fade-in" id={`session-${session.id}`}>
      <div className="session-card-header">
        <div className="session-card-id">
          <code>{session.id.slice(0, 8)}...</code>
        </div>
        <div className={`badge ${statusClass}`}>
          {dotClass && <span className={`pulse-dot ${dotClass}`} />}
          {session.status}
        </div>
      </div>

      <div className="session-card-meta">
        <div className="session-card-meta-item">
          <span className="meta-label">Created</span>
          <span className="meta-value">{timeAgo(session.created_at)}</span>
        </div>
        <div className="session-card-meta-item">
          <span className="meta-label">Client</span>
          <span className="meta-value">
            {session.client_connected ? (
              <span style={{ color: 'var(--sc-success)' }}>● Connected</span>
            ) : (
              <span style={{ color: 'var(--sc-text-muted)' }}>○ Waiting</span>
            )}
          </span>
        </div>
      </div>

      <div className="session-card-actions">
        {session.status !== 'ended' && (
          <>
            <button
              className="btn btn-primary btn-sm"
              onClick={handleView}
              id={`view-session-${session.id}`}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                <circle cx="12" cy="12" r="3"/>
              </svg>
              View
            </button>
            <button
              className="btn btn-secondary btn-sm"
              onClick={() => onCopyLink(session)}
              id={`copy-link-${session.id}`}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <rect x="9" y="9" width="13" height="13" rx="2"/>
                <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/>
              </svg>
              Copy Link
            </button>
            <button
              className="btn btn-danger btn-sm"
              onClick={() => onEnd(session.id)}
              id={`end-session-${session.id}`}
            >
              End
            </button>
          </>
        )}
        
        {session.status === 'ended' && (
          <button
            className="btn btn-secondary btn-sm"
            onClick={() => onRestart(session.id)}
            id={`restart-session-${session.id}`}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M23 4v6h-6M1 20v-6h6"/>
              <path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/>
            </svg>
            Restart
          </button>
        )}
      </div>
    </div>
  )
}
