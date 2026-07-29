import os


# 当前config_data.py所在目录，即项目根目录
BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)


# Chroma向量库配置
collection_name = "humic_knowledge_v2"

persist_directory = os.path.join(
    BASE_DIR,
    "data",
    "chroma_db",
)


# MD5记录文件路径
md5_path = os.path.join(
    BASE_DIR,
    "data",
    "md5.txt",
)


# 模型配置
embedding_model_name = "text-embedding-v4"
chat_model_name = "qwen3-max"


# 文本切分配置
chunk_size = 1000
chunk_overlap = 150

separators = [
    "\n\n",
    "\n",
    "。",
    "！",
    "？",
    ". ",
    "! ",
    "? ",
    " ",
    "",
]



# 检索配置
retrieval_k = 5
retrieval_fetch_k = 20
retrieval_lambda_mult = 0.5

similarity_threshold = 0.6


