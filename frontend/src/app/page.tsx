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

function activeFilters(hf: HardFilters): string {
  return Object.entries(hf)
    .filter(([, v]) => v !== null)
    .map(([k, v]) => `${k}: ${v}`)
    .join(' · ') || ''
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

  const filters = data ? activeFilters(data.hard_filters) : ''

  return (
    <main className="page">
        <p className="eyebrow">TASCO AI · POI Search</p>
        <h1 className="heading">Tìm kiếm địa điểm<br />bằng ngôn ngữ tự nhiên</h1>
        <p className="subheading">
          Nhập mô tả — AI sẽ hiểu ý định, lọc theo tiêu chí và tìm đúng nơi bạn cần.
        </p>

        <form onSubmit={handleSearch} className="search-form">
          <input
            type="text"
            className="search-input"
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder="Ví dụ: quán cafe yên tĩnh có wifi ở Quận 1"
            disabled={loading}
            autoFocus
          />
          <button
            type="submit"
            className="search-btn"
            disabled={loading || !query.trim()}
          >
            {loading ? 'Đang tìm…' : 'Tìm kiếm'}
          </button>
        </form>

        {error && (
          <div className="error-box">
            {error}
          </div>
        )}

        {loading && (
          <div className="loading-wrap">
            <div className="loading-spinner" />
            Đang phân tích truy vấn và tìm kiếm…
          </div>
        )}

        {data && !loading && (
          <>
            <div className="analysis-card">
              <span className="analysis-label">Phân tích truy vấn</span>
              <p className="analysis-row">
                <strong>Truy vấn:</strong> {data.normalized_query || data.original_query}
              </p>
              {filters && (
                <p className="analysis-row">
                  <strong>Bộ lọc:</strong> {filters}
                </p>
              )}
              {data.ranking_signals.length > 0 && (
                <div className="signals-wrap">
                  {data.ranking_signals.map((s, i) => (
                    <span key={i} className="signal-chip">
                      {s.signal} {(s.confidence * 100).toFixed(0)}%
                    </span>
                  ))}
                </div>
              )}
            </div>

            <p className="results-header">{data.count} kết quả</p>

            {data.items.length === 0 ? (
              <div className="empty-state">
                <p>Không tìm thấy địa điểm phù hợp.</p>
                <small>Thử thay đổi từ khoá hoặc bỏ bớt tiêu chí lọc.</small>
              </div>
            ) : (
              data.items.map((r, i) => (
                <div key={i} className="result-card">
                  <div className="result-meta">
                    <span className="result-name">{r.name || r.poi_id || r.vector_id}</span>
                    <div className="result-badges">
                      {r.matched_attribute_count > 0 && (
                        <span className="attr-badge">{r.matched_attribute_count} attr</span>
                      )}
                      {r.score !== null && (
                        <span className="result-score">{r.score.toFixed(4)}</span>
                      )}
                    </div>
                  </div>
                  {r.text && <p className="result-text">{r.text}</p>}
                </div>
              ))
            )}
          </>
        )}
    </main>
  )
}
