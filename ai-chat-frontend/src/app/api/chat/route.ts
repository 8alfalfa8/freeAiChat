import { type NextRequest, NextResponse } from "next/server"

interface ChatRequest {
  message: string
  history: Array<{
    role: "user" | "assistant"
    content: string
  }>
}

export async function POST(request: NextRequest) {
  try {
    const body: ChatRequest = await request.json()

    // 自前のAPIエンドポイントのURL（環境変数から取得）
    // const customApiUrl = process.env.CUSTOM_API_URL || "https://your-api-endpoint.com/chat"
    // const apiKey = process.env.CUSTOM_API_KEY
    // FastAPIエンドポイントに送信
    const fastApiUrl = process.env.FASTAPI_URL || "http://localhost:8000"

    // 自前のAPIに送信するリクエストボディを構築
    const apiRequestBody = {
      message: body.message,
      conversation_history: body.history,
      // 必要に応じて他のパラメータを追加
      max_tokens: 1000,
      temperature: 0.7,
    }

    // 自前のAPIにリクエストを送信
    const response = await fetch(`${fastApiUrl}/ask`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        // APIキーが必要な場合
        // ...(apiKey && { Authorization: `Bearer ${apiKey}` }),
        // または
        // ...(apiKey && { "X-API-Key": apiKey }),
      },
      // body: JSON.stringify({"question": "LangChainとは何ですか？"}),
      body: JSON.stringify({"question": apiRequestBody.message}),
    })

    if (!response.ok) {
      throw new Error(`カスタムAPI エラー: ${response.status} ${response.statusText}`)
    }

    const data = await response.json()

    // レスポンスの形式は自前のAPIに合わせて調整
    return NextResponse.json({
      // response: data.response || data.message || data.text || "回答を取得できませんでした",
      response: data.answer || "回答を取得できませんでした",
      // 必要に応じて他の情報も返す
      usage: data.usage,
      model: data.model,
    })
  } catch (error) {
    console.error("Chat API エラー:", error)

    return NextResponse.json(
      {
        error: "内部サーバーエラーが発生しました",
        details: error instanceof Error ? error.message : "不明なエラー",
      },
      { status: 500 },
    )
  }
}
