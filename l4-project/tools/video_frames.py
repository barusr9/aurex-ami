"""Save one video frame every N seconds as a small JPEG, to see what was shared on screen."""
import sys, os, av

video, outdir, step = sys.argv[1], sys.argv[2], int(sys.argv[3])
os.makedirs(outdir, exist_ok=True)
c = av.open(video)
s = c.streams.video[0]
s.thread_type = "AUTO"; s.codec_context.skip_frame = "NONKEY"
next_t, n = 0.0, 0
for frame in c.decode(s):
    t = float(frame.pts * s.time_base)
    if t >= next_t:
        img = frame.to_image()
        img.thumbnail((960, 540))
        m, sec = divmod(int(t), 60)
        img.save(os.path.join(outdir, f"f_{m:03d}m{sec:02d}s.jpg"), quality=70)
        n += 1
        next_t += step
print("frames:", n)
