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

# SQLite数据库路径
database_path = os.path.join(
    BASE_DIR,
    "data",
    "app.db",
)


# 组内上传原始文件的保存目录
uploads_directory = os.path.join(
    BASE_DIR,
    "data",
    "uploads",
)


# 模型配置
# 向量化模型：仍使用阿里云百炼 DashScope。
# 注意：DeepSeek 目前不提供 Embedding API，向量化不能换成 DeepSeek。
# 若更换向量化模型，必须重建整个 Chroma 向量库（不同模型的向量不能通用）。
embedding_model_name = "text-embedding-v4"

# 对话模型：DeepSeek（OpenAI 兼容接口）
# 可选 deepseek-chat（通用）或 deepseek-reasoner（推理思考）
chat_model_name = "deepseek-chat"


# 文本切分配置
parent_chunk_size =1800
parent_chunk_overlap = 200
child_chunk_size = 450
child_chunk_overlap = 80

separators = [
    "\n\n",
    "。",
    "！",
    "？",
    ". ",
    "! ",
    "? ",
    "；",
    "; ",
    "\n",
    " ",
    "",
]



# 检索配置
retrieval_candidate_k = 20
retrieval_fetch_k = 50
retrieval_lambda_mult = 0.7
rerank_final_k = 5


