import ctypes
from ctypes import Structure, POINTER, c_int, c_float, c_bool, byref
import cv2
import numpy as np
import random
import os
import math

if os.name == 'nt':
    mesh_lib = ctypes.CDLL('./cpp/mesh_render.dll')
else:
    mesh_lib = ctypes.CDLL('./cpp/mesh_render.so')

class Vector3d(Structure):
    _fields_ = [('x', c_float),
                ('y', c_float),
                ('z', c_float)]

class Vector2d(Structure):
    _fields_ = [('x', c_float),
                ('y', c_float)]

class Ray(Structure):
    _fields_ = [('origin', Vector3d),
                ('direction', Vector3d)]

class Triangle(Structure):
    _fields_ = [('v0', POINTER(Vector3d)),
                ('v1', POINTER(Vector3d)),
                ('v2', POINTER(Vector3d)),
                ('imagePoint0', POINTER(Vector2d)),
                ('imagePoint1', POINTER(Vector2d)),
                ('imagePoint2', POINTER(Vector2d))]

class Mesh(Structure):
    _fields_ = [('triangles', POINTER(Triangle)),
                ('points3d', POINTER(Vector3d)),
                ('points2d', POINTER(Vector2d)),
                ('triangleCount', c_int),
                ('pointCount', c_int),
                ('use_light_info', c_bool),
                ('light_x', c_float),
                ('light_y', c_float),
                ('light_z', c_float),
                ('light_intensivity', c_float),
                ('use_shadow_info', c_bool),
                ('light_diameter', c_float),
                ('shadow_y', c_float)]


# Function prototypes
mesh_lib.create_mesh.restype = POINTER(Mesh)
mesh_lib.create_mesh.argtypes = [c_int, c_int, c_int, c_int]
mesh_lib.delete_mesh.argtypes = [POINTER(Mesh)]

mesh_lib.reproject_point.restype = c_bool
mesh_lib.reproject_point.argtypes = [POINTER(Mesh), c_float, c_float, c_float, POINTER(c_float), POINTER(c_float)]

mesh_lib.render.restype = ctypes.c_int
mesh_lib.render.argtypes = [
    ctypes.POINTER(ctypes.c_ubyte), ctypes.c_int, ctypes.c_int, ctypes.c_int,
    ctypes.POINTER(Mesh),
    ctypes.POINTER(ctypes.c_ubyte), ctypes.c_int, ctypes.c_int, ctypes.c_int,
    ctypes.c_float, ctypes.c_float, ctypes.c_float
]

