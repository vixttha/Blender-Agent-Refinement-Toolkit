"""Create and verify linked asset fixtures from inside Blender."""

import sys
from pathlib import Path

import bpy


def create(project, resource):
    resource.parent.mkdir(parents=True, exist_ok=True)
    generated = bpy.data.images.new("Fixture Pixel", width=1, height=1)
    generated.pixels[:] = (1, 0, 0, 1)
    generated.filepath_raw = str(resource)
    generated.file_format = "PNG"
    generated.save()
    bpy.data.images.remove(generated)

    image = bpy.data.images.load(str(resource))
    image.filepath = "//" + resource.relative_to(project.parent).as_posix()
    material = bpy.data.materials.new("Fixture Material")
    material.use_nodes = True
    texture = material.node_tree.nodes.new("ShaderNodeTexImage")
    texture.image = image
    shader = material.node_tree.nodes.get("Principled BSDF")
    material.node_tree.links.new(texture.outputs["Color"], shader.inputs["Base Color"])
    cube = bpy.data.objects["Cube"]
    cube.data.materials.clear()
    cube.data.materials.append(material)
    assert "FINISHED" in bpy.ops.wm.save_as_mainfile(filepath=str(project), relative_remap=False)


def verify(project, resource):
    assert "FINISHED" in bpy.ops.wm.open_mainfile(filepath=str(project), load_ui=False, use_scripts=False)
    image = bpy.data.images[resource.name]
    assert Path(bpy.path.abspath(image.filepath)).resolve() == resource.resolve(), image.filepath
    image.reload()
    assert tuple(image.size) == (1, 1), tuple(image.size)


def create_shared(project):
    bpy.data.objects.remove(bpy.data.objects["Cube"], do_unlink=True)
    mesh = bpy.data.meshes.new("Shared Fixture Mesh")
    mesh.from_pydata(
        [(0, 0, 0), (1, 0, 0), (0, 1, 0), (1.00005, 0, 0), (0.00005, 1, 0), (1, 1, 0)],
        [], [(0, 1, 2), (3, 5, 4)],
    )
    mesh.materials.append(bpy.data.materials.new("Shared Material"))
    layer = mesh.uv_layers.new(name="Fixture UV")
    for loop in layer.uv:
        loop.vector = (0.25, 0.75)
    for name, location in (("Fixture A", (-2, 0, 0)), ("Fixture B", (4, 1, 0))):
        instance = bpy.data.objects.new(name, mesh)
        bpy.context.collection.objects.link(instance)
        instance.location = location
    mesh.update()
    assert "FINISHED" in bpy.ops.wm.save_as_mainfile(filepath=str(project))


def verify_shared(project):
    assert "FINISHED" in bpy.ops.wm.open_mainfile(filepath=str(project), load_ui=False, use_scripts=False)
    first, second = bpy.data.objects["Fixture A"], bpy.data.objects["Fixture B"]
    assert tuple(first.location) == (-2, 0, 0)
    assert tuple(second.location) == (4, 1, 0)
    assert first.data == second.data
    mesh = first.data
    assert len(mesh.vertices) == 4 and len(mesh.polygons) == 2
    assert mesh.materials[0].name == "Shared Material"
    assert all(face.material_index == 0 for face in mesh.polygons)
    assert all(tuple(loop.vector) == (0.25, 0.75) for loop in mesh.uv_layers["Fixture UV"].uv)


def create_multi_scene(project):
    active = bpy.context.scene
    active.name = "Active Triangle"
    secondary = bpy.data.scenes.new("Secondary Cube")
    cube = bpy.data.objects["Cube"]
    previous_collections = list(cube.users_collection)
    secondary.collection.objects.link(cube)
    for collection in previous_collections:
        collection.objects.unlink(cube)

    mesh = bpy.data.meshes.new("Triangle")
    mesh.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
    mesh.update()
    triangle = bpy.data.objects.new("Triangle", mesh)
    active.collection.objects.link(triangle)
    assert bpy.context.scene == active
    assert "FINISHED" in bpy.ops.wm.save_as_mainfile(filepath=str(project))


def verify_multi_scene(project):
    assert "FINISHED" in bpy.ops.wm.open_mainfile(filepath=str(project), load_ui=False, use_scripts=False)
    assert bpy.context.scene.name == "Active Triangle"
    expected = {"Active Triangle": ("Triangle", 3, 1), "Secondary Cube": ("Cube", 8, 6)}
    assert set(bpy.data.scenes.keys()) == set(expected)
    for name, (object_name, vertices, faces) in expected.items():
        obj, = [obj for obj in bpy.data.scenes[name].objects if obj.type == "MESH"]
        assert obj.name == object_name
        assert (len(obj.data.vertices), len(obj.data.polygons)) == (vertices, faces)


if __name__ == "__main__":
    action, *paths = sys.argv[sys.argv.index("--") + 1:]
    operations = {
        "create": create,
        "verify": verify,
        "create_shared": create_shared,
        "verify_shared": verify_shared,
        "create_multi_scene": create_multi_scene,
        "verify_multi_scene": verify_multi_scene,
    }
    operations[action](*(Path(path) for path in paths))
