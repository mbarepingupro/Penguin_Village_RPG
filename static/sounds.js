const GameSounds = {
    _ctx: null,

    _resumePromise: null,

    getCtx() {
        try {
            if (!this._ctx || this._ctx.state === 'closed') {
                this._ctx = new (window.AudioContext || window.webkitAudioContext)();
            }
            if (this._ctx.state === 'suspended') {
                this._resumePromise = this._ctx.resume();
            }
        } catch(e) { return null; }
        return this._ctx;
    },

    // Returns a Promise that resolves once the AudioContext is running.
    // Safe to call from any context; resolves immediately if already running.
    ensureRunning() {
        const ctx = this.getCtx();
        if (!ctx) return Promise.resolve();
        if (ctx.state === 'running') return Promise.resolve();
        return (this._resumePromise || ctx.resume());
    },

    _play(config) {
        if (window._soundMuted) return;
        try {
            const ctx = this.getCtx();
            if (!ctx) return;
            const now = ctx.currentTime + 0.02;
            config.notes.forEach(note => {
                const osc = ctx.createOscillator();
                const gain = ctx.createGain();
                osc.connect(gain);
                gain.connect(ctx.destination);
                osc.type = note.type || 'square';
                const t = now + (note.time || 0);
                osc.frequency.setValueAtTime(note.freq, t);
                if (note.freqEnd) {
                    osc.frequency.linearRampToValueAtTime(note.freqEnd, t + (note.dur || 0.1));
                }
                gain.gain.setValueAtTime(note.vol || 0.15, t);
                gain.gain.exponentialRampToValueAtTime(0.001, t + (note.dur || 0.1));
                osc.start(t);
                osc.stop(t + (note.dur || 0.1) + 0.01);
            });
        } catch(e) {}
    },

    uiClick()    { this._play({notes: [{freq:800, dur:0.05, type:'sine', vol:0.08}]}); },
    uiHover()    { this._play({notes: [{freq:600, dur:0.03, type:'sine', vol:0.04}]}); },
    modalOpen()  { this._play({notes: [{freq:400, dur:0.08, type:'sine', vol:0.10}, {freq:600, dur:0.08, type:'sine', vol:0.10, time:0.06}]}); },
    modalClose() { this._play({notes: [{freq:600, dur:0.08, type:'sine', vol:0.08}, {freq:400, dur:0.08, type:'sine', vol:0.08, time:0.06}]}); },
    tabSwitch()  { this._play({notes: [{freq:500, dur:0.06, type:'triangle', vol:0.08}, {freq:700, dur:0.06, type:'triangle', vol:0.08, time:0.04}]}); },
    error()      { this._play({notes: [{freq:200, dur:0.15, type:'square', vol:0.10}, {freq:150, dur:0.15, type:'square', vol:0.10, time:0.10}]}); },

    footstep() {
        const freq = 300 + Math.random() * 100;
        this._play({notes: [{freq, dur:0.06, type:'sine', vol:0.05}]});
    },
    moveClick()   { this._play({notes: [{freq:500, dur:0.05, type:'sine', vol:0.08}, {freq:700, dur:0.05, type:'sine', vol:0.06, time:0.04}]}); },
    moveBlocked() { this._play({notes: [{freq:200, dur:0.10, type:'square', vol:0.08}]}); },
    buildingClick() { this._play({notes: [{freq:400, dur:0.08, type:'triangle', vol:0.10}, {freq:550, dur:0.10, type:'triangle', vol:0.10, time:0.06}, {freq:700, dur:0.08, type:'triangle', vol:0.08, time:0.14}]}); },
    mapZoom()     { this._play({notes: [{freq:400, freqEnd:600, dur:0.08, type:'sine', vol:0.04}]}); },

    jobStart()   { this._play({notes: [{freq:300, dur:0.10, type:'triangle', vol:0.12}, {freq:400, dur:0.10, type:'triangle', vol:0.12, time:0.08}, {freq:500, dur:0.15, type:'triangle', vol:0.10, time:0.16}]}); },
    jobCollect() { this._play({notes: [{freq:523, dur:0.10, type:'square', vol:0.15}, {freq:659, dur:0.10, type:'square', vol:0.15, time:0.08}, {freq:784, dur:0.10, type:'square', vol:0.12, time:0.16}, {freq:1047, dur:0.20, type:'square', vol:0.12, time:0.24}]}); },
    collectTink() {
        const freq = 1200 + Math.random() * 400;
        this._play({notes: [{freq, dur:0.06, type:'sine', vol:0.05}]});
    },

    combatStart()   { this._play({notes: [{freq:200, dur:0.15, type:'square', vol:0.15}, {freq:200, freqEnd:400, dur:0.20, type:'square', vol:0.15, time:0.10}]}); },
    combatRoll()    { this._play({notes: [{freq:300, freqEnd:800, dur:0.50, type:'sawtooth', vol:0.06}]}); },
    combatVictory() { this._play({notes: [{freq:523, dur:0.12, type:'square', vol:0.18}, {freq:659, dur:0.12, type:'square', vol:0.18, time:0.10}, {freq:784, dur:0.12, type:'square', vol:0.15, time:0.20}, {freq:1047, dur:0.30, type:'square', vol:0.15, time:0.30}]}); },
    combatDefeat()  { this._play({notes: [{freq:400, dur:0.15, type:'square', vol:0.15}, {freq:300, dur:0.15, type:'square', vol:0.12, time:0.12}, {freq:200, dur:0.25, type:'square', vol:0.10, time:0.24}]}); },

    minigameStart()    { this._play({notes: [{freq:400, dur:0.08, type:'square', vol:0.12}, {freq:500, dur:0.08, type:'square', vol:0.12, time:0.06}, {freq:600, dur:0.08, type:'square', vol:0.12, time:0.12}, {freq:800, dur:0.15, type:'square', vol:0.10, time:0.18}]}); },
    minigameHit()      { const freq = 800 + Math.random() * 400; this._play({notes: [{freq, dur:0.06, type:'sine', vol:0.10}]}); },
    minigameMiss()     { this._play({notes: [{freq:200, dur:0.10, type:'square', vol:0.08}]}); },
    minigameCombo()    { this._play({notes: [{freq:600, dur:0.05, type:'sine', vol:0.10}, {freq:900, dur:0.08, type:'sine', vol:0.10, time:0.04}]}); },
    minigameComplete() { this._play({notes: [{freq:523, dur:0.10, type:'triangle', vol:0.12}, {freq:659, dur:0.10, type:'triangle', vol:0.12, time:0.08}, {freq:784, dur:0.15, type:'triangle', vol:0.10, time:0.16}, {freq:1047, dur:0.25, type:'triangle', vol:0.10, time:0.26}]}); },

    purchase()    { this._play({notes: [{freq:800, dur:0.06, type:'square', vol:0.12}, {freq:1200, dur:0.06, type:'square', vol:0.12, time:0.05}, {freq:1600, dur:0.10, type:'square', vol:0.10, time:0.10}]}); },
    cantAfford()  { this._play({notes: [{freq:200, dur:0.15, type:'square', vol:0.10}, {freq:180, dur:0.20, type:'square', vol:0.08, time:0.12}]}); },

    equip()   { this._play({notes: [{freq:1000, dur:0.04, type:'square', vol:0.10}, {freq:1500, dur:0.06, type:'square', vol:0.08, time:0.03}, {freq:2000, dur:0.04, type:'sine', vol:0.06, time:0.06}]}); },
    unequip() { this._play({notes: [{freq:1500, dur:0.04, type:'square', vol:0.08}, {freq:1000, dur:0.06, type:'square', vol:0.08, time:0.03}]}); },
    wear()    { this._play({notes: [{freq:400, freqEnd:200, dur:0.15, type:'sine', vol:0.08}]}); },
    unwear()  { this._play({notes: [{freq:200, freqEnd:400, dur:0.15, type:'sine', vol:0.06}]}); },
    forge()   { this._play({notes: [{freq:150, dur:0.10, type:'sawtooth', vol:0.10}, {freq:200, dur:0.08, type:'square', vol:0.12, time:0.10}, {freq:800, dur:0.05, type:'sine', vol:0.10, time:0.18}, {freq:1200, dur:0.10, type:'sine', vol:0.08, time:0.22}]}); },

    iglooVisit()      { this._play({notes: [{freq:523, dur:0.15, type:'sine', vol:0.10}, {freq:659, dur:0.20, type:'sine', vol:0.10, time:0.12}]}); },
    socialModeChange(){ this._play({notes: [{freq:500, dur:0.06, type:'triangle', vol:0.08}, {freq:650, dur:0.08, type:'triangle', vol:0.08, time:0.05}]}); },

    hotelRest() { this._play({notes: [{freq:400, dur:0.10, type:'sine', vol:0.10}, {freq:500, dur:0.10, type:'sine', vol:0.10, time:0.08}, {freq:600, dur:0.10, type:'sine', vol:0.10, time:0.16}, {freq:800, dur:0.20, type:'sine', vol:0.08, time:0.24}]}); },

    donate() { this._play({notes: [{freq:300, dur:0.08, type:'triangle', vol:0.10}, {freq:450, dur:0.10, type:'triangle', vol:0.10, time:0.06}, {freq:600, dur:0.12, type:'triangle', vol:0.08, time:0.14}]}); },

    levelUp() { this._play({notes: [{freq:100, freqEnd:200, dur:0.50, type:'square', vol:0.08}, {freq:523, dur:0.15, type:'square', vol:0.18, time:0.50}, {freq:659, dur:0.15, type:'square', vol:0.18, time:0.65}, {freq:784, dur:0.15, type:'square', vol:0.15, time:0.80}, {freq:1047, dur:0.30, type:'square', vol:0.15, time:0.95}, {freq:784, dur:0.10, type:'square', vol:0.10, time:1.10}, {freq:1047, dur:0.40, type:'square', vol:0.12, time:1.20}]}); },
    achievement()      { this._play({notes: [{freq:440, dur:0.12, type:'square', vol:0.15}, {freq:554, dur:0.12, type:'square', vol:0.15, time:0.10}, {freq:659, dur:0.12, type:'square', vol:0.12, time:0.20}, {freq:880, dur:0.25, type:'square', vol:0.12, time:0.30}]}); },
    firstKill()        { this._play({notes: [{freq:330, dur:0.10, type:'square', vol:0.12}, {freq:440, dur:0.10, type:'square', vol:0.12, time:0.08}, {freq:660, dur:0.20, type:'square', vol:0.12, time:0.16}]}); },
    secretDiscovered() { this._play({notes: [{freq:300, dur:0.20, type:'sine', vol:0.10}, {freq:450, dur:0.20, type:'sine', vol:0.10, time:0.15}, {freq:600, dur:0.20, type:'sine', vol:0.10, time:0.30}, {freq:900, dur:0.35, type:'sine', vol:0.10, time:0.45}]}); },
    streak()           { this._play({notes: [{freq:440, dur:0.10, type:'triangle', vol:0.10}, {freq:550, dur:0.10, type:'triangle', vol:0.10, time:0.08}, {freq:660, dur:0.15, type:'triangle', vol:0.10, time:0.16}]}); },
    buildingLevelUp()  { this._play({notes: [{freq:262, dur:0.15, type:'triangle', vol:0.12}, {freq:330, dur:0.15, type:'triangle', vol:0.12, time:0.12}, {freq:392, dur:0.15, type:'triangle', vol:0.10, time:0.24}, {freq:523, dur:0.30, type:'triangle', vol:0.10, time:0.36}]}); },

    welcomeBack()    { this._play({notes: [{freq:400, dur:0.15, type:'sine', vol:0.10}, {freq:500, dur:0.15, type:'sine', vol:0.10, time:0.10}, {freq:650, dur:0.20, type:'sine', vol:0.08, time:0.20}]}); },
    mayorAppears()   { this._play({notes: [{freq:350, dur:0.10, type:'triangle', vol:0.10}, {freq:440, dur:0.10, type:'triangle', vol:0.10, time:0.08}, {freq:550, dur:0.15, type:'triangle', vol:0.08, time:0.16}]}); },
    tutorialAdvance(){ this._play({notes: [{freq:500, dur:0.08, type:'sine', vol:0.08}, {freq:700, dur:0.10, type:'sine', vol:0.08, time:0.06}]}); },
    typewriterTick() {
        if (Math.random() > 0.3) return;
        this._play({notes: [{freq: 800 + Math.random() * 200, dur:0.02, type:'sine', vol:0.02}]});
    },

    furniturePlace()  { this._play({notes: [{freq:300, dur:0.08, type:'sine', vol:0.10}, {freq:450, dur:0.10, type:'sine', vol:0.08, time:0.06}]}); },
    furnitureRemove() { this._play({notes: [{freq:450, dur:0.08, type:'sine', vol:0.08}, {freq:300, dur:0.10, type:'sine', vol:0.06, time:0.06}]}); },
    iglooUpgrade()    { this._play({notes: [{freq:300, dur:0.10, type:'triangle', vol:0.12}, {freq:400, dur:0.10, type:'triangle', vol:0.12, time:0.08}, {freq:500, dur:0.10, type:'triangle', vol:0.10, time:0.16}, {freq:700, dur:0.20, type:'triangle', vol:0.10, time:0.24}]}); },

    missionClaim() { this._play({notes: [{freq:600, dur:0.08, type:'square', vol:0.12}, {freq:800, dur:0.08, type:'square', vol:0.12, time:0.06}, {freq:1000, dur:0.12, type:'square', vol:0.10, time:0.12}]}); },
    streakClaim()  { this._play({notes: [{freq:500, dur:0.08, type:'triangle', vol:0.10}, {freq:650, dur:0.08, type:'triangle', vol:0.10, time:0.06}, {freq:800, dur:0.12, type:'triangle', vol:0.10, time:0.12}]}); },

    overworldOpen()   { this._play({notes: [{freq:200, freqEnd:100, dur:0.30, type:'sine', vol:0.08}]}); },
    overworldHover()  { this._play({notes: [{freq:500, dur:0.04, type:'sine', vol:0.04}]}); },
    overworldLocked() { this._play({notes: [{freq:150, dur:0.15, type:'square', vol:0.08}]}); },
    overworldEnter()  { this._play({notes: [{freq:400, dur:0.08, type:'triangle', vol:0.10}, {freq:550, dur:0.10, type:'triangle', vol:0.10, time:0.06}]}); },

    titleEquip() { this._play({notes: [{freq:523, dur:0.10, type:'sine', vol:0.10}, {freq:659, dur:0.10, type:'sine', vol:0.10, time:0.08}, {freq:784, dur:0.15, type:'sine', vol:0.08, time:0.16}]}); },

    chime() { this._play({notes: [{freq:880, dur:0.10, type:'sine', vol:0.10}, {freq:1100, dur:0.15, type:'sine', vol:0.08, time:0.08}]}); },
    // Each of the 6 runes gets a distinct pentatonic pitch (A4–C6).
    // Awaits AudioContext resume before scheduling — fixes silent reveal phase
    // when the context is still 'suspended' at game start.
    runeChime(idx) {
        const FREQS = [523, 659, 784, 880, 1047, 440];
        const freq = FREQS[idx & 7] || 523;
        const self = this;
        const doPlay = () => self._play({notes: [
            {freq,           dur: 0.22, type:'sine', vol: 0.13},
            {freq: freq*1.5, dur: 0.12, type:'sine', vol: 0.05, time: 0.16},
        ]});
        const ctx = this.getCtx();
        if (!ctx) return;
        if (ctx.state === 'running') {
            doPlay();
        } else {
            this.ensureRunning().then(doPlay);
        }
    },
};

