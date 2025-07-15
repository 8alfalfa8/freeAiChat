"use client"

import { useState } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Label } from "@/components/ui/label"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Switch } from "@/components/ui/switch"
import { Progress } from "@/components/ui/progress"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Upload, Link, FileText, Loader2, CheckCircle, AlertCircle, Database, Settings } from "lucide-react"

interface IngestResponse {
  success: boolean
  message: string
  chunks?: number
  processing_time?: number
}

export default function AdminPage() {
  // テキストインジェスト用の状態
  const [textContent, setTextContent] = useState("")
  const [textLoading, setTextLoading] = useState(false)
  const [textResult, setTextResult] = useState<IngestResponse | null>(null)

  // URLインジェスト用の状態
  const [url, setUrl] = useState("")
  const [urlChunkSize, setUrlChunkSize] = useState(1000)
  const [urlPreprocess, setUrlPreprocess] = useState(true)
  const [urlLoading, setUrlLoading] = useState(false)
  const [urlResult, setUrlResult] = useState<IngestResponse | null>(null)

  // ファイルアップロード用の状態
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [fileChunkSize, setFileChunkSize] = useState(1000)
  const [filePreprocess, setFilePreprocess] = useState(true)
  const [fileLoading, setFileLoading] = useState(false)
  const [fileResult, setFileResult] = useState<IngestResponse | null>(null)
  const [uploadProgress, setUploadProgress] = useState(0)

  // テキストインジェスト
  const handleTextIngest = async () => {
    if (!textContent.trim()) return

    setTextLoading(true)
    setTextResult(null)

    try {
      const response = await fetch("/api/admin/ingest/text", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          text: textContent,
        }),
      })

      const result = await response.json()
      setTextResult(result)

      if (result.success) {
        setTextContent("")
      }
    } catch (error) {
      setTextResult({
        success: false,
        message: "テキストの処理中にエラーが発生しました",
      })
    } finally {
      setTextLoading(false)
    }
  }

  // URLインジェスト
  const handleUrlIngest = async () => {
    if (!url.trim()) return

    setUrlLoading(true)
    setUrlResult(null)

    try {
      const response = await fetch("/api/admin/ingest/url", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          url: url,
          chunk_size: urlChunkSize,
          preprocess: urlPreprocess,
        }),
      })

      const result = await response.json()
      setUrlResult(result)

      if (result.success) {
        setUrl("")
      }
    } catch (error) {
      setUrlResult({
        success: false,
        message: "URLの処理中にエラーが発生しました",
      })
    } finally {
      setUrlLoading(false)
    }
  }

  // ファイルアップロード
  const handleFileUpload = async () => {
    if (!selectedFile) return

    setFileLoading(true)
    setFileResult(null)
    setUploadProgress(0)

    try {
      const formData = new FormData()
      formData.append("file", selectedFile)
      formData.append("chunk_size", fileChunkSize.toString())
      formData.append("preprocess", filePreprocess.toString())

      const response = await fetch("/api/admin/ingest/file", {
        method: "POST",
        body: formData,
      })

      const result = await response.json()
      setFileResult(result)

      if (result.success) {
        setSelectedFile(null)
        setUploadProgress(100)
      }
    } catch (error) {
      setFileResult({
        success: false,
        message: "ファイルの処理中にエラーが発生しました",
      })
    } finally {
      setFileLoading(false)
    }
  }

  const ResultAlert = ({ result }: { result: IngestResponse | null }) => {
    if (!result) return null

    return (
      <Alert className={result.success ? "border-green-200 bg-green-50" : "border-red-200 bg-red-50"}>
        {result.success ? (
          <CheckCircle className="h-4 w-4 text-green-600" />
        ) : (
          <AlertCircle className="h-4 w-4 text-red-600" />
        )}
        <AlertDescription className={result.success ? "text-green-800" : "text-red-800"}>
          {result.message}
          {result.success && result.chunks && (
            <div className="mt-2 flex gap-4 text-sm">
              <Badge variant="secondary">チャンク数: {result.chunks}</Badge>
              {result.processing_time && (
                <Badge variant="secondary">処理時間: {result.processing_time.toFixed(2)}秒</Badge>
              )}
            </div>
          )}
        </AlertDescription>
      </Alert>
    )
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-blue-50 p-4">
      <div className="max-w-6xl mx-auto">
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900 mb-2 flex items-center gap-2">
            <Database className="w-8 h-8 text-blue-600" />
            知識ベース管理
          </h1>
          <p className="text-gray-600">テキスト、URL、ファイルから知識ベースにデータを追加できます</p>
        </div>

        <Tabs defaultValue="text" className="space-y-6">
          <TabsList className="grid w-full grid-cols-3">
            <TabsTrigger value="text" className="flex items-center gap-2">
              <FileText className="w-4 h-4" />
              テキスト
            </TabsTrigger>
            <TabsTrigger value="url" className="flex items-center gap-2">
              <Link className="w-4 h-4" />
              URL
            </TabsTrigger>
            <TabsTrigger value="file" className="flex items-center gap-2">
              <Upload className="w-4 h-4" />
              ファイル
            </TabsTrigger>
          </TabsList>

          {/* テキストインジェスト */}
          <TabsContent value="text">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <FileText className="w-5 h-5" />
                  テキストを追加
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div>
                  <Label htmlFor="text-content">テキスト内容</Label>
                  <Textarea
                    id="text-content"
                    placeholder="知識ベースに追加したいテキストを入力してください..."
                    value={textContent}
                    onChange={(e) => setTextContent(e.target.value)}
                    rows={8}
                    className="mt-2"
                  />
                  <p className="text-sm text-gray-500 mt-1">文字数: {textContent.length}</p>
                </div>

                <Button onClick={handleTextIngest} disabled={!textContent.trim() || textLoading} className="w-full">
                  {textLoading ? (
                    <>
                      <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                      処理中...
                    </>
                  ) : (
                    <>
                      <FileText className="w-4 h-4 mr-2" />
                      テキストを追加
                    </>
                  )}
                </Button>

                <ResultAlert result={textResult} />
              </CardContent>
            </Card>
          </TabsContent>

          {/* URLインジェスト */}
          <TabsContent value="url">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Link className="w-5 h-5" />
                  URLから追加
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div>
                  <Label htmlFor="url-input">URL</Label>
                  <Input
                    id="url-input"
                    type="url"
                    placeholder="https://example.com"
                    value={url}
                    onChange={(e) => setUrl(e.target.value)}
                    className="mt-2"
                  />
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <Label htmlFor="url-chunk-size">チャンクサイズ</Label>
                    <Input
                      id="url-chunk-size"
                      type="number"
                      min="100"
                      max="5000"
                      value={urlChunkSize}
                      onChange={(e) => setUrlChunkSize(Number(e.target.value))}
                      className="mt-2"
                    />
                  </div>

                  <div className="flex items-center space-x-2 mt-6">
                    <Switch id="url-preprocess" checked={urlPreprocess} onCheckedChange={setUrlPreprocess} />
                    <Label htmlFor="url-preprocess">前処理を実行</Label>
                  </div>
                </div>

                <Button onClick={handleUrlIngest} disabled={!url.trim() || urlLoading} className="w-full">
                  {urlLoading ? (
                    <>
                      <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                      処理中...
                    </>
                  ) : (
                    <>
                      <Link className="w-4 h-4 mr-2" />
                      URLから追加
                    </>
                  )}
                </Button>

                <ResultAlert result={urlResult} />
              </CardContent>
            </Card>
          </TabsContent>

          {/* ファイルアップロード */}
          <TabsContent value="file">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Upload className="w-5 h-5" />
                  ファイルをアップロード
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div>
                  <Label htmlFor="file-input">ファイル選択</Label>
                  <Input
                    id="file-input"
                    type="file"
                    accept=".txt,.pdf,.docx,.md"
                    onChange={(e) => setSelectedFile(e.target.files?.[0] || null)}
                    className="mt-2"
                  />
                  {selectedFile && (
                    <div className="mt-2 p-2 bg-gray-50 rounded text-sm">
                      <p>
                        <strong>ファイル名:</strong> {selectedFile.name}
                      </p>
                      <p>
                        <strong>サイズ:</strong> {(selectedFile.size / 1024).toFixed(2)} KB
                      </p>
                      <p>
                        <strong>タイプ:</strong> {selectedFile.type}
                      </p>
                    </div>
                  )}
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <Label htmlFor="file-chunk-size">チャンクサイズ</Label>
                    <Input
                      id="file-chunk-size"
                      type="number"
                      min="100"
                      max="5000"
                      value={fileChunkSize}
                      onChange={(e) => setFileChunkSize(Number(e.target.value))}
                      className="mt-2"
                    />
                  </div>

                  <div className="flex items-center space-x-2 mt-6">
                    <Switch id="file-preprocess" checked={filePreprocess} onCheckedChange={setFilePreprocess} />
                    <Label htmlFor="file-preprocess">前処理を実行</Label>
                  </div>
                </div>

                {fileLoading && uploadProgress > 0 && (
                  <div>
                    <Label>アップロード進捗</Label>
                    <Progress value={uploadProgress} className="mt-2" />
                  </div>
                )}

                <Button onClick={handleFileUpload} disabled={!selectedFile || fileLoading} className="w-full">
                  {fileLoading ? (
                    <>
                      <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                      アップロード中...
                    </>
                  ) : (
                    <>
                      <Upload className="w-4 h-4 mr-2" />
                      ファイルをアップロード
                    </>
                  )}
                </Button>

                <ResultAlert result={fileResult} />
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>

        {/* 設定情報 */}
        <Card className="mt-6">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Settings className="w-5 h-5" />
              設定情報
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
              <div className="p-3 bg-blue-50 rounded">
                <h4 className="font-semibold text-blue-900">対応ファイル形式</h4>
                <p className="text-blue-700 mt-1">TXT, PDF</p>
              </div>
              <div className="p-3 bg-green-50 rounded">
                <h4 className="font-semibold text-green-900">推奨チャンクサイズ</h4>
                <p className="text-green-700 mt-1">500-2000文字</p>
              </div>
              <div className="p-3 bg-purple-50 rounded">
                <h4 className="font-semibold text-purple-900">前処理機能</h4>
                <p className="text-purple-700 mt-1">テキスト正規化、重複除去</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
