#!BPY

"""
Name: 'Blender Gelato'
Blender: 241
Group: 'Render'
Tooltip: 'Render with NVIDIA Gelato ®'
"""

__author__ = 'Mario Ambrogetti'
__version__ = '0.7'
__url__ = ['']
__bpydoc__ = """\
Blender to NVIDIA Gelato ®
"""

# ***** BEGIN GPL LICENSE BLOCK *****
#
# Script copyright (C) Mario Ambrogetti
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software Foundation,
# Inc., 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.
#
# ***** END GPL LICENCE BLOCK *****

import Blender, os
from math import degrees, radians, atan2

GELATOHOME = os.getenv('GELATOHOME')
if (GELATOHOME):
	GELATO = os.path.join(GELATOHOME, 'bin', 'gelato')
else:
	GELATO  = 'gelato'

if (os.name == 'nt'):
	FILENAME = 'C:/gelato.pyg'
else:
	FILENAME = '/tmp/gelato.pyg'

class gelato_pyg:
	def __init__(self):
		self.PRECISION     = 5
		self.SCALEBIAS     = 0.1
		self.FACTORAMBIENT = 200

	def head(self):
		curcam  = self.scene.getCurrentCamera()

		self.camera_name = curcam.name

		try:
			scale = self.context.getRenderWinSize() / 100.0
		except:
			scale = 1.0

		self.file.write('Parameter ("string filter", "%s")\n' %
			self.filter)

		self.file.write('Parameter ("float[2] filterwidth", (%f, %f))\n' %
			(self.filterwidth_x , self.filterwidth_y))

		if (self.preview):
			self.file.write('Output ("%s", "iv", "%s", "%s")\n' %
				(self.title, self.data, self.camera_name))

		if (self.format != 'null'):
			self.file.write('Output ("%s", "%s", "%s", "%s")\n' %
				(self.output, self.format, self.data, self.camera_name))

		self.file.write('\n')

		self.file.write('Attribute ("int verbosity", %d)\n' %
			self.verbose)

		self.file.write('Attribute ("int[2] resolution", (%d, %d))\n' %
			(int(self.sizex * scale), int(self.sizey * scale)))

		self.file.write('Attribute ("float pixelaspect", 1.0)\n')

		self.file.write('Attribute ("int[2] spatialquality", (%d, %d))\n' %
			(self.spatialquality_x , self.spatialquality_y))

		self.file.write('Attribute ("string bucketorder", "%s")\n' %
			self.bucketorder)

		self.file.write('Attribute ("int twosided", 1)\n')

		self.camera(curcam)

		if (not self.ao and self.shadows):
			self.cameras_shadows()

		self.file.write('\nWorld ()\n')

		if (self.ao):
			self.ambient_occlusion()
		elif (self.sky):
			# enableSky()
			self.background_color()

	def tail(self):
		self.file.write('\nRender ("%s")\n'
			% self.camera_name)

	def write_matrix(self, matrix):
		self.file.write('((%f, %f, %f, %f), (%f, %f, %f, %f), (%f, %f, %f, %f), (%f, %f, %f, %f))\n' % (
			matrix[0][0], matrix[0][1], matrix[0][2], matrix[0][3],
			matrix[1][0], matrix[1][1], matrix[1][2], matrix[1][3],
			matrix[2][0], matrix[2][1], matrix[2][2], matrix[2][3],
			matrix[3][0], matrix[3][1], matrix[3][2], matrix[3][3]))

	def set_transform(self, matrix):
		self.file.write('SetTransform ')
		self.write_matrix(matrix)

	def append_transform(self, matrix):
		self.file.write('AppendTransform ')
		self.write_matrix(matrix)

	def convert_translation(self, matrix):
		trans  = matrix.translationPart()
		self.file.write('Translate (%f, %f, %f)\n' %
			(trans.x, trans.y, trans.z))

	def convert_matrix(self, matrix):
		euler  = matrix.toEuler()
		trans  = matrix.translationPart()
		scale  = matrix.scalePart()

		self.file.write('Translate (%f, %f, %f)\n' %
			(trans.x, trans.y, trans.z))

		self.file.write('Scale (%f, %f, %f)\n' %
			(scale.x, scale.y, -scale.z))

		self.file.write('Rotate (%f, 0, 0, 1)\n' %
			euler.z)

		self.file.write('Rotate (%f, 0, 1, 0)\n' %
			-euler.y)

		self.file.write('Rotate (%f, 1, 0, 0)\n' %
			-euler.x)

	def camera_shadows_name(self, name, idx):
		if (idx < 0):
			return '__' + name + '-shadows' + '__'
		else:
			return '__' + name + '-shadows-' + str(idx) + '__'

	def instance_name(self, name, idx):
		if (idx < 0):
			return name
		else:
			return '__' + name + '-' + str(idx) + '__'

	def file_shadows_name(self, name, idx):
		if (idx < 0):
			return name + '.sm'
		else:
			return name + '-' + str(idx) + '.sm'

	def background_color(self):
		if (not self.world):
			return

		col = self.world.getHor()

		self.file.write('\nPushAttributes ()\n')

		self.file.write('Attribute ("color C", (%f, %f, %f))\n' %
			(col[0], col[1], col[2]))

		self.file.write('Shader ("surface", "constant")\n')
		self.file.write('Input ("backplane.pyg")\n')

		self.file.write('PopAttributes ()\n')

	def ambient_occlusion(self):
		self.file.write('\nAttribute ("string geometryset", "+localocclusion")\n')
		self.file.write('Attribute ("float occlusion:maxpixeldist", 20)\n')
		self.file.write('Attribute ("float occlusion:maxerror", 0.2)\n')
		self.file.write('Shader ("surface", "ambocclude", '
				'"string occlusionname", "localocclusion", '
				'"float samples", 512, '
				'"float bias", 0.01)\n')

	def ambientlight(self):
		if (not self.world):
			return

		col = self.world.getAmb()
		if (col != [0.0, 0.0, 0.0]):
			self.file.write('\nLight ("%s", "ambientlight", '
					'"float intensity", %f, '
					'"color lightcolor", (%f, %f, %f))\n' % (
				self.world.getName(),
				self.lights_factor / self.FACTORAMBIENT,
				col[0], col[1], col[2]))

	def pointlight(self, obj, lamp, matrix, idx):
		name = obj.name

		self.file.write('\nPushTransform ()\n')

		self.convert_translation(matrix)

		self.file.write('Light ("%s", "pointlight", '
				'"float falloff", 2.0, '
				'"float intensity", %f, '
				'"color lightcolor", (%f, %f, %f))\n' % (
			self.instance_name(name, idx),
			lamp.getEnergy() * self.lights_factor,
			lamp.R, lamp.G, lamp.B))

		self.file.write('PopTransform ()\n')

	def distantlight(self, obj, lamp, matrix, idx):
		name = obj.name

		self.file.write('\nPushTransform ()\n')

		self.convert_matrix(matrix)

		if (self.shadows):
			self.file.write('Parameter ("string shadowname", "%s")\n' %
				self.file_shadows_name(name, idx))

		self.file.write('Light ("%s", "distantlight", '
				'"float intensity", %f, '
				'"color lightcolor", (%f, %f, %f), '
				'"float shadowbias", %f)\n' % (
			self.instance_name(name, idx),
			lamp.getEnergy() * self.lights_factor,
			lamp.R, lamp.G, lamp.B,
			lamp.bias * self.SCALEBIAS))

		self.file.write('PopTransform ()\n')

	def spotlight(self, obj, lamp, matrix, idx):
		name = obj.name

		self.file.write('\nPushTransform ()\n')

		self.convert_matrix(matrix)

		if (self.shadows):
			self.file.write('Parameter ("string shadowname", "%s")\n' %
				self.file_shadows_name(name, idx))

		self.file.write('Light ("%s", "spotlight", '
				'"float falloff", 2.0, '
				'"float intensity", %f, '
				'"color lightcolor", (%f, %f, %f), '
				'"float coneangle", %f, '
				'"float conedeltaangle", %f, '
				'"float shadowbias", %f)\n' % (
			self.instance_name(name, idx),
			lamp.getEnergy() * self.lights_factor,
			lamp.R, lamp.G, lamp.B,
			radians(lamp.spotSize / 2.0),
			radians(lamp.spotBlend * lamp.spotSize / 4.0),
			lamp.bias * self.SCALEBIAS))

		self.file.write('PopTransform ()\n')

	def camera_light(self, obj, lamp, name, matrix, idx):
		self.file.write('\nPushTransform ()\n')

		self.convert_matrix(matrix)

		self.file.write('Camera ("%s", '
				'"int[2] resolution", (%d, %d), '
				'"int[2] spatialquality", (%d, %d), '
				'"string projection", "perspective", "float fov", %f, '
				'"float near", %f, '
				'"float far", %f)\n' % (
			self.camera_shadows_name(name, idx),
			lamp.bufferSize, lamp.bufferSize,
			lamp.samples, lamp.samples,
			lamp.spotSize,
			lamp.clipStart,
			lamp.clipEnd))

		self.file.write('PopTransform ()\n')

		self.file.write('Output ("%s", '
				'"shadow", "z", "%s", "float[2] filterwidth", (1,1), '
                                '"int dynamic", %d)\n' % (
			self.file_shadows_name(name, idx),
			self.camera_shadows_name(name, idx),
			self.dynamic_shadows))

	def camera(self, obj):
		type = obj.getType()
		if (type != 'Camera'):
			return

		name   = obj.name
		matrix = obj.getMatrix()
		cam    = Blender.Camera.Get(obj.getData().name)

		self.file.write('\nPushTransform ()\n')
		self.file.write('PushAttributes ()\n')

		self.convert_matrix(matrix)

		self.file.write('Attribute ("float near", %f)\n' %
			cam.clipStart)

		self.file.write('Attribute ("float far", %f)\n' %
			cam.clipEnd)

		if (cam.getType()):
			# orthographic camera
			aspx = cam.scale / 2.0
			aspy = aspx * self.sizey / self.sizex * float(self.context.aspectRatioY()) / float(self.context.aspectRatioX())

			self.file.write('Attribute ("string projection", "orthographic")\n')
			self.file.write('Attribute ("float[4] screen", (%f, %f, %f, %f))\n' %
				(-aspx, aspx, -aspy, aspy))
		else:
			# perspective camera
			if (self.context.aspectRatioX() != self.context.aspectRatioY()):
				aspx = self.sizex / self.sizey
				aspy = float(self.context.aspectRatioY()) / float(self.context.aspectRatioX())
				self.file.write('Attribute ("float[4] screen", (%f, %f, %f, %f))\n' %
					(-aspx, aspx, -aspy, aspy))

			if (self.sizex > self.sizey):
				fac = self.sizey / self.sizex
			else:
				fac = 1.0

			self.file.write('Attribute ("string projection", "perspective")\n')
			self.file.write('Attribute ("float fov", %f)\n' %
				degrees(2*atan2(16.0 * fac, cam.lens)))

		self.file.write('Camera ("%s")\n' %
			name)

		self.file.write('PopAttributes ()\n')
		self.file.write('PopTransform ()\n')

	def camera_shadows(self, obj, matrix = None, idx = -1):
		type = obj.getType()
		if (type != 'Lamp'):
			return

		name = obj.name
		lamp = Blender.Lamp.Get(obj.getData().name)

		if (matrix):
			mat = matrix
		else:
			mat = obj.matrix

		ltype = lamp.getType()
		if (ltype == Blender.Lamp.Types.Spot or ltype == Blender.Lamp.Types.Sun or ltype == Blender.Lamp.Types.Lamp):
			self.camera_light(obj, lamp, name, mat, idx)

	def light(self, obj, matrix = None, idx = -1):
		type = obj.getType()
		if (type != 'Lamp'):
			return

		name = obj.name
		lamp = Blender.Lamp.Get(obj.getData().name)

		if (matrix):
			mat = matrix
		else:
			mat = obj.matrix

		ltype = lamp.getType()
		if (ltype == Blender.Lamp.Types.Lamp):
			self.pointlight(obj, lamp, mat, idx)
		elif (ltype == Blender.Lamp.Types.Sun):
			self.distantlight(obj, lamp, mat, idx)
		elif (ltype == Blender.Lamp.Types.Spot):
			self.spotlight(obj, lamp, mat, idx)

	def mesh(self, obj, matrix = None, idx = -1):
		type = obj.getType()
		if ((type != 'Mesh') and (type != 'Surf')):
			return

		name = obj.name

		try:
			mesh = Blender.NMesh.GetRawFromObject(name)
		except:
			return

		if (len(mesh.faces) == 0):
			return

		self.file.write('\nPushAttributes ()\n')
		self.file.write('Attribute ("string name", "%s")\n' % self.instance_name(name, idx))

		if (not mesh.mode & Blender.NMesh.Modes.TWOSIDED):
			self.file.write('Attribute ("int twosided", 0)\n')

		if (not self.ao):
			if (mesh.materials):
				material = Blender.Material.Get(mesh.materials[0].name)
				self.file.write('Attribute ("color C", (%f, %f, %f))\n' %
					(material.R, material.G, material.B))
				alpha = material.alpha
				if (alpha < 1.0):
					self.file.write('Attribute ("color opacity", (%f, %f, %f))\n' %
						(alpha, alpha, alpha))
			self.file.write('Shader ("surface", "plastic" )\n')

		if (matrix):
			self.set_transform(matrix)
		else:
			self.set_transform(obj.matrix)

		self.file.write('Mesh ("linear", (')

		nlist = []
		for face in mesh.faces:
			nlist.append(str(len(face.v)))
		self.file.write(', '.join(nlist))

		self.file.write('), (')

		# if NURBS smooth surface
		if (type == 'Surf'):
			smooth = 1
		else:
			smooth = 0

		nlist = []
		for face in mesh.faces:
			if (face.smooth):
				smooth = 1
			for vert in face.v:
				nlist.append(str(vert.index))
		self.file.write(', '.join(nlist))

		self.file.write('), "vertex point P", (')

		nlist   = []
		normals = []
		for vert in mesh.verts:
			normals.append(vert.no)
			nlist.append('(%f, %f, %f)' % (
				round(vert.co.x, self.PRECISION),
				round(vert.co.y, self.PRECISION),
				round(vert.co.z, self.PRECISION)))
		self.file.write(', '.join(nlist))

		if (smooth):
			for face in mesh.faces:
				if (face.smooth):
					continue
				for vert in face.v:
					normals[vert.index] = face.no

			self.file.write('), "vertex normal N", (')

			nlist = []
			for nor in normals:
				nlist.append('(%f, %f, %f)' % (
					round(nor[0], self.PRECISION),
					round(nor[1], self.PRECISION),
					round(nor[2], self.PRECISION)))
			self.file.write(', '.join(nlist))

		self.file.write('))\n')

		self.file.write('PopAttributes ()\n')

	def visible(self, obj):
		if ((obj.users > 1) and  (set(obj.layers) & self.viewlayer == set([]))):
			if (self.verbose > 1):
				print 'Info: Object', obj.name, 'invisible'
			return False
		return True

	def build(self, obj, method):
		if (not self.visible(obj)):
			return
		try:
			# get duplicate object
			dupobjs = obj.DupObjects
		except:
			dupobjs = None

		if (dupobjs):
			i = 0
			for dobj, mat in dupobjs:
				exec('self.%s(dobj, mat, %d)' % (method, i))
				i = i +1
			return
		else:
			try:
				# skip object if DupObjects
				if (obj.parent and obj.parent.DupObjects):
					return
			except:
				pass

		exec('self.%s(obj)' % method)

	def cameras_shadows(self):
		for obj in self.objects:
			self.build(obj, 'camera_shadows');

	def lights(self):
		self.ambientlight()
		for obj in self.objects:
			self.build(obj, 'light');

	def geometries(self):
		for obj in self.objects:
			if (self.verbose > 1):
				print 'Info: Object', obj.name, 'type', obj.getType()
			self.build(obj, 'mesh');

	def setup(self):
		# verbosity
		try:
			rt = Blender.Get('rt')
			if (rt == 42):
				self.verbose = 0
			if (rt == 43):
				self.verbose = 2
			else:
				self.verbose = 1
		except:
			self.verbose = 1

		# filename
		self.filename = gui_filename.val

		# ambient occlusion
		self.ao = gui_ambient_occlusion.val

		# output file name image
		v = gui_format.val
		if (v == 1):
			self.format = 'tiff'
			self.suffix = '.tif'
		elif (v == 2):
			self.format = 'jpg'
			self.suffix = '.jpg'
		elif (v == 3):
			self.format = 'targa'
			self.suffix = '.tga'
		elif (v == 4):
			self.format = 'ppm'
			self.suffix = '.ppm'
		elif (v == 5):
			self.format = 'OpenEXR'
			self.suffix = '.exr'
		else:
			self.format = 'null'
			self.suffix = None

		file_ext = os.path.splitext(self.filename)
		self.title = os.path.basename(file_ext[0])
		if (self.suffix):
			self.output = file_ext[0] + self.suffix

		# output data
		try:
			self.data = convert_data[gui_data.val]
		except IndexError:
			self.data = convert_data[0]

		# bucketorder
		try:
			self.bucketorder = convert_bucketorder[gui_bucketorder.val]
		except IndexError:
			self.bucketorder = convert_bucketorder[0]

		# pixel filter
		try:
			self.filter = convert_filter[gui_filter.val]
		except IndexError:
			self.filter = convert_filter[0]

		# spatialquality
		self.spatialquality_x = int(gui_antialiasing_x.val)
		self.spatialquality_y = int(gui_antialiasing_y.val)

		# filterwidth
		self.filterwidth_x = float(gui_filterwidth_x.val)
		self.filterwidth_y = float(gui_filterwidth_y.val)

		# preview window
		self.preview = gui_preview.val

		# background color
		self.sky = gui_sky.val

		# dynamic shadows
		self.shadows = self.dynamic_shadows = gui_dynamic_shadows.val

		# light factor
		self.lights_factor = gui_lights_factor.val

	def export(self, scene):
		self.scene = scene

		self.setup()

		if (self.verbose > 0):
			timestart= Blender.sys.time()
			print 'Info: starting Gelato pyg export to', self.filename

		try:
			self.file = open(self.filename, 'w')
		except IOError:
			Draw.PupMenu('Error: cannot write file' + self.filename)
			return

		self.viewlayer = set(Blender.Window.ViewLayer())
		self.objects   = scene.getChildren()
		self.world     = Blender.World.GetCurrent()
		self.context   = self.scene.getRenderingContext()
		self.sizex     = float(self.context.imageSizeX())
		self.sizey     = float(self.context.imageSizeY())

		self.head()
		if (not self.ao):
			self.lights()
		self.geometries()
		self.tail()

		self.file.close()

		if (self.verbose > 0):
			print 'Info: finished Gelato pyg export (%.2fs)' % (Blender.sys.time() - timestart)

