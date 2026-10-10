"""Transcribe the Zoom audio with faster-whisper; write timestamped segments as they come."""
import sys, time
from faster_whisper import WhisperModel

audio, out, model_name = sys.argv[1], sys.argv[2], (sys.argv[3] if len(sys.argv) > 3 else "small")
t0 = time.time()
model = WhisperModel(model_name, device="cpu", compute_type="int8", cpu_threads=6)
segments, info = model.transcribe(
    audio, language="en", beam_size=2, vad_filter=True,
    vad_parameters=dict(min_silence_duration_ms=700),
    condition_on_previous_text=False,
)
print(f"model={model_name} duration={info.duration:.0f}s", flush=True)

def ts(s):
    m, s = divmod(int(s), 60); h, m = divmod(m, 60)
    return f"{h:d}:{m:02d}:{s:02d}"

with open(out, "w") as f:
    for seg in segments:
        line = f"[{ts(seg.start)} - {ts(seg.end)}] {seg.text.strip()}"
        f.write(line + "\n"); f.flush()
        if int(seg.start) % 300 < 5:
            print(f"... at {ts(seg.start)} ({time.time()-t0:.0f}s elapsed)", flush=True)
print(f"done in {time.time()-t0:.0f}s", flush=True)
