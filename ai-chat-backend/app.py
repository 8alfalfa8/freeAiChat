# file: ai-chat-backend/app.py
"""
LLM活用チャットアプリケーション
FastAPIを使用して、RAG（Retrieval-Augmented Generation）を実現
WeaviateやHuggingFace/Groq/OpenAIのLLMを利用
PDF/TXTファイルのテキスト抽出、URLからの情報取得も含む
"""

###########################################################
# ライブラリインポート
###########################################################
# 標準ライブラリ
import os
import re
import shutil
import unicodedata
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse

# サードパーティライブラリ
import requests
import weaviate
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from pypdf import PdfReader
from pydantic import BaseModel
from weaviate.embedded import EmbeddedOptions

# LangChain関連
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from langchain_groq import ChatGroq
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_openai import ChatOpenAI
from langchain_weaviate import WeaviateVectorStore


# 環境変数の読み込み
load_dotenv()

# FastAPIアプリの初期化
app = FastAPI(
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    swagger_ui_parameters={"cache_control": "no-store"},
)


####################################
# リクエストモデルの定義
####################################

class QueryRequest(BaseModel):
    """RAG質問リクエスト"""
    question: str


class IngestRequest(BaseModel):
    """テキスト直接保存リクエスト"""
    text: str


class UrlIngestRequest(BaseModel):
    """URLからコンテンツを取得して保存するリクエスト"""
    url: str
    chunk_size: int = 1000
    preprocess: bool = True


class FileIngestRequest(BaseModel):
    """ファイル処理内部用リクエストモデル"""
    directory_path: str
    chunk_size: int
    preprocess: bool


####################################
# 埋め込みモデルとベクトルストアの設定
####################################

# 埋め込みモデルの初期化
embeddings = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2"
)

# Weaviateクライアントの初期化
try:
    weaviate_url = os.getenv("WEAVIATE_URL", "http://localhost:8080")

    # URLからホストとポートを抽出
    if weaviate_url.startswith("http://"):
        http_host = weaviate_url[7:]
        http_secure = False
    elif weaviate_url.startswith("https://"):
        http_host = weaviate_url[8:]
        http_secure = True
    else:
        http_host = weaviate_url
        http_secure = False

    if ":" in http_host:
        http_host, http_port = http_host.split(":")
        http_port = int(http_port)
    else:
        http_port = 443 if http_secure else 80

    client = weaviate.connect_to_local(
        host=http_host,
        port=http_port,
        grpc_port=50051
    )
    print("既存のWeaviateインスタンスに接続しました")
except Exception as e:
    print(f"既存インスタンスへの接続に失敗しました: {e}")
    try:
        client = weaviate.WeaviateClient(
            embedded_options=EmbeddedOptions(
                hostname="localhost",
                port=8090,
                grpc_port=50052,
                persistence_data_path="./weaviate_data"
            )
        )
        print("Weaviateを組み込みモードで起動しました（ポート8090）")
    except Exception as e:
        print(f"組み込みモードの初期化にも失敗しました: {e}")
        raise RuntimeError("Weaviateの初期化に完全に失敗しました")

# ベクトルストアの初期化
vector_store = WeaviateVectorStore(
    client=client,
    index_name=os.getenv("WEAVIATE_INDEX_NAME", "DefaultIndex"),
    text_key="text",
    embedding=embeddings
)


####################################
# LLMプロバイダーの設定
####################################

def get_llm():
    """
    環境変数 LLM_PROVIDER に基づいてLLMインスタンスを返す。
    毎回新規インスタンスを生成する（環境変数変更を反映させるため）。
    本番運用時は functools.lru_cache 等でのキャッシュを検討。
    """
    provider = os.getenv("LLM_PROVIDER", "groq")

    if provider == "openai":
        return ChatOpenAI(
            model="gpt-4-turbo",
            temperature=0.5,
            api_key=os.getenv("OPENAI_API_KEY")
        )
    elif provider == "groq":
        return ChatGroq(
            model="llama3-70b-8192",
            temperature=0.5,
            api_key=os.getenv("GROQ_API_KEY")
        )
    else:
        raise ValueError(f"サポートされていないLLMプロバイダー: {provider}")


