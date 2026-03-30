import { useState, useEffect, useRef, useCallback } from 'react'
import './RemoteTerminal.css'

/**
 * Remote terminal component — execute commands on the client machine.
 */
export default function RemoteTerminal({ sendMessage, lastMessage }) {
  const [input, setInput] = useState('')
  const [lines, setLines] = useState([
    { type: 'info', text: '● Connected to remote terminal. Type a command and press Enter.' },
  ])
  const [isRunning, setIsRunning] = useState(false)
  const [currentCommandId, setCurrentCommandId] = useState(null)
  const [history, setHistory] = useState([])
  const [historyIndex, setHistoryIndex] = useState(-1)
  const outputRef = useRef(null)
  const inputRef = useRef(null)

  // Auto-scroll to bottom
  useEffect(() => {
    if (outputRef.current) {
      outputRef.current.scrollTop = outputRef.current.scrollHeight
    }
  }, [lines])

  // Handle incoming messages
  useEffect(() => {
    if (!lastMessage) return
    const { type } = lastMessage

    if (type === 'command_output') {
      const stream = lastMessage.stream || 'stdout'
      setLines(prev => [...prev, {
        type: stream === 'stderr' ? 'error' : 'output',
        text: lastMessage.data || '',
      }])
    }

    if (type === 'command_complete') {
      const code = lastMessage.exit_code
      setLines(prev => [...prev, {
        type: code === 0 ? 'success' : 'error',
        text: `\n[Process exited with code ${code}]\n`,
      }])
      setIsRunning(false)
      setCurrentCommandId(null)
    }
  }, [lastMessage])

  const handleSubmit = (e) => {
    e.preventDefault()
    const cmd = input.trim()
    if (!cmd) return

    const commandId = crypto.randomUUID()

    setLines(prev => [...prev, { type: 'command', text: `$ ${cmd}` }])
    setHistory(prev => [...prev, cmd])
    setHistoryIndex(-1)
    setInput('')
    setIsRunning(true)
    setCurrentCommandId(commandId)

    sendMessage({
      type: 'command_run',
      command: cmd,
      command_id: commandId,
      timeout: 120,
    })
  }

  const handleKill = () => {
    if (currentCommandId) {
      sendMessage({
        type: 'command_kill',
        command_id: currentCommandId,
      })
    }
  }

  const handleClear = () => {
    setLines([{ type: 'info', text: '● Terminal cleared.' }])
  }

  const handleKeyDown = (e) => {
    if (e.key === 'ArrowUp') {
      e.preventDefault()
      if (history.length > 0) {
        const newIndex = historyIndex < history.length - 1 ? historyIndex + 1 : historyIndex
        setHistoryIndex(newIndex)
        setInput(history[history.length - 1 - newIndex] || '')
      }
    } else if (e.key === 'ArrowDown') {
      e.preventDefault()
      if (historyIndex > 0) {
        const newIndex = historyIndex - 1
        setHistoryIndex(newIndex)
        setInput(history[history.length - 1 - newIndex] || '')
      } else {
        setHistoryIndex(-1)
        setInput('')
      }
    }
  }

  // Focus input on click anywhere
  const handleContainerClick = () => {
    inputRef.current?.focus()
  }

  return (
    <div className="remote-terminal" onClick={handleContainerClick}>
      {/* Terminal toolbar */}
      <div className="term-toolbar">
        <div className="term-toolbar-left">
          <div className="term-dots">
            <span className="term-dot term-dot-red" />
            <span className="term-dot term-dot-yellow" />
            <span className="term-dot term-dot-green" />
          </div>
          <span className="term-title">Remote Shell</span>
        </div>
        <div className="term-toolbar-right">
          {isRunning && (
            <button className="btn btn-danger btn-sm" onClick={handleKill}>
              ■ Kill
            </button>
          )}
          <button className="btn btn-secondary btn-sm" onClick={handleClear}>
            Clear
          </button>
        </div>
      </div>

      {/* Output area */}
      <div className="term-output" ref={outputRef}>
        {lines.map((line, i) => (
          <div key={i} className={`term-line term-line-${line.type}`}>
            <pre>{line.text}</pre>
          </div>
        ))}
        {isRunning && (
          <div className="term-line term-line-running">
            <div className="spinner" style={{ width: 12, height: 12 }} />
            <span>Running...</span>
          </div>
        )}
      </div>

      {/* Input */}
      <form className="term-input-bar" onSubmit={handleSubmit}>
        <span className="term-prompt">$</span>
        <input
          ref={inputRef}
          className="term-input"
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={isRunning ? 'Waiting for command to finish...' : 'Type a command...'}
          disabled={isRunning}
          autoFocus
        />
      </form>
    </div>
  )
}
