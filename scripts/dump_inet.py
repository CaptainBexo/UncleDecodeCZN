"""Parse temp/inet *.c0 HTTP cache: extract URL + body preview."""
import glob, os, json, io

INET = r"E:\Games\ChaosZeroNightmare\bin\appdata\cznlive\temp\inet"
OUT = r"D:\UncleDecodeCZN\cache_out"
os.makedirs(OUT, exist_ok=True)

for p in sorted(glob.glob(os.path.join(INET, "*", "*.c0"))):
    d = open(p, "rb").read()
    print("=" * 70)
    print(os.path.basename(p), len(d), "B")
    # header: 0x30 bytes then quoted strings: key1(hex hash), key2(cache key), url
    # find quoted strings
    i = 0x30
    strs = []
    while i < min(len(d), 0x2000):
        if d[i:i+1] == b'"':
            j = d.find(b'"', i+1)
            if 0 < j - i < 2000:
                strs.append(d[i+1:j].decode("latin1"))
                i = j + 1
                continue
        if d[i:i+1] == b']':
            # possible terminator after url
            pass
        i += 1
    for s in strs[:4]:
        print("  STR:", s[:300])
    # guess body: search for JSON object/array start after the last string
    body_start = None
    for s in strs:
        if s.startswith("http"):
            body_start = d.find(b'"', d.find(s.encode()) + len(s) + 2)
    # fallback: find first { or [ followed by plausible json within file after 0x60
    for m in range(0x60, min(len(d), 0x400)):
        if d[m:m+1] in (b"{", b"["):
            try:
                json.loads(d[m:].decode("utf-8", "strict"))
                body_start = m
                break
            except Exception:
                continue
    if body_start is not None:
        body = d[body_start:]
        print(f"  BODY@{body_start} ({len(body)} B) preview:")
        print(textwrap_indent if False else body[:600].decode("utf-8", "replace"))
        name = os.path.basename(p) + ".body"
        open(os.path.join(OUT, name), "wb").write(body)
        print("  saved ->", os.path.join(OUT, name))
    else:
        print("  no JSON body found; hex tail:")
        print(" ", d[-200:].hex())
