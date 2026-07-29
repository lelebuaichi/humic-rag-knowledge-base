"""
知识库服务：
1. MD5精确查重
2. 文本切分
3. 文本向量化
4. 写入Chroma
"""

import hashlib
import os
from datetime import datetime
from pathlib import Path

from langchain_chroma import Chroma
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

import config_data as config

from file_service import (
    create_file_record,
    get_file_by_md5,
    mark_file_failed,
    mark_file_ready,
    save_original_file,
)


def prepare_md5_file() -> Path:
    """
    确保MD5记录文件及其父目录存在。
    """

    md5_file = Path(config.md5_path)

    # 当md5_path包含文件夹时，确保文件夹存在
    md5_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    # 文件不存在时创建空文件
    md5_file.touch(exist_ok=True)

    return md5_file


def check_md5(md5_str: str) -> bool:
    """
    检查MD5是否已经记录。

    True：
        已经处理过。

    False：
        没有处理过。
    """

    md5_file = prepare_md5_file()

    with md5_file.open(
        "r",
        encoding="utf-8",
    ) as file:
        for line in file:
            saved_md5 = line.strip()

            if saved_md5 == md5_str:
                return True

    return False


def save_md5(md5_str: str) -> None:
    """
    将MD5追加到记录文件。
    """

    md5_file = prepare_md5_file()

    with md5_file.open(
        "a",
        encoding="utf-8",
    ) as file:
        file.write(md5_str + "\n")


def get_string_md5(
    input_str: str,
    encoding: str = "utf-8",
) -> str:
    """
    计算字符串的MD5。
    """

    string_bytes = input_str.encode(encoding)

    md5_object = hashlib.md5()
    md5_object.update(string_bytes)

    return md5_object.hexdigest()


def get_bytes_md5(file_bytes: bytes) -> str:
    """
    计算原始文件二进制的MD5。

    PDF等文件应使用这个函数。
    """

    md5_object = hashlib.md5()
    md5_object.update(file_bytes)

    return md5_object.hexdigest()


class KnowledgeBaseService:

    def __init__(self):
        """
        初始化Chroma和文本分割器。
        """

        # 创建Chroma持久化文件夹
        os.makedirs(
            config.persist_directory,
            exist_ok=True,
        )

        # 创建或连接Chroma向量库
        self.chroma = Chroma(
            collection_name=config.collection_name,
            embedding_function=DashScopeEmbeddings(
                model=config.embedding_model_name
            ),
            persist_directory=config.persist_directory,
        )

        # 创建文本分割器
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=config.chunk_size,
            chunk_overlap=config.chunk_overlap,
            separators=config.separators,
            length_function=len,
        )

    def upload_by_str(
        self,
        data: str,
        filename: str,
        operator: str,
        page_number: int = 1,
        section_name: str = "body",
    ) -> str:
        """
        上传一段字符串。

        主要适用于TXT或程序直接提供的文本。
        """

        if not data.strip():
            return "内容为空，未载入知识库"

        operator = operator.strip()

        if not operator:
            return "上传人不能为空"

        # 将字符串包装成Document
        document = Document(
            page_content=data.strip(),
            metadata={
                "source": filename,
                "page": page_number,
                "section": section_name,
                "content_type": "body",
            },
        )

        # 字符串没有原始文件bytes，
        # 因此使用UTF-8编码后的字节计算MD5
        return self.upload_documents(
            documents=[document],
            file_bytes=data.encode("utf-8"),
            filename=filename,
            operator=operator,
        )

    def delete_documents_by_md5(
            self,
            file_md5: str,
    ) -> int:
        """
        根据文件MD5删除Chroma中的全部知识片段。

        返回实际找到并删除的知识片段数量。
        """

        result = self.chroma.get(
            where={
                "file_md5": file_md5,
            },
        )

        document_ids = result.get(
            "ids",
            [],
        )

        if not document_ids:
            return 0

        self.chroma.delete(
            ids=document_ids,
        )

        return len(document_ids)

    def upload_documents(
        self,
        documents: list[Document],
        file_bytes: bytes,
        filename: str,
        operator: str,
        uploader_id: int,
    ) -> str:
        """
        上传Document列表。

        主要适用于PDF按页解析后的文档。
        """

        if not documents:
            return "没有可载入知识库的文档"

        operator = operator.strip()

        if not operator:
            return "上传人不能为空"

        # 对原始文件计算MD5
        file_md5 = get_bytes_md5(file_bytes)

        existing_record = get_file_by_md5(
            file_md5
        )

        if existing_record is not None:
            status = existing_record["status"]

            if status == "ready":
                return (
                    "该文献已经存在于共享知识库中。"
                    f"上传人：{existing_record['uploader_name']}；"
                    f"上传时间：{existing_record['upload_time']}；"
                    f"知识片段数：{existing_record['chunk_count']}。"
                )

            if status == "processing":
                return (
                    "该文献正在处理中，请勿重复上传。"
                )

            return (
                "该文献此前处理失败，"
                "请联系管理员清理失败记录后重新上传。"
            )

        # 文件完全相同则跳过
        if check_md5(file_md5):
            return "跳过：该文件已经在知识库中"

        create_time = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        prepared_documents: list[Document] = []
        stored_path = save_original_file(
            file_bytes=file_bytes,
            filename=filename,
            file_md5=file_md5,
        )

        file_id = create_file_record(
            file_md5=file_md5,
            original_filename=filename,
            stored_path=stored_path,
            uploader_id=uploader_id,
        )

        for document in documents:
            page_content = document.page_content.strip()

            if not page_content:
                continue

            # 复制原Document中的元数据
            metadata = document.metadata.copy()

            # 增加统一的上传信息
            metadata.update(
                {
                    "source": filename,
                    "uploader": operator,
                    "create_time": create_time,
                    "file_md5": file_md5,
                }
            )

            prepared_documents.append(
                Document(
                    page_content=page_content,
                    metadata=metadata,
                )
            )

        if not prepared_documents:
            mark_file_failed(file_id)

            return "文档中没有可写入的有效文字"

        # 对Document进行切分，并保留每页元数据
        knowledge_chunks = (
            self.splitter.split_documents(
                prepared_documents
            )
        )

        if not knowledge_chunks:
            mark_file_failed(file_id)

            return "文本切分后没有生成有效知识片段"

        # 将Document列表写入Chroma
        try:
            self.chroma.add_documents(
                documents=knowledge_chunks
            )

            # Chroma写入成功后更新文献状态
            mark_file_ready(
                file_id=file_id,
                chunk_count=len(knowledge_chunks),
            )

            # 暂时保留旧MD5记录，兼容已有逻辑
            save_md5(file_md5)

        except Exception:
            # 发生异常时把文献标记为失败
            mark_file_failed(file_id)
            raise

        return (
            "内容已经成功载入共享知识库，"
            f"共生成 {len(knowledge_chunks)} 个知识片段"
        )


if __name__ == "__main__":
    service = KnowledgeBaseService()

    result = service.upload_by_str(
        data="蔡依林",
        filename="testfile.txt",
        operator="测试用户",
        page_number=1,
        section_name="body",
    )

    print(result)