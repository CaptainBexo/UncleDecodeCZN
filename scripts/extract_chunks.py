"""Proper .ssrc extractor.

Layout per chunk:
  [entry]* [16B trailer: 'SSRC' + u32 chunk_id + u64 hash]
  entry = zstd frame (<= raw content) zero-padded to 16-byte alignment.
  Raw chunks (e.g. base_large parts): [raw bytes][16B trailer], no frames.

Outputs:
  decoded/<chunk>.bin          concatenated decompressed frames (or raw)
  frames.jsonl                 per-frame: chunk, idx, in_off, in_len, out_off, out_len
"""
import glob, json, os, sys
import zstandard as zstd

CH = r"E:\Games\ChaosZeroNightmare\bin\appdata\cznlive\gameres\chunks"
OUT = r"D:\UncleDecodeCZN\decoded"
MAGIC = b"\x28\xb5\x2f\xfd"
os.makedirs(OUT, exist_ok=True)

log = open(os.path.join(OUT, "frames.jsonl"), "w", encoding="utf-8")
total_in = total_out = 0

for p in sorted(glob.glob(os.path.join(CH, "*.ssrc"))):
    name = os.path.basename(p)[:-5]
    d = open(p, "rb").read()
    assert d[-16:-12] == b"SSRC", f"{name}: no SSRC trailer"
    chunk_id = int.from_bytes(d[-12:-8], "little")
    payload = d[:-16]
    out_path = os.path.join(OUT, name + ".bin")
    out = open(out_path, "wb")
    idx = 0
    pos = 0
    if payload[:4] == MAGIC:
        while pos < len(payload):
            if payload[pos:pos+4] != MAGIC:
                # expect zero padding then next frame; scan to next 16-boundary magic
                nxt = payload.find(MAGIC, pos, pos + 32)
                if nxt == -1:
                    break
                pos = nxt
            dobj = zstd.ZstdDecompressor().decompressobj()
            data = dobj.decompress(payload[pos:])
            unc = len(payload[pos:]) - len(dobj.unused_data)
            log.write(json.dumps({"chunk": name, "idx": idx, "in_off": pos,
                                  "in_len": unc, "out_off": out.tell(),
                                  "out_len": len(data), "chunk_id": chunk_id}) + "\n")
            out.write(data)
            pos += unc
            pos = (pos + 15) & ~15
            idx += 1
    else:  # raw chunk
        log.write(json.dumps({"chunk": name, "idx": 0, "in_off": 0,
                              "in_len": len(payload), "out_off": 0,
                              "out_len": len(payload), "chunk_id": chunk_id,
                              "raw": True}) + "\n")
        out.write(payload)
        idx = 1
    out.close()
    sz = os.path.getsize(out_path)
    total_in += len(d)
    total_out += sz
    print(f"{name:32s} id={chunk_id:3d} frames={idx:5d} out={sz:>13,}")

log.close()
print(f"\nTOTAL in={total_in:,} out={total_out:,}")
