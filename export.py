#!/usr/bin/env python3
import os
import re
import sys
import time
import argparse
from datetime import datetime, timedelta
from pathlib import Path

# Parse --help early to avoid Slack API calls
if "--help" in sys.argv or "-h" in sys.argv:
    parser = argparse.ArgumentParser()
    parser.add_argument("--channels", type=str)
    parser.add_argument("--start", type=str)
    parser.add_argument("--end", type=str)
    parser.add_argument("--thread-sleep", type=float, default=0.5)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--all-channels", action="store_true")
    parser.add_argument("--all-dms", action="store_true")
    parser.add_argument("--save-unresolved", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.print_help()
    sys.exit(0)

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from tqdm import tqdm

SLACK_TOKEN = os.getenv("SLACK_TOKEN")
if not SLACK_TOKEN:
    print("❌ SLACK_TOKEN environment variable is not set.")
    sys.exit(1)

client = WebClient(token=SLACK_TOKEN)

# ------------------------------------------------------------------------------
def fmt_ts(ts: str) -> str:
    return datetime.fromtimestamp(float(ts)).strftime("%Y-%m-%d %H:%M:%S")

def safe_name(name: str) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in name)

def resolve_text(txt, user_map, group_map):
    txt = re.sub(r"<@([UW][A-Z0-9]+)>", lambda m: f"@{user_map.get(m.group(1), m.group(1))}", txt)
    txt = re.sub(r"<(U[A-Z0-9]+)>", lambda m: f"<{user_map.get(m.group(1), m.group(1))}>", txt)
    txt = re.sub(r"<!subteam\^([A-Z0-9]+)>", lambda m: f"@{group_map.get(m.group(1), m.group(1))}", txt)
    return txt

def fetch_user_map():
    m, cursor, backoff = {}, None, 10
    while True:
        try:
            r = client.users_list(cursor=cursor)
            for u in r["members"]:
                m[u["id"]] = u.get("real_name") or u.get("name") or u["id"]
            cursor = r.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break
            backoff = 10
        except SlackApiError as e:
            if e.response["error"] == "ratelimited":
                wait = int(e.response.headers.get("Retry-After", backoff))
                print(f"⏳ users.list rate-limited, sleeping {wait}s …")
                time.sleep(wait)
                backoff = min(backoff * 2, 120)
            else:
                print("⚠️ users.list failed:", e)
                break
    return m

def fetch_group_map():
    try:
        r = client.usergroups_list()
        return {g["id"]: (g.get("name") or g.get("handle") or g["id"]) for g in r["usergroups"]}
    except SlackApiError:
        return {}

def fetch_all_channels(types="public_channel,private_channel,im,mpim"):
    channels, cursor = [], None
    while True:
        r = client.conversations_list(types=types, limit=200, cursor=cursor)
        channels.extend(r["channels"])
        cursor = r.get("response_metadata", {}).get("next_cursor")
        if not cursor:
            break
    return channels

def label_for_channel(ch, user_map):
    if ch.get("is_im"):
        return f"DM with {user_map.get(ch.get('user'), ch['id'])}"
    return ch.get("name", f"channel_{ch['id']}")

def resolve_selection(channels, selection, user_map):
    idx_map = {str(i): ch for i, ch in enumerate(channels)}
    label_map = {label_for_channel(ch, user_map).lower(): ch for ch in channels}
    selected = []
    for token in selection.split(","):
        key = token.strip().lower()
        ch = idx_map.get(key) or label_map.get(key)
        if ch:
            selected.append(ch)
        else:
            print(f"⚠️ Not found: {token}")
    return selected

# ------------------------------------------------------------------------------
def fetch_thread(channel_id, parent_ts, index, total, thread_sleep, verbose):
    replies, cursor = [], None
    while True:
        try:
            if verbose:
                print(f"🔄 Fetching thread replies for parent_ts={parent_ts}")
            r = client.conversations_replies(channel=channel_id, ts=parent_ts, cursor=cursor, limit=100)
            replies.extend(r.get("messages", [])[1:])
            cursor = r.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break
            time.sleep(thread_sleep)
        except SlackApiError as e:
            if e.response["error"] == "ratelimited":
                wait = int(e.response.headers.get("Retry-After", 30))
                print(f"⏳ Rate-limited on thread {index}/{total}, sleeping {wait}s …")
                time.sleep(wait)
            else:
                print("⚠️ conversations.replies failed:", e)
                break
    return replies

