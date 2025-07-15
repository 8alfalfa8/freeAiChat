import { type NextRequest, NextResponse } from "next/server"

interface UrlIngestRequest {
  url: string
  chunk_size: number
  preprocess: boolean
}

export async function POST(request: NextRequest) {
  try {
    const body: UrlIngestRequest = await request.json()

    if (!body.url || !isValidUrl(body.url)) {
      return NextResponse.json(
        {
          success: false,
          message: "有効なURLを入力してください",
        },
        { status: 400 },
      )
    }

    const startTime = Date.now()

    // FastAPIエンドポイントに送信
    const fastApiUrl = process.env.FASTAPI_URL || "http://localhost:8000"
    const response = await fetch(`${fastApiUrl}/ingest-url`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        // 必要に応じてAPIキーを追加
        // ...(process.env.FASTAPI_API_KEY && {
        //  Authorization: `Bearer ${process.env.FASTAPI_API_KEY}`,
        //}),
      },
      body: JSON.stringify({
        url: body.url,
        chunk_size: body.chunk_size || 1000,
        preprocess: body.preprocess !== false,
      }),
    })

    if (!response.ok) {
      throw new Error(`FastAPI エラー: ${response.status}`)
    }

    const result = await response.json()
    const processingTime = (Date.now() - startTime) / 1000

    return NextResponse.json({
      success: true,
      message: "URLからのデータが正常に追加されました",
      chunks: result.chunks,
      processing_time: processingTime,
    })
  } catch (error) {
    console.error("URL ingest error:", error)

    return NextResponse.json(
      {
        success: false,
        message: "URLの処理中にエラーが発生しました",
        details: error instanceof Error ? error.message : "不明なエラー",
      },
      { status: 500 },
    )
  }
}

function isValidUrl(string: string): boolean {
  try {
    new URL(string)
    return true
  } catch (_) {
    return false
  }
}
