"""SCSP (.scsp) Spine skeleton -> standard Spine 3.8 JSON.

Python port of SCSPParser.cpp from Chaos-Zero-Nightmare-ASSet-Ripper
(https://github.com/cznrip/Chaos-Zero-Nightmare-ASSet-Ripper, MIT, author akioukun),
ported 2026-10-02. 1:1 with the C++: same constants, same read order, same emitted
structure (nlohmann::ordered_json insertion order is preserved by plain dicts).

Container: u32 dec_len, u32 comp_len at offset 0, then an LZ4 block. The inner
'scsp1u' payload holds a header (0x08 magic 'scsp', 0x0C version u32, 0x12/0x16
width/height f32, string table refs), the string table at 8+string_offset, and the
section stream starting at 0x08 + 0x62.

Public: unwrap(data) -> bytes, to_json(inner) -> dict, convert(path) -> dict.
"""
import json
import math
import os
import struct
import sys

import lz4.block

U32_FF = 0xFFFFFFFF
TRANSFORM_MODES = {0: "normal", 1: "onlyTranslation", 2: "noRotationOrReflection",
                   3: "noScale", 4: "noScaleOrReflection"}
BLEND_MODES = {0: "normal", 1: "additive", 2: "multiply", 3: "screen"}
POS_MODES = {0: "fixed", 1: "percent"}
SPACING_MODES = {0: "length", 1: "fixed", 2: "percent"}
ROTATE_MODES = {0: "tangent", 1: "chain", 2: "chainScale"}


# --- outer container -------------------------------------------------------

def unwrap(data):
    """u32 dec_len + u32 comp_len (read as C++ int32), then LZ4 block (mirrors DecompressSCSP)."""
    if len(data) < 8:
        raise ValueError("SCSP file too small")
    dec_len, comp_len = struct.unpack_from("<ii", data, 0)
    if comp_len < 0 or dec_len <= 0:
        raise ValueError("Invalid SCSP header")
    if 8 + comp_len > len(data):
        raise ValueError("Compressed block exceeds file size")
    return lz4.block.decompress(data[8:8 + comp_len], uncompressed_size=dec_len)


# --- primitives (mirror read_le / read_cstr / round_float / *_to_hex) -------

def _f(buf, pos):
    return struct.unpack_from("<f", buf, pos)[0]


def _u16(buf, pos):
    return struct.unpack_from("<H", buf, pos)[0]


def _i16(buf, pos):
    return struct.unpack_from("<h", buf, pos)[0]


def _i16of(v):
    """C++ implicit uint16->int16_t conversion (map lookups); wraps >= 0x8000."""
    return v - 0x10000 if v >= 0x8000 else v


def _u32(buf, pos):
    return struct.unpack_from("<I", buf, pos)[0]


def _u8(buf, pos):
    return buf[pos]


def _cstr(buf, start, end):
    """C++ bounds read_cstr at `end`, but returns the NUL-trimmed string at `start`."""
    if start >= end:
        return ""
    n = buf.find(b"\x00", start, end)
    if n < 0:
        n = end
    return buf[start:n].decode("utf-8", "replace")


def _c_round(x):
    """std::round: half away from zero (Python's round() is banker's)."""
    return math.floor(x + 0.5) if x >= 0 else math.ceil(x - 0.5)


def _round_float(value, decimals=6):
    rounded = _c_round(value)
    if abs(value - rounded) < 1e-5:
        return rounded
    m = 10.0 ** decimals
    return _c_round(value * m) / m


def _clamp01(x):
    return 0.0 if x < 0.0 else (1.0 if x > 1.0 else x)


def _bytes_hex(r, g, b, a=None):
    v = [_clamp01(x) for x in ((r, g, b) if a is None else (r, g, b, a))]
    return "".join(f"{int(_c_round(x * 255.0)) & 0xFF:02X}" for x in v)


def _read_f32_array(buf, pos, count):
    """C++ read_f32_array: silently truncates at buf end, returns (arr, newpos)."""
    arr = []
    for _ in range(count):
        if pos + 4 > len(buf):
            break
        arr.append(_f(buf, pos))
        pos += 4
    return arr, pos


def _bezier_from_spine_block(block):
    """C++ bezier_from_spine_block -> (cx1, cy1, cx2, cy2) or None."""
    if len(block) < 19:
        return None
    x0, y0 = block[1], block[2]
    x1, y1 = block[3], block[4]
    x2, y2 = block[5], block[6]
    ddfx = x1 - 2.0 * x0
    dddfx = x2 - 3.0 * x1 + 3.0 * x0
    ddfy = y1 - 2.0 * y0
    dddfy = y2 - 3.0 * y1 + 3.0 * y0
    h = 1.0 / 10.0
    A = 3.0 * h * h
    B = 6.0 * h * h * h
    Ux = (dddfx / B - 1.0) / 3.0
    Vx = (ddfx - dddfx) / (2.0 * A)
    Uy = (dddfy / B - 1.0) / 3.0
    Vy = (ddfy - dddfy) / (2.0 * A)
    return (_clamp01(-Vx - Ux), _clamp01(-Vy - Uy), _clamp01(-Vx - 2.0 * Ux), _clamp01(-Vy - 2.0 * Uy))


def _add_curve(i, curves, frame):
    start = i * 19
    end = start + 19
    if end > len(curves):
        return
    b = curves[start:end]
    if b[0] == 1.0:
        frame["curve"] = "stepped"
    elif b[0] == 2.0:
        out = _bezier_from_spine_block(b)
        if out is not None:
            frame["curve"] = _round_float(out[0])
            frame["c2"] = _round_float(out[1])
            frame["c3"] = _round_float(out[2])
            frame["c4"] = _round_float(out[3])


