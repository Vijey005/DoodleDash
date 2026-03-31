"""
DoodleDash – Multiplayer Backend
FastAPI + WebSockets + AI Inference
"""

import os
import asyncio
import json
import uuid
import numpy as np
import tensorflow as tf
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from tensorflow.keras.models import load_model

from game_manager import GameManager, GameState

# ─── App Setup ─────────────────────────────────────────────────────────────────

app = FastAPI(title="DoodleDash")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")

# ─── Globals ───────────────────────────────────────────────────────────────────

model = None
classes = []
game_manager: GameManager = None

# Active timers per room (for draw time-limit)
room_timers: dict[str, asyncio.Task] = {}

# ─── Model Loading ─────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    global model, classes, game_manager

    model_path = "ai_model/doodledash_model.h5"
    classes_path = "ai_model/classes.txt"

    if os.path.exists(model_path):
        model = load_model(model_path)
        print("✅  Model loaded.")
    else:
        print(f"❌  Model not found at {model_path}")

    if os.path.exists(classes_path):
        with open(classes_path, "r") as f:
            classes = [line.strip() for line in f.readlines() if line.strip()]
        print(f"✅  {len(classes)} classes loaded.")
    else:
        print(f"❌  Classes file not found at {classes_path}")

    game_manager = GameManager(classes)


# ─── Routes ────────────────────────────────────────────────────────────────────

@app.get("/")
async def index():
    return FileResponse("static/index.html")


# ─── AI Prediction Helper ─────────────────────────────────────────────────────

def predict(pixels: list[float]) -> tuple[str, float, list[dict]]:
    """Run inference on 784-float pixel array. Returns (guess, confidence, top5)."""
    arr = np.array(pixels, dtype=np.float32)

    nonzero = np.count_nonzero(arr > 0.05)
    if nonzero < 10:
        return ("...", 0.0, [])

    # Model trained on 0-255 (QuickDraw standard). Client sends 0-255 integers.
    # Scale up if values are in 0-1 range.
    if arr.max() <= 1.0:
        arr = arr * 255.0

    try:
        tensor = arr.reshape(1, 28, 28, 1)
        preds = model.predict(tensor, verbose=0)[0]
    except Exception:
        try:
            tensor = arr.reshape(1, 784)
            preds = model.predict(tensor, verbose=0)[0]
        except Exception:
            return ("Error", 0.0, [])

    top_indices = np.argsort(preds)[::-1][:5]

    top_guesses = [
        {"label": classes[i], "confidence": round(float(preds[i]) * 100, 1)}
        for i in top_indices
    ]

    best_idx = top_indices[0]
    return (classes[best_idx], float(preds[best_idx]), top_guesses)


# ─── Draw Timer ────────────────────────────────────────────────────────────────

async def draw_timer(room_id: str, seconds: int):
    """Background task that fires time_up when drawing time runs out."""
    try:
        for remaining in range(seconds, 0, -1):
            await asyncio.sleep(1)
            room = game_manager.get_room(room_id)
            if not room or room.state != GameState.GAME_LOOP:
                return
            if room.round_solved:
                return
            if remaining % 5 == 0 or remaining <= 10:
                await game_manager.broadcast(room, {
                    "type": "timer",
                    "remaining": remaining,
                })

        # Time's up!
        room = game_manager.get_room(room_id)
        if room and room.state == GameState.GAME_LOOP and not room.round_solved:
            await game_manager.time_up(room)
    except asyncio.CancelledError:
        pass


# ─── WebSocket Endpoint ───────────────────────────────────────────────────────

