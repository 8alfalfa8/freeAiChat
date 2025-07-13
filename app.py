
###########################################################
# LLM活用チャットアプリケーション
# FastAPIを使用して、RAG（Retrieval-Augmented Generation）を実現
# WeaviateやHuggingFaceGroqまたはOpenAIのLLMを利用
# このコードは、PDFファイルのテキスト抽出機能も含む
###########################################################
# ライブラリインポート
import os
import re
from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_weaviate import WeaviateVectorStore
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI
import weaviate
from weaviate.embedded import EmbeddedOptions
from pypdf import PdfReader
from pathlib import Path
import unicodedata
import shutil

import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from typing import Union

# 環境変数の読み込み
load_dotenv()

# FastAPIアプリの初期化
app = FastAPI(
    # 開発時にこれらの設定を追加
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    # キャッシュを無効化
    swagger_ui_parameters={"cache_control": "no-store"},
)

####################################
# リクエストモデルの定義
# クエリリクエストモデル
####################################
class QueryRequest(BaseModel):
    question: str

# インジェストリクエストモデル
# テキストを知識ベースに保存するためのリクエストモデル
class IngestRequest(BaseModel):
    text: str

# URLインジェストリクエストモデル
# URLからテキストを抽出して知識ベースに保存するためのリクエストモデル
class UrlIngestRequest(BaseModel):
    url: str
    chunk_size: int = 1000
    preprocess: bool = True

# アップロードファイルリクエストモデル
# ファイルアップロードのためのリクエストモデル
class UploadFileRequest(BaseModel):
    file: UploadFile = File(...)
    chunk_size: int = 1000
    preprocess: bool = True

####################################
# 埋め込みモデルとベクトルストアの設定
####################################

# 埋め込みモデルの初期化
# 最新のHuggingFaceEmbeddingsを使用
embeddings = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2"
)

# Weaviateクライアントの初期化
try:
    weaviate_url = os.getenv("WEAVIATE_URL", "http://localhost:8080")
    
    # Parse URL
    if weaviate_url.startswith("http://"):
        http_host = weaviate_url[7:]
        http_secure = False
    elif weaviate_url.startswith("https://"):
        http_host = weaviate_url[8:]
        http_secure = True
    else:
        http_host = weaviate_url
        http_secure = False
    
    # Split host and port
    if ":" in http_host:
        http_host, http_port = http_host.split(":")
        http_port = int(http_port)
    else:
        http_port = 80 if not http_secure else 443

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
# 最新のWeaviateVectorStoreを使用
vector_store = WeaviateVectorStore(
    client=client,
    index_name=os.getenv("WEAVIATE_INDEX_NAME", "DefaultIndex"),
    text_key="text",
    embedding=embeddings
)

####################################
# LLMプロバイダーの設定
####################################

# LLMプロバイダーの選択
def get_llm():
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
# 言語検出用の関数を追加
def detect_language(text: str) -> str:
    """テキストの言語を簡単に検出"""
    # 日本語の文字が含まれているか
    if re.search(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]', text):
        return 'ja'
    # 英語と仮定（簡易的な実装）
    return 'en'

# 多言語対応のプロンプトテンプレート
def get_prompt_template(language: str) -> str:
    """言語に応じたプロンプトテンプレートを返す"""
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
    return templates.get(language, templates['en'])  # デフォルトは英語

def preprocess_text_txt(text: str) -> str:
    """テキストの前処理を行う"""
    # 不要な空白、改行、特殊文字を削除
    text = re.sub(r'\s+', ' ', text).strip()
    # ASCII以外の文字も保持（日本語対応）
    text = ''.join(char for char in text if char.isprintable() or char.isspace())
    return text
    