def _merge_vertex_attachment(bones, verts):
    """C++ 'bones' walk: [nn, b0,x,y,w, b1,x,y,w, ...]; vf can walk past verts end."""
    if bones:
        jv = []
        i = 0
        vf = 0
        while i < len(bones):
            c = bones[i]
            i += 1
            jv.append(c)
            for _ in range(c):
                jv.append(bones[i]); i += 1
                jv.append(verts[vf]); vf += 1
                jv.append(verts[vf]); vf += 1
                jv.append(verts[vf]); vf += 1
        return jv
    return verts


# --- header ----------------------------------------------------------------

def _parse_header(buf):
    """Mirror ParseHeader; positions relative to the payload start (buf+8 in the C++)."""
    if len(buf) < 0x62:
        raise ValueError("Buffer too small for SCSP header")
    string_offset = _u32(buf, 0x00)
    string_length = _u32(buf, 0x04)
    strings_base = string_offset + 8
    strings_end = strings_base + string_length
    if strings_end > len(buf):
        raise ValueError("String table exceeds buffer")
    if buf[0x08:0x0C] != b"scsp":
        raise ValueError("Invalid SCSP magic")
    hdr_version = _u32(buf, 0x08 + 0x04)
    width = _f(buf, 0x08 + 0x0E)
    height = _f(buf, 0x08 + 0x12)

    def read_string(rel):
        if rel == U32_FF:
            return ""
        off = strings_base + rel
        if off >= strings_end:
            return ""
        return _cstr(buf, off, strings_end)

    version = read_string(_u32(buf, 0x08 + 0x4E))
    if len(version) > 5 and version.endswith(".scsp"):
        version = version[:-5]
    return {
        "string_offset": string_offset, "string_length": string_length,
        "hdr_version": hdr_version, "width": width, "height": height,
        "hash": read_string(_u32(buf, 0x08 + 0x4A)),
        "version": version,
        "images_path": read_string(_u32(buf, 0x08 + 0x5A)),
        "audio_path": read_string(_u32(buf, 0x08 + 0x5E)),
    }


# --- sections --------------------------------------------------------------

def _parse_bones(buf, pos, sb, se, bone_names):
    if pos + 2 > len(buf):
        return [], pos
    count = _u16(buf, pos)
    pos += 2
    bones = []
    for _ in range(count):
        if pos + 6 > len(buf):
            break
        index = _i16(buf, pos); pos += 2
        name_rel = _u32(buf, pos); pos += 4
        if pos + 2 > len(buf):
            break
        parent = _i16(buf, pos); pos += 2
        if pos + 32 > len(buf):
            break
        length = _f(buf, pos)
        x = _f(buf, pos + 4)
        y = _f(buf, pos + 8)
        rot = _f(buf, pos + 12)
        sx = _f(buf, pos + 16)
        sy = _f(buf, pos + 20)
        shx = _f(buf, pos + 24)
        shy = _f(buf, pos + 28)
        pos += 32
        if pos + 3 > len(buf):
            break
        tmode = _u16(buf, pos); pos += 2
        skin = buf[pos] != 0; pos += 1

        name = ""
        if name_rel != U32_FF and sb + name_rel < se:
            name = _cstr(buf, sb + name_rel, se)
        if not name:
            continue
        bone_names[index] = name

        bone = {"name": name}
        if parent >= 0 and parent in bone_names:
            bone["parent"] = bone_names[parent]
        if length != 0.0:
            bone["length"] = length
        if x != 0.0:
            bone["x"] = x
        if y != 0.0:
            bone["y"] = y
        if rot != 0.0:
            bone["rotation"] = rot
        if sx != 1.0:
            bone["scaleX"] = sx
        if sy != 1.0:
            bone["scaleY"] = sy
        if shx != 0.0:
            bone["shearX"] = shx
        if shy != 0.0:
            bone["shearY"] = shy
        if tmode in TRANSFORM_MODES:
            bone["transform"] = TRANSFORM_MODES[tmode]
        if skin:
            bone["skin"] = True
        bones.append(bone)
    return bones, pos


def _parse_ik(buf, pos, sb, se, bone_names, ik_names):
    if pos + 2 > len(buf):
        return [], pos
    count = _u16(buf, pos)
    pos += 2
    iks = []
    for i in range(count):
        if pos + 4 > len(buf):
            break
        name_rel = _u32(buf, pos); pos += 4
        name = ""
        if name_rel != U32_FF and sb + name_rel < se:
            name = _cstr(buf, sb + name_rel, se)
        if not name:
            name = "ik" + str(i)
        if pos + 4 > len(buf):
            break
        order = _u32(buf, pos); pos += 4
        if pos + 1 > len(buf):
            break
        skin_required = buf[pos] != 0; pos += 1
        if pos + 4 > len(buf):
            break
        bend_direction = struct.unpack_from("<i", buf, pos)[0]; pos += 4
        if pos + 1 > len(buf):
            break
        compress = buf[pos] != 0; pos += 1
        if pos + 8 > len(buf):
            break
        mix = _f(buf, pos); pos += 4
        softness = _f(buf, pos); pos += 4
        if pos + 1 > len(buf):
            break
        stretch = buf[pos] != 0; pos += 1
        if pos + 1 > len(buf):
            break
        uniform = buf[pos] != 0; pos += 1
        if pos + 2 > len(buf):
            break
        t_idx = _i16(buf, pos); pos += 2
        target_name = ""
        if t_idx >= 0 and t_idx in bone_names:
            target_name = bone_names[t_idx]
        if pos + 2 > len(buf):
            break
        nb = _u16(buf, pos); pos += 2
        bnames = []
        for _ in range(nb):
            if pos + 2 > len(buf):
                break
            bidx = _i16(buf, pos); pos += 2
            if bidx >= 0 and bidx in bone_names:
                bnames.append(bone_names[bidx])
        ik = {"name": name, "order": int(order), "skin": skin_required,
              "bones": bnames, "target": target_name, "mix": mix, "softness": softness,
              "bendPositive": bend_direction >= 0}
        if compress:
            ik["compress"] = True
        if stretch:
            ik["stretch"] = True
        if uniform:
            ik["uniform"] = True
        ik_names[i] = name
        iks.append(ik)
    return iks, pos


