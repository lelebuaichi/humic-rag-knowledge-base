"""
连接已有的Chroma向量库，并提供Retriever检索器。
"""

from langchain_chroma import Chroma
from sentence_transformers import CrossEncoder
import config_data as config
from langchain_core.documents import Document
from file_service import get_parent_chunk
import re
import unicodedata
import os

from rank_bm25 import BM25Okapi
class VectorStoreService:

    def __init__(self, embedding):
        self.embedding = embedding

        self.vector_store = Chroma(
            collection_name=config.collection_name,
            embedding_function=self.embedding,
            persist_directory=config.persist_directory,
        )

        # Reranker：用于对MMR召回结果重新打分排序
        # 国内环境从ModelScope预下载到 ./hf_cache/models，
        # 由compose挂载到 /models 后本地加载，避免HuggingFace网络问题。
        self.reranker = CrossEncoder(
            os.getenv(
                "RERANKER_MODEL",
                "/models/bge-reranker-base",
            )
        )
        self.bm25 = None
        self.bm25_documents: list[Document] = []
        self.bm25_document_count = 0

    def _tokenize_for_bm25(
            self,
            text: str,
    ) -> list[str]:
        """
        对英文论文文本做BM25分词。
        """

        # Unicode规范化：
        # 例如 ﬁ -> fi
        text = unicodedata.normalize(
            "NFKC",
            text,
        )

        text = text.lower()

        tokens = re.findall(
            r"[a-z0-9]+(?:['’.-][a-z0-9]+)*"
            r"|[\u4e00-\u9fff]",
            text,
        )

        return tokens

    def build_bm25_index(self) -> None:
        """
        从Chroma读取全部正文Child，
        构建BM25稀疏检索索引。
        """

        result = self.vector_store.get(
            where={
                "$and": [
                    {
                        "content_type": "body"
                    },
                    {
                        "chunk_level": "child"
                    },
                ]
            },
            include=[
                "documents",
                "metadatas",
            ],
        )

        documents = result.get("documents") or []
        metadatas = result.get("metadatas") or []

        self.bm25_documents = []

        for content, metadata in zip(
                documents,
                metadatas,
        ):
            if not content:
                continue

            self.bm25_documents.append(
                Document(
                    page_content=content,
                    metadata=metadata or {},
                )
            )

        if not self.bm25_documents:
            self.bm25 = None
            print("没有可用于BM25索引的Child")
            return

        tokenized_corpus = [
            self._tokenize_for_bm25(
                document.page_content
            )
            for document in self.bm25_documents
        ]

        self.bm25 = BM25Okapi(
            tokenized_corpus
        )

        self.bm25_document_count = len(
            self.bm25_documents
        )

    def invalidate_bm25_index(self) -> None:
        """
        让当前BM25缓存失效。

        当知识库中的Child发生新增或删除后调用。
        下一次执行bm25_search()时会自动重新构建索引。
        """

        self.bm25 = None
        self.bm25_documents = []

    def get_retriever(self):
        return self.vector_store.as_retriever(
            search_type="mmr",
            search_kwargs={
                "k": config.retrieval_candidate_k,
                "fetch_k": config.retrieval_fetch_k,
                "lambda_mult": config.retrieval_lambda_mult,
                "filter": {
                    "$and": [
                        {
                            "content_type": "body"
                        },
                        {
                            "chunk_level": "child"
                        },
                    ]
                },
            },
        )

    def bm25_search(
            self,
            query: str,
            k: int = 20,
    ) -> list[Document]:

        current_result = self.vector_store.get(
            where={
                "$and": [
                    {"content_type": "body"},
                    {"chunk_level": "child"},
                ]
            },
        )

        current_count = len(
            current_result.get("ids", [])
        )

        if (
                self.bm25 is None
                or current_count != self.bm25_document_count
        ):
            self.build_bm25_index()

        # Query也要使用和语料完全相同的分词方式
        query_tokens = self._tokenize_for_bm25(
            query
        )

        # 给所有Child计算BM25分数
        scores = self.bm25.get_scores(
            query_tokens
        )

        # 把：
        # Child + BM25分数
        # 配对起来
        scored_documents = [
            (document, float(score))
            for document, score in zip(
                self.bm25_documents,
                scores,
            )
        ]

        # 从高到低排序
        scored_documents.sort(
            key=lambda item: item[1],
            reverse=True,
        )

        # 只取Top-K
        results = []

        for document, score in scored_documents[:k]:
            metadata = document.metadata.copy()
            metadata["bm25_score"] = score

            results.append(
                Document(
                    page_content=document.page_content,
                    metadata=metadata,
                )
            )

        return results
    def semantic_search(
            self,
            query: str,
    ) -> list[Document]:
        retriever = self.get_retriever()
        return retriever.invoke(query)

    def hybrid_search(
            self,
            query: str,
            k: int = 20,
    ) -> list[Document]:
        """
        混合检索：
        1. Semantic Search
        2. BM25 Search
        3. 使用 RRF 融合两路排名
        """

        semantic_docs = self.semantic_search(
            query
        )

        bm25_docs = self.bm25_search(
            query,
            k=k,
        )

        # key:
        # (parent_id, child_index)
        #
        # value:
        # {
        #     "document": Document,
        #     "rrf_score": float
        # }
        fused_results = {}

        rrf_k = 60

        # ---------- Semantic ----------
        for rank, document in enumerate(
                semantic_docs,
                start=1,
        ):

            key = (
                document.metadata.get("parent_id"),
                document.metadata.get("child_index"),
            )

            if key not in fused_results:
                fused_results[key] = {
                    "document": document,
                    "rrf_score": 0.0,
                }

            fused_results[key]["rrf_score"] += (
                    1.0 / (rrf_k + rank)
            )

        # ---------- BM25 ----------
        for rank, document in enumerate(
                bm25_docs,
                start=1,
        ):

            key = (
                document.metadata.get("parent_id"),
                document.metadata.get("child_index"),
            )

            if key not in fused_results:
                fused_results[key] = {
                    "document": document,
                    "rrf_score": 0.0,
                }

            fused_results[key]["rrf_score"] += (
                    1.0 / (rrf_k + rank)
            )

        # 按 RRF 分数从高到低排序
        ranked_results = sorted(
            fused_results.values(),
            key=lambda item: item["rrf_score"],
            reverse=True,
        )

        results = []

        for item in ranked_results[:k]:
            document = item["document"]

            metadata = document.metadata.copy()

            metadata["rrf_score"] = item["rrf_score"]

            results.append(
                Document(
                    page_content=document.page_content,
                    metadata=metadata,
                )
            )

        return results


    def retrieve_with_rerank(
            self,
            query: str,
    ) -> list[Document]:
        """
        先使用Hybrid Search召回候选Child，
        再使用Cross-Encoder重新排序。
        """

        # 1. Hybrid Search 粗召回
        candidates = self.hybrid_search(
            query=query,
            k=config.retrieval_candidate_k,
        )

        if not candidates:
            print("没有检索到候选文档")
            return []

        # 2. 先看看Hybrid原始排序
        print("\n========== Hybrid Search 原始排序 ==========")

        for index, document in enumerate(
                candidates,
                start=1,
        ):
            print(
                f"\n第 {index} 名："
                f"{document.page_content[:150]}"
            )

        # 3. 构造Cross-Encoder输入
        # 每一项都是 [问题, 候选文本]
        pairs = [
            [
                query,
                document.page_content,
            ]
            for document in candidates
        ]

        # 4. Reranker重新打分
        scores = self.reranker.predict(pairs)

        # 5. 文档和分数绑定
        scored_documents = [
            (
                document,
                float(score),
            )
            for document, score in zip(
                candidates,
                scores,
            )
        ]

        # 6. 按Reranker分数从高到低排序
        scored_documents.sort(
            key=lambda item: item[1],
            reverse=True,
        )

        # 7. 查看Reranker新排序
        print("\n========== Reranker 新排序 ==========")

        for index, (document, score) in enumerate(
                scored_documents,
                start=1,
        ):
            print(
                f"\n第 {index} 名"
                f" | score={score:.4f}"
            )
            print(document.page_content[:150])

        # 8. 最终只保留Top-K
        final_documents = []

        for document, score in scored_documents[
            :config.rerank_final_k
        ]:
            document.metadata["rerank_score"] = score
            final_documents.append(document)

        return final_documents

    def retrieve_parent_documents(
            self,
            query: str,
    ) -> list[Document]:
        """
        Small-to-Big检索：

        1. MMR召回Child
        2. Reranker筛选Child
        3. 根据parent_id回溯SQLite中的Parent
        4. 对Parent去重
        """

        # 先获得Reranker筛选后的Child
        child_documents = self.retrieve_with_rerank(
            query=query
        )

        if not child_documents:
            return []

        parent_documents = []

        # 用于Parent去重
        seen_parent_ids = set()

        for child_document in child_documents:

            parent_id = child_document.metadata.get(
                "parent_id"
            )

            if not parent_id:
                continue

            # 同一个Parent只取一次
            if parent_id in seen_parent_ids:
                continue

            # 根据parent_id去SQLite查询完整Parent
            parent_data = get_parent_chunk(
                parent_id
            )

            if parent_data is None:
                continue

            parent_documents.append(
                Document(
                    page_content=parent_data["content"],
                    metadata={
                        "parent_id": parent_data["parent_id"],
                        "file_id": parent_data["file_id"],
                        "parent_index": parent_data["parent_index"],
                        "page": parent_data["page"],
                        "section": parent_data["section"],
                        "content_type": parent_data["content_type"],
                        "source": parent_data["source"],
                        "uploader": parent_data["uploader"],
                        "create_time": parent_data["create_time"],
                    }
                )
            )

            seen_parent_ids.add(parent_id)

        return parent_documents


if __name__ == "__main__":
    from langchain_community.embeddings import DashScopeEmbeddings

    embedding = DashScopeEmbeddings(
        model=config.embedding_model_name
    )

    service = VectorStoreService(
        embedding=embedding
    )

    query = (
        "What role does hydroxyl radical (•OH) play "
        "in the humification of Enteromorpha prolifera "
        "by Fenton's reagent?"
    )

    parent_documents = service.retrieve_parent_documents(
        query=query
    )

    print(
        "\n========== Small-to-Big 最终 Parent =========="
    )

    print(
        f"\n最终返回 Parent 数量："
        f"{len(parent_documents)}"
    )

    for index, document in enumerate(
        parent_documents,
        start=1,
    ):
        print(
            f"\n========== Parent {index} =========="
        )

        print(
            "parent_id:",
            document.metadata.get("parent_id")
        )

        print(
            "page:",
            document.metadata.get("page")
        )

        print(
            "parent_index:",
            document.metadata.get("parent_index")
        )

        print("\n完整 Parent 文本：\n")

        print(document.page_content)

