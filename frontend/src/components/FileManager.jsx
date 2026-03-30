import { useState, useEffect, useCallback } from 'react'
import './FileManager.css'

/**
 * Remote file browser with upload/download support.
 */
export default function FileManager({ sendMessage, lastMessage }) {
  const [currentPath, setCurrentPath] = useState('')
  const [items, setItems] = useState([])
  const [parentPath, setParentPath] = useState('')
  const [isRoot, setIsRoot] = useState(true)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [transfers, setTransfers] = useState({}) // transfer_id -> {name, progress, total, type}
  const [dragOver, setDragOver] = useState(false)
  const [toast, setToast] = useState(null)

  // Request directory listing
  const navigateTo = useCallback((path) => {
    setLoading(true)
    setError(null)
    sendMessage({ type: 'file_list', path })
  }, [sendMessage])

  // Initial load
  useEffect(() => {
    navigateTo('')
  }, [navigateTo])

  // Handle incoming messages
  useEffect(() => {
    if (!lastMessage) return
    const { type } = lastMessage

    if (type === 'file_list_response') {
      setItems(lastMessage.items || [])
      setCurrentPath(lastMessage.path || '')
      setParentPath(lastMessage.parent || '')
      setIsRoot(lastMessage.is_root || false)
      setError(lastMessage.error || null)
      setLoading(false)
    }

    if (type === 'file_download_start') {
      setTransfers(prev => ({
        ...prev,
        [lastMessage.transfer_id]: {
          name: lastMessage.name,
          total: lastMessage.size,
          received: 0,
          type: 'download',
          chunks: [],
        }
      }))
    }

    if (type === 'file_download_complete') {
      const transfer = transfers[lastMessage.transfer_id]
      if (transfer) {
        // Combine chunks and trigger download
        const blob = new Blob(transfer.chunks)
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = transfer.name
        document.body.appendChild(a)
        a.click()
        document.body.removeChild(a)
        URL.revokeObjectURL(url)

        setTransfers(prev => {
          const next = { ...prev }
          delete next[lastMessage.transfer_id]
          return next
        })
        showToast(`Downloaded: ${transfer.name}`, 'success')
      }
    }

    if (type === 'file_download_error') {
      setTransfers(prev => {
        const next = { ...prev }
        delete next[lastMessage.transfer_id]
        return next
      })
      showToast(`Download failed: ${lastMessage.error}`, 'error')
    }

    if (type === 'file_upload_success') {
      setTransfers(prev => {
        const next = { ...prev }
        delete next[lastMessage.transfer_id]
        return next
      })
      showToast('Upload complete!', 'success')
      navigateTo(currentPath)
    }

    if (type === 'file_upload_error') {
      setTransfers(prev => {
        const next = { ...prev }
        delete next[lastMessage.transfer_id]
        return next
      })
      showToast(`Upload failed: ${lastMessage.error}`, 'error')
    }

    if (type === 'file_delete_response') {
      if (lastMessage.success) {
        showToast('Deleted successfully', 'success')
        navigateTo(currentPath)
      } else {
        showToast(`Delete failed: ${lastMessage.error}`, 'error')
      }
    }
  }, [lastMessage])

  // Handle binary file chunks
  const handleBinaryChunk = useCallback((transferId, chunkData) => {
    setTransfers(prev => {
      const transfer = prev[transferId]
      if (!transfer) return prev
      return {
        ...prev,
        [transferId]: {
          ...transfer,
          received: transfer.received + chunkData.byteLength,
          chunks: [...transfer.chunks, chunkData],
        }
      }
    })
  }, [])

  // Expose handleBinaryChunk for parent
  useEffect(() => {
    window.__fileManagerChunkHandler = handleBinaryChunk
    return () => { delete window.__fileManagerChunkHandler }
  }, [handleBinaryChunk])

  // Download a file
  const handleDownload = (item) => {
    const transferId = crypto.randomUUID()
    sendMessage({
      type: 'file_download_request',
      path: item.path,
      transfer_id: transferId,
    })
  }

  // Upload files via drag & drop or file input
  const handleUpload = async (files) => {
    for (const file of files) {
      const transferId = crypto.randomUUID()

      setTransfers(prev => ({
        ...prev,
        [transferId]: { name: file.name, total: file.size, received: 0, type: 'upload' }
      }))

      sendMessage({
        type: 'file_upload_start',
        transfer_id: transferId,
        name: file.name,
        path: currentPath,
      })

      // Read and send in chunks
      const buffer = await file.arrayBuffer()
      const chunkSize = 64 * 1024
      for (let offset = 0; offset < buffer.byteLength; offset += chunkSize) {
        const chunk = buffer.slice(offset, offset + chunkSize)
        // Convert to base64 for JSON transport
        const base64 = btoa(
          new Uint8Array(chunk).reduce((data, byte) => data + String.fromCharCode(byte), '')
        )
        sendMessage({
          type: 'file_upload_chunk',
          transfer_id: transferId,
          data: base64,
        })
      }

      sendMessage({
        type: 'file_upload_complete',
        transfer_id: transferId,
      })
    }
  }

  const handleDelete = (item) => {
    if (confirm(`Delete "${item.name}"? This cannot be undone.`)) {
      sendMessage({ type: 'file_delete', path: item.path })
    }
  }

  const handleDrop = (e) => {
    e.preventDefault()
    setDragOver(false)
    const files = Array.from(e.dataTransfer.files)
    if (files.length > 0) handleUpload(files)
  }

  const formatSize = (bytes) => {
    if (bytes === 0) return '—'
    const units = ['B', 'KB', 'MB', 'GB', 'TB']
    const i = Math.floor(Math.log(bytes) / Math.log(1024))
    return `${(bytes / Math.pow(1024, i)).toFixed(i > 0 ? 1 : 0)} ${units[i]}`
  }

  const formatDate = (ts) => {
    if (!ts) return '—'
    return new Date(ts * 1000).toLocaleDateString('en-US', {
      month: 'short', day: 'numeric', year: 'numeric',
      hour: '2-digit', minute: '2-digit',
    })
  }

  const showToast = (message, type) => {
    setToast({ message, type })
    setTimeout(() => setToast(null), 3000)
  }

  // Breadcrumb parts
  const pathParts = currentPath ? currentPath.replace(/\\/g, '/').split('/').filter(Boolean) : []

  return (
    <div
      className={`file-manager ${dragOver ? 'file-manager-dragover' : ''}`}
      onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
      onDragLeave={() => setDragOver(false)}
      onDrop={handleDrop}
    >
      {/* Toolbar */}
      <div className="fm-toolbar">
        <div className="fm-breadcrumb">
          <button
            className="fm-breadcrumb-item"
            onClick={() => navigateTo('')}
          >
            💻 Root
          </button>
          {pathParts.map((part, i) => {
            const fullPath = pathParts.slice(0, i + 1).join('/')
            return (
              <span key={i}>
                <span className="fm-breadcrumb-sep">/</span>
                <button
                  className="fm-breadcrumb-item"
                  onClick={() => navigateTo(fullPath)}
                >
                  {part}
                </button>
              </span>
            )
          })}
        </div>
        <div className="fm-toolbar-actions">
          <button
            className="btn btn-secondary btn-sm"
            onClick={() => navigateTo(currentPath)}
          >
            ↻ Refresh
          </button>
          <label className="btn btn-primary btn-sm" style={{ cursor: 'pointer' }}>
            ↑ Upload
            <input
              type="file"
              multiple
              style={{ display: 'none' }}
              onChange={(e) => handleUpload(Array.from(e.target.files))}
            />
          </label>
        </div>
      </div>

      {/* Transfer progress */}
      {Object.entries(transfers).length > 0 && (
        <div className="fm-transfers">
          {Object.entries(transfers).map(([id, t]) => (
            <div key={id} className="fm-transfer-item">
              <span className="fm-transfer-name">
                {t.type === 'download' ? '↓' : '↑'} {t.name}
              </span>
              <div className="fm-progress-bar">
                <div
                  className="fm-progress-fill"
                  style={{ width: `${t.total > 0 ? (t.received / t.total * 100) : 0}%` }}
                />
              </div>
              <span className="fm-transfer-size">{formatSize(t.received)} / {formatSize(t.total)}</span>
            </div>
          ))}
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="fm-error">⚠ {error}</div>
      )}

      {/* File listing */}
      <div className="fm-listing">
        {loading ? (
          <div className="fm-loading">
            <div className="spinner" style={{ width: 24, height: 24 }} />
            <span>Loading...</span>
          </div>
        ) : (
          <table className="fm-table">
            <thead>
              <tr>
                <th className="fm-col-name">Name</th>
                <th className="fm-col-size">Size</th>
                <th className="fm-col-modified">Modified</th>
                <th className="fm-col-actions">Actions</th>
              </tr>
            </thead>
            <tbody>
              {!isRoot && parentPath !== undefined && (
                <tr className="fm-row fm-row-parent" onClick={() => navigateTo(parentPath)}>
                  <td className="fm-col-name">
                    <span className="fm-icon">📂</span> ..
                  </td>
                  <td>—</td>
                  <td>—</td>
                  <td></td>
                </tr>
              )}
              {items.map((item, i) => (
                <tr
                  key={i}
                  className="fm-row"
                  onDoubleClick={() => item.is_dir && navigateTo(item.path)}
                >
                  <td className="fm-col-name">
                    <span className="fm-icon">{item.is_dir ? '📁' : '📄'}</span>
                    <span className="fm-filename">{item.name}</span>
                    {item.error && <span className="fm-access-denied">🔒</span>}
                  </td>
                  <td className="fm-col-size">{item.is_dir ? '—' : formatSize(item.size)}</td>
                  <td className="fm-col-modified">{formatDate(item.modified)}</td>
                  <td className="fm-col-actions">
                    {item.is_dir ? (
                      <button className="btn btn-secondary btn-sm" onClick={() => navigateTo(item.path)}>
                        Open
                      </button>
                    ) : (
                      <button className="btn btn-secondary btn-sm" onClick={() => handleDownload(item)}>
                        ↓ Download
                      </button>
                    )}
                    <button className="btn btn-danger btn-sm" onClick={() => handleDelete(item)}>
                      ✕
                    </button>
                  </td>
                </tr>
              ))}
              {items.length === 0 && !loading && (
                <tr>
                  <td colSpan={4} className="fm-empty">This directory is empty</td>
                </tr>
              )}
            </tbody>
          </table>
        )}
      </div>

      {/* Drag overlay */}
      {dragOver && (
        <div className="fm-drop-overlay">
          <div className="fm-drop-message">
            <span className="fm-drop-icon">📥</span>
            Drop files here to upload
          </div>
        </div>
      )}

      {toast && (
        <div className={`toast toast-${toast.type}`}>{toast.message}</div>
      )}
    </div>
  )
}
