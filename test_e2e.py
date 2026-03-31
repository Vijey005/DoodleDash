"""
DoodleDash E2E Test - Simulates 2 players via WebSocket.
Logs everything to test_results.log
"""
import asyncio
import json
import httpx
import websockets
import sys

LOG_FILE = "test_results.log"
log_fh = None

def log(msg):
    global log_fh
    if log_fh is None:
        log_fh = open(LOG_FILE, "w", encoding="utf-8")
    log_fh.write(msg + "\n")
    log_fh.flush()

class Player:
    def __init__(self, name):
        self.name = name
        self.ws = None
        self.messages = []
        self.player_id = name.lower().replace(" ", "")
        self.room_id = None
        self.is_host = False

    async def connect(self, room_id):
        self.room_id = room_id
        url = f"ws://localhost:8000/ws/{room_id}"
        self.ws = await websockets.connect(url)
        await self.ws.send(json.dumps({
            "action": "join",
            "player_id": self.player_id,
            "nickname": self.name,
            "avatar_eyes": 0,
            "avatar_mouth": 1,
            "avatar_skin": 2,
        }))
        log(f"  [{self.name}] Connected to room {room_id}")

    async def recv_all(self, timeout=2.0):
        msgs = []
        try:
            while True:
                raw = await asyncio.wait_for(self.ws.recv(), timeout=timeout)
                msg = json.loads(raw)
                msgs.append(msg)
                log(f"  [{self.name}] <- {msg.get('type', '???')}: {json.dumps(msg)[:150]}")
        except asyncio.TimeoutError:
            pass
        except websockets.exceptions.ConnectionClosed as e:
            log(f"  [{self.name}] CONNECTION CLOSED: {e}")
        self.messages.extend(msgs)
        return msgs

    async def send(self, data):
        log(f"  [{self.name}] -> {data.get('action', '???')}")
        await self.ws.send(json.dumps(data))

    async def close(self):
        if self.ws:
            await self.ws.close()


