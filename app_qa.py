"""
Streamlit文献查询聊天页面。
"""

import uuid

import streamlit as st

from rag import RagService


st.set_page_config(
    page_title="文献查询",
    page_icon="🔍",
)

st.title("文献查询")
st.divider()


# --------------------------------------------------
# 1. 初始化页面显示用的消息记录
# --------------------------------------------------
if "messages" not in st.session_state:
    st.session_state["messages"] = [
        {
            "role": "assistant",
            "content": "你好，有什么可以帮助你？",
        }
    ]


# --------------------------------------------------
# 2. 初始化RAG服务
# --------------------------------------------------
if "rag" not in st.session_state:
    st.session_state["rag"] = RagService()


# --------------------------------------------------
# 3. 为当前浏览器会话生成独立session_id
# --------------------------------------------------
if "session_id" not in st.session_state:
    st.session_state["session_id"] = str(
        uuid.uuid4()
    )


session_config = {
    "configurable": {
        "session_id": st.session_state["session_id"]
    }
}


# --------------------------------------------------
# 4. 显示此前的页面聊天记录
# --------------------------------------------------
for message in st.session_state["messages"]:
    with st.chat_message(message["role"]):
        st.write(message["content"])


# --------------------------------------------------
# 5. 显示用户输入框
# --------------------------------------------------
prompt = st.chat_input(
    "请输入需要查询的问题"
)


# --------------------------------------------------
# 6. 用户提交问题后执行RAG
# --------------------------------------------------
if prompt:
    # 显示用户问题
    with st.chat_message("user"):
        st.write(prompt)

    # 保存用户问题，用于下一次页面刷新后继续显示
    st.session_state["messages"].append(
        {
            "role": "user",
            "content": prompt,
        }
    )

    try:
        with st.chat_message("assistant"):
            with st.spinner("AI思考中……"):
                # 调用LangChain流式执行
                response_stream = (
                    st.session_state["rag"]
                    .chain
                    .stream(
                        {
                            "input": prompt
                        },
                        config=session_config,
                    )
                )

                # write_stream负责逐块显示，
                # 并返回拼接后的完整回答
                ai_response = st.write_stream(
                    response_stream
                )

        # 理论上StrOutputParser输出的都是字符串。
        # 这里增加一次类型保护。
        if isinstance(ai_response, list):
            ai_response = "".join(
                str(chunk)
                for chunk in ai_response
            )

        # 保存AI回答，用于下一次页面刷新后继续显示
        st.session_state["messages"].append(
            {
                "role": "assistant",
                "content": ai_response,
            }
        )

    except Exception as error:
        error_message = f"回答生成失败：{error}"

        with st.chat_message("assistant"):
            st.error(error_message)

        st.session_state["messages"].append(
            {
                "role": "assistant",
                "content": error_message,
            }
        )