####################################
# テキスト処理ユーティリティ
####################################

def detect_language(text: str) -> str:
    """
    テキストの言語を簡易検出。
    日本語文字（ひらがな・カタカナ・漢字）が含まれれば 'ja'、
    それ以外は 'en' と仮定する。
    """
    if re.search(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]', text):
        return 'ja'
    return 'en'


def get_prompt_template(language: str) -> str:
    """言語に応じたRAGプロンプトテンプレートを返す"""
    templates = {
        'ja': """以下の文脈に基づいて質問に日本語で答えてください:
{context}

質問: {question}

回答は日本語で、明確かつ簡潔にお願いします。""",
        'en': """Answer the question based on the following context:
{context}

Question: {question}

Please provide a clear and concise answer in English."""
    }
    return templates.get(language, templates['en'])


def preprocess_text_txt(text: str) -> str:
    """TXT用テキスト前処理。不要な空白・改行を正規化"""
    text = re.sub(r'\s+', ' ', text).strip()
    text = ''.join(char for char in text if char.isprintable() or char.isspace())
    return text


def preprocess_text_pdf(text: str) -> str:
    """PDF用テキスト前処理。全角半角統一と空白正規化"""
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r'\s+', ' ', text)
    # 文末後にスペースがない場合に追加（文の区切りを明確化）
    text = re.sub(r'([。．.!?])([^\s])', r'\1 \2', text)
    text = text.strip()
    return text


def split_into_sentences(text: str) -> List[str]:
    """
    テキストを文単位に分割（日本語・英語対応）。
    日本語の句点・英語のピリオド等を区切りとして使用。
    """
    # 日本語の文分割
    ja_sentences = re.split(r'([。．！？!?]+\s*)', text)
    ja_sentences = [
        ja_sentences[i] + (ja_sentences[i + 1] if i + 1 < len(ja_sentences) else '')
        for i in range(0, len(ja_sentences) - 1, 2)
    ]

    # 英語の文分割
    final_sentences = []
    for sentence in ja_sentences:
        en_sentences = re.split(r'([.!?]+\s*)', sentence)
        en_sentences = [
            en_sentences[i] + (en_sentences[i + 1] if i + 1 < len(en_sentences) else '')
            for i in range(0, len(en_sentences) - 1, 2)
        ]
        final_sentences.extend(en_sentences)

    return [s.strip() for s in final_sentences if s.strip()]


#####################################
# チャンキング処理
#####################################

def split_into_chunks_pdf(text: str, chunk_size: int, overlap: int = 100) -> List[str]:
    """
    PDFテキストを文単位で分割し、適切なチャンクサイズに調整。
    隣接チャンク間のオーバーラップ部分も追加して文脈の連続性を保つ。
    """
    sentences = split_into_sentences(text)
    chunks = []
    current_chunk = ""

    for sentence in sentences:
        if len(current_chunk) + len(sentence) <= chunk_size:
            current_chunk += sentence + " "
        else:
            if current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = sentence + " "
            else:
                # 1文がchunk_sizeを超える場合は強制分割
                for i in range(0, len(sentence), chunk_size):
                    chunks.append(sentence[i:i + chunk_size].strip())

    if current_chunk:
        chunks.append(current_chunk.strip())

    # オーバーラップチャンクの生成（隣接チャンク間の重複部分）
    if len(chunks) > 1 and overlap > 0:
        overlapped_chunks = []
        for i in range(len(chunks) - 1):
            overlap_text = chunks[i][max(0, len(chunks[i]) - overlap):]
            next_overlap = chunks[i + 1][:overlap]
            overlapped_chunks.append(f"{overlap_text} {next_overlap}".strip())
        chunks.extend(overlapped_chunks)

    # 重複除去
    seen = set()
    unique_chunks = []
    for chunk in chunks:
        if chunk not in seen:
            seen.add(chunk)
            unique_chunks.append(chunk)

    return unique_chunks