# Persistent data

KEYREGISTER = 'BlenderGelato'

def default_value():
	global gui_filename, gui_ambient_occlusion, gui_format, gui_data, gui_bucketorder
	global gui_antialiasing_x, gui_antialiasing_y, gui_filter, gui_filterwidth_x, gui_filterwidth_y
	global gui_preview, gui_sky, gui_dynamic_shadows, gui_lights_factor

	gui_filename          = Blender.Draw.Create(FILENAME)
	gui_ambient_occlusion = Blender.Draw.Create(0)
	gui_format            = Blender.Draw.Create(0)		# iv
	gui_data              = Blender.Draw.Create(0)		# rgb
	gui_bucketorder       = Blender.Draw.Create(2)		# spiral
	gui_antialiasing_x    = Blender.Draw.Create(4)
	gui_antialiasing_y    = Blender.Draw.Create(4)
	gui_filterwidth_x     = Blender.Draw.Create(2.0)
	gui_filterwidth_y     = Blender.Draw.Create(2.0)
	gui_filter            = Blender.Draw.Create(0)		# gaussian
	gui_preview           = Blender.Draw.Create(1)
	gui_sky               = Blender.Draw.Create(1)
	gui_dynamic_shadows   = Blender.Draw.Create(0)
	gui_lights_factor     = Blender.Draw.Create(50.0)

