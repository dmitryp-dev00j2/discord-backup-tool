import argparse
import sqlite3
import sys
import time
from pathlib import Path
import httpx

def init_db(db_path: Path):
    """Initialize the SQLite database and create the base message tables."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                channel_id TEXT NOT NULL,
                author_id TEXT NOT NULL,
                author_name TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                edited_timestamp TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS attachments (
                id TEXT PRIMARY KEY,
                message_id TEXT NOT NULL,
                filename TEXT NOT NULL,
                url TEXT NOT NULL,
                size INTEGER NOT NULL,
                FOREIGN KEY (message_id) REFERENCES messages (id) ON DELETE CASCADE
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS reactions (
                message_id TEXT NOT NULL,
                emoji_name TEXT,
                emoji_id TEXT,
                count INTEGER NOT NULL,
                PRIMARY KEY (message_id, emoji_name, emoji_id),
                FOREIGN KEY (message_id) REFERENCES messages (id) ON DELETE CASCADE
            )
        """)
    return conn

def fetch_messages_batch(chan_id: str, token: str, before_id: str = None):
    url = f"https://discord.com/api/v9/channels/{chan_id}/messages"
    headers = {"Authorization": token}
    params = {"limit": 100}
    if before_id:
        params["before"] = before_id

    while True:
        resp = httpx.get(url, headers=headers, params=params)
        if resp.status_code == 429:
            # FIXME: Discord sometimes returns a "retry_after" header in seconds but the JSON body
            # has "retry_after" as float seconds. Let's inspect both.
            try:
                retry_after = float(resp.json().get("retry_after", 1.0))
            except (ValueError, KeyError, httpx.ResponseNotRead):
                retry_after = float(resp.headers.get("Retry-After", 1.0))
            print(f"\nRate limited. Sleeping for {retry_after}s...", file=sys.stderr)
            time.sleep(retry_after)
            continue
        elif resp.status_code == 401:
            print("Error: Unauthorized token. Make sure your token is valid.", file=sys.stderr)
            sys.exit(1)
        elif resp.status_code == 403:
            print(f"Error: Missing permissions for channel {chan_id}.", file=sys.stderr)
            sys.exit(1)
        resp.raise_for_status()
        return resp.json()

def save_messages(conn: sqlite3.Connection, messages: list):
    with conn:
        for msg in messages:
            author = msg.get("author", {})
            conn.execute(
                "INSERT OR REPLACE INTO messages VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    msg["id"],
                    msg["channel_id"],
                    author.get("id", "0"),
                    author.get("username", "Unknown"),
                    msg.get("content", ""),
                    msg["timestamp"],
                    msg.get("edited_timestamp")
                )
            )
            for att in msg.get("attachments", []):
                conn.execute(
                    "INSERT OR REPLACE INTO attachments VALUES (?, ?, ?, ?, ?)",
                    (
                        att["id"],
                        msg["id"],
                        att["filename"],
                        att["url"],
                        att["size"]
                    )
                )
            
            # Clear old reaction state to avoid stale count sync
            conn.execute("DELETE FROM reactions WHERE message_id = ?", (msg["id"],))
            for reaction in msg.get("reactions", []):
                emoji = reaction.get("emoji", {})
                conn.execute(
                    "INSERT OR REPLACE INTO reactions VALUES (?, ?, ?, ?)",
                    (
                        msg["id"],
                        emoji.get("name"),
                        emoji.get("id"),
                        reaction.get("count", 0)
                    )
                )

def main():
    parser = argparse.ArgumentParser(
        description="Backup Discord channel history and attachments to a local SQLite database."
    )
    parser.add_argument("--token", required=True, help="Discord user authorization token")
    parser.add_argument("--channel", required=True, help="Discord channel ID to back up")
    parser.add_argument("--db", default="discord_backup.db", help="Path to SQLite database file")
    args = parser.parse_args()

    db_path = Path(args.db)
    conn = init_db(db_path)

    print(f"Starting backup for channel {args.channel}...")
    before_id = None
    total_fetched = 0

    try:
        while True:
            batch = fetch_messages_batch(args.channel, args.token, before_id)
            if not batch:
                break

            save_messages(conn, batch)
            total_fetched += len(batch)
            before_id = batch[-1]["id"]
            # print(f"DEBUG: Fetched {len(batch)} messages, last ID: {before_id}")
            print(f"Saved {total_fetched} messages...", end="\r")
            time.sleep(0.5)

    except httpx.HTTPStatusError as e:
        print(f"\nHTTP error occurred: {e}", file=sys.stderr)
        sys.exit(1)
    except httpx.RequestError as e:
        print(f"\nNetwork error occurred: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"\nBackup complete. Total messages saved: {total_fetched}")

if __name__ == "__main__":
    main()
