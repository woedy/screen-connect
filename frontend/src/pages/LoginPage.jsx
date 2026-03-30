import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'
import './LoginPage.css'

export default function LoginPage() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const { login } = useAuth()
  const navigate = useNavigate()

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)

    try {
      await login(username, password)
      navigate('/dashboard')
    } catch (err) {
      const msg = err.response?.data?.detail || 'Invalid credentials. Please try again.'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-page">
      <div className="bg-gradient-mesh" />

      <div className="login-container fade-in">
        {/* Logo */}
        <div className="login-logo">
          <div className="login-logo-icon">
            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <rect x="2" y="3" width="20" height="14" rx="2" stroke="currentColor" strokeWidth="1.5"/>
              <path d="M8 21h8M12 17v4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
              <circle cx="12" cy="10" r="2" fill="currentColor" opacity="0.6"/>
              <path d="M12 8a4 4 0 014 4" stroke="currentColor" strokeWidth="1" opacity="0.3"/>
              <path d="M12 6a6 6 0 016 6" stroke="currentColor" strokeWidth="1" opacity="0.2"/>
            </svg>
          </div>
          <h1 className="login-title">ScreenConnect</h1>
          <p className="login-subtitle">Remote Support Dashboard</p>
        </div>

        {/* Form */}
        <form className="login-form glass-card" onSubmit={handleSubmit}>
          <h2 className="login-form-title">Sign In</h2>
          <p className="login-form-desc">Enter your credentials to access the dashboard</p>

          {error && (
            <div className="login-error" id="login-error">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10"/>
                <path d="M15 9l-6 6M9 9l6 6"/>
              </svg>
              {error}
            </div>
          )}

          <div className="form-group">
            <label className="label" htmlFor="username">Username</label>
            <input
              className="input"
              id="username"
              type="text"
              placeholder="Enter your username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="username"
              required
              autoFocus
            />
          </div>

          <div className="form-group">
            <label className="label" htmlFor="password">Password</label>
            <input
              className="input"
              id="password"
              type="password"
              placeholder="Enter your password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              required
            />
          </div>

          <button
            className="btn btn-primary btn-lg login-submit"
            type="submit"
            disabled={loading || !username || !password}
            id="login-submit"
          >
            {loading ? (
              <>
                <div className="spinner" />
                Signing in...
              </>
            ) : (
              'Sign In'
            )}
          </button>
        </form>

        <p className="login-footer">
          Secure remote support sessions powered by WebSocket
        </p>
      </div>
    </div>
  )
}
