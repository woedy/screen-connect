import { useAuth } from '../contexts/AuthContext'
import { useNavigate } from 'react-router-dom'
import './Navbar.css'

export default function Navbar() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  return (
    <nav className="navbar">
      <div className="navbar-inner">
        <div className="navbar-brand" onClick={() => navigate('/dashboard')}>
          <div className="navbar-logo">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <rect x="2" y="3" width="20" height="14" rx="2" stroke="currentColor" strokeWidth="1.5"/>
              <path d="M8 21h8M12 17v4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
              <circle cx="12" cy="10" r="2" fill="currentColor" opacity="0.5"/>
              <path d="M12 8a4 4 0 014 4" stroke="currentColor" strokeWidth="1" opacity="0.3"/>
              <path d="M12 6a6 6 0 016 6" stroke="currentColor" strokeWidth="1" opacity="0.2"/>
            </svg>
          </div>
          <span className="navbar-title">ScreenConnect</span>
        </div>

        <div className="navbar-actions">
          {user && (
            <div className="navbar-user">
              <div className="navbar-avatar">
                {user.username?.charAt(0).toUpperCase()}
              </div>
              <span className="navbar-username">{user.username}</span>
            </div>
          )}
          <button className="btn btn-secondary btn-sm" onClick={handleLogout} id="logout-btn">
            Logout
          </button>
        </div>
      </div>
    </nav>
  )
}