class MeshModel:
    F = 50.0
    film_distance = 66.7
    def __init__(self, wcnt, hcnt, image, use_light_info = True, use_shadow_info = True):
        self.input_image = image
        self.input_height, self.input_width, C = image.shape
        self.input_stride = self.input_width * 3
        self.lens_radius = 130.0
        self.wcnt = wcnt
        self.hcnt = hcnt

        self.mesh_ptr = mesh_lib.create_mesh(self.input_width, self.input_height, wcnt, hcnt)
        self.mesh_ptr.contents.use_light_info = use_light_info
        self.mesh_ptr.contents.light_intensivity = 1.0
        self.mesh_ptr.contents.light_x = 0
        self.mesh_ptr.contents.light_y = -100
        self.mesh_ptr.contents.light_z = -100

        self.mesh_ptr.contents.use_shadow_info = use_shadow_info
        self.mesh_ptr.contents.light_diameter = 20
        self.mesh_ptr.contents.shadow_y = -80

        self.point_count = self.mesh_ptr.contents.pointCount
        self.points = [self.mesh_ptr.contents.points3d[i] for i in range(self.point_count)]

    def set_output_size(self, output_width, output_height):
        self.output_width = output_width
        self.output_height = output_height

    def render_matrix(self, input_image, input_width, input_stride, input_height, mesh, output_image, output_width, output_stride, output_height, R, L, F):
        return mesh_lib.render(input_image, input_width, input_stride, input_height, mesh, output_image, output_width, output_stride, output_height, R, L, F)

    def get_best_object_distance(self):
        return 1 / ((1 / MeshModel.F) - (1 / MeshModel.film_distance))

    def set_light_position(self, x, y, z):
        self.mesh_ptr.contents.light_x = x
        self.mesh_ptr.contents.light_y = y
        self.mesh_ptr.contents.light_z = z

    def set_shadow_y(self, y):
        self.mesh_ptr.contents.shadow_y = y

    def set_light_diameter(self, diameter):
        self.mesh_ptr.contents.light_diameter = diameter
        
    def project_point(self, x, y):
        dst_x = c_float()
        dst_y = c_float()
        result = mesh_lib.reproject_point(self.mesh_ptr, MeshModel.film_distance, x, y, ctypes.byref(dst_x), ctypes.byref(dst_y))
        return (self.output_width / 2) - dst_x.value, (self.output_height / 2) - dst_y.value
        
    def render(self, background_template = None):
        output_stride = self.output_width * 4
        output_image = np.zeros((self.output_height, output_stride), dtype=np.uint8)

        input_image_ptr = self.input_image.ctypes.data_as(ctypes.POINTER(ctypes.c_ubyte))
        output_image_ptr = output_image.ctypes.data_as(ctypes.POINTER(ctypes.c_ubyte))

        self.render_matrix(input_image_ptr, self.input_width, self.input_stride, self.input_height, self.mesh_ptr, output_image_ptr, self.output_width, output_stride, self.output_height, self.lens_radius, MeshModel.film_distance, MeshModel.F)
        img = output_image.reshape((self.output_height, self.output_width, 4))
        mask = img[:,:,3]        
        img = img[:,:,:3]
        if background_template is not None:
            background = np.copy(background_template)
            img = cv2.rotate(img, cv2.ROTATE_180)
            mask = cv2.rotate(mask, cv2.ROTATE_180)
            for x in range(self.output_height):
                for y in range(self.output_width):
                    a = mask[x, y] / 255.0                    
                    background[x, y, 0] = img[x, y, 0] * a + background[x, y, 0] * (1 - a)
                    background[x, y, 1] = img[x, y, 1] * a + background[x, y, 1] * (1 - a)
                    background[x, y, 2] = img[x, y, 2] * a + background[x, y, 2] * (1 - a)

            return background

        for x in range(self.output_height):
            for y in range(self.output_width):
                a = mask[x, y] / 255.0
                img[x, y, 0] = img[x, y, 0] * a
                img[x, y, 1] = img[x, y, 1] * a
                img[x, y, 2] = img[x, y, 2] * a
        
        img = cv2.rotate(img, cv2.ROTATE_180)
        return img

    def cylynder_horizontal(self, R = None, dA = 0):
        h, w = self.input_height, self.input_width
        dx, dy = w // 2, h // 2
        if R == None: R = w * 3
        A = w / R
        for point in self.points:
            Ai = - A / 2 + A * point.x / h + dA
            point.z = (R - R * math.cos(Ai))
            point.x = R * math.sin(Ai)
            point.y -= dy

    def cylynder_vertical(self, R = None, dA = 0):
        h, w = self.input_height, self.input_width
        dx, dy = w // 2, h // 2
        if R == None: R = h * 3
        A = h / R
        for point in self.points:
            Ai = - A / 2 + A * point.y / w + dA
            point.z = (R - R * math.cos(Ai))
            point.x -= dx
            point.y = R * math.sin(Ai)            

    def shift(self, dx, dy, dz):
        for point in self.points:            
            point.x += dx
            point.y += dy
            point.z += dz

    def get_mass_center(self):
        x = 0
        y = 0
        z = 0    
        for point in self.points:
            x += point.x
            y += point.y
            z += point.z

        return x/len(self.points), y/len(self.points), z/len(self.points)

    def rotate_z(self, a):
        cx, cy, cz = self.get_mass_center()
        for point in self.points:
            translated_x = point.x - cx
            translated_y = point.y - cy
            rotated_x = translated_x * math.cos(a) - translated_y * math.sin(a)
            rotated_y = translated_x * math.sin(a) + translated_y * math.cos(a)
            point.x = rotated_x + cx
            point.y = rotated_y + cy

    def rotate_x(self, a):
        cx, cy, cz = self.get_mass_center()
        for point in self.points:
            translated_z = point.z - cz
            translated_y = point.y - cy
            rotated_z = translated_z * math.cos(a) - translated_y * math.sin(a)
            rotated_y = translated_z * math.sin(a) + translated_y * math.cos(a)
            point.z = rotated_z + cz
            point.y = rotated_y + cy

    def rotate_y(self, a):
        cx, cy, cz = self.get_mass_center()
        for point in self.points:
            translated_z = point.z - cz
            translated_x = point.x - cx
            rotated_x = translated_x * math.cos(a) - translated_z * math.sin(a)
            rotated_z = translated_x * math.sin(a) + translated_z * math.cos(a)
            point.x = rotated_x + cx
            point.z = rotated_z + cz

    def rotate(self, a):
        cos_theta = math.cos(a)
        sin_theta = math.sin(a)
        for point in self.points:
            x_new = point.x * cos_theta - point.y * sin_theta
            y_new = point.x * sin_theta + point.y * cos_theta
            point.x = x_new
            point.y = y_new

    def free(self):
        mesh_lib.delete_mesh(self.mesh_ptr)