def preprocess_text_pdf(text: str) -> str:
    """テキストの前処理を強化"""
    # 全角・半角統一と不要な文字の除去
    text = unicodedata.normalize("NFKC", text)
    
    # 特殊文字と不要な空白を除去 (日本語の句読点や記号は保持)
     #text = re.sub(r'[^\w\s\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF、。・「」『』【】～]', ' ', text)
    
    # URLとメールアドレスの除去
    #text = re.sub(r'https?://\S+|www\.\S+', '', text)
    #text = re.sub(r'\S+@\S+', '', text)
    
    # 連続する空白、改行、タブを単一スペースに
    text = re.sub(r'\s+', ' ', text)
    
    # 文の区切りを考慮した前処理
    text = re.sub(r'([。．.!?])([^\s])', r'\1 \2', text)  # 文末後にスペースがない場合に追加
    
    # 前後の空白を削除
    text = text.strip()
    
    return text

def split_into_sentences(text: str) -> List[str]:
    """テキストを文単位に分割（日本語と英語に対応）"""
    # 日本語の文分割（句点、読点、感嘆符、疑問符で分割）
    ja_sentences = re.split(r'([。．！？!?]+\s*)', text)
    ja_sentences = [ja_sentences[i] + (ja_sentences[i+1] if i+1 < len(ja_sentences) else '') 
                   for i in range(0, len(ja_sentences)-1, 2)]
    
    # 英語の文分割（ピリオド、感嘆符、疑問符で分割）
    final_sentences = []
    for sentence in ja_sentences:
        en_sentences = re.split(r'([.!?]+\s*)', sentence)
        en_sentences = [en_sentences[i] + (en_sentences[i+1] if i+1 < len(en_sentences) else '') 
                      for i in range(0, len(en_sentences)-1, 2)]
        final_sentences.extend(en_sentences)
    
    # 空の文を除去
    final_sentences = [s.strip() for s in final_sentences if s.strip()]
    return final_sentences

#####################################
# チャンキング処理
#####################################
def split_into_chunks_pdf(text: str, chunk_size: int, overlap: int = 100) -> List[str]:
    """テキストを文単位で分割し、適切なチャンクサイズに調整"""
    sentences = split_into_sentences(text)
    chunks = []
    current_chunk = ""
    
    for sentence in sentences:
        # 現在のチャンクに文を追加した場合の長さをチェック
        if len(current_chunk) + len(sentence) <= chunk_size:
            current_chunk += sentence + " "
        else:
            if current_chunk:  # 現在のチャンクが空でない場合のみ追加
                chunks.append(current_chunk.strip())
                current_chunk = sentence + " "
            else:  # 1文がチャンクサイズを超える場合
                # 長い文を強制的に分割
                for i in range(0, len(sentence), chunk_size):
                    chunk_part = sentence[i:i+chunk_size]
                    chunks.append(chunk_part.strip())
    
    # 最後のチャンクを追加
    if current_chunk:
        chunks.append(current_chunk.strip())
    
    # オーバーラップを考慮してチャンクを調整
    if len(chunks) > 1 and overlap > 0:
        overlapped_chunks = []
        for i in range(len(chunks)-1):
            current = chunks[i]
            next_part = chunks[i+1]
            
            # 現在のチャンクの末尾からオーバーラップ分を取得
            overlap_start = max(0, len(current) - overlap)
            overlap_text = current[overlap_start:]
            
            # 次のチャンクの先頭からオーバーラップ分を取得
            next_overlap_text = next_part[:overlap]
            
            # オーバーラップチャンクを作成（重複部分を自然な形で結合）
            overlapped = f"{overlap_text} {next_overlap_text}".strip()
            overlapped_chunks.append(overlapped)
        
        chunks.extend(overlapped_chunks)
    
    # 重複するチャンクを除去
    unique_chunks = []
    seen_chunks = set()
    for chunk in chunks:
        if chunk not in seen_chunks:
            seen_chunks.add(chunk)
            unique_chunks.append(chunk)
    
    return unique_chunks

