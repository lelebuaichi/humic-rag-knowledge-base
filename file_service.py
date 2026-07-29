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
    将上传的原始PDF或TXT保存到data/uploads。

    实际文件名使用MD5，避免：
    1. 不同用户上传同名文件；
    2. 原始文件名包含特殊字符；
    3. 同一个文件被重复保存。
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

    stored_path = (
        UPLOADS_DIRECTORY
        / f"{file_md5}{suffix}"
    )

    # 相同MD5文件已存在时，不重复写入磁盘
    if stored_path.exists():
        return str(stored_path)

    # 先写临时文件，完成后再替换，
    # 避免写入中断后留下不完整文件
    temporary_path = stored_path.with_name(
        f"{stored_path.name}.tmp"
    )

    temporary_path.write_bytes(
        file_bytes
    )

    temporary_path.replace(
        stored_path
    )

    return str(stored_path)


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