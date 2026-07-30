from getpass import getpass

from auth_service import create_user
from database import init_database

def main() -> None:
    # 确保首次创建管理员前，数据库表已经存在
    init_database()

    print("创建课题组知识库管理员账号")


    username = input(
        "管理员用户名："
    ).strip()

    display_name = input(
        "管理员姓名："
    ).strip()

    password = getpass(
        "管理员密码（至少8位）："
    )

    confirm_password = getpass(
        "再次输入密码："
    )

    if password != confirm_password:
        print("两次输入的密码不一致")
        return

    try:
        user_id = create_user(
            username=username,
            display_name=display_name,
            password=password,
            role="admin",
        )

        print(
            f"管理员创建成功，用户ID：{user_id}"
        )

    except ValueError as error:
        print(f"创建失败：{error}")


if __name__ == "__main__":
    main()