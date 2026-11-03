import streamlit as st

from auth_service import authenticate_user


USER_SESSION_KEY = "authenticated_user"


def init_auth_state() -> None:
    """
    初始化当前浏览器会话的登录状态。
    """

    if USER_SESSION_KEY not in st.session_state:
        st.session_state[USER_SESSION_KEY] = None


def render_login_page() -> None:
    """
    显示登录界面，并处理用户名和密码验证。
    """

    st.title("智能验布机异常处理助手")

    st.write(
        "本系统仅供授权用户使用。"
    )

    with st.form("login_form"):
        username = st.text_input(
            "用户名"
        )

        password = st.text_input(
            "密码",
            type="password",
        )

        submitted = st.form_submit_button(
            "登录",
            use_container_width=True,
        )

    if not submitted:
        return

    if not username.strip():
        st.error("请输入用户名")
        return

    if not password:
        st.error("请输入密码")
        return

    user = authenticate_user(
        username=username,
        password=password,
    )

    if user is None:
        st.error(
            "用户名或密码错误，"
            "或者当前账号已被禁用。"
        )
        return

    st.session_state[USER_SESSION_KEY] = user

    # 登录成功后重新运行页面
    st.rerun()


def require_login() -> dict:
    """
    要求当前用户必须登录。

    登录成功时返回用户信息字典；
    未登录时显示登录页面并停止执行后续代码。
    """

    init_auth_state()

    user = st.session_state[USER_SESSION_KEY]

    if user is None:
        render_login_page()
        st.stop()

    return user


def require_admin() -> dict:
    """
    要求当前用户必须是管理员。
    """

    user = require_login()

    if user["role"] != "admin":
        st.error("当前页面仅管理员可以访问")
        st.stop()

    return user


def render_account_sidebar(
    user: dict,
) -> None:
    """
    在侧边栏显示当前用户和退出按钮。
    """

    with st.sidebar:
        st.divider()

        st.write(
            f"当前用户：{user['display_name']}"
        )

        role_text = (
            "管理员"
            if user["role"] == "admin"
            else "普通成员"
        )

        st.caption(
            f"角色：{role_text}"
        )

        if st.button(
            "退出登录",
            use_container_width=True,
        ):
            # 清空整个浏览器会话，避免下一个登录者
            # 看到上一个用户的前端聊天记录
            st.session_state.clear()
            st.rerun()