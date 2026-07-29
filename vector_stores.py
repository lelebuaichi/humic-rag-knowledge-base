"""
连接已有的Chroma向量库，并提供Retriever检索器。
"""

from langchain_chroma import Chroma

import config_data as config


class VectorStoreService:

    def __init__(self, embedding):
        self.embedding = embedding

        self.vector_store = Chroma(
            collection_name=config.collection_name,
            embedding_function=self.embedding,
            persist_directory=config.persist_directory,
        )

    def get_retriever(self):
        """
        返回只检索正文内容的MMR检索器。
        """

        return self.vector_store.as_retriever(
            search_type="mmr",
            search_kwargs={
                # 最终返回5条
                "k": config.retrieval_k,

                # 先取20条候选
                "fetch_k": config.retrieval_fetch_k,

                # 平衡相关性和多样性
                "lambda_mult": config.retrieval_lambda_mult,

                # 只检索正文
                "filter": {
                    "content_type": "body"
                },
            },
        )