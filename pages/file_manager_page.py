import streamlit as st

from auth_ui import (
    require_login,
    render_account_sidebar,
)
from file_service import (
    delete_file_record,
    delete_original_file,
    get_file_by_id,
    list_file_records,
    remove_legacy_md5,
)
from knowledge_base import KnowledgeBaseService

st.set_page_config(
    page_title="共享文献管理",
    page_icon="📚",
    layout="wide",
)

@st.cache_resource
def get_knowledge_base_service() -> KnowledgeBaseService:
    """
    创建并缓存Chroma知识库服务。
    """

    return KnowledgeBaseService()


knowledge_base_service = (
    get_knowledge_base_service()
)

# 只有登录用户才能访问
current_user = require_login()

render_account_sidebar(current_user)


st.title("共享文献列表")

delete_message = st.session_state.pop(
    "file_delete_message",
    None,
)

if delete_message:
    st.success(delete_message)

st.caption(
    "查看课题组共享知识库中已经登记的文献。"
)


# 手动刷新页面
if st.button("刷新文献列表"):
    st.rerun()


records = list_file_records()


if not records:
    st.info("共享知识库中暂时没有文献。")
    st.stop()


# 状态英文转换为中文
status_text = {
    "processing": "处理中",
    "ready": "可用",
    "failed": "处理失败",
}


display_records = []

for index, record in enumerate(
    records,
    start=1,
):
    display_records.append(
        {
            "序号": index,
            "文献名称": record[
                "original_filename"
            ],
            "上传人": record[
                "uploader_name"
            ],
            "上传账号": record[
                "uploader_username"
            ],
            "上传时间": record[
                "upload_time"
            ],
            "知识片段数": record[
                "chunk_count"
            ],
            "状态": status_text.get(
                record["status"],
                record["status"],
            ),
        }
    )


ready_count = sum(
    record["status"] == "ready"
    for record in records
)

processing_count = sum(
    record["status"] == "processing"
    for record in records
)

failed_count = sum(
    record["status"] == "failed"
    for record in records
)

total_chunks = sum(
    record["chunk_count"]
    for record in records
    if record["status"] == "ready"
)


column1, column2, column3, column4 = st.columns(4)

column1.metric(
    "文献总数",
    len(records),
)

column2.metric(
    "可用文献",
    ready_count,
)

column3.metric(
    "处理中或失败",
    processing_count + failed_count,
)

column4.metric(
    "知识片段总数",
    total_chunks,
)


st.dataframe(
    display_records,
    use_container_width=True,
    hide_index=True,
)

if current_user["role"] == "admin":
    st.divider()

    st.subheader("管理员删除文献")

    st.warning(
        "删除后，该文献的原始文件、知识片段和"
        "数据库记录都会被清除。此操作不可撤销。"
    )

    record_by_id = {
        record["id"]: record
        for record in records
    }

    selected_file_id = st.selectbox(
        "选择需要删除的文献",
        options=list(record_by_id.keys()),
        format_func=lambda file_id: (
            record_by_id[file_id][
                "original_filename"
            ]
            + "｜上传人："
            + record_by_id[file_id][
                "uploader_name"
            ]
            + "｜状态："
            + status_text.get(
                record_by_id[file_id]["status"],
                record_by_id[file_id]["status"],
            )
        ),
    )

    selected_record = record_by_id[
        selected_file_id
    ]

    st.write(
        f"文献名称："
        f"{selected_record['original_filename']}"
    )

    st.write(
        f"知识片段数："
        f"{selected_record['chunk_count']}"
    )

    confirm_delete = st.checkbox(
        "我确认永久删除这篇文献",
        key=(
            f"confirm_delete_"
            f"{selected_file_id}"
        ),
    )

    delete_button = st.button(
        "永久删除文献",
        type="primary",
        disabled=not confirm_delete,
    )

    if delete_button:
        try:
            # 删除前重新查询，防止页面数据已经过期
            file_record = get_file_by_id(
                selected_file_id
            )

            if file_record is None:
                st.error(
                    "该文献记录已经不存在，"
                    "请刷新页面。"
                )
                st.stop()

            file_md5 = file_record[
                "file_md5"
            ]

            # 1. 删除Chroma中的向量和文本片段
            deleted_chunk_count = (
                knowledge_base_service
                .delete_documents_by_md5(
                    file_md5
                )
            )

            # 2. 删除保存的原始PDF或TXT
            delete_original_file(
                file_record["stored_path"]
            )

            # 3. 删除旧版MD5判重记录
            remove_legacy_md5(
                file_md5
            )

            # 4. 最后删除SQLite记录
            delete_file_record(
                selected_file_id
            )

            st.session_state[
                "file_delete_message"
            ] = (
                f"已删除文献："
                f"{file_record['original_filename']}；"
                f"清理知识片段 "
                f"{deleted_chunk_count} 个。"
            )

            st.rerun()

        except Exception as error:
            st.error(
                f"删除失败：{error}"
            )

if failed_count > 0:
    st.warning(
        f"当前有 {failed_count} 篇文献处理失败，"
        "需要管理员进一步检查。"
    )