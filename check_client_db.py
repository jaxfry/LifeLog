
import sqlite3
import os

DB_PATH = "lifelog_client/lifelog.db"

def check_db():
    if not os.path.exists(DB_PATH):
        print(f"Database not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT count(*) FROM sync_queue")
        count = cursor.fetchone()[0]
        print(f"Items in sync_queue: {count}")
        
        if count > 0:
            cursor.execute("SELECT created_at, extension_id FROM sync_queue ORDER BY created_at DESC LIMIT 5")
            rows = cursor.fetchall()
            print("Latest 5 items:")
            for row in rows:
                print(f"- {row[0]} [{row[1]}]")
                
    except Exception as e:
        print(f"Error reading database: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    check_db()
