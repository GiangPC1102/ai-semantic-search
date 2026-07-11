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
  // Extended POI fields — all optional; render only when present
  rating: number | null
  brand: string | null
  category: string | null
  sub_category: string | null
  city: string | null
  district: string | null
  address: string | null
  review_count: number | null
  popularity_score: number | null
  price_level: number | null
  opening_hours: string | null
  attributes: string[] | null
  tags: string[] | null
  description: string | null
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

  // Set of signal names present in this query — used to gate stat display per result.
  const activeSignals = new Set(data?.ranking_signals.map(s => s.signal) ?? [])

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

                const cats = [r.brand, r.category, r.sub_category].filter(Boolean) as string[]
                const locationParts = [r.address, r.district, r.city].filter(Boolean) as string[]
                const showRating = activeSignals.has('rating') && r.rating != null
                const showReviewCount = activeSignals.has('review_count') && r.review_count != null
                const showPopularity = activeSignals.has('popularity_score') && r.popularity_score != null
                const showPrice = activeSignals.has('price_level') && r.price_level != null
                const priceStr = showPrice ? '$'.repeat(Math.min(r.price_level!, 4)) : null
                const bodyText = r.description || r.text

                return (
                  <div key={i} className="result-card">
                    {/* Header: rank + name + score bar */}
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

                    {/* Category / brand chips */}
                    {cats.length > 0 && (
                      <div className="result-cats">
                        {cats.map(c => <span key={c} className="result-cat-chip">{c}</span>)}
                      </div>
                    )}

                    {/* Location */}
                    {locationParts.length > 0 && (
                      <p className="result-location">📍 {locationParts.join(', ')}</p>
                    )}

                    {/* Stats — only rendered when the signal was identified for this query */}
                    {(showRating || priceStr || showPopularity) && (
                      <div className="result-stats">
                        {showRating && (
                          <span className="stat-item">★ {r.rating!.toFixed(1)}{showReviewCount ? ` (${r.review_count!.toLocaleString()})` : ''}</span>
                        )}
                        {priceStr && <span className="stat-item stat-price">{priceStr}</span>}
                        {showPopularity && (
                          <span className="stat-item">🔥 {(r.popularity_score! * 100).toFixed(0)}%</span>
                        )}
                      </div>
                    )}

                    {/* Opening hours */}
                    {r.opening_hours && (
                      <p className="result-hours">⏰ {r.opening_hours}</p>
                    )}

                    {/* Description / text */}
                    {bodyText && <p className="result-text">{bodyText}</p>}

                    {/* Matched attribute chips (relevance reasons) */}
                    {reasons.length > 0 && (
                      <div className="reason-chips">
                        {reasons.map(name => (
                          <span key={name} className="reason-chip">✓ {name}</span>
                        ))}
                      </div>
                    )}

                    {/* Extra attributes & tags */}
                    {((r.attributes?.length ?? 0) > 0 || (r.tags?.length ?? 0) > 0) && (
                      <div className="tag-chips">
                        {(r.attributes ?? []).map(a => <span key={a} className="tag-chip">{a}</span>)}
                        {(r.tags ?? []).map(t => <span key={t} className="tag-chip tag-chip--tag">{t}</span>)}
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
