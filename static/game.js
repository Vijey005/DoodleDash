/* ═══════════════════════════════════════════════════════════════════════════
   DoodleDash – Client-Side Game Logic
   Manages WebSocket, Canvas, Screens, and Game Flow
   ═══════════════════════════════════════════════════════════════════════════ */

(() => {
    "use strict";

    // ── Constants ────────────────────────────────────────────────────────────────

    const AVATAR_EYES = [
        '<circle cx="8" cy="10" r="2"/><circle cx="24" cy="10" r="2"/>',
        '<rect x="4" y="8" width="8" height="4"/><rect x="20" y="8" width="8" height="4"/><line x1="12" y1="10" x2="20" y2="10" stroke="black" stroke-width="1"/>',
        '<path d="M6 12 Q9 6 12 12 M20 12 Q23 6 26 12" fill="none" stroke="black" stroke-width="2"/>',
        '<circle cx="8" cy="10" r="1.5"/><line x1="20" y1="10" x2="26" y2="10" stroke="black" stroke-width="2"/>'
    ];
    const AVATAR_MOUTHS = [
        '<path d="M10 20 Q16 26 22 20" fill="none" stroke="black" stroke-width="2"/>',
        '<circle cx="16" cy="22" r="3" fill="black"/>',
        '<line x1="10" y1="22" x2="22" y2="22" stroke="black" stroke-width="2"/>',
        '<path d="M10 20 Q16 26 22 20 Z" fill="black"/>'
    ];
    const AVATAR_SKINS = ["#fff9c4", "#ffccbc", "#d7ccc8", "#b3e5fc", "#c8e6c9", "#e1bee7"];
    const SEND_INTERVAL = 250; // Increased slightly to prevent network choke

    // ── Sound Manager ────────────────────────────────────────────────────────────

    const Sound = {
        ctx: null,
        init: () => {
            if (!Sound.ctx) {
                const AudioContext = window.AudioContext || window.webkitAudioContext;
                if (AudioContext) {
                    Sound.ctx = new AudioContext();
                }
            }
            Sound.resume();
        },
        resume: () => {
            if (Sound.ctx && Sound.ctx.state === 'suspended') {
                Sound.ctx.resume();
            }
        },
        playTone: (freq, type, duration, vol = 0.1) => {
            if (!Sound.ctx) Sound.init();
            if (!Sound.ctx) return;
            if (Sound.ctx.state === 'suspended') Sound.resume();

            const osc = Sound.ctx.createOscillator();
            const gain = Sound.ctx.createGain();
            osc.type = type;
            osc.frequency.setValueAtTime(freq, Sound.ctx.currentTime);

            gain.gain.setValueAtTime(vol, Sound.ctx.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.01, Sound.ctx.currentTime + duration);

            osc.connect(gain);
            gain.connect(Sound.ctx.destination);

            osc.start();
            osc.stop(Sound.ctx.currentTime + duration);
        },
        // UI interactions
        playPop: () => Sound.playTone(600, "sine", 0.1, 0.1),
        playClick: () => Sound.playTone(900, "sine", 0.05, 0.08),
        // Positive events
        playJoin: () => {
            Sound.playTone(400, "sine", 0.15, 0.12);
            setTimeout(() => Sound.playTone(600, "sine", 0.15, 0.12), 120);
            setTimeout(() => Sound.playTone(800, "sine", 0.25, 0.12), 240);
        },
        playStart: () => {
            Sound.playTone(500, "square", 0.1, 0.12);
            setTimeout(() => Sound.playTone(700, "square", 0.1, 0.12), 120);
            setTimeout(() => Sound.playTone(1000, "square", 0.35, 0.15), 240);
        },
        playCorrect: () => {
            Sound.playTone(523, "sine", 0.12, 0.2);
            setTimeout(() => Sound.playTone(659, "sine", 0.12, 0.2), 100);
            setTimeout(() => Sound.playTone(784, "sine", 0.12, 0.2), 200);
            setTimeout(() => Sound.playTone(1047, "sine", 0.4, 0.25), 300);
        },
        playVoteSelect: () => {
            Sound.playTone(700, "sine", 0.08, 0.1);
            setTimeout(() => Sound.playTone(900, "sine", 0.12, 0.1), 80);
        },
        playCategoryResult: () => {
            Sound.playTone(600, "triangle", 0.1, 0.15);
            setTimeout(() => Sound.playTone(800, "triangle", 0.1, 0.15), 100);
            setTimeout(() => Sound.playTone(1000, "triangle", 0.3, 0.15), 200);
        },
        // Countdown / Warning
        playTick: () => Sound.playTone(800, "triangle", 0.05, 0.06),
        playTickUrgent: () => {
            Sound.playTone(1000, "square", 0.08, 0.12);
        },
        playVoteTick: () => Sound.playTone(600, "triangle", 0.04, 0.04),
        // Negative events
        playTimeUp: () => {
            Sound.playTone(400, "sawtooth", 0.15, 0.2);
            setTimeout(() => Sound.playTone(300, "sawtooth", 0.15, 0.2), 150);
            setTimeout(() => Sound.playTone(200, "sawtooth", 0.5, 0.25), 300);
        },
        playGameOver: () => {
            Sound.playTone(500, "sawtooth", 0.2, 0.15);
            setTimeout(() => Sound.playTone(400, "sawtooth", 0.2, 0.15), 200);
            setTimeout(() => Sound.playTone(300, "sawtooth", 0.2, 0.15), 400);
            setTimeout(() => Sound.playTone(200, "sawtooth", 0.5, 0.2), 600);
        },
        playError: () => {
            Sound.playTone(200, "square", 0.15, 0.15);
            setTimeout(() => Sound.playTone(180, "square", 0.25, 0.15), 150);
        },
        playLeave: () => {
            Sound.playTone(600, "sine", 0.1, 0.1);
            setTimeout(() => Sound.playTone(400, "sine", 0.2, 0.1), 100);
        }
    };


    // ── State ────────────────────────────────────────────────────────────────────

    let ws = null;
    let playerId = sessionStorage.getItem("dd_player_id") || generateId();
    let nickname = sessionStorage.getItem("dd_nickname") || "";
    let avatarEyes = parseInt(sessionStorage.getItem("dd_avatar_eyes") || "0");
    let avatarMouth = parseInt(sessionStorage.getItem("dd_avatar_mouth") || "0");
    let avatarSkin = parseInt(sessionStorage.getItem("dd_avatar_skin") || "0");
    let roomId = null;
    let isHost = false;
    let isSoloMode = false;
    let totalRounds = 3;

    // Game state
    let myRole = ""; // "drawer" | "watcher"
    let currentWord = "";
    let drawingAllowed = false;

    // Canvas state
    let canvas, ctx;
    let isDrawing = false;
    let lastX = 0, lastY = 0;
    let penColor = "#2d2d2d";
    let penSize = 25; // Increased to 25 to match relative thickness of test canvas (600x600 vs 400x400)
    let currentTool = "pen";
    let sendTimer = null;

    // Stroke tracking for clean 28x28 rendering (avoids anti-aliasing blur)
    let allStrokes = [];      // Array of { points: [{x,y},...], tool: "pen"|"eraser" }
    let currentStroke = null;  // Stroke currently being drawn



    // ── Helpers ──────────────────────────────────────────────────────────────────

    function generateId() {
        const id = Math.random().toString(36).substring(2, 10);
        sessionStorage.setItem("dd_player_id", id);
        return id;
    }

    function $(sel) { return document.querySelector(sel); }
    function $$(sel) { return document.querySelectorAll(sel); }

    function showScreen(id) {
        $$(".screen").forEach(s => s.classList.remove("active"));
        const target = $(`#screen-${id}`);
        if (target) target.classList.add("active");
    }

    function toast(msg, type = "info") {
        const container = $("#toast-container");
        if (!container) return;
        const el = document.createElement("div");
        el.className = `btn btn-secondary`;
        el.style.pointerEvents = "auto";
        el.style.fontSize = "0.9rem";
        el.innerHTML = `<i class="ph-bold ph-info"></i> ${msg}`;
        if (type === "error") el.style.border = "3px solid #ef5350";
        if (type === "success") el.style.border = "3px solid #66bb6a";

        container.appendChild(el);
        setTimeout(() => el.remove(), 3000);
    }

    function showOverlay(icon, title, body, duration = 3000, type = "success") {
        const ov = $("#overlay-result");
        const content = $(".overlay-content");
        $("#overlay-icon").innerHTML = icon;
        $("#overlay-title").textContent = title;
        $("#overlay-body").textContent = body;

        // Apply type-based shadow color
        content.classList.remove("overlay-success", "overlay-fail", "overlay-info");
        content.classList.add(`overlay-${type}`);

        ov.classList.remove("hidden");
        if (duration > 0) {
            setTimeout(() => ov.classList.add("hidden"), duration);
        }
    }

    function saveSession() {
        sessionStorage.setItem("dd_nickname", nickname);
        sessionStorage.setItem("dd_avatar_eyes", avatarEyes.toString());
        sessionStorage.setItem("dd_avatar_mouth", avatarMouth.toString());
        sessionStorage.setItem("dd_avatar_skin", avatarSkin.toString());
    }

    function renderAvatar(eyes, mouth, skin, big = false) {
        const size = big ? 60 : 30;
        const skinColor = AVATAR_SKINS[skin] || "#fff9c4";
        const eyesSvg = AVATAR_EYES[eyes] || "";
        const mouthSvg = AVATAR_MOUTHS[mouth] || "";
        return `<div class="avatar-circle" style="width:${size}px; height:${size}px; background:${skinColor}; border:2px solid #2d2d2d; border-radius:50%; display:flex; align-items:center; justify-content:center; overflow:hidden; box-shadow: 2px 2px 0 #2d2d2d; flex-shrink: 0;"><svg viewBox="0 0 32 32" style="width:70%; height:70%;">${eyesSvg}${mouthSvg}</svg></div>`;
    }

    // ── BOOT & ENTRY ─────────────────────────────────────────────────────────────

    function initEntry() {
        const nicknameInput = $("#nickname-input");
        if (nickname) nicknameInput.value = nickname;
        updateAvatarPreview();

        $("#btn-prev-eyes").onclick = () => { avatarEyes = (avatarEyes - 1 + AVATAR_EYES.length) % AVATAR_EYES.length; updateAvatarPreview(); };
        $("#btn-next-eyes").onclick = () => { avatarEyes = (avatarEyes + 1) % AVATAR_EYES.length; updateAvatarPreview(); };
        $("#btn-prev-mouth").onclick = () => { avatarMouth = (avatarMouth - 1 + AVATAR_MOUTHS.length) % AVATAR_MOUTHS.length; updateAvatarPreview(); };
        $("#btn-next-mouth").onclick = () => { avatarMouth = (avatarMouth + 1) % AVATAR_MOUTHS.length; updateAvatarPreview(); };
        $("#btn-prev-skin").onclick = () => { avatarSkin = (avatarSkin - 1 + AVATAR_SKINS.length) % AVATAR_SKINS.length; updateAvatarPreview(); };
        $("#btn-next-skin").onclick = () => { avatarSkin = (avatarSkin + 1) % AVATAR_SKINS.length; updateAvatarPreview(); };

        $("#btn-create-room").onclick = async () => {
            nickname = nicknameInput.value.trim();
            if (!nickname) { toast("Name please!", "error"); return; }
            saveSession();
            isSoloMode = false;
            try {
                const res = await fetch("/api/create-room", { method: "POST" });
                const data = await res.json();
                roomId = data.room_id;
                connectWebSocket();
            } catch (e) { toast("Error creating room", "error"); }
        };

        $("#btn-solo").onclick = async () => {
            nickname = nicknameInput.value.trim();
            if (!nickname) { toast("Name please!", "error"); return; }
            saveSession();
            isSoloMode = true;
            try {
                const res = await fetch("/api/create-room", { method: "POST" });
                const data = await res.json();
                roomId = data.room_id;
                connectWebSocket();
            } catch (e) { toast("Error creating room", "error"); }
        };

        $("#btn-join-room").onclick = () => {
            nickname = nicknameInput.value.trim();
            if (!nickname) { toast("Name please!", "error"); return; }
            const code = $("#room-code-input").value.trim().toUpperCase();
            if (code.length < 4) { toast("Check room code!", "error"); return; }
            saveSession();
            roomId = code;
            connectWebSocket();
        };

        // Chat listeners (Desktop)
        $("#btn-send-chat").onclick = () => sendChat("desktop");
        $("#chat-input").onkeypress = (e) => {
            if (e.key === "Enter") sendChat("desktop");
        };

        // Chat listeners (Mobile)
        $("#mobile-chat-bar").onclick = openMobileChat;
        $("#btn-close-mobile-chat").onclick = closeMobileChat;
        $("#btn-mobile-send-chat").onclick = () => sendChat("mobile");
        $("#mobile-chat-input").onkeypress = (e) => {
            if (e.key === "Enter") sendChat("mobile");
        };

        // Try to unlock audio on interaction
        document.body.addEventListener('click', () => { Sound.init(); Sound.resume(); }, { once: true });
        document.body.addEventListener('touchstart', () => { Sound.init(); Sound.resume(); }, { once: true });
    }

    function updateAvatarPreview() {
        $("#avatar-preview-container").innerHTML = renderAvatar(avatarEyes, avatarMouth, avatarSkin, true);
    }

    function sendChat(source) {
        const inputId = source === "mobile" ? "#mobile-chat-input" : "#chat-input";
        const input = $(inputId);
        const msg = input.value.trim();
        if (!msg) return;
        send({ action: "chat", message: msg });
        input.value = "";
    }

    function openMobileChat() {
        const popup = $("#mobile-chat-popup");
        popup.classList.remove("hidden");
        // Copy desktop messages to mobile popup
        const mobileMsgs = $("#mobile-chat-messages");
        mobileMsgs.innerHTML = $("#chat-messages").innerHTML;
        mobileMsgs.scrollTop = mobileMsgs.scrollHeight;
        // Focus the input
        setTimeout(() => $("#mobile-chat-input").focus(), 100);
    }

    function closeMobileChat() {
        $("#mobile-chat-popup").classList.add("hidden");
    }

    // ── WebSocket ─────────────────────────────────────────────────────────────

    function connectWebSocket() {
        const protocol = location.protocol === "https:" ? "wss:" : "ws:";
        const url = `${protocol}//${location.host}/ws/${roomId}`;
        ws = new WebSocket(url);

        ws.onopen = () => {
            Sound.playJoin();
            ws.send(JSON.stringify({
                action: "join",
                player_id: playerId,
                nickname: nickname,
                avatar_eyes: avatarEyes,
                avatar_mouth: avatarMouth,
                avatar_skin: avatarSkin,
            }));
        };

        ws.onmessage = (event) => {
            const msg = JSON.parse(event.data);
            handleMessage(msg);
        };

        ws.onerror = () => toast("Connection error 😵", "error");
        ws.onclose = () => {
            if (sendTimer) clearInterval(sendTimer);
            toast("Disconnected 🔌", "error");
        };
    }

    function send(data) {
        if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(data));
    }

    function handleMessage(msg) {
        switch (msg.type) {
            case "joined": onJoined(msg); break;
            case "error": toast(msg.message, "error"); Sound.playError(); break;
            case "room_state": onRoomState(msg.room); break;
            case "player_joined": if (msg.player.player_id !== playerId) { toast(`${msg.player.nickname} joined!`, "success"); Sound.playJoin(); } break;
            case "player_left": toast(`Someone left.`, "info"); Sound.playLeave(); break;

            case "category_vote": onCategoryVote(msg); break;
            case "vote_update": $("#vote-status").textContent = `${msg.vote_count}/${msg.total_players} voted`; break;
            case "vote_timer": onVoteTimer(msg); break;
            case "category_result": showOverlay('<i class="ph-duotone ph-check-circle"></i>', msg.category, "Get ready!", 2000, "success"); Sound.playCategoryResult(); break;

            case "word_select": onWordSelect(msg); break;

            case "draw_start":
                Sound.playStart();
                onDrawStart(msg);
                break;
            case "ai_guess": onAiGuess(msg); break;
            case "timer":
                $("#game-timer").textContent = msg.remaining;
                if (msg.remaining <= 5 && msg.remaining > 0) Sound.playTickUrgent();
                else if (msg.remaining <= 10) Sound.playTick();
                $("#game-timer").classList.toggle("warning", msg.remaining <= 10);
                break;
            case "round_solved": onRoundSolved(msg); break;
            case "time_up":
                drawingAllowed = false;
                Sound.playTimeUp();
                showOverlay('<i class="ph-duotone ph-alarm"></i>', "Time's Up!", `Word was: ${msg.word}`, 3000, "fail");
                break;
            case "round_result": renderGamePlayers(msg.players); break;
            case "stroke": onRemoteStroke(msg); break;
            case "clear_canvas": if (ctx) { ctx.fillStyle = "#ffffff"; ctx.fillRect(0, 0, canvas.width, canvas.height); } break;
            case "game_over": onGameOver(msg); break;
            case "chat": onChatMessage(msg); break;
        }
    }

    function onJoined(msg) {
        playerId = msg.player_id;
        roomId = msg.room_id;
        isHost = msg.is_host;
        showScreen("lobby");
        $("#lobby-room-code").textContent = roomId;
        $("#btn-copy-code").onclick = () => { navigator.clipboard.writeText(roomId); toast("Copied!", "success"); };

        // Show/hide solo easter egg
        const eggEl = $("#solo-easter-egg");
        if (eggEl) {
            if (isSoloMode) {
                eggEl.classList.remove("hidden");
            } else {
                eggEl.classList.add("hidden");
            }
        }

        if (isHost) {
            $("#host-controls").classList.remove("hidden");
            $("#guest-wait").classList.add("hidden");
            $$(".btn-round").forEach(btn => {
                btn.onclick = () => {
                    $$(".btn-round").forEach(b => b.classList.remove("active"));
                    btn.classList.add("active");
                    totalRounds = parseInt(btn.dataset.rounds);
                };
            });
            $("#btn-start-game").onclick = () => send({ action: "start_game", total_rounds: totalRounds });
        } else {
            $("#host-controls").classList.add("hidden");
            $("#guest-wait").classList.remove("hidden");
        }
    }

    function onRoomState(room) {
        if (room.state === "LOBBY") {
            showScreen("lobby");
        }

        // Hide solo easter egg if there are other players
        const eggEl = $("#solo-easter-egg");
        if (eggEl && room.players.length > 1) {
            eggEl.classList.add("hidden");
        }

        const container = $("#lobby-players");
        if (container) {
            container.innerHTML = room.players.map(p => `
                <div class="sb-player">
                    ${renderAvatar(p.avatar_eyes, p.avatar_mouth, p.avatar_skin)}
                    <span class="sb-name">${p.nickname}</span>
                    ${p.is_host ? '<i class="ph-fill ph-crown" style="color:#fbc02d"></i>' : ''}
                </div>
            `).join("");
        }
    }

    function onCategoryVote(msg) {
        showScreen("category-vote");
        $("#vote-round").textContent = msg.round;
        $("#vote-status").textContent = "Pick a theme!";
        const grid = $("#category-options");
        grid.innerHTML = msg.categories.map(cat => `<button class="btn btn-secondary" style="width:100%; height:80px; font-size:1.2rem;" data-cat="${cat}">${cat}</button>`).join("");
        grid.querySelectorAll("button").forEach(btn => {
            btn.onclick = () => {
                grid.querySelectorAll("button").forEach(b => { b.classList.remove("btn-primary"); b.classList.add("btn-secondary"); });
                btn.classList.remove("btn-secondary"); btn.classList.add("btn-primary");
                send({ action: "vote_category", category: btn.dataset.cat });
                $("#vote-status").textContent = "Waiting for others...";
                Sound.playVoteSelect();
            };
        });
    }

    function onVoteTimer(msg) {
        const remaining = msg.remaining;
        const statusEl = $("#vote-status");
        if (statusEl) {
            const existingText = statusEl.textContent;
            // Preserve voting status info, append timer
            const baseText = existingText.replace(/\s*⏱.*$/, "");
            statusEl.textContent = `${baseText} ⏱ ${remaining}s`;
        }
        if (remaining <= 5 && remaining > 0) Sound.playTickUrgent();
        else if (remaining <= 10) Sound.playVoteTick();
    }

    function onWordSelect(msg) {
        showScreen("word-select");
        if (msg.role === "drawer") {
            $("#word-select-title").innerHTML = '<i class="ph-bold ph-pencil-simple"></i> Draw!';
            $("#word-select-subtitle").textContent = "Wait while they pick a word...";
            $("#word-options").innerHTML = "";
        } else {
            $("#word-select-title").innerHTML = '<i class="ph-bold ph-target"></i> Pick!';
            $("#word-select-subtitle").textContent = `Pick a word for ${msg.drawer_nickname}:`;
            const grid = $("#word-options");
            grid.innerHTML = msg.words.map(w => `<button class="btn btn-secondary" style="justify-content:space-between;" data-word="${w}">${w} <i class="ph-bold ph-arrow-right"></i></button>`).join("");
            grid.querySelectorAll("button").forEach(btn => {
                btn.onclick = () => {
                    send({ action: "vote_word", word: btn.dataset.word });
                    showScreen("game");
                    $("#word-status").textContent = "Good choice! Waiting...";
                    Sound.playVoteSelect();
                };
            });
        }
    }

    function onDrawStart(msg) {
        showScreen("game");
        myRole = msg.role;
        drawingAllowed = (myRole === "drawer");

        initCanvas(); // Initialize canvas

        $("#game-round").textContent = msg.round || 1;
        $("#game-total-rounds").textContent = msg.total_rounds || 3;

        if (myRole === "drawer") {
            currentWord = msg.word;
            $("#game-word-display").innerHTML = `<span style="color:#2d2d2d;">${currentWord}</span>`;
            $("#draw-tools").classList.remove("hidden");
            toast("You are drawing!", "success");
        } else {
            $("#game-word-display").textContent = msg.word_hint;
            $("#draw-tools").classList.add("hidden");
            toast(`${msg.drawer_nickname} is drawing!`, "info");
        }

        $("#game-timer").textContent = msg.time_limit;
        $("#ai-guess-word").textContent = "...";
        $("#ai-confidence").textContent = "0%";

        if (sendTimer) clearInterval(sendTimer);
        if (drawingAllowed) {
            sendTimer = setInterval(sendCanvasData, SEND_INTERVAL);
        }
    }

    // ── CANVASSING ─────────────────────────────────────────────────────────────

    function initCanvas() {
        canvas = $("#draw-canvas");
        if (!canvas) {
            console.error("Canvas element not found!");
            return;
        }

        // Context creation (reusing if exists)
        if (!ctx) {
            ctx = canvas.getContext("2d", { willReadFrequently: true });
        }

        // Fill white and reset stroke history
        ctx.fillStyle = "#ffffff";
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        allStrokes = [];
        currentStroke = null;

        // Add Listeners (it's safe to re-add named functions)
        canvas.removeEventListener("pointerdown", onPointerDown);
        canvas.removeEventListener("pointermove", onPointerMove);
        canvas.removeEventListener("pointerup", onPointerUp);
        canvas.removeEventListener("pointerleave", onPointerUp);

        canvas.addEventListener("pointerdown", onPointerDown);
        canvas.addEventListener("pointermove", onPointerMove);
        canvas.addEventListener("pointerup", onPointerUp);
        canvas.addEventListener("pointerleave", onPointerUp);
        canvas.addEventListener("touchstart", e => e.preventDefault(), { passive: false });

        // Tools
        $$(".color-btn").forEach(btn => {
            btn.onclick = () => {
                $$(".color-btn").forEach(b => b.classList.remove("active"));
                btn.classList.add("active");
                penColor = btn.dataset.color;
                currentTool = "pen";
                activateToolBtn("btn-pen");
                Sound.playPop();
            };
        });
        $("#btn-pen").onclick = () => { currentTool = "pen"; activateToolBtn("btn-pen"); Sound.playPop(); };
        $("#btn-eraser").onclick = () => { currentTool = "eraser"; activateToolBtn("btn-eraser"); Sound.playPop(); };
        $("#btn-clear").onclick = () => {
            ctx.fillStyle = "#ffffff";
            ctx.fillRect(0, 0, canvas.width, canvas.height);
            allStrokes = [];       // Reset stroke history
            currentStroke = null;
            send({ action: "clear_canvas" });
            Sound.playPop();
        };
    }

    function activateToolBtn(id) {
        $$(".tool-btn").forEach(b => b.classList.remove("active-tool"));
        $(`#${id}`).classList.add("active-tool");
    }

    function getPos(e) {
        const rect = canvas.getBoundingClientRect();
        return {
            x: (e.clientX - rect.left) * (canvas.width / rect.width),
            y: (e.clientY - rect.top) * (canvas.height / rect.height)
        };
    }

    function onPointerDown(e) {
        if (!drawingAllowed) return;
        Sound.resume(); // Ensure audio context is running on user interaction
        isDrawing = true;
        const p = getPos(e);
        lastX = p.x; lastY = p.y;
        canvas.setPointerCapture(e.pointerId);

        // Start tracking a new stroke for the 28x28 pipeline
        currentStroke = { points: [{ x: p.x, y: p.y }], tool: currentTool };
    }

    function onPointerMove(e) {
        if (!isDrawing || !drawingAllowed) return;
        const p = getPos(e);

        ctx.beginPath();
        ctx.moveTo(lastX, lastY);
        ctx.lineTo(p.x, p.y);
        ctx.strokeStyle = currentTool === "eraser" ? "#ffffff" : penColor;
        ctx.lineWidth = currentTool === "eraser" ? 20 : penSize;
        ctx.lineCap = "round";
        ctx.lineJoin = "round";
        ctx.stroke();

        // Track coordinate for stroke-based 28x28 rendering
        if (currentStroke) {
            currentStroke.points.push({ x: p.x, y: p.y });
        }

        send({ action: "stroke", points: [{ x: lastX, y: lastY }, { x: p.x, y: p.y }], color: ctx.strokeStyle, width: ctx.lineWidth });
        lastX = p.x; lastY = p.y;
    }

    function onPointerUp(e) {
        // Finalize the current stroke into the history
        if (currentStroke && currentStroke.points.length > 1) {
            allStrokes.push(currentStroke);
        }
        currentStroke = null;
        isDrawing = false;
    }

    function onRemoteStroke(msg) {
        if (!ctx) return;
        const pts = msg.points;
        ctx.beginPath();
        ctx.moveTo(pts[0].x, pts[0].y);
        ctx.lineTo(pts[1].x, pts[1].y);
        ctx.strokeStyle = msg.color;
        ctx.lineWidth = msg.width;
        ctx.lineCap = "round";
        ctx.lineJoin = "round";
        ctx.stroke();
    }

    function sendCanvasData() {
        if (!canvas || !drawingAllowed) return;
        try {
            const pixels = getCanvas28x28FromStrokes();
            send({ action: "draw_data", pixels: pixels });
        } catch (e) { console.error("Canvas error:", e); }
    }

    /**
     * Stroke-based 28x28 rendering.
     * Instead of downscaling the large canvas pixels (which causes severe
     * anti-aliasing blur that destroys fine details on complex drawings),
     * we use the raw stroke coordinates collected during drawing.
     *
     * Process:
     *  1. Compute bounding box from all pen-stroke coordinates.
     *  2. Scale coordinates to fit inside a 20x20 area, centered in 28x28.
     *  3. Redraw strokes on a fresh 28x28 canvas with a fixed line width.
     *  4. Extract pixels and invert (white bg → 0, black stroke → 255).
     *
     * This produces sharp, unbroken lines regardless of drawing size,
     * closely matching the QuickDraw .npy training data format.
     */
    function getCanvas28x28FromStrokes() {
        // Gather all strokes including the one currently being drawn
        const strokesToProcess = [...allStrokes];
        if (currentStroke && currentStroke.points.length > 1) {
            strokesToProcess.push(currentStroke);
        }

        // Collect all PEN stroke points for bounding box calculation
        // (eraser strokes don't define the drawing's extent)
        const penPoints = [];
        for (const stroke of strokesToProcess) {
            if (stroke.tool === "pen") {
                for (const pt of stroke.points) {
                    penPoints.push(pt);
                }
            }
        }

        if (penPoints.length < 2) return new Array(784).fill(0);

        // ── Bounding box from coordinates ─────────────────────────────
        let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
        for (const pt of penPoints) {
            if (pt.x < minX) minX = pt.x;
            if (pt.x > maxX) maxX = pt.x;
            if (pt.y < minY) minY = pt.y;
            if (pt.y > maxY) maxY = pt.y;
        }

        const cropW = maxX - minX;
        const cropH = maxY - minY;

        // If the drawing is essentially a single point/dot
        if (cropW < 1 && cropH < 1) {
            // Draw a centered dot
            const outCanvas = document.createElement("canvas");
            outCanvas.width = 28; outCanvas.height = 28;
            const outCtx = outCanvas.getContext("2d");
            outCtx.fillStyle = "white";
            outCtx.fillRect(0, 0, 28, 28);
            outCtx.fillStyle = "black";
            outCtx.beginPath();
            outCtx.arc(14, 14, 2, 0, Math.PI * 2);
            outCtx.fill();
            return extractInvertedPixels(outCtx);
        }

        // ── Scale to fit 20x20, centered in 28x28 ────────────────────
        const targetSize = 20;
        const scale = targetSize / Math.max(cropW, cropH);
        const scaledW = cropW * scale;
        const scaledH = cropH * scale;
        const offsetX = 4 + (targetSize - scaledW) / 2;
        const offsetY = 4 + (targetSize - scaledH) / 2;

        // ── Create 28x28 canvas and redraw strokes ───────────────────
        const outCanvas = document.createElement("canvas");
        outCanvas.width = 28;
        outCanvas.height = 28;
        const outCtx = outCanvas.getContext("2d");

        // White background
        outCtx.fillStyle = "white";
        outCtx.fillRect(0, 0, 28, 28);

        // Disable image smoothing for crisp, pixel-perfect lines
        outCtx.imageSmoothingEnabled = false;
        outCtx.lineCap = "round";
        outCtx.lineJoin = "round";

        for (const stroke of strokesToProcess) {
            if (stroke.points.length < 2) continue;

            outCtx.beginPath();
            // Pen strokes → black, Eraser strokes → white
            outCtx.strokeStyle = stroke.tool === "eraser" ? "white" : "black";
            // Fixed line width: ~2px matches QuickDraw .npy stroke weight
            outCtx.lineWidth = stroke.tool === "eraser" ? 3 : 2;

            const first = stroke.points[0];
            outCtx.moveTo(
                (first.x - minX) * scale + offsetX,
                (first.y - minY) * scale + offsetY
            );

            for (let i = 1; i < stroke.points.length; i++) {
                const pt = stroke.points[i];
                outCtx.lineTo(
                    (pt.x - minX) * scale + offsetX,
                    (pt.y - minY) * scale + offsetY
                );
            }

            outCtx.stroke();
        }

        return extractInvertedPixels(outCtx);
    }

    /**
     * Extract 784-element pixel array from a 28x28 canvas context.
     * Inverts values so white background → 0, black stroke → 255.
     */
    function extractInvertedPixels(outCtx) {
        const outData = outCtx.getImageData(0, 0, 28, 28).data;
        const pixels = [];

        for (let i = 0; i < outData.length; i += 4) {
            const r = outData[i];
            const g = outData[i + 1];
            const b = outData[i + 2];

            // Invert: White(255) → 0 (background), Black(0) → 255 (stroke)
            const darkest = Math.min(r, g, b);
            let inverted = 255 - darkest;

            // Threshold very faint values to clean 0
            if (inverted < 15) inverted = 0;

            pixels.push(Math.floor(inverted));
        }

        return pixels;
    }

    function onAiGuess(msg) {
        $("#ai-guess-word").textContent = msg.guess;
        const conf = Math.round(msg.confidence);
        $("#ai-confidence").textContent = `${conf}%`;
        const badge = $("#ai-confidence");
        badge.style.background = conf > 80 ? "#66bb6a" : (conf > 50 ? "#ffa726" : "#ef5350");
    }

    function onRoundSolved(msg) {
        Sound.playCorrect();
        if (sendTimer) clearInterval(sendTimer);
        drawingAllowed = false;
        showOverlay('<i class="ph-duotone ph-check-fat"></i>', "Correct!", `Word: ${msg.word} (+${msg.score} pts)`, 3000, "success");
        $("#game-word-display").innerHTML = `<span style="color:#66bb6a">${msg.word}</span>`;
    }

    function renderGamePlayers(players) {
        const container = $("#game-players");
        if (!container) return;
        const sorted = [...players].sort((a, b) => b.score - a.score);
        container.innerHTML = sorted.map(p => `
            <div class="sb-player ${p.player_id === (myRole === 'drawer' ? playerId : '') ? 'active-drawer' : ''}">
                ${renderAvatar(p.avatar_eyes, p.avatar_mouth, p.avatar_skin)}
                <div style="flex:1;">
                    <div class="sb-name">${p.nickname}</div>
                    <div class="sb-score">${p.score} pts</div>
                </div>
                ${p.score >= 1000 ? '<i class="ph-fill ph-star" style="color:#fbc02d"></i>' : ''}
            </div>
        `).join("");
    }

    function onGameOver(msg) {
        Sound.playGameOver();
        showScreen("gameover");
        const container = $("#rankings");
        container.innerHTML = msg.rankings.map((r, i) => `
            <div class="doodle-card" style="padding: 10px; display:flex; align-items:center; gap:15px; border-width:2px; width:100%;">
                <div style="font-size:2rem; font-weight:bold; color:#ffa726;">#${i + 1}</div>
                ${renderAvatar(r.avatar_eyes, r.avatar_mouth, r.avatar_skin)}
                <div style="text-align:left; flex:1;">
                    <div class="sb-name" style="font-size:1.5rem;">${r.nickname}</div>
                    <div class="sb-score" style="font-size:1.2rem;">${r.score} pts</div>
                </div>
                ${i === 0 ? '<i class="ph-fill ph-trophy" style="font-size:2rem; color:#fbc02d;"></i>' : ''}
            </div>
        `).join("");

        if (isHost) {
            $("#btn-play-again").classList.remove("hidden");
            $("#btn-play-again").onclick = () => send({ action: "return_lobby" });
        }
        $("#btn-leave").onclick = () => { ws.close(); location.reload(); };
    }

    function onChatMessage(msg) {
        if (msg.nickname !== nickname) Sound.playPop();
        const html = `<span style="font-weight:bold;">${msg.nickname}:</span> ${msg.message}`;

        // Desktop chat panel
        const div = document.createElement("div");
        div.className = "chat-msg";
        div.innerHTML = html;
        $("#chat-messages").appendChild(div);
        $("#chat-messages").scrollTop = $("#chat-messages").scrollHeight;

        // Mobile: update last message bar
        const lastBar = $("#mobile-chat-last");
        if (lastBar) lastBar.textContent = `${msg.nickname}: ${msg.message}`;

        // Mobile: if popup is open, add message there too
        const mobilePopup = $("#mobile-chat-popup");
        if (mobilePopup && !mobilePopup.classList.contains("hidden")) {
            const mDiv = document.createElement("div");
            mDiv.className = "chat-msg";
            mDiv.innerHTML = html;
            $("#mobile-chat-messages").appendChild(mDiv);
            $("#mobile-chat-messages").scrollTop = $("#mobile-chat-messages").scrollHeight;
        }
    }

    document.addEventListener("DOMContentLoaded", () => {
        showScreen("entry");
        initEntry();
    });

})();
