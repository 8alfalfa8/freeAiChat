import { type NextRequest, NextResponse } from "next/server"

export async function POST(request: NextRequest) {
  try {
    const formData = await request.formData()
    const file = formData.get("file") as File
    const chunkSize = Number(formData.get("chunk_size")) || 1000
    const preprocess = formData.get("preprocess") === "true"

    if (!file) {
      return NextResponse.json(
        {
          success: false,
          message: "ファイルが選択されていません",
        },
        { status: 400 },
      )
    }

    // ファイルサイズチェック（10MB制限）
    if (file.size > 10 * 1024 * 1024) {
      return NextResponse.json(
        {
          success: false,
          message: "ファイルサイズが10MBを超えています",
        },
        { status: 400 },
      )
    }

    const startTime = Date.now()

    // FastAPIに送信するためのFormDataを作成
    const fastApiFormData = new FormData()
    fastApiFormData.append("file", file)
    fastApiFormData.append("chunk_size", chunkSize.toString())
    fastApiFormData.append("preprocess", preprocess.toString())

    // FastAPIエンドポイントに送信
    const fastApiUrl = process.env.FASTAPI_URL || "http://localhost:8000"
    const response = await fetch(`${fastApiUrl}/upload/`, {
      method: "POST",
      headers: {
        // ...(process.env.FASTAPI_API_KEY && {
        //  Authorization: `Bearer ${process.env.FASTAPI_API_KEY}`,
        //}),
      },
      body: fastApiFormData,
    })

    if (!response.ok) {
      throw new Error(`FastAPI エラー: ${response.status}`)
    }

    const result = await response.json()
    const processingTime = (Date.now() - startTime) / 1000

    return NextResponse.json({
      success: true,
      message: `ファイル「${file.name}」が正常に追加されました`,
      chunks: result.chunks,
      processing_time: processingTime,
    })
  } catch (error) {
    console.error("File ingest error:", error)

    return NextResponse.json(
      {
        success: false,
        message: "ファイルの処理中にエラーが発生しました",
        details: error instanceof Error ? error.message : "不明なエラー",
      },
      { status: 500 },
    )
  }
}
