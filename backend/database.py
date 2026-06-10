"""
探店地图 - 数据库层
SQLite 数据库初始化 + CRUD 操作
"""

import sqlite3
import json
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'tandian.db')


def get_db():
    """获取数据库连接"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """初始化数据库表"""
    conn = get_db()
    cursor = conn.cursor()

    cursor.executescript('''
        -- 博主表
        CREATE TABLE IF NOT EXISTS bloggers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            platform TEXT NOT NULL DEFAULT 'bilibili',
            platform_uid TEXT NOT NULL UNIQUE,
            avatar TEXT DEFAULT '',
            followers TEXT DEFAULT '',
            bio TEXT DEFAULT '',
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- 视频表
        CREATE TABLE IF NOT EXISTS videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            blogger_id INTEGER NOT NULL,
            platform_video_id TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            cover_url TEXT DEFAULT '',
            tags TEXT DEFAULT '[]',
            publish_date TEXT DEFAULT '',
            url TEXT DEFAULT '',
            duration TEXT DEFAULT '',
            play_count TEXT DEFAULT '',
            status TEXT DEFAULT 'new',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (blogger_id) REFERENCES bloggers(id) ON DELETE CASCADE,
            UNIQUE(blogger_id, platform_video_id)
        );

        -- 店铺表（AI分析提取的结果）
        CREATE TABLE IF NOT EXISTS stores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT DEFAULT '',
            lat REAL DEFAULT 0,
            lng REAL DEFAULT 0,
            address TEXT DEFAULT '',
            avg_price REAL DEFAULT 0,
            rating REAL DEFAULT 0,
            recommend_dishes TEXT DEFAULT '[]',
            tags TEXT DEFAULT '[]',
            note TEXT DEFAULT '',
            source_video_id INTEGER,
            source_blogger_id INTEGER,
            confidence REAL DEFAULT 0,
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (source_video_id) REFERENCES videos(id),
            FOREIGN KEY (source_blogger_id) REFERENCES bloggers(id)
        );

        -- AI分析记录
        CREATE TABLE IF NOT EXISTS analysis_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id INTEGER NOT NULL,
            model_name TEXT DEFAULT '',
            prompt_tokens INTEGER DEFAULT 0,
            completion_tokens INTEGER DEFAULT 0,
            raw_response TEXT DEFAULT '',
            extracted_data TEXT DEFAULT '{}',
            store_ids TEXT DEFAULT '[]',
            success BOOLEAN DEFAULT 0,
            error_message TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (video_id) REFERENCES videos(id) ON DELETE CASCADE
        );

        -- AI分析步骤记录（用于后台可观测时间线）
        CREATE TABLE IF NOT EXISTS analysis_steps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id INTEGER NOT NULL,
            analysis_log_id INTEGER,
            run_id TEXT DEFAULT '',
            step_name TEXT NOT NULL,
            status TEXT DEFAULT 'running',
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            ended_at TIMESTAMP,
            duration_ms INTEGER DEFAULT 0,
            input_summary TEXT DEFAULT '',
            output_summary TEXT DEFAULT '',
            error_message TEXT DEFAULT '',
            metadata_json TEXT DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (video_id) REFERENCES videos(id) ON DELETE CASCADE,
            FOREIGN KEY (analysis_log_id) REFERENCES analysis_logs(id) ON DELETE SET NULL
        );

        -- 索引
        CREATE INDEX IF NOT EXISTS idx_videos_blogger ON videos(blogger_id);
        CREATE INDEX IF NOT EXISTS idx_videos_status ON videos(status);
        CREATE INDEX IF NOT EXISTS idx_stores_category ON stores(category);
        CREATE INDEX IF NOT EXISTS idx_stores_source ON stores(source_video_id);
        CREATE INDEX IF NOT EXISTS idx_analysis_video ON analysis_logs(video_id);
        CREATE INDEX IF NOT EXISTS idx_analysis_steps_video ON analysis_steps(video_id);
        CREATE INDEX IF NOT EXISTS idx_analysis_steps_log ON analysis_steps(analysis_log_id);
        CREATE INDEX IF NOT EXISTS idx_analysis_steps_run ON analysis_steps(run_id);
    ''')

    conn.commit()
    conn.close()


# ==================== Blogger CRUD ====================

def add_blogger(name, platform_uid, platform='bilibili', avatar='', followers='', bio=''):
    conn = get_db()
    try:
        conn.execute(
            """INSERT INTO bloggers (name, platform, platform_uid, avatar, followers, bio)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (name, platform, platform_uid, avatar, followers, bio)
        )
        conn.commit()
        return conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()