def _parse_slots(buf, pos, sb, se, bone_names, slot_names):
    if pos + 2 > len(buf):
        return [], pos
    count = _u16(buf, pos)
    pos += 2
    slots = []
    for _ in range(count):
        if pos + 2 > len(buf):
            break
        slot_index = _i16(buf, pos); pos += 2
        if pos + 4 > len(buf):
            break
        name_rel = _u32(buf, pos); pos += 4
        name = ""
        if name_rel != U32_FF and sb + name_rel < se:
            name = _cstr(buf, sb + name_rel, se)
        if pos + 2 > len(buf):
            break
        bone_idx = _i16(buf, pos); pos += 2
        bone_name = bone_names.get(bone_idx, "")
        if pos + 32 > len(buf):
            break
        cr = _f(buf, pos + 0); cg = _f(buf, pos + 4); cb = _f(buf, pos + 8); ca = _f(buf, pos + 12)
        pos += 16
        dr = _f(buf, pos + 0); dg = _f(buf, pos + 4); db = _f(buf, pos + 8); da = _f(buf, pos + 12)  # noqa: F841 (C++ reads but unused beyond dark rgb)
        pos += 16
        if pos + 1 > len(buf):
            break
        has_dark = buf[pos] != 0; pos += 1
        if pos + 4 > len(buf):
            break
        attach_rel = _u32(buf, pos); pos += 4
        if pos + 2 > len(buf):
            break
        blend_raw = _u16(buf, pos); pos += 2
        attachment = ""
        if attach_rel != U32_FF and sb + attach_rel < se:
            attachment = _cstr(buf, sb + attach_rel, se)
        if not name:
            name = "slot" + str(slot_index)
        slot_names[slot_index] = name

        slot = {"name": name, "bone": bone_name}
        col_hex = _bytes_hex(cr, cg, cb, ca)
        if col_hex != "FFFFFFFF":
            slot["color"] = col_hex
        if has_dark:
            slot["dark"] = _bytes_hex(dr, dg, db)
        if attachment:
            slot["attachment"] = attachment
        blend = BLEND_MODES.get(blend_raw, "normal")
        if blend != "normal":
            slot["blend"] = blend
        slots.append(slot)
    return slots, pos


def _parse_transform(buf, pos, sb, se, bone_names, transform_names):
    if pos + 2 > len(buf):
        return [], pos
    count = _u16(buf, pos)
    pos += 2
    transforms = []
    for i in range(count):
        if pos + 4 > len(buf):
            break
        name_off = _u32(buf, pos); pos += 4
        name = ""
        if name_off != U32_FF and sb + name_off < se:
            name = _cstr(buf, sb + name_off, se)
        if not name:
            name = "transform" + str(i)
        if pos + 4 > len(buf):
            break
        order = _u32(buf, pos); pos += 4
        if pos + 1 > len(buf):
            break
        skin_req = buf[pos] != 0; pos += 1
        if pos + 44 > len(buf):
            break
        rotate_mix = _f(buf, pos); pos += 4
        translate_mix = _f(buf, pos); pos += 4
        scale_mix = _f(buf, pos); pos += 4
        shear_mix = _f(buf, pos); pos += 4
        off_rot = _f(buf, pos); pos += 4
        off_x = _f(buf, pos); pos += 4
        off_y = _f(buf, pos); pos += 4
        off_sx = _f(buf, pos); pos += 4
        off_sy = _f(buf, pos); pos += 4
        off_shy = _f(buf, pos); pos += 4
        if pos + 1 > len(buf):
            break
        is_relative = buf[pos] != 0; pos += 1
        if pos + 1 > len(buf):
            break
        is_local = buf[pos] != 0; pos += 1
        if pos + 2 > len(buf):
            break
        tgt = _i16(buf, pos); pos += 2
        tgt_name = "root"
        if tgt >= 0 and tgt in bone_names:
            tgt_name = bone_names[tgt]
        if pos + 2 > len(buf):
            break
        bc = _u16(buf, pos); pos += 2
        blist = []
        for _ in range(bc):
            if pos + 2 > len(buf):
                break
            bi = _i16(buf, pos); pos += 2
            blist.append(bone_names[bi] if (bi >= 0 and bi in bone_names) else "root")
        tr = {"name": name, "order": int(order), "skin": skin_req, "target": tgt_name,
              "bones": blist, "rotateMix": rotate_mix, "translateMix": translate_mix,
              "scaleMix": scale_mix, "shearMix": shear_mix, "rotation": off_rot,
              "x": off_x, "y": off_y, "scaleX": off_sx, "scaleY": off_sy, "shearY": off_shy,
              "relative": is_relative, "local": is_local}
        transform_names[i] = name
        transforms.append(tr)
    return transforms, pos


