from getpass import getpass

from auth_service import reset_password
from database import init_database


def main() -> None:
    # 确保数据库表已存在
    init_database()

    print("重置「智能验布机异常处理助手」用户密码")

    username = input(
        "要重置的用户名："
    ).strip()

    new_password = getpass(
        "新密码（至少8位）："
    )

    confirm_password = getpass(
        "再次输入新密码："
    )

    if new_password != confirm_password:
        print("两次输入的密码不一致")
        return

    try:
        reset_password(
            username=username,
            new_password=new_password,
        )

        print(
            f"用户 {username} 密码重置成功"
        )

    except ValueError as error:
        print(f"重置失败：{error}")


if __name__ == "__main__":
    main()
