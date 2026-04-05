import { useState, useEffect, useCallback, useRef } from 'react'
import api from '../api/client'
import SessionCard from '../components/SessionCard'
import './DashboardPage.css'

export default function DashboardPage() {
  const [sessions, setSessions] = useState([])
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [creating, setCreating] = useState(false)
  const [toast, setToast] = useState(null)
  const [nextPageUrl, setNextPageUrl] = useState(null)
  const [streamConnected, setStreamConnected] = useState(false)
  const fetchInFlightRef = useRef(false)

  const fetchSessions = useCallback(async () => {
    // Skip overlapping polls to avoid piling up pending requests.
    if (fetchInFlightRef.current) return
    fetchInFlightRef.current = true
    try {
      const res = await api.get('/api/sessions/list/')
      const payload = res.data
      const items = Array.isArray(payload) ? payload : (payload.results || [])
      const next = Array.isArray(payload) ? null : (payload.next || null)
      setSessions(items)
      setNextPageUrl(next)
    } catch (err) {
      console.error('Failed to fetch sessions:', err)
    } finally {
      setLoading(false)
      fetchInFlightRef.current = false
    }
  }, [])

  const handleLoadMore = async () => {
    if (!nextPageUrl || loadingMore) return
    setLoadingMore(true)
    try {
      const res = await api.get(nextPageUrl)
      const payload = res.data
      const items = Array.isArray(payload) ? payload : (payload.results || [])
      const next = Array.isArray(payload) ? null : (payload.next || null)
      setSessions((prev) => [...prev, ...items])
      setNextPageUrl(next)
    } catch (err) {
      console.error('Failed to load more sessions:', err)
      showToast('Failed to load more sessions', 'error')
    } finally {
      setLoadingMore(false)
    }
  }

  useEffect(() => {
    const token = localStorage.getItem('access_token')
    if (!token || typeof EventSource === 'undefined') return

    const source = new EventSource(`/api/sessions/stream/?token=${encodeURIComponent(token)}`)
    source.addEventListener('sessions', (e) => {
      try {
        const rows = JSON.parse(e.data)
        if (Array.isArray(rows)) {
          setSessions(rows)
          setNextPageUrl(null) // Stream endpoint is a snapshot feed
        }
      } catch (err) {
        console.error('Failed to parse session stream payload', err)
      }
    })
    source.onopen = () => setStreamConnected(true)
    source.onerror = () => setStreamConnected(false)

    return () => {
      source.close()
      setStreamConnected(false)
    }
  }, [])

  useEffect(() => {
    if (streamConnected) return
    let timerId = null
    let cancelled = false

    const scheduleNext = () => {
      if (cancelled) return
      // Use slower cadence when tab is hidden to reduce backend load.
      const delay = document.hidden ? 15000 : 5000
      timerId = setTimeout(async () => {
        await fetchSessions()
        scheduleNext()
      }, delay)
    }

    const onVisibilityChange = () => {
      if (timerId) clearTimeout(timerId)
      // Refresh immediately when returning to the tab.
      if (!document.hidden) {
        fetchSessions()
      }
      scheduleNext()
    }

    fetchSessions()
    scheduleNext()
    document.addEventListener('visibilitychange', onVisibilityChange)

    return () => {
      cancelled = true
      if (timerId) clearTimeout(timerId)
      document.removeEventListener('visibilitychange', onVisibilityChange)
    }
  }, [fetchSessions, streamConnected])

  const handleCreateSession = async () => {
    setCreating(true)
    try {
      const res = await api.post('/api/sessions/')
      setSessions((prev) => [res.data, ...prev])
      showToast('Session created successfully!', 'success')
    } catch {
      showToast('Failed to create session', 'error')
    } finally {
      setCreating(false)
    }
  }

  const handleEndSession = async (sessionId) => {
    try {
      await api.post(`/api/sessions/${sessionId}/end/`)
      setSessions((prev) =>
        prev.map((s) => (s.id === sessionId ? { ...s, status: 'ended' } : s))
      )
      showToast('Session ended', 'success')
    } catch {
      showToast('Failed to end session', 'error')
    }
  }

  const handleRestartSession = async (sessionId) => {
    try {
      await api.post(`/api/sessions/${sessionId}/restart/`)
      setSessions((prev) =>
        prev.map((s) => (s.id === sessionId ? { ...s, status: 'waiting' } : s))
      )
      showToast('Session restarted', 'success')
    } catch {
      showToast('Failed to restart session', 'error')
    }
  }

  const handleCopyLink = (session) => {
    // Build the agent command for the client
    const wsProtocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const wsHost = window.location.host
    const agentCmd = `python agent.py --server ${wsProtocol}://${wsHost} --session ${session.id} --token ${session.token}`
    
    navigator.clipboard.writeText(agentCmd).then(() => {
      showToast('Agent command copied to clipboard!', 'success')
    }).catch(() => {
      // Fallback — copy join URL instead
      const joinUrl = `${window.location.origin}/api/sessions/${session.id}/join/?token=${session.token}`
      navigator.clipboard.writeText(joinUrl)
      showToast('Join URL copied to clipboard!', 'success')
    })
  }

  const showToast = (message, type) => {
    setToast({ message, type })
    setTimeout(() => setToast(null), 3000)
  }

  const activeSessions = sessions.filter((s) => s.status !== 'ended')
  const endedSessions = sessions.filter((s) => s.status === 'ended')

  return (
    <div className="dashboard-page fade-in">
      <div className="dashboard-container">
        {/* Header */}
        <div className="dashboard-header">
          <div>
            <h1 className="dashboard-title">Support Sessions</h1>
            <p className="dashboard-subtitle">
              Manage and monitor your remote support sessions
            </p>
          </div>
          <button
            className="btn btn-primary btn-lg create-session-btn"
            onClick={handleCreateSession}
            disabled={creating}
            id="create-session-btn"
          >
            {creating ? (
              <>
                <div className="spinner" />
                Creating...
              </>
            ) : (
              <>
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                  <path d="M12 5v14M5 12h14" />
                </svg>
                New Session
              </>
            )}
          </button>
        </div>

        {/* Active sessions */}
        <section className="dashboard-section">
          <h2 className="section-title">
            <span className="pulse-dot pulse-dot-success" />
            Active Sessions
            <span className="section-count">{activeSessions.length}</span>
          </h2>

          {loading ? (
            <div className="dashboard-loading">
              <div className="spinner" style={{ width: 28, height: 28 }} />
              <span>Loading sessions...</span>
            </div>
          ) : activeSessions.length === 0 ? (
            <div className="dashboard-empty glass-card">
              <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" opacity="0.3">
                <rect x="2" y="3" width="20" height="14" rx="2"/>
                <path d="M8 21h8M12 17v4"/>
              </svg>
              <p>No active sessions</p>
              <span>Create a new session to get started</span>
            </div>
          ) : (
            <div className="sessions-grid">
              {activeSessions.map((session) => (
                <SessionCard
                  key={session.id}
                  session={session}
                  onEnd={handleEndSession}
                  onRestart={handleRestartSession}
                  onCopyLink={handleCopyLink}
                />
              ))}
            </div>
          )}
        </section>

        {/* Ended sessions */}
        {endedSessions.length > 0 && (
          <section className="dashboard-section">
            <h2 className="section-title">
              Recent History
              <span className="section-count">{endedSessions.length}</span>
            </h2>
            <div className="sessions-grid">
              {endedSessions.slice(0, 6).map((session) => (
                <SessionCard
                  key={session.id}
                  session={session}
                  onEnd={handleEndSession}
                  onRestart={handleRestartSession}
                  onCopyLink={handleCopyLink}
                />
              ))}
            </div>
          </section>
        )}

        {nextPageUrl && (
          <div style={{ display: 'flex', justifyContent: 'center', marginTop: 20 }}>
            <button
              className="btn btn-secondary"
              onClick={handleLoadMore}
              disabled={loadingMore}
            >
              {loadingMore ? 'Loading...' : 'Load More'}
            </button>
          </div>
        )}
      </div>

      {/* Toast */}
      {toast && (
        <div className={`toast toast-${toast.type}`}>
          {toast.message}
        </div>
      )}
    </div>
  )
}
