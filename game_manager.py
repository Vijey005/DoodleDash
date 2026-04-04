"""
DoodleDash Game Manager
Handles room states, player management, scoring, turns, and game logic.
"""

import asyncio
import json
import random
import time
import uuid
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set
from fastapi import WebSocket

# ─── Game States ───────────────────────────────────────────────────────────────

class GameState(str, Enum):
    LOBBY = "LOBBY"
    CATEGORY_VOTE = "CATEGORY_VOTE"
    WORD_SELECT = "WORD_SELECT"
    GAME_LOOP = "GAME_LOOP"
    ROUND_RESULT = "ROUND_RESULT"
    RAPID_ROUND = "RAPID_ROUND"
    GAME_OVER = "GAME_OVER"

# ─── Categories & Words ───────────────────────────────────────────────────────

CATEGORIES = {
    "Animals": ["Cat", "Dog", "Bird", "Fish", "Elephant", "Rabbit", "Owl", "Snail", "Snake", "Spider", "Shark", "Butterfly", "Bee"],
    "Food": ["Apple", "Banana", "Hamburger", "Pizza", "Cookie", "Donut", "Ice Cream", "Carrot", "Grapes", "Lollipop", "Watermelon", "Mushroom"],
    "Nature": ["Tree", "Flower", "Sun", "Moon", "Star", "Cloud", "Mountain", "Rainbow", "Lightning", "Rain", "Snowflake", "Leaf", "Cactus", "Palm Tree", "Grass", "Tornado"],
    "Objects": ["Key", "Chair", "Clock", "Book", "Camera", "Candle", "Compass", "Crown", "Diamond", "Hammer", "Hat", "Pencil", "Scissors", "Umbrella", "Paintbrush", "Light Bulb", "Toothbrush", "Wristwatch", "Sock"],
    "Technology": ["Laptop", "Cell Phone", "Television", "Car", "Bicycle", "Airplane", "Sailboat", "Flying Saucer"],
    "Buildings": ["House", "Castle", "Lighthouse", "Bridge"],
    "Sports": ["Baseball Bat", "Basketball", "Soccer Ball"],
    "Everyday": ["Bed", "Table", "Backpack", "Coffee Cup", "Eyeglasses", "Hand", "Skull", "Smiley Face", "Snowman", "Line"],
}

# ─── Data Classes ──────────────────────────────────────────────────────────────

@dataclass
class Player:
    player_id: str
    nickname: str
    avatar_eyes: int = 0
    avatar_mouth: int = 0
    avatar_skin: int = 0
    score: int = 0
    is_host: bool = False
    is_connected: bool = True
    websocket: WebSocket = None  # Not serialized

    def to_dict(self):
        return {
            "player_id": self.player_id,
            "nickname": self.nickname,
            "avatar_eyes": self.avatar_eyes,
            "avatar_mouth": self.avatar_mouth,
            "avatar_skin": self.avatar_skin,
            "score": self.score,
            "is_host": self.is_host,
        }


@dataclass
class Room:
    room_id: str
    state: GameState = GameState.LOBBY
    players: Dict[str, Player] = field(default_factory=dict)
    total_rounds: int = 3
    current_round: int = 0
    
    # Category vote 
    category_options: List[str] = field(default_factory=list)
    category_votes: Dict[str, str] = field(default_factory=dict)   # player_id -> category
    chosen_category: str = ""
    
    # Word selection 
    current_drawer_id: Optional[str] = None
    word_options: List[str] = field(default_factory=list)
    word_votes: Dict[str, str] = field(default_factory=dict)       # player_id -> word
    current_word: str = ""
    
    # Drawing phase 
    draw_start_time: float = 0.0
    draw_time_limit: int = 60     # seconds
    ai_guesses: List[dict] = field(default_factory=list)
    round_solved: bool = False
    round_score: int = 0
    
    # Turn tracking 
    drawer_order: List[str] = field(default_factory=list)
    drawer_index: int = 0
    
    # Rapid round 
    rapid_word: str = ""
    rapid_players: List[str] = field(default_factory=list)
    rapid_start_time: float = 0.0
    rapid_winner: Optional[str] = None

    def get_host(self) -> Optional[Player]:
        for p in self.players.values():
            if p.is_host:
                return p
        return None

    def get_connected_players(self) -> List[Player]:
        return [p for p in self.players.values() if p.is_connected]

    def to_dict(self):
        return {
            "room_id": self.room_id,
            "state": self.state.value,
            "players": [p.to_dict() for p in self.players.values()],
            "total_rounds": self.total_rounds,
            "current_round": self.current_round,
            "current_drawer_id": self.current_drawer_id,
            "current_word": self.current_word if self.state == GameState.GAME_LOOP else "",
            "draw_time_limit": self.draw_time_limit,
            "chosen_category": self.chosen_category,
        }


