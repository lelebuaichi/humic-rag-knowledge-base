"""
Streamlit知识库文件上传页面。

功能：
1. 支持TXT和PDF上传；
2. PDF优先提取文字层；
3. 文字层不足时，将整页渲染成PNG并使用RapidOCR；
4. 按页保留来源、页码、正文/参考文献类型和提取方式；
5. 将Document列表交给KnowledgeBaseService切分并写入Chroma。
"""


import re

import fitz
import streamlit as st

from langchain_core.documents import Document
from langchain_core.documents.base import Blob

from langchain_community.document_loaders.parsers import (
    RapidOCRBlobParser,
)

from knowledge_base import KnowledgeBaseService

from auth_ui import (
    require_login,
    render_account_sidebar,
)

st.set_page_config(
    page_title="课题组文献上传",
    page_icon="📄",
    layout="wide",
)


current_user = require_login()

render_account_sidebar(current_user)


st.title("课题组文献上传")


# 用于识别论文中的参考文献标题。
REFERENCE_PATTERN = re.compile(
    r"(?im)^\s*(references|bibliography|参考文献)\s*$"
)


@st.cache_resource     #语法糖
def get_knowledge_base_service() -> KnowledgeBaseService:    #被装饰的函数，也就是另外一个函数的参数
    """
    创建并缓存知识库服务对象。

    Streamlit每次交互都会重新执行脚本，
    使用cache_resource可以避免重复创建Chroma连接。
    """
    return KnowledgeBaseService()


@st.cache_resource
def get_ocr_parser() -> RapidOCRBlobParser:
    """
    创建并缓存RapidOCR解析器，
    避免每处理一页都重新初始化OCR模型。
    """
    return RapidOCRBlobParser()


service = get_knowledge_base_service()


def read_txt_file(file_bytes: bytes) -> str:
    """
    读取TXT文件，依次尝试常见编码。
    """

    encodings = [
        "utf-8-sig",
        "utf-8",
        "gb18030",
    ]

    for encoding in encodings:
        try:
            return file_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue

    raise ValueError("TXT文件编码无法识别。")


def create_txt_documents(
    text: str,
    file_name: str,
    include_references: bool,
) -> list[Document]:
    """
    将TXT文本转换为Document列表。

    如果检测到参考文献标题，则把正文和参考文献分开。
    """

    text = text.strip()

    if not text:
        return []

    reference_match = REFERENCE_PATTERN.search(text)

    # 没有检测到参考文献标题，整篇作为正文。
    if reference_match is None:
        return [
            Document(
                page_content=text,
                metadata={
                    "source": file_name,
                    "page": 1,
                    "section": "body",
                    "content_type": "body",
                    "extraction_method": "txt_decode",
                },
            )
        ]

    documents: list[Document] = []

    body_text = text[:reference_match.start()].strip()
    reference_text = text[reference_match.start():].strip()

    if body_text:
        documents.append(
            Document(
                page_content=body_text,
                metadata={
                    "source": file_name,
                    "page": 1,
                    "section": "body",
                    "content_type": "body",
                    "extraction_method": "txt_decode",
                },
            )
        )

    if include_references and reference_text:
        documents.append(
            Document(
                page_content=reference_text,
                metadata={
                    "source": file_name,
                    "page": 1,
                    "section": "references",
                    "content_type": "reference",
                    "extraction_method": "txt_decode",
                },
            )
        )

    return documents


def ocr_page_with_rapidocr(page: fitz.Page) -> str:
    """
    将整个PDF页面渲染成PNG，再使用RapidOCR识别文字。

    这种方式可以避开PyPDFLoader直接提取PDF内嵌图片时，
    某些图片压缩格式导致的reshape错误。
    """

    # 2倍缩放可提升OCR清晰度。
    matrix = fitz.Matrix(2.0, 2.0)

    pixmap = page.get_pixmap(
        matrix=matrix,
        alpha=False,
    )

    image_bytes = pixmap.tobytes("png")

    image_blob = Blob.from_data(
        data=image_bytes,
        mime_type="image/png",
    )

    parser = get_ocr_parser()

    parsed_documents = list(
        parser.lazy_parse(image_blob)
    )

    text_parts: list[str] = []

    for document in parsed_documents:
        text = document.page_content.strip()

        if text:
            text_parts.append(text)

    return "\n".join(text_parts)