// Warm up AudioContext on first user interaction
(function() {
    function _warmUp() { try { GameSounds.getCtx(); } catch(e) {} }
    document.addEventListener('click',      _warmUp, { once: true, capture: true });
    document.addEventListener('keydown',    _warmUp, { once: true, capture: true });
    document.addEventListener('touchstart', _warmUp, { once: true, capture: true });
})();

// Backward-compatible Sounds shim — keeps existing onclick="Sounds.toggleMute()" working
const Sounds = {
    get muted() { return !!window._soundMuted; },
    getCtx()        { return GameSounds.getCtx(); },
    toggleMute() {
        window._soundMuted = !window._soundMuted;
        const btn = document.getElementById('mute-btn');
        if (btn) btn.textContent = window._soundMuted ? '🔇' : '🔊';
        return window._soundMuted;
    },
    collect()            { GameSounds.jobCollect(); },
    streak()             { GameSounds.streak(); },
    donate()             { GameSounds.donate(); },
    levelUp()            { GameSounds.levelUp(); },
    buildingLevelUp()    { GameSounds.buildingLevelUp(); },
    rest()               { GameSounds.hotelRest(); },
    equip()              { GameSounds.equip(); },
    purchase()           { GameSounds.purchase(); },
    doorbell()           { GameSounds.iglooVisit(); },
    relationshipLevelUp(){ GameSounds.achievement(); },
    socialModeChange()   { GameSounds.socialModeChange(); },
    wear()               { GameSounds.wear(); },
    unwear()             { GameSounds.unwear(); },
    combatStart()        { GameSounds.combatStart(); },
    victory()            { GameSounds.combatVictory(); },
    defeat()             { GameSounds.combatDefeat(); },
    chime()              { GameSounds.chime(); },
};

// Global function aliases
window.playCombatStartSound = () => GameSounds.combatStart();
window.playVictorySound     = () => GameSounds.combatVictory();
window.playDefeatSound      = () => GameSounds.combatDefeat();
window.playCollectTink      = () => GameSounds.collectTink();
window.playLevelUpFanfare   = () => GameSounds.levelUp();
