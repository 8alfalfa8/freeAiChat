# 🛠️freeAiChat

このリポジトリは、マルチLLM対応AIチャットAPIエンジンです。

---

## 「LangChain + Weaviate + 切り替え可能なLLM（OpenAI/Groq） + API呼び出し + 無料Embedding」(RAG)に基づくチャットアプリケーション構成設計と実装案

---

### システム構成図

```
[ユーザー画面] 
    │
    ▼
[FastAPIサービス]  ← 呼び出し → [LangChain RAG処理]
    │                          │
    ▼                          ▼
[WeaviateベクトルDB]      [LLMプロバイダー]
    ▲                     ├─ OpenAI
    │                     ├─ Groq
    │                     └─ その他LLM
    │
[無料Embeddingモデル]
```

---

### 📦 構成ファイル

```
freeAiChat
├─ LICENSE                             ← ライセンス
├─ README                              ← 説明
├─ requirements.txt                    ← 必須パッケージ一覧
├─ app.py                              ← コアサービス
├─ init_weaviate.py                    ← Weaviate初期化
└─ docker-compose.yml                  ← Weaviate docker
```

### コアコンポーネント実装

#### 1. 環境準備 (`requirements.txt`)

```python
langchain-core
langchain-community
langchain-openai
langchain-groq
langchain-weaviate
langchain-huggingface
weaviate-client>=4.0.0
sentence-transformers  # 無料のEmbeddingモデル
fastapi
uvicorn
python-dotenv
PyPDF2>=1.27.0
```

```bash
# 仮想環境の作成（任意）
python3 -m venv venv
source venv/bin/activate

# 必要なパッケージをインストール
pip install -r requirements.txt
```

#### 2. 環境設定 (`.env`)

```env
# LLM設定
OPENAI_API_KEY=your_openai_key
GROQ_API_KEY=your_groq_key
LLM_PROVIDER=groq  # 切り替え可能：openai または groq

# Weaviate設定
WEAVIATE_URL=http://localhost:8080
WEAVIATE_INDEX_NAME=knowledge_base
```

#### 3. コアサービス (`app.py`)

```python
app.py をご参照ください。
```

#### 4. Weaviate 初期化 (`init_weaviate.py`)

```python
init_weaviate.py をご参照ください。
```

---

### システム動作フロー

#### 1. **ナレッジベース構築**

* ユーザーが `/ingest` API を通じてテキストをアップロード
* 無料の `sentence-transformers` でEmbeddingを生成
* データは Weaviate ベクトルDBに保存

#### 2. **質問応答フロー**

```mermaid
graph TD
A[ユーザーの質問] --> B[FastAPI]
B --> C[LangChain RAGチェーン]
C --> D[Weaviateで検索]
D --> E[プロンプト構成]
E --> F{LLM選択}
F -->|OpenAI| G[ G: GPT-4]
F -->|Groq| H[ H: Llama3]
F -->|・・・| I[ ・・・: ・・・]
G/H/・・・ --> J[回答生成]
J --> K[ユーザーに返答]
```

#### 3. **LLM切り替え機構**

* 環境変数 `LLM_PROVIDER` による制御
* コードを変更せずにLLMを切り替え可能
* 実行中の動的切り替えにも対応

---

### デプロイと使用方法

#### 1. サービス起動

```bash
# Weaviate 起動(初回)
docker-compose up -d

初回以降
docker ps         #コンテナー一覧
docker stop       #コンテナー停止
docker start      #コンテナー開始

# Weaviateインデックスの初期化
python init_weaviate.py

# APIサービス起動
uvicorn app:app --reload
```

#### 2. ナレッジ追加API使用例

```bash
curl -X POST "http://localhost:8000/ingest" \
-H "Content-Type: application/json" \
-d '{"text": "LangChainは大規模言語モデルアプリケーションの開発用フレームワークです..."}'
```

```bash
curl -X POST "http://localhost:8000/ingest-pdfs" \
-H "Content-Type: application/json" \
-d '{"directory_path": "/pdf_path"}'
```

```bash
curl -X POST "http://localhost:8000/ingest-txts" \
-H "Content-Type: application/json" \
-d '{"directory_path": "/txt_path"}'
```

#### 3. 質問API使用例

```bash
curl -X POST "http://localhost:8000/ask" \
-H "Content-Type: application/json" \
-d '{"question": "LangChainとは何ですか？"}'
```
応答結果
```bash
curl -X POST "http://localhost:8000/ask" -H "Content-Type: application/json" -d '{"question": "LangChainとは何ですか？"}'
{"answer":"LangChainは大規模言語モデルアプリケーションの開発用フレームワークです。"}
```
---

### 特長とメリット

1. **コスト最適化**

   * 無料のオープンソースEmbeddingモデルを使用
   * 高性能かつ低コストなLLM（Groq vs OpenAI）を切り替え可能

2. **柔軟なアーキテクチャ**

   * 環境変数でLLMプロバイダーを簡単に切り替え可能
   * 他のLLM（Anthropicやローカルモデルなど）への拡張も対応

3. **プロダクション対応**

   * 標準的なAPIインターフェース
   * モジュール設計により拡張性確保
   * ベクトル検索と生成処理を分離

4. **高パフォーマンス**

   * Groqは超低遅延応答を提供（リアルタイムシナリオに最適）
   * Weaviateはベクトル検索のパフォーマンスを最適化

---

このソリューションは、コストと性能のバランスが求められるナレッジベース型QA（質問応答）アプリケーションに特に適しており、実運用において無料のEmbeddingモデルを活用しつつ、要件に応じてLLMプロバイダーを柔軟に選択できます。

## ⚠️ 自己責任に関する注意事項（Self Responsibility Disclaimer）

本ツール（Terraform Code Generator from Excel）は、ユーザーの利便性向上を目的として無償で提供されていますが、**ご利用に際してはすべて自己責任でお願いいたします。**

* 本ツールを利用して生成されたコードの**正確性・完全性・安全性**について、開発者および関連団体は一切の保証を致しません。
* ユーザーが本ツールを使用することによって生じた**いかなる損害・不具合・システム障害等に対しても、開発者および関連団体は責任を負いません**。
* 実際の運用環境に適用する際は、**必ずご自身の責任において十分な検証およびレビューを実施してください。**

## 🤝 商談歓迎

追加機能の開発、環境構築のご支援をご希望の方は、下記までご連絡ください。
```
Colorful株式会社

〒151-0051
東京都渋谷区千駄ヶ谷3-51-10
PORTAL POINT HARAJUKU 607
info@colorful-inc.jp
```
https://colorful-inc.jp/

## 📝 ライセンス

本リポジトリは [MIT ライセンス](./LICENSE) のもとで公開されています。


