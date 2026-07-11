'use client'

import { useState } from 'react'

interface PoiDetail {
  id: string
  name: string
  brand_name: string | null
  category: string | null
  subcategory: string | null
  city: string | null
  district: string | null
  address: string | null
  rating: number | null
  review_count: number | null
  popularity_score: number | null
  price_level: string | null
  open_hours: { is_24h?: boolean; open_time?: string; close_time?: string } | null
  description: string | null
}

interface SearchExplain {
  hard_attributes: Record<string, string>
  ranking_signals: string[]
  attributes: string[]
}

interface TascoSearchItem {
  poi_id: string | null
  vector_id: string
  name: string | null
  text: string | null
  score: number | null
  matched_attribute_count: number
  matched_attribute_ids: string[]
  attributes: string[]
  explain: SearchExplain
  payload: Record<string, unknown>
  poi: PoiDetail | null
}

interface SearchResponse {
  original_query: string
  normalized_query: string
  hard_filtered_poi_count: number
  poi_hits_count: number
  count: number
  items: TascoSearchItem[]
}

function activeFilters(hard: Record<string, string> | undefined): string {
  if (!hard) return ''
  return Object.entries(hard)
    .map(([k, v]) => `${k}: ${v}`)
    .join(' · ') || ''
}

function formatOpenHours(
  hours: PoiDetail['open_hours'],
): string | null {
  if (!hours) return null
  if (hours.is_24h) return 'Open 24 hours'
  const range = [hours.open_time, hours.close_time].filter(Boolean).join(' – ')
  return range || null
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

function PriceLevel({ level }: { level: number }) {
  const clamped = Math.min(Math.max(level, 1), 5)
  const labels = ['', 'Rẻ', 'Bình dân', 'Trung bình', 'Khá mắc', 'Cao cấp']
  return (
    <span className="price-indicator" title={`${labels[clamped]} (${clamped}/5)`}>
      <span className="price-indicator-filled">{'$'.repeat(clamped)}</span>
      <span className="price-indicator-empty">{'$'.repeat(5 - clamped)}</span>
    </span>
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

  const firstExplain = data?.items[0]?.explain
  const filters = activeFilters(firstExplain?.hard_attributes)
  const signalLabels = firstExplain?.ranking_signals ?? []

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
            {signalLabels.length > 0 && (
              <div className="signals-wrap">
                {signalLabels.map((s, i) => (
                  <span key={i} className="signal-chip">{s}</span>
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
              const poi = r.poi

              const catParts = [
                poi?.brand_name,
                poi?.category,
                poi?.subcategory,
              ].filter(Boolean) as string[]

              const locationParts = [
                poi?.address,
                poi?.city,
              ].filter(Boolean) as string[]

              const priceNum = poi?.price_level
                ? Number.parseInt(poi.price_level, 10)
                : NaN
              const validPrice = !Number.isNaN(priceNum) && priceNum >= 1 && priceNum <= 5

              const popularityPct = poi?.popularity_score != null
                ? Math.round(poi.popularity_score)
                : null

              const bodyText = poi?.description || r.text
              const hoursLabel = formatOpenHours(poi?.open_hours ?? null)

              const explainHardAttrs = r.explain?.hard_attributes ?? {}
              const explainSignals = r.explain?.ranking_signals ?? []
              const explainMatched = r.explain?.attributes ?? []
              const hasExplain =
                Object.keys(explainHardAttrs).length > 0 ||
                explainSignals.length > 0 ||
                explainMatched.length > 0

              const hasAnalysis = hasExplain

              return (
                <div key={i} className="result-card">
                  {/* ── Two-column layout ── */}
                  <div className="card-columns">

                  {/* ── Left (70%): Place Info ── */}
                  <div className="card-place-zone">
                    <div className="card-header">
                      <span className="rank-badge">#{i + 1}</span>
                      <h2 className="card-name">{r.name || r.poi_id || r.vector_id}</h2>
                    </div>

                    {(r.attributes?.length ?? 0) > 0 && (
                      <div className="tag-chips">
                        {r.attributes.map(a => (
                          <span key={a} className="tag-chip">{a}</span>
                        ))}
                      </div>
                    )}

                    {bodyText && <p className="card-description">{bodyText}</p>}

                    {poi?.rating != null && (
                      <div className="card-rating-row">
                        <span className="rating-score">{poi.rating.toFixed(1)}</span>
                        <StarRating rating={poi.rating} />
                        {poi.review_count != null && (
                          <span className="rating-count">({poi.review_count.toLocaleString()} reviews)</span>
                        )}
                        {validPrice && (
                          <>
                            <span className="rating-dot">·</span>
                            <PriceLevel level={priceNum} />
                          </>
                        )}
                      </div>
                    )}

                    {catParts.length > 0 && (
                      <p className="card-category">{catParts.join(' · ')}</p>
                    )}

                    {locationParts.length > 0 && (
                      <p className="card-location">
                        <IconPin />
                        {locationParts.join(', ')}
                      </p>
                    )}

                    {hoursLabel && (
                      <p className="card-hours">
                        <IconClock />
                        {hoursLabel}
                      </p>
                    )}

                    {popularityPct != null && (
                      <div className="card-popularity">
                        <span className="popularity-label-pre">Popularity</span>
                        <div className="popularity-bar-track">
                          <div className="popularity-bar-fill" style={{ width: `${popularityPct}%` }} />
                        </div>
                        <span className="popularity-label">{popularityPct}%</span>
                      </div>
                    )}
                  </div>

                  {/* ── Right (30%): System Analysis ── */}
                  {hasAnalysis && (
                    <div className="card-analysis-zone">
                      <div className="analysis-zone-header">
                        <IconBrain />
                        <span>Why this result</span>
                      </div>

                      {Object.keys(explainHardAttrs).length > 0 && (
                        <div className="explain-section">
                          <span className="explain-section-label">Applied filters</span>
                          <div className="explain-chips">
                            {Object.entries(explainHardAttrs).map(([k, v]) => (
                              <span key={k} className="filter-chip">{v}</span>
                            ))}
                          </div>
                        </div>
                      )}

                      {explainSignals.length > 0 && (
                        <div className="explain-section">
                          <span className="explain-section-label">Ranking signals</span>
                          <div className="explain-chips">
                            {explainSignals.map(s => (
                              <span key={s} className="signal-chip">{s}</span>
                            ))}
                          </div>
                        </div>
                      )}

                      {explainMatched.length > 0 && (
                        <div className="explain-section">
                          <span className="explain-section-label">Matched attributes</span>
                          <div className="reason-chips">
                            {explainMatched.map(name => (
                              <span key={name} className="reason-chip">
                                <IconCheck />
                                {name}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}

                  </div>{/* end card-columns */}
                </div>
              )
            })
          )}
        </>
      )}
    </main>
  )
}
