import { useState, useRef, useCallback, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import useWebSocket from '../hooks/useWebSocket'
import ScreenCanvas from '../components/ScreenCanvas'
import FileManager from '../components/FileManager'
import RemoteTerminal from '../components/RemoteTerminal'
import SystemInfo from '../components/SystemInfo'
import ProcessManager from '../components/ProcessManager'
import ClipboardSync from '../components/ClipboardSync'
import ActionsManager from '../components/ActionsManager'
import './SessionPage.css'

const DEFAULT_WS_BASE = `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}`
const WS_BASE = import.meta.env.VITE_WS_BASE_URL || DEFAULT_WS_BASE

const TABS = [
  { id: 'screen', label: '🖥 Screen', icon: 'screen' },
  { id: 'files', label: '📁 Files', icon: 'files' },
  { id: 'terminal', label: '⌨ Terminal', icon: 'terminal' },
  { id: 'system', label: '⚙ System', icon: 'system' },
  { id: 'processes', label: '📊 Processes', icon: 'processes' },
  { id: 'clipboard', label: '📋 Clipboard', icon: 'clipboard' },
  { id: 'actions', label: '🛠 Actions', icon: 'actions' },
]

export default function SessionPage() {
  const { sessionId } = useParams()
  const navigate = useNavigate()
  const canvasRef = useRef(null)

  const [activeTab, setActiveTab] = useState('screen')
  const [clientConnected, setClientConnected] = useState(false)
  const [agentConnected, setAgentConnected] = useState(false)
  const [sessionEnded, setSessionEnded] = useState(false)
  const [lastMessage, setLastMessage] = useState(null)
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [lowBandwidth, setLowBandwidth] = useState(() => {
    return localStorage.getItem(`sc_low_bw_${sessionId}`) === 'true'
  })
  const [streamingEnabled, setStreamingEnabled] = useState(() => {
    return localStorage.getItem(`sc_stream_en_${sessionId}`) !== 'false'
  })
  
  const [cameraSnapshot, setCameraSnapshot] = useState(null)
  const [showCameraModal, setShowCameraModal] = useState(false)

  // Retrieve auth token
  const token = localStorage.getItem('access_token')
  const wsUrl = token
    ? `${WS_BASE}/ws/session/${sessionId}/?token=${token}&role=agent`
    : null

  // Handle JSON messages
  const handleMessage = useCallback((data) => {
    const { type } = data
    // Removed diagnostic logging from hot path to save main-thread CPU

    if (type === 'connection_status') {
      if (data.role === 'client') {
        setClientConnected(data.status === 'connected')
      }
    }

    if (type === 'session_ended') {
      setSessionEnded(true)
      setTimeout(() => navigate('/dashboard'), 3000)
      return
    }

    // Forward all messages to active tab components
    setLastMessage(data)
  }, [navigate])

  // Handle binary messages (screen frames, file chunks)
  const handleBinaryMessage = useCallback((arrayBuffer) => {
    if (arrayBuffer.byteLength < 13) return

    // Use a view for header and subarrays for data payloads to avoid expensive memory copies (slice)
    const uint8 = new Uint8Array(arrayBuffer)
    const msgType = uint8[0]

    if (msgType === 0x01) {
      // Screen frame: [type(1)] [width(2)] [height(2)] [timestamp(8)] [jpeg...]
      const dv = new DataView(arrayBuffer)
      const width = dv.getUint16(1)
      const height = dv.getUint16(3)
      const jpegData = uint8.subarray(13) // Zero-copy view
      canvasRef.current?.drawFrame(jpegData, width, height)
    }

    if (msgType === 0x02) {
      // File chunk: [type(1)] [transfer_id(36)] [data...]
      const decoder = new TextDecoder()
      const transferId = decoder.decode(uint8.subarray(1, 37))
      const chunkData = uint8.subarray(37) // Zero-copy view
      // Forward to FileManager via global handler
      window.__fileManagerChunkHandler?.(transferId, chunkData)
    }

    if (msgType === 0x03) {
      // Camera snapshot: [type(1)] [timestamp(8)] [jpeg...]
      const jpegData = uint8.subarray(9) // Header is 9 bytes for Camera Snap
      const blob = new Blob([jpegData], { type: 'image/jpeg' })
      const url = URL.createObjectURL(blob)
      setCameraSnapshot(url)
      setShowCameraModal(true)
    }
  }, [])

  const { sendMessage, isConnected, disconnect } = useWebSocket(wsUrl, {
    onMessage: handleMessage,
    onBinaryMessage: handleBinaryMessage,
  })

  useEffect(() => {
    if (isConnected) {
      setAgentConnected(true)
    } else {
      setAgentConnected(false)
    }
  }, [isConnected])

  const handleMouseEvent = useCallback((type, data) => {
    sendMessage({ type, ...data })
  }, [sendMessage])

  const handleKeyEvent = useCallback((data) => {
    sendMessage({ type: 'key_press', ...data })
  }, [sendMessage])

  const handleScrollEvent = useCallback((data) => {
    sendMessage({ type: 'scroll', ...data })
  }, [sendMessage])

  const handleEndSession = () => {
    sendMessage({ type: 'session_end' })
  }

  const handleBack = () => {
    disconnect()
    navigate('/dashboard')
  }

  const toggleFullscreen = () => {
    const el = document.querySelector('.session-page')
    if (!document.fullscreenElement) {
      el?.requestFullscreen?.()
      setIsFullscreen(true)
    } else {
      document.exitFullscreen?.()
      setIsFullscreen(false)
    }
  }

  const toggleLowBandwidth = () => {
    const newVal = !lowBandwidth
    setLowBandwidth(newVal)
    localStorage.setItem(`sc_low_bw_${sessionId}`, newVal)
    sendMessage({ type: 'bandwidth_mode', enabled: newVal })
  }

  const toggleStreaming = () => {
    const newVal = !streamingEnabled
    setStreamingEnabled(newVal)
    localStorage.setItem(`sc_stream_en_${sessionId}`, newVal)
    sendMessage({ type: 'streaming_toggle', enabled: newVal })
  }

  // Sync state with agent on initial connection or reconnection
  useEffect(() => {
    if (isConnected) {
      // Small delay to ensure agent is ready for control messages
      const timer = setTimeout(() => {
        sendMessage({ type: 'bandwidth_mode', enabled: lowBandwidth })
        sendMessage({ type: 'streaming_toggle', enabled: streamingEnabled })
      }, 500)
      return () => clearTimeout(timer)
    }
  }, [isConnected, lowBandwidth, streamingEnabled, sendMessage])

  useEffect(() => {
    // Cleanup blob URL when modal closes or component unmounts
    return () => {
      if (cameraSnapshot) URL.revokeObjectURL(cameraSnapshot)
    }
  }, [cameraSnapshot])

  useEffect(() => {
    const handler = () => setIsFullscreen(!!document.fullscreenElement)
    document.addEventListener('fullscreenchange', handler)
    return () => document.removeEventListener('fullscreenchange', handler)
  }, [])

  if (sessionEnded) {
    return (
      <div className="session-page">
        <div className="session-ended-overlay">
          <div className="session-ended-card glass-card">
            <span style={{ fontSize: 48 }}>👋</span>
            <h3>Session Ended</h3>
            <p>Redirecting to dashboard...</p>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="session-page">
      {/* Toolbar */}
      <div className="session-toolbar">
        <div className="session-toolbar-left">
          <button className="btn btn-secondary btn-sm" onClick={handleBack}>
            ← Back
          </button>
          <div className="session-toolbar-info">
            <code className="session-id-display">
              {sessionId?.substring(0, 8)}...
            </code>
            <div className="toolbar-status-group">
              <span className={`badge ${isConnected ? 'badge-active' : 'badge-ended'}`}>
                <span className={`pulse-dot ${isConnected ? 'pulse-dot-success' : 'pulse-dot-danger'}`} />
                {isConnected ? 'Connected' : 'Disconnected'}
              </span>
              <span className={`badge ${clientConnected ? 'badge-active' : 'badge-waiting'}`}>
                <span className={`pulse-dot ${clientConnected ? 'pulse-dot-success' : 'pulse-dot-warning'}`} />
                Client: {clientConnected ? 'connected' : 'waiting'}
              </span>
            </div>
          </div>
        </div>
        <div className="session-toolbar-right">
          {activeTab === 'screen' && (
            <>
              <button 
                className={`btn btn-sm ${streamingEnabled ? 'btn-secondary' : 'btn-primary'}`} 
                onClick={toggleStreaming}
                title="Toggles the screen stream on/off to save bandwidth"
              >
                {streamingEnabled ? '⏹ Stop Stream' : '▶ Start Stream'}
              </button>
              <button 
                className={`btn btn-sm ${lowBandwidth ? 'btn-primary' : 'btn-secondary'}`} 
                onClick={toggleLowBandwidth}
                title="Lowers FPS and Quality to save mobile data"
              >
                {lowBandwidth ? '📶 Low Bandwidth: ON' : '📶 Low Bandwidth: OFF'}
              </button>
              <button className="btn btn-secondary btn-sm" onClick={toggleFullscreen}>
                {isFullscreen ? '⊡ Exit Fullscreen' : '⊞ Fullscreen'}
              </button>
            </>
          )}
          <button className="btn btn-danger btn-sm" onClick={handleEndSession}>
            ■ End Session
          </button>
        </div>
      </div>

      {/* Tab bar */}
      <div className="session-tabs">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            className={`session-tab ${activeTab === tab.id ? 'session-tab-active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="session-content">
        {activeTab === 'screen' && (
          <div className="session-screen-area">
            {clientConnected ? (
              <ScreenCanvas
                ref={canvasRef}
                onMouseEvent={handleMouseEvent}
                onKeyEvent={handleKeyEvent}
                onScrollEvent={handleScrollEvent}
              />
            ) : (
              <div className="session-waiting fade-in">
                <div className="waiting-animation">
                  <div className="waiting-ring" />
                  <div className="waiting-ring waiting-ring-2" />
                  <div className="waiting-ring waiting-ring-3" />
                  <svg className="waiting-icon" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
                    <rect x="2" y="3" width="20" height="14" rx="2" />
                    <path d="M8 21h8M12 17v4" />
                  </svg>
                </div>
                <h3>Waiting for client to connect...</h3>
                <p>Share the session ID and token with the person who needs support.</p>
              </div>
            )}
          </div>
        )}

        {activeTab === 'files' && (
          <FileManager sendMessage={sendMessage} lastMessage={lastMessage} />
        )}

        {activeTab === 'terminal' && (
          <RemoteTerminal sendMessage={sendMessage} lastMessage={lastMessage} />
        )}

        {activeTab === 'system' && (
          <SystemInfo sendMessage={sendMessage} lastMessage={lastMessage} />
        )}

        {activeTab === 'processes' && (
          <ProcessManager sendMessage={sendMessage} lastMessage={lastMessage} />
        )}

        {activeTab === 'clipboard' && (
          <ClipboardSync sendMessage={sendMessage} lastMessage={lastMessage} />
        )}

        {activeTab === 'actions' && (
          <ActionsManager sendMessage={sendMessage} lastMessage={lastMessage} />
        )}
      </div>

      {/* Camera Snapshot Modal */}
      {showCameraModal && (
        <div className="camera-modal-overlay fade-in" onClick={() => setShowCameraModal(false)}>
          <div className="camera-modal-card glass-card" onClick={e => e.stopPropagation()}>
            <div className="camera-modal-header">
              <h3>📸 Remote Camera Snapshot</h3>
              <button className="btn-close" onClick={() => setShowCameraModal(false)}>×</button>
            </div>
            <div className="camera-modal-body">
              {cameraSnapshot ? (
                <img src={cameraSnapshot} alt="Remote Snapshot" className="snapshot-img" />
              ) : (
                <div className="snapshot-placeholder">Loading snapshot...</div>
              )}
            </div>
            <div className="camera-modal-footer">
              <button className="btn btn-primary" onClick={() => setShowCameraModal(false)}>Close</button>
              <a href={cameraSnapshot} download={`snapshot_${Date.now()}.jpg`} className="btn btn-secondary">
                💾 Download
              </a>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
