try {
    const AudioContext = window.AudioContext || window.webkitAudioContext;

    if (AudioContext) {
        class SoundManager {
            constructor() {
                this.ctx = new AudioContext();
                this.masterGain = this.ctx.createGain();
                this.masterGain.gain.value = 0.3; // Default volume
                this.masterGain.connect(this.ctx.destination);
            }

            playTone(freq, type, duration, startTime = 0) {
                if (this.ctx.state === 'suspended') this.ctx.resume();
                const osc = this.ctx.createOscillator();
                const gain = this.ctx.createGain();

                osc.type = type;
                osc.frequency.setValueAtTime(freq, this.ctx.currentTime + startTime);

                gain.gain.setValueAtTime(0.1, this.ctx.currentTime + startTime);
                gain.gain.exponentialRampToValueAtTime(0.01, this.ctx.currentTime + startTime + duration);

                osc.connect(gain);
                gain.connect(this.masterGain);

                osc.start(this.ctx.currentTime + startTime);
                osc.stop(this.ctx.currentTime + startTime + duration);
            }

            playClick() { this.playTone(800, 'square', 0.05); }

            playJoin() {
                this.playTone(400, 'sine', 0.1, 0);
                this.playTone(600, 'sine', 0.2, 0.1);
            }

            playLeave() {
                this.playTone(600, 'sine', 0.1, 0);
                this.playTone(400, 'sine', 0.2, 0.1);
            }

            playCorrect() {
                if (this.ctx.state === 'suspended') this.ctx.resume();
                const now = this.ctx.currentTime;

                const osc = this.ctx.createOscillator();
                const gain = this.ctx.createGain();

                osc.frequency.setValueAtTime(523.25, now); // C5
                osc.frequency.setValueAtTime(1046.50, now + 0.1); // C6

                gain.gain.setValueAtTime(0.1, now);
                gain.gain.linearRampToValueAtTime(0, now + 0.5);

                osc.connect(gain);
                gain.connect(this.masterGain);

                osc.start(now);
                osc.stop(now + 0.5);
            }

            playTimeUp() { this.playTone(150, 'sawtooth', 0.5); }
            playTick() { this.playTone(1000, 'square', 0.03); }
        }

        window.soundManager = new SoundManager();
        console.log("SoundManager initialized");
    } else {
        console.warn("Web Audio API not supported");
        window.soundManager = null;
    }
} catch (e) {
    console.error("SoundManager init error:", e);
    window.soundManager = null;
}
