from flask import Flask, request, redirect, url_for, render_template_string, flash, abort
import sqlite3
from contextlib import closing
from datetime import datetime
import os

app = Flask(__name__)
app.secret_key = "change-this-secret-key"

DB_PATH = "reservations.db"
ADMIN_KEY = "pasta333"


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with closing(get_db()) as conn:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS reservations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id TEXT NOT NULL,
                seat_position TEXT NOT NULL,
                request_type TEXT NOT NULL CHECK(request_type IN ('question', 'submission')),
                status TEXT NOT NULL CHECK(status IN ('waiting', 'cancelled', 'completed')),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        cur.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_waiting_student
            ON reservations(student_id)
            WHERE status = 'waiting'
        """)
        cur.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_waiting_seat
            ON reservations(seat_position)
            WHERE status = 'waiting'
        """)
        conn.commit()


@app.before_request
def setup():
    init_db()


def get_waiting_reservations():
    with closing(get_db()) as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, student_id, seat_position, request_type, status, created_at
            FROM reservations
            WHERE status = 'waiting'
            ORDER BY datetime(created_at) ASC, id ASC
        """)
        return cur.fetchall()


def get_my_waiting_reservation(student_id):
    with closing(get_db()) as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, student_id, seat_position, request_type, status, created_at
            FROM reservations
            WHERE student_id = ? AND status = 'waiting'
            ORDER BY datetime(created_at) ASC, id ASC
            LIMIT 1
        """, (student_id,))
        return cur.fetchone()


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        student_id = request.form.get("student_id", "").strip()
        seat_position = request.form.get("seat_position", "").strip()
        request_type = request.form.get("request_type", "").strip()

        if not student_id:
            flash("学生番号を入力してください。")
            return redirect(url_for("index"))

        if not seat_position:
            flash("席番号を入力してください。")
            return redirect(url_for("index"))

        if request_type not in ("question", "submission"):
            flash("予約内容を選択してください。")
            return redirect(url_for("index"))

        now = datetime.now().isoformat(timespec="seconds")

        try:
            with closing(get_db()) as conn:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO reservations(
                        student_id, seat_position, request_type, status, created_at, updated_at
                    )
                    VALUES (?, ?, ?, 'waiting', ?, ?)
                """, (student_id, seat_position, request_type, now, now))
                conn.commit()
            flash("予約を受け付けました。")
            return redirect(url_for("index", student_id=student_id))
        except sqlite3.IntegrityError:
            my_reservation = get_my_waiting_reservation(student_id)
            if my_reservation is not None:
                flash("この学生番号では既に予約中です。多重予約はできません。")
            else:
                flash("その席は既に予約されています。")
            return redirect(url_for("index", student_id=student_id))

    student_id = request.args.get("student_id", "").strip()
    waiting = get_waiting_reservations()
    my_reservation = get_my_waiting_reservation(student_id) if student_id else None

    my_position = None
    if my_reservation is not None:
        for i, row in enumerate(waiting, start=1):
            if row["id"] == my_reservation["id"]:
                my_position = i
                break

    return render_template_string(
        STUDENT_TEMPLATE,
        waiting=waiting,
        student_id=student_id,
        my_reservation=my_reservation,
        my_position=my_position
    )


@app.route("/cancel/<int:reservation_id>", methods=["POST"])
def cancel_reservation(reservation_id):
    student_id = request.form.get("student_id", "").strip()
    if not student_id:
        flash("キャンセルには学生番号が必要です。")
        return redirect(url_for("index"))

    now = datetime.now().isoformat(timespec="seconds")

    with closing(get_db()) as conn:
        cur = conn.cursor()
        cur.execute("""
            UPDATE reservations
            SET status = 'cancelled', updated_at = ?
            WHERE id = ? AND student_id = ? AND status = 'waiting'
        """, (now, reservation_id, student_id))
        conn.commit()

        if cur.rowcount == 0:
            flash("キャンセルできませんでした。学生番号または予約状態を確認してください。")
        else:
            flash("予約をキャンセルしました。")

    return redirect(url_for("index", student_id=student_id))


@app.route("/admin")
def admin():
    key = request.args.get("key", "")
    if key != ADMIN_KEY:
        abort(403)

    waiting = get_waiting_reservations()
    return render_template_string(ADMIN_TEMPLATE, waiting=waiting, admin_key=key)


@app.route("/complete/<int:reservation_id>", methods=["POST"])
def complete_reservation(reservation_id):
    key = request.form.get("key", "")
    if key != ADMIN_KEY:
        abort(403)

    now = datetime.now().isoformat(timespec="seconds")

    with closing(get_db()) as conn:
        cur = conn.cursor()
        cur.execute("""
            UPDATE reservations
            SET status = 'completed', updated_at = ?
            WHERE id = ? AND status = 'waiting'
        """, (now, reservation_id))
        conn.commit()

    return redirect(url_for("admin", key=key))


STUDENT_TEMPLATE = """
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <title>順番取りシステム</title>
    <style>
        body {
            font-family: sans-serif;
            margin: 2rem auto;
            max-width: 900px;
            line-height: 1.6;
        }
        h1, h2 { margin-bottom: 0.5rem; }
        form, .box {
            border: 1px solid #ccc;
            padding: 1rem;
            margin-bottom: 1.5rem;
            border-radius: 8px;
        }
        label {
            display: block;
            margin-top: 0.5rem;
            font-weight: bold;
        }
        input, button {
            margin-top: 0.3rem;
            padding: 0.5rem;
            font-size: 1rem;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 0.8rem;
        }
        th, td {
            border: 1px solid #ccc;
            padding: 0.6rem;
            text-align: center;
        }
        .flash {
            background: #f5f5cc;
            border: 1px solid #d8d88a;
            padding: 0.8rem;
            margin-bottom: 1rem;
            border-radius: 6px;
        }
        .note {
            color: #555;
            font-size: 0.95rem;
        }
        .danger {
            background: #b00020;
            color: white;
            border: none;
            border-radius: 6px;
            cursor: pointer;
        }
        .primary {
            background: #1565c0;
            color: white;
            border: none;
            border-radius: 6px;
            cursor: pointer;
        }
        .inline-label {
            display: inline;
            font-weight: normal;
            margin-right: 1rem;
        }
    </style>
