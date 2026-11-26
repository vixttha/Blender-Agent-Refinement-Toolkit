"""Bounded GLB 2.0 core geometry inspection, not a full glTF validator.

No URI is resolved, no decoder is loaded, and no Blender process is required.
Counts refer to encoded primitive records, not welded or deformed geometry.
"""
from array import array
import json
import math
import struct

MAX_GLB_BYTES = 128 * 1024 * 1024
MAX_JSON_BYTES = 4 * 1024 * 1024
MAX_RECORDS = 50_000
MAX_JSON_ITEMS = 500_000
MAX_DEPTH = 64
MAX_POSITIONS = 2_000_000
MAX_INDICES = 6_000_000
MAX_INSTANCE_POSITIONS = 4_000_000
MAX_SPARSE = 250_000
COMPONENTS = {5120: "b", 5121: "B", 5122: "h", 5123: "H", 5125: "I", 5126: "f"}
SHAPES = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT2": 4, "MAT3": 9, "MAT4": 16}
IDENTITY = (1., 0., 0., 0., 0., 1., 0., 0., 0., 0., 1., 0., 0., 0., 0., 1.)


def _fail(message):
    raise ValueError("GLB: " + message)


def _int(value, label, minimum=0, maximum=MAX_GLB_BYTES):
    if type(value) is not int or not minimum <= value <= maximum:
        _fail("invalid " + label)
    return value


def _dict(value, label):
    if not isinstance(value, dict):
        _fail("invalid " + label)
    return value


def _list(value, label, limit=MAX_RECORDS):
    if not isinstance(value, list) or len(value) > limit:
        _fail("invalid or oversized " + label)
    return value


def _ref(records, index, label):
    return records[_int(index, label, maximum=len(records) - 1)]


def _unique(pairs):
    result = {}
    for k, v in pairs:
        if k in result:
            _fail("duplicate JSON key")
        result[k] = v
    return result


def _constant(value):
    _fail("non-finite JSON number")


def _read(stream, size):
    data = stream.read(size)
    if len(data) != size:
        _fail("truncated container")
    return data


def _container(stream, length):
    _int(length, "container size", 20, MAX_GLB_BYTES)
    magic, version, declared = struct.unpack("<4sII", _read(stream, 12))
    if magic != b"glTF" or version != 2 or declared != length:
        _fail("invalid magic, version or declared length")
    offset = 12
    document = binary = None
    chunks = 0
    while offset < length:
        chunks += 1
        if chunks > MAX_RECORDS:
            _fail("chunk count limit exceeded")
        if length - offset < 8:
            _fail("truncated chunk header")
        size, kind = struct.unpack("<I4s", _read(stream, 8))
        if size % 4 or size > length - offset - 8:
            _fail("invalid chunk length or alignment")
        if offset == 12 and kind != b"JSON":
            _fail("JSON must be first")
        if kind == b"JSON":
            if document is not None or size > MAX_JSON_BYTES:
                _fail("duplicate or oversized JSON chunk")
            try:
                document = json.loads(_read(stream, size).decode("utf-8"),
                                      object_pairs_hook=_unique, parse_constant=_constant)
            except (UnicodeError, RecursionError, ValueError) as exc:
                raise ValueError("GLB: invalid JSON chunk") from exc
        elif kind == b"BIN\0":
            if binary is not None or document is None or offset != 20 + json_size:
                _fail("duplicate or misplaced BIN chunk")
            binary = _read(stream, size)
        else:
            stream.seek(size, 1)  # Unknown chunks are ignored by glTF readers.
        if offset == 12:
            json_size = size
        offset += 8 + size
    document = _dict(document, "JSON root")
    stack = [(document, 0)]
    items = 0
    while stack:
        obj, depth = stack.pop()
        items += 1
        if depth > MAX_DEPTH or items > MAX_JSON_ITEMS:
            _fail("JSON complexity limit exceeded")
        if isinstance(obj, dict):
            stack.extend((x, depth + 1) for x in obj.values())
        elif isinstance(obj, list):
            stack.extend((x, depth + 1) for x in obj)
        elif isinstance(obj, float) and not math.isfinite(obj):
            _fail("non-finite JSON number")
    return document, memoryview(binary or b"")


