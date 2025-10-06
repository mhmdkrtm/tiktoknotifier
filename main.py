stop_tasks()
        
    while True:
        try:
            await client.start()
        except AttributeError as e:
            if "ping_loop" in str(e):
                print(f"[ℹ️] Swallowed ping_loop bug for @{username}")
                await asyncio.sleep(CHECK_OFFLINE)
                continue
            else:
                print(f"[!] @{username} AttributeError: {e}")
                stop_tasks()
                await asyncio.sleep(CHECK_OFFLINE)
        except Exception as e:
            err = str(e).lower()
            if "rate_limit" in err:
                print(f"[!] @{username} hit rate limit — waiting 5 min.")
                stop_tasks()
                await asyncio.sleep(300)
            elif "userofflineerror" in err:
                print(f"[ℹ️] @{username} offline — retry in {CHECK_OFFLINE}s.")
                stop_tasks()
                await asyncio.sleep(CHECK_OFFLINE)
            elif "one connection per client" in err:
                print(f"[ℹ️] @{username} already connected — skipping duplicate.")
                await asyncio.sleep(CHECK_OFFLINE)
            else:
                print(f"[!] @{username} error:", e)
                stop_tasks()
                await asyncio.sleep(CHECK_OFFLINE)

async def main():
    # Final check for required variables
    if not all([TG_API_ID, TG_API_HASH, TG_BOT_TOKEN, MY_USER_ID]):
        print("❌ FATAL: One or more Telegram credentials are missing. Please fill in the variables in Section 1.")
        return
        
    if not os.path.exists(USERS_FILE):
        print("❌ users.txt not found. Please create a file with one username per line.")
        return
        
    os.makedirs('./temp', exist_ok=True)
    
    with open(USERS_FILE) as f:
        users = [u.strip() for u in f if u.strip() and not u.startswith('#')]
    
    if not users:
        print("❌ users.txt is empty. Add TikTok usernames.")
        return

    print(f"🔥 Monitoring {len(users)} TikTok users…")
    
    await asyncio.gather(*(watch_user(u) for u in users))

if name == "main":
    def handle_sigterm(*args):
        print("\nSIGTERM received, shutting down...")
        
    signal.signal(signal.SIGTERM, handle_sigterm)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nProgram interrupted by user.")
    except Exception as e:
        print(f"Unhandled fatal error: {e}")
