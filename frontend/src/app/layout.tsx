import type { Metadata } from 'next'
import { Bricolage_Grotesque, IBM_Plex_Sans, IBM_Plex_Mono } from 'next/font/google'
import { Toaster } from 'react-hot-toast'
import '../styles/globals.css'

const display = Bricolage_Grotesque({
  subsets: ['latin'],
  variable: '--font-display',
})

const body = IBM_Plex_Sans({
  subsets: ['latin'],
  weight: ['400', '500', '600'],
  variable: '--font-body',
})

const mono = IBM_Plex_Mono({
  subsets: ['latin'],
  weight: ['400', '500'],
  variable: '--font-mono',
})

export const metadata: Metadata = {
  title: 'BlessedEar — Music Discovery',
  description: 'Real recommendations, built from your own listening history.',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" className={`${display.variable} ${body.variable} ${mono.variable}`}>
      <body className="font-body bg-ink text-bone">
        {children}
        <Toaster
          position="top-right"
          toastOptions={{
            className: 'font-body',
            style: {
              background: '#211E29',
              color: '#F2EDE4',
              border: '1px solid #38333F',
              borderRadius: '0.875rem',
              fontSize: '0.875rem',
            },
            success: { iconTheme: { primary: '#E8A33D', secondary: '#211E29' } },
            error: { iconTheme: { primary: '#E85C4A', secondary: '#211E29' } },
          }}
        />
      </body>
    </html>
  )
}