def split_into_chunks_txt(text: str, chunk_size: int, overlap: int = 100) -> List[str]:
    """テキストをオーバーラップのあるチャンクに分割"""
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start = end - overlap  # オーバーラップ分戻る
    return chunks

#####################################
# ファイル処理ユーティリティ
#####################################
def extract_text_from_txt(txt_path: str) -> str:
    """TXTファイルからテキストを抽出する"""
    try:
        with open(txt_path, 'r', encoding='utf-8') as f:
            text = f.read()
            if not text:  # 空ファイルチェック
                print(f"警告: ファイル {txt_path} は空です")
                return ""
            return text
    except UnicodeDecodeError:
        # UTF-8で読み込めない場合、他のエンコーディングを試す
        try:
            with open(txt_path, 'r', encoding='shift_jis') as f:
                text = f.read()
                if not text:
                    print(f"警告: ファイル {txt_path} は空です")
                    return ""
                return text
        except Exception as e:
            print(f"TXTファイル {txt_path} の読み込みに失敗しました: {str(e)}")
            return ""
    except Exception as e:
        print(f"TXTファイル {txt_path} の読み込みに失敗しました: {str(e)}")
        return ""

def extract_text_from_pdf(pdf_path: str) -> str:
    try:
        reader = PdfReader(pdf_path)
        text = ""
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
        return text
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDFの読み込みに失敗しました: {str(e)}")

#####################################
# ディレクトリ処理関数
#####################################
def process_pdf_directory(directory_path: str, chunk_size: int, preprocess: bool) -> List[str]:
    pdf_chunks = []
    try:
        path = Path(directory_path)
        if not path.exists():
            raise HTTPException(status_code=404, detail="指定されたディレクトリが見つかりません")
        
        pdf_files = list(path.glob("*.pdf"))
        if not pdf_files:
            raise HTTPException(status_code=404, detail="PDFファイルが見つかりません")
        
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
                print(f"ファイル {pdf_file.name} の処理中にエラーが発生しました: {str(e)}")
                continue
        
        if not pdf_chunks:
            raise HTTPException(status_code=500, detail="有効なテキストチャンクを生成できませんでした")
        
        return pdf_chunks
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def process_txt_directory(directory_path: str, chunk_size: int, preprocess: bool) -> List[str]:
    """指定されたディレクトリ内のすべてのTXTファイルを処理してチャンクに分割"""
    txt_chunks = []
    try:
        path = Path(directory_path)
        if not path.exists():
            raise HTTPException(status_code=404, detail="指定されたディレクトリが見つかりません")
        
        txt_files = list(path.glob("*.txt"))
        if not txt_files:
            raise HTTPException(status_code=404, detail="TXTファイルが見つかりません")
        
        for txt_file in txt_files:
            try:
                text = extract_text_from_txt(str(txt_file))
                if not text:  # 空のテキストはスキップ
                    continue
                    
                if preprocess:
                    text = preprocess_text_txt(text)
                
                chunks = split_into_chunks_txt(text, chunk_size)
                if chunks:
                    txt_chunks.extend(chunks)
            except Exception as e:
                print(f"ファイル {txt_file.name} の処理中にエラーが発生しました: {str(e)}")
                continue
        
        if not txt_chunks:
            raise HTTPException(status_code=500, detail="有効なテキストを抽出できませんでした")
        
        return txt_chunks
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

######################################
# RAGチェーン設定
######################################
# リトリーバーの設定
retriever = vector_store.as_retriever(search_kwargs={"k": 3})

# RAGチェーンの構築を修正
def get_rag_chain(question: str):
    """質問の言語に基づいてRAGチェーンを構築"""
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
# /askエンドポイントを修正
@app.post("/ask")
async def ask_question(request: QueryRequest):
    try:
        rag_chain = get_rag_chain(request.question)  # 言語に応じたチェーンを取得
        response = rag_chain.invoke(request.question)
        return {"answer": response}
    except Exception as e:
        return {"error": str(e)}

