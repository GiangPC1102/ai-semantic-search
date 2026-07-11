'use client'

import { useState } from 'react'

interface TascoSearchItem {
  poi_id: string | null
  vector_id: string
  name: string | null
  text: string | null
  score: number | null
  matched_attribute_count: number
  matched_attribute_ids: string[]
  payload: Record<string, unknown>
}

interface RankingSignal {
  signal: string
  confidence: number
  signal_name_vi: string | null
}

interface HardFilters {
  brand: string | null
  category: string | null
  subcategory: string | null
  city: string | null
  district: string | null
}

interface AttributeHit {
  id: string
  attribute_id: string | null
  name: string | null
}

interface SearchResponse {
  original_query: string
  normalized_query: string
  hard_filters: HardFilters
  ranking_signals: RankingSignal[]
  attribute_hits: AttributeHit[]
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

  // Build attribute id → display name map from the global attribute hits list.
  const attrMap: Record<string, string> = {}
  if (data) {
    for (const h of data.attribute_hits) {
      if (h.attribute_id && h.name) attrMap[h.attribute_id] = h.name
    }
  }

  // Normalise scores relative to the top result so the bar is always meaningful.
  const maxScore = data
    ? Math.max(...data.items.map(r => r.score ?? 0), 0.001)
    : 1

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
                      {s.signal_name_vi || s.signal} {(s.confidence * 100).toFixed(0)}%
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
              data.items.map((r, i) => {
                const pct = Math.round(((r.score ?? 0) / maxScore) * 100)
                const reasons = (r.matched_attribute_ids ?? [])
                  .map(id => attrMap[id])
                  .filter(Boolean) as string[]

                return (
                  <div key={i} className="result-card">
                    <div className="result-meta">
                      <div className="result-rank-name">
                        <span className="rank-badge">#{i + 1}</span>
                        <div className="result-name-wrap">
                          <span className="result-name">{r.name || r.poi_id || r.vector_id}</span>
                          {r.poi_id && <span className="result-poi-id">{r.poi_id}</span>}
                        </div>
                      </div>
                      <div className="result-score-wrap">
                        <div className="relevance-bar">
                          <div className="relevance-fill" style={{ width: `${pct}%` }} />
                        </div>
                        <span className="result-score">{pct}%</span>
                      </div>
                    </div>
                    {r.text && <p className="result-text">{r.text}</p>}
                    {reasons.length > 0 && (
                      <div className="reason-chips">
                        {reasons.map(name => (
                          <span key={name} className="reason-chip">✓ {name}</span>
                        ))}
                      </div>
                    )}
                  </div>
                )
              })
            )}
          </>
        )}
    </main>
  )
}
