 import { useState, useEffect, useCallback, useMemo } from 'react'
import BrowserProfileDetails from './BrowserProfileDetails'
import './BrowserManager.css'

export default function BrowserManager({ sendMessage, lastMessage }) {
  const [browsers, setBrowsers] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [search, setSearch] = useState('')
  const [copiedPath, setCopiedPath] = useState(null)
  
  // Profile deep dive state
  const [selectedBrowser, setSelectedBrowser] = useState(null)
  const [profileData, setProfileData] = useState([])
  const [profileLoading, setProfileLoading] = useState(false)

  const refreshBrowsers = useCallback(() => {
    setLoading(true)
    setError(null)
    sendMessage({ type: 'browser_list_request' })
  }, [sendMessage])

  useEffect(() => {
    refreshBrowsers()
  }, [refreshBrowsers])

  useEffect(() => {
    if (lastMessage?.type === 'browser_list_response') {
      setLoading(false)
      if (lastMessage.error) {
        setError(lastMessage.error)
      } else {
        // Sort: Default first, then alphabetical
        const sorted = (lastMessage.browsers || []).sort((a, b) => {
          if (a.is_default && !b.is_default) return -1
          if (!a.is_default && b.is_default) return 1
          return a.name.localeCompare(b.name)
        })
        setBrowsers(sorted)
      }
    } else if (lastMessage?.type === 'browser_profile_response') {
      setProfileLoading(false)
      setProfileData(lastMessage.profiles || [])
    }
  }, [lastMessage])

  const filteredBrowsers = useMemo(() => {
    if (!search) return browsers
    const s = search.toLowerCase()
    return browsers.filter(b => 
      b.name.toLowerCase().includes(s) || 
      b.path.toLowerCase().includes(s)
    )
  }, [browsers, search])

  const copyPath = (path) => {
    navigator.clipboard.writeText(path)
    setCopiedPath(path)
    setTimeout(() => setCopiedPath(null), 2000)
  }

  const handleDeepDive = (browser) => {
    setSelectedBrowser(browser)
    setProfileData([])
    setProfileLoading(true)
    sendMessage({
      type: 'browser_profile_request',
      name: browser.name,
      path: browser.path
    })
  }

  const getBrowserIcon = (name) => {
    const n = name.toLowerCase()
    if (n.includes('chrome')) return '🌐'
    if (n.includes('firefox')) return '🦊'
    if (n.includes('edge')) return '🟦'
    if (n.includes('opera')) return '⭕'
    if (n.includes('brave')) return '🦁'
    if (n.includes('safari')) return '🧭'
    if (n.includes('explorer')) return '🌍'
    return '🔗'
  }

  return (
    <div className="browser-manager fade-in">
      {/* Header Toolbar */}
      <div className="bm-toolbar">
        <div className="bm-toolbar-left">
          <div className="bm-search-wrapper">
            <input 
              type="text" 
              className="bm-search" 
              placeholder="Search browsers..." 
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            <span className="bm-search-icon">🔍</span>
          </div>
          <span className="bm-count">
            {filteredBrowsers.length} {filteredBrowsers.length === 1 ? 'Browser' : 'Browsers'}
          </span>
        </div>
        
        <button 
          className={`btn btn-secondary ${loading ? 'btn-loading' : ''}`} 
          onClick={refreshBrowsers}
          disabled={loading}
        >
          {loading ? 'Scanning...' : '↻ Refresh List'}
        </button>
      </div>

      {error && (
        <div className="bm-error glass-card toast-error fade-in">
          <span>⚠️ <b>Error:</b> {error}</span>
        </div>
      )}

      {loading && !browsers.length ? (
        <div className="bm-loading glass-card">
          <div className="spinner" style={{ width: 32, height: 32 }}></div>
          <p>Querying remote registry for installed browsers...</p>
        </div>
      ) : (
        <div className="bm-grid">
          {filteredBrowsers.map((browser, index) => (
            <div 
              key={index} 
              className={`bm-card glass-card ${browser.is_default ? 'bm-card-default' : ''}`}
              style={{ animationDelay: `${index * 50}ms` }}
            >
              {browser.is_default && (
                <div className="bm-default-badge badge badge-active">
                  ⭐ Default Browser
                </div>
              )}
              
              <div className="bm-card-header">
                <div className="bm-icon-box">
                  <span className="bm-icon">{getBrowserIcon(browser.name)}</span>
                </div>
                <div className="bm-title-group">
                  <h4 className="bm-name">{browser.name}</h4>
                  <span className="bm-version-pill">{browser.version || 'System'}</span>
                </div>
              </div>

              <div className="bm-path-section">
                <div className="bm-path-label">Executable Path</div>
                <div className="bm-path-bar">
                  <code className="bm-path" title={browser.path}>{browser.path}</code>
                  <button 
                    className="bm-copy-btn" 
                    onClick={() => copyPath(browser.path)}
                    title="Copy Path"
                  >
                    {copiedPath === browser.path ? '✅' : '📋'}
                  </button>
                </div>
              </div>
              <div className="bm-card-footer">
                <span className="bm-tag-info">Detected</span>
                <button 
                  className="btn btn-sm btn-ghost bm-deep-dive-btn"
                  onClick={() => handleDeepDive(browser)}
                >
                  🕵️ Deep Dive
                </button>
              </div>
            </div>
          ))}

          {!filteredBrowsers.length && !loading && (
            <div className="bm-empty glass-card">
              <span className="bm-empty-icon">{search ? '🔍' : '🚫'}</span>
              <p>{search ? `No browsers matching "${search}"` : 'No browsers detected on the remote system'}</p>
              {search && <button className="btn btn-sm" onClick={() => setSearch('')}>Clear Search</button>}
            </div>
          )}
        </div>
      )}

      {selectedBrowser && (
        <BrowserProfileDetails 
          browser={selectedBrowser}
          profiles={profileData}
          loading={profileLoading}
          onClose={() => setSelectedBrowser(null)}
        />
      )}
    </div>
  )
}