# ─── Game Manager ──────────────────────────────────────────────────────────────

class GameManager:
    def __init__(self, classes: List[str]):
        self.rooms: Dict[str, Room] = {}
        self.player_room_map: Dict[str, str] = {}   # player_id -> room_id
        self.classes = classes   # all class labels from AI model
        self.vote_timers: Dict[str, asyncio.Task] = {}   # room_id -> vote timer task

    # ── Room Management ───────────────────────────────────────────────────────

    def create_room(self) -> str:
        room_id = uuid.uuid4().hex[:6].upper()
        while room_id in self.rooms:
            room_id = uuid.uuid4().hex[:6].upper()
        self.rooms[room_id] = Room(room_id=room_id)
        return room_id

    def get_room(self, room_id: str) -> Optional[Room]:
        return self.rooms.get(room_id)

    def join_room(self, room_id: str, player_id: str, nickname: str,
                  avatar_eyes: int, avatar_mouth: int, avatar_skin: int, websocket) -> Optional[Player]:
        room = self.get_room(room_id)
        if not room:
            return None
        if room.state != GameState.LOBBY:
            return None
        
        is_host = len(room.players) == 0
        player = Player(
            player_id=player_id,
            nickname=nickname,
            avatar_eyes=avatar_eyes,
            avatar_mouth=avatar_mouth,
            avatar_skin=avatar_skin,
            is_host=is_host,
            websocket=websocket
        )
        
        room.players[player_id] = player
        self.player_room_map[player_id] = room_id
        return player

    def leave_room(self, player_id: str):
        room_id = self.player_room_map.get(player_id)
        if not room_id:
            return None
        room = self.get_room(room_id)
        if not room:
            return None
        
        player = room.players.get(player_id)
        if player:
            player.is_connected = False
            player.websocket = None
        
        del self.player_room_map[player_id]
        
        connected = room.get_connected_players()
        
        # If everyone left, remove the room  
        if not connected:
            del self.rooms[room_id]
            return room_id
        
        # If host left, assign new host  
        if player and player.is_host:
            player.is_host = False
            connected[0].is_host = True
        
        return room_id

    # ── Broadcast Helpers ─────────────────────────────────────────────────────

    async def broadcast(self, room: Room, message: dict, exclude: str = None):
        for p in room.get_connected_players():
            if p.player_id != exclude and p.websocket:
                try:
                    await p.websocket.send_json(message)
                except Exception:
                    pass

    async def send_to(self, room: Room, player_id: str, message: dict):
        p = room.players.get(player_id)
        if p and p.websocket:
            try:
                await p.websocket.send_json(message)
            except Exception:
                pass

    async def broadcast_room_state(self, room: Room):
        await self.broadcast(room, {
            "type": "room_state",
            "room": room.to_dict(),
        })

    # ── Game Flow ─────────────────────────────────────────────────────────────

    async def start_game(self, room: Room, total_rounds: int):
        room.total_rounds = total_rounds
        room.current_round = 0
        
        # Reset scores
        for p in room.players.values():
            p.score = 0
        
        # Build drawer order  
        connected = room.get_connected_players()
        room.drawer_order = [p.player_id for p in connected]
        random.shuffle(room.drawer_order)
        room.drawer_index = 0
        
        await self.start_next_round(room)

    async def start_next_round(self, room: Room):
        room.current_round += 1
        
        if room.current_round > room.total_rounds:
            await self.end_game(room)
            return
        
        # Category vote phase 
        all_cats = list(CATEGORIES.keys())
        room.category_options = random.sample(all_cats, min(3, len(all_cats)))
        room.category_votes = {}
        room.state = GameState.CATEGORY_VOTE
        
        await self.broadcast(room, {
            "type": "category_vote",
            "categories": room.category_options,
            "round": room.current_round,
            "total_rounds": room.total_rounds,
        })
        
        # Start 20-second vote timer
        self._cancel_vote_timer(room.room_id)
        self.vote_timers[room.room_id] = asyncio.create_task(
            self._vote_countdown(room, "category", 20)
        )

    async def cast_category_vote(self, room: Room, player_id: str, category: str):
        if category not in room.category_options:
            return
        room.category_votes[player_id] = category
        
        connected_ids = {p.player_id for p in room.get_connected_players()}
        
        await self.broadcast(room, {
            "type": "vote_update",
            "vote_count": len(room.category_votes),
            "total_players": len(connected_ids),
        })
        
        # Check if all connected players voted  
        if connected_ids <= set(room.category_votes.keys()):
            self._cancel_vote_timer(room.room_id)
            await self.resolve_category_vote(room)

    async def resolve_category_vote(self, room: Room):
        if room.state != GameState.CATEGORY_VOTE:
            return
        
        # Tally votes  
        vote_counts: Dict[str, int] = {}
        for cat in room.category_votes.values():
            vote_counts[cat] = vote_counts.get(cat, 0) + 1
        
        if vote_counts:
            max_votes = max(vote_counts.values())
            winners = [c for c, v in vote_counts.items() if v == max_votes]
            room.chosen_category = random.choice(winners)
        else:
            # No one voted — pick randomly
            room.chosen_category = random.choice(room.category_options)
        
        await self.broadcast(room, {
            "type": "category_result",
            "category": room.chosen_category,
        })
        
        await asyncio.sleep(2)
        await self.start_word_select(room)

    async def start_word_select(self, room: Room):
        # Pick the drawer 
        connected_ids = [p.player_id for p in room.get_connected_players()]
        
        # Cycle through drawer order  
        while room.drawer_order[room.drawer_index % len(room.drawer_order)] not in connected_ids:
            room.drawer_index += 1
            if room.drawer_index >= len(room.drawer_order) * 2:
                room.drawer_index = 0
                break
        
        room.current_drawer_id = room.drawer_order[room.drawer_index % len(room.drawer_order)]
        room.drawer_index += 1
        
        # Word options from chosen category  
        cat_words = CATEGORIES.get(room.chosen_category, [])
        # Filter to only words that exist in the model's class list
        valid_words = [w for w in cat_words if w in self.classes]
        room.word_options = random.sample(valid_words, min(3, len(valid_words)))
        room.word_votes = {}
        room.state = GameState.WORD_SELECT
        
        # Check if solo player (no non-drawers to vote)
        non_drawers = [p for p in room.get_connected_players() if p.player_id != room.current_drawer_id]
        
        if not non_drawers:
            # Solo mode: auto-pick a random word and start drawing
            room.current_word = random.choice(room.word_options)
            await self.start_drawing(room)
            return
        
        # Send to non-drawers: they pick the word  
        await self.send_to(room, room.current_drawer_id, {
            "type": "word_select",
            "role": "drawer",
            "message": "You are the Drawer! Other players are picking a word for you...",
        })
        
        for p in non_drawers:
            await self.send_to(room, p.player_id, {
                "type": "word_select",
                "role": "voter",
                "words": room.word_options,
                "drawer_nickname": room.players[room.current_drawer_id].nickname,
            })
        
        # Start 20-second word vote timer
        self._cancel_vote_timer(room.room_id)
        self.vote_timers[room.room_id] = asyncio.create_task(
            self._vote_countdown(room, "word", 20)
        )

    async def cast_word_vote(self, room: Room, player_id: str, word: str):
        if player_id == room.current_drawer_id:
            return
        if word not in room.word_options:
            return
        room.word_votes[player_id] = word
        
        non_drawer_ids = {p.player_id for p in room.get_connected_players() if p.player_id != room.current_drawer_id}
        
        if non_drawer_ids <= set(room.word_votes.keys()):
            self._cancel_vote_timer(room.room_id)
            await self.resolve_word_vote(room)

    async def resolve_word_vote(self, room: Room):
        if room.state != GameState.WORD_SELECT:
            return
        
        vote_counts: Dict[str, int] = {}
        for word in room.word_votes.values():
            vote_counts[word] = vote_counts.get(word, 0) + 1
        
        max_votes = max(vote_counts.values()) if vote_counts else 0
        winners = [w for w, v in vote_counts.items() if v == max_votes]
        room.current_word = random.choice(winners) if winners else random.choice(room.word_options)
        
        await self.start_drawing(room)

    # ── Vote Timer Helpers ────────────────────────────────────────────────

    def _cancel_vote_timer(self, room_id: str):
        task = self.vote_timers.get(room_id)
        if task and not task.done():
            task.cancel()

    async def _vote_countdown(self, room: Room, vote_type: str, seconds: int):
        """Countdown timer for voting phases. Broadcasts ticks and auto-resolves."""
        try:
            for remaining in range(seconds, 0, -1):
                await asyncio.sleep(1)
                # Check if vote already resolved
                if vote_type == "category" and room.state != GameState.CATEGORY_VOTE:
                    return
                if vote_type == "word" and room.state != GameState.WORD_SELECT:
                    return
                
                await self.broadcast(room, {
                    "type": "vote_timer",
                    "remaining": remaining,
                    "vote_type": vote_type,
                })
            
            # Time's up — auto-resolve
            if vote_type == "category" and room.state == GameState.CATEGORY_VOTE:
                await self.resolve_category_vote(room)
            elif vote_type == "word" and room.state == GameState.WORD_SELECT:
                await self.resolve_word_vote(room)
        except asyncio.CancelledError:
            pass

    async def start_drawing(self, room: Room):
        room.state = GameState.GAME_LOOP
        room.draw_start_time = time.time()
        room.round_solved = False
        room.round_score = 0
        room.ai_guesses = []
        
        # Tell the drawer the word  
        await self.send_to(room, room.current_drawer_id, {
            "type": "draw_start",
            "role": "drawer",
            "word": room.current_word,
            "time_limit": room.draw_time_limit,
            "round": room.current_round,
            "total_rounds": room.total_rounds,
        })
        
        # Tell the watchers  
        for p in room.get_connected_players():
            if p.player_id != room.current_drawer_id:
                await self.send_to(room, p.player_id, {
                    "type": "draw_start",
                    "role": "watcher",
                    "word_hint": self._make_hint(room.current_word),
                    "time_limit": room.draw_time_limit,
                    "drawer_nickname": room.players[room.current_drawer_id].nickname,
                    "round": room.current_round,
                    "total_rounds": room.total_rounds,
                })
        
        await self.broadcast_room_state(room)

    def _make_hint(self, word: str) -> str:
        return " ".join("_" if c != " " else "  " for c in word)

    async def process_ai_guess(self, room: Room, guess: str, confidence: float, top_guesses: list):
        if room.state != GameState.GAME_LOOP:
            return
        
        elapsed = time.time() - room.draw_start_time
        is_correct = guess.lower() == room.current_word.lower()
        
        guess_data = {
            "type": "ai_guess",
            "guess": guess,
            "confidence": round(confidence * 100, 1),
            "correct": is_correct,
            "elapsed": round(elapsed, 1),
            "top_guesses": top_guesses[:5],
        }
        
        await self.broadcast(room, guess_data)
        
        if is_correct and not room.round_solved:
            room.round_solved = True
            # Score: 1000 max, decreasing over time  
            time_bonus = max(0, 1.0 - (elapsed / room.draw_time_limit))
            room.round_score = int(200 + 800 * time_bonus)
            
            drawer = room.players.get(room.current_drawer_id)
            if drawer:
                drawer.score += room.round_score
            
            await self.broadcast(room, {
                "type": "round_solved",
                "word": room.current_word,
                "score": room.round_score,
                "drawer_id": room.current_drawer_id,
                "elapsed": round(elapsed, 1),
            })
            
            await asyncio.sleep(3)
            await self.end_turn(room)

    async def time_up(self, room: Room):
        if room.state != GameState.GAME_LOOP or room.round_solved:
            return
        
        await self.broadcast(room, {
            "type": "time_up",
            "word": room.current_word,
        })
        
        await asyncio.sleep(3)
        await self.end_turn(room)

    async def end_turn(self, room: Room):
        room.state = GameState.ROUND_RESULT
        
        await self.broadcast(room, {
            "type": "round_result",
            "round": room.current_round,
            "scores": {p.player_id: p.score for p in room.players.values()},
            "players": [p.to_dict() for p in room.players.values()],
        })
        
        await asyncio.sleep(3)
        
        # Check if more rounds remain  
        connected = room.get_connected_players()
        all_have_drawn = room.drawer_index >= len(room.drawer_order)
        
        if all_have_drawn:
            # Reset drawer index for next round cycle  
            room.drawer_index = 0
            await self.start_next_round(room)
        else:
            # Next drawer in same round  
            await self.start_word_select(room)

    async def end_game(self, room: Room):
        # Check for ties  
        connected = room.get_connected_players()
        if len(connected) < 2:
            await self.show_final_results(room)
            return
        
        sorted_players = sorted(connected, key=lambda p: p.score, reverse=True)
        
        if len(sorted_players) >= 2 and sorted_players[0].score == sorted_players[1].score and sorted_players[0].score > 0:
            # Tie → Rapid Round  
            tied = [p for p in sorted_players if p.score == sorted_players[0].score]
            await self.start_rapid_round(room, [p.player_id for p in tied[:2]])
        else:
            await self.show_final_results(room)

    async def start_rapid_round(self, room: Room, player_ids: List[str]):
        room.state = GameState.RAPID_ROUND
        room.rapid_players = player_ids
        
        # Pick a random word  
        all_words = []
        for words in CATEGORIES.values():
            all_words.extend(words)
        valid_words = [w for w in all_words if w in self.classes]
        room.rapid_word = random.choice(valid_words)
        room.rapid_start_time = time.time()
        room.rapid_winner = None
        
        await self.broadcast(room, {
            "type": "rapid_round",
            "players": player_ids,
            "player_nicknames": [room.players[pid].nickname for pid in player_ids],
            "word": room.rapid_word,
        })

    async def process_rapid_guess(self, room: Room, player_id: str, guess: str, confidence: float):
        if room.state != GameState.RAPID_ROUND:
            return
        if player_id not in room.rapid_players:
            return
        if room.rapid_winner:
            return
        
        await self.broadcast(room, {
            "type": "rapid_guess",
            "player_id": player_id,
            "guess": guess,
            "confidence": round(confidence * 100, 1),
        })
        
        if guess.lower() == room.rapid_word.lower() and confidence > 0.80:
            room.rapid_winner = player_id
            # Bonus points  
            room.players[player_id].score += 500
            
            await self.broadcast(room, {
                "type": "rapid_winner",
                "winner_id": player_id,
                "winner_nickname": room.players[player_id].nickname,
                "word": room.rapid_word,
            })
            
            await asyncio.sleep(3)
            await self.show_final_results(room)

    async def show_final_results(self, room: Room):
        room.state = GameState.GAME_OVER
        
        sorted_players = sorted(
            room.get_connected_players(),
            key=lambda p: p.score,
            reverse=True
        )
        
        await self.broadcast(room, {
            "type": "game_over",
            "rankings": [
                {
                    "rank": i + 1,
                    "player_id": p.player_id,
                    "nickname": p.nickname,
                    "score": p.score,
                    "avatar_eyes": p.avatar_eyes,
                    "avatar_mouth": p.avatar_mouth,
                    "avatar_skin": p.avatar_skin,
                }
                for i, p in enumerate(sorted_players)
            ],
        })

    async def return_to_lobby(self, room: Room):
        room.state = GameState.LOBBY
        room.current_round = 0
        room.current_drawer_id = None
        room.current_word = ""
        for p in room.players.values():
            p.score = 0
        await self.broadcast_room_state(room)