def _numbers(values, size, label):
    values = _list(values, label, size)
    if len(values) != size or any(type(v) not in (int, float) for v in values):
        _fail("invalid " + label)
    try:
        result = tuple(float(v) for v in values)
    except OverflowError:
        _fail("non-finite " + label)
    if not all(math.isfinite(v) for v in result):
        _fail("non-finite " + label)
    return result


def _matrix(node):
    if "matrix" in node:
        if any(k in node for k in ("translation", "rotation", "scale")):
            _fail("matrix and TRS coexist")
        m = _numbers(node["matrix"], 16, "node matrix")
        if (m[3], m[7], m[11], m[15]) != (0, 0, 0, 1):
            _fail("non-affine node matrix")
        return m
    tx, ty, tz = _numbers(node.get("translation", [0, 0, 0]), 3, "translation")
    sx, sy, sz = _numbers(node.get("scale", [1, 1, 1]), 3, "scale")
    x, y, z, w = _numbers(node.get("rotation", [0, 0, 0, 1]), 4, "rotation")
    if not math.isclose(x*x+y*y+z*z+w*w, 1.0, abs_tol=1e-5):
        _fail("non-unit quaternion")
    return ((1-2*y*y-2*z*z)*sx, (2*x*y+2*z*w)*sx, (2*x*z-2*y*w)*sx, 0.,
            (2*x*y-2*z*w)*sy, (1-2*x*x-2*z*z)*sy, (2*y*z+2*x*w)*sy, 0.,
            (2*x*z+2*y*w)*sz, (2*y*z-2*x*w)*sz, (1-2*x*x-2*y*y)*sz, 0.,
            tx, ty, tz, 1.)


def _mul(a, b):
    m = tuple(sum(a[k*4+r]*b[c*4+k] for k in range(4))
              for c in range(4) for r in range(4))
    if not all(math.isfinite(v) for v in m):
        _fail("non-finite composed transform")
    return m


def _box():
    return [[math.inf]*3, [-math.inf]*3]


def _include(box, point):
    for k, v in enumerate(point):
        if not math.isfinite(v):
            _fail("non-finite position")
        box[0][k] = min(box[0][k], v)
        box[1][k] = max(box[1][k], v)


def _bounds(box):
    return {"min": box[0], "max": box[1]}


def _degenerate(a, b, c):
    u = [b[i]-a[i] for i in range(3)]
    v = [c[i]-a[i] for i in range(3)]
    return all(u[i]*v[j] == u[j]*v[i] for i, j in ((0, 1), (1, 2), (2, 0)))