def get_all_bloggers():
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM bloggers WHERE status='active' ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_blogger(blogger_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM bloggers WHERE id=?", (blogger_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def delete_blogger(blogger_id):
    conn = get_db()
    conn.execute("UPDATE bloggers SET status='deleted' WHERE id=?", (blogger_id,))
    conn.commit()
    conn.close()


# ==================== Video CRUD ====================

def add_videos_batch(blogger_id, video_list):
    """批量插入视频，跳过已存在的"""
    conn = get_db()
    added = 0
    for v in video_list:
        try:
            cursor = conn.execute(
                """INSERT OR IGNORE INTO videos
                   (blogger_id, platform_video_id, title, description, cover_url, tags,
                    publish_date, url, duration, play_count)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    blogger_id,
                    v['platform_video_id'],
                    v['title'],
                    v.get('description', ''),
                    v.get('cover_url', ''),
                    json.dumps(v.get('tags', []), ensure_ascii=False),
                    v.get('publish_date', ''),
                    v.get('url', ''),
                    v.get('duration', ''),
                    v.get('play_count', ''),
                )
            )
            if cursor.rowcount > 0:
                added += 1
        except Exception:
            continue
    conn.commit()
    conn.close()
    return added


def _video_filters_sql(blogger_id=None, status=None, keyword=''):
    query = " WHERE 1=1"
    params = []
    if blogger_id:
        query += " AND v.blogger_id=?"
        params.append(blogger_id)
    if status:
        query += " AND v.status=?"
        params.append(status)
    keyword = (keyword or '').strip()
    if keyword:
        like = f"%{keyword}%"
        query += """ AND (
            v.title LIKE ?
            OR v.platform_video_id LIKE ?
            OR v.publish_date LIKE ?
            OR v.play_count LIKE ?
            OR b.name LIKE ?
        )"""
        params.extend([like, like, like, like, like])
    return query, params


def get_videos(blogger_id=None, status=None, limit=50, offset=0, keyword=''):
    conn = get_db()
    query = """SELECT v.*,
                      COALESCE(b.name, '未知博主') as blogger_name,
                      COUNT(CASE WHEN s.status='active' THEN 1 END) as active_store_count
               FROM videos v
               LEFT JOIN bloggers b ON v.blogger_id=b.id
               LEFT JOIN stores s ON s.source_video_id=v.id"""
    where_sql, params = _video_filters_sql(blogger_id=blogger_id, status=status, keyword=keyword)
    query += where_sql
    query += " GROUP BY v.id ORDER BY v.publish_date DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def count_videos(blogger_id=None, status=None, keyword=''):
    conn = get_db()
    query = "SELECT COUNT(*) FROM videos v LEFT JOIN bloggers b ON v.blogger_id=b.id"
    where_sql, params = _video_filters_sql(blogger_id=blogger_id, status=status, keyword=keyword)
    query += where_sql
    total = conn.execute(query, params).fetchone()[0]
    conn.close()
    return total


def get_video(video_id):
    conn = get_db()
    row = conn.execute(
        """SELECT v.*, b.name as blogger_name, b.avatar as blogger_avatar
           FROM videos v JOIN bloggers b ON v.blogger_id=b.id
           WHERE v.id=?""",
        (video_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def update_video_status(video_id, status):
    conn = get_db()
    conn.execute("UPDATE videos SET status=? WHERE id=?", (status, video_id))
    conn.commit()
    conn.close()


# ==================== Store CRUD ====================

def find_store_by_source(video_id, store_name):
    """检查同一视频是否已提取过同名店铺，返回已有记录的 id 或 None"""
    conn = get_db()
    row = conn.execute(
        "SELECT id FROM stores WHERE source_video_id=? AND name=? AND status='active'",
        (video_id, store_name)
    ).fetchone()
    conn.close()
    return row[0] if row else None


def delete_stores_by_video(video_id):
    """删除某视频之前提取的所有店铺（重新分析时先清理旧数据）"""
    conn = get_db()
    conn.execute("UPDATE stores SET status='deleted' WHERE source_video_id=?", (video_id,))
    conn.commit()
    conn.close()


def add_store(store_data):
    conn = get_db()
    cursor = conn.execute(
        """INSERT INTO stores
           (name, category, lat, lng, address, avg_price, rating,
            recommend_dishes, tags, note, source_video_id, source_blogger_id, confidence)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            store_data['name'],
            store_data.get('category', ''),
            store_data.get('lat', 0),
            store_data.get('lng', 0),
            store_data.get('address', ''),
            store_data.get('avg_price', 0),
            store_data.get('rating', 0),
            json.dumps(store_data.get('recommend_dishes', []), ensure_ascii=False),
            json.dumps(store_data.get('tags', []), ensure_ascii=False),
            store_data.get('note', ''),
            store_data.get('source_video_id'),
            store_data.get('source_blogger_id'),
            store_data.get('confidence', 0),
        )
    )
    conn.commit()
    store_id = cursor.lastrowid
    conn.close()
    return store_id


