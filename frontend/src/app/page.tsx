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

function StarRating({ rating }: { rating: number }) {
  const filled = Math.round(rating)
  return (
    <span className="stars" aria-label={`${rating.toFixed(1)} out of 5 stars`}>
      {[1, 2, 3, 4, 5].map(i => (
        <span key={i} className={i <= filled ? 'star star--full' : 'star star--empty'}>★</span>
      ))}
    </span>
  )
}

function IconPin() {
  return (
    <svg className="icon-pin" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M7 1C4.79 1 3 2.79 3 5c0 3.25 4 8 4 8s4-4.75 4-8c0-2.21-1.79-4-4-4z"/>
      <circle cx="7" cy="5" r="1.2" fill="currentColor" stroke="none"/>
    </svg>
  )
}

function IconClock() {
  return (
    <svg className="icon-clock" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="7" cy="7" r="5.5"/>
      <path d="M7 4.5v3l1.5 1.5"/>
    </svg>
  )
}

function IconCheck() {
  return (
    <svg className="icon-check" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
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

              // Category line: brand · category · sub_category
              const catParts = [r.brand, r.category, r.sub_category].filter(Boolean) as string[]

              // Location line: address, district, city
              const locationParts = [r.address, r.district, r.city].filter(Boolean) as string[]

              const priceStr = r.price_level != null
                ? '$'.repeat(Math.min(r.price_level, 4))
                : null

              const popularityPct = r.popularity_score != null
                ? Math.round(r.popularity_score * 100)
                : null

              const bodyText = r.description || r.text
              const hasChips = reasons.length > 0 || (r.attributes?.length ?? 0) > 0 || (r.tags?.length ?? 0) > 0

              return (
                <div key={i} className="result-card">

                  {/* ── Name + rank ── */}
                  <div className="card-header">
                    <span className="rank-badge">#{i + 1}</span>
                    <h2 className="card-name">{r.name || r.poi_id || r.vector_id}</h2>
                  </div>

                  {/* ── Rating row (always shown when data present) ── */}
                  {r.rating != null && (
                    <div className="card-rating-row">
                      <span className="rating-score">{r.rating.toFixed(1)}</span>
                      <StarRating rating={r.rating} />
                      {r.review_count != null && (
                        <span className="rating-count">({r.review_count.toLocaleString()} reviews)</span>
                      )}
                      {priceStr && (
                        <>
                          <span className="rating-dot">·</span>
                          <span className="price-level">{priceStr}</span>
                        </>
                      )}
                    </div>
                  )}

                  {/* ── Category / brand ── */}
                  {catParts.length > 0 && (
                    <p className="card-category">{catParts.join(' · ')}</p>
                  )}

                  {/* ── Address / location ── */}
                  {locationParts.length > 0 && (
                    <p className="card-location">
                      <IconPin />
                      {locationParts.join(', ')}
                    </p>
                  )}

                  {/* ── Opening hours ── */}
                  {r.opening_hours && (
                    <p className="card-hours">
                      <IconClock />
                      {r.opening_hours}
                    </p>
                  )}

                  {/* ── Popularity bar ── */}
                  {popularityPct != null && (
                    <div className="card-popularity">
                      <div className="popularity-bar-track">
                        <div className="popularity-bar-fill" style={{ width: `${popularityPct}%` }} />
                      </div>
                      <span className="popularity-label">{popularityPct}% popular</span>
                    </div>
                  )}

                  {/* ── Description ── */}
                  {bodyText && <p className="card-description">{bodyText}</p>}

                  {/* ── Matched attributes + tags ── */}
                  {hasChips && (
                    <>
                      <hr className="card-chips-divider" />
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
                    </>
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
