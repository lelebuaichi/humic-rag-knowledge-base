import hashlib
import hmac
import secrets
import sqlite3
from datetime import datetime

from database import get_connection


# PBKDF2重复计算次数
PBKDF2_ITERATIONS = 200_000


def normalize_username(username: str) -> str:
    """
    统一处理用户名，避免大小写和首尾空格造成重复。
    """

    return username.strip().lower()


def _derive_password_hash(
    password: str,
    salt: bytes,
) -> str:
    """
    根据密码和盐值计算PBKDF2哈希。
    """

    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
    )

    return password_hash.hex()


def create_user(
    username: str,
    display_name: str,
    password: str,
    role: str = "member",
) -> int:
    """
    创建组内用户，返回新用户ID。
    """

    username = normalize_username(username)
    display_name = display_name.strip()

    if not username:
        raise ValueError("用户名不能为空")

    if not display_name:
        raise ValueError("姓名不能为空")

    if len(password) < 8:
        raise ValueError("密码长度不能少于8位")

    if role not in {"admin", "member"}:
        raise ValueError("用户角色只能是admin或member")

    # 每个用户生成独立随机盐值
    salt = secrets.token_bytes(16)

    password_hash = _derive_password_hash(
        password,
        salt,
    )

    created_at = datetime.now().isoformat(
        timespec="seconds"
    )

    try:
        with get_connection() as connection:
            cursor = connection.execute(
                """
                INSERT INTO users (
                    username,
                    display_name,
                    password_hash,
                    password_salt,
                    role,
                    status,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, 'active', ?)
                """,
                (
                    username,
                    display_name,
                    password_hash,
                    salt.hex(),
                    role,
                    created_at,
                ),
            )

            return int(cursor.lastrowid)

    except sqlite3.IntegrityError as error:
        raise ValueError(
            f"用户名 {username} 已经存在"
        ) from error


def authenticate_user(
    username: str,
    password: str,
) -> dict | None:
    """
    验证用户名和密码。

    验证成功返回用户字典；
    验证失败返回None。
    """

    username = normalize_username(username)

    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT
                id,
                username,
                display_name,
                password_hash,
                password_salt,
                role,
                status,
                created_at
            FROM users
            WHERE username = ?
            """,
            (username,),
        ).fetchone()

    if row is None:
        return None

    if row["status"] != "active":
        return None

    salt = bytes.fromhex(
        row["password_salt"]
    )

    candidate_hash = _derive_password_hash(
        password,
        salt,
    )

    if not hmac.compare_digest(
        candidate_hash,
        row["password_hash"],
    ):
        return None

    # 不把密码哈希和盐值返回给页面
    return {
        "id": row["id"],
        "username": row["username"],
        "display_name": row["display_name"],
        "role": row["role"],
        "status": row["status"],
        "created_at": row["created_at"],
    }


def list_users() -> list[dict]:
    """
    返回用户列表，不包含密码信息。
    """

    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                id,
                username,
                display_name,
                role,
                status,
                created_at
            FROM users
            ORDER BY id
            """
        ).fetchall()

    return [
        dict(row)
        for row in rows
    ]


def set_user_status(
    user_id: int,
    status: str,
) -> None:
    """
    启用或禁用用户。
    """

    if status not in {"active", "disabled"}:
        raise ValueError(
            "用户状态只能是active或disabled"
        )

    with get_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE users
            SET status = ?
            WHERE id = ?
            """,
            (
                status,
                user_id,
            ),
        )

        if cursor.rowcount == 0:
            raise ValueError(
                f"没有找到ID为{user_id}的用户"
            )