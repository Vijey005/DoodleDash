<p align="center">
  <img src="https://img.shields.io/badge/python-3.10+-blue?logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/FastAPI-0.100+-009688?logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/TensorFlow-2.x-FF6F00?logo=tensorflow&logoColor=white" alt="TensorFlow">
  <img src="https://img.shields.io/badge/WebSockets-Real--Time-blueviolet?logo=websocket" alt="WebSockets">
</p>

# ✏️ DoodleDash

**DoodleDash** is a real-time multiplayer drawing game where players take turns sketching a prompted word while an **AI model tries to guess** what's being drawn — live, as you draw. Think Pictionary meets machine learning!

Built with **FastAPI**, **WebSockets**, **TensorFlow/Keras**, and a hand-crafted **HTML5 Canvas** frontend.

---

## 🎮 How the Game Works

1. **Create or Join a Room** — A host creates a room and shares the 6-character code. Others join using the code.
2. **Vote on a Category** — All players vote on a theme (Animals, Food, Nature, Objects, etc.).
3. **Pick a Word** — Non-drawing players pick a word for the drawer from the chosen category.
4. **Draw!** — The selected drawer sketches the word on a shared canvas. All other players watch the strokes appear in real-time.
5. **AI Guesses Live** — As the drawer sketches, the canvas is downscaled to 28×28 pixels and sent to a trained neural network every 250ms. The AI's top guess and confidence are shown to everyone.
6. **Scoring** — If the AI correctly identifies the drawing, the drawer earns points. Faster drawings earn more points (up to 1000 per round).
7. **Rapid Round** — If two players are tied at the end, they enter a sudden-death rapid-fire round where both draw simultaneously and the first correct AI guess wins.
8. **Game Over** — Final rankings are displayed with trophies!

---

## 🛠️ Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| **Backend** | [FastAPI](https://fastapi.tiangolo.com/) (Python) | REST API + WebSocket server |
| **Real-Time** | WebSockets | Bi-directional communication for live drawing, chat, and game events |
| **AI Model** | TensorFlow / Keras | CNN trained on [Google QuickDraw](https://quickdraw.withgoogle.com/data) dataset (86 classes) |
| **Frontend** | Vanilla HTML5, CSS3, JavaScript | Canvas drawing, game UI, responsive design |
| **Fonts** | Google Fonts (Balsamiq Sans, Patrick Hand) | Hand-drawn sketchbook aesthetic |
| **Icons** | [Phosphor Icons](https://phosphoricons.com/) | UI iconography |
| **Audio** | Web Audio API | Procedurally generated sound effects (no audio files needed) |

---

## 📁 Project Structure

```
DoodleDash/
├── main.py                 # FastAPI app — routes, WebSocket handler, AI prediction
├── game_manager.py         # Game state machine — rooms, players, turns, scoring
├── requirements.txt        # Python dependencies
├── ai_model/
│   ├── doodledash_model.h5 # Trained Keras CNN model (86 classes)
│   ├── classes.txt         # Class labels (one per line)
│   └── data/               # Training data (.npy files, not in repo)
├── static/
│   ├── index.html          # Main game UI (all screens)
│   ├── style.css           # Sketchbook-themed design system
│   ├── game.js             # Client-side game logic, canvas, WebSocket
│   ├── sound.js            # Standalone sound manager module (Web Audio API)
│   └── test_model.html     # Debug tool for testing AI predictions (see below)
├── test_e2e.py             # End-to-end test suite (see below)
└── .gitignore
```

### 📝 About Extra Files

| File | Why It Exists |
|---|---|
| `static/test_model.html` | A standalone debug page for testing the AI model. You can draw on a canvas, see the 28×28 downscaled input the model receives, and check prediction results. Useful during development to diagnose model accuracy issues. |
| `static/sound.js` | An earlier standalone sound manager module using the Web Audio API. The sound logic was later integrated directly into `game.js`, but this file is kept as a reference implementation. |
| `test_e2e.py` | End-to-end test suite that validates WebSocket connections, room creation, game flow, and AI predictions programmatically. |
| `ai_model/data/` | Contains the QuickDraw `.npy` training data files (~10GB total). Excluded from the repo via `.gitignore` — only the trained model (`.h5`) is committed. |

---

## 🚀 Getting Started

### Prerequisites

- **Python 3.10+**
- **pip**

### Installation

```bash
# Clone the repository
git clone https://github.com/Vijey005/DoodleDash.git
cd DoodleDash

# Create a virtual environment
python -m venv .venv

# Activate it
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Running the Server

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Then open **http://localhost:8000** in your browser.

### Playing

1. Enter your name and customize your avatar
2. Click **Create Room** to host, or enter a room code and click **Join**
3. Share the 6-character room code with friends
4. The host selects number of rounds and clicks **Start Game!**
5. Draw, watch, chat, and let the AI try to guess! 🎨

---

## 🧠 How the AI Works

The AI model is a **Convolutional Neural Network (CNN)** trained on Google's [Quick, Draw!](https://quickdraw.withgoogle.com/data) dataset.

### Pipeline

1. **Drawing** → Player draws on a 600×600 HTML5 Canvas
2. **Preprocessing** → JavaScript crops the drawing to its bounding box, scales it to fit in a 20×20 area, centers it in a 28×28 grid, and inverts pixel values (white background → 0, black ink → 255)
3. **Transmission** → The 784-pixel array is sent via WebSocket every 250ms
4. **Inference** → The FastAPI backend feeds the array into the Keras model
5. **Result** → Top-5 predictions with confidence scores are broadcast to all players

### Model Details

- **Input**: 28×28×1 grayscale image (0–255 range)
- **Architecture**: CNN with convolutional layers, pooling, and dense classifier
- **Output**: 86 classes (see `ai_model/classes.txt`)
- **Training Data**: Google QuickDraw `.npy` files (~86 categories)

---

## 🎨 Game Features

- ✅ **Multiplayer rooms** with shareable room codes
- ✅ **Real-time canvas sync** — watchers see strokes as they happen
- ✅ **Category & word voting** — democratic game flow
- ✅ **AI live prediction** with confidence meter
- ✅ **Time-based scoring** — faster = more points
- ✅ **Rapid tiebreaker round** — sudden death for tied players
- ✅ **In-game chat** with desktop and mobile support
- ✅ **Custom avatars** — pick eyes, mouth, and skin color
- ✅ **Drawing tools** — pen colors, eraser, clear canvas
- ✅ **Sound effects** — procedurally generated via Web Audio API
- ✅ **Fully responsive** — optimized for both desktop and mobile
- ✅ **Sketchbook UI theme** — hand-drawn aesthetic with graph paper background

---

## 📄 License

This project is open source and available for educational purposes.

---

<p align="center">
  <b>Made with ❤️ and lots of doodles</b>
</p>