def update_registry():
	d = {
		'filename'          : gui_filename.val,
		'ambient_occlusion' : gui_ambient_occlusion.val,
		'format'            : gui_format.val,
		'data'              : gui_data.val,
		'bucketorder'       : gui_bucketorder.val,
		'antialiasing_x'    : gui_antialiasing_x.val,
		'antialiasing_y'    : gui_antialiasing_y.val,
		'filterwidth_x'     : gui_filterwidth_x.val,
		'filterwidth_y'     : gui_filterwidth_y.val,
		'filter'            : gui_filter.val,
		'preview'           : gui_preview.val,
		'sky'               : gui_sky.val,
		'dynamic_shadows'   : gui_dynamic_shadows.val,
		'lights_factor'     : gui_lights_factor.val,
	}
	Blender.Registry.SetKey(KEYREGISTER, d, True)

default_value()

rdict = Blender.Registry.GetKey(KEYREGISTER, True)
if (rdict):
	try:
		gui_filename              = Blender.Draw.Create(rdict['filename'])
		gui_ambient_occlusion.val = rdict['ambient_occlusion']
		gui_format.val            = rdict['format']
		gui_data.val              = rdict['data']
		gui_bucketorder.val       = rdict['bucketorder']
		gui_antialiasing_x.val    = rdict['antialiasing_x']
		gui_antialiasing_y.val    = rdict['antialiasing_y']
		gui_filterwidth_x.val     = rdict['filterwidth_x']
		gui_filterwidth_y.val     = rdict['filterwidth_y']
		gui_filter.val            = rdict['filter']
		gui_preview.val           = rdict['preview']
		gui_sky.val               = rdict['sky']
		gui_dynamic_shadows.val   = rdict['dynamic_shadows']
		gui_lights_factor.val      = rdict['lights_factor']
	except:
		update_registry()

