import { useState, useEffect, useCallback } from 'react'
import './ProcessManager.css'

/**
 * Remote process manager — view and kill running processes.
 */
export default function ProcessManager({ sendMessage, lastMessage }) {
  const [processes, setProcesses] = useState([])
  const [totalCount, setTotalCount] = useState(0)
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState('')
  const [sortBy, setSortBy] = useState('memory_mb')
  const [sortDir, setSortDir] = useState('desc')
  const [toast, setToast] = useState(null)

  const requestProcesses = useCallback(() => {
    sendMessage({ type: 'process_list_request' })
  }, [sendMessage])

  useEffect(() => {
    requestProcesses()
    const interval = setInterval(requestProcesses, 5000)
    return () => clearInterval(interval)
  }, [requestProcesses])

  useEffect(() => {
    if (!lastMessage) return

    if (lastMessage.type === 'process_list') {
      setProcesses(lastMessage.processes || [])
      setTotalCount(lastMessage.total_count || 0)
      setLoading(false)
    }

    if (lastMessage.type === 'process_kill_response') {
      if (lastMessage.success) {
        showToast(`Killed: ${lastMessage.name} (PID ${lastMessage.pid})`, 'success')
        requestProcesses()
      } else {
        showToast(`Failed: ${lastMessage.error}`, 'error')
      }
    }
  }, [lastMessage, requestProcesses])

  const handleKill = (proc) => {
    if (confirm(`Kill process "${proc.name}" (PID ${proc.pid})?`)) {
      sendMessage({ type: 'process_kill', pid: proc.pid })
    }
  }

  const handleSort = (column) => {
    if (sortBy === column) {
      setSortDir(prev => prev === 'asc' ? 'desc' : 'asc')
    } else {
      setSortBy(column)
      setSortDir('desc')
    }
  }

  const showToast = (message, type) => {
    setToast({ message, type })
    setTimeout(() => setToast(null), 3000)
  }

  // Filter and sort
  const filtered = processes
    .filter(p => !filter || p.name.toLowerCase().includes(filter.toLowerCase()) ||
      String(p.pid).includes(filter))
    .sort((a, b) => {
      const va = a[sortBy] || 0
      const vb = b[sortBy] || 0
      if (typeof va === 'string') return sortDir === 'asc' ? va.localeCompare(vb) : vb.localeCompare(va)
      return sortDir === 'asc' ? va - vb : vb - va
    })

  const sortIcon = (col) => {
    if (sortBy !== col) return ''
    return sortDir === 'asc' ? ' ↑' : ' ↓'
  }

  return (
    <div className="process-manager">
      {/* Toolbar */}
      <div className="pm-toolbar">
        <div className="pm-toolbar-left">
          <input
            className="pm-search"
            type="text"
            placeholder="Search processes..."
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          />
          <span className="pm-count">{filtered.length} / {totalCount} processes</span>
        </div>
        <button className="btn btn-secondary btn-sm" onClick={requestProcesses}>
          ↻ Refresh
        </button>
      </div>

      {/* Process table */}
      <div className="pm-table-container">
        {loading ? (
          <div className="pm-loading">
            <div className="spinner" style={{ width: 24, height: 24 }} />
            <span>Loading processes...</span>
          </div>
        ) : (
          <table className="pm-table">
            <thead>
              <tr>
                <th className="pm-col-pid" onClick={() => handleSort('pid')}>
                  PID{sortIcon('pid')}
                </th>
                <th className="pm-col-name" onClick={() => handleSort('name')}>
                  Name{sortIcon('name')}
                </th>
                <th className="pm-col-cpu" onClick={() => handleSort('cpu_percent')}>
                  CPU %{sortIcon('cpu_percent')}
                </th>
                <th className="pm-col-mem" onClick={() => handleSort('memory_mb')}>
                  Memory{sortIcon('memory_mb')}
                </th>
                <th className="pm-col-user">User</th>
                <th className="pm-col-actions">Actions</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((proc) => (
                <tr key={proc.pid} className="pm-row">
                  <td className="pm-col-pid pm-mono">{proc.pid}</td>
                  <td className="pm-col-name">{proc.name}</td>
                  <td className="pm-col-cpu">
                    <div className="pm-cpu-bar">
                      <div
                        className="pm-cpu-fill"
                        style={{
                          width: `${Math.min(proc.cpu_percent || 0, 100)}%`,
                          background: (proc.cpu_percent || 0) > 50 ? 'var(--sc-danger)' : 'var(--sc-accent)'
                        }}
                      />
                    </div>
                    <span className="pm-mono">{(proc.cpu_percent || 0).toFixed(1)}</span>
                  </td>
                  <td className="pm-col-mem pm-mono">{proc.memory_mb} MB</td>
                  <td className="pm-col-user">{proc.username || '—'}</td>
                  <td className="pm-col-actions">
                    <button
                      className="btn btn-danger btn-sm"
                      onClick={() => handleKill(proc)}
                    >
                      Kill
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {toast && (
        <div className={`toast toast-${toast.type}`}>{toast.message}</div>
      )}
    </div>
  )
}
