"""Deterministic, synthetic GLB fixtures and bounded parser regressions."""
import copy
import hashlib
import itertools
import io
import json
import math
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from blender_agent.glb import inspect_glb
from blender_agent.inspect import inspect_asset


def chunk(kind, payload, pad=b"\0"):
    payload += pad * (-len(payload) % 4)
    return struct.pack("<I4s", len(payload), kind) + payload


def container(chunks):
    payload = b"".join(chunks)
    return struct.pack("<4sII", b"glTF", 2, len(payload)+12) + payload


def encode(doc, data):
    return container([chunk(b"JSON", json.dumps(doc, separators=(",", ":")).encode(), b" "),
                      chunk(b"BIN\0", data)])


def fixture(points=((0,0,0),(1,0,0),(0,1,0)), indices=(0,1,2), component=5123, mode=4,
            stride=12):
    points = tuple(points)
    data = b"".join(struct.pack("<3f", *p) + b"\0"*(stride-12) for p in points)
    view = {"buffer":0,"byteLength":len(data)}
    if stride != 12:
        view["byteStride"] = stride
    doc = {"asset":{"version":"2.0"}, "buffers":[{"byteLength":0}],
           "bufferViews":[view],
           "accessors":[{"bufferView":0,"componentType":5126,"count":len(points),"type":"VEC3",
                         "min":[min(p[i] for p in points) for i in range(3)],
                         "max":[max(p[i] for p in points) for i in range(3)]}],
           "meshes":[{"primitives":[{"attributes":{"POSITION":0},"mode":mode}]}],
           "nodes":[{"mesh":0}], "scenes":[{"nodes":[0]}], "scene":0}
    if indices is not None:
        fmt = {5121:"B",5123:"H",5125:"I"}[component]
        values = struct.pack("<"+fmt*len(indices), *indices)
        doc["bufferViews"].append({"buffer":0,"byteOffset":len(data),"byteLength":len(values)})
        doc["accessors"].append({"bufferView":1,"componentType":component,"count":len(indices),"type":"SCALAR"})
        doc["meshes"][0]["primitives"][0]["indices"] = 1
        data += values
    doc["buffers"][0]["byteLength"] = len(data)
    return doc, data


def triangle_glb():
    return encode(*fixture())


def check(raw):
    return inspect_glb(io.BytesIO(raw), len(raw))


