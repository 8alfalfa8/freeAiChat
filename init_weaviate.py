import os
from dotenv import load_dotenv
load_dotenv()
import weaviate
from weaviate.classes.config import Property, DataType  # Import DataType enum
from weaviate.embedded import EmbeddedOptions

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

# Weaviateクライアントの初期化
try:
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

index_name = os.getenv("WEAVIATE_INDEX_NAME", "DefaultCollection")  # Provide default name

# Get the collections object
collections = client.collections

# スキーマ存在確認 & 作成
if not collections.exists(index_name):
    # Create the collection
    collections.create(
        name=index_name,
        properties=[
            Property(name="text", data_type=DataType.TEXT)
        ],
        vectorizer_config=None
    )
    print("索引创建成功")
else:
    print("索引已存在")

client.close()  # コネクションを明示的にクローズ