def _parse_path(buf, pos, sb, se, bone_names, slot_names, path_names):
    if pos + 2 > len(buf):
        return [], pos
    count = _u16(buf, pos)
    pos += 2
    paths = []
    for i in range(count):
        if pos + 4 > len(buf):
            break
        name_off = _u32(buf, pos); pos += 4
        name = ""
        if name_off != U32_FF and sb + name_off < se:
            name = _cstr(buf, sb + name_off, se)
        if not name:
            name = "path" + str(i)
        if pos + 4 > len(buf):
            break
        order = _u32(buf, pos); pos += 4
        if pos + 1 > len(buf):
            break
        skin_req = buf[pos] != 0; pos += 1
        if pos + 6 > len(buf):
            break
        position_mode = _u16(buf, pos); pos += 2
        spacing_mode = _u16(buf, pos); pos += 2
        rotate_mode = _u16(buf, pos); pos += 2
        if pos + 20 > len(buf):
            break
        off_rot = _f(buf, pos); pos += 4
        position = _f(buf, pos); pos += 4
        spacing = _f(buf, pos); pos += 4
        rotate_mix = _f(buf, pos); pos += 4
        translate_mix = _f(buf, pos); pos += 4
        if pos + 2 > len(buf):
            break
        tgt = _i16(buf, pos); pos += 2
        tgt_name = "slot0"
        if tgt >= 0 and tgt in slot_names:
            tgt_name = slot_names[tgt]
        if pos + 2 > len(buf):
            break
        bc = _u16(buf, pos); pos += 2
        blist = []
        for _ in range(bc):
            if pos + 2 > len(buf):
                break
            bi = _i16(buf, pos); pos += 2
            blist.append(bone_names[bi] if (bi >= 0 and bi in bone_names) else "root")
        pc = {"name": name, "order": int(order), "skin": skin_req,
              "positionMode": POS_MODES.get(position_mode, "percent"),
              "spacingMode": SPACING_MODES.get(spacing_mode, "length"),
              "rotateMode": ROTATE_MODES.get(rotate_mode, "tangent"),
              "rotation": off_rot, "position": position, "spacing": spacing,
              "rotateMix": rotate_mix, "translateMix": translate_mix,
              "target": tgt_name, "bones": blist}
        path_names[i] = name
        paths.append(pc)
    return paths, pos


def _read_vertex_attachment(buf, pos, sb, se):
    """C++ ParseAssignVertexAttachment -> (bones, verts, vcount, world_len, path, pos).

    Like the C++, every early return keeps whatever bones/verts were already read
    (world_len 0) and leaves pos at the failing check; it never aborts the caller.
    """
    world_vertices_len = 0
    if pos + 2 > len(buf):
        return [], [], 0, 0, "", pos
    bcount = _u16(buf, pos); pos += 2
    bones = []
    for _ in range(bcount):
        if pos + 2 > len(buf):
            break
        bones.append(_i16(buf, pos)); pos += 2
    if pos + 2 > len(buf):
        return bones, [], 0, 0, "", pos
    vcount = _u16(buf, pos); pos += 2
    verts = []
    for _ in range(vcount):
        if pos + 4 > len(buf):
            break
        verts.append(_f(buf, pos)); pos += 4
    if pos + 8 > len(buf):
        return bones, verts, vcount, 0, "", pos
    world_vertices_len = _u32(buf, pos); pos += 4
    path_off = _u32(buf, pos); pos += 4
    path = ""
    if path_off != U32_FF and sb + path_off < se:
        path = _cstr(buf, sb + path_off, se)
    return bones, verts, vcount, world_vertices_len, path, pos


