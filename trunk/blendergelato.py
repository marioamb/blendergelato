#!BPY

"""
Name: 'Blender Gelato'
Blender: 241
Group: 'Render'
Tooltip: 'Render with NVIDIA Gelato ®'
"""

__author__ = 'Mario Ambrogetti'
__version__ = '0.4'
__url__ = ['']
__bpydoc__ = """\

"""

# ***** BEGIN GPL LICENSE BLOCK *****
#
# Script copyright (C) Bob Holcomb
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
# --------------------------------------------------------------------------

import os, Blender
from math import degrees, radians, atan2

VERBOSE = 2
GELATO  = os.path.join(os.getenv('GELATOHOME'), 'bin', 'gelato')

if (os.name == 'nt'):
	FILENAME = 'C:/gelato.pyg'
else:
	FILENAME = '/tmp/gelato.pyg'

class gelato_pyg:
	def __init__(self):
		self.PRECISION	 = 5
		self.LIGHTFACTOR = 50

	def head(self):
		curcam  = self.scene.getCurrentCamera()
		camera  = Blender.Camera.Get(curcam.getData().name)
		context = self.scene.getRenderingContext()
		matrix  = curcam.getInverseMatrix()
		sizex   = float(context.imageSizeX())
		sizey   = float(context.imageSizeY())

		try:
			scale = context.getRenderWinSize() / 100.0
		except:
			scale = 1.0

		self.file.write('Output ("%s", "%s", "%s", "main")\n\n' % 
			(self.output, self.format, self.data))

		self.file.write('Attribute ("int[2] resolution", (%d, %d))\n' %
			(int(sizex * scale), int(sizey * scale)))

		self.file.write('Attribute ("float pixelaspect", 1.0)\n')
		self.file.write('Attribute ("int[2] spatialquality", (4, 4))\n')
		self.file.write('Attribute ("string bucketorder", "spiral")\n')
		self.file.write('Attribute ("int twosided", 1)\n')

		self.file.write('Attribute ("float near", %f)\n' % camera.clipStart)
		self.file.write('Attribute ("float far", %f)\n' % camera.clipEnd)

		if (camera.getType()):
			# orthographic camera
			aspx = camera.scale / 2.0
			aspy = aspx * sizey / sizex * float(context.aspectRatioY()) / float(context.aspectRatioX())
			self.file.write('Attribute ("string projection", "orthographic")\n')
			self.file.write('Attribute ("float[4] screen", (%f, %f, %f, %f))\n' % (-aspx, aspx, -aspy, aspy))
		else:
			# perspective camera
			if (context.aspectRatioX() != context.aspectRatioY()):
				aspx = sizex / sizey
				aspy = float(context.aspectRatioY()) / float(context.aspectRatioX())
				self.file.write('Attribute ("float[4] screen", (%f, %f, %f, %f))\n' %
					(-aspx, aspx, -aspy, aspy))
			if (sizex > sizey):
				fac = sizey / sizex
			else:
				fac = 1.0
			self.file.write('Attribute ("string projection", "perspective")\n')
			self.file.write('Attribute ("float fov", %f)\n' % degrees(2*atan2(16.0 * fac, camera.lens)))

		self.file.write('SetTransform ((%f, %f, %f, %f), (%f, %f, %f, %f), (%f, %f, %f, %f), (%f, %f, %f, %f))\n' %
			(matrix[0][0], matrix[0][1], -matrix[0][2], matrix[0][3],
			 matrix[1][0], matrix[1][1], -matrix[1][2], matrix[1][3],
			 matrix[2][0], matrix[2][1], -matrix[2][2], matrix[2][3],
			 matrix[3][0], matrix[3][1], -matrix[3][2], matrix[3][3]))

		self.file.write('World ()\n')

		if (self.ao):
			self.ambient_occlusion()

	def tail(self):
		self.file.write('\nRender ("camera")\n')

	def translate(self, obj):
		t = obj.matrix.translationPart()
		self.file.write('Translate (%f, %f, %f)\n' % (t.x, t.y, t.z))

	def transform(self, obj):
		self.file.write('SetTransform ((%f, %f, %f, %f), (%f, %f, %f, %f), (%f, %f, %f, %f), (%f, %f, %f, %f))\n' %
			(obj.matrix[0][0], obj.matrix[0][1], obj.matrix[0][2], obj.matrix[0][3],
			 obj.matrix[1][0], obj.matrix[1][1], obj.matrix[1][2], obj.matrix[1][3],
			 obj.matrix[2][0], obj.matrix[2][1], obj.matrix[2][2], obj.matrix[2][3],
			 obj.matrix[3][0], obj.matrix[3][1], obj.matrix[3][2], obj.matrix[3][3]))

	def ambient_occlusion(self):
		self.file.write('\nAttribute ("string geometryset", "+localocclusion")\n')
		self.file.write('Attribute ("float occlusion:maxpixeldist", 20)\n')
		self.file.write('Attribute ("float occlusion:maxerror", 0.2)\n')
		self.file.write('Shader ("surface", "ambocclude", '
		                '"string occlusionname", "localocclusion", '
				'"float samples", 512, '
				'"float bias", 0.01)\n')

	def ambientlight(self):
		world = Blender.World.GetCurrent()

		if (world and (world.getAmb() != [0.0, 0.0, 0.0])):
			self.file.write('\nLight ("%s", "ambientlight", '
					'"color lightcolor", (%f, %f, %f))\n' %
				(world.getName(),
				 world.amb.r, world.amb.g, world.amb.b))

	def pointlight(self, obj, lamp, name):
		f = obj.matrix.translationPart()

		self.file.write('\nLight ("%s", "pointlight", '
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

		self.file.write('\nLight ("%s", "distantlight", '
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

		self.file.write('\nLight ("%s", "spotlight", '
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
			 radians(lamp.spotSize / 2),
			 radians(lamp.spotBlend * lamp.spotSize / 2)))

	def light(self, obj):
		name = obj.name
		lamp = Blender.Lamp.Get(obj.getData().name)

		type = lamp.getType()
		if (type == Blender.Lamp.Types.Lamp):
			self.pointlight(obj, lamp, name)
		elif (type == Blender.Lamp.Types.Sun):
			self.distantlight(obj, lamp, name)
		elif (type == Blender.Lamp.Types.Spot):
			self.spotlight(obj, lamp, name)

	def mesh(self, obj):
		name = obj.name
		mesh = Blender.NMesh.GetRawFromObject(name)

		if (len(mesh.faces) == 0):
			return

		self.file.write('\nPushAttributes ()\n')
		self.file.write('Attribute ("string name", "%s")\n' % name)

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
			self.file.write('Shader ("surface", "defaultsurface" )\n')

		self.transform(obj)

		self.file.write('Mesh ("linear", (')

		nlist = []
		for face in mesh.faces:
			nlist.append(str(len(face.v)))
		self.file.write(', '.join(nlist))

		self.file.write('), (',)

		smooth  = 0
		nlist   = []
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
			nlist.append('(%f, %f, %f)' %
				(round(vert.co.x, self.PRECISION),
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
				nlist.append('(%f, %f, %f)' %
					(round(nor[0], self.PRECISION),
				 	 round(nor[1], self.PRECISION),
				 	 round(nor[2], self.PRECISION)))
			self.file.write(', '.join(nlist))

		self.file.write('))\n')

		self.file.write('PopAttributes ()\n')

	def lights(self):
		self.ambientlight()
		for obj in self.objects:
			# check if visible
			if ((set(obj.layers) & self.viewlayer) == set([])):
				continue
			type = obj.getType()
			if (type == 'Lamp'):
				self.light(obj)

	def geometries(self):
		for obj in self.objects:
			# check if visible
			if ((set(obj.layers) & self.viewlayer) == set([])):
				continue
			type = obj.getType()
			if (type == 'Mesh'):
				self.mesh(obj)

	def export(self, filename, scene, verbose = VERBOSE):
		self.verbose  = verbose
		self.filename = filename
		self.scene    = scene
		self.ao       = gui_ao.val

		if (self.verbose > 1):
			timestart= Blender.sys.time()
			print 'Info: starting Gelato pyg export to', self.filename

		try:
			self.file = open(filename, 'w')
		except IOError:
			if (self.verbose > 0):
				Draw.PupMenu('Error: cannot write file' + filename)
			return

		self.viewlayer = set(Blender.Window.ViewLayer())
		self.objects   = scene.getChildren()

		# output image file name
		v = gui_format.val
		if (v == 1):
			self.format = 'tiff'
			self.suffix = '.tiff'
		elif (v == 2):
			self.format = 'OpenEXR'
			self.suffix = '.exr'
		else:
			self.format = 'iv'
			self.suffix = None

		file_ext = os.path.splitext(self.filename)
		if (self.suffix):
			self.output = file_ext[0] + self.suffix
		else:
			self.output = os.path.basename(file_ext[0])

		# output data
		v = gui_data.val
		if (v == 1):
			self.data = "rgba"
		elif (v == 2):
			self.data = "z"
		else:
			self.data = "rgb"

		self.head()
		self.lights()
		self.geometries()
		self.tail()

		self.file.close()

		if (self.verbose > 1):
			print 'Info: finished Gelato pyg export (%.2fs)' % (Blender.sys.time() - timestart)

# Persistent data

gui_filename = Blender.Draw.Create(FILENAME)
gui_ao 	     = Blender.Draw.Create(0)
gui_format   = Blender.Draw.Create(0)
gui_data     = Blender.Draw.Create(0)

def update_registry():
	d = {}
	d['filename'] = gui_filename.val
	d['ao']       = gui_ao.val
	d['format']   = gui_format.val
	d['data']     = gui_data.val
	Blender.Registry.SetKey('BlenderGelato', d, True)

rdict = Blender.Registry.GetKey('BlenderGelato', True)
if rdict:
	try:
		gui_filename.val = rdict['filename']
		gui_ao.val       = rdict['ao']
		gui_format.val   = rdict['format']
		gui_data.val     = rdict['data']
	except:
		update_registry()

# GUI

ID_BUTTON_SAVE   = 1000
ID_BUTTON_RENDER = 1001
ID_FILENAME      = 1002
ID_SELECT	 = 1003

pyg = gelato_pyg()

def select_callback(name):
	global gui_filename
	gui_filename = Blender.Draw.Create(os.path.abspath(name))

def handle_event(evt, val):
	if ((evt == Blender.Draw.ESCKEY) or (evt == Blender.Draw.QKEY)):
		Blender.Draw.Exit()

def handle_button_event(evt):
	if (evt == ID_FILENAME):
		if not (gui_filename.val == ""):
			gui_filename.val = gui_filename.val
		Blender.Draw.Redraw(1)
	elif (evt == ID_SELECT):
		Blender.Window.FileSelector(select_callback, '.pyg', gui_filename.val)
		Blender.Draw.Redraw(1)
	elif (evt == ID_BUTTON_SAVE):
		pyg.export(gui_filename.val, Blender.Scene.GetCurrent())
	elif (evt == ID_BUTTON_RENDER):
		pyg.export(gui_filename.val, Blender.Scene.GetCurrent())
		if (os.path.isfile(gui_filename.val)):
			os.system('%s %s&' % (GELATO, gui_filename.val))
	update_registry()

def draw_gui():
	global gui_filename, gui_ao, gui_format, gui_data

	Blender.BGL.glClearColor(.5325,.6936,.0,1.0)
	Blender.BGL.glClear(Blender.BGL.GL_COLOR_BUFFER_BIT)
	Blender.BGL.glColor3f(1,1,1)

	x = 10
	y = 10
	s = 30

	# line 1

	Blender.BGL.glRasterPos2i(x+2, y+5)
	Blender.Draw.Text('Blender Gelato V' + __version__)

	y += s

	# line 2

	Blender.Draw.PushButton('Render', ID_BUTTON_RENDER, x, y, 90, 20, 'Save and render pyg file')
	gui_format = Blender.Draw.Menu(
		'Output format %t'
		'|iv (view) %x0'
		'|tiff %x1'
		'|openEXR %x2',
		1, x+95, y, 80, 20, gui_format.val, 'Select output format')
	gui_data = Blender.Draw.Menu(
		'Output data %t'
		'|rgb %x0'
		'|rgba %x1'
		'|z %x2',
		1, x+185, y, 50, 20, gui_data.val, 'Select output data')

	y += s

	# line 3

	Blender.Draw.PushButton('Save', ID_BUTTON_SAVE, x, y, 90, 20, 'Save pyg file')
	Blender.Draw.Button('Filename', ID_SELECT, x+95, y, 90, 20, 'Select file name')
	gui_filename = Blender.Draw.String('', ID_FILENAME, x+185, y, 300, 20, gui_filename.val, 160, 'File name')

	y += s

	# line 4

	gui_ao = Blender.Draw.Toggle("Ambient Occlusion", 0, x, y, 130, 20, gui_ao.val, "Enable Ambient Occlusion")


	Blender.Draw.Redraw(1)

Blender.Draw.Register(draw_gui, handle_event, handle_button_event)

