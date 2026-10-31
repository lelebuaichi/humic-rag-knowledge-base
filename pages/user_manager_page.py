import streamlit as st
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from auth_service import (
    create_user,
    list_users,
    set_user_status,
)
from auth_ui import (
    require_admin,
    render_account_sidebar,
)


st.set_page_config(
    page_title="组员账号管理",
    page_icon="👥",
    layout="wide",
)


# 当前页面只允许管理员访问
current_user = require_admin()

render_account_sidebar(current_user)


st.title("组员账号管理")

st.caption(
    "管理员可以创建组员账号，并启用或禁用已有账号。"
)


# 显示操作成功消息
operation_message = st.session_state.pop(
    "user_operation_message",
    None,
)

if operation_message:
    st.success(operation_message)


# ==================================================
# 创建普通成员
# ==================================================

st.subheader("创建组员账号")

with st.form(
    "create_member_form",
    clear_on_submit=True,
):
    username = st.text_input(
        "登录用户名",
        help="用户名必须唯一，建议使用姓名拼音或工号。",
    )

    display_name = st.text_input(
        "组员姓名",
    )

    password = st.text_input(
        "初始密码",
        type="password",
        help="密码长度至少为8位。",
    )

    confirm_password = st.text_input(
        "再次输入初始密码",
        type="password",
    )

    create_button = st.form_submit_button(
        "创建组员账号",
        use_container_width=True,
    )


if create_button:
    username = username.strip()
    display_name = display_name.strip()

    if not username:
        st.error("请输入登录用户名。")

    elif not display_name:
        st.error("请输入组员姓名。")

    elif password != confirm_password:
        st.error("两次输入的密码不一致。")

    else:
        try:
            user_id = create_user(
                username=username,
                display_name=display_name,
                password=password,
                role="member",
            )

            st.session_state[
                "user_operation_message"
            ] = (
                f"组员账号创建成功："
                f"{display_name}，用户ID：{user_id}。"
            )

            st.rerun()

        except ValueError as error:
            st.error(f"创建失败：{error}")


# ==================================================
# 用户列表
# ==================================================

st.divider()

st.subheader("账号列表")

users = list_users()


role_text = {
    "admin": "管理员",
    "member": "普通成员",
}

status_text = {
    "active": "已启用",
    "disabled": "已禁用",
}


display_users = []

for index, user in enumerate(
    users,
    start=1,
):
    display_users.append(
        {
            "序号": index,
            "用户ID": user["id"],
            "登录用户名": user["username"],
            "姓名": user["display_name"],
            "角色": role_text.get(
                user["role"],
                user["role"],
            ),
            "状态": status_text.get(
                user["status"],
                user["status"],
            ),
            "创建时间": user["created_at"],
        }
    )


active_count = sum(
    user["status"] == "active"
    for user in users
)

member_count = sum(
    user["role"] == "member"
    for user in users
)


column1, column2, column3 = st.columns(3)

column1.metric(
    "账号总数",
    len(users),
)

column2.metric(
    "普通成员",
    member_count,
)

column3.metric(
    "已启用账号",
    active_count,
)


st.dataframe(
    display_users,
    use_container_width=True,
    hide_index=True,
)


# ==================================================
# 启用或禁用普通成员
# ==================================================

st.divider()

st.subheader("启用或禁用组员账号")

member_users = [
    user
    for user in users
    if user["role"] == "member"
]


if not member_users:
    st.info("当前还没有普通成员账号。")

else:
    member_by_id = {
        user["id"]: user
        for user in member_users
    }

    selected_user_id = st.selectbox(
        "选择组员",
        options=list(member_by_id.keys()),
        format_func=lambda user_id: (
            member_by_id[user_id]["display_name"]
            + "｜账号："
            + member_by_id[user_id]["username"]
            + "｜状态："
            + status_text.get(
                member_by_id[user_id]["status"],
                member_by_id[user_id]["status"],
            )
        ),
    )

    selected_user = member_by_id[
        selected_user_id
    ]

    current_status = selected_user[
        "status"
    ]

    if current_status == "active":
        target_status = "disabled"
        button_text = "禁用该账号"
        help_text = (
            "禁用后，该组员将无法继续登录系统。"
        )

    else:
        target_status = "active"
        button_text = "重新启用该账号"
        help_text = (
            "重新启用后，该组员可以正常登录系统。"
        )

    st.info(help_text)

    change_status_button = st.button(
        button_text,
        type="primary",
        use_container_width=True,
    )

    if change_status_button:
        try:
            set_user_status(
                user_id=selected_user_id,
                status=target_status,
            )

            target_status_text = status_text[
                target_status
            ]

            st.session_state[
                "user_operation_message"
            ] = (
                f"账号状态修改成功："
                f"{selected_user['display_name']}，"
                f"当前状态为{target_status_text}。"
            )

            st.rerun()

        except ValueError as error:
            st.error(
                f"修改账号状态失败：{error}"
            )