def _parse_skins(buf, pos, sb, se, slot_names, attachment_meta, hdr_version, skin_names):
    skins = []
    if pos + 2 > len(buf):
        return skins, pos
    skin_count = _u16(buf, pos)
    pos += 2
    for sidx in range(skin_count):
        name = "default"
        if pos + 4 > len(buf):
            break
        off = _u32(buf, pos); pos += 4
        if off != U32_FF and sb + off < se:
            s = _cstr(buf, sb + off, se)
            if s:
                name = s
        skin_names[sidx] = name
        if pos + 2 > len(buf):
            break
        bc = _u16(buf, pos); pos += 2
        pos += 2 * bc
        if pos + 2 > len(buf):
            break
        cc = _u16(buf, pos); pos += 2
        for _ in range(cc):
            if pos + 4 > len(buf):
                break
            pos += 4
        attachments_json = {}
        if pos + 2 > len(buf):
            break
        ac = _u16(buf, pos)
        pos += 2
        for a in range(ac):
            if pos + 2 > len(buf):
                break
            slot_idx = _u16(buf, pos); pos += 2
            slot_name = slot_names.get(_i16of(slot_idx), "slot" + str(slot_idx))
            if pos + 4 > len(buf):
                break
            name_off = _u32(buf, pos); pos += 4
            att_name = "att" + str(a)
            if name_off != U32_FF and sb + name_off < se:
                s = _cstr(buf, sb + name_off, se)
                if s:
                    att_name = s
            if pos + 2 > len(buf):
                break
            atype = _i16(buf, pos); pos += 2
            if pos + 4 > len(buf):
                break
            pos += 4  # ctor_name unused

            att = None
            if atype == 0:
                # Region
                if pos + 24 > len(buf):
                    break
                x = _f(buf, pos); pos += 4
                y = _f(buf, pos); pos += 4
                rot = _f(buf, pos); pos += 4
                sx = _f(buf, pos); pos += 4
                sy = _f(buf, pos); pos += 4
                w = _f(buf, pos); pos += 4
                h = _f(buf, pos); pos += 4
                pos += 24  # skip 6 floats
                if pos + 2 > len(buf):
                    break
                vc = _u16(buf, pos); pos += 2
                pos += 4 * vc
                if pos + 2 > len(buf):
                    break
                uc = _u16(buf, pos); pos += 2
                pos += 4 * uc
                if pos + 4 > len(buf):
                    break
                poff = _u32(buf, pos); pos += 4
                path = ""
                if poff != U32_FF and sb + poff < se:
                    path = _cstr(buf, sb + poff, se)
                if pos + 16 > len(buf):
                    break
                cr = _f(buf, pos); pos += 4
                cg = _f(buf, pos); pos += 4
                cb = _f(buf, pos); pos += 4
                ca = _f(buf, pos); pos += 4
                att = {"type": "region", "x": x, "y": y, "rotation": rot,
                       "scaleX": sx, "scaleY": sy, "width": w, "height": h}
                if path:
                    att["path"] = path
                color = _bytes_hex(cr, cg, cb, ca)
                if color != "FFFFFFFF":
                    att["color"] = color
            elif atype == 1:
                bones, verts, vcount, world_vertices_len, vpath, pos = _read_vertex_attachment(buf, pos, sb, se)
                is_weighted = bool(bones)
                attachment_meta[(name, slot_idx, att_name)] = (is_weighted, [] if is_weighted else verts)
                att = {"type": "boundingbox", "vertexCount": world_vertices_len >> 1,
                       "vertices": _merge_vertex_attachment(bones, verts)}
                if vpath:
                    att["path"] = vpath
            elif atype == 2 or atype == 3:
                bones, verts, _vcount, _wvl, vpath, pos = _read_vertex_attachment(buf, pos, sb, se)
                is_weighted = bool(bones)
                attachment_meta[(name, slot_idx, att_name)] = (is_weighted, [] if is_weighted else verts)
                pos += 4 * 6  # skip 24 bytes
                uvc = _u16(buf, pos); pos += 2
                _uvs, pos = _read_f32_array(buf, pos, uvc)  # C++ reads into `uvs` but never emits it
                ruvc = _u16(buf, pos); pos += 2
                region_uvs, pos = _read_f32_array(buf, pos, ruvc)
                tc = _u16(buf, pos); pos += 2
                triangles = []
                for _ in range(tc):
                    triangles.append(_u16(buf, pos)); pos += 2
                ec = _u16(buf, pos); pos += 2
                edges = []
                for _ in range(ec):
                    edges.append(_u16(buf, pos)); pos += 2
                mpath = vpath
                moff = _u32(buf, pos); pos += 4
                if moff != U32_FF and sb + moff < se:
                    s = _cstr(buf, sb + moff, se)
                    if s:
                        mpath = s
                _regionU = _f(buf, pos); pos += 4
                _regionV = _f(buf, pos); pos += 4
                _regionU2 = _f(buf, pos); pos += 4
                _regionV2 = _f(buf, pos); pos += 4
                width = _f(buf, pos); pos += 4
                height = _f(buf, pos); pos += 4
                _cr = _f(buf, pos); pos += 4
                _cg = _f(buf, pos); pos += 4
                _cb = _f(buf, pos); pos += 4
                _ca = _f(buf, pos); pos += 4
                hull = _u32(buf, pos); pos += 4
                # C++ reads regionRotate but never emits it
                pos += 1
                pos += 4  # _deg
                parent_off = _u32(buf, pos); pos += 4
                parent_name = ""
                if parent_off != U32_FF and sb + parent_off < se:
                    parent_name = _cstr(buf, sb + parent_off, se)
                out_verts = _merge_vertex_attachment(bones, verts)
                if atype == 3:
                    temp_skin_name = ""
                    if hdr_version > 0x7530:
                        pos += 2
                    else:
                        pos += 2  # temp_skin_idx (unused)
                        soff = _u32(buf, pos); pos += 4
                        if soff != U32_FF and sb + soff < se:
                            temp_skin_name = _cstr(buf, sb + soff, se)
                    skin_idx = _i16(buf, pos); pos += 2
                    deform_flag = buf[pos] != 0; pos += 1
                    att = {"type": "linkedmesh",
                           "parent": parent_name if parent_name else att_name,
                           "deform": deform_flag, "uvs": region_uvs, "triangles": triangles,
                           "vertices": out_verts, "hull": hull, "edges": edges,
                           "width": width, "height": height}
                    if hdr_version > 0x7530:
                        att["skinIndex"] = skin_idx
                    else:
                        att["skin"] = temp_skin_name if temp_skin_name else "default"
                    if mpath:
                        att["path"] = mpath
                else:
                    pos += 5  # skip 5 bytes
                    att = {"type": "mesh", "uvs": region_uvs, "triangles": triangles,
                           "vertices": out_verts, "hull": hull, "edges": edges,
                           "width": width, "height": height}
                    if mpath:
                        att["path"] = mpath
            elif atype == 4:
                bones, verts, _vcount, world_vertices_len, vpath, pos = _read_vertex_attachment(buf, pos, sb, se)
                is_weighted = bool(bones)
                attachment_meta[(name, slot_idx, att_name)] = (is_weighted, [] if is_weighted else verts)
                cnt = _u16(buf, pos); pos += 2
                lengths, pos = _read_f32_array(buf, pos, cnt)
                closed = buf[pos] != 0; pos += 1
                constant_speed = buf[pos] != 0; pos += 1
                att = {"type": "path", "closed": closed, "constantSpeed": constant_speed,
                       "lengths": lengths, "vertexCount": world_vertices_len >> 1,
                       "vertices": _merge_vertex_attachment(bones, verts)}
                if vpath:
                    att["path"] = vpath
            elif atype == 5:
                x = _f(buf, pos); pos += 4
                y = _f(buf, pos); pos += 4
                rotation = _f(buf, pos); pos += 4
                pos += 4
                att = {"type": "point", "x": x, "y": y, "rotation": rotation}
            elif atype == 6:
                bones, verts, _vcount, world_vertices_len, vpath, pos = _read_vertex_attachment(buf, pos, sb, se)
                is_weighted = bool(bones)
                attachment_meta[(name, slot_idx, att_name)] = (is_weighted, [] if is_weighted else verts)
                end_slot_idx = _i16(buf, pos); pos += 2
                end_slot_name = slot_names.get(end_slot_idx, "slot" + str(end_slot_idx))
                att = {"type": "clipping", "end": end_slot_name,
                       "vertexCount": world_vertices_len >> 1,
                       "vertices": _merge_vertex_attachment(bones, verts)}
                if vpath:
                    att["path"] = vpath

            if att is not None:
                attachments_json.setdefault(slot_name, {})[att_name] = att

        skins.append({"name": name, "attachments": attachments_json})

    # Post-process linked mesh skin indices
    for skin in skins:
        for _slot, slots in skin.get("attachments", {}).items():
            for _a, att in slots.items():
                if att.get("type") == "linkedmesh" and "skinIndex" in att:
                    att["skin"] = skin_names.get(att["skinIndex"], "default")
                    del att["skinIndex"]
    return skins, pos


