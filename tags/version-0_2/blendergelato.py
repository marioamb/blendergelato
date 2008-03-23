
import Blender
from math import pi, atan2

VERBOSE  = 2
FILENAME = '/tmp/output.pyg'

class gelato_pyg:
	def __init__(self, filename, verbose = 1):
		self.verbose     = verbose
		self.filename    = filename
		self.LIGHTFACTOR = 50
		self.PRECISION	 = 5

		try:
			self.file = open(filename, 'w')

		except IOError:
			if (self.verbose > 0) : print 'Error: cannot write file', filename

	def head(self):
		curcam  = self.scene.getCurrentCamera()
		camera  = Blender.Camera.Get(curcam.getData().name)
		context = self.scene.getRenderingContext()
		matrix  = curcam.getInverseMatrix()
		sizex   = float(context.imageSizeX())
		sizey   = float(context.imageSizeY())
		scale   = context.getRenderWinSize() / 100.0

		if (sizex > sizey):
			fac = sizey / sizex
		else:
			fac = 1.0

		self.file.write('Output ("file.tiff", "iv", "rgba", "main")\n\n')

		self.file.write('Attribute ("int[2] resolution", (%s, %s))\n' %
			(int(sizex * scale), int(sizey * scale )))

		self.file.write('Attribute ("float pixelaspect", %f)\n' %
			(float(context.aspectRatioX()) / float(context.aspectRatioY())))

		self.file.write('Attribute ("string projection", "perspective")\n')
		self.file.write('Attribute ("float near", %f)\n' % camera.clipStart)
		self.file.write('Attribute ("float far", %f)\n' % camera.clipEnd)
		self.file.write('Attribute ("float fov", %f)\n' % (360.0 * atan2(16.0 * fac, camera.lens) / pi))

		self.file.write('SetTransform (%f, %f, %f, %f, %f, %f, %f, %f, %f, %f, %f, %f, %f, %f, %f, %f)\n' %
			(matrix[0][0], matrix[0][1], -matrix[0][2], matrix[0][3],
			 matrix[1][0], matrix[1][1], -matrix[1][2], matrix[1][3],
			 matrix[2][0], matrix[2][1], -matrix[2][2], matrix[2][3],
			 matrix[3][0], matrix[3][1], -matrix[3][2], matrix[3][3]))

		self.file.write('World ()\n')

	def tail(self):
		self.file.write('\nRender ("camera")\n')

	def translate(self, obj):
		t = obj.matrix.translationPart()
		self.file.write('Translate (%f, %f, %f)\n' % (t.x, t.y, t.z))

	def transform(self, obj):
		self.file.write('SetTransform (%f, %f, %f, %f, %f, %f, %f, %f, %f, %f, %f, %f, %f, %f, %f, %f)\n' %
			(obj.matrix[0][0], obj.matrix[0][1], obj.matrix[0][2], obj.matrix[0][3],
			 obj.matrix[1][0], obj.matrix[1][1], obj.matrix[1][2], obj.matrix[1][3],
			 obj.matrix[2][0], obj.matrix[2][1], obj.matrix[2][2], obj.matrix[2][3],
			 obj.matrix[3][0], obj.matrix[3][1], obj.matrix[3][2], obj.matrix[3][3]))

	def ambientlight(self):
		world = Blender.World.GetCurrent()

		if (world and (world.getAmb() != [0.0, 0.0, 0.0])):
			self.file.write('\nLight ("%s", "ambientlight", '
			                '"float intensity", %f, '
					'"color lightcolor", (%f, %f, %f))\n' %
				(world.getName(),
				 world.getRange(),
				 world.amb[0], world.amb[1], world.amb[2]))

	def pointlight(self, obj, lamp, name):
		f = obj.matrix.translationPart()

		self.file.write('Light ("%s", "pointlight", '
		                '"point from", (%f, %f, %f), '
				'"float intensity", %f, '
				'"color lightcolor", (%f, %f, %f))\n' %
			(name,
			 f.x, f.y, f.z,
			 lamp.getEnergy() * self.LIGHTFACTOR,
			 lamp.R, lamp.G, lamp.B))

	def distantlight(self, obj, lamp, name):
		f = obj.matrix.translationPart()
		t = Blender.Mathutils.Vector(obj.matrix[3][0] - obj.matrix[2][0],
		                             obj.matrix[3][1] - obj.matrix[2][1],
					     obj.matrix[3][2] - obj.matrix[2][2])

		self.file.write('Light ("%s", "distantlight", '
		                '"point from", (%f, %f, %f), '
		                '"point to", (%f, %f, %f), '
		                '"float intensity", %f, '
				'"color lightcolor", (%f, %f, %f))\n' %
			(name,
			 f.x, f.y, f.z,
			 t.x, t.y, t.z,
			 lamp.getEnergy() * self.LIGHTFACTOR,
			 lamp.R, lamp.G, lamp.B))

	def spotlight(self, obj, lamp, name):
		f = obj.matrix.translationPart()
		t = Blender.Mathutils.Vector(obj.matrix[3][0] - obj.matrix[2][0],
		                             obj.matrix[3][1] - obj.matrix[2][1],
					     obj.matrix[3][2] - obj.matrix[2][2])

		self.file.write('Light ("%s", "spotlight", '
		                '"point from", (%f, %f, %f), '
		                '"point to", (%f, %f, %f), '
		                '"float intensity", %f, '
				'"color lightcolor", (%f, %f, %f), '
				'"float coneangle", %f, '
				'"float conedeltaangle", %f)\n' %
			(name,
			 f.x, f.y, f.z,
			 t.x, t.y, t.z,
			 lamp.getEnergy() * self.LIGHTFACTOR,
			 lamp.R, lamp.G, lamp.B,
			 lamp.spotSize * pi/360.0,
			 lamp.spotBlend * lamp.spotSize * pi/360.0))

	def light(self, obj):
		name = obj.name
		lamp = Blender.Lamp.Get(obj.getData().name)

		type = lamp.getType()
		if (type == Blender.Lamp.Types['Lamp']):
			self.pointlight(obj, lamp, name)
		elif (type == Blender.Lamp.Types['Sun']):
			self.distantlight(obj, lamp, name)
		elif (type == Blender.Lamp.Types['Spot']):
			self.spotlight(obj, lamp, name)

	def mesh(self, obj):
		name = obj.name
		mesh = Blender.NMesh.GetRawFromObject(name)

		if len(mesh.faces) == 0:
			return

		self.file.write('\nPushAttributes ()\n')
		self.file.write('Attribute ("string name", "%s")\n' % name)

		if (mesh.materials):
			material = Blender.Material.Get(mesh.materials[0].name)
			self.file.write('Attribute ("color C", (%f, %f, %f))\n' %
				(material.R, material.G, material.B))
			alpha = material.alpha
			if (alpha < 1.0):
				self.file.write('Attribute ("color opacity", (%f, %f, %f))\n' %
					(alpha, alpha, alpha))

		self.file.write('Shader ("surface", "plastic" )\n')

		self.transform(obj)

		self.file.write('Mesh ("linear", (')

		nlist = []
		for face in mesh.faces:
			nlist.append(str(len(face.v)))
		self.file.write(', '.join(nlist))

		self.file.write('), (',)

		nlist = []
		for face in mesh.faces:
                	for vert in face.v:
                        	nlist.append(str(vert.index))
		self.file.write(', '.join(nlist))

		self.file.write('), "vertex point P", (',)

		nlist = []
		for vert in mesh.verts:
			nlist.append('%f, %f, %f' %
				(round(vert.co[0], self.PRECISION),
				 round(vert.co[1], self.PRECISION),
				 round(vert.co[2], self.PRECISION)))
		self.file.write(', '.join(nlist))

		self.file.write('))\n')
		self.file.write('PopAttributes ()\n')

	def lights(self):
		self.ambientlight()
		for obj in self.objects:
			type = obj.getType()
			if (type == 'Lamp'):
				self.light(obj)

	def geometries(self):
		for obj in self.objects:
			type = obj.getType()
			if (type == 'Mesh'):
				self.mesh(obj)

	def export(self, scene):
		self.scene   = scene
		self.objects = scene.getChildren()
		if (self.verbose > 1) : print 'Info: starting Gelato pyg export to', self.filename
		self.head()
		self.lights()
		self.geometries()
		self.tail()
		if (self.verbose > 1) : print 'Info: finished Gelato pyg export'

pyg = gelato_pyg(FILENAME, VERBOSE)
pyg.export(Blender.Scene.GetCurrent())