</head>
<body>
    <h1>順番取りシステム</h1>
    <p class="note">学生番号、席番号、予約内容を入力して予約してください。</p>

    {% with messages = get_flashed_messages() %}
      {% if messages %}
        {% for msg in messages %}
          <div class="flash">{{ msg }}</div>
        {% endfor %}
      {% endif %}
    {% endwith %}

    <form method="POST" action="/">
        <label for="student_id">学生番号</label>
        <input type="text" id="student_id" name="student_id" value="{{ student_id }}" required>

        <label for="seat_position">席番号</label>
        <input type="text" id="seat_position" name="seat_position" placeholder="例: A-3" required>
        <p class="note">席番号は A-3 のような形式で入力してください。</p>

        <label>予約内容</label>
        <div style="margin-top: 0.5rem;">
            <label class="inline-label">
                <input type="radio" name="request_type" value="question" required>
                質問
            </label>
            <label class="inline-label">
                <input type="radio" name="request_type" value="submission" required>
                提出・確認
            </label>
        </div>

        <div style="margin-top: 1rem;">
            <button class="primary" type="submit">予約する</button>
        </div>
    </form>

    {% if my_reservation %}
    <div class="box">
        <h2>自分の予約</h2>
        <p>席番号: <strong>{{ my_reservation["seat_position"] }}</strong></p>
        <p>予約内容:
            <strong>
            {% if my_reservation["request_type"] == "question" %}
                質問
            {% else %}
                提出・確認
            {% endif %}
            </strong>
        </p>
        <p>現在の順番: <strong>{{ my_position }}</strong> 番目</p>
        <p>受付時刻: {{ my_reservation["created_at"] }}</p>

        <form method="POST" action="{{ url_for('cancel_reservation', reservation_id=my_reservation['id']) }}">
            <input type="hidden" name="student_id" value="{{ student_id }}">
            <button class="danger" type="submit">キャンセルする</button>
        </form>
    </div>
    {% endif %}

    <div class="box">
        <h2>現在の予約一覧</h2>
        {% if waiting %}
        <table>
            <thead>
                <tr>
                    <th>順番</th>
                    <th>席番号</th>
                    <th>予約内容</th>
                    <th>受付時刻</th>
                </tr>
            </thead>
            <tbody>
                {% for row in waiting %}
                <tr>
                    <td>{{ loop.index }}</td>
                    <td>{{ row["seat_position"] }}</td>
                    <td>
                        {% if row["request_type"] == "question" %}
                            質問
                        {% else %}
                            提出・確認
                        {% endif %}
                    </td>
                    <td>{{ row["created_at"] }}</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
        {% else %}
        <p>現在、予約はありません。</p>
        {% endif %}
    </div>
</body>
</html>
"""

ADMIN_TEMPLATE = """
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <title>運営管理画面</title>
    <style>
        body {
            font-family: sans-serif;
            margin: 2rem auto;
            max-width: 1000px;
            line-height: 1.6;
        }
        h1 { margin-bottom: 1rem; }
        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 1rem;
        }
        th, td {
            border: 1px solid #ccc;
            padding: 0.7rem;
            text-align: center;
        }
        button {
            padding: 0.45rem 0.8rem;
            border: none;
            border-radius: 6px;
            background: #2e7d32;
            color: white;
            cursor: pointer;
        }
        .topbar {
            margin-bottom: 1rem;
        }
        .note {
            color: #555;
        }
    </style>
</head>
<body>
    <h1>運営管理画面</h1>
    <div class="topbar">
        <a href="{{ url_for('admin', key=admin_key) }}">更新</a>
        <span class="note">未完了の予約を受付順に表示しています。</span>
    </div>

    {% if waiting %}
    <table>
        <thead>
            <tr>
                <th>順番</th>
                <th>学生番号</th>
                <th>席番号</th>
                <th>予約内容</th>
                <th>受付時刻</th>
                <th>操作</th>
            </tr>
        </thead>
        <tbody>
            {% for row in waiting %}
            <tr>
                <td>{{ loop.index }}</td>
                <td>{{ row["student_id"] }}</td>
                <td>{{ row["seat_position"] }}</td>
                <td>
                    {% if row["request_type"] == "question" %}
                        質問
                    {% else %}
                        提出・確認
                    {% endif %}
                </td>
                <td>{{ row["created_at"] }}</td>
                <td>
                    <form method="POST" action="{{ url_for('complete_reservation', reservation_id=row['id']) }}">
                        <input type="hidden" name="key" value="{{ admin_key }}">
                        <button type="submit">完了</button>
                    </form>
                </td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
    {% else %}
    <p>現在、未完了の予約はありません。</p>
    {% endif %}
</body>
</html>
"""


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)