import { useState, useEffect, useRef } from 'react'
import mqtt from 'mqtt'
import styles from './Simulator.module.css'

export default function Simulator() {
    const [client, setClient] = useState(null)
    const [connectStatus, setConnectStatus] = useState('Disconnected')
    const [pubStatus, setPubStatus] = useState('')

    const [formData, setFormData] = useState({
        deviceId: 'AC-1001',
        temperature: 29.5,
        energyConsumption: 4.8,
        voltage: 230,
        current: 6.2,
        status: 'online',
    })

    useEffect(() => {
        return () => {
            if (client) {
                client.end()
            }
        }
    }, [client])

    const handleConnect = () => {
        if (client) {
            client.end()
            setClient(null)
            setConnectStatus('Disconnected')
            return
        }

        setConnectStatus('Connecting...')
        // Connect via WebSockets to Mosquitto
        const mqttClient = mqtt.connect('ws://localhost:9001', {
            clientId: 'webapp_' + Math.random().toString(16).substr(2, 8),
        })

        mqttClient.on('connect', () => {
            setConnectStatus('Connected')
            setClient(mqttClient)
        })

        mqttClient.on('error', (err) => {
            setConnectStatus(`Error: ${err.message}`)
            mqttClient.end()
        })

        mqttClient.on('close', () => {
            setConnectStatus('Disconnected')
            setClient(null)
        })
    }

    const handlePublish = (e) => {
        e.preventDefault()
        if (!client || !client.connected) {
            setPubStatus('Error: Not connected to MQTT broker')
            return
        }

        const topic = `devices/${formData.deviceId}/telemetry`
        const payload = {
            ...formData,
            timestamp: new Date().toISOString(),
            temperature: Number(formData.temperature),
            energyConsumption: Number(formData.energyConsumption),
            voltage: Number(formData.voltage),
            current: Number(formData.current),
        }

        client.publish(topic, JSON.stringify(payload), { qos: 1 }, (err) => {
            if (err) {
                setPubStatus(`Publish error: ${err.message}`)
            } else {
                setPubStatus(`Published to ${topic} at ${new Date().toLocaleTimeString()}`)
                setTimeout(() => setPubStatus(''), 3000)
            }
        })
    }

    const handleChange = (e) => {
        const { name, value } = e.target
        setFormData(prev => ({ ...prev, [name]: value }))
    }

    return (
        <div className={styles.simulatorContainer}>
            <div className={styles.header}>
                <h2>MQTT Device Simulator</h2>
                <p>Publish telemetry directly to the Mosquitto broker via WebSockets</p>
            </div>

            <div className={styles.connectionPanel}>
                <div className={styles.statusRow}>
                    <span className={styles.statusLabel}>Broker Status:</span>
                    <span className={`${styles.statusValue} ${connectStatus === 'Connected' ? styles.green : styles.red}`}>
                        {connectStatus}
                    </span>
                </div>
                <button
                    onClick={handleConnect}
                    className={`${styles.btn} ${client ? styles.btnDisconnect : styles.btnConnect}`}
                >
                    {client ? 'Disconnect' : 'Connect to ws://localhost:9001'}
                </button>
            </div>

            <form className={styles.formContainer} onSubmit={handlePublish}>
                <div className={styles.formGrid}>
                    <div className={styles.formGroup}>
                        <label>Device ID</label>
                        <input type="text" name="deviceId" value={formData.deviceId} onChange={handleChange} required />
                    </div>

                    <div className={styles.formGroup}>
                        <label>Status</label>
                        <select name="status" value={formData.status} onChange={handleChange}>
                            <option value="online">online</option>
                            <option value="offline">offline</option>
                            <option value="error">error</option>
                        </select>
                    </div>

                    <div className={styles.formGroup}>
                        <label>Temperature (°C)</label>
                        <input type="number" step="0.1" name="temperature" value={formData.temperature} onChange={handleChange} required />
                    </div>

                    <div className={styles.formGroup}>
                        <label>Energy (kWh)</label>
                        <input type="number" step="0.1" name="energyConsumption" value={formData.energyConsumption} onChange={handleChange} required />
                    </div>

                    <div className={styles.formGroup}>
                        <label>Voltage (V)</label>
                        <input type="number" step="1" name="voltage" value={formData.voltage} onChange={handleChange} required />
                    </div>

                    <div className={styles.formGroup}>
                        <label>Current (A)</label>
                        <input type="number" step="0.1" name="current" value={formData.current} onChange={handleChange} required />
                    </div>
                </div>

                <div className={styles.formActions}>
                    <button type="submit" disabled={!client} className={styles.btnPublish}>
                        Publish Telemetry
                    </button>
                    {pubStatus && <div className={styles.pubStatus}>{pubStatus}</div>}
                </div>
            </form>
        </div>
    )
}
