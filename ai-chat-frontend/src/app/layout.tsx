import type React from "react"
import type { Metadata } from "next"
import { Inter } from "next/font/google"
import "./globals.css"
import Link from "next/link"
import { Button } from "@/components/ui/button"
import { MessageCircle, Database } from "lucide-react"

const inter = Inter({ subsets: ["latin"] })

export const metadata: Metadata = {
  title: "AIチャット & 知識ベース管理",
  description: "カスタムAPIを使用したチャットアプリケーションと知識ベース管理",
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="ja">
      <body className={inter.className}>
        <nav className="border-b bg-white/50 backdrop-blur-sm sticky top-0 z-50">
          <div className="max-w-6xl mx-auto px-4 py-3">
            <div className="flex items-center justify-between">
              <h1 className="text-xl font-bold">AIアプリケーション</h1>
              <div className="flex gap-2">
                <Button variant="ghost" size="sm" asChild>
                  <Link href="/" className="flex items-center gap-2">
                    <MessageCircle className="w-4 h-4" />
                    チャット
                  </Link>
                </Button>
                <Button variant="ghost" size="sm" asChild>
                  <Link href="/admin" className="flex items-center gap-2">
                    <Database className="w-4 h-4" />
                    管理画面
                  </Link>
                </Button>
              </div>
            </div>
          </div>
        </nav>
        {children}
      </body>
    </html>
  )
}