@app.post("/ingest")
async def ingest_documents(request: IngestRequest):
    """テキストを知識ベースに保存"""
    try:
        vector_store.add_texts([request.text])
        return {"status": "success", "message": "ドキュメントが知識ベースに保存されました"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

##########################################
# ファイルアップロードエンドポイント
##########################################
# アップロードされたファイルの保存ディレクトリ
uploaded_files_dir=os.getenv("UPLOADED_FILES_DIR", "./doc/")
# アップロードされたPDFとTXTファイルのディレクトリ
PDF_DIR = f"{uploaded_files_dir}/pdfs"
TXT_DIR = f"{uploaded_files_dir}/txts"

# ディレクトリ作成
os.makedirs(PDF_DIR, exist_ok=True)
os.makedirs(TXT_DIR, exist_ok=True)

# 拡張子と保存先のマッピング
EXTENSION_MAP = {
    ".pdf": PDF_DIR,
    ".txt": TXT_DIR
}

class FileIngestRequest(BaseModel):
    directory_path: str
    chunk_size: int
    preprocess: bool

@app.post("/upload/")
async def upload_file(
    file: UploadFile = File(...),
    chunk_size: int = Form(default=1024),
    preprocess: bool = Form(default=True)
):
    """
    ファイルをアップロードして保存
    - file: アップロードするファイル
    - chunk_size: チャンクサイズ (デフォルト: 1000)
    - preprocess: 前処理を行うか (デフォルト: True)
    """    
    filename = os.path.basename(file.filename)
    ext = os.path.splitext(filename)[1].lower()  # .pdf or .txt
    request = FileIngestRequest(
        directory_path=PDF_DIR if ext == ".pdf" else TXT_DIR,
        chunk_size=chunk_size, 
        preprocess=preprocess
    )

    # 許可された拡張子かチェック
    if ext not in EXTENSION_MAP:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {ext}. Only PDF and TXT are allowed."
        )

    # 保存パスの生成
    save_dir = EXTENSION_MAP[ext]
    file_path = os.path.join(save_dir, filename)

    # 保存処理（上書き）
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    if ext == ".pdf":
        ingest_result = ingest_pdfs_from_directory(request)
    else:
        ingest_result = ingest_txts_from_directory(request)

    return {"message": f"File uploaded successfully, {ingest_result['message']}", 
    "filename": filename,
    "ingest_result": ingest_result}