def _parse_events(buf, pos, sb, se, event_names):
    if pos + 2 > len(buf):
        return {}, pos
    event_count = _u16(buf, pos)
    pos += 2
    events = {}
    for e in range(event_count):
        if pos + 4 > len(buf):
            break
        name_off = _u32(buf, pos); pos += 4
        name = ""
        if name_off != U32_FF and sb + name_off < se:
            name = _cstr(buf, sb + name_off, se)
        if pos + 12 > len(buf):
            break
        int_data = _u32(buf, pos); pos += 4
        float_data = _f(buf, pos); pos += 4
        string_off = _u32(buf, pos); pos += 4
        string_data = ""
        if string_off != U32_FF and sb + string_off < se:
            string_data = _cstr(buf, sb + string_off, se)
        if pos + 12 > len(buf):
            break
        audio_off = _u32(buf, pos); pos += 4
        audio_data = ""
        if audio_off != U32_FF and sb + audio_off < se:
            audio_data = _cstr(buf, sb + audio_off, se)
        volume = _f(buf, pos); pos += 4
        balance = _f(buf, pos); pos += 4
        evt = {"int": int_data, "float": float_data, "string": string_data,
               "audio": audio_data, "volume": volume, "balance": balance}
        if name:
            events[name] = evt
            event_names[e] = name
    return events, pos