def append_page_documents(
    documents: list[Document],
    page_text: str,
    file_name: str,
    page_number: int,
    extraction_method: str,
    include_references: bool,
    in_reference_section: bool,
) -> bool:
    """
    将当前页面内容加入documents，并返回新的参考文献状态。

    返回值：
        True：当前页或之前页面已经进入参考文献区域。
        False：仍处于正文区域。
    """

    # 前面的页面已经进入参考文献区域。
    if in_reference_section:
        if include_references:
            documents.append(
                Document(
                    page_content=page_text,
                    metadata={
                        "source": file_name,
                        "page": page_number,
                        "section": "references",
                        "content_type": "reference",
                        "extraction_method": extraction_method,
                    },
                )
            )

        return True

    reference_match = REFERENCE_PATTERN.search(page_text)

    # 普通正文页。
    if reference_match is None:
        documents.append(
            Document(
                page_content=page_text,
                metadata={
                    "source": file_name,
                    "page": page_number,
                    "section": "body",
                    "content_type": "body",
                    "extraction_method": extraction_method,
                },
            )
        )

        return False

    # 当前页同时包含正文末尾和参考文献开头。
    body_text = page_text[:reference_match.start()].strip()
    reference_text = page_text[reference_match.start():].strip()

    if body_text:
        documents.append(
            Document(
                page_content=body_text,
                metadata={
                    "source": file_name,
                    "page": page_number,
                    "section": "body",
                    "content_type": "body",
                    "extraction_method": extraction_method,
                },
            )
        )

    if include_references and reference_text:
        documents.append(
            Document(
                page_content=reference_text,
                metadata={
                    "source": file_name,
                    "page": page_number,
                    "section": "references",
                    "content_type": "reference",
                    "extraction_method": extraction_method,
                },
            )
        )

    return True


def read_pdf_file(
    file_bytes: bytes,
    file_name: str,
    include_references: bool,
) -> tuple[
    list[Document],
    int,
    list[int],
    list[int],
    list[str],
]:
    """
    读取PDF并按页生成Document。

    处理规则：
    1. 优先读取PDF现有文字层；
    2. 当前页文字少于30个字符时，使用整页RapidOCR；
    3. 保留页码和提取方式；
    4. 区分正文和参考文献。
    """

    documents: list[Document] = []
    ocr_pages: list[int] = []
    failed_pages: list[int] = []
    ocr_errors: list[str] = []

    in_reference_section = False

    try:
        pdf_document = fitz.open(
            stream=file_bytes,
            filetype="pdf",
        )
    except Exception as error:
        raise ValueError(
            f"PDF无法打开，文件可能损坏或格式异常：{error}"
        ) from error

    try:
        total_pages = pdf_document.page_count

        for page_index in range(total_pages):
            page_number = page_index + 1
            page = pdf_document[page_index]

            try:
                page_text = page.get_text("text").strip()
            except Exception as error:
                page_text = ""
                ocr_errors.append(
                    f"第{page_number}页文字层提取失败：{error}"
                )

            extraction_method = "text_layer"

            # 文字层太少，通常说明当前页为扫描页或图片页。
            if len(page_text) < 30:
                try:
                    page_text = ocr_page_with_rapidocr(
                        page
                    ).strip()

                    extraction_method = "rapidocr"
                    ocr_pages.append(page_number)

                except Exception as error:
                    failed_pages.append(page_number)
                    ocr_errors.append(
                        f"第{page_number}页RapidOCR失败：{error}"
                    )
                    continue

            if not page_text:
                failed_pages.append(page_number)
                continue

            in_reference_section = append_page_documents(
                documents=documents,
                page_text=page_text,
                file_name=file_name,
                page_number=page_number,
                extraction_method=extraction_method,
                include_references=include_references,
                in_reference_section=in_reference_section,
            )

        return (
            documents,
            total_pages,
            ocr_pages,
            failed_pages,
            ocr_errors,
        )

    finally:
        pdf_document.close()