# GUI

ID_BUTTON_SAVE    = 1000
ID_BUTTON_RENDER  = 1001
ID_FILENAME       = 1002
ID_SELECT         = 1003
ID_BUTTON_DEFAULT = 1004
ID_BUTTON_EXIT    = 1005

convert_data        = ['rgb', 'rgba', 'z', 'avgz', 'volz']
convert_bucketorder = ['horizontal', 'vertical', 'spiral']
convert_filter      = ['gaussian', 'box', 'triangle', 'catmull-rom', 'sinc', 'blackman-harris', 'mitchell', 'mitchell', 'b-spline']

pyg = gelato_pyg()

def select_callback(name):
	global gui_filename

	gui_filename.val = os.path.abspath(name)
	update_registry()

def handle_event(evt, val):
	if ((evt == Blender.Draw.ESCKEY) or (evt == Blender.Draw.QKEY)):
		Blender.Draw.Exit()

def handle_button_event(evt):
	if (evt == ID_BUTTON_EXIT):
		Blender.Draw.Exit()
	elif (evt == ID_FILENAME):
		if (not gui_filename.val == ''):
			gui_filename.val = gui_filename.val
		Blender.Draw.Redraw(1)
	elif (evt == ID_SELECT):
		Blender.Window.FileSelector(select_callback, '.pyg', gui_filename.val)
		Blender.Draw.Redraw(1)
	elif (evt == ID_BUTTON_DEFAULT):
		default_value()
	elif (evt == ID_BUTTON_SAVE):
		pyg.export(Blender.Scene.GetCurrent())
	elif (evt == ID_BUTTON_RENDER):
		pyg.export(Blender.Scene.GetCurrent())
		if (os.path.isfile(gui_filename.val)):
			os.system('%s %s&' % (GELATO, gui_filename.val))

	if (gui_format.val == 0):
		gui_preview.val = 1

	update_registry()

