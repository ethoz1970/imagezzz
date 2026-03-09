#!/usr/bin/env python3
"""
One-time migration: JSON files -> SQLite database.

Imports:
  - static/outputs/sessions.json -> gen_sessions table
  - static/outputs/*.json (image metadata) -> images table
  - static/outputs/pro_users.json -> logged for reference (no auto-migration)

Run: python migrate_to_sqlite.py
"""

import os
import json
import glob
import db

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "static", "outputs")
SESSION_FILE = os.path.join(OUTPUT_DIR, "sessions.json")
PRO_USERS_FILE = os.path.join(OUTPUT_DIR, "pro_users.json")

SKIP_FILES = {"sessions.json", "daily_limits.json", "pro_users.json"}


def migrate():
    print("Initializing database...")
    db.init_db()

    # 1. Migrate sessions
    sessions = {}
    if os.path.exists(SESSION_FILE):
        with open(SESSION_FILE, "r") as f:
            sessions = json.load(f)
        print(f"Found {len(sessions)} sessions in sessions.json")

        for sid, sdata in sessions.items():
            db.save_gen_session(
                session_id=sid,
                name=sdata.get("name", "Unnamed Session"),
                tracking_id=sdata.get("tracking_id"),
                public=sdata.get("public", False),
                created_at=sdata.get("created_at", 0),
            )
        print(f"  Migrated {len(sessions)} sessions.")
    else:
        print("No sessions.json found, skipping.")

    # 2. Migrate image metadata
    json_files = glob.glob(os.path.join(OUTPUT_DIR, "*.json"))
    image_count = 0
    orphan_count = 0

    for jpath in json_files:
        fname = os.path.basename(jpath)
        if fname in SKIP_FILES:
            continue

        try:
            with open(jpath, "r") as f:
                meta = json.load(f)
        except Exception as e:
            print(f"  WARNING: Could not read {fname}: {e}")
            continue

        png_filename = fname.replace(".json", ".png")
        png_path = os.path.join(OUTPUT_DIR, png_filename)

        # Skip if the .png doesn't exist (orphan metadata)
        if not os.path.exists(png_path):
            orphan_count += 1
            continue

        session_id = meta.get("session_id")

        # If the image references a session that doesn't exist, create a placeholder
        if session_id and session_id not in sessions:
            db.save_gen_session(
                session_id=session_id,
                name="Recovered Session",
                tracking_id=meta.get("tracking_id"),
                created_at=meta.get("timestamp", 0),
            )
            sessions[session_id] = True  # mark as created

        db.save_image(
            filename=png_filename,
            session_id=session_id,
            tracking_id=meta.get("tracking_id"),
            prompt=meta.get("prompt"),
            original_prompt=meta.get("original_prompt"),
            generation_time=meta.get("generation_time"),
            public=meta.get("public", False),
            created_at=meta.get("timestamp"),
        )
        image_count += 1

    print(f"  Migrated {image_count} images ({orphan_count} orphan metadata files skipped).")

    # 3. Report pro users
    if os.path.exists(PRO_USERS_FILE):
        with open(PRO_USERS_FILE, "r") as f:
            pro_users = json.load(f)
        print(f"\nPro users found ({len(pro_users)}):")
        for tid, info in pro_users.items():
            print(f"  tracking_id: {tid}  granted_at: {info.get('granted_at', '?')}")
        print("  (These are not auto-migrated. Grant tokens manually after users register.)")
    else:
        print("\nNo pro_users.json found.")

    print(f"\nMigration complete! Database at: {db.DB_PATH}")


if __name__ == "__main__":
    migrate()
