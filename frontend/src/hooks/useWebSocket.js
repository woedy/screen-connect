import { useState, useEffect, useRef, useCallback } from 'react'

/**
 * Custom hook for WebSocket lifecycle management with binary message support.
 *
 * @param {string|null} url - WebSocket URL to connect to
 * @param {object} options
 * @param {function} options.onMessage - callback for incoming JSON messages
 * @param {function} options.onBinaryMessage - callback for incoming binary messages (ArrayBuffer)
 * @param {function} options.onOpen - callback on connection open
 * @param {function} options.onClose - callback on connection close
 * @param {function} options.onError - callback on error
 * @param {boolean} options.autoReconnect - whether to auto-reconnect (default true)
 * @param {number} options.reconnectInterval - ms between reconnect attempts (default 3000)
 */
export default function useWebSocket(url, options = {}) {
  const {
    onMessage,
    onBinaryMessage,
    onOpen,
    onClose,
    onError,
    autoReconnect = true,
    reconnectInterval = 3000,
  } = options

  const [readyState, setReadyState] = useState(WebSocket.CLOSED)
  const wsRef = useRef(null)
  const reconnectTimerRef = useRef(null)
  const manualCloseRef = useRef(false)

  // Store callbacks in refs to avoid reconnection on callback change
  const onMessageRef = useRef(onMessage)
  const onBinaryMessageRef = useRef(onBinaryMessage)
  const onOpenRef = useRef(onOpen)
  const onCloseRef = useRef(onClose)
  const onErrorRef = useRef(onError)

  useEffect(() => { onMessageRef.current = onMessage }, [onMessage])
  useEffect(() => { onBinaryMessageRef.current = onBinaryMessage }, [onBinaryMessage])
  useEffect(() => { onOpenRef.current = onOpen }, [onOpen])
  useEffect(() => { onCloseRef.current = onClose }, [onClose])
  useEffect(() => { onErrorRef.current = onError }, [onError])

  const connect = useCallback(() => {
    if (!url) return

    // Clean up existing connection
    if (wsRef.current) {
      wsRef.current.close()
    }

    const ws = new WebSocket(url)
    ws.binaryType = 'arraybuffer'
    wsRef.current = ws

    ws.onopen = (e) => {
      setReadyState(WebSocket.OPEN)
      onOpenRef.current?.(e)
    }

    ws.onmessage = (e) => {
      if (e.data instanceof ArrayBuffer) {
        // Binary message — route to binary handler
        onBinaryMessageRef.current?.(e.data)
      } else {
        // Text message — parse as JSON
        try {
          const data = JSON.parse(e.data)
          onMessageRef.current?.(data)
        } catch {
          onMessageRef.current?.(e.data)
        }
      }
    }

    ws.onerror = (e) => {
      onErrorRef.current?.(e)
    }

    ws.onclose = (e) => {
      setReadyState(WebSocket.CLOSED)
      onCloseRef.current?.(e)

      // Auto-reconnect unless manually closed
      if (autoReconnect && !manualCloseRef.current) {
        reconnectTimerRef.current = setTimeout(() => {
          connect()
        }, reconnectInterval)
      }
    }
  }, [url, autoReconnect, reconnectInterval])

  const sendMessage = useCallback((data) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      const msg = typeof data === 'string' ? data : JSON.stringify(data)
      wsRef.current.send(msg)
    }
  }, [])

  const sendBinary = useCallback((data) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(data)
    }
  }, [])

  const disconnect = useCallback(() => {
    manualCloseRef.current = true
    clearTimeout(reconnectTimerRef.current)
    wsRef.current?.close()
  }, [])

  useEffect(() => {
    manualCloseRef.current = false
    connect()
    return () => {
      manualCloseRef.current = true
      clearTimeout(reconnectTimerRef.current)
      wsRef.current?.close()
    }
  }, [url]) // Reconnect when URL changes

  return {
    readyState,
    sendMessage,
    sendBinary,
    disconnect,
    isConnected: readyState === WebSocket.OPEN,
  }
}
