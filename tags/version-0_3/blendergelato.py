#!BPY

"""
Name: 'Blender Gelato'
Blender: 241
Group: 'Render'
Tooltip: 'Render with NVIDIA Gelato ®'
"""

__author__ = 'Mario Ambrogetti'
__version__ = '0.3'
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

		self.file.write('Output ("file.tiff", "iv", "rgba", "main")\n\n')

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
		self.file.write('\nShader ("surface", "ambocclude", '
		                '"string occlusionname", "localocclusion", '
				'"float samples", 512, '
				'"float bias", 0.01)\n')
		self.file.write('Attribute ("string geometryset", "+localocclusion")\n')
		self.file.write('Attribute ("float occlusion:maxpixeldist", 20)\n')
		self.file.write('Attribute ("float occlusion:maxerror", 0.2)\n')

	def ambientlight(self):
		world = Blender.World.GetCurrent()

		if (world and (world.getAmb() != [0.0, 0.0, 0.0])):
			self.file.write('\nLight ("%s", "ambientlight", '
					'"color lightcolor", (%f, %f, %f))\n' %
				(world.getName(),
				 world.amb[0], world.amb[1], world.amb[2]))

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
#		mesh = Blender.NMesh.GetRaw(name)
		mesh = Blender.NMesh.GetRawFromObject(name)

		if (len(mesh.faces) == 0):
			return

		self.file.write('\nPushAttributes ()\n')
		self.file.write('Attribute ("string name", "%s")\n' % name)

		if (not mesh.mode & Blender.NMesh.Modes.TWOSIDED):
			self.file.write('Attribute ("int twosided", 0)\n')

		subsurf = 0
		try:
			mods = obj.modifiers
			for mod in mods:
				if (mod.type == Blender.Modifier.Type.SUBSURF):
					subsurf = 1
		except:
			pass

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

		self.transform(obj)

		if (subsurf):
			interp = 'catmull-clark'
		else:
			interp = 'linear'
		self.file.write('Mesh ("%s", (' % interp)

		nlist = []
		for face in mesh.faces:
			nlist.append(str(len(face.v)))
		self.file.write(', '.join(nlist))

		self.file.write('), (',)

		smooth = 0
		nlist  = []
		for face in mesh.faces:
			if (face.smooth):
				smooth = 1
			for vert in face.v:
				nlist.append(str(vert.index))
		self.file.write(', '.join(nlist))

		self.file.write('), "vertex point P", (')

		nlist = []
		for vert in mesh.verts:
			nlist.append('%f, %f, %f' %
				(round(vert.co[0], self.PRECISION),
				 round(vert.co[1], self.PRECISION),
				 round(vert.co[2], self.PRECISION)))
		self.file.write(', '.join(nlist))

		self.file.write('))\n')

		if (smooth):

			self.file.write('Parameter ("vertex normal N", (')
	
			nlist = []
			for vert in mesh.verts:
				nlist.append('%f, %f, %f' %
					(round(vert.no[0], self.PRECISION),
				 	 round(vert.no[1], self.PRECISION),
				 	 round(vert.no[2], self.PRECISION)))
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

	def export(self, filename, scene, verbose = VERBOSE):
		self.verbose  = verbose
		self.filename = filename
		self.scene    = scene
		self.ao       = gui_ao.val

		self.objects  = scene.getChildren()

		if (self.verbose > 1):
			timestart= Blender.sys.time()
			print 'Info: starting Gelato pyg export to', self.filename

		try:
			self.file = open(filename, 'w')

		except IOError:
			if (self.verbose > 0):
				print 'Error: cannot write file', filename
			return

		self.head()
		self.lights()
		self.geometries()
		self.tail()

		self.file.close()

		if (self.verbose > 1):
			print 'Info: finished Gelato pyg export (%.2fs)' % (Blender.sys.time() - timestart)

# GUI

ID_BUTTON_SAVE   = 1000
ID_BUTTON_RENDER = 1001
ID_FILENAME      = 1002
ID_SELECT	 = 1003

gui_filename = Blender.Draw.Create(FILENAME)
gui_ao 	     = Blender.Draw.Create(0)

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

def draw_gui():
	global gui_filename, gui_ao

	Blender.BGL.glClearColor(.2,.2,.2,1)
	Blender.BGL.glClear(Blender.BGL.GL_COLOR_BUFFER_BIT)
	Blender.BGL.glColor3f(1,1,1)

	gui_ao = Blender.Draw.Toggle("Ambient Occlusion", 0, 10, 90, 150, 20, gui_ao.val, "Enable Ambient Occlusion")

	gui_filename = Blender.Draw.String('Filename: ', ID_FILENAME, 10, 60, 400, 20, gui_filename.val, 160, "File name")
	Blender.Draw.Button ("Select", ID_SELECT, 415, 60, 90, 20, "select the directory where the files are saved")

	Blender.Draw.PushButton('Render', ID_BUTTON_RENDER, 110, 30, 90, 20, "Save and render pyg file")
	Blender.Draw.PushButton('Save',   ID_BUTTON_SAVE,   10,  30, 90, 20, "Save pyg file")

	Blender.BGL.glRasterPos2i(10,10)
	Blender.Draw.Text('Blender Gelato V' + __version__)

	Blender.Draw.Redraw(1)

Blender.Draw.Register(draw_gui, handle_event, handle_button_event)