with st.form("knowledge_upload_form"):
    uploader_file = st.file_uploader(
        "请上传文件",
        type=["txt", "pdf"],
        accept_multiple_files=False,
    )

    # 上传人直接使用当前登录账号，不能手工冒用他人姓名
    operator = current_user["username"]

    st.info(
        f"当前上传人："
        f"{current_user['display_name']} "
        f"（账号：{current_user['username']}）"
    )

    include_references = st.checkbox(
        "将参考文献部分也写入知识库",
        value=False,
        help=(
            "普通问答知识库通常不需要将论文末尾的"
            "参考文献列表写入向量库。"
        ),
    )

    submit_button = st.form_submit_button(
        "开始载入知识库"
    )


if submit_button:
    if uploader_file is None:
        st.error("请先选择需要上传的文件。")
        st.stop()

    operator = operator.strip()

    if not operator:
        st.error("请输入上传人姓名。")
        st.stop()

    file_name = uploader_file.name
    file_type = uploader_file.type
    file_size_kb = uploader_file.size / 1024
    file_bytes = uploader_file.getvalue()

    st.subheader(f"文件名：{file_name}")

    st.write(
        f"格式：{file_type} | "
        f"大小：{file_size_kb:.2f} KB | "
        f"上传人：{operator}"
    )

    # 统一初始化，避免TXT和PDF分支变量不一致。
    documents: list[Document] = []
    total_pages = 0
    ocr_pages: list[int] = []
    failed_pages: list[int] = []
    ocr_errors: list[str] = []

    try:
        if file_name.lower().endswith(".txt"):
            text = read_txt_file(file_bytes)

            documents = create_txt_documents(
                text=text,
                file_name=file_name,
                include_references=include_references,
            )

            total_pages = 1

        elif file_name.lower().endswith(".pdf"):
            (
                documents,
                total_pages,
                ocr_pages,
                failed_pages,
                ocr_errors,
            ) = read_pdf_file(
                file_bytes=file_bytes,
                file_name=file_name,
                include_references=include_references,
            )

        else:
            st.error("暂不支持该文件格式。")
            st.stop()

    except Exception as error:
        st.error(f"文件读取失败：{error}")
        st.stop()

    if not documents:
        st.error(
            "PDF文字层提取和RapidOCR均未获得可入库文字。"
            "该文件可能已经损坏、被加密、页面清晰度过低，"
            "或者需要多模态模型进一步解析。"
        )

        if ocr_errors:
            with st.expander("查看详细错误"):
                for error_message in ocr_errors:
                    st.code(error_message)

        st.stop()

    st.write(
        f"文件共 {total_pages} 页，"
        f"当前生成 {len(documents)} 个页面级文档。"
    )

    if ocr_pages:
        ocr_page_text = "、".join(
            str(page_number)
            for page_number in ocr_pages
        )

        st.info(
            f"第 {ocr_page_text} 页没有足够的文字层，"
            "已使用RapidOCR识别。"
        )

    if failed_pages:
        failed_page_text = "、".join(
            str(page_number)
            for page_number in failed_pages
        )

        st.warning(
            f"第 {failed_page_text} 页经过处理后"
            "仍未提取到有效文字，因此不会写入知识库。"
        )

    if ocr_errors:
        with st.expander("查看OCR或文字提取错误"):
            for error_message in ocr_errors:
                st.code(error_message)

    preview_parts: list[str] = []

    for document in documents[:5]:
        preview_parts.append(
            f"文件：{document.metadata.get('source', '未知')}\n"
            f"页码：{document.metadata.get('page', '未知')}\n"
            f"章节：{document.metadata.get('section', '未知')}\n"
            f"类型：{document.metadata.get('content_type', '未知')}\n"
            f"提取方式："
            f"{document.metadata.get('extraction_method', '未知')}\n"
            f"内容：\n{document.page_content[:1500]}"
        )

    with st.expander("查看提取结果"):
        st.text(
            ("\n\n" + "=" * 70 + "\n\n").join(
                preview_parts
            )
        )

    with st.spinner(
        "正在切分、向量化并载入知识库……"
    ):
        try:
            result = service.upload_documents(
                documents=documents,
                file_bytes=file_bytes,
                filename=file_name,
                operator = current_user["username"],
                uploader_id=current_user["id"],
            )
        except Exception as error:
            st.error(f"写入知识库失败：{error}")
            st.stop()

    if result.startswith("跳过"):
        st.warning(result)
    elif "成功" in result:
        st.success(result)
    else:
        st.info(result)