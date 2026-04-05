import { useState } from 'react'

export default function BrowserProfileDetails({ browser, profiles, onClose, loading }) {
  const [activeTab, setActiveTab] = useState('identity')

  if (!browser) return null

  const getSeverityColor = (score) => {
    if (score >= 4) return 'var(--sc-error)'
    if (score >= 2) return 'var(--sc-warning)'
    return 'var(--sc-success)'
  }

  return (
    <div className="bm-modal-overlay fade-in" onClick={onClose}>
      <div className="bm-modal glass-card" onClick={e => e.stopPropagation()}>
        <div className="bm-modal-header">
          <div className="bm-modal-title-group">
            <span className="bm-modal-icon">🔍</span>
            <h3 className="bm-modal-title">Deep Dive: {browser.name}</h3>
          </div>
          <button className="bm-modal-close" onClick={onClose}>&times;</button>
        </div>

        <div className="bm-modal-body">
          {loading ? (
            <div className="bm-modal-loading">
              <div className="spinner"></div>
              <p>Harvesting profile forensics from remote machine...</p>
            </div>
          ) : profiles.length === 0 ? (
            <div className="bm-modal-empty">
              <span className="bm-empty-icon">📂</span>
              <p>No accessible profiles found for this browser.</p>
            </div>
          ) : (
            <div className="bm-profile-container">
              <div className="bm-profile-sidebar">
                {profiles.map((profile, i) => (
                  <div 
                    key={i} 
                    className={`bm-profile-item ${activeTab === i ? 'active' : ''}`}
                    onClick={() => setActiveTab(i)}
                  >
                    <div className="bm-profile-avatar">
                      {profile.avatar_url ? (
                        <img src={profile.avatar_url} alt="" />
                      ) : (
                        <span>{profile.name[0]}</span>
                      )}
                    </div>
                    <div className="bm-profile-info">
                      <span className="bm-p-name">{profile.name}</span>
                      <span className="bm-p-folder">{profile.folder}</span>
                    </div>
                  </div>
                ))}
              </div>

              <div className="bm-profile-content">
                {profiles[activeTab] && (
                  <div className="bm-details-view fade-in" key={activeTab}>
                    {/* Identity Section */}
                    <div className="bm-details-section">
                      <h5 className="bm-section-title">👤 Identity Audit</h5>
                      <div className="bm-info-grid">
                        <div className="bm-info-item">
                          <label>Synced Account</label>
                          <span className="bm-val">{profiles[activeTab].email}</span>
                        </div>
                        <div className="bm-info-item">
                          <label>Profile Name</label>
                          <span className="bm-val">{profiles[activeTab].name}</span>
                        </div>
                      </div>
                    </div>

                    {/* Security Health Check */}
                    <div className="bm-details-section">
                      <h5 className="bm-section-title">🛡️ Security Health Check</h5>
                      <div className="bm-health-cards">
                        <div className="bm-health-card">
                          <span className="bm-h-icon">🛡️</span>
                          <div className="bm-h-info">
                            <label>SafeBrowsing</label>
                            <span className={`bm-h-status ${profiles[activeTab].security.safebrowsing_enabled ? 'text-success' : 'text-error'}`}>
                              {profiles[activeTab].security.safebrowsing_enhanced ? 'Enhanced Protection' : 
                               profiles[activeTab].security.safebrowsing_enabled ? 'Standard' : 'Disabled'}
                            </span>
                          </div>
                        </div>
                        <div className="bm-health-card">
                          <span className="bm-h-icon">🔑</span>
                          <div className="bm-h-info">
                            <label>Saved Passwords</label>
                            <span className="bm-h-val">{profiles[activeTab].security.password_count}</span>
                          </div>
                        </div>
                        <div className="bm-health-card">
                          <span className="bm-h-icon">🛂</span>
                          <div className="bm-h-info">
                            <label>Site Permissions</label>
                            <span className="bm-h-val">{profiles[activeTab].security.permissions_count} active</span>
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* Forensic: Top Sites */}
                    <div className="bm-details-section">
                      <h5 className="bm-section-title">🕵️ Forensic: Top Sites</h5>
                      <div className="bm-forensic-list">
                        {profiles[activeTab].forensics.length > 0 ? (
                          profiles[activeTab].forensics.map((site, i) => (
                            <div key={i} className="bm-forensic-item">
                              <div className="bm-f-title-row">
                                <span className="bm-f-title">{site.title}</span>
                                <span className="bm-f-visits">{site.visits} visits</span>
                              </div>
                              <code className="bm-f-url">{site.url}</code>
                            </div>
                          ))
                        ) : (
                          <p className="bm-muted">No history data found.</p>
                        )}
                      </div>
                    </div>

                    {/* Extensions List */}
                    <div className="bm-details-section">
                      <h5 className="bm-section-title">🧩 Extensions Audit ({profiles[activeTab].extensions.length})</h5>
                      <div className="bm-ext-grid">
                        {profiles[activeTab].extensions.map((ext, i) => (
                          <div key={i} className="bm-ext-item">
                            <div className="bm-ext-header">
                              <span className="bm-ext-name">{ext.name}</span>
                              <span className="bm-ext-ver">v{ext.version}</span>
                            </div>
                            <code className="bm-ext-id">{ext.id}</code>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
      
      <style dangerouslySetInnerHTML={{ __html: `
        .bm-modal-overlay {
          position: fixed;
          top: 0; left: 0; right: 0; bottom: 0;
          background: rgba(0, 0, 0, 0.7);
          backdrop-filter: blur(10px);
          z-index: 1000;
          display: flex;
          align-items: center;
          justify-content: center;
          padding: 24px;
        }
        .bm-modal {
          width: 100%;
          max-width: 1100px;
          height: 85vh;
          display: flex;
          flex-direction: column;
          overflow: hidden;
          background: var(--sc-bg-glass);
          border: 1px solid var(--sc-border);
          box-shadow: 0 32px 64px rgba(0, 0, 0, 0.4);
        }
        .bm-modal-header {
          padding: 20px 24px;
          border-bottom: 1px solid var(--sc-border);
          display: flex;
          justify-content: space-between;
          align-items: center;
        }
        .bm-modal-title-group {
          display: flex;
          align-items: center;
          gap: 12px;
        }
        .bm-modal-icon { font-size: 24px; }
        .bm-modal-title { margin: 0; font-size: 1.2rem; font-weight: 600; color: var(--sc-accent); }
        .bm-modal-close {
          background: transparent; border: none; font-size: 28px; color: var(--sc-text-dim); cursor: pointer;
          line-height: 1; padding: 4px; border-radius: 4px; transition: all 0.2s;
        }
        .bm-modal-close:hover { color: white; background: rgba(255, 255, 255, 0.1); }
        .bm-modal-body { flex: 1; overflow: hidden; position: relative; }
        
        .bm-profile-container { display: flex; height: 100%; }
        .bm-profile-sidebar { 
          width: 260px; border-right: 1px solid var(--sc-border); 
          background: rgba(0, 0, 0, 0.2); overflow-y: auto;
        }
        .bm-profile-item {
          padding: 16px; display: flex; gap: 12px; align-items: center; cursor: pointer;
          border-bottom: 1px solid rgba(255, 255, 255, 0.05); transition: all 0.2s;
        }
        .bm-profile-item:hover { background: rgba(255, 255, 255, 0.05); }
        .bm-profile-item.active { background: rgba(99, 102, 241, 0.15); border-right: 3px solid var(--sc-accent); }
        
        .bm-profile-avatar {
          width: 40px; height: 40px; border-radius: 50%; background: var(--sc-accent);
          display: flex; align-items: center; justify-content: center; overflow: hidden;
          font-weight: bold; color: white; border: 2px solid rgba(255, 255, 255, 0.1);
        }
        .bm-profile-avatar img { width: 100%; height: 100%; object-fit: cover; }
        .bm-profile-info { display: flex; flex-direction: column; overflow: hidden; }
        .bm-p-name { font-weight: 500; font-size: 14px; color: var(--sc-text); }
        .bm-p-folder { font-size: 11px; color: var(--sc-text-dim); overflow: hidden; text-overflow: ellipsis; }

        .bm-profile-content { flex: 1; overflow-y: auto; padding: 24px; background: rgba(0, 0, 0, 0.1); }
        .bm-details-section { margin-bottom: 32px; }
        .bm-section-title { 
          margin: 0 0 16px 0; font-size: 14px; font-weight: 600; text-transform: uppercase;
          letter-spacing: 0.5px; color: var(--sc-text-dim); display: flex; align-items: center;
        }
        
        .bm-info-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px; }
        .bm-info-item { background: rgba(255, 255, 255, 0.03); padding: 12px; border-radius: 8px; border: 1px solid rgba(255, 255, 255, 0.05); }
        .bm-info-item label { display: block; font-size: 11px; color: var(--sc-text-dim); margin-bottom: 4px; }
        .bm-info-item .bm-val { font-size: 14px; font-weight: 500; word-break: break-all; }

        .bm-health-cards { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }
        .bm-health-card { 
          background: rgba(255, 255, 255, 0.03); padding: 16px; border-radius: 12px;
          border: 1px solid rgba(255, 255, 255, 0.05); display: flex; gap: 12px; align-items: center;
        }
        .bm-h-icon { font-size: 24px; padding: 10px; background: rgba(255, 255, 255, 0.05); border-radius: 10px; }
        .bm-h-info label { display: block; font-size: 11px; color: var(--sc-text-dim); margin-bottom: 2px; }
        .bm-h-status, .bm-h-val { font-weight: 600; font-size: 14px; }
        .text-success { color: #2ecc71; }
        .text-error { color: #e74c3c; }

        .bm-forensic-list { display: flex; flex-direction: column; gap: 10px; }
        .bm-forensic-item { 
          background: rgba(0, 0, 0, 0.2); padding: 12px; border-radius: 8px;
          border: 1px solid rgba(255, 255, 255, 0.05);
        }
        .bm-f-title-row { display: flex; justify-content: space-between; margin-bottom: 6px; }
        .bm-f-title { font-weight: 500; font-size: 14px; color: var(--sc-accent-light); }
        .bm-f-visits { font-size: 12px; color: var(--sc-text-dim); padding: 2px 8px; background: rgba(255,255,255,0.05); border-radius: 10px; }
        .bm-f-url { font-size: 11px; color: var(--sc-text-dim); opacity: 0.7; word-break: break-all; }

        .bm-ext-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; }
        .bm-ext-item { 
          padding: 12px; background: rgba(255, 255, 255, 0.03); border-radius: 8px;
          border: 1px solid rgba(255, 255, 255, 0.05);
        }
        .bm-ext-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 4px; }
        .bm-ext-name { font-size: 13px; font-weight: 500; color: var(--sc-text); }
        .bm-ext-ver { font-size: 10px; padding: 2px 6px; background: var(--sc-accent); color: white; border-radius: 4px; }
        .bm-ext-id { font-size: 10px; color: var(--sc-text-dim); opacity: 0.6; }

        .bm-modal-loading {
          height: 100%; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 16px;
        }
        .bm-modal-empty {
          height: 100%; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 12px; opacity: 0.6;
        }
        .bm-muted { color: var(--sc-text-dim); font-style: italic; font-size: 13px; }
      ` }} />
    </div>
  )
}
