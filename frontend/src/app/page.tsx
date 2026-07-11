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

const C = {
  bg: '#06101f',
  surface: '#0d1f3c',
  surfaceHover: '#102540',
  border: '#1a3560',
  accent: '#00c2e0',
  accentDim: '#00c2e022',
  text: '#c8dff7',
  muted: '#5a7a9e',
  error: '#ff4757',
  errorBg: '#1a0a0d',
  score: '#00c2e0',
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
    <>
      <style>{`
        * { box-sizing: border-box; margin: 0; padding: 0; }
        html, body { background: ${C.bg}; min-height: 100vh; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif; color: ${C.text}; }

        .page { max-width: 720px; margin: 0 auto; padding: 64px 24px 96px; }

        .eyebrow {
          font-size: 11px;
          letter-spacing: 0.18em;
          text-transform: uppercase;
          color: ${C.accent};
          font-weight: 600;
          margin-bottom: 14px;
        }
        .heading {
          font-size: clamp(26px, 5vw, 36px);
          font-weight: 700;
          color: #e8f4ff;
          line-height: 1.15;
          margin-bottom: 10px;
          text-wrap: balance;
        }
        .subheading {
          font-size: 15px;
          color: ${C.muted};
          margin-bottom: 44px;
          line-height: 1.5;
        }

        .search-form {
          display: flex;
          gap: 0;
          margin-bottom: 40px;
          border: 1px solid ${C.border};
          border-radius: 6px;
          overflow: hidden;
          transition: border-color 0.2s;
        }
        .search-form:focus-within {
          border-color: ${C.accent};
          box-shadow: 0 0 0 3px ${C.accentDim};
        }
        .search-input {
          flex: 1;
          padding: 14px 18px;
          font-size: 15px;
          background: ${C.surface};
          color: ${C.text};
          border: none;
          outline: none;
        }
        .search-input::placeholder { color: ${C.muted}; }
        .search-input:disabled { opacity: 0.5; }
        .search-btn {
          padding: 14px 24px;
          background: ${C.accent};
          color: #06101f;
          border: none;
          cursor: pointer;
          font-size: 14px;
          font-weight: 700;
          letter-spacing: 0.04em;
          white-space: nowrap;
          transition: opacity 0.15s;
        }
        .search-btn:disabled { opacity: 0.4; cursor: not-allowed; }
        .search-btn:not(:disabled):hover { opacity: 0.88; }

        .error-box {
          background: ${C.errorBg};
          border: 1px solid ${C.error}44;
          border-left: 3px solid ${C.error};
          padding: 14px 18px;
          margin-bottom: 32px;
          color: ${C.error};
          font-size: 14px;
          border-radius: 4px;
        }

        .loading-wrap {
          padding: 32px 0;
          display: flex;
          align-items: center;
          gap: 12px;
          color: ${C.muted};
          font-size: 14px;
        }
        .loading-spinner {
          width: 16px;
          height: 16px;
          border: 2px solid ${C.border};
          border-top-color: ${C.accent};
          border-radius: 50%;
          animation: spin 0.7s linear infinite;
          flex-shrink: 0;
        }
        @keyframes spin { to { transform: rotate(360deg); } }
        @media (prefers-reduced-motion: reduce) {
          .loading-spinner { animation: none; border-top-color: ${C.accent}; }
        }

        .analysis-card {
          background: ${C.surface};
          border: 1px solid ${C.border};
          border-top: 2px solid ${C.accent};
          border-radius: 6px;
          padding: 20px 22px;
          margin-bottom: 32px;
        }
        .analysis-label {
          font-size: 10px;
          letter-spacing: 0.16em;
          text-transform: uppercase;
          color: ${C.accent};
          font-weight: 700;
          display: block;
          margin-bottom: 14px;
        }
        .analysis-row {
          font-size: 14px;
          color: ${C.text};
          margin-bottom: 8px;
          line-height: 1.5;
        }
        .analysis-row strong { color: #e8f4ff; font-weight: 600; margin-right: 6px; }
        .signals-wrap { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
        .signal-chip {
          font-family: 'SF Mono', 'Fira Code', monospace;
          font-size: 11px;
          padding: 3px 9px;
          border: 1px solid ${C.border};
          border-radius: 3px;
          color: ${C.accent};
          background: ${C.accentDim};
        }

        .results-header {
          font-family: 'SF Mono', 'Fira Code', monospace;
          font-size: 11px;
          letter-spacing: 0.14em;
          text-transform: uppercase;
          color: ${C.muted};
          margin-bottom: 14px;
          display: flex;
          align-items: center;
          gap: 10px;
        }
        .results-header::after {
          content: '';
          flex: 1;
          height: 1px;
          background: ${C.border};
        }

        .result-card {
          background: ${C.surface};
          border: 1px solid ${C.border};
          border-radius: 6px;
          padding: 18px 20px;
          margin-bottom: 10px;
          transition: border-color 0.15s, background 0.15s;
        }
        .result-card:hover {
          border-color: ${C.accent}66;
          background: ${C.surfaceHover};
        }
        .result-meta {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 10px;
          gap: 12px;
        }
        .result-name {
          font-size: 15px;
          font-weight: 600;
          color: #e8f4ff;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }
        .result-badges {
          display: flex;
          align-items: center;
          gap: 8px;
          flex-shrink: 0;
        }
        .result-score {
          font-family: 'SF Mono', 'Fira Code', monospace;
          font-size: 11px;
          color: ${C.accent};
          white-space: nowrap;
        }
        .attr-badge {
          font-size: 10px;
          padding: 2px 7px;
          background: ${C.accentDim};
          border: 1px solid ${C.accent}44;
          border-radius: 2px;
          color: ${C.accent};
          font-weight: 600;
          white-space: nowrap;
        }
        .result-text {
          font-size: 14px;
          line-height: 1.65;
          color: ${C.muted};
        }

        .empty-state {
          text-align: center;
          padding: 56px 0;
          color: ${C.muted};
        }
        .empty-state p { font-size: 15px; margin-bottom: 8px; }
        .empty-state small { font-size: 13px; color: ${C.border}; }

        .divider {
          border: none;
          border-top: 1px solid ${C.border};
          margin: 40px 0;
        }
      `}</style>

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
    </>
  )
}
