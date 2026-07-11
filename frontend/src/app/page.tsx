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

function IconPin() {
  return (
    <svg className="result-location-icon" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M7 1C4.79 1 3 2.79 3 5c0 3.25 4 8 4 8s4-4.75 4-8c0-2.21-1.79-4-4-4z"/>
      <circle cx="7" cy="5" r="1.2" fill="currentColor" stroke="none"/>
    </svg>
  )
}

function IconClock() {
  return (
    <svg className="result-hours-icon" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="7" cy="7" r="5.5"/>
      <path d="M7 4.5v3l1.5 1.5"/>
    </svg>
  )
}

function IconCheck() {
  return (
    <svg className="reason-chip-icon" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M2 5l2.5 2.5L8 3"/>
    </svg>
  )
}

function IconBrain() {
  return (
    <svg className="analysis-icon" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M5 2a2 2 0 00-2 2v.5A2.5 2.5 0 005.5 7H7"/>
      <path d="M9 2a2 2 0 012 2v.5A2.5 2.5 0 018.5 7H7"/>
      <path d="M7 7v5"/>
      <path d="M4.5 9.5a1.5 1.5 0 003 0"/>
    </svg>
  )
}

export default function SearchPage() {
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [data, setData] = useState<SearchResponse | null>(null)
  const [isFilterAttribute, setIsFilterAttribute] = useState(true)

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
        body: JSON.stringify({ query: q, is_filter_attribute: isFilterAttribute }),
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

  const attrMap: Record<string, string> = {}
  if (data) {
    for (const h of data.attribute_hits) {
      if (h.attribute_id && h.name) attrMap[h.attribute_id] = h.name
    }
  }

  const maxScore = data
    ? Math.max(...data.items.map(r => r.score ?? 0), 0.001)
    : 1

  const activeSignals = new Set(data?.ranking_signals.map(s => s.signal) ?? [])

  return (
    <main className="page">
      <p className="eyebrow">
        <span className="eyebrow-dot" />
        TASCO AI · Place Search
      </p>
      <h1 className="heading">
        Find places with<br /><em>natural language</em>
      </h1>
      <p className="subheading">
        Describe what you&apos;re looking for — our AI understands intent,
        applies filters, and surfaces exactly the right places.
      </p>

      <form onSubmit={handleSearch} className="search-form">
        <input
          type="text"
          className="search-input"
          value={query}
          onChange={e => setQuery(e.target.value)}
          placeholder="e.g. quiet café with wifi in District 1"
          disabled={loading}
          autoFocus
        />
        <button
          type="submit"
          className="search-btn"
          disabled={loading || !query.trim()}
        >
          {loading ? 'Searching…' : 'Search'}
        </button>
      </form>

      <div className="toggle-row">
        <label className="toggle-label" htmlFor="filter-attr-toggle">
          Filter by attributes
        </label>
        <button
          id="filter-attr-toggle"
          type="button"
          role="switch"
          aria-checked={isFilterAttribute}
          className={`toggle-switch${isFilterAttribute ? ' toggle-switch--on' : ''}`}
          onClick={() => setIsFilterAttribute(v => !v)}
        >
          <span className="toggle-thumb" />
        </button>
      </div>

      {error && (
        <div className="error-box" role="alert">
          {error}
        </div>
      )}

      {loading && (
        <div className="loading-wrap" aria-live="polite">
          <div className="loading-spinner" />
          Analyzing query and searching…
        </div>
      )}

      {data && !loading && (
        <>
          <div className="analysis-card">
            <div className="analysis-header">
              <IconBrain />
              <span className="analysis-label">Query Analysis</span>
            </div>
            <p className="analysis-row">
              <strong>Query</strong> {data.normalized_query || data.original_query}
            </p>
            {filters && (
              <p className="analysis-row">
                <strong>Filters</strong> {filters}
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

          <p className="results-header">{data.count} result{data.count !== 1 ? 's' : ''}</p>

          {data.items.length === 0 ? (
            <div className="empty-state">
              <p>No matching places found.</p>
              <small>Try adjusting your search terms or removing some filters.</small>
            </div>
          ) : (
            data.items.map((r, i) => {
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
                  <div className="result-meta">
                    <div className="result-rank-name">
                      <span className="rank-badge">#{i + 1}</span>
                      <div className="result-name-wrap">
                        <span className="result-name">{r.name || r.poi_id || r.vector_id}</span>
                        {r.poi_id && <span className="result-poi-id">{r.poi_id}</span>}
                      </div>
                    </div>
                  </div>

                  {cats.length > 0 && (
                    <div className="result-cats">
                      {cats.map(c => <span key={c} className="result-cat-chip">{c}</span>)}
                    </div>
                  )}

                  {locationParts.length > 0 && (
                    <p className="result-location">
                      <IconPin />
                      {locationParts.join(', ')}
                    </p>
                  )}

                  {(showRating || priceStr || showPopularity) && (
                    <div className="result-stats">
                      {showRating && (
                        <span className="stat-item">
                          <span className="stat-star">★</span>
                          {r.rating!.toFixed(1)}
                          {showReviewCount && (
                            <span style={{ color: 'var(--text-muted)', fontWeight: 400 }}>
                              &nbsp;({r.review_count!.toLocaleString()})
                            </span>
                          )}
                        </span>
                      )}
                      {priceStr && <span className="stat-item stat-price">{priceStr}</span>}
                      {showPopularity && (
                        <span className="stat-item">
                          {(r.popularity_score! * 100).toFixed(0)}% popular
                        </span>
                      )}
                    </div>
                  )}

                  {r.opening_hours && (
                    <p className="result-hours">
                      <IconClock />
                      {r.opening_hours}
                    </p>
                  )}

                  {bodyText && <p className="result-text">{bodyText}</p>}

                  {reasons.length > 0 && (
                    <div className="reason-chips">
                      {reasons.map(name => (
                        <span key={name} className="reason-chip">
                          <IconCheck />
                          {name}
                        </span>
                      ))}
                    </div>
                  )}

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
