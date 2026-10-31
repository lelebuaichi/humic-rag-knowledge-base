import os

from langchain_openai import ChatOpenAI
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import (
    ChatPromptTemplate,
    MessagesPlaceholder,
)
from langchain_core.runnables import (
    RunnableLambda,
    RunnableWithMessageHistory,
)

from file_history_store import get_history
from vector_stores import VectorStoreService
import config_data as config


class RagService:

    def __init__(self):
        # 向量化模型仍使用阿里云百炼 DashScope
        dashscope_api_key = os.getenv("DASHSCOPE_API_KEY")

        if not dashscope_api_key:
            raise RuntimeError(
                "未检测到 DASHSCOPE_API_KEY，"
                "请配置环境变量或 Streamlit Secrets。"
            )

        # 对话模型使用 DeepSeek
        deepseek_api_key = os.getenv("DEEPSEEK_API_KEY")

        if not deepseek_api_key:
            raise RuntimeError(
                "未检测到 DEEPSEEK_API_KEY，"
                "请配置环境变量或 Streamlit Secrets。"
            )
        """初始化RAG服务。"""

        # 创建向量库服务
        self.vector_service = VectorStoreService(
            embedding=DashScopeEmbeddings(
                model=config.embedding_model_name,
                dashscope_api_key=dashscope_api_key,
            )
        )

        # 创建提示词模板
        self.prompt_template = ChatPromptTemplate.from_messages(
            [
                (
                    "system", """
                    请根据提供的参考资料回答用户问题。

                    要求：
                    1. 优先依据当前参考资料中的明确事实回答。
                    2. 不要将对话历史中的AI回答视为事实依据。
                    3. 如果参考资料没有明确支持某个结论，不要自行补充或强化因果关系。
                    4. 可以总结和归纳参考资料，但应区分“文献明确说明”和“可能的推断”。
                    5. 如果参考资料不足以回答某一点，请明确说明资料不足。
                    6. 回答应简洁、专业。

                    当前参考资料：
                    {context}
                    """
                ),

                # 历史消息插入位置
                MessagesPlaceholder(
                    variable_name="history"
                ),

                # 当前用户问题
                (
                    "user",
                    "请回答用户提问：{input}",
                ),
            ]
        )

        # 创建聊天模型
        self.chat_model = ChatOpenAI(
            model=config.chat_model_name,
            api_key=deepseek_api_key,
            base_url=os.getenv(
                "LLM_BASE_URL",
                "https://api.deepseek.com",
            ),
        )

        # 创建完整执行链
        self.chain = self._get_chain()

    def _get_chain(self):
        """创建并返回带历史记录的RAG链。"""

        def retrieve_documents(
                query: str,
        ) -> list[Document]:
            """
            完整检索流程：

            Query
            → Semantic + BM25
            → RRF Hybrid Search
            → Reranker
            → Top-K Child
            → Small-to-Big
            → Parent
            """

            return self.vector_service.retrieve_parent_documents(
                query=query
            )

        def format_documents(
                docs: list[Document],
        ) -> str:
            """
            将检索到的Document列表整理成参考资料字符串。
            """

            if not docs:
                return "未检索到相关参考资料。"

            formatted_parts = []

            for index, doc in enumerate(docs, start=1):
                metadata = doc.metadata

                formatted_parts.append(
                    f"参考资料{index}：\n"
                    f"文档内容：{doc.page_content}\n"
                    f"来源文件："
                    f"{metadata.get('source', '未知')}\n"
                    f"页码："
                    f"{metadata.get('page', '未知')}\n"
                    f"章节："
                    f"{metadata.get('section', '未知')}\n"
                    f"内容类型："
                    f"{metadata.get('content_type', '未知')}\n"
                    f"上传人："
                    f"{metadata.get('uploader', '未知')}\n"
                    f"上传时间："
                    f"{metadata.get('create_time', '未知')}"
                )

            return "\n\n".join(formatted_parts)

        def print_prompt_value(value):
            """
            打印已经填充完成的最终提示词。
            该函数仅用于调试。
            """

            print("\n========== 最终提示词 ==========")
            print(value.to_string())
            print("================================\n")

            # 必须返回原值，继续传给模型
            return value

        # 从输入字典中提取当前问题
        extract_input = RunnableLambda(
            lambda value: value["input"]
        )

        # 从输入字典中提取历史记录
        extract_history = RunnableLambda(
            lambda value: value.get("history", [])
        )

        # 普通RAG链
        rag_chain = (
            {
                # 当前问题直接填入提示词
                "input": extract_input,

                # 当前问题进入向量库检索
                "context": (
                        extract_input
                        | RunnableLambda(retrieve_documents)
                        | RunnableLambda(format_documents)
                ),

                # 历史记录填入MessagesPlaceholder
                "history": extract_history,
            }
            | self.prompt_template
            | RunnableLambda(print_prompt_value)
            | self.chat_model
            | StrOutputParser()
        )

        # 为RAG链增加会话历史管理
        conversation_chain = RunnableWithMessageHistory(
            rag_chain,
            get_history,
            input_messages_key="input",
            history_messages_key="history",
        )

        return conversation_chain

    def ask(
        self,
        question: str,
        session_id: str,
    ) -> str:
        """
        提问接口。

        question：
            用户当前问题。

        session_id：
            用于区分不同会话。
        """

        if not question.strip():
            return "问题不能为空。"

        session_config = {
            "configurable": {
                "session_id": session_id
            }
        }

        return self.chain.invoke(
            {
                "input": question.strip()
            },
            config=session_config,
        )


if __name__ == "__main__":
    rag_service = RagService()

    result = rag_service.ask(
        question="What role does hydroxyl radical (•OH) play "
        "in the humification of Enteromorpha prolifera "
        "by Fenton's reagent?",
        session_id="rag_grounding_test_001",
    )

    print("模型回答：")
    print(result)