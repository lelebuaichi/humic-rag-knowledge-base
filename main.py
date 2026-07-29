from pathlib import Path

import streamlit as st

import config_data as config
from auth_ui import USER_SESSION_KEY
from database import init_database


# 整个应用的默认页面配置
st.set_page_config(
    page_title="聚能腐植酸课题组知识库",
    page_icon="📚",
    layout="wide",
)
# ==================================================
# 初始化运行目录和SQLite数据库
# ==================================================

Path(config.persist_directory).mkdir(
    parents=True,
    exist_ok=True,
)

Path(config.uploads_directory).mkdir(
    parents=True,
    exist_ok=True,
)

Path(config.database_path).parent.mkdir(
    parents=True,
    exist_ok=True,
)

Path("chat_history").mkdir(
    parents=True,
    exist_ok=True,
)

init_database()

# ==================================================
# 定义四个页面
# ==================================================

qa_page = st.Page(
    "pages/qa_page.py",
    title="知识库问答",
    icon="💬",
    default=True,
)

upload_page = st.Page(
    "pages/file_upload_page.py",
    title="文献上传",
    icon="📄",
)

file_manager_page = st.Page(
    "pages/file_manager_page.py",
    title="共享文献管理",
    icon="📚",
)

user_manager_page = st.Page(
    "pages/user_manager_page.py",
    title="组员账号管理",
    icon="👥",
)


# ==================================================
# 读取当前登录用户
# ==================================================

current_user = st.session_state.get(
    USER_SESSION_KEY
)


# ==================================================
# 根据登录状态和角色生成导航
# ==================================================

if current_user is None:
    # 未登录时只注册问答页面。
    # qa_page.py中的require_login()
    # 会负责显示登录界面。
    current_page = st.navigation(
        [
            qa_page,
        ]
    )

elif current_user["role"] == "admin":
    # 管理员可以访问全部四个页面
    current_page = st.navigation(
        {
            "知识库": [
                qa_page,
                upload_page,
                file_manager_page,
            ],
            "系统管理": [
                user_manager_page,
            ],
        }
    )

else:
    # 普通成员不能访问账号管理页面
    current_page = st.navigation(
        {
            "知识库": [
                qa_page,
                upload_page,
                file_manager_page,
            ],
        }
    )


# 执行当前选中的页面
current_page.run()