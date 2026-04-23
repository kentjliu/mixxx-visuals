/**
 * Mixxx Visuals Bridge
 *
 * Reads deck state via ControlProxy every 50 ms and broadcasts it as
 * a proprietary SysEx message on whatever MIDI output port Mixxx has
 * selected for this mapping (IAC Driver Bus 1 on macOS).
 *
 * SysEx format (10 bytes):
 *   F0 7D 01 <deck> <bpm_msb> <bpm_lsb> <beat> <vol> <play> F7
 *
 *   deck     : 0 = Channel1, 1 = Channel2
 *   bpm_msb  : high 7 bits of (round(bpm * 10))
 *   bpm_lsb  : low  7 bits of (round(bpm * 10))
 *              → reconstruct: bpm = ((msb << 7) | lsb) / 10.0
 *              max encodable: 1638.3 BPM — plenty of headroom
 *   beat     : round(beat_distance * 127)   — 0 = just fired, 127 = next imminent
 *   vol      : round(volume * 127)
 *   play     : 1 if playing, 0 if stopped
 *
 * Setup (macOS):
 *   1. Open Audio MIDI Setup → Window → Show MIDI Studio
 *   2. Double-click IAC Driver → check "Device is online"
 *   3. Copy this file + the .xml to ~/Library/Containers/org.mixxx.mixxx/
 *      Data/Library/Application Support/Mixxx/controllers/
 *   4. Mixxx → Preferences → Controllers → enable "Mixxx Visuals Bridge"
 *      and set output port to "IAC Driver Bus 1"
 */

var MixxxVisualsBridge = {};

MixxxVisualsBridge.DECKS = ["[Channel1]", "[Channel2]"];
MixxxVisualsBridge.TIMER_MS = 50;
MixxxVisualsBridge._timer = null;

MixxxVisualsBridge.init = function (id, debugging) {
    print("[MixxxVisualsBridge] init – starting " + MixxxVisualsBridge.TIMER_MS + " ms timer");
    MixxxVisualsBridge._timer = engine.beginTimer(
        MixxxVisualsBridge.TIMER_MS,
        MixxxVisualsBridge.tick
    );
};

MixxxVisualsBridge.shutdown = function (id) {
    if (MixxxVisualsBridge._timer !== null) {
        engine.stopTimer(MixxxVisualsBridge._timer);
        MixxxVisualsBridge._timer = null;
    }
    print("[MixxxVisualsBridge] shutdown");
};

MixxxVisualsBridge._tickCount = 0;

MixxxVisualsBridge.tick = function () {
    MixxxVisualsBridge._tickCount++;

    // Log every 100 ticks (~5 s) to confirm the timer is firing
    if (MixxxVisualsBridge._tickCount % 100 === 1) {
        print("[MixxxVisualsBridge] tick #" + MixxxVisualsBridge._tickCount);
    }

    var decks = MixxxVisualsBridge.DECKS;
    for (var i = 0; i < decks.length; i++) {
        var group = decks[i];

        var bpm       = engine.getValue(group, "bpm")            || 0.0;
        var beatDist  = engine.getValue(group, "beat_distance")  || 0.0;
        var play      = engine.getValue(group, "play_indicator") ? 1 : 0;
        var volume    = engine.getValue(group, "volume")         || 0.0;

        // Clamp + encode BPM as 14-bit integer (BPM × 10)
        var bpmInt = Math.round(Math.min(16383, Math.max(0, bpm * 10)));
        var bpmMsb = (bpmInt >> 7) & 0x7F;
        var bpmLsb = bpmInt & 0x7F;

        // Encode beat_distance and volume as 7-bit
        var beatByte = Math.round(Math.min(1.0, Math.max(0.0, beatDist)) * 127);
        var volByte  = Math.round(Math.min(1.0, Math.max(0.0, volume))  * 127);

        // SysEx packet: F0 7D 01 <deck> <bpmMsb> <bpmLsb> <beat> <vol> <play> F7
        var msg = [0xF0, 0x7D, 0x01, i, bpmMsb, bpmLsb, beatByte, volByte, play, 0xF7];
        midi.sendSysexMsg(msg, msg.length);

        // Also send a plain CC so we can verify basic MIDI routing works
        // CC 20 on channel 1: deck index; CC 21: bpm MSB; CC 22: bpm LSB
        midi.sendShortMsg(0xB0, 20 + i * 3,     i);
        midi.sendShortMsg(0xB0, 20 + i * 3 + 1, bpmMsb);
        midi.sendShortMsg(0xB0, 20 + i * 3 + 2, bpmLsb);
    }
};