def ingest_pdfs_from_directory(request: FileIngestRequest):
    try:
        chunks = process_pdf_directory(
            request.directory_path,
            request.chunk_size,
            request.preprocess
        )

        # バッチ処理のサイズを動的に調整
        batch_size = min(50, max(10, len(chunks) // 10))
        successful_chunks = 0
        
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i + batch_size]
            try:
                vector_store.add_texts(batch)
                successful_chunks += len(batch)
            except Exception as e:
                print(f"バッチ {i//batch_size + 1} の保存中にエラーが発生しました: {str(e)}")
                # 失敗した場合は個別に試す
                for chunk in batch:
                    try:
                        vector_store.add_texts([chunk])
                        successful_chunks += 1
                    except Exception as e:
                        print(f"チャンクの保存に失敗しました: {str(e)}")
                        continue

        return {
            "status": "success" if successful_chunks > 0 else "partial",
            "message": f"{successful_chunks}/{len(chunks)}個のチャンクを保存しました",
            "details": {
                "chunk_size": request.chunk_size,
                "preprocessing": request.preprocess,
                "source_directory": PDF_DIR
            }
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def ingest_txts_from_directory(request: FileIngestRequest):
    """TXTディレクトリの内容を処理して保存"""
    try:
        chunks = process_txt_directory(
            request.directory_path,
            request.chunk_size,
            request.preprocess
        )

        # チャンクをバッチ処理で保存
        batch_size = 50
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i + batch_size]
            vector_store.add_texts(batch)
        
        print(f"保存成功: {len(chunks)} チャンク");
        return {
            "status": "success",
            "message": f"{len(chunks)}個のチャンクを保存しました",
            "details": {
                "chunk_size": request.chunk_size,
                "preprocessing": request.preprocess,
                "source_directory": TXT_DIR
            }
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

template = """以下の文脈に基づいて質問に答えてください:
{context}

質問: {question}
"""
prompt = ChatPromptTemplate.from_template(template)

rag_chain = (
    {"context": retriever, "question": RunnablePassthrough()}
    | prompt
    | get_llm()
    | StrOutputParser()
)

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

def fetch_url_content(url: str) -> Union[str, None]:
    """URLからテキストコンテンツを取得"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        # HTMLの場合はBeautifulSoupでテキストを抽出
        if 'text/html' in response.headers.get('Content-Type', ''):
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 不要な要素を削除
            for element in soup(['script', 'style', 'nav', 'footer', 'iframe', 'noscript']):
                element.decompose()
                
            # メインコンテンツを優先的に取得
            main_content = soup.find('main') or soup.find('article') or soup.body
            text = main_content.get_text(separator='\n', strip=True) if main_content else soup.get_text()
            print("text:", text[:100])  # 最初の100文字を表示
            return text
        else:
            # プレーンテキストやその他のコンテンツ
            return response.text
    except Exception as e:
        print(f"URLからのコンテンツ取得に失敗しました: {str(e)}")
        return None

def process_url_content(content: str, chunk_size: int, preprocess: bool) -> List[str]:
    """URLコンテンツを処理してチャンクに分割"""
    if not content:
        return []
    
    if preprocess:
        content = preprocess_text_txt(content)  # TXT用の前処理を使用
        print("前処理後のコンテンツ:", content) 
    
    return split_into_chunks_txt(content, chunk_size)


##########################################
# 指定URL情報保存エンドポイント
##########################################
@app.post("/ingest-url")
async def ingest_from_url(request: UrlIngestRequest):
    """
    URLの内容を知識ベースに保存
    - url: 取得対象のURL
    - chunk_size: チャンクサイズ (デフォルト: 1000)
    - preprocess: 前処理を行うか (デフォルト: True)
    """
    if not is_valid_url(request.url):
        raise HTTPException(status_code=400, detail="無効なURL形式です")
    
    content = fetch_url_content(request.url)
    if not content:
        raise HTTPException(status_code=400, detail="URLからコンテンツを取得できませんでした")
    
    chunks = process_url_content(content, request.chunk_size, request.preprocess)
    if not chunks:
        raise HTTPException(status_code=400, detail="有効なチャンクを生成できませんでした")
    
    try:
        # バッチ処理で保存
        batch_size = min(50, max(10, len(chunks) // 10))
        print(f"バッチサイズ: {batch_size}")
        print(f"保存するチャンク数: {len(chunks)}")
        successful_chunks = 0
        
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i + batch_size]
            try:
                print(f"バッチ {i//batch_size + 1} を保存中: {len(batch)} チャンク")
                vector_store.add_texts(batch)
                successful_chunks += len(batch)
            except Exception as e:
                print(f"バッチ {i//batch_size + 1} の保存中にエラーが発生しました: {str(e)}")
                # 失敗した場合は個別に試す
                for chunk in batch:
                    try:
                        vector_store.add_texts([chunk])
                        successful_chunks += 1
                    except Exception as e:
                        print(f"チャンクの保存に失敗しました: {str(e)}")
                        continue
        
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"知識ベースへの保存中にエラーが発生しました: {str(e)}")

# シャットダウン処理
@app.on_event("shutdown")
async def shutdown_event():
    """アプリケーション終了時にクライアントを閉じる"""
    client.close()
    print("Weaviateクライアントを閉じました")

# アプリケーションの起動(例: uvicorn app:app --reload)
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