def split_into_chunks_txt(text: str, chunk_size: int, overlap: int = 100) -> List[str]:
    """TXTテキストをスライディングウィンドウでチャンク分割"""
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start = end - overlap
    return chunks


#####################################
# ファイル処理ユーティリティ
#####################################

def extract_text_from_txt(txt_path: str) -> str:
    """TXTファイルからテキストを抽出（UTF-8 / Shift_JIS対応）"""
    encodings = ['utf-8', 'shift_jis']
    for encoding in encodings:
        try:
            with open(txt_path, 'r', encoding=encoding) as f:
                text = f.read()
                if not text:
                    print(f"警告: ファイル {txt_path} は空です")
                return text
        except UnicodeDecodeError:
            continue
        except Exception as e:
            print(f"TXTファイル {txt_path} の読み込みに失敗しました: {e}")
            return ""
    print(f"TXTファイル {txt_path} を読み込めるエンコーディングが見つかりませんでした")
    return ""


def extract_text_from_pdf(pdf_path: str) -> str:
    """PDFファイルからテキストを抽出"""
    try:
        reader = PdfReader(pdf_path)
        text = ""
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
        return text
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDFの読み込みに失敗しました: {e}")


#####################################
# ディレクトリ処理関数
#####################################

def process_pdf_directory(directory_path: str, chunk_size: int, preprocess: bool) -> List[str]:
    """指定ディレクトリ内の全PDFを処理してチャンクリストを返す"""
    path = Path(directory_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="指定されたディレクトリが見つかりません")

    pdf_files = list(path.glob("*.pdf"))
    if not pdf_files:
        raise HTTPException(status_code=404, detail="PDFファイルが見つかりません")

    pdf_chunks = []
    for pdf_file in pdf_files:
        try:
            text = extract_text_from_pdf(str(pdf_file))
            if not text.strip():
                print(f"警告: ファイル {pdf_file.name} からテキストを抽出できませんでした")
                continue

            if preprocess:
                text = preprocess_text_pdf(text)

            chunks = split_into_chunks_pdf(text, chunk_size)
            if chunks:
                pdf_chunks.extend(chunks)
            else:
                print(f"警告: ファイル {pdf_file.name} から有効なチャンクを生成できませんでした")
        except Exception as e:
            print(f"ファイル {pdf_file.name} の処理中にエラーが発生しました: {e}")
            continue

    if not pdf_chunks:
        raise HTTPException(status_code=500, detail="有効なテキストチャンクを生成できませんでした")

    return pdf_chunks


def process_txt_directory(directory_path: str, chunk_size: int, preprocess: bool) -> List[str]:
    """指定ディレクトリ内の全TXTを処理してチャンクリストを返す"""
    path = Path(directory_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="指定されたディレクトリが見つかりません")

    txt_files = list(path.glob("*.txt"))
    if not txt_files:
        raise HTTPException(status_code=404, detail="TXTファイルが見つかりません")

    txt_chunks = []
    for txt_file in txt_files:
        try:
            text = extract_text_from_txt(str(txt_file))
            if not text:
                continue

            if preprocess:
                text = preprocess_text_txt(text)

            chunks = split_into_chunks_txt(text, chunk_size)
            if chunks:
                txt_chunks.extend(chunks)
        except Exception as e:
            print(f"ファイル {txt_file.name} の処理中にエラーが発生しました: {e}")
            continue

    if not txt_chunks:
        raise HTTPException(status_code=500, detail="有効なテキストを抽出できませんでした")

    return txt_chunks


######################################
# RAGチェーン設定
######################################