class GlbTests(unittest.TestCase):
    def test_triangle_and_unsigned_index_types(self):
        for component in (5121,5123,5125):
            with self.subTest(component=component):
                result = check(encode(*fixture(component=component)))
                self.assertEqual((result["vertices"],result["triangles"],result["degenerate_triangles"]), (3,1,0))
                self.assertEqual(result["bounds"],{"min":[0,0,0],"max":[1,1,0]})

    def test_nonindexed_and_interleaved(self):
        for stride in (12,16,24):
            with self.subTest(stride=stride):
                self.assertEqual(check(encode(*fixture(indices=None,stride=stride)))["triangles"],1)

    def test_strip_fan_and_mixed_degenerate(self):
        points = ((0,0,0),(1,0,0),(0,1,0),(1,1,0))
        for mode in (5,6):
            with self.subTest(mode=mode):
                self.assertEqual(check(encode(*fixture(points,(0,1,2,3),mode=mode)))["triangles"],2)
        result = check(encode(*fixture(points,(0,1,2,0,0,1))))
        self.assertEqual((result["triangles"],result["degenerate_triangles"],result["usable_triangles"]),(2,1,1))

    def test_exact_degeneracy_independent_of_vertex_order(self):
        for points, degenerate in (
            (((2**60,3*2**60,0),(0,0,0),(80,240,0)),True),
            (((2**60,2**60,0),(0,0,0),(1,0,0)),False),
            (((0,0,0),(2**-149,0,0),(0,2**-149,0)),False),
            (((0,0,0),(1,1,1),(2,2,2)),True),
        ):
            for order in itertools.permutations(points):
                with self.subTest(order=order, degenerate=degenerate):
                    doc,data=fixture(order)
                    if degenerate:
                        with self.assertRaisesRegex(ValueError,"no usable scene-referenced"):
                            check(encode(doc,data))
                    else:
                        self.assertEqual(check(encode(doc,data))["usable_triangles"],1)

    def test_position_bounds_use_exact_float32_precision(self):
        doc,data=fixture(((0,0,0),(1000000,0,0),(0,1,0)))
        for bad in (999999.5, 1e100):
            with self.subTest(bound=bad):
                doc["accessors"][0]["max"][0]=bad
                with self.assertRaisesRegex(ValueError,"POSITION bound"):
                    check(encode(doc,data))
        doc["accessors"][0]["max"][0]=1000000.01
        self.assertEqual(check(encode(doc,data))["bounds"]["max"][0],1000000)
        doc,data=fixture(((0,0,0),(0.1,0,0),(0,1,0)))
        self.assertEqual(check(encode(doc,data))["triangles"],1)

    def test_reserved_primitive_restart_index(self):
        points = [(0,0,0),(1,0,0),(0,1,0)] + [(1,1,0)]*253
        doc,data=fixture(points,indices=(0,1,255),component=5121)
        with self.assertRaisesRegex(ValueError,"restart index"):
            check(encode(doc,data))

    def test_matrix_trailing_padding_may_be_omitted(self):
        # MAT3 unsigned byte: 3 four-byte columns, final byte may be omitted.
        for count in (1, 2):
            with self.subTest(count=count):
                doc, data = fixture()
                data += b"\0" * (-len(data) % 4)
                payload = b"\0" * (12*count - 1)
                doc["bufferViews"].append({"buffer":0,"byteOffset":len(data),"byteLength":len(payload)})
                doc["accessors"].append({"bufferView":2,"componentType":5121,"count":count,"type":"MAT3"})
                doc["buffers"][0]["byteLength"] = len(data)+len(payload)
                self.assertEqual(check(encode(doc,data+payload))["triangles"],1)
                doc["bufferViews"][2]["byteLength"] -= 1
                with self.assertRaisesRegex(ValueError,"outside bufferView"):
                    check(encode(doc,data+payload))

    def test_sparse_views_must_not_have_target(self):
        doc,data=fixture(indices=None)
        data = bytes((1,2,0,0))+struct.pack("<6f",1,0,0,0,1,0)
        doc["bufferViews"]=[{"buffer":0,"byteLength":2},{"buffer":0,"byteOffset":4,"byteLength":24}]
        doc["accessors"][0].pop("bufferView")
        doc["accessors"][0]["sparse"]={"count":2,"indices":{"bufferView":0,"componentType":5121},
                                      "values":{"bufferView":1}}
        doc["buffers"][0]["byteLength"]=len(data)
        for view in doc["bufferViews"]:
            view["target"]=34962
            with self.assertRaisesRegex(ValueError,"sparse bufferView cannot declare target"):
                check(encode(doc,data))
            del view["target"]

    def test_sparse_positions(self):
        doc,data=fixture(indices=None)
        data = bytes((1,2,0,0))+struct.pack("<6f",1,0,0,0,1,0)
        doc["bufferViews"]=[{"buffer":0,"byteLength":2},{"buffer":0,"byteOffset":4,"byteLength":24}]
        doc["accessors"][0].pop("bufferView")
        doc["accessors"][0]["sparse"]={"count":2,"indices":{"bufferView":0,"componentType":5121},
                                      "values":{"bufferView":1}}
        doc["buffers"][0]["byteLength"]=len(data)
        self.assertEqual(check(encode(doc,data))["triangles"],1)
        for bad in (bytes((1,1)),bytes((2,1)),bytes((1,3))):
            with self.subTest(indices=bad), self.assertRaisesRegex(ValueError,"GLB"):
                check(encode(doc,bad+data[2:]))

    def test_sparse_overrides_indices(self):
        doc,data=fixture()
        data = data[:36]+bytes((0,1,2,0))+struct.pack("<3H",0,1,2)
        doc["bufferViews"]=[{"buffer":0,"byteLength":36},{"buffer":0,"byteOffset":36,"byteLength":3},
                            {"buffer":0,"byteOffset":40,"byteLength":6}]
        doc["accessors"][1].pop("bufferView")
        doc["accessors"][1]["sparse"]={"count":3,"indices":{"bufferView":1,"componentType":5121},"values":{"bufferView":2}}
        doc["buffers"][0]["byteLength"]=len(data)
        self.assertEqual(check(encode(doc,data))["triangles"],1)

    def test_container_rejections(self):
        raw=triangle_glb()
        doc,data=fixture()
        j=chunk(b"JSON",json.dumps(doc).encode(),b" ")
        b=chunk(b"BIN\0",data)
        cases=[b"",raw[:11],b"BAD!"+raw[4:],raw[:4]+struct.pack("<I",1)+raw[8:],
               raw[:-1],raw+b"\0",container([b,j]),container([j,j,b]),container([j,b,b]),
               container([struct.pack("<I4s",1,b"JSON")+b"x"]),container([j,struct.pack("<I4s",100,b"BIN\0")]),
               container([chunk(b"JSON",b'{"asset":{},"asset":{}}',b" "),b])]
        for raw in cases:
            with self.subTest(raw=raw[:20]),self.assertRaisesRegex(ValueError,"GLB"):
                check(raw)

    def test_unknown_chunk_is_skipped(self):
        doc,data=fixture()
        self.assertEqual(check(container([chunk(b"JSON",json.dumps(doc).encode(),b" "),
                             chunk(b"BIN\0",data),chunk(b"TEST",b"safe")]))["triangles"],1)

    def test_bad_layouts_and_reference_types(self):
        mutators=[
            lambda d:d["bufferViews"][0].update(buffer=1),
            lambda d:d["bufferViews"][0].update(byteLength=999),
            lambda d:d["bufferViews"][0].update(byteOffset=1),
            lambda d:d["bufferViews"][0].update(byteStride=8),
            lambda d:d["bufferViews"][0].update(byteStride=13),
            lambda d:d["accessors"][0].update(count=999),
            lambda d:d["accessors"][0].update(count=True),
            lambda d:d["accessors"][0].update(componentType=5123),
            lambda d:d["accessors"][0].update(type=[]),
            lambda d:d["accessors"][0].update(normalized=True),
            lambda d:d["accessors"][0].update(min=[99,99,99]),
            lambda d:d["accessors"][1].update(componentType=5126),
            lambda d:d["meshes"][0]["primitives"][0].update(indices=-1),
            lambda d:d["meshes"][0]["primitives"][0].update(attributes={"POSITION":False}),
            lambda d:d["meshes"][0]["primitives"][0].update(attributes={"POSITION":0,"NORMAL":1}),
            lambda d:d["meshes"][0]["primitives"][0].update(extensions=None),
        ]
        for i,mutate in enumerate(mutators):
            with self.subTest(case=i):
                doc,data=fixture()
                mutate(doc)
                # NORMAL has same count; use a distinct accessor count to test mismatch.
                if i==14:
                    doc["accessors"][1]["count"]=2
                with self.assertRaisesRegex(ValueError,"GLB"):
                    check(encode(doc,data))

    def test_geometry_rejections(self):
        cases=[fixture(indices=(0,1,3)),fixture(indices=(0,1)),fixture(indices=(0,0,1)),
               fixture(points=((0,0,0),(1,0,0),(2,0,0))),
               fixture(indices=(0,1,2),mode=0),
               fixture(indices=(0,1,2),mode=1),fixture(mode=7)]
        for doc,data in cases:
            with self.subTest(doc=doc),self.assertRaisesRegex(ValueError,"GLB"):
                check(encode(doc,data))
        doc,data=fixture()
        for bad in (math.inf,-math.inf,math.nan):
            with self.subTest(value=bad),self.assertRaisesRegex(ValueError,"GLB"):
                check(encode(doc,struct.pack("<f",bad)+data[4:]))

    def test_scene_instances_and_transforms(self):
        doc,data=fixture()
        doc["nodes"]=[{"children":[1],"translation":[3,0,0]},{"mesh":0,"scale":[2,2,2]},
                      {"mesh":0,"matrix":[1,0,0,0,0,1,0,0,0,0,1,0,-2,0,0,1]}]
        doc["scenes"]=[{"nodes":[0,2]},{"nodes":[2]}]
        r=check(encode(doc,data))
        self.assertEqual((r["mesh_count"],r["scene_count"],r["scene_instance_count"],r["triangles"],r["scene_instance_triangles"]),(1,2,3,1,3))
        self.assertEqual(r["scene_base_bounds"],{"min":[-2,0,0],"max":[5,2,0]})

    def test_multiple_meshes_primitives_and_unused_mesh(self):
        doc,data=fixture()
        doc["meshes"][0]["primitives"].append(copy.deepcopy(doc["meshes"][0]["primitives"][0]))
        doc["meshes"].append(copy.deepcopy(doc["meshes"][0]))
        r=check(encode(doc,data))
        self.assertEqual((r["mesh_count"],r["referenced_mesh_count"],r["primitive_count"],r["triangles"],r["scene_instance_triangles"]),(2,1,4,4,2))

    def test_scene_rejections(self):
        for nodes,scenes in [
            ([{"mesh":9}],[{"nodes":[0]}]),
            ([{"mesh":0,"children":[0]}],[{"nodes":[0]}]),
            ([{"children":[1]},{"children":[0],"mesh":0}],[{"nodes":[0]}]),
            ([{"children":[2]},{"children":[2]},{"mesh":0}],[{"nodes":[0,1]}]),
            ([{"mesh":0}],[{"nodes":[1]}]),
            ([{"mesh":0}],[{"nodes":[0,0]}]),
            ([{"mesh":0}],[{"nodes":[]}]),
            ([{"mesh":0,"rotation":[1,1,1,1]}],[{"nodes":[0]}])]:
            with self.subTest(nodes=nodes,scenes=scenes):
                doc,data=fixture()
                doc.update(nodes=nodes,scenes=scenes)
                with self.assertRaisesRegex(ValueError,"GLB"):
                    check(encode(doc,data))

    def test_inventory(self):
        doc,data=fixture()
        p=doc["meshes"][0]["primitives"][0]
        p["attributes"]["TEXCOORD_0"]=0  # Inventory only; non-position formats are not certified.
        p["targets"]=[{"POSITION":0}]
        p["material"]=0
        doc.update(materials=[{}],images=[{"bufferView":0,"mimeType":"image/png"}],
                   textures=[{"source":0}],skins=[{"joints":[0]}],animations=[{}])
        r=check(encode(doc,data))
        self.assertEqual([r[k] for k in ("material_count","image_count","texture_count","uv_attribute_count",
                                       "skin_count","joint_reference_count","animation_count","morph_target_count")],[1]*8)

    def test_extension_and_uri_rejections(self):
        mutators=[lambda d:d.update(extensionsRequired=["KHR_mesh_quantization"]),
                  lambda d:d["meshes"][0]["primitives"][0].update(extensions={"KHR_draco_mesh_compression":{}}),
                  lambda d:d["bufferViews"][0].update(extensions={"EXT_meshopt_compression":{}}),
                  lambda d:d["bufferViews"][0].update(extensions={"KHR_meshopt_compression":{}}),
                  lambda d:d["nodes"][0].update(extensions={"EXT_mesh_gpu_instancing":{}}),
                  lambda d:d["buffers"][0].update(uri="https://example.invalid/data.bin"),
                  lambda d:d.update(images=[{"uri":"../private.png"}])]
        for i,mutate in enumerate(mutators):
            with self.subTest(case=i):
                doc,data=fixture()
                mutate(doc)
                with self.assertRaisesRegex(ValueError,"GLB"):
                    check(encode(doc,data))

    def test_limits(self):
        raw=triangle_glb()
        for key,limit in (("MAX_GLB_BYTES",20),("MAX_JSON_BYTES",10),("MAX_DEPTH",2),
                          ("MAX_RECORDS",1),("MAX_POSITIONS",2),("MAX_INDICES",2),
                          ("MAX_INSTANCE_POSITIONS",2),("MAX_JSON_ITEMS",3)):
            with self.subTest(limit=key),patch("blender_agent.glb."+key,limit),self.assertRaisesRegex(ValueError,"GLB"):
                check(raw)

    def test_readonly_inspection_and_digest(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"triangle.glb"
            raw=triangle_glb()
            path.write_bytes(raw)
            info=inspect_asset(path,directory)
            self.assertEqual(info["inspection"],"embedded_base_geometry")
            self.assertEqual(info["sha256"],hashlib.sha256(raw).hexdigest())
            self.assertEqual(path.read_bytes(),raw)
            with patch("blender_agent.inspect.MAX_PREVIEW_BYTES",20),self.assertRaisesRegex(ValueError,"size limit"):
                inspect_asset(path,directory)


if __name__ == "__main__":
    unittest.main()
