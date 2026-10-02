"""Probe SCSP container: decompress with the CSNRipper LZ block algorithm and dump the inner layout."""
import sys, struct, os
sys.path.insert(0, os.path.dirname(__file__))
from czn_pack import Pack


def decompress_block(src, dec_len):
    out = bytearray(); i = 0; n = len(src)
    while i < n:
        token = src[i]; i += 1
        lit = token >> 4
        if lit == 15:
            b = 255
            while i < n and b == 255:
                b = src[i]; i += 1; lit += b
        if lit:
            if i + lit > n: break
            out += src[i:i+lit]; i += lit
            if i >= n: break
        if i + 2 > n: break
        off = src[i] | (src[i+1] << 8); i += 2
        if off == 0: break
        mlen = (token % 16) + 4
        if (token % 16) == 15:
            b = 255
            while i < n and b == 255:
                b = src[i]; i += 1; mlen += b
        start = len(out) - off
        for j in range(mlen):
            out.append(out[start + j])
    return bytes(out[:dec_len])


def main():
    P = Pack()
    for path in ['effect/lenore_1041_ug_eff_pat2.scsp', 'model/1005_battle_ready.scsp', 'model/1005001.scsp']:
        d = P.extract(path)
        dec_len, comp_len = struct.unpack_from('<II', d, 0)
        dec = decompress_block(d[8:8+comp_len], dec_len)
        print(f'== {path}: file={len(d):,} dec_len={dec_len:,} comp={comp_len:,} decompressed={len(dec):,} ({100*len(dec)/dec_len:.1f}%)')
        print('   head hex:', dec[:32].hex())
        i = dec.find(b'3.8.')
        if i >= 0:
            print('   version @', i, ':', dec[i:i+26])
        i = dec.find(b'scsp')
        if i >= 0:
            print('   scsp magic @', i, ':', dec[i:i+12])
        so, sl = struct.unpack_from('<II', dec, 0)
        print(f'   u32@0={so:,} u32@4={sl:,} floats@0x16,0x1A={struct.unpack_from("<ff", dec, 0x16)}')


if __name__ == '__main__':
    main()
