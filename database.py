import sqlite3
from pathlib import Path

import config_data as config


DATABASE_PATH = Path(config.database_path)


def get_connection() -> sqlite3.Connection:
    """
    创建并返回SQLite数据库连接。
    """

    # 确保data目录存在
    DATABASE_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    connection = sqlite3.connect(
        DATABASE_PATH
    )

    # 查询结果可以通过字段名访问
    connection.row_factory = sqlite3.Row

    # 开启SQLite外键约束
    connection.execute(
        "PRAGMA foreign_keys = ON;"
    )

    return connection


def init_database() -> None:
    """
    创建用户表和文献表。
    如果表已经存在，则不会重复创建。
    """

    with get_connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                username TEXT NOT NULL UNIQUE,

                display_name TEXT NOT NULL,

                password_hash TEXT NOT NULL,

                password_salt TEXT NOT NULL,

                role TEXT NOT NULL DEFAULT 'member'
                    CHECK (
                        role IN ('admin', 'member')
                    ),

                status TEXT NOT NULL DEFAULT 'active'
                    CHECK (
                        status IN ('active', 'disabled')
                    ),

                created_at TEXT NOT NULL
            );


            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                file_md5 TEXT NOT NULL UNIQUE,

                original_filename TEXT NOT NULL,

                stored_path TEXT NOT NULL,

                uploader_id INTEGER NOT NULL,

                upload_time TEXT NOT NULL,

                chunk_count INTEGER NOT NULL DEFAULT 0,

                status TEXT NOT NULL DEFAULT 'ready'
                    CHECK (
                        status IN (
                            'processing',
                            'ready',
                            'failed'
                        )
                    ),

                FOREIGN KEY (uploader_id)
                    REFERENCES users(id)
                    ON DELETE RESTRICT
            );


            CREATE INDEX IF NOT EXISTS
                idx_files_uploader_id
            ON files(uploader_id);
            
            CREATE TABLE IF NOT EXISTS parent_chunks (
    parent_id TEXT PRIMARY KEY,

    file_id INTEGER NOT NULL,

    parent_index INTEGER NOT NULL,

    page INTEGER,

    section TEXT,

    content_type TEXT NOT NULL DEFAULT 'body',

    content TEXT NOT NULL,

    FOREIGN KEY (file_id)
        REFERENCES files(id)
        ON DELETE CASCADE,

    UNIQUE (
        file_id,
        parent_index
    )
);


CREATE INDEX IF NOT EXISTS
    idx_parent_chunks_file_id
ON parent_chunks(file_id);


CREATE INDEX IF NOT EXISTS
    idx_parent_chunks_parent_index
ON parent_chunks(parent_index);


            CREATE INDEX IF NOT EXISTS
                idx_files_upload_time
            ON files(upload_time);
            """
        )


if __name__ == "__main__":
    init_database()

    print(
        f"数据库初始化完成：{DATABASE_PATH}"
    )