# リトリーバーの設定（上位3件を取得）
retriever = vector_store.as_retriever(search_kwargs={"k": 3})


def get_rag_chain(question: str):
    """
    質問の言語を検出し、言語に応じたプロンプトでRAGチェーンを構築。
    /ask エンドポイントから呼び出される。
    """
    language = detect_language(question)
    template = get_prompt_template(language)
    prompt = ChatPromptTemplate.from_template(template)

    return (
        {"context": retriever, "question": RunnablePassthrough()}
        | prompt
        | get_llm()
        | StrOutputParser()
    )


##########################################
# APIエンドポイント
##########################################

@app.post("/ask")
async def ask_question(request: QueryRequest):
    """RAGを使って質問に回答する"""
    try:
        rag_chain = get_rag_chain(request.question)
        response = rag_chain.invoke(request.question)
        return {"answer": response}
    except Exception as e:
        return {"error": str(e)}


@app.post("/ingest")
async def ingest_documents(request: IngestRequest):
    """テキストを直接知識ベースに保存"""
    try:
        vector_store.add_texts([request.text])
        return {"status": "success", "message": "ドキュメントが知識ベースに保存されました"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


##########################################
# ファイルアップロードエンドポイント
##########################################

# アップロード先ディレクトリ設定
uploaded_files_dir = os.getenv("UPLOADED_FILES_DIR", "./doc")
PDF_DIR = os.path.join(uploaded_files_dir, "pdfs")
TXT_DIR = os.path.join(uploaded_files_dir, "txts")

os.makedirs(PDF_DIR, exist_ok=True)
os.makedirs(TXT_DIR, exist_ok=True)

EXTENSION_MAP = {
    ".pdf": PDF_DIR,
    ".txt": TXT_DIR
}


@app.post("/upload/")
async def upload_file(
    file: UploadFile = File(...),
    chunk_size: int = Form(default=1024),
    preprocess: bool = Form(default=True)
):
    """
    ファイルをアップロードして知識ベースに保存。
    PDF/TXTのみ対応。アップロード後に自動でインジェスト処理を実行。
    """
    filename = os.path.basename(file.filename)
    ext = os.path.splitext(filename)[1].lower()

    if ext not in EXTENSION_MAP:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {ext}. Only PDF and TXT are allowed."
        )

    save_dir = EXTENSION_MAP[ext]
    file_path = os.path.join(save_dir, filename)

    # ファイル保存（上書き）
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # インジェスト処理の実行
    request_obj = FileIngestRequest(
        directory_path=save_dir,
        chunk_size=chunk_size,
        preprocess=preprocess
    )

    if ext == ".pdf":
        ingest_result = ingest_pdfs_from_directory(request_obj)
    else:
        ingest_result = ingest_txts_from_directory(request_obj)

    return {
        "message": f"File uploaded successfully, {ingest_result['message']}",
        "filename": filename,
        "ingest_result": ingest_result
    }


def ingest_pdfs_from_directory(request: FileIngestRequest):
    """PDFディレクトリの内容を処理してベクトルストアに保存"""
    chunks = process_pdf_directory(
        request.directory_path,
        request.chunk_size,
        request.preprocess
    )

    batch_size = min(50, max(10, len(chunks) // 10))
    successful_chunks = 0

    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i + batch_size]
        try:
            vector_store.add_texts(batch)
            successful_chunks += len(batch)
        except Exception as e:
            print(f"バッチ {i // batch_size + 1} の保存中にエラーが発生しました: {e}")
            # 個別リトライ
            for chunk in batch:
                try:
                    vector_store.add_texts([chunk])
                    successful_chunks += 1
                except Exception as e:
                    print(f"チャンクの保存に失敗しました: {e}")

    return {
        "status": "success" if successful_chunks > 0 else "partial",
        "message": f"{successful_chunks}/{len(chunks)}個のチャンクを保存しました",
        "details": {
            "chunk_size": request.chunk_size,
            "preprocessing": request.preprocess,
            "source_directory": request.directory_path
        }
    }


def ingest_txts_from_directory(request: FileIngestRequest):
    """TXTディレクトリの内容を処理してベクトルストアに保存"""
    chunks = process_txt_directory(
        request.directory_path,
        request.chunk_size,
        request.preprocess
    )

    batch_size = 50
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i + batch_size]
        vector_store.add_texts(batch)

    print(f"保存成功: {len(chunks)} チャンク")
    return {
        "status": "success",
        "message": f"{len(chunks)}個のチャンクを保存しました",
        "details": {
            "chunk_size": request.chunk_size,
            "preprocessing": request.preprocess,
            "source_directory": request.directory_path
        }
    }