class _Geometry:
    def __init__(self, doc, binary):
        self.doc = doc
        self.binary = binary
        asset = _dict(doc.get("asset"), "asset")
        if asset.get("version") != "2.0" or asset.get("minVersion", "2.0") != "2.0":
            _fail("unsupported asset version")
        required = _list(doc.get("extensionsRequired", []), "required extensions")
        if required:
            _fail("unsupported required extension")
        self.extensions = _list(doc.get("extensionsUsed", []), "used extensions")
        if any(not isinstance(v, str) for v in self.extensions):
            _fail("invalid extension name")
        buffers = self.records("buffers")
        if len(buffers) != 1 or "uri" in buffers[0]:
            _fail("requires one embedded binary buffer; URI resources unsupported")
        length = _int(buffers[0].get("byteLength"), "buffer length", 1)
        if not length <= len(binary) <= length + 3:
            _fail("BIN chunk does not match buffer length")
        self.views = self.records("bufferViews")
        self.accessors = self.records("accessors")
        self.sparse_total = 0
        self.positions_total = self.indices_total = 0
        for view in self.views:
            if _int(view.get("buffer"), "buffer reference", maximum=0) != 0:
                _fail("invalid buffer reference")
            start = _int(view.get("byteOffset", 0), "bufferView offset")
            size = _int(view.get("byteLength"), "bufferView length", 1)
            if start + size > length:
                _fail("bufferView outside buffer")
            if "byteStride" in view:
                stride = _int(view["byteStride"], "byteStride", 4, 252)
                if stride % 4:
                    _fail("misaligned byteStride")
            if "EXT_meshopt_compression" in _dict(view.get("extensions", {}), "bufferView extensions"):
                _fail("unsupported compressed bufferView")
        # Validate layouts of all accessors, including unconsumed inventory attributes.
        self.layouts = [self.layout(a) for a in self.accessors]
        if any(binary[length:]):
            _fail("nonzero BIN padding")

    def records(self, key):
        return [_dict(x, key + " entry") for x in _list(self.doc.get(key, []), key)]

    def region(self, view_index, offset, count, item, alignment, *, packed=False):
        view = _ref(self.views, view_index, "bufferView reference")
        start = _int(view.get("byteOffset", 0), "view offset") + offset
        stride = view.get("byteStride", item)
        if packed and "byteStride" in view:
            _fail("packed accessor cannot be strided")
        if stride < item or stride % alignment or offset % alignment or start % alignment:
            _fail("invalid accessor stride or alignment")
        if offset + (count-1)*stride + item > view["byteLength"]:
            _fail("accessor outside bufferView")
        return start, stride

    def layout(self, a):
        component = _int(a.get("componentType"), "component type")
        shape = a.get("type")
        if component not in COMPONENTS or not isinstance(shape, str) or shape not in SHAPES:
            _fail("unsupported accessor format")
        unit = struct.calcsize("<" + COMPONENTS[component])
        item = SHAPES[shape]*unit
        alignment = unit
        if shape.startswith("MAT"):
            dim = int(shape[-1])
            item = dim*((dim*unit+3)//4*4)
            alignment = max(4, unit)
        count = _int(a.get("count"), "accessor count", 1, MAX_INDICES)
        offset = _int(a.get("byteOffset", 0), "accessor offset")
        base = None
        if "bufferView" in a:
            base = self.region(a["bufferView"], offset, count, item, alignment)
        elif offset:
            _fail("accessor without bufferView has offset")
        sparse = a.get("sparse")
        overrides = {}
        if sparse is not None:
            sparse = _dict(sparse, "sparse accessor")
            n = _int(sparse.get("count"), "sparse count", 1, min(count, MAX_SPARSE))
            self.sparse_total += n
            if self.sparse_total > MAX_SPARSE:
                _fail("sparse work limit exceeded")
            indices = _dict(sparse.get("indices"), "sparse indices")
            values = _dict(sparse.get("values"), "sparse values")
            ic = _int(indices.get("componentType"), "sparse component")
            if ic not in (5121, 5123, 5125):
                _fail("invalid sparse index type")
            decoder = struct.Struct("<" + COMPONENTS[ic])
            ip, istride = self.region(indices.get("bufferView"),
                _int(indices.get("byteOffset", 0), "sparse index offset"), n,
                decoder.size, decoder.size, packed=True)
            vp, vstride = self.region(values.get("bufferView"),
                _int(values.get("byteOffset", 0), "sparse value offset"), n,
                item, alignment, packed=True)
            last = -1
            for j in range(n):
                k, = decoder.unpack_from(self.binary, ip+j*istride)
                if not last < k < count:
                    _fail("sparse indices not strictly increasing or out of range")
                overrides[k] = vp+j*vstride
                last = k
        return component, shape, count, base, overrides

    def values(self, index, *, position):
        a = _ref(self.accessors, index, "accessor reference")
        component, shape, count, base, overrides = self.layouts[index]
        if position:
            if component != 5126 or shape != "VEC3":
                _fail("unsupported POSITION format")
            self.positions_total += count
            if self.positions_total > MAX_POSITIONS:
                _fail("position work limit exceeded")
        else:
            if component not in (5121, 5123, 5125) or shape != "SCALAR":
                _fail("invalid index accessor")
            if "bufferView" in a and "byteStride" in self.views[a["bufferView"]]:
                _fail("index accessor must be packed")
            self.indices_total += count
            if self.indices_total > MAX_INDICES:
                _fail("index work limit exceeded")
        if a.get("normalized", False) is not False:
            _fail("normalized positions or indices unsupported")
        if position and base is not None and (base[0] % 4 or base[1] % 4):
            _fail("misaligned POSITION")
        decoder = struct.Struct("<" + COMPONENTS[component]*SHAPES[shape])
        zero = (0,)*SHAPES[shape]
        for k in range(count):
            if k in overrides:
                yield decoder.unpack_from(self.binary, overrides[k])
            elif base is None:
                yield zero
            else:
                yield decoder.unpack_from(self.binary, base[0]+k*base[1])

    def primitive(self, p, box, material_count):
        p = _dict(p, "primitive")
        if "KHR_draco_mesh_compression" in _dict(p.get("extensions", {}), "primitive extensions"):
            _fail("unsupported compressed primitive")
        attributes = _dict(p.get("attributes"), "attributes")
        if "POSITION" not in attributes:
            _fail("missing POSITION")
        pos = array("f")
        local = _box()
        for point in self.values(attributes["POSITION"], position=True):
            _include(box, point)
            _include(local, point)
            pos.extend(point)
        accessor = self.accessors[attributes["POSITION"]]
        for key, actual in zip(("min", "max"), local):
            declared = _numbers(accessor.get(key), 3, "POSITION " + key)
            if any(not math.isclose(a, b, rel_tol=1e-6, abs_tol=1e-12) for a, b in zip(actual, declared)):
                _fail("declared POSITION bounds do not match binary data")
        count = len(pos)//3
        for key, index in attributes.items():
            _ref(self.accessors, index, "attribute reference")
            if self.layouts[index][2] != count:
                _fail("attribute count mismatch")
        for target in _list(p.get("targets", []), "morph targets"):
            for index in _dict(target, "morph target").values():
                _ref(self.accessors, index, "morph accessor")
                if self.layouts[index][2] != count:
                    _fail("morph attribute count mismatch")
        if "material" in p:
            _int(p["material"], "material reference", maximum=material_count-1)
        mode = _int(p.get("mode", 4), "primitive mode", maximum=6)
        restart = None
        if "indices" in p:
            accessor = _ref(self.accessors, p["indices"], "index accessor reference")
            restart = {5121: 255, 5123: 65535, 5125: 4294967295}.get(accessor["componentType"])
            indices = (i[0] for i in self.values(p["indices"], position=False))
        else:
            self.indices_total += count
            if self.indices_total > MAX_INDICES:
                _fail("index work limit exceeded")
            indices = iter(range(count))
        triangles = degenerate = n = 0
        first = previous = before = None
        for i in indices:
            if i == restart or i >= count:
                _fail("reserved restart index or index outside POSITION")
            n += 1
            tri = None
            if mode == 4 and n % 3 == 0:
                tri = (before, previous, i)
            elif mode == 5 and n >= 3:
                tri = (before, previous, i)
            elif mode == 6 and n >= 3:
                tri = (first, previous, i)
            if tri is not None:
                triangles += 1
                a, b, c = (pos[k*3:k*3+3] for k in tri)
                degenerate += _degenerate(a, b, c)
            if first is None:
                first = i
            before, previous = previous, i
        if (mode == 4 and (n < 3 or n % 3) or mode in (5, 6) and n < 3
                or mode == 1 and (n < 2 or n % 2) or mode in (2, 3) and n < 2):
            _fail("invalid primitive element count")
        return pos, triangles, degenerate, sum(k.startswith("TEXCOORD_") for k in attributes)


def inspect_glb(stream, length):
    doc, binary = _container(stream, length)
    geometry = _Geometry(doc, binary)
    meshes = geometry.records("meshes")
    nodes = geometry.records("nodes")
    scenes = geometry.records("scenes")
    materials = geometry.records("materials")
    images = geometry.records("images")
    textures = geometry.records("textures")
    skins = geometry.records("skins")
    animations = geometry.records("animations")
    for image in images:
        if "uri" in image:
            _fail("image URI resources unsupported")
        _ref(geometry.views, image.get("bufferView"), "image bufferView")
    for texture in textures:
        if "source" in texture:
            _ref(images, texture["source"], "texture source")
    for skin in skins:
        for joint in _list(skin.get("joints"), "skin joints"):
            _ref(nodes, joint, "joint reference")
    box = _box()
    primitives = []
    total_primitives = uv = morph = 0
    for mesh in meshes:
        group = []
        for p in _list(mesh.get("primitives"), "mesh primitives"):
            total_primitives += 1
            if total_primitives > MAX_RECORDS:
                _fail("primitive limit exceeded")
            group.append(geometry.primitive(p, box, len(materials)))
            uv += group[-1][3]
            morph += len(p.get("targets", []))
        if not group:
            _fail("empty mesh primitives")
        primitives.append(group)
    parents = {}
    children = []
    matrices = []
    for i, node in enumerate(nodes):
        if "EXT_mesh_gpu_instancing" in _dict(node.get("extensions", {}), "node extensions"):
            _fail("unsupported GPU instancing")
        if "mesh" in node:
            _ref(meshes, node["mesh"], "node mesh")
        if "skin" in node:
            _ref(skins, node["skin"], "node skin")
        matrices.append(_matrix(node))
        group = _list(node.get("children", []), "node children")
        for child in group:
            _ref(nodes, child, "child reference")
            if child in parents:
                _fail("node has multiple parents or duplicate child")
            parents[child] = i
        children.append(group)
    # Verify even disconnected node trees; a cycle has no root.
    visited = set()
    stack = [i for i in range(len(nodes)) if i not in parents]
    while stack:
        i = stack.pop()
        visited.add(i)
        stack.extend(children[i])
    if len(visited) != len(nodes):
        _fail("node cycle")
    if "scene" in doc:
        _ref(scenes, doc["scene"], "default scene")
    used_meshes = set()
    instance_count = instance_triangles = instance_degenerate = instance_positions = traversal = 0
    transformed = _box()
    for scene in scenes:
        roots = _list(scene.get("nodes", []), "scene roots")
        if any(type(i) is not int for i in roots) or len(set(roots)) != len(roots):
            _fail("invalid or duplicate scene root")
        stack = []
        for i in roots:
            _ref(nodes, i, "scene root")
            if i in parents:
                _fail("scene root has a parent")
            stack.append((i, IDENTITY, 0))
        while stack:
            i, parent, depth = stack.pop()
            traversal += 1
            if depth > MAX_DEPTH or traversal > MAX_RECORDS*2:
                _fail("scene traversal limit exceeded")
            m = _mul(parent, matrices[i])
            stack.extend((k, m, depth+1) for k in children[i])
            if "mesh" not in nodes[i]:
                continue
            mesh = nodes[i]["mesh"]
            used_meshes.add(mesh)
            instance_count += 1
            for pos, triangles, degenerate, _ in primitives[mesh]:
                instance_triangles += triangles
                instance_degenerate += degenerate
                instance_positions += len(pos)//3
                if instance_positions > MAX_INSTANCE_POSITIONS or instance_triangles > MAX_INDICES:
                    _fail("instance geometry work limit exceeded")
                for k in range(0, len(pos), 3):
                    x, y, z = pos[k:k+3]
                    _include(transformed, (m[0]*x+m[4]*y+m[8]*z+m[12],
                                           m[1]*x+m[5]*y+m[9]*z+m[13],
                                           m[2]*x+m[6]*y+m[10]*z+m[14]))
    if instance_triangles <= instance_degenerate:
        _fail("no usable scene-referenced triangle surface")
    triangles = sum(p[1] for mesh in primitives for p in mesh)
    degenerate = sum(p[2] for mesh in primitives for p in mesh)
    return {"encoding": "glb2", "geometry_scope": "encoded_base_mesh_primitives",
            "vertices": geometry.positions_total, "triangles": triangles,
            "degenerate_triangles": degenerate, "usable_triangles": triangles-degenerate,
            "bounds": _bounds(box), "scene_base_bounds": _bounds(transformed),
            "scene_instance_count": instance_count, "scene_instance_triangles": instance_triangles,
            "scene_instance_degenerate_base_triangles": instance_degenerate,
            "mesh_count": len(meshes), "primitive_count": total_primitives,
            "referenced_mesh_count": len(used_meshes), "scene_count": len(scenes),
            "node_count": len(nodes), "material_count": len(materials),
            "image_count": len(images), "texture_count": len(textures),
            "uv_attribute_count": uv, "skin_count": len(skins),
            "joint_reference_count": sum(len(s["joints"]) for s in skins),
            "animation_count": len(animations), "morph_target_count": morph,
            "extensions_used": geometry.extensions,
            "validation_scope": "core embedded base triangle geometry; not full glTF conformance, deformed geometry or transformed triangle quality"}
