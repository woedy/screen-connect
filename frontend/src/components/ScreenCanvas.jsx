import { useRef, useEffect, useCallback, useState, forwardRef, useImperativeHandle } from 'react'
import './ScreenCanvas.css'

/**
 * Canvas-based screen renderer for remote screen viewing and input control.
 * Uses createImageBitmap for off-thread JPEG decoding and requestAnimationFrame batching.
 */
const ScreenCanvas = forwardRef(function ScreenCanvas({ onMouseEvent, onKeyEvent, onScrollEvent }, ref) {
  const canvasRef = useRef(null)
  const containerRef = useRef(null)
  const [fps, setFps] = useState(0)
  const [resolution, setResolution] = useState({ w: 0, h: 0 })
  const [remoteSize, setRemoteSize] = useState({ width: 1920, height: 1080 })
  const frameCountRef = useRef(0)
  const lastFpsTimeRef = useRef(Date.now())
  const pendingFrameRef = useRef(null)
  const rafIdRef = useRef(null)

  // Track FPS
  useEffect(() => {
    const interval = setInterval(() => {
      const now = Date.now()
      const elapsed = (now - lastFpsTimeRef.current) / 1000
      setFps(Math.round(frameCountRef.current / elapsed))
      frameCountRef.current = 0
      lastFpsTimeRef.current = now
    }, 1000)
    return () => clearInterval(interval)
  }, [])

  // rAF render loop — only draws the latest pending frame
  const renderLoop = useCallback(() => {
    const frame = pendingFrameRef.current
    if (frame) {
      pendingFrameRef.current = null
      const canvas = canvasRef.current
      if (canvas) {
        const ctx = canvas.getContext('2d', { alpha: false, desynchronized: true })
        if (canvas.width !== frame.width || canvas.height !== frame.height) {
          canvas.width = frame.width
          canvas.height = frame.height
        }
        ctx.drawImage(frame, 0, 0)
        
        // Only update resolution state if it actually changed
        setResolution(prev => {
          if (prev.w === frame.width && prev.h === frame.height) return prev
          return { w: frame.width, h: frame.height }
        })
        
        frameCountRef.current++
        frame.close() // Release ImageBitmap memory
      }
    }
    rafIdRef.current = requestAnimationFrame(renderLoop)
  }, [])

  useEffect(() => {
    rafIdRef.current = requestAnimationFrame(renderLoop)
    return () => cancelAnimationFrame(rafIdRef.current)
  }, [renderLoop])

  const drawFrame = useCallback((jpegArrayBuffer, width, height) => {
    if (width && height && (remoteSize.width !== width || remoteSize.height !== height)) {
      setRemoteSize({ width, height })
    }

    const blob = new Blob([jpegArrayBuffer], { type: 'image/jpeg' })
    createImageBitmap(blob, { colorSpaceConversion: 'none' }).then((bitmap) => {
      // Close previous bitmap if it was never drawn
      if (pendingFrameRef.current) {
        pendingFrameRef.current.close()
      }
      pendingFrameRef.current = bitmap
    }).catch(() => {
      // Fallback
    })
  }, [remoteSize])

  // Draw a tile/delta from binary data
  const drawTile = useCallback((jpegArrayBuffer, x, y, width, height) => {
    const blob = new Blob([jpegArrayBuffer], { type: 'image/jpeg' })
    createImageBitmap(blob, { colorSpaceConversion: 'none' }).then((bitmap) => {
      const canvas = canvasRef.current
      if (canvas) {
        const ctx = canvas.getContext('2d', { alpha: false, desynchronized: true })
        // Draw tile directly to context
        ctx.drawImage(bitmap, x, y, width, height)
        frameCountRef.current++
        bitmap.close()
      }
    }).catch(() => {
    })
  }, [])

  // Expose drawFrame to parent via ref
  useImperativeHandle(ref, () => ({
    drawFrame,
    drawTile,
  }), [drawFrame, drawTile])

  // Map canvas coordinates to remote screen coordinates
  const mapCoordinates = useCallback((e) => {
    const canvas = canvasRef.current
    if (!canvas) return { x: 0, y: 0 }

    const rect = canvas.getBoundingClientRect()
    const scaleX = remoteSize.width / rect.width
    const scaleY = remoteSize.height / rect.height
    return {
      x: Math.round((e.clientX - rect.left) * scaleX),
      y: Math.round((e.clientY - rect.top) * scaleY),
    }
  }, [remoteSize])

  // Mouse handlers
  const handleClick = useCallback((e) => {
    const coords = mapCoordinates(e)
    const button = e.button === 2 ? 'right' : e.button === 1 ? 'middle' : 'left'
    onMouseEvent?.('mouse_click', { ...coords, button, clicks: 1 })
  }, [mapCoordinates, onMouseEvent])

  const handleDoubleClick = useCallback((e) => {
    const coords = mapCoordinates(e)
    onMouseEvent?.('mouse_click', { ...coords, button: 'left', clicks: 2 })
  }, [mapCoordinates, onMouseEvent])

  const handleMouseMove = useCallback((e) => {
    const coords = mapCoordinates(e)
    
    // Throttle move events to ~30 FPS (match agent loop)
    const now = Date.now()
    if (now - (handleMouseMove._lastSent || 0) < 33) return
    handleMouseMove._lastSent = now

    onMouseEvent?.('mouse_move', coords)
  }, [mapCoordinates, onMouseEvent])

  const handleContextMenu = useCallback((e) => {
    e.preventDefault()
    const coords = mapCoordinates(e)
    onMouseEvent?.('mouse_click', { ...coords, button: 'right', clicks: 1 })
  }, [mapCoordinates, onMouseEvent])

  const handleScroll = useCallback((e) => {
    e.preventDefault()
    const coords = mapCoordinates(e)
    onScrollEvent?.({ ...coords, delta: -e.deltaY })
  }, [mapCoordinates, onScrollEvent])

  // Keyboard handler
  const handleKeyDown = useCallback((e) => {
    e.preventDefault()
    e.stopPropagation()

    if (['Control', 'Alt', 'Shift', 'Meta'].includes(e.key)) return

    const modifiers = []
    if (e.ctrlKey) modifiers.push('ctrl')
    if (e.altKey) modifiers.push('alt')
    if (e.shiftKey) modifiers.push('shift')
    if (e.metaKey) modifiers.push('meta')

    onKeyEvent?.({ key: e.key, modifiers })
  }, [onKeyEvent])

  // Attach wheel listener with { passive: false }
  useEffect(() => {
    const canvas = canvasRef.current
    if (canvas) {
      canvas.addEventListener('wheel', handleScroll, { passive: false })
      return () => canvas.removeEventListener('wheel', handleScroll)
    }
  }, [handleScroll])

  // Make canvas focusable
  useEffect(() => {
    const canvas = canvasRef.current
    if (canvas) canvas.focus()
  }, [])

  return (
    <div className="screen-canvas-container" ref={containerRef}>
      <canvas
        ref={canvasRef}
        className="screen-canvas"
        tabIndex={0}
        onClick={handleClick}
        onDoubleClick={handleDoubleClick}
        onMouseMove={handleMouseMove}
        onContextMenu={handleContextMenu}
        onKeyDown={handleKeyDown}
      />
      <div className="screen-canvas-overlay">
        <span className="overlay-stat">{fps} FPS</span>
        <span className="overlay-stat">{resolution.w}×{resolution.h}</span>
      </div>
    </div>
  )
})

export default ScreenCanvas
