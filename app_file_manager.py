import streamlit as st

from auth_ui import (
    require_login,
    render_account_sidebar,
)
from file_service import list_file_records


st.set_page_config(
    page_title="共享文献管理",
    page_icon="📚",
    layout="wide",
)


# 只有登录用户才能访问
current_user = require_login()

render_account_sidebar(current_user)


st.title("共享文献列表")

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


if failed_count > 0:
    st.warning(
        f"当前有 {failed_count} 篇文献处理失败，"
        "需要管理员进一步检查。"
    )