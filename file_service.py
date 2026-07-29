import sqlite3
from datetime import datetime
from pathlib import Path

import config_data as config
from database import get_connection


UPLOADS_DIRECTORY = Path(
    config.uploads_directory
)

ALLOWED_SUFFIXES = {
    ".pdf",
    ".txt",
}


def get_file_by_md5(
    file_md5: str,
) -> dict | None:
    """
    根据MD5查询文献记录。
    """

    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT
                files.id,
                files.file_md5,
                files.original_filename,
                files.stored_path,
                files.uploader_id,
                files.upload_time,
                files.chunk_count,
                files.status,
                users.username AS uploader_username,
                users.display_name AS uploader_name
            FROM files
            JOIN users
                ON users.id = files.uploader_id
            WHERE files.file_md5 = ?
            """,
            (file_md5,),
        ).fetchone()

    if row is None:
        return None

    return dict(row)


def save_original_file(
    file_bytes: bytes,
    filename: str,
    file_md5: str,
) -> str:
    """
    保存上传的原始PDF或TXT。

    数据库中只保存相对于项目根目录的路径，
    从而兼容Windows本地环境和Linux容器环境。
    """

    suffix = Path(filename).suffix.lower()

    if suffix not in ALLOWED_SUFFIXES:
        raise ValueError(
            "只支持保存PDF或TXT文件"
        )

    UPLOADS_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    stored_filename = (
        f"{file_md5}{suffix}"
    )

    absolute_path = (
        UPLOADS_DIRECTORY
        / stored_filename
    )

    # 写入数据库的可移植相对路径
    relative_path = (
        Path("data")
        / "uploads"
        / stored_filename
    )

    if absolute_path.exists():
        return relative_path.as_posix()

    temporary_path = absolute_path.with_name(
        f"{absolute_path.name}.tmp"
    )

    temporary_path.write_bytes(
        file_bytes
    )

    temporary_path.replace(
        absolute_path
    )

    return relative_path.as_posix()


def create_file_record(
    file_md5: str,
    original_filename: str,
    stored_path: str,
    uploader_id: int,
) -> int:
    """
    创建正在处理中的文献记录，返回记录ID。
    """

    upload_time = datetime.now().isoformat(
        timespec="seconds"
    )

    try:
        with get_connection() as connection:
            cursor = connection.execute(
                """
                INSERT INTO files (
                    file_md5,
                    original_filename,
                    stored_path,
                    uploader_id,
                    upload_time,
                    chunk_count,
                    status
                )
                VALUES (?, ?, ?, ?, ?, 0, 'processing')
                """,
                (
                    file_md5,
                    original_filename,
                    stored_path,
                    uploader_id,
                    upload_time,
                ),
            )

            return int(cursor.lastrowid)

    except sqlite3.IntegrityError as error:
        raise ValueError(
            "该文献已经存在于共享知识库中"
        ) from error


def mark_file_ready(
    file_id: int,
    chunk_count: int,
) -> None:
    """
    文献成功写入Chroma后，
    将状态更新为ready并记录片段数。
    """

    if chunk_count < 0:
        raise ValueError(
            "知识片段数量不能小于0"
        )

    with get_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE files
            SET
                status = 'ready',
                chunk_count = ?
            WHERE id = ?
            """,
            (
                chunk_count,
                file_id,
            ),
        )

        if cursor.rowcount == 0:
            raise ValueError(
                f"没有找到ID为{file_id}的文献记录"
            )


def mark_file_failed(
    file_id: int,
) -> None:
    """
    文献处理失败时，将状态更新为failed。
    """

    with get_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE files
            SET status = 'failed'
            WHERE id = ?
            """,
            (file_id,),
        )

        if cursor.rowcount == 0:
            raise ValueError(
                f"没有找到ID为{file_id}的文献记录"
            )


def list_file_records() -> list[dict]:
    """
    查询所有文献及上传人信息。
    """

    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                files.id,
                files.file_md5,
                files.original_filename,
                files.stored_path,
                files.upload_time,
                files.chunk_count,
                files.status,
                users.username AS uploader_username,
                users.display_name AS uploader_name
            FROM files
            JOIN users
                ON users.id = files.uploader_id
            ORDER BY files.upload_time DESC
            """
        ).fetchall()

    return [
        dict(row)
        for row in rows
    ]
def get_file_by_id(
    file_id: int,
) -> dict | None:
    """
    根据文献ID查询完整记录。
    """

    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT
                files.id,
                files.file_md5,
                files.original_filename,
                files.stored_path,
                files.uploader_id,
                files.upload_time,
                files.chunk_count,
                files.status,
                users.username AS uploader_username,
                users.display_name AS uploader_name
            FROM files
            JOIN users
                ON users.id = files.uploader_id
            WHERE files.id = ?
            """,
            (file_id,),
        ).fetchone()

    if row is None:
        return None

    return dict(row)


def resolve_stored_path(
    stored_path: str,
) -> Path:
    """
    将数据库中的存储路径转换为当前运行环境下的绝对路径。
    """

    file_path = Path(stored_path)

    # 新版记录保存的是相对路径
    if not file_path.is_absolute():
        file_path = (
            Path(config.BASE_DIR)
            / file_path
        )

    return file_path


def delete_original_file(
    stored_path: str,
) -> None:
    """
    删除保存的原始文件。
    """

    file_path = resolve_stored_path(
        stored_path
    )

    if file_path.exists():
        file_path.unlink()


def remove_legacy_md5(
    file_md5: str,
) -> None:
    """
    从旧版md5.txt中删除指定MD5。

    当前仍保留旧MD5判重逻辑，
    因此删除文献时必须同步删除该记录，
    否则同一文件无法重新上传。
    """

    md5_path = Path(
        config.md5_path
    )

    if not md5_path.exists():
        return

    existing_md5_values = [
        line.strip()
        for line in md5_path.read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]

    remaining_md5_values = [
        value
        for value in existing_md5_values
        if value != file_md5
    ]

    new_content = "\n".join(
        remaining_md5_values
    )

    if new_content:
        new_content += "\n"

    temporary_path = md5_path.with_name(
        f"{md5_path.name}.tmp"
    )

    temporary_path.write_text(
        new_content,
        encoding="utf-8",
    )

    temporary_path.replace(
        md5_path
    )


def delete_file_record(
    file_id: int,
) -> None:
    """
    删除SQLite中的文献记录。
    """

    with get_connection() as connection:
        cursor = connection.execute(
            """
            DELETE FROM files
            WHERE id = ?
            """,
            (file_id,),
        )

        if cursor.rowcount == 0:
            raise ValueError(
                f"没有找到ID为{file_id}的文献记录"
            )