def fetch_channel_structured(ch_id, start_ts, end_ts, thread_sleep, verbose):
    cursor = None
    tops, threads = [], {}
    while True:
        try:
            r = client.conversations_history(channel=ch_id, cursor=cursor, limit=200, oldest=start_ts, latest=end_ts)
            for m in r["messages"]:
                if "subtype" in m and m["subtype"] != "thread_broadcast":
                    continue
                tsf = float(m["ts"])
                if start_ts <= tsf <= end_ts:
                    tops.append(m)
                    if "thread_ts" in m and m["ts"] == m["thread_ts"]:
                        threads[m["ts"]] = []
            cursor = r.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break
        except SlackApiError as e:
            if e.response["error"] == "ratelimited":
                wait = int(e.response.headers.get("Retry-After", 30))
                print(f"⏳ Rate-limited on history, sleeping {wait}s …")
                time.sleep(wait)
            else:
                print("⚠️ conversations.history failed:", e)
                break
        time.sleep(1)
    for idx, ts in enumerate(threads, 1):
        threads[ts] = fetch_thread(ch_id, ts, idx, len(threads), thread_sleep, verbose)
    return tops, threads

# ------------------------------------------------------------------------------
def write_channel(messages, threads, out_path: Path, resolve, user_map, group_map):
    with out_path.open("w") as f:
        for m in sorted(messages, key=lambda x: float(x["ts"])):
            text = m.get("text", "")
            if resolve:
                text = resolve_text(text, user_map, group_map)
            f.write(f"[{fmt_ts(m['ts'])}] <{user_map.get(m.get('user'), 'unknown')}> {text}\n\n")
            if "thread_ts" in m and m["ts"] == m["thread_ts"]:
                for r in sorted(threads.get(m["ts"], []), key=lambda x: float(x["ts"])):
                    rtext = resolve_text(r.get("text", ""), user_map, group_map) if resolve else r.get("text", "")
                    f.write(f"    ↳ [{fmt_ts(r['ts'])}] <{user_map.get(r.get('user'), 'unknown')}> {rtext}\n\n")

# ------------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--channels", type=str)
    parser.add_argument("--start", type=str)
    parser.add_argument("--end", type=str)
    parser.add_argument("--thread-sleep", type=float, default=0.5)
    parser.add_argument("--all", action="store_true", help="Export all channels and DMs")
    parser.add_argument("--all-channels", action="store_true", help="Export all public/private channels")
    parser.add_argument("--all-dms", action="store_true", help="Export all direct messages")
    parser.add_argument("--save-unresolved", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    print("🔐 Authenticated.")
    user_map = fetch_user_map()
    group_map = fetch_group_map()
    all_channels = fetch_all_channels()
    selected = []

    if args.all:
        selected = all_channels
    elif args.all_channels:
        selected = [c for c in all_channels if not c.get("is_im")]
    elif args.all_dms:
        selected = [c for c in all_channels if c.get("is_im")]
    elif args.channels:
        selected = resolve_selection(all_channels, args.channels, user_map)
    else:
        print("\n📋 Available channels:")
        for i, ch in enumerate(all_channels):
            print(f"{i:3}: {label_for_channel(ch, user_map)}")
        chan_input = input("Enter channel indexes or names (comma-separated) [Enter = ALL]: ").strip()
        if not chan_input:
            selected = all_channels
        else:
            selected = resolve_selection(all_channels, chan_input, user_map)

    DATE_FMT = "%Y-%m-%d"
    start_str = args.start or input("📆 Start date? [default: 2000-01-01]: ") or "2000-01-01"
    end_str = args.end or input("📆 End date? [default: today]: ") or (datetime.now() + timedelta(days=1)).strftime(DATE_FMT)
    start_ts = int(time.mktime(datetime.strptime(start_str, DATE_FMT).timetuple()))
    end_ts = int(time.mktime(datetime.strptime(end_str, DATE_FMT).timetuple())) + 86399

    out_dir = Path(f"output-{datetime.now().strftime('%Y-%m-%d-%H-%M')}")
    out_dir.mkdir(exist_ok=True)
    unresolved_dir = None
    if args.save_unresolved:
        unresolved_dir = Path(f"{out_dir}-unresolved")
        unresolved_dir.mkdir(exist_ok=True)

    for ch in tqdm(selected, desc="📥 Exporting", unit="channel"):
        label = label_for_channel(ch, user_map)
        print(f"\n📁 Exporting: {label}")
        tops, threads = fetch_channel_structured(ch["id"], start_ts, end_ts, args.thread_sleep, args.verbose)
        base = f"dm-{safe_name(user_map.get(ch.get('user'), ch['id']))}" if ch.get("is_im") else safe_name(ch.get("name", ch["id"]))
        write_channel(tops, threads, out_dir / f"{base}.txt", True, user_map, group_map)
        if unresolved_dir:
            write_channel(tops, threads, unresolved_dir / f"{base}.txt", False, user_map, group_map)

    print(f"\n✅ Done! Exported to: {out_dir}")
    if unresolved_dir:
        print(f"🗃 Raw unresolved files saved to: {unresolved_dir}")

if __name__ == "__main__":
    main()
