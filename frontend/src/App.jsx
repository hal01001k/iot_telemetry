import { useState, useEffect, useRef, useCallback } from 'react'
import styles from './App.module.css'
import Simulator from './Simulator.jsx'

// ── Config ──────────────────────────────────────────────────────────────────
const WS_URL = 'ws://localhost:8000/ws/telemetry'
const RECONNECT_DELAY = 3000

// ── Hooks ───────────────────────────────────────────────────────────────────
function useTelemetrySocket() {
    const [status, setStatus] = useState('connecting') // connecting | connected | disconnected
    const [lastEvent, setLastEvent] = useState(null)
    const wsRef = useRef(null)
    const timerRef = useRef(null)

    const connect = useCallback(() => {
        if (wsRef.current) wsRef.current.close()
        clearTimeout(timerRef.current)
        setStatus('connecting')

        const ws = new WebSocket(WS_URL)
        wsRef.current = ws

        ws.onopen = () => setStatus('connected')
        ws.onclose = () => {
            setStatus('disconnected')
            timerRef.current = setTimeout(connect, RECONNECT_DELAY)
        }
        ws.onerror = () => ws.close()
        ws.onmessage = (evt) => {
            try {
                const msg = JSON.parse(evt.data)
                if (msg.event === 'telemetry') setLastEvent(msg)
            } catch (_) { }
        }
    }, [])

    useEffect(() => {
        connect()
        return () => {
            clearTimeout(timerRef.current)
            wsRef.current?.close()
        }
    }, [connect])

    return { status, lastEvent }
}

// ── Sub-components ───────────────────────────────────────────────────────────
function StatusBadge({ status }) {
    const labels = { connecting: 'Connecting…', connected: 'Connected', disconnected: 'Disconnected' }
    return (
        <div className={`${styles.badge} ${styles[status]}`}>
            <span className={styles.dot} />
            {labels[status]}
        </div>
    )
}

function MetricCard({ label, value, unit, highlight }) {
    return (
        <div className={`${styles.metric} ${highlight ? styles.metricHighlight : ''}`}>
            <span className={styles.metricLabel}>{label}</span>
            <span className={styles.metricValue}>{value ?? '—'}{value != null && unit ? <span className={styles.unit}> {unit}</span> : ''}</span>
        </div>
    )
}

function StatusMetric({ value }) {
    const cls = value === 'online' ? styles.statusOnline
        : value === 'offline' ? styles.statusOffline
            : value ? styles.statusError
                : ''
    return (
        <div className={styles.metric}>
            <span className={styles.metricLabel}>Status</span>
            <span className={`${styles.metricValue} ${cls}`}>{value ?? '—'}</span>
        </div>
    )
}

function AlertPanel({ alerts }) {
    if (!alerts || alerts.length === 0) return null
    return (
        <div className={styles.alertPanel}>
            <div className={styles.alertHeader}>⚠ Alerts</div>
            {alerts.map((a, i) => (
                <div key={i} className={styles.alertItem}>
                    <span className={styles.alertType}>{a.type}</span>
                    <span className={styles.alertMsg}>{a.message}</span>
                </div>
            ))}
        </div>
    )
}

function IngestionLog({ events }) {
    return (
        <div className={styles.logPanel}>
            <div className={styles.logHeader}>Event Log <span className={styles.logCount}>{events.length}</span></div>
            <div className={styles.logList}>
                {events.length === 0 && <div className={styles.logEmpty}>No events yet</div>}
                {events.map((e, i) => (
                    <div key={i} className={styles.logEntry}>
                        <span className={styles.logTime}>{new Date(e.receivedAt).toLocaleTimeString()}</span>
                        <span className={styles.logDevice}>{e.data.deviceId}</span>
                        <span className={styles.logTemp}>{e.data.temperature}°C</span>
                        {e.alerts?.length > 0 && <span className={styles.logAlert}>{e.alerts.length} alert{e.alerts.length !== 1 ? 's' : ''}</span>}
                    </div>
                ))}
            </div>
        </div>
    )
}

// ── Main App ─────────────────────────────────────────────────────────────────
export default function App() {
    const { status, lastEvent } = useTelemetrySocket()
    const [history, setHistory] = useState([])
    const [activeTab, setActiveTab] = useState('dashboard')

    useEffect(() => {
        if (lastEvent) {
            setHistory(prev => [lastEvent, ...prev].slice(0, 50))
        }
    }, [lastEvent])

    const data = lastEvent?.data
    const alerts = lastEvent?.alerts

    return (
        <div className={styles.app}>
            {/* Header */}
            <header className={styles.header}>
                <div className={styles.headerLeft}>
                    <div className={styles.logo}>
                        <span className={styles.logoIcon}>◉</span>
                        IoT <span className={styles.logoAccent}>Telemetry</span>
                    </div>
                    <div className={styles.headerSub}>Live Sensor Dashboard</div>
                </div>

                <div className={styles.tabs}>
                    <button
                        className={`${styles.tabBtn} ${activeTab === 'dashboard' ? styles.tabActive : ''}`}
                        onClick={() => setActiveTab('dashboard')}
                    >
                        Dashboard
                    </button>
                    <button
                        className={`${styles.tabBtn} ${activeTab === 'simulator' ? styles.tabActive : ''}`}
                        onClick={() => setActiveTab('simulator')}
                    >
                        Simulator
                    </button>
                </div>

                <StatusBadge status={status} />
            </header>

            <main className={styles.main}>
                {activeTab === 'simulator' ? (
                    <Simulator />
                ) : (
                    <>
                        {/* Device info row */}
                        {data ? (
                            <>
                                <div className={styles.deviceRow}>
                                    <div className={styles.deviceInfo}>
                                        <div className={styles.deviceId}>{data.deviceId}</div>
                                        <div className={styles.deviceTs}>Last update · {new Date(lastEvent.receivedAt).toLocaleTimeString()}</div>
                                    </div>
                                    <div className={styles.deviceSource}>
                                        <span className={styles.sourceTag}>via HTTP/MQTT</span>
                                    </div>
                                </div>

                                {/* Metrics grid */}
                                <div className={styles.metricsGrid}>
                                    <MetricCard label="Temperature" value={data.temperature} unit="°C" highlight={data.temperature > 35} />
                                    <MetricCard label="Energy" value={data.energyConsumption} unit="kWh" highlight={data.energyConsumption > 10} />
                                    <MetricCard label="Voltage" value={data.voltage} unit="V" />
                                    <MetricCard label="Current" value={data.current} unit="A" />
                                    <StatusMetric value={data.status} />
                                    <MetricCard label="Timestamp" value={data.timestamp?.replace('T', ' ').replace('Z', '')} />
                                </div>

                                {/* Alerts */}
                                <AlertPanel alerts={alerts} />
                            </>
                        ) : (
                            <div className={styles.waiting}>
                                <div className={styles.waitingSpinner} />
                                <div className={styles.waitingText}>Waiting for live telemetry…</div>
                                <div className={styles.waitingHint}>Send a <code>POST /telemetry</code> or publish to MQTT topic <code>devices/&#123;id&#125;/telemetry</code></div>
                            </div>
                        )}

                        {/* Ingestion log */}
                        <IngestionLog events={history} />
                    </>
                )}
            </main>

            <footer className={styles.footer}>
                <span>ws://localhost:8000/ws/telemetry</span>
                <span>·</span>
                <span>MQTT: localhost:1883 → devices/+/telemetry</span>
                <span>·</span>
                <span>Auto-reconnects every {RECONNECT_DELAY / 1000}s</span>
            </footer>
        </div>
    )
}