def get_all_stores(category=None):
    conn = get_db()
    query = """SELECT s.*,
                      b.name as blogger_name,
                      b.avatar as blogger_avatar,
                      v.title as source_video_title,
                      v.url as source_video_url,
                      v.platform_video_id as source_video_bvid,
                      v.cover_url as source_video_cover
               FROM stores s
               LEFT JOIN bloggers b ON s.source_blogger_id=b.id
               LEFT JOIN videos v ON s.source_video_id=v.id
               WHERE s.status='active'"""
    params = []
    if category and category != 'all':
        query += " AND s.category=?"
        params.append(category)
    query += " ORDER BY s.rating DESC, s.created_at DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_store(store_id):
    conn = get_db()
    row = conn.execute(
        """SELECT s.*,
                  b.name as blogger_name,
                  b.avatar as blogger_avatar,
                  v.title as source_video_title,
                  v.url as source_video_url,
                  v.platform_video_id as source_video_bvid,
                  v.cover_url as source_video_cover
           FROM stores s
           LEFT JOIN bloggers b ON s.source_blogger_id=b.id
           LEFT JOIN videos v ON s.source_video_id=v.id
           WHERE s.id=?""",
        (store_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def delete_video(video_id):
    conn = get_db()
    conn.execute("DELETE FROM videos WHERE id=?", (video_id,))
    conn.commit()
    conn.close()


def delete_videos_batch(video_ids):
    ids = [int(v) for v in video_ids if str(v).isdigit()]
    if not ids:
        return 0
    conn = get_db()
    placeholders = ','.join(['?'] * len(ids))
    cursor = conn.execute(f"DELETE FROM videos WHERE id IN ({placeholders})", ids)
    deleted = cursor.rowcount if cursor.rowcount is not None else 0
    conn.commit()
    conn.close()
    return deleted


def delete_store(store_id):
    conn = get_db()
    row = conn.execute(
        "SELECT source_video_id FROM stores WHERE id=? AND status='active'",
        (store_id,)
    ).fetchone()
    source_video_id = row['source_video_id'] if row else None
    conn.execute("UPDATE stores SET status='deleted' WHERE id=?", (store_id,))
    active_store_count = None
    if source_video_id:
        active_store_count = conn.execute(
            "SELECT COUNT(*) FROM stores WHERE source_video_id=? AND status='active'",
            (source_video_id,)
        ).fetchone()[0]
        conn.execute(
            "UPDATE videos SET status=? WHERE id=?",
            ('analyzed' if active_store_count else 'no_store', source_video_id)
        )
    conn.commit()
    conn.close()
    return {
        'source_video_id': source_video_id,
        'active_store_count': active_store_count,
    }


def delete_stores_batch(store_ids):
    ids = [int(v) for v in store_ids if str(v).isdigit()]
    if not ids:
        return {'deleted': 0, 'updated_videos': 0}

    conn = get_db()
    placeholders = ','.join(['?'] * len(ids))
    rows = conn.execute(
        f"SELECT DISTINCT source_video_id FROM stores WHERE id IN ({placeholders}) AND status='active'",
        ids
    ).fetchall()
    source_video_ids = [row['source_video_id'] for row in rows if row['source_video_id']]

    cursor = conn.execute(
        f"UPDATE stores SET status='deleted' WHERE id IN ({placeholders}) AND status='active'",
        ids
    )
    deleted = cursor.rowcount if cursor.rowcount is not None else 0

    updated_videos = 0
    for video_id in source_video_ids:
        active_store_count = conn.execute(
            "SELECT COUNT(*) FROM stores WHERE source_video_id=? AND status='active'",
            (video_id,)
        ).fetchone()[0]
        conn.execute(
            "UPDATE videos SET status=? WHERE id=?",
            ('analyzed' if active_store_count else 'no_store', video_id)
        )
        updated_videos += 1

    conn.commit()
    conn.close()
    return {'deleted': deleted, 'updated_videos': updated_videos}


# ==================== Analysis Log ====================

def add_analysis_log(video_id, model_name, raw_response, extracted_data,
                      store_ids, success, error_message='',
                      prompt_tokens=0, completion_tokens=0):
    conn = get_db()
    cursor = conn.execute(
        """INSERT INTO analysis_logs
           (video_id, model_name, prompt_tokens, completion_tokens,
            raw_response, extracted_data, store_ids, success, error_message)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            video_id, model_name, prompt_tokens, completion_tokens,
            raw_response,
            json.dumps(extracted_data, ensure_ascii=False),
            json.dumps(store_ids, ensure_ascii=False),
            1 if success else 0, error_message
        )
    )
    conn.commit()
    log_id = cursor.lastrowid
    conn.close()
    return log_id


def get_analysis_logs(video_id=None, limit=20):
    conn = get_db()
    query = "SELECT * FROM analysis_logs"
    params = []
    if video_id:
        query += " WHERE video_id=?"
        params.append(video_id)
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _json_dumps(value):
    return json.dumps(value or {}, ensure_ascii=False)


def _merge_step_metadata(existing_json, metadata):
    try:
        existing = json.loads(existing_json or '{}')
    except json.JSONDecodeError:
        existing = {}
    existing.update(metadata or {})
    return _json_dumps(existing)


def start_analysis_step(video_id, run_id, step_name, input_summary='', metadata=None):
    conn = get_db()
    cursor = conn.execute(
        """INSERT INTO analysis_steps
           (video_id, run_id, step_name, status, input_summary, metadata_json)
           VALUES (?, ?, ?, 'running', ?, ?)""",
        (video_id, run_id, step_name, input_summary or '', _json_dumps(metadata))
    )
    conn.commit()
    step_id = cursor.lastrowid
    conn.close()
    return step_id


def finish_analysis_step(step_id, status='success', output_summary='',
                         error_message='', metadata=None, duration_ms=None):
    conn = get_db()
    row = conn.execute(
        "SELECT metadata_json FROM analysis_steps WHERE id=?",
        (step_id,)
    ).fetchone()
    if not row:
        conn.close()
        return
    metadata_json = _merge_step_metadata(row['metadata_json'], metadata)
    conn.execute(
        """UPDATE analysis_steps
           SET status=?,
               ended_at=CURRENT_TIMESTAMP,
               duration_ms=?,
               output_summary=?,
               error_message=?,
               metadata_json=?
           WHERE id=?""",
        (status, int(duration_ms or 0), output_summary or '', error_message or '', metadata_json, step_id)
    )
    conn.commit()
    conn.close()


def attach_analysis_steps_to_log(run_id, analysis_log_id):
    conn = get_db()
    conn.execute(
        "UPDATE analysis_steps SET analysis_log_id=? WHERE run_id=?",
        (analysis_log_id, run_id)
    )
    conn.commit()
    conn.close()


def get_analysis_steps(video_id=None, analysis_log_id=None, limit=100):
    conn = get_db()
    query = "SELECT * FROM analysis_steps WHERE 1=1"
    params = []
    if video_id:
        query += " AND video_id=?"
        params.append(video_id)
    if analysis_log_id:
        query += " AND analysis_log_id=?"
        params.append(analysis_log_id)
    query += " ORDER BY id ASC LIMIT ?"
    params.append(limit)
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ==================== Stats ====================

def get_stats():
    conn = get_db()
    total_stores = conn.execute("SELECT COUNT(*) FROM stores WHERE status='active'").fetchone()[0]
    total_bloggers = conn.execute("SELECT COUNT(*) FROM bloggers WHERE status='active'").fetchone()[0]
    total_videos = conn.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
    analyzed = conn.execute("SELECT COUNT(*) FROM videos WHERE status='analyzed'").fetchone()[0]
    categories = conn.execute(
        "SELECT category, COUNT(*) as cnt FROM stores WHERE status='active' GROUP BY category"
    ).fetchall()
    conn.close()
    return {
        'total_stores': total_stores,
        'total_bloggers': total_bloggers,
        'total_videos': total_videos,
        'analyzed_videos': analyzed,
        'pending_videos': total_videos - analyzed,
        'categories': [dict(r) for r in categories],
    }