@app.websocket("/ws/{room_id}")
async def ws_endpoint(websocket: WebSocket, room_id: str):
    await websocket.accept()

    player_id = None

    try:
        while True:
            raw = await websocket.receive_text()
            data = json.loads(raw)
            action = data.get("action")

            # ── Join Room ─────────────────────────────────────────────────

            if action == "join":
                nickname = data.get("nickname", "Anon")
                avatar_eyes = data.get("avatar_eyes", 0)
                avatar_mouth = data.get("avatar_mouth", 0)
                avatar_skin = data.get("avatar_skin", 0)
                player_id = data.get("player_id", uuid.uuid4().hex[:8])

                room = game_manager.get_room(room_id)
                if not room:
                    await websocket.send_json({"type": "error", "message": "Room not found."})
                    await websocket.close()
                    return

                player = game_manager.join_room(
                    room_id, player_id, nickname, avatar_eyes, avatar_mouth, avatar_skin, websocket
                )
                if not player:
                    await websocket.send_json({"type": "error", "message": "Cannot join. Game may have already started."})
                    await websocket.close()
                    return

                await websocket.send_json({
                    "type": "joined",
                    "player_id": player_id,
                    "room_id": room_id,
                    "is_host": player.is_host,
                })

                await game_manager.broadcast(room, {
                    "type": "player_joined",
                    "player": player.to_dict(),
                })

                await game_manager.broadcast_room_state(room)

            # ── Start Game (Host only) ────────────────────────────────────

            elif action == "start_game":
                room = game_manager.get_room(room_id)
                if not room:
                    continue
                player = room.players.get(player_id)
                if not player or not player.is_host:
                    continue
                total_rounds = data.get("total_rounds", 3)
                await game_manager.start_game(room, total_rounds)

            # ── Category Vote ─────────────────────────────────────────────

            elif action == "vote_category":
                room = game_manager.get_room(room_id)
                if not room or room.state != GameState.CATEGORY_VOTE:
                    continue
                category = data.get("category")
                if category and player_id:
                    await game_manager.cast_category_vote(room, player_id, category)

            # ── Word Vote ─────────────────────────────────────────────────

            elif action == "vote_word":
                room = game_manager.get_room(room_id)
                if not room or room.state != GameState.WORD_SELECT:
                    continue
                word = data.get("word")
                if word and player_id:
                    await game_manager.cast_word_vote(room, player_id, word)

            # ── Drawing Data (pixels) ─────────────────────────────────────

            elif action == "draw_data":
                room = game_manager.get_room(room_id)
                if not room:
                    continue

                pixels = data.get("pixels")
                if not pixels or model is None:
                    continue

                if room.state == GameState.GAME_LOOP and player_id == room.current_drawer_id:
                    guess, confidence, top_guesses = predict(pixels)
                    await game_manager.process_ai_guess(room, guess, confidence, top_guesses)

                    # Start timer on first draw data if not already running
                    if room_id not in room_timers or room_timers[room_id].done():
                        room_timers[room_id] = asyncio.create_task(
                            draw_timer(room_id, room.draw_time_limit)
                        )

                elif room.state == GameState.RAPID_ROUND and player_id in room.rapid_players:
                    guess, confidence, top_guesses = predict(pixels)
                    await game_manager.process_rapid_guess(room, player_id, guess, confidence)

            # ── Canvas Stroke Broadcast (for watchers) ────────────────────

            elif action == "stroke":
                room = game_manager.get_room(room_id)
                if not room:
                    continue
                if room.state in (GameState.GAME_LOOP, GameState.RAPID_ROUND):
                    await game_manager.broadcast(room, {
                        "type": "stroke",
                        "player_id": player_id,
                        "points": data.get("points", []),
                        "color": data.get("color", "#333"),
                        "width": data.get("width", 3),
                        "tool": data.get("tool", "pen"),
                    }, exclude=player_id)

            elif action == "clear_canvas":
                room = game_manager.get_room(room_id)
                if room:
                    await game_manager.broadcast(room, {
                        "type": "clear_canvas",
                        "player_id": player_id,
                    }, exclude=player_id)

            # ── Return to Lobby ───────────────────────────────────────────

            elif action == "return_lobby":
                room = game_manager.get_room(room_id)
                if room:
                    player = room.players.get(player_id)
                    if player and player.is_host:
                        await game_manager.return_to_lobby(room)

            # ── Chat message ──────────────────────────────────────────────

            elif action == "chat":
                room = game_manager.get_room(room_id)
                if room and player_id:
                    player = room.players.get(player_id)
                    await game_manager.broadcast(room, {
                        "type": "chat",
                        "player_id": player_id,
                        "nickname": player.nickname if player else "???",
                        "message": data.get("message", "")[:200],
                    })

    except WebSocketDisconnect:
        if player_id:
            left_room_id = game_manager.leave_room(player_id)
            if left_room_id:
                room = game_manager.get_room(left_room_id)
                if room:
                    await game_manager.broadcast(room, {
                        "type": "player_left",
                        "player_id": player_id,
                    })
                    await game_manager.broadcast_room_state(room)
    except Exception as e:
        print(f"WS Error: {e}")
        if player_id:
            game_manager.leave_room(player_id)


# ─── REST: Create / Query Room ────────────────────────────────────────────────

@app.post("/api/create-room")
async def create_room():
    room_id = game_manager.create_room()
    return {"room_id": room_id}


@app.get("/api/room/{room_id}")
async def room_info(room_id: str):
    room = game_manager.get_room(room_id)
    if not room:
        return {"error": "Room not found"}
    return room.to_dict()
