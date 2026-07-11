'use client'

import { useState } from 'react'

interface TascoSearchItem {
  poi_id: string | null
  vector_id: string
  name: string | null
  text: string | null
  score: number | null
  matched_attribute_count: number
  payload: Record<string, unknown>
}

interface RankingSignal {
  signal: string
  confidence: number
}

interface HardFilters {
  brand: string | null
  category: string | null
  subcategory: string | null
  city: string | null
  district: string | null
}

interface SearchResponse {
  original_query: string
  normalized_query: string
  hard_filters: HardFilters
  ranking_signals: RankingSignal[]
  count: number
  items: TascoSearchItem[]
}

const styles = {
  main: {
    maxWidth: 760,
    margin: '0 auto',
    padding: '48px 24px 80px',
  } as React.CSSProperties,
  heading: {
    fontSize: 28,
    fontWeight: 500,
    margin: '0 0 4px',
    color: '#0a0a0a',
  } as React.CSSProperties,
  subheading: {
    fontSize: 15,
    color: '#6b6258',
    margin: '0 0 36px',
  } as React.CSSProperties,
  form: {
    display: 'flex',
    gap: 8,
    marginBottom: 36,
  } as React.CSSProperties,
  input: {
    flex: 1,
    padding: '11px 14px',
    fontSize: 15,
    border: '1px solid #d4d0ca',
    outline: 'none',
    background: '#fff',
    color: '#0a0a0a',
  } as React.CSSProperties,
  button: {
    padding: '11px 22px',
    background: '#0a0a0a',
    color: '#faf9f6',
    border: 'none',
    cursor: 'pointer',
    fontSize: 15,
    whiteSpace: 'nowrap',
  } as React.CSSProperties,
  buttonDisabled: {
    opacity: 0.4,
    cursor: 'not-allowed',
  } as React.CSSProperties,
  error: {
    background: '#fef2f2',
    border: '1px solid #fca5a5',
    padding: '14px 16px',
    marginBottom: 28,
    color: '#b91c1c',
    fontSize: 14,
  } as React.CSSProperties,
  analysisBox: {
    borderLeft: '3px solid #b8232c',
    background: '#f0ebe1',
    padding: '16px 20px',
    marginBottom: 32,
  } as React.CSSProperties,
  analysisLabel: {
    fontFamily: 'monospace',
    fontSize: 10,
    letterSpacing: '0.14em',
    textTransform: 'uppercase' as const,
    color: '#6b6258',
    marginBottom: 10,
    display: 'block',
  } as React.CSSProperties,
  analysisRow: {
    fontSize: 14,
    color: '#1a1a1a',
    margin: '4px 0',
  } as React.CSSProperties,
  signal: {
    display: 'inline-block',
    fontFamily: 'monospace',
    fontSize: 11,
    padding: '2px 7px',
    border: '1px solid #d4d0ca',
    marginRight: 6,
    marginTop: 4,
    color: '#6b6258',
  } as React.CSSProperties,
  resultsHeader: {
    fontFamily: 'monospace',
    fontSize: 11,
    letterSpacing: '0.14em',
    textTransform: 'uppercase' as const,
    color: '#6b6258',
    marginBottom: 16,
  } as React.CSSProperties,
  resultCard: {
    border: '1px solid #e8e4dc',
    padding: '16px 18px',
    marginBottom: 10,
    background: '#fff',
  } as React.CSSProperties,
  resultMeta: {
    display: 'flex',
    justifyContent: 'space-between',
    marginBottom: 8,
  } as React.CSSProperties,
  resultId: {
    fontFamily: 'monospace',
    fontSize: 11,
    color: '#a09890',
  } as React.CSSProperties,
  resultScore: {
    fontFamily: 'monospace',
    fontSize: 11,
    color: '#b8232c',
  } as React.CSSProperties,
  resultText: {
    fontSize: 14,
    lineHeight: 1.6,
    color: '#1a1a1a',
    margin: 0,
  } as React.CSSProperties,
  empty: {
    color: '#6b6258',
    fontSize: 14,
    padding: '24px 0',
  } as React.CSSProperties,
  loading: {
    color: '#6b6258',
    fontSize: 14,
    padding: '24px 0',
  } as React.CSSProperties,
}

function activeFilters(hf: HardFilters): string {
  return Object.entries(hf)
    .filter(([, v]) => v !== null)
    .map(([k, v]) => `${k}: ${v}`)
    .join(' · ') || 'none'
}

export default function SearchPage() {
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [data, setData] = useState<SearchResponse | null>(null)

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault()
    const q = query.trim()
    if (!q) return

    setLoading(true)
    setError(null)
    setData(null)

    try {
      const res = await fetch('/api/tasco/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: q }),
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error((err as { detail?: string }).detail ?? `HTTP ${res.status}`)
      }
      setData(await res.json() as SearchResponse)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error')
    } finally {
      setLoading(false)
    }
  }

  return (
    <main style={styles.main}>
      <h1 style={styles.heading}>AI Semantic Search</h1>
      <p style={styles.subheading}>Tìm kiếm địa điểm bằng ngôn ngữ tự nhiên</p>

      <form onSubmit={handleSearch} style={styles.form}>
        <input
          type="text"
          value={query}
          onChange={e => setQuery(e.target.value)}
          placeholder="Ví dụ: quán cafe yên tĩnh có wifi ở Quận 1"
          style={styles.input}
          disabled={loading}
        />
        <button
          type="submit"
          disabled={loading || !query.trim()}
          style={{ ...styles.button, ...(loading || !query.trim() ? styles.buttonDisabled : {}) }}
        >
          {loading ? 'Đang tìm…' : 'Tìm kiếm'}
        </button>
      </form>

      {error && <div style={styles.error}>{error}</div>}

      {loading && <p style={styles.loading}>Đang phân tích truy vấn và tìm kiếm…</p>}

      {data && !loading && (
        <>
          <div style={styles.analysisBox}>
            <span style={styles.analysisLabel}>Phân tích truy vấn</span>
            <p style={styles.analysisRow}>
              <strong>Normalized:</strong> {data.normalized_query || data.original_query}
            </p>
            {activeFilters(data.hard_filters) !== 'none' && (
              <p style={styles.analysisRow}>
                <strong>Filters:</strong> {activeFilters(data.hard_filters)}
              </p>
            )}
            {data.ranking_signals.length > 0 && (
              <div style={{ marginTop: 8 }}>
                {data.ranking_signals.map((s, i) => (
                  <span key={i} style={styles.signal}>
                    {s.signal} {(s.confidence * 100).toFixed(0)}%
                  </span>
                ))}
              </div>
            )}
          </div>

          <p style={styles.resultsHeader}>{data.count} kết quả</p>

          {data.items.length === 0 ? (
            <p style={styles.empty}>
              Không có kết quả. Collection Qdrant có thể chưa có dữ liệu POI.
            </p>
          ) : (
            data.items.map((r, i) => (
              <div key={i} style={styles.resultCard}>
                <div style={styles.resultMeta}>
                  <span style={styles.resultId}>{r.name || r.poi_id || r.vector_id}</span>
                  <span style={styles.resultScore}>score: {r.score?.toFixed(4) ?? '-'}</span>
                </div>
                <p style={styles.resultText}>{r.text}</p>
              </div>
            ))
          )}
        </>
      )}
    </main>
  )
}
