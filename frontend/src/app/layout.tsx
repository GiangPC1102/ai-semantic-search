import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'AI Semantic Search',
  description: 'Tìm kiếm địa điểm bằng ngôn ngữ tự nhiên',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="vi">
      <body style={{ margin: 0, fontFamily: 'system-ui, -apple-system, sans-serif', background: '#faf9f6' }}>
        {children}
      </body>
    </html>
  )
}
