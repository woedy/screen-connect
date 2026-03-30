import { useState, useEffect, useCallback } from 'react'
import './SystemInfo.css'

/**
 * System information dashboard — shows remote machine details.
 */
export default function SystemInfo({ sendMessage, lastMessage }) {
  const [info, setInfo] = useState(null)
  const [loading, setLoading] = useState(true)

  const requestInfo = useCallback(() => {
    setLoading(true)
    sendMessage({ type: 'system_info_request' })
  }, [sendMessage])

  useEffect(() => {
    requestInfo()
    const interval = setInterval(requestInfo, 10000) // Refresh every 10s
    return () => clearInterval(interval)
  }, [requestInfo])

  useEffect(() => {
    if (!lastMessage || lastMessage.type !== 'system_info') return
    setInfo(lastMessage)
    setLoading(false)
  }, [lastMessage])

  const formatBytes = (bytes) => {
    if (!bytes) return '—'
    const units = ['B', 'KB', 'MB', 'GB', 'TB']
    const i = Math.floor(Math.log(bytes) / Math.log(1024))
    return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${units[i]}`
  }

  const formatUptime = (bootTime) => {
    if (!bootTime) return '—'
    const seconds = Math.floor(Date.now() / 1000 - bootTime)
    const days = Math.floor(seconds / 86400)
    const hours = Math.floor((seconds % 86400) / 3600)
    const mins = Math.floor((seconds % 3600) / 60)
    if (days > 0) return `${days}d ${hours}h ${mins}m`
    if (hours > 0) return `${hours}h ${mins}m`
    return `${mins}m`
  }

  if (loading && !info) {
    return (
      <div className="sysinfo-loading">
        <div className="spinner" style={{ width: 24, height: 24 }} />
        <span>Fetching system info...</span>
      </div>
    )
  }

  if (info?.error) {
    return <div className="sysinfo-error">⚠ {info.error}</div>
  }

  return (
    <div className="system-info">
      <div className="sysinfo-header">
        <h3>System Overview</h3>
        <button className="btn btn-secondary btn-sm" onClick={requestInfo}>
          ↻ Refresh
        </button>
      </div>

      <div className="sysinfo-grid">
        {/* Machine info */}
        <div className="sysinfo-card glass-card">
          <div className="sysinfo-card-header">
            <span className="sysinfo-card-icon">💻</span>
            <span className="sysinfo-card-title">Machine</span>
          </div>
          <div className="sysinfo-card-body">
            <div className="sysinfo-row">
              <span className="sysinfo-label">Hostname</span>
              <span className="sysinfo-value">{info?.hostname || '—'}</span>
            </div>
            <div className="sysinfo-row">
              <span className="sysinfo-label">OS</span>
              <span className="sysinfo-value">{info?.platform} {info?.platform_release}</span>
            </div>
            <div className="sysinfo-row">
              <span className="sysinfo-label">Architecture</span>
              <span className="sysinfo-value">{info?.architecture || '—'}</span>
            </div>
            <div className="sysinfo-row">
              <span className="sysinfo-label">User</span>
              <span className="sysinfo-value">{info?.username || '—'}</span>
            </div>
            <div className="sysinfo-row">
              <span className="sysinfo-label">IP Address</span>
              <span className="sysinfo-value sysinfo-mono">{info?.ip_address || '—'}</span>
            </div>
            {info?.boot_time && (
              <div className="sysinfo-row">
                <span className="sysinfo-label">Uptime</span>
                <span className="sysinfo-value">{formatUptime(info.boot_time)}</span>
              </div>
            )}
          </div>
        </div>

        {/* CPU */}
        {info?.cpu_count && (
          <div className="sysinfo-card glass-card">
            <div className="sysinfo-card-header">
              <span className="sysinfo-card-icon">⚡</span>
              <span className="sysinfo-card-title">CPU</span>
            </div>
            <div className="sysinfo-card-body">
              <div className="sysinfo-gauge">
                <div className="sysinfo-gauge-bar">
                  <div
                    className="sysinfo-gauge-fill"
                    style={{
                      width: `${info.cpu_percent || 0}%`,
                      background: (info.cpu_percent || 0) > 80 ? 'var(--sc-danger)' :
                        (info.cpu_percent || 0) > 50 ? 'var(--sc-warning)' : 'var(--sc-success)'
                    }}
                  />
                </div>
                <span className="sysinfo-gauge-label">{info.cpu_percent || 0}%</span>
              </div>
              <div className="sysinfo-row">
                <span className="sysinfo-label">Cores</span>
                <span className="sysinfo-value">{info.cpu_count}</span>
              </div>
              <div className="sysinfo-row">
                <span className="sysinfo-label">Processor</span>
                <span className="sysinfo-value">{info?.processor || '—'}</span>
              </div>
            </div>
          </div>
        )}

        {/* Memory */}
        {info?.memory_total && (
          <div className="sysinfo-card glass-card">
            <div className="sysinfo-card-header">
              <span className="sysinfo-card-icon">🧠</span>
              <span className="sysinfo-card-title">Memory</span>
            </div>
            <div className="sysinfo-card-body">
              <div className="sysinfo-gauge">
                <div className="sysinfo-gauge-bar">
                  <div
                    className="sysinfo-gauge-fill"
                    style={{
                      width: `${info.memory_percent || 0}%`,
                      background: (info.memory_percent || 0) > 85 ? 'var(--sc-danger)' :
                        (info.memory_percent || 0) > 60 ? 'var(--sc-warning)' : 'var(--sc-accent)'
                    }}
                  />
                </div>
                <span className="sysinfo-gauge-label">{info.memory_percent || 0}%</span>
              </div>
              <div className="sysinfo-row">
                <span className="sysinfo-label">Used</span>
                <span className="sysinfo-value">{formatBytes(info.memory_used)}</span>
              </div>
              <div className="sysinfo-row">
                <span className="sysinfo-label">Total</span>
                <span className="sysinfo-value">{formatBytes(info.memory_total)}</span>
              </div>
            </div>
          </div>
        )}

        {/* Disks */}
        {info?.disks?.length > 0 && (
          <div className="sysinfo-card glass-card">
            <div className="sysinfo-card-header">
              <span className="sysinfo-card-icon">💾</span>
              <span className="sysinfo-card-title">Storage</span>
            </div>
            <div className="sysinfo-card-body">
              {info.disks.map((disk, i) => (
                <div key={i} className="sysinfo-disk">
                  <div className="sysinfo-disk-header">
                    <span className="sysinfo-mono">{disk.device}</span>
                    <span className="sysinfo-label">{disk.fstype}</span>
                  </div>
                  <div className="sysinfo-gauge">
                    <div className="sysinfo-gauge-bar">
                      <div
                        className="sysinfo-gauge-fill"
                        style={{
                          width: `${disk.percent}%`,
                          background: disk.percent > 90 ? 'var(--sc-danger)' : 'var(--sc-accent)'
                        }}
                      />
                    </div>
                    <span className="sysinfo-gauge-label">{disk.percent}%</span>
                  </div>
                  <div className="sysinfo-disk-meta">
                    {formatBytes(disk.used)} / {formatBytes(disk.total)}
                    <span className="sysinfo-label"> — {formatBytes(disk.free)} free</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Network */}
        {info?.network_interfaces?.length > 0 && (
          <div className="sysinfo-card glass-card">
            <div className="sysinfo-card-header">
              <span className="sysinfo-card-icon">🌐</span>
              <span className="sysinfo-card-title">Network</span>
            </div>
            <div className="sysinfo-card-body">
              {info.network_interfaces.map((iface, i) => (
                <div key={i} className="sysinfo-row">
                  <span className="sysinfo-label">{iface.name}</span>
                  <span className="sysinfo-value sysinfo-mono">{iface.ip}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