def get_random_augment(image, output_width, output_height, points = [], backgrounds = None, background_fnames = None):
    if backgrounds is not None and background_fnames is not None:
        raise Exception("backgrounds and background_fnames can't be not None both")
    if backgrounds is None and background_fnames is None:
        raise Exception("backgrounds and background_fnames can't be None both")
    h, w, dc = image.shape

# calculate best size
    object_distance = 1 / ((1 / MeshModel.F) - (1 / MeshModel.film_distance))
    best_width = output_width * object_distance / MeshModel.film_distance
    best_height = output_height * object_distance / MeshModel.film_distance    
    k = min(best_height / h, best_width / w) * random.uniform(0.5, 0.9)
    image = cv2.resize(image, (int(w * k), int(h * k)), interpolation = cv2.INTER_LINEAR)
    points = [(p[0] * k, p[1] * k) for p in points]
    h, w, dc = image.shape
    if background_fnames is not None:
        background = cv2.imread(random.choice(background_fnames))
    else:
        background = random.choice(backgrounds)
    background = cv2.resize(background, (output_width, output_height), interpolation = cv2.INTER_LINEAR)

#render
    mesh = MeshModel(50, 50, image, True, True)
    mesh.lens_radius = 1
    if random.choice([True, False]):
        mesh.cylynder_vertical(R = w * random.uniform(4, 20))
    else:
        mesh.cylynder_horizontal(R = h * random.uniform(4, 20))
    mesh.shift(0, 0, mesh.get_best_object_distance())
    mesh.rotate_y(math.radians(random.uniform(-5, 5)))
    mesh.rotate_x(math.radians(random.uniform(-5, 5)))
    mesh.rotate_z(math.radians(random.uniform(-5, 5)))
    mesh.shift(random.uniform(-5, 5), random.uniform(-5, 5), random.uniform(-5, 5))
    mesh.set_output_size(output_width, output_height)
    mesh.set_light_diameter(random.uniform(10.0, 50.0))
    mesh.set_shadow_y(random.uniform(-80.0, 0.0))
    output_image = mesh.render(background)

    new_points = []
    for x, y in points:
        new_x, new_y = mesh.project_point(x, y)
        new_points.append((new_x, new_y))
    
    mesh.free()
    return output_image, new_points



