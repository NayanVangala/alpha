import { useCallback, useEffect, useState } from "react"
import { api, type Device, type Headband } from "@/lib/api"

/** Finding and connecting a headband: scans by itself while nothing is connected. */
export function useDevices(h: Headband, onConnect?: () => void) {
  const [devices, setDevices] = useState<Device[] | null>(null)
  const [scanning, setScanning] = useState(false)
  const [connectingTo, setConnectingTo] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const scan = useCallback(async () => {
    setScanning(true)
    setError(null)
    try {
      const body = await api.scan()
      setDevices(body.devices ?? [])
      setError(body.error ?? null)
    } catch {
      setDevices([])
      setError("Couldn't reach the board's server. Is it still running?")
    }
    setScanning(false)
  }, [])

  useEffect(() => {
    if (h.phase === "locked") setConnectingTo(null)
  }, [h.phase])
  useEffect(() => {
    if (h.phase === "locked" && devices === null && !scanning) void scan()
  }, [h.phase, devices, scanning, scan])

  const connect = async (name: string) => {
    onConnect?.()
    setConnectingTo(name)
    setError(null)
    const r = await api.connect(name)
    if (!r.ok) {
      setConnectingTo(null)
      setError(((await r.json().catch(() => ({}))) as { detail?: string }).detail || "Couldn't connect.")
    }
  }

  const rescan = () => !scanning && !connectingTo && void scan()
  return { devices, scanning, connectingTo, error: error || (h.phase === "locked" ? h.error : null), rescan, connect }
}
