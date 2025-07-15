import { type NextRequest, NextResponse } from "next/server"

interface TextIngestRequest {
  text: string
}

export async function POST(request: NextRequest) {
  try {
    const body: TextIngestRequest = await request.json()

    if (!body.text || body.text.trim().length === 0) {
      return NextResponse.json(
        {
          success: false,
          message: "テキストが空です",
        },
        { status: 400 },
      )
    }

    const startTime = Date.now()

    // FastAPIエンドポイントに送信
    const fastApiUrl = process.env.FASTAPI_URL || "http://localhost:8000"
    const response = await fetch(`${fastApiUrl}/ingest`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        // 必要に応じてAPIキーを追加
        //...(process.env.FASTAPI_API_KEY && {
        //  Authorization: `Bearer ${process.env.FASTAPI_API_KEY}`,
        //}),
      },
      body: JSON.stringify({
        text: body.text,
      }),
    })

    if (!response.ok) {
      throw new Error(`FastAPI エラー: ${response.status}`)
    }

    const result = await response.json()
    const processingTime = (Date.now() - startTime) / 1000

    return NextResponse.json({
      success: true,
      message: "テキストが正常に追加されました",
      chunks: result.chunks || Math.ceil(body.text.length / 1000),
      processing_time: processingTime,
    })
  } catch (error) {
    console.error("Text ingest error:", error)

    return NextResponse.json(
      {
        success: false,
        message: "テキストの処理中にエラーが発生しました",
        details: error instanceof Error ? error.message : "不明なエラー",
      },
      { status: 500 },
    )
  }
}