def draw_gui():
	global gui_filename, gui_ambient_occlusion, gui_format, gui_data, gui_bucketorder
	global gui_antialiasing_x, gui_antialiasing_y, gui_filter, gui_filterwidth_x, gui_filterwidth_y
	global gui_preview, gui_sky, gui_dynamic_shadows, gui_lights_factor

	Blender.BGL.glClearColor(.5325, .6936, .0, 1.0)
	Blender.BGL.glClear(Blender.BGL.GL_COLOR_BUFFER_BIT)

	x = x0 = 10 # cursor x
	y = 10      # cursor y
	s = 30      # step y
	h = 20      # height button

	# line 1

	Blender.BGL.glColor3f(1.0, 1.0, 1.0)
	Blender.BGL.glRasterPos2i(x+2, y+5)
	Blender.Draw.Text('Blender Gelato V' + __version__)
	x += 140

	Blender.Draw.PushButton('Default', ID_BUTTON_DEFAULT, x, y,
		90, h, 'Set default value')
	x += 95

	Blender.Draw.PushButton('Exit', ID_BUTTON_EXIT, x, y,
		90, h, 'Exit Python script')

	x = x0
	y += s

	# line 2

	Blender.Draw.PushButton('Render', ID_BUTTON_RENDER, x, y,
		90, h, 'Save and render pyg file')
	x += 95

	gui_preview = Blender.Draw.Toggle("Preview", 0, x, y,
		90, h, gui_preview.val, "Enable window preview")
	x += 95

	gui_format = Blender.Draw.Menu(
		'Output format %t'
		'|null %x0'
		'|tiff %x1'
		'|jpeg %x2'
		'|targa %x3'
		'|ppm %x4'
		'|openEXR %x5',
		1, x, y,
		90, h, gui_format.val, 'Select output format')
	x += 95

	gui_data = Blender.Draw.Menu(
		'Output data %t'
		'|rgb %x0'
		'|rgba %x1'
		'|z %x2'
		'|avgz %x3'
		'|volz %x4',
		1, x, y,
		50, h, gui_data.val, 'Select output data')
	x += 55

	gui_bucketorder = Blender.Draw.Menu(
		'Bucketorder %t'
		'|horizontal %x0'
		'|vertical %x1'
		'|spiral %x2',
		1, x, y,
		80, h, gui_bucketorder.val, 'Render Bucketorder')

	x = x0
	y += s

	# line 3

	Blender.Draw.PushButton('Save', ID_BUTTON_SAVE, x, y,
		90, h, 'Save pyg file')
	x += 95

	Blender.Draw.Button('Filename:', ID_SELECT, x, y,
		90, h, 'Select file name')
	x += 90

	gui_filename = Blender.Draw.String('', ID_FILENAME, x, y,
		295, h, gui_filename.val, 160, 'File name')

	x = x0
	y += s

	# line 4

	gui_antialiasing_x = Blender.Draw.Number('AA X: ', 1, x, y,
		90, h, gui_antialiasing_x.val, 1, 16, 'Set spatial antialiasing x')
	x += 95

	gui_antialiasing_y = Blender.Draw.Number('AA Y: ', 1, x, y,
		90, h, gui_antialiasing_y.val, 1, 16, 'Set spatial antialiasing y')
	x += 95

	gui_filter = Blender.Draw.Menu(
		'Pixel filter %t'
		'|gaussian %x0'
		'|box %x1'
		'|triangle %x2'
		'|catmull-rom %x3'
		'|sinc %x4'
		'|blackman-harris %x5'
		'|mitchell %x6'
		'|b-spline %x7',
		1, x, y,
		115, h, gui_filter.val, 'Pixel filter')
	x += 120

	gui_filterwidth_x = Blender.Draw.Slider('Filter X: ', 1, x, y,
		170, h, gui_filterwidth_x.val, 0.0, 32.0, 0, 'Set filter width x')
	x += 175

	gui_filterwidth_y = Blender.Draw.Slider('Filter Y: ', 1, x, y,
		170, h, gui_filterwidth_y.val, 0.0, 32.0, 0, 'Set filter width y')

	x = x0
	y += s

	# line 5

	if (not gui_ambient_occlusion.val):
		gui_sky = Blender.Draw.Toggle("Sky", 0, x, y,
			40, h, gui_sky.val, "Enable background color")
		x += 45

		gui_dynamic_shadows = Blender.Draw.Toggle("Dynamic shadows", 0, x, y,
			120, h, gui_dynamic_shadows.val, "Enable dynamic shadows")
		x += 125

		gui_lights_factor = Blender.Draw.Slider('Lights factor: ', 1, x, y,
			240, h, gui_lights_factor.val, 0.0, 1000.0, 0, 'Set lights factor')

	x = x0
	y += s

	# line 6

	gui_ambient_occlusion = Blender.Draw.Toggle("Ambient Occlusion", 0, x, y,
		130, h, gui_ambient_occlusion.val, "Enable Ambient Occlusion")

	Blender.Draw.Redraw(1)

Blender.Draw.Register(draw_gui, handle_event, handle_button_event)