async def test_full_game():
    log("=" * 60)
    log("DoodleDash E2E Test")
    log("=" * 60)

    # Step 1: Create Room
    log("\n-- Step 1: Create Room --")
    async with httpx.AsyncClient() as client:
        res = await client.post("http://localhost:8000/api/create-room")
        data = res.json()
        room_id = data.get("room_id")
        if not room_id:
            log(f"  FAIL: No room_id in response: {data}")
            return
        log(f"  OK: Room created: {room_id}")

    # Step 2: Player 1 joins
    log("\n-- Step 2: Player 1 (Alice) joins --")
    alice = Player("Alice")
    try:
        await alice.connect(room_id)
    except Exception as e:
        log(f"  FAIL: Alice connect error: {e}")
        return

    msgs = await alice.recv_all(timeout=2)
    joined = [m for m in msgs if m.get("type") == "joined"]
    if joined:
        alice.is_host = joined[0].get("is_host", False)
        log(f"  OK: Alice joined. is_host={alice.is_host}")
    else:
        log(f"  FAIL: No 'joined' message. Got: {[m.get('type') for m in msgs]}")
        await alice.close()
        return

    room_states = [m for m in msgs if m.get("type") == "room_state"]
    if room_states:
        players = room_states[-1].get("room", {}).get("players", [])
        log(f"  OK: Room state. Players: {[p['nickname'] for p in players]}")
    else:
        log(f"  WARN: No room_state message")

    # Step 3: Player 2 joins
    log("\n-- Step 3: Player 2 (Bob) joins --")
    bob = Player("Bob")
    try:
        await bob.connect(room_id)
    except Exception as e:
        log(f"  FAIL: Bob connect error: {e}")
        await alice.close()
        return

    msgs_bob = await bob.recv_all(timeout=2)
    joined_bob = [m for m in msgs_bob if m.get("type") == "joined"]
    if joined_bob:
        log(f"  OK: Bob joined. is_host={joined_bob[0].get('is_host', False)}")
    else:
        log(f"  FAIL: No 'joined' for Bob. Got: {[m.get('type') for m in msgs_bob]}")
        await alice.close()
        await bob.close()
        return

    # Alice should get player_joined
    msgs_alice = await alice.recv_all(timeout=2)
    pj = [m for m in msgs_alice if m.get("type") == "player_joined"]
    rs = [m for m in msgs_alice if m.get("type") == "room_state"]
    if pj:
        log(f"  OK: Alice got player_joined for {pj[0].get('player', {}).get('nickname')}")
    if rs:
        players = rs[-1].get("room", {}).get("players", [])
        log(f"  OK: Updated room: {[p['nickname'] for p in players]}")

    # Step 4: Start Game
    log("\n-- Step 4: Start Game (2 rounds) --")
    await alice.send({"action": "start_game", "total_rounds": 2})

    msgs_alice = await alice.recv_all(timeout=3)
    msgs_bob = await bob.recv_all(timeout=3)

    cv_alice = [m for m in msgs_alice if m.get("type") == "category_vote"]
    cv_bob = [m for m in msgs_bob if m.get("type") == "category_vote"]

    if cv_alice:
        categories = cv_alice[0].get("categories", [])
        log(f"  OK: Categories: {categories}")
    else:
        log(f"  FAIL: No category_vote. Alice got: {[m.get('type') for m in msgs_alice]}")
        await alice.close()
        await bob.close()
        return

    # Step 5: Vote
    log("\n-- Step 5: Vote --")
    chosen_cat = categories[0]
    await alice.send({"action": "vote_category", "category": chosen_cat})
    await bob.send({"action": "vote_category", "category": chosen_cat})
    log(f"  Both voted: {chosen_cat}")

    await asyncio.sleep(1)
    msgs_alice = await alice.recv_all(timeout=5)
    msgs_bob = await bob.recv_all(timeout=5)

    alice_types = [m.get("type") for m in msgs_alice]
    bob_types = [m.get("type") for m in msgs_bob]
    log(f"  Alice msgs: {alice_types}")
    log(f"  Bob msgs: {bob_types}")

    # Step 6: Word Select
    log("\n-- Step 6: Word Select --")
    # The drawer gets role="drawer", non-drawers get role="voter" with words
    ws_alice = [m for m in msgs_alice if m.get("type") == "word_select"]
    ws_bob = [m for m in msgs_bob if m.get("type") == "word_select"]

    drawer = None
    watcher = None
    words = []
    drawer_msg = None
    voter_msg = None

    for m in ws_alice:
        if m.get("role") == "drawer":
            drawer = alice
            watcher = bob
            drawer_msg = m
        elif m.get("role") == "voter":
            voter_msg = m
            words = m.get("words", [])
            drawer = bob
            watcher = alice

    for m in ws_bob:
        if m.get("role") == "drawer":
            drawer = bob
            watcher = alice
            drawer_msg = m
        elif m.get("role") == "voter":
            voter_msg = m
            words = m.get("words", [])
            if drawer is None:
                drawer = alice
                watcher = bob

    if drawer:
        log(f"  OK: {drawer.name} is the drawer")
    else:
        log(f"  FAIL: Could not determine drawer")
        await alice.close()
        await bob.close()
        return

    if words:
        log(f"  OK: Word options: {words}")
    else:
        log(f"  FAIL: No words available!")
        await alice.close()
        await bob.close()
        return

    # Voter picks a word
    picked_word = words[0]
    await watcher.send({"action": "vote_word", "word": picked_word})
    log(f"  {watcher.name} voted for word: {picked_word}")

    await asyncio.sleep(1)
    msgs_drawer = await drawer.recv_all(timeout=3)
    msgs_watcher = await watcher.recv_all(timeout=3)

    ds_all = msgs_drawer + msgs_watcher
    ds_types = [m.get("type") for m in ds_all]
    log(f"  Post-word-vote msgs: {ds_types}")

    ds_msgs = [m for m in ds_all if m.get("type") == "draw_start"]
    if ds_msgs:
        the_word = ds_msgs[0].get("word", "???")
        log(f"  OK: draw_start! word={the_word}")
    else:
        log(f"  WARN: No draw_start yet, waiting...")
        await asyncio.sleep(2)
        msgs_drawer = await drawer.recv_all(timeout=3)
        msgs_watcher = await watcher.recv_all(timeout=3)
        ds_all = msgs_drawer + msgs_watcher
        ds_msgs = [m for m in ds_all if m.get("type") == "draw_start"]
        if ds_msgs:
            the_word = ds_msgs[0].get("word", "???")
            log(f"  OK: draw_start (delayed)! word={the_word}")
        else:
            log(f"  FAIL: No draw_start. Got: {[m.get('type') for m in ds_all]}")
            await alice.close()
            await bob.close()
            return

    # Step 7: Send drawing data
    log("\n-- Step 7: Send drawing data --")
    pixels = [0.0] * 784
    for i in range(8, 20):
        pixels[i * 28 + 14] = 0.9

    await drawer.send({"action": "draw_data", "pixels": pixels})
    log(f"  {drawer.name} sent drawing data")

    await asyncio.sleep(3)
    msgs_drawer = await drawer.recv_all(timeout=3)
    msgs_watcher = await watcher.recv_all(timeout=3)

    ai_msgs = [m for m in (msgs_drawer + msgs_watcher) if m.get("type") == "ai_guess"]
    timer_msgs = [m for m in (msgs_drawer + msgs_watcher) if m.get("type") == "timer"]

    if ai_msgs:
        g = ai_msgs[-1]
        log(f"  OK: AI guess: '{g.get('guess')}' ({g.get('confidence', 0):.1f}%)")
    else:
        log(f"  WARN: No AI guess. Types: {[m.get('type') for m in msgs_drawer + msgs_watcher]}")

    if timer_msgs:
        log(f"  OK: Timer: {timer_msgs[-1].get('remaining')}s remaining")
    else:
        log(f"  WARN: No timer messages")

    # Step 8: Wait for round end
    log("\n-- Step 8: Wait for round end (up to 35s) --")
    round_ended = False
    game_over = False

    for tick in range(12):
        await asyncio.sleep(3)
        msgs_drawer = await drawer.recv_all(timeout=1)
        msgs_watcher = await watcher.recv_all(timeout=1)

        all_msgs = msgs_drawer + msgs_watcher
        all_types = [m.get("type") for m in all_msgs]

        if "round_result" in all_types:
            rr = [m for m in all_msgs if m.get("type") == "round_result"][0]
            log(f"  OK: Round result: {json.dumps(rr)[:200]}")
            round_ended = True
            break
        if "time_up" in all_types:
            log(f"  OK: Time up")
        if "round_solved" in all_types:
            log(f"  OK: Round solved!")
        if "game_over" in all_types:
            go = [m for m in all_msgs if m.get("type") == "game_over"][0]
            log(f"  OK: Game Over! {json.dumps(go.get('rankings', []))[:200]}")
            game_over = True
            break

        if all_types:
            log(f"    tick {tick}: {all_types}")

    if not round_ended and not game_over:
        log(f"  WARN: Round did not end within 35s")

    # Step 9: Continue to next round or game over
    if round_ended and not game_over:
        log("\n-- Step 9: Next round --")
        await asyncio.sleep(2)
        msgs_drawer = await drawer.recv_all(timeout=5)
        msgs_watcher = await watcher.recv_all(timeout=5)
        all_msgs = msgs_drawer + msgs_watcher
        all_types = [m.get("type") for m in all_msgs]
        log(f"  Next messages: {all_types}")

        if "game_over" in all_types:
            log(f"  OK: Game Over!")
        elif "category_vote" in all_types:
            log(f"  OK: Next round category vote")

    # Cleanup
    log("\n-- Cleanup --")
    await alice.close()
    await bob.close()
    log("  OK: Both disconnected")

    log("\n" + "=" * 60)
    log("Test Complete!")
    log("=" * 60)

if __name__ == "__main__":
    asyncio.run(test_full_game())
    print(f"Done! Results in {LOG_FILE}")