def _parse_animations(buf, pos, sb, se, bone_names, slot_names, skin_names, ik_names,
                      transform_names, path_names, event_names, attachment_meta, hdr_version):
    animations = {}
    if pos + 2 > len(buf):
        return animations, pos
    anim_count = _u16(buf, pos)
    pos += 2
    for ai in range(anim_count):
        if pos + 8 > len(buf):
            break
        name_off = _u32(buf, pos); pos += 4
        duration = _f(buf, pos); pos += 4
        name = "anim" + str(ai)
        if name_off != U32_FF and sb + name_off < se:
            name = _cstr(buf, sb + name_off, se)
        anim = {"bones": {}, "slots": {}, "ik": {}, "transform": {}, "path": {},
                "deform": {}, "events": []}
        if pos + 2 > len(buf):
            break
        timeline_count = _u16(buf, pos)
        pos += 2
        for _k in range(timeline_count):
            if pos + 2 > len(buf):
                break
            ttype = _u16(buf, pos)
            pos += 2
            if ttype <= 3:
                bone_idx = _u16(buf, pos); pos += 2
                fc = _u16(buf, pos); pos += 2
                values, pos = _read_f32_array(buf, pos, fc)
                cc = _u16(buf, pos); pos += 2
                curves, pos = _read_f32_array(buf, pos, cc)
                bkey = bone_names.get(_i16of(bone_idx), str(bone_idx))
                tname_str = ("rotate", "translate", "scale", "shear")[ttype]
                bjson = anim["bones"].setdefault(bkey, {})
                frames_arr = bjson.setdefault(tname_str, [])
                val_count = 2 if ttype == 0 else 3
                frame_count = fc // val_count
                for i in range(frame_count):
                    fr = {}
                    if ttype == 0:
                        fr["time"] = values[i * 2]
                        fr["angle"] = values[i * 2 + 1]
                    else:
                        fr["time"] = values[i * 3]
                        fr["x"] = values[i * 3 + 1]
                        fr["y"] = values[i * 3 + 2]
                    _add_curve(i, curves, fr)
                    frames_arr.append(fr)
            elif ttype == 4:
                slot_idx = _u16(buf, pos); pos += 2
                fc = _u16(buf, pos); pos += 2
                times, pos = _read_f32_array(buf, pos, fc)
                name_cnt = _u16(buf, pos); pos += 2
                names = []
                for _ in range(name_cnt):
                    soff = _u32(buf, pos); pos += 4
                    if soff != U32_FF and sb + soff < se:
                        names.append(_cstr(buf, sb + soff, se))
                    else:
                        names.append("")
                sname = slot_names.get(_i16of(slot_idx), str(slot_idx))
                sjson = anim["slots"].setdefault(sname, {})
                arr = sjson.setdefault("attachment", [])
                count = min(fc, len(names))
                for i in range(count):
                    fr = {"time": times[i], "name": names[i] if names[i] else None}
                    arr.append(fr)
            elif ttype == 6:
                slot_idx = _u16(buf, pos); pos += 2
                fc = _u16(buf, pos); pos += 2
                values, pos = _read_f32_array(buf, pos, fc)
                cc = _u16(buf, pos); pos += 2
                curves, pos = _read_f32_array(buf, pos, cc)
                fv_frames = _u16(buf, pos); pos += 2
                frame_vertices = []
                for _ in range(fv_frames):
                    cnt = _u16(buf, pos); pos += 2
                    fv, pos = _read_f32_array(buf, pos, cnt)
                    frame_vertices.append(fv)
                att_off = _u32(buf, pos); pos += 4
                att_name = ""
                if att_off != U32_FF and sb + att_off < se:
                    att_name = _cstr(buf, sb + att_off, se)
                skinname = "default"
                if hdr_version > 0x7530 and pos + 2 <= len(buf):
                    sidx = _u16(buf, pos); pos += 2
                    skinname = skin_names.get(sidx, "default")
                is_unweighted = True
                setup = []
                key = (skinname, slot_idx, att_name)
                if key in attachment_meta:
                    is_unweighted = not attachment_meta[key][0]
                    setup = attachment_meta[key][1]
                sname = slot_names.get(_i16of(slot_idx), str(slot_idx))
                djson = anim["deform"].setdefault(skinname, {}).setdefault(sname, {}).setdefault(att_name, [])
                n = min(fc, fv_frames)
                for i in range(n):
                    fr = {"time": values[i]}
                    verts = frame_vertices[i]
                    if verts:
                        if is_unweighted and len(setup) == len(verts):
                            diffs = [verts[k] - setup[k] for k in range(len(verts))]
                        else:
                            diffs = verts
                        start = 0
                        while start < len(diffs) and abs(diffs[start]) < 1e-6:
                            start += 1
                        if start < len(diffs):
                            end = len(diffs) - 1
                            while end >= 0 and abs(diffs[end]) < 1e-6:
                                end -= 1
                            fr["vertices"] = diffs[start:end + 1]
                            if start > 0:
                                fr["offset"] = start
                    _add_curve(i, curves, fr)
                    djson.append(fr)
            elif ttype == 7:
                fc = _u16(buf, pos); pos += 2
                _times, pos = _read_f32_array(buf, pos, fc)
                evc = _u16(buf, pos); pos += 2
                for _ in range(evc):
                    pos += 4
            elif ttype == 8:
                slot_count = len(slot_names)
                fc = _u16(buf, pos); pos += 2
                times, pos = _read_f32_array(buf, pos, fc)
                groups = _u16(buf, pos); pos += 2
                draw_order = []
                for i in range(groups):
                    c = _u16(buf, pos); pos += 2
                    fr = {"time": times[i] if i < len(times) else 0.0}
                    offsets = []
                    if c == slot_count:
                        new_order = []
                        for _ in range(c):
                            new_order.append(_u32(buf, pos)); pos += 4
                        for orig in range(slot_count):
                            new_pos = -1
                            for p in range(slot_count):
                                if new_order[p] == orig:
                                    new_pos = p
                                    break
                            if new_pos != -1 and new_pos != orig:
                                offsets.append({"slot": slot_names.get(orig, str(orig)),
                                                "offset": new_pos - orig})
                    else:
                        for _ in range(c):
                            sidx = _u32(buf, pos); pos += 4
                            offset = struct.unpack_from("<i", buf, pos)[0]; pos += 4
                            if offset != 0:
                                offsets.append({"slot": slot_names.get(_i16of(sidx & 0xFFFF), str(sidx)),
                                                "offset": offset})
                    if offsets:
                        fr["offsets"] = offsets
                        draw_order.append(fr)
                if draw_order:
                    anim["drawOrder"] = draw_order
            elif ttype == 5 or ttype == 9 or ttype == 10 or ttype >= 11:
                idx = _u16(buf, pos); pos += 2
                fc = _u16(buf, pos); pos += 2
                values, pos = _read_f32_array(buf, pos, fc)
                cc = _u16(buf, pos); pos += 2
                curves, pos = _read_f32_array(buf, pos, cc)
                if ttype == 5:
                    sname = slot_names.get(_i16of(idx), str(idx))
                    ENTRIES = 5
                    frames = fc // ENTRIES
                    arr = anim["slots"].setdefault(sname, {}).setdefault("color", [])
                    for i in range(frames):
                        b = i * ENTRIES
                        fr = {"time": values[b],
                              "color": _bytes_hex(values[b + 1], values[b + 2], values[b + 3], values[b + 4])}
                        _add_curve(i, curves, fr)
                        arr.append(fr)
                elif ttype == 9:
                    cname = ik_names.get(idx, "ik" + str(idx))
                    ENTRIES = 6
                    frames = fc // ENTRIES
                    arr = anim["ik"].setdefault(cname, [])
                    for i in range(frames):
                        b = i * ENTRIES
                        fr = {"time": values[b], "mix": values[b + 1], "softness": values[b + 2],
                              "bendPositive": values[b + 3] >= 0.0}
                        if values[b + 4] != 0:
                            fr["compress"] = True
                        if values[b + 5] != 0:
                            fr["stretch"] = True
                        _add_curve(i, curves, fr)
                        arr.append(fr)
                elif ttype == 10:
                    cname = transform_names.get(idx, "transform" + str(idx))
                    ENTRIES = 5
                    frames = fc // ENTRIES
                    arr = anim["transform"].setdefault(cname, [])
                    for i in range(frames):
                        b = i * ENTRIES
                        fr = {"time": values[b], "rotateMix": values[b + 1],
                              "translateMix": values[b + 2], "scaleMix": values[b + 3],
                              "shearMix": values[b + 4]}
                        _add_curve(i, curves, fr)
                        arr.append(fr)
                elif ttype == 11 or ttype == 12 or ttype == 13:
                    cname = path_names.get(idx, "path" + str(idx))
                    pjson = anim["path"].setdefault(cname, {})
                    if ttype == 13:
                        ENTRIES = 3
                        frames = fc // ENTRIES
                        arr = []
                        pjson["mix"] = arr
                        for i in range(frames):
                            b = i * ENTRIES
                            fr = {"time": values[b], "rotateMix": values[b + 1],
                                  "translateMix": values[b + 2]}
                            _add_curve(i, curves, fr)
                            arr.append(fr)
                    else:
                        ENTRIES = 2
                        frames = fc // ENTRIES
                        key = "position" if ttype == 11 else "spacing"
                        arr = []
                        pjson[key] = arr
                        for i in range(frames):
                            b = i * ENTRIES
                            fr = {"time": values[b], key: values[b + 1]}
                            _add_curve(i, curves, fr)
                            arr.append(fr)
                elif ttype == 14:
                    sname = slot_names.get(_i16of(idx), str(idx))
                    ENTRIES = 8
                    frames = fc // ENTRIES
                    arr = anim["slots"].setdefault(sname, {}).setdefault("twoColor", [])
                    for i in range(frames):
                        b = i * ENTRIES
                        fr = {"time": values[b],
                              "light": _bytes_hex(values[b + 1], values[b + 2], values[b + 3], values[b + 4]),
                              "dark": _bytes_hex(values[b + 5], values[b + 6], values[b + 7])}
                        _add_curve(i, curves, fr)
                        arr.append(fr)
            else:
                break

        if not anim["events"]:
            del anim["events"]
        anim["duration"] = duration
        animations[name] = anim
    return animations, pos


