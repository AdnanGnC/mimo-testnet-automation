"""
Analyze MiMo token usage from SQLite tracker DB.

Usage:
    python scripts/analyze_token_usage.py
    python scripts/analyze_token_usage.py --since 2026-05-01
"""

import argparse
import sqlite3
import sys
from datetime import datetime
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Analyze MiMo token usage")
    parser.add_argument("--db", default="logs/token_tracker.db", help="SQLite DB path")
    parser.add_argument("--since", help="Filter from date (YYYY-MM-DD)")
    parser.add_argument("--task-type", help="Filter by task type")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"❌ Token tracker DB not found: {db_path}")
        sys.exit(1)

    conn = sqlite3.connect(db_path)

    where = []
    params = []
    if args.since:
        where.append("timestamp >= ?")
        params.append(args.since)
    if args.task_type:
        where.append("task_type = ?")
        params.append(args.task_type)
    where_clause = "WHERE " + " AND ".join(where) if where else ""

    # Total summary
    cursor = conn.execute(
        f"""SELECT 
            COUNT(*) as calls,
            SUM(prompt_tokens),
            SUM(completion_tokens),
            SUM(total_tokens),
            AVG(latency_ms),
            MIN(timestamp),
            MAX(timestamp)
        FROM token_usage {where_clause}""",
        params,
    )
    row = cursor.fetchone()
    if not row[0]:
        print("No usage data found.")
        return

    print("\n" + "=" * 60)
    print("📊 MiMo Token Usage Summary")
    print("=" * 60)
    print(f"  Period:          {row[5]} → {row[6]}")
    print(f"  Total API calls: {row[0]:,}")
    print(f"  Prompt tokens:   {row[1]:,}")
    print(f"  Completion tok:  {row[2]:,}")
    print(f"  TOTAL tokens:    {row[3]:,}")
    print(f"  Avg latency:     {row[4]:,.1f}ms")

    # Per task type
    cursor = conn.execute(
        f"""SELECT 
            task_type,
            COUNT(*) as calls,
            SUM(total_tokens) as total,
            AVG(latency_ms) as avg_lat,
            AVG(total_tokens) as avg_tok
        FROM token_usage {where_clause}
        GROUP BY task_type
        ORDER BY total DESC""",
        params,
    )
    print(f"\n📈 Breakdown by task type:")
    print(f"  {'Task':<20} {'Calls':>8} {'Total Tokens':>15} {'Avg Tokens':>12} {'Avg Latency':>12}")
    print(f"  {'-'*20} {'-'*8} {'-'*15} {'-'*12} {'-'*12}")
    for r in cursor:
        print(f"  {r[0]:<20} {r[1]:>8,} {r[2]:>15,} {r[3]:>12,.0f} {r[4]:>11,.0f}ms")

    # Per day
    cursor = conn.execute(
        f"""SELECT 
            substr(timestamp, 1, 10) as day,
            COUNT(*) as calls,
            SUM(total_tokens) as total
        FROM token_usage {where_clause}
        GROUP BY day
        ORDER BY day DESC
        LIMIT 14""",
        params,
    )
    print(f"\n📅 Last 14 days:")
    print(f"  {'Date':<12} {'Calls':>8} {'Tokens':>12}")
    print(f"  {'-'*12} {'-'*8} {'-'*12}")
    for r in cursor:
        print(f"  {r[0]:<12} {r[1]:>8,} {r[2]:>12,}")

    conn.close()


if __name__ == "__main__":
    main()