####################################
# URL処理ユーティリティ
####################################

def is_valid_url(url: str) -> bool:
    """URLが有効かどうかを検証"""
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False


def fetch_url_content(url: str) -> Optional[str]:
    """URLからテキストコンテンツを取得。HTMLはBeautifulSoupで抽出"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        content_type = response.headers.get('Content-Type', '')
        if 'text/html' in content_type:
            soup = BeautifulSoup(response.text, 'html.parser')
            # 不要な要素を除去
            for element in soup(['script', 'style', 'nav', 'footer', 'iframe', 'noscript']):
                element.decompose()

            main_content = soup.find('main') or soup.find('article') or soup.body
            text = main_content.get_text(separator='\n', strip=True) if main_content else soup.get_text()
            return text
        else:
            return response.text
    except Exception as e:
        print(f"URLからのコンテンツ取得に失敗しました: {e}")
        return None


def process_url_content(content: str, chunk_size: int, preprocess: bool) -> List[str]:
    """URLコンテンツを前処理してチャンク分割"""
    if not content:
        return []

    if preprocess:
        content = preprocess_text_txt(content)

    return split_into_chunks_txt(content, chunk_size)


##########################################
# URL情報保存エンドポイント
##########################################

@app.post("/ingest-url")
async def ingest_from_url(request: UrlIngestRequest):
    """
    URLの内容を知識ベースに保存。
    HTMLページの場合は主要コンテンツを抽出して保存。
    """
    if not is_valid_url(request.url):
        raise HTTPException(status_code=400, detail="無効なURL形式です")

    content = fetch_url_content(request.url)
    if not content:
        raise HTTPException(status_code=400, detail="URLからコンテンツを取得できませんでした")

    chunks = process_url_content(content, request.chunk_size, request.preprocess)
    if not chunks:
        raise HTTPException(status_code=400, detail="有効なチャンクを生成できませんでした")

    batch_size = min(50, max(10, len(chunks) // 10))
    successful_chunks = 0

    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i + batch_size]
        try:
            print(f"バッチ {i // batch_size + 1} を保存中: {len(batch)} チャンク")
            vector_store.add_texts(batch)
            successful_chunks += len(batch)
        except Exception as e:
            print(f"バッチ {i // batch_size + 1} の保存中にエラーが発生しました: {e}")
            for chunk in batch:
                try:
                    vector_store.add_texts([chunk])
                    successful_chunks += 1
                except Exception as e:
                    print(f"チャンクの保存に失敗しました: {e}")

    return {
        "status": "success" if successful_chunks > 0 else "partial",
        "message": f"{successful_chunks}/{len(chunks)}個のチャンクを保存しました",
        "details": {
            "url": request.url,
            "chunk_size": request.chunk_size,
            "preprocessing": request.preprocess,
            "content_length": len(content)
        }
    }


##########################################
# シャットダウン処理
##########################################

@app.on_event("shutdown")
async def shutdown_event():
    """アプリケーション終了時にWeaviateクライアントを閉じる"""
    client.close()
    print("Weaviateクライアントを閉じました")


##########################################
# アプリケーション起動
##########################################

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