# --- top level -------------------------------------------------------------

def to_json(inner):
    """Parse the unwrapped 'scsp1u' payload -> spine 3.8 JSON dict."""
    if not inner:
        return {}
    hdr = _parse_header(inner)
    sb = hdr["string_offset"] + 8
    se = sb + hdr["string_length"]

    skeleton = {"spine": hdr["version"] if hdr["version"] else "3.8.79", "x": 0.0, "y": 0.0}
    if hdr["width"] != 0.0:
        skeleton["width"] = hdr["width"]
    if hdr["height"] != 0.0:
        skeleton["height"] = hdr["height"]
    if hdr["hash"]:
        skeleton["hash"] = hdr["hash"]
    if hdr["images_path"]:
        skeleton["images"] = hdr["images_path"]
    if hdr["audio_path"]:
        skeleton["audio"] = hdr["audio_path"]

    pos = 0x08 + 0x62
    bone_names = {}
    bones, pos = _parse_bones(inner, pos, sb, se, bone_names)
    ik_names = {}
    iks, pos = _parse_ik(inner, pos, sb, se, bone_names, ik_names)
    slot_names = {}
    slots, pos = _parse_slots(inner, pos, sb, se, bone_names, slot_names)
    transform_names = {}
    transforms, pos = _parse_transform(inner, pos, sb, se, bone_names, transform_names)
    path_names = {}
    paths, pos = _parse_path(inner, pos, sb, se, bone_names, slot_names, path_names)
    attachment_meta = {}
    skin_names = {}
    skins, pos = _parse_skins(inner, pos, sb, se, slot_names, attachment_meta, hdr["hdr_version"], skin_names)
    event_names = {}
    events, pos = _parse_events(inner, pos, sb, se, event_names)
    animations, pos = _parse_animations(inner, pos, sb, se, bone_names, slot_names, skin_names,
                                        ik_names, transform_names, path_names, event_names,
                                        attachment_meta, hdr["hdr_version"])

    return {"skeleton": skeleton, "bones": bones, "ik": iks, "slots": slots,
            "transform": transforms, "path": paths, "skins": skins, "events": events,
            "animations": animations}


def convert(path):
    """Read file -> unwrap -> to_json."""
    with open(path, "rb") as f:
        return to_json(unwrap(f.read()))


# --- self-check / CLI ------------------------------------------------------

FIXTURES = os.environ.get("CZN_FIXTURES", "")   # optional: dir with sample .scsp files


def _selftest():
    import os
    if not FIXTURES or not os.path.isdir(FIXTURES):
        print("[i] no fixture dir (set CZN_FIXTURES to a folder of sample .scsp files) "
              "- selftest skipped")
        return 0
    files = ["model__1041.scsp", "card__unique_1041_01.scsp",
             "effect__lenore_1041_ug_eff_petal.scsp", "face__portrait__1041.scsp"]
    ok = True
    for fn in files:
        path = os.path.join(FIXTURES, fn)
        try:
            d = convert(path)
        except Exception as e:  # noqa: BLE001
            ok = False
            print(f"[X] {fn}: {type(e).__name__}: {e}")
            continue
        sk = d["skeleton"]
        n = (f"bones={len(d['bones'])} slots={len(d['slots'])} "
             f"skins={len(d['skins'])} anims={len(d['animations'])}")
        print(f"[OK] {fn}: spine={sk.get('spine')} {n}")
    # model__1041 must be rich
    try:
        model = convert(os.path.join(FIXTURES, "model__1041.scsp"))
        for k in ("bones", "slots", "skins", "animations"):
            assert model[k], f"model__1041.{k} empty"
        assert model["skeleton"]["spine"] == "3.8.79", model["skeleton"]["spine"]
        print("[OK] model__1041 richness: bones=%d slots=%d skins=%d anims=%d spine=%s" % (
            len(model["bones"]), len(model["slots"]), len(model["skins"]),
            len(model["animations"]), model["skeleton"]["spine"]))
    except Exception as e:  # noqa: BLE001
        ok = False
        print(f"[X] model__1041 richness: {type(e).__name__}: {e}")
    print("scsp2json selftest", "ok" if ok else "FAILED")
    return 0 if ok else 1


def _main(argv):
    if "--selftest" in argv:
        return _selftest()
    rc = 0
    for path in argv[1:]:
        try:
            d = convert(path)
        except Exception as e:  # noqa: BLE001
            rc = 1
            print(f"[X] {path}: {type(e).__name__}: {e}")
            continue
        print(f"{path}: spine={d['skeleton'].get('spine')} bones={len(d['bones'])} "
              f"slots={len(d['slots'])} skins={len(d['skins'])} "
              f"animations={len(d['animations'])}")
    return rc


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv))
