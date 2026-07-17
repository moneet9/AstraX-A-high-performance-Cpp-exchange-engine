import React, { useState, useEffect, useRef, useCallback } from 'react'
import OrderBook from './components/OrderBook'
import TradeFeed from './components/TradeFeed'
import AgentPanel from './components/AgentPanel'
import LatencyPanel from './components/LatencyPanel'
import PriceChart from './components/PriceChart'
import Stats from './components/Stats'

export default function App() {
  const [connected, setConnected] = useState(false)
  const [book, setBook] = useState(null)
  const [agents, setAgents] = useState([])
  const [fills, setFills] = useState([])
  const [priceHistory, setPriceHistory] = useState([])
  const [latency, setLatency] = useState(null)
  const [step, setStep] = useState(0)
  const [analysisType, setAnalysisType] = useState('strategy_plan')
  const [analysisText, setAnalysisText] = useState('')
  const [regimeSummary, setRegimeSummary] = useState('Click "Find Similar Regimes" to compare the current market against archived conditions.')
  const [regimeMatches, setRegimeMatches] = useState([])
  const [regimeMeta, setRegimeMeta] = useState(null)
  const [llmConfig, setLlmConfig] = useState(null)
  const wsRef = useRef(null)

  const connect = useCallback(() => {
    const ws = new WebSocket('ws://localhost:8765')
    wsRef.current = ws

    ws.onopen = () => setConnected(true)
    ws.onclose = () => {
      setConnected(false)
      setTimeout(connect, 2000)
    }
    ws.onerror = () => ws.close()

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data)
      if (data.type === 'tick') {
        setBook(data.book)
        setAgents(data.agents)
        setStep(data.step)

        if (data.fills.length > 0) {
          setFills(prev => [...data.fills, ...prev].slice(0, 100))
        }

        if (data.book.mid) {
          setPriceHistory(prev => {
            const next = [...prev, { time: data.step, value: data.book.mid / 10000 }]
            return next.slice(-500)
          })
        }

        if (data.latency) {
          setLatency(data.latency)
        }
      } else if (data.type === 'analysis') {
        setAnalysisText(data.content || '')
      } else if (data.type === 'regime_similarity') {
        setRegimeMeta({
          currentStep: data.current_step,
          currentDescription: data.current_description,
          archiveSize: data.archive_size,
          ok: data.ok,
          error: data.error,
        })
        setRegimeMatches(data.matches || [])
        if (data.ok) {
          setRegimeSummary(
            data.matches?.length
              ? `Compared step ${data.current_step} against ${data.archive_size} archived regimes.`
              : 'There are not enough archived regimes yet. Let the simulator run a little longer and try again.'
          )
        } else {
          setRegimeSummary(data.error || 'Regime comparison is unavailable right now.')
        }
      } else if (data.type === 'init') {
        setLlmConfig(data.llm || null)
      }
    }
  }, [])

  const requestAnalysis = useCallback((type = analysisType) => {
    if (type === 'regime_similarity') {
      setAnalysisText('')
      wsRef.current?.send(JSON.stringify({
        command: 'regime_similarity',
        limit: 5,
      }))
    } else {
      wsRef.current?.send(JSON.stringify({
        command: 'analysis',
        analysis_type: type,
      }))
    }
    setAnalysisType(type)
  }, [analysisType])

  useEffect(() => {
    connect()
    return () => wsRef.current?.close()
  }, [connect])

  const latestMid = book?.mid ? (book.mid / 10000).toFixed(4) : '—'
  const latestSpread = book?.spread ?? '—'
  const latencyLabel = latency ?? '—'

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', position: 'relative' }}>
      <header style={{
        display: 'grid',
        gridTemplateColumns: '1.5fr 1fr',
        gap: '16px',
        padding: '20px 22px',
        background: 'linear-gradient(135deg, rgba(22, 31, 56, 0.96), rgba(9, 16, 31, 0.92))',
        borderRadius: '18px',
        border: '1px solid var(--border)',
        boxShadow: '0 24px 80px rgba(0, 0, 0, 0.28)',
        backdropFilter: 'blur(14px)',
      }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
            <span style={{
              display: 'inline-flex',
              alignItems: 'center',
              padding: '5px 10px',
              borderRadius: '999px',
              background: 'rgba(34, 211, 238, 0.12)',
              color: 'var(--cyan)',
              border: '1px solid rgba(34, 211, 238, 0.2)',
              fontSize: '11px',
              fontWeight: 700,
              letterSpacing: '0.08em',
              textTransform: 'uppercase',
            }}>
              AstraX
            </span>
            <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
              High-performance C++ exchange engine
            </span>
          </div>

          <h1 style={{ fontSize: '30px', lineHeight: 1.05, fontWeight: 700, letterSpacing: '-0.03em' }}>
            Price-time priority matching with low-latency telemetry.
          </h1>

          <p style={{ maxWidth: '64ch', fontSize: '14px', color: 'var(--text-secondary)', lineHeight: 1.6 }}>
            Live market activity, agent behavior, and latency are rendered in a single glassy control surface designed to feel like a production trading system.
          </p>
        </div>

        <div style={{ display: 'grid', gap: '10px', alignContent: 'start' }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: '10px' }}>
            <div style={{ padding: '14px 16px', borderRadius: '14px', background: 'rgba(255, 255, 255, 0.03)', border: '1px solid var(--border)' }}>
              <div style={{ fontSize: '11px', color: 'var(--text-secondary)', marginBottom: '6px' }}>MID</div>
              <div style={{ fontSize: '18px', fontWeight: 700 }}>{latestMid}</div>
            </div>
            <div style={{ padding: '14px 16px', borderRadius: '14px', background: 'rgba(255, 255, 255, 0.03)', border: '1px solid var(--border)' }}>
              <div style={{ fontSize: '11px', color: 'var(--text-secondary)', marginBottom: '6px' }}>SPREAD</div>
              <div style={{ fontSize: '18px', fontWeight: 700 }}>{latestSpread}</div>
            </div>
            <div style={{ padding: '14px 16px', borderRadius: '14px', background: 'rgba(255, 255, 255, 0.03)', border: '1px solid var(--border)' }}>
              <div style={{ fontSize: '11px', color: 'var(--text-secondary)', marginBottom: '6px' }}>LATENCY</div>
              <div style={{ fontSize: '18px', fontWeight: 700 }}>{latencyLabel}</div>
            </div>
            <div style={{ padding: '14px 16px', borderRadius: '14px', background: 'rgba(255, 255, 255, 0.03)', border: '1px solid var(--border)' }}>
              <div style={{ fontSize: '11px', color: 'var(--text-secondary)', marginBottom: '6px' }}>STATUS</div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '14px', fontWeight: 600 }}>
                <span style={{
                  width: '10px',
                  height: '10px',
                  borderRadius: '50%',
                  background: connected ? 'var(--green)' : 'var(--red)',
                  boxShadow: `0 0 0 6px ${connected ? 'rgba(52, 211, 153, 0.12)' : 'rgba(251, 113, 133, 0.12)'}`,
                }} />
                {connected ? 'Live' : 'Reconnecting'}
              </div>
            </div>
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
            <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
              Step {step.toLocaleString()}
            </span>
            <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
              {['Latency', 'Orders/sec', 'Cache misses', 'CPU usage', 'Memory usage'].map((label) => (
                <span key={label} style={{
                  padding: '6px 10px',
                  borderRadius: '999px',
                  background: 'rgba(96, 165, 250, 0.1)',
                  color: 'var(--text-primary)',
                  border: '1px solid rgba(96, 165, 250, 0.16)',
                  fontSize: '11px',
                }}>
                  {label}
                </span>
              ))}
            </div>
          </div>
        </div>
      </header>

      <Stats book={book} step={step} fillCount={fills.length} />

      <div style={{
        display: 'grid',
        gridTemplateColumns: '1fr 1fr',
        gap: '16px',
      }}>
        <div style={{
          background: 'var(--bg-card)',
          border: '1px solid var(--border)',
          borderRadius: '16px',
          padding: '16px',
          display: 'flex',
          flexDirection: 'column',
          gap: '12px',
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', flexWrap: 'wrap' }}>
            <div>
              <div style={{ fontSize: '11px', color: 'var(--text-secondary)', marginBottom: '4px' }}>AI ANALYSIS</div>
              <div style={{ fontSize: '18px', fontWeight: 700 }}>Strategy, market report, simulation summary</div>
            </div>
            <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
              {llmConfig ? `Model: ${llmConfig.chat_model}` : 'LM Studio not reported yet'}
            </div>
          </div>
          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
            {[
              ['strategy_plan', 'Strategy Plan'],
              ['market_report', 'Market Report'],
              ['simulation_summary', 'Simulation Summary'],
              ['regime_similarity', 'Find Similar Regimes'],
            ].map(([value, label]) => (
              <button
                key={value}
                onClick={() => requestAnalysis(value)}
                style={{
                  padding: '9px 12px',
                  borderRadius: '999px',
                  border: analysisType === value ? '1px solid var(--cyan)' : '1px solid var(--border)',
                  background: analysisType === value ? 'rgba(34, 211, 238, 0.14)' : 'rgba(255, 255, 255, 0.03)',
                  color: 'var(--text-primary)',
                  cursor: 'pointer',
                }}
              >
                {label}
              </button>
            ))}
          </div>
          <div style={{
            minHeight: '120px',
            padding: '12px',
            borderRadius: '12px',
            background: 'rgba(255, 255, 255, 0.03)',
            border: '1px solid var(--border)',
            whiteSpace: 'pre-wrap',
            lineHeight: 1.6,
            color: analysisText ? 'var(--text-primary)' : 'var(--text-secondary)',
          }}>
            {analysisText || 'Click a report button to generate analysis from the live simulator state.'}
          </div>

          <div style={{
            padding: '12px',
            borderRadius: '12px',
            background: 'rgba(255, 255, 255, 0.03)',
            border: '1px solid var(--border)',
            display: 'grid',
            gap: '10px',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', flexWrap: 'wrap' }}>
              <div>
                <div style={{ fontSize: '11px', color: 'var(--text-secondary)', marginBottom: '4px' }}>REGIME MATCHES</div>
                <div style={{ fontSize: '15px', fontWeight: 700 }}>Embedding-based similarity search</div>
              </div>
              <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                {regimeMeta ? `Archive size: ${regimeMeta.archiveSize}` : 'Waiting for a similarity request'}
              </div>
            </div>
            <div style={{ fontSize: '13px', color: 'var(--text-secondary)', lineHeight: 1.6 }}>
              {regimeSummary}
            </div>
            {regimeMeta?.currentDescription ? (
              <div style={{
                padding: '10px 12px',
                borderRadius: '10px',
                background: 'rgba(0, 0, 0, 0.14)',
                fontSize: '12px',
                color: 'var(--text-secondary)',
                lineHeight: 1.6,
              }}>
                <strong style={{ color: 'var(--text-primary)' }}>Current regime:</strong> {regimeMeta.currentDescription}
              </div>
            ) : null}
            <div style={{ display: 'grid', gap: '8px' }}>
              {regimeMatches.length > 0 ? regimeMatches.map((match) => (
                <div key={`${match.step}-${match.score}`} style={{
                  padding: '10px 12px',
                  borderRadius: '10px',
                  border: '1px solid var(--border)',
                  background: 'rgba(255, 255, 255, 0.02)',
                  display: 'grid',
                  gap: '6px',
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', flexWrap: 'wrap' }}>
                    <strong>Step {match.step}</strong>
                    <span style={{ color: 'var(--cyan)', fontWeight: 700 }}>Similarity {match.score}</span>
                  </div>
                  <div style={{ fontSize: '12px', color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                    {match.description}
                  </div>
                </div>
              )) : (
                <div style={{ fontSize: '12px', color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                  No ranked matches yet. Once the archive fills, the closest past regimes will appear here.
                </div>
              )}
            </div>
          </div>
        </div>

        <div style={{
          background: 'var(--bg-card)',
          border: '1px solid var(--border)',
          borderRadius: '16px',
          padding: '16px',
          display: 'grid',
          gap: '10px',
          alignContent: 'start',
        }}>
          <div style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>MODEL SETTINGS</div>
          <div style={{ fontSize: '14px' }}>Strategy planning: <strong>{llmConfig?.chat_model ?? 'qwen/qwen3-4b-2507'}</strong></div>
          <div style={{ fontSize: '14px' }}>Market analysis: <strong>{llmConfig?.chat_model ?? 'qwen/qwen3-4b-2507'}</strong></div>
          <div style={{ fontSize: '14px' }}>Embeddings: <strong>{llmConfig?.embed_model ?? 'nomic-embed-text'}</strong></div>
          <div style={{ fontSize: '12px', color: 'var(--text-secondary)', lineHeight: 1.6 }}>
            The dashboard asks LM Studio for a live plan or report using the current exchange snapshot. If the local server is unavailable, the simulator continues running and only the analysis request will fail.
          </div>
        </div>
      </div>

      <div style={{
        display: 'grid',
        gridTemplateColumns: '1fr 2fr 1fr',
        gap: '16px',
        minHeight: '400px',
      }}>
        <OrderBook book={book} />
        <PriceChart data={priceHistory} />
        <TradeFeed fills={fills} />
      </div>

      <AgentPanel agents={agents} />

      <LatencyPanel latency={latency} />
    </div>
  )
}

// AstraX repo sync
