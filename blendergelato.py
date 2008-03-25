#!BPY

"""
Name: 'Blender Gelato'
Blender: 242
Group: 'Render'
Tooltip: 'Render with NVIDIA Gelato (R)'
"""

__author__ = 'Mario Ambrogetti'
__version__ = '0.10'
__url__ = ['']
__bpydoc__ = """\
Blender to NVIDIA Gelato (R)
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

import Blender, sys, os
from math import degrees, radians, atan2

class enum_type(object):
	def __init__(self, *args):
		self.names = list(args)
		for idx, name in enumerate(self.names):
			setattr(self, name, idx)

	def __len__(self):
		return len(self.names)

	def __iter__(self):
		return enumerate(self.names)

	def __contains__(self, item):
		try:
			dummy = self[item]
			return True
		except:
			return False

	def __getitem__(self, key):
		if (type(key) == type(0)):
			return self.names[key]
		else:
			return getattr(self, key)

	def __str__(self):
		return str([(self.names[idx], idx) for idx in range(len(self.names))])

	def has_key(self, key):
		return self.__contains__(key)

class shader(object):
	class parameter(object):
		__slots__ = ['type', 'id', 'tooltip', 'widget', 'change']

		def __init__(self, type, value, id, tooltip):
			self.type    = type
			self.id      = id
			self.tooltip = tooltip
			self.widget  = Blender.Draw.Create(value)
			self.change  = False

	__slots__ = ['literal', 'types', 'file', 'base_id', 'verbose', 'size', 'parameters', 'type', 'name']

	def __init__(self, file, base_id, verbose = 1):
		self.literal = enum_type('float', 'string', 'color', 'point', 'vector', 'normal', 'matrix')
		self.types   = enum_type('surface', 'displacement', 'volume', 'light')

		self.file       = file
		self.base_id    = base_id
		self.verbose    = verbose
		self.size       = 200
		self.parameters = {}
		self.type       = -1
		self.name       = None

		self.parse_file()

	def __len__(self):
		return len(self.parameters)

	def __iter__(self):
		return enumerate(self.parameters.keys())

	def __getitem__(self, key):
		return self.parameters[key].widget.val

	def __setitem__(self, key, value):
		par = self.parameters[key]
		par.widget.val = str(value)
		par.change = True
		Blender.Draw.Redraw(1)

	def __str__(self):
		if (self.type == -1 or (not self.name)):
			return 'null'
		s = ''
		for name, par in self.parameters.iteritems():
			if (par.change):
				type = par.type
				if (type == self.literal.float):
					s = s + ('Parameter ("%s %s", %f)\n' % (self.literal[type], name, float(par.widget.val)))
				elif (type == self.literal.string):
					s = s + ('Parameter ("%s %s", "%s")\n' % (self.literal[type], name, par.widget.val))
				else:
					if (self.verbose > 1):
						print 'Error: unknow parameter', name

		s = s + ('Shader ("%s", "%s")\n' % (self.types[self.type], self.name))

		return s

	def set_verbose(self, verbose):
		self.verbose = verbose

	def update(self, id):
		for k, par in self.parameters.iteritems():
			if (par.id == id):
				par.change = True
				return

	def gui(self, x, y, h, s):
		Blender.BGL.glColor3f(0.0, 0.0, 0.0)
		Blender.BGL.glRasterPos2i(x+6, y+h/2-4)
		Blender.Draw.Text('Shader name: ')
		Blender.BGL.glColor3f(1.0, 1.0, 1.0)
		Blender.BGL.glRasterPos2i(x+Blender.Draw.GetStringWidth('Shader name: ')+6, y+h/2-4)
		Blender.Draw.Text(self.name)
		y += s

		i = j = 0
		for name, par in self.parameters.iteritems():
			type = par.type
			if (type == self.literal.float):
				par.widget = Blender.Draw.String(name + ': ', par.id, x + j, y,
					self.size, h, par.widget.val, 80, par.tooltip)
				i = i + 1
			elif (type == self.literal.string):
				par.widget = Blender.Draw.String(name + ': ', par.id, x + j, y,
					self.size, h, par.widget.val, 128, par.tooltip)
				i = i + 1
			else:
				if (self.verbose > 1):
					print 'Error: unknow parameter', name
				continue

			if (i % 3):
				j = j + self.size + 10
			else:
				j = 0
				y += s

	def parse_file(self):
		cmd='%s %s' % (GSOINFO, self.file)

		try:
			fd = os.popen(cmd, 'r')
		except:
			if (self.verbose > 0):
				print 'Error: command', cmd
			return

		line = fd.readline().strip()

		try:
			(type, name) = line.split(' ')
		except ValueError:
			return

		if (not self.types.has_key(type)):
			if (self.verbose > 1):
				print 'Error: unknow shader type', type, name
			return

		self.type = self.types[type]
		self.name = name

		i = 0
		for line in fd:
			elements = line.strip().split(' ')

			if (not self.literal.has_key(elements[0])):
				if (self.verbose > 1):
					print 'Error: unknow parameter type', elements
				continue

			lit = self.literal[elements[0]]

			par = None

			if (lit == self.literal.float):
				par = self.parameter(lit, elements[2], self.base_id + i, self.name + ' [float] ' + elements[1])
			elif (lit == self.literal.string):
				par = self.parameter(lit, elements[2][1:-1], self.base_id + i, self.name + ' [string] ' + elements[1])
			else:
				if (self.verbose > 1):
					print 'Error: unknow parameter', elements
				continue

			if (par):
				self.parameters[elements[1]] = par
				i = i + 1

		fd.close()

class gelato_pyg(object):

	class geometry(object):
		__slots__ = ['materials', 'nverts', 'verts']

		def __init__(self, material, nvert):
			self.materials = [material]
			self.nverts    = [nvert]
			self.verts     = []
		def append(self, material, nvert):
			self.materials.append(material)
			self.nverts.append(nvert)
		def append_vert(self, vert):
			self.verts.append(vert)
	"""
	Gelato class export.
	"""
	def __init__(self):
		self.PRECISION     = 5
		self.SCALEBIAS     = 0.1
		self.FACTORAMBIENT = 200

	def head(self):
		"""
		Write pyg header.
		"""
		curcam  = self.scene.getCurrentCamera()

		try:
			self.camera_name = curcam.name
		except:
			raise NameError, 'no camera present'

		try:
			scale = self.context.getRenderWinSize() / 100.0
		except:
			scale = 1.0

		self.file.write('## Exported by Blender Gelato ' + __version__ + '\n\n')

		self.file.write('Parameter ("string filter", "%s")\n' %
			self.filter)

		self.file.write('Parameter ("float[2] filterwidth", (%f, %f))\n' %
			(self.filterwidth_x , self.filterwidth_y))

		self.file.write('Parameter ("float gamma", %f)\n' %
			self.gamma)

		self.file.write('Parameter ("float gain", %f)\n' %
			self.gain)

		if (self.shadows):
				self.file.write('Output ("%s", "null", "%s", "%s")\n' %
					(self.title, self.data, self.camera_name))
		else:
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

		self.file.write('Attribute ("int ray:maxdepth", %d)\n' %
			self.maxdepth)

		self.camera(curcam)

		if (not self.ambient_occlusion and (self.shadows or self.dynamic_shadows)):
			self.cameras_shadows()

		self.file.write('\nWorld ()\n')

		if (self.ambient_occlusion):
			self.enable_ambient_occlusion()
		else:
			if (self.sky):
				self.background_color()
			if (self.key_fill_rim):
				self.enable_key_fill_rim()
			if (self.raytrace_shadows):
				self.enable_raytrace()

	def tail(self):
		"""
		Write the posterior part of pyg file.
		"""
		self.file.write('\nRender ("%s")\n\n'
			% self.camera_name)

	def join_list(self, l):
		return ', '.join([str(i) for i in l])

	def write_matrix(self, matrix):
		"""
		Write 16 elements of matrix.
		"""
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
		try:
			euler = matrix.toEuler()
		except:
			euler = Blender.Mathutils.Vector(0.0, 0.0, 0.0)

		try:
			scale = matrix.scalePart()
		except:
			scale = Blender.Mathutils.Vector(1.0, 1.0, 1.0)

		try:
			trans = matrix.translationPart()
		except:
			trans = Blender.Mathutils.Vector(0.0, 0.0, 0.0)

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

	def instance_name(self, name, idx):
		if (idx < 0):
			return name
		else:
			return '__' + name + '-' + str(idx) + '__'

	def camera_shadows_name(self, name, idx):
		if (idx < 0):
			return '__' + name + '-shadows' + '__'
		else:
			return '__' + name + '-shadows-' + str(idx) + '__'

	def file_shadows_name(self, name, idx):
		if (idx < 0):
			return os.path.join(self.directory, name + SHADOWMAP_EXT)
		else:
			return os.path.join(self.directory, name + '-' + str(idx) + SHADOWMAP_EXT)

	def enable_raytrace(self):
		self.file.write('\nAttribute ("string geometryset", "+shadows")\n')

	def enable_key_fill_rim(self):
		self.file.write('\nInput ("cameralights.pyg")\n')

	def enable_ambient_occlusion(self):
		self.file.write('\nAttribute ("string geometryset", "+localocclusion")\n')
		self.file.write('Attribute ("float occlusion:maxpixeldist", 20)\n')
		self.file.write('Attribute ("float occlusion:maxerror", 0.2)\n')

		if (shader_ambocclude):
			self.file.write(str(shader_ambocclude))
		else:
			self.file.write('Shader ("surface", "ambocclude", '
					'"string occlusionname", "localocclusion", '
					'"float samples", 512, '
					'"float bias", 0.01)\n')

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

	def shadow_name(self, name = None, idx = -1):
		shadowname = None
		if (name and (self.shadow_maps or self.dynamic_shadows)):
			shadowname = self.file_shadows_name(name, idx)
		elif (self.raytrace_shadows):
			shadowname = 'shadows'
		if (shadowname):
			self.file.write('Parameter ("string shadowname", "%s")\n' %
				shadowname)

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

		self.shadow_name(name, idx)
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

		self.shadow_name(name, idx)
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

		self.shadow_name(name, idx)
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

	def camera_light(self, obj, lamp, name, matrix, idx):
		self.file.write('\nPushTransform ()\n')

		self.convert_matrix(matrix)

		self.file.write('Camera ("%s", '
				'"int[2] resolution", (%d, %d), '
				'"int[2] spatialquality", (%d, %d), '
				'"string projection", "perspective", '
				'"float fov", %f, '
				'"float near", %f, '
				'"float far", %f)\n' % (
			self.camera_shadows_name(name, idx),
			lamp.bufferSize, lamp.bufferSize,
			lamp.samples, lamp.samples,
			lamp.spotSize,
			lamp.clipStart,
			lamp.clipEnd))

		self.file.write('PopTransform ()\n')

		if (self.dynamic_shadows):
			self.file.write('Parameter ("int dynamic", 1)\n')

		self.file.write('Output ("%s", '
				'"shadow", "z", "%s", '
				'"float[2] filterwidth", (1.0, 1.0))\n' % (
			self.file_shadows_name(name, idx),
			self.camera_shadows_name(name, idx)))

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

	def mesh_geometry(self, name, transform, single_sided, interpolation, nverts,\
			verts, points, normals = None, vertexcolor = None, holes = None):
		self.set_transform(transform)

		if (single_sided):
			self.file.write('Attribute ("int twosided", 0)\n')

		self.file.write('Mesh ("%s", (%s), (%s), "vertex point P", (%s)' %
			(interpolation, self.join_list(nverts), self.join_list(verts), points))

		if (normals):
			self.file.write(', "vertex normal N", (%s)' % normals)

		if (vertexcolor):
			self.file.write(', "vertex color C", (%s)' % vertexcolor)

		if (holes):
			self.file.write(', "int[%d] holes", (%s)' %
				(len(holes), self.join_list(holes)))

		self.file.write(')\n')

	def mesh(self, obj, matrix = None, idx = -1):
		type = obj.getType()
		if ((type != 'Mesh') and (type != 'Surf')):
			return

		name = obj.name

		try:
			mesh = Blender.NMesh.GetRawFromObject(name)
		except:
			return

		nfaces = len(mesh.faces)
		if (nfaces == 0):
			return

		# transform

		if (matrix):
			transform = matrix
		else:
			transform = obj.matrix

		# single sided face

		single_sided = False
		if ((not mesh.mode & Blender.NMesh.Modes.TWOSIDED) and (not self.all_double_sided)):
			single_sided = True

		# vertex colors

		vtcolor = mesh.hasVertexColours()

		# get property catmull_clark

		catmull_clark = False
		try:
			prop = obj.getProperty('catmull_clark')

			if (prop.getType() == 'BOOL'):
				catmull_clark = prop.getData()
		except:
			pass

		# interpolation type

		if (catmull_clark):
			interpolation = 'catmull-clark'
		else:
			interpolation = 'linear'

		# if NURBS smooth surface
		if (type == 'Surf'):
			smooth = True
		else:
			smooth = False

		# geometry

		if (vtcolor):
			nlist_col = range(len(mesh.verts))

		nverts = []
		verts = []
		dict_geometry = {}

		for i, face in enumerate(mesh.faces):
			if (face.smooth):
				smooth = True
			l = len(face.v)
			nverts.append(l)
			mat_idx = face.materialIndex
			if (dict_geometry.has_key(mat_idx)):
				dict_geometry[mat_idx].append(i, l)
			else:
				dict_geometry[mat_idx] = self.geometry(i, l)
			for vert in face.v:
				verts.append(vert.index)
				dict_geometry[mat_idx].append_vert(vert.index)
			if (vtcolor):
				for j in range(len(face.v)):
					c = face.col[j]
					nlist_col[face.v[j].index] = (c.r, c.g, c.b)

		# points

		nlist = []
		nlist_nor = []
		for vert in mesh.verts:
			nlist_nor.append(vert.no)
			nlist.append('(%f, %f, %f)' % (
				round(vert.co.x, self.PRECISION),
				round(vert.co.y, self.PRECISION),
				round(vert.co.z, self.PRECISION)))
		points = ', '.join(nlist)

		# normals

		normals = None
		if (smooth and (not catmull_clark)):
			for face in mesh.faces:
				if (face.smooth):
					continue
				for vert in face.v:
					nlist_nor[vert.index] = face.no
			nlist = []
			for nor in nlist_nor:
				nlist.append('(%f, %f, %f)' % (
					round(nor[0], self.PRECISION),
					round(nor[1], self.PRECISION),
					round(nor[2], self.PRECISION)))
			normals = ', '.join(nlist)

		# vertex color

		vertexcolor = None
		if (vtcolor):
			nlist = []
			for c in nlist_col:
				nlist.append('(%f, %f, %f)' % (
						c[0] / 255.0,
						c[1] / 255.0,
						c[2] / 255.0))
			vertexcolor = ', '.join(nlist)

		self.file.write('\nPushAttributes ()\n')
		self.file.write('Attribute ("string name", "%s")\n' % self.instance_name(name, idx))

		if ((not self.ambient_occlusion) and mesh.materials):

			# materials

			multiple_mat = len(mesh.materials) > 1
			if (multiple_mat and catmull_clark):
				set_mat = set(range(nfaces))

			for i, geo in dict_geometry.iteritems():

				try:
					mat = mesh.materials[i]
				except:
					continue
				
				self.file.write('PushAttributes ()\n')

				# vertex color

				flags = mat.getMode()
				if (not flags & Blender.Material.Modes['VCOL_PAINT']):
					vertexcolor = None

				# multiple materials on a single mesh

				holes = None

				if (multiple_mat and catmull_clark):
					holes = list(set_mat - set(geo.materials))

				# color

				self.file.write('Attribute ("color C", (%f, %f, %f))\n' %
					(mat.R, mat.G, mat.B))

				# alpha

				alpha = mat.alpha
				if (alpha < 1.0):
					self.file.write('Attribute ("color opacity", (%f, %f, %f))\n' %
						(alpha, alpha, alpha))

				# shader surface (TODO)

				self.file.write('Shader ("surface", "plastic")\n')

				# geometry

				if (catmull_clark):
					self.mesh_geometry(name, transform, single_sided, interpolation, nverts, verts, points, normals, vertexcolor, holes)
				else:
					self.mesh_geometry(name, transform, single_sided, interpolation, geo.nverts, geo.verts, points, normals, vertexcolor)

				self.file.write('PopAttributes ()\n')
		else:
			self.mesh_geometry(name, transform, single_sided, interpolation, nverts, verts, points, normals)

		self.file.write('PopAttributes ()\n')

	def visible(self, obj):
		if ((obj.users > 1) and (set(obj.layers) & self.viewlayer == set())):
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
				i = i + 1
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
		Blender.Window.DrawProgressBar(0.0, 'Lights ...')
		n = float(len(self.objects))
		for i, obj in enumerate(self.objects):
			self.build(obj, 'light');
			Blender.Window.DrawProgressBar(i / n, 'Lights ...')

	def geometries(self):
		Blender.Window.DrawProgressBar(0.0, 'Geometries ...')
		n = float(len(self.objects))
		for i, obj in enumerate(self.objects):
			if (self.verbose > 1):
				print 'Info: Object', obj.name, 'type', obj.getType()
			self.build(obj, 'mesh');
			Blender.Window.DrawProgressBar(i / n, 'Geometries ...')

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
		self.filename = permanents['filename'].val

		# beauty pass
		self.beauty  = permanents['beauty'].val

		# shadows pass
		self.shadows = permanents['shadows'].val

		# ambient occlusion pass
		self.ambient_occlusion = permanents['ambient_occlusion'].val

		# output file name image
		v = permanents['format'].val
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

		# output directory
		dir_file = os.path.split(self.filename)
		self.directory = dir_file[0]

		# output data
		try:
			self.data = convert_data[permanents['data'].val]
		except IndexError:
			self.data = convert_data[0]

		# bucketorder
		try:
			self.bucketorder = convert_bucketorder[permanents['bucketorder'].val]
		except IndexError:
			self.bucketorder = convert_bucketorder[0]

		# pixel filter
		try:
			self.filter = convert_filter[permanents['filter'].val]
		except IndexError:
			self.filter = convert_filter[0]

		# spatialquality
		self.spatialquality_x = int(permanents['antialiasing_x'].val)
		self.spatialquality_y = int(permanents['antialiasing_y'].val)

		# filterwidth
		self.filterwidth_x = float(permanents['filterwidth_x'].val)
		self.filterwidth_y = float(permanents['filterwidth_y'].val)

		# preview window
		self.preview = permanents['preview'].val

		# background color
		self.sky = permanents['sky'].val

		# shadow maps
		self.shadow_maps = permanents['shadow_maps'].val

		# dynamic shadows
		self.dynamic_shadows = permanents['dynamic_shadows'].val

		# raytrace shadows
		self.raytrace_shadows = permanents['raytrace_shadows'].val

		# light factor
		self.lights_factor = permanents['lights_factor'].val

		# gamma
		self.gamma = permanents['gamma'].val

		# gain
		self.gain = permanents['gain'].val

		# maxdepth
		self.maxdepth = permanents['maxdepth'].val

		# key-fill-rim lights
		self.key_fill_rim = permanents['key_fill_rim'].val

		# double side
		self.all_double_sided = permanents['all_double_sided'].val

		# no all lights
		self.no_all_lights = permanents['no_all_lights'].val

		# shader ambocclude
		if (shader_ambocclude):
			shader_ambocclude.set_verbose(self.verbose)

	def export(self, scene):
		self.scene = scene

		self.setup()

		if (self.verbose > 0):
			timestart = Blender.sys.time()
			print 'Info: starting Gelato pyg export to', self.filename

		try:
			self.file = open(self.filename, 'w')
		except IOError:
			Blender.Draw.PupMenu('Error:%t|cannot write file' + self.filename)
			return

		self.viewlayer = set(Blender.Window.ViewLayer())
		self.objects   = scene.getChildren()
		self.world     = Blender.World.GetCurrent()
		self.context   = self.scene.getRenderingContext()
		self.sizex     = float(self.context.imageSizeX())
		self.sizey     = float(self.context.imageSizeY())

		self.head()

		if ((not self.ambient_occlusion) and
                    (not self.shadows) and
                    (not self.no_all_lights)):
			self.lights()

		self.geometries()

		self.tail()

		Blender.Window.DrawProgressBar(1.0, '')

		self.file.close()

		if (self.verbose > 0):
			print 'Info: finished Gelato pyg export (%.2fs)' % (Blender.sys.time() - timestart)

# GUI

ID_BUTTON_SAVE          = 1000
ID_BUTTON_RENDER        = 1001
ID_SELECT               = 1002
ID_BUTTON_DEFAULT       = 1003
ID_BUTTON_EXIT          = 1004
ID_BUTTON_SHADOWMAPS    = 1005
ID_BUTTON_DYNAMIC       = 1006
ID_BUTTON_RAYTRACE      = 1007
ID_BUTTON_BEAUTY        = 1008
ID_BUTTON_SHADOWS       = 1009
ID_BUTTON_AO            = 1010
ID_BUTTON_CATMULL_CLARK = 1011

convert_data        = ['rgb', 'rgba', 'z', 'avgz', 'volz']
convert_bucketorder = ['horizontal', 'vertical', 'spiral']
convert_filter      = ['gaussian', 'box', 'triangle', 'catmull-rom', 'sinc', 'blackman-harris', 'mitchell', 'b-spline', 'min', 'max', 'average']

def select_callback(name):
	global permanents
	permanents['filename'].val = os.path.abspath(name)
	registry_save()

def handle_event(evt, val):
	if ((evt == Blender.Draw.ESCKEY) or (evt == Blender.Draw.QKEY)):
		ret = Blender.Draw.PupMenu("OK?%t|Exit Blender Gelato%x1")
		if ret == 1:
			registry_save()
			Blender.Draw.Exit()

def handle_button_event(evt):
	if (evt == ID_BUTTON_EXIT):
		Blender.Draw.Exit()
	elif (evt == ID_BUTTON_BEAUTY):
		permanents['shadows'].val = 0
		permanents['ambient_occlusion'].val = 0
	elif (evt == ID_BUTTON_SHADOWS):
		permanents['beauty'].val = 0
		permanents['ambient_occlusion'].val = 0
	elif (evt == ID_BUTTON_AO):
		permanents['beauty'].val = 0
		permanents['shadows'].val = 0
	elif (evt == ID_SELECT):
		Blender.Window.FileSelector(select_callback, '.pyg', permanents['filename'].val)
	elif (evt == ID_BUTTON_DEFAULT):
		registry_default()
	elif (evt == ID_BUTTON_SAVE):
		pyg.export(Blender.Scene.GetCurrent())
	elif (evt == ID_BUTTON_SHADOWMAPS):
		permanents['dynamic_shadows'].val = 0
		permanents['raytrace_shadows'].val = 0
	elif (evt == ID_BUTTON_DYNAMIC):
		permanents['shadow_maps'].val = 0
		permanents['raytrace_shadows'].val = 0
	elif (evt == ID_BUTTON_RAYTRACE):
		permanents['shadow_maps'].val = 0
		permanents['dynamic_shadows'].val = 0
	elif (evt == ID_BUTTON_CATMULL_CLARK):
		set_property_catmull_clark()
	elif (evt == ID_BUTTON_RENDER):
		pyg.export(Blender.Scene.GetCurrent())
		if (os.path.isfile(permanents['filename'].val)):
			os.system('%s %s&' % (GELATO, permanents['filename'].val))

	if (permanents['beauty'].val == 0 and permanents['shadows'].val == 0 and permanents['ambient_occlusion'].val == 0):
		permanents['beauty'].val = 1

	if (permanents['format'].val == 0):
		permanents['preview'].val = 1

	if (shader_ambocclude):
		shader_ambocclude.update(evt)

	registry_save()
	Blender.Draw.Redraw(1)

def draw_gui():
	global permanents

	Blender.BGL.glClearColor(.5325, .6936, .0, 1.0)
	Blender.BGL.glClear(Blender.BGL.GL_COLOR_BUFFER_BIT)

	x = x0 = 10 # cursor x
	y = 10      # cursor y
	s = 30      # step y
	h = 20      # height button

	# line

	Blender.BGL.glColor3f(1.0, 1.0, 1.0)
	Blender.BGL.glRasterPos2i(x+2, y+5)
	Blender.Draw.Text('Blender Gelato V' + __version__)
	x += 190

	Blender.Draw.PushButton('Default', ID_BUTTON_DEFAULT, x, y,
		90, h, 'Set default value')
	x += 95

	Blender.Draw.PushButton('Exit', ID_BUTTON_EXIT, x, y,
		90, h, 'Exit Python script')

	x = x0
	y += s

	# line

	Blender.Draw.PushButton('Render', ID_BUTTON_RENDER, x, y,
		90, h, 'Save and render pyg file')
	x += 95

	permanents['preview'] = Blender.Draw.Toggle('Preview', 0, x, y,
		90, h, permanents['preview'].val, 'Enable window preview')
	x += 95

	permanents['format'] = Blender.Draw.Menu(
		'Output format %t'
		'|null %x0'
		'|tiff %x1'
		'|jpeg %x2'
		'|targa %x3'
		'|ppm %x4'
		'|openEXR %x5',
		1, x, y,
		90, h, permanents['format'].val, 'Select output format')
	x += 95

	permanents['data'] = Blender.Draw.Menu(
		'Output data %t'
		'|rgb %x0'
		'|rgba %x1'
		'|z %x2'
		'|avgz %x3'
		'|volz %x4',
		1, x, y,
		60, h, permanents['data'].val, 'Select output data')
	x += 65

	permanents['bucketorder'] = Blender.Draw.Menu(
		'Bucketorder %t'
		'|horizontal %x0'
		'|vertical %x1'
		'|spiral %x2',
		1, x, y,
		80, h, permanents['bucketorder'].val, 'Render Bucketorder')

	x = x0
	y += s

	# line

	Blender.Draw.PushButton('Save', ID_BUTTON_SAVE, x, y,
		90, h, 'Save pyg file')
	x += 95

	Blender.Draw.Button('Filename:', ID_SELECT, x, y,
		90, h, 'Select file name')
	x += 90

	permanents['filename'] = Blender.Draw.String('', 1, x, y,
		300, h, permanents['filename'].val, 160, 'File name')

	x = x0
	y += s

	# line

	permanents['antialiasing_x'] = Blender.Draw.Number('AA X: ', 1, x, y,
		90, h, permanents['antialiasing_x'].val, 1, 16, 'Spatial antialiasing x')
	x += 95

	permanents['antialiasing_y'] = Blender.Draw.Number('AA Y: ', 1, x, y,
		90, h, permanents['antialiasing_y'].val, 1, 16, 'Spatial antialiasing y')
	x += 95

	permanents['gamma'] = Blender.Draw.Number('Gamma: ', 1, x, y,
		100, h, permanents['gamma'].val, 0.0, 10.0, 'Image gamma')
	x += 105

	permanents['gain'] = Blender.Draw.Number('Gain: ', 1, x, y,
		100, h, permanents['gain'].val, 0.0, 10.0, 'Image gain')

	x = x0
	y += s

	# line

	if (permanents['data'].val >= 2):
		zfilter = '|min %x8' '|max %x9' '|average %x10'
	else:
		zfilter = ''

	permanents['filter'] = Blender.Draw.Menu(
		'Pixel filter %t'
		'|gaussian %x0'
		'|box %x1'
		'|triangle %x2'
		'|catmull-rom %x3'
		'|sinc %x4'
		'|blackman-harris %x5'
		'|mitchell %x6'
		'|b-spline %x7'
		+ zfilter,
		1, x, y,
		130, h, permanents['filter'].val, 'Pixel filter')
	x += 135

	permanents['filterwidth_x'] = Blender.Draw.Number('Filter X: ', 1, x, y,
		120, h, permanents['filterwidth_x'].val, 0.0, 32.0, 'Filter width x')
	x += 125

	permanents['filterwidth_y'] = Blender.Draw.Number('Filter Y: ', 1, x, y,
		120, h, permanents['filterwidth_y'].val, 0.0, 32.0, 'Filter width y')

	x = x0
	y += s

	# line

	permanents['lights_factor'] = Blender.Draw.Slider('Lights factor: ', 1, x, y,
		255, h, permanents['lights_factor'].val, 0.0, 1000.0, 0, 'Lights factor')
	x += 260

	permanents['maxdepth'] = Blender.Draw.Number('maxdepth: ', 1, x, y,
		120, h, permanents['maxdepth'].val, 0, 16, 'Raytrace maxdepth')

	x = x0
	y += s

	# line

	Blender.BGL.glColor3f(0.0, 0.0, 0.0)
	Blender.BGL.glRasterPos2i(x+6, y+h/2-4)
	Blender.Draw.Text('Property:')
	x += 75

	Blender.Draw.PushButton('catmull_clark', ID_BUTTON_CATMULL_CLARK, x, y,
		130, h, 'Enable catmull-clark property')

	x = x0
	y += s

	# line

	Blender.BGL.glColor3f(0.0, 0.0, 0.0)
	Blender.BGL.glRasterPos2i(x+6, y+h/2-4)
	Blender.Draw.Text('Pass:')
	x += 75

	permanents['beauty'] = Blender.Draw.Toggle('Beauty', ID_BUTTON_BEAUTY, x, y,
		130, h, permanents['beauty'].val, 'Enable beauty pass')
	x += 130

	permanents['shadows'] = Blender.Draw.Toggle('Shadows', ID_BUTTON_SHADOWS, x, y,
		130, h, permanents['shadows'].val, 'Enable shadows pass')
	x += 130

	permanents['ambient_occlusion'] = Blender.Draw.Toggle('Ambient Occlusion', ID_BUTTON_AO, x, y,
		130, h, permanents['ambient_occlusion'].val, 'Enable ambient occlusion pass')

	x = x0
	y += s

	# line

	if (not permanents['ambient_occlusion'].val):

		Blender.BGL.glColor3f(0.0, 0.0, 0.0)
		Blender.BGL.glRasterPos2i(x+6, y+h/2-4)
		Blender.Draw.Text('Shadows:')
		x += 75

		permanents['shadow_maps'] = Blender.Draw.Toggle('Shadowmaps', ID_BUTTON_SHADOWMAPS, x, y,
			130, h, permanents['shadow_maps'].val, 'Enable Shadow maps')
		x += 130

		permanents['dynamic_shadows'] = Blender.Draw.Toggle('Dynamic', ID_BUTTON_DYNAMIC, x, y,
			130, h, permanents['dynamic_shadows'].val, 'Enable Dynamic shadows')
		x += 130

		permanents['raytrace_shadows'] = Blender.Draw.Toggle('Raytrace', ID_BUTTON_RAYTRACE, x, y,
			130, h, permanents['raytrace_shadows'].val, 'Enable Raytrace shadows')

		x = x0
		y += s

	# line

	if (not permanents['ambient_occlusion'].val):

		Blender.BGL.glColor3f(0.0, 0.0, 0.0)
		Blender.BGL.glRasterPos2i(x+6, y+h/2-4)
		Blender.Draw.Text('Enable:')
		x += 75

		permanents['sky'] = Blender.Draw.Toggle('Sky', 0, x, y,
			60, h, permanents['sky'].val, 'Enable background color')
		x += 65

		permanents['key_fill_rim'] = Blender.Draw.Toggle('Key Fill Rim lights', 0, x, y,
			110, h, permanents['key_fill_rim'].val, 'Enable Key Fill Rim lights')
		x += 115

		permanents['all_double_sided'] = Blender.Draw.Toggle('All double sided', 0, x, y,
			120, h, permanents['all_double_sided'].val, 'Enable all double sided faces')

		x = x0
		y += s

	# line

	if (not permanents['ambient_occlusion'].val):

		Blender.BGL.glColor3f(0.0, 0.0, 0.0)
		Blender.BGL.glRasterPos2i(x+6, y+h/2-4)
		Blender.Draw.Text('Disable:')
		x += 75

		permanents['no_all_lights'] = Blender.Draw.Toggle('All lights', 0, x, y,
			60, h, permanents['no_all_lights'].val, 'Disable all lights')
		x += 65

	if (permanents['ambient_occlusion'].val and shader_ambocclude):
		shader_ambocclude.gui(x, y, h, s)

def set_property_catmull_clark():
	for obj in Blender.Object.GetSelected():
		type = obj.getType()
		if ((type != 'Mesh') and (type != 'Surf')):
			continue
		try:
			try:
				prop = obj.getProperty('catmull_clark')
				obj.removeProperty(prop)
			except:
				pass

			obj.addProperty('catmull_clark', 1, 'BOOL')
			Blender.Redraw()
			Blender.RedrawAll()
		except:
			pass

# registry

def registry_default():
	global FILENAME, permanents
	permanents = {
		'beauty':            Blender.Draw.Create(1),
		'shadows':           Blender.Draw.Create(0),
		'ambient_occlusion': Blender.Draw.Create(0),
		'filename':          Blender.Draw.Create(FILENAME),
		'antialiasing_x':    Blender.Draw.Create(4),
		'antialiasing_y':    Blender.Draw.Create(4),
		'filterwidth_x':     Blender.Draw.Create(2.0),
		'filterwidth_y':     Blender.Draw.Create(2.0),
		'gamma':             Blender.Draw.Create(1.0),
		'gain':              Blender.Draw.Create(1.0),
		'format':            Blender.Draw.Create(0),		# null
		'data':              Blender.Draw.Create(0),		# rgb
		'bucketorder':       Blender.Draw.Create(2),		# spiral
		'filter':            Blender.Draw.Create(0),		# gaussian
		'preview':           Blender.Draw.Create(1),
		'sky':               Blender.Draw.Create(1),
		'shadow_maps':       Blender.Draw.Create(0),
		'dynamic_shadows':   Blender.Draw.Create(0),
		'raytrace_shadows':  Blender.Draw.Create(0),
		'lights_factor':     Blender.Draw.Create(50.0),
		'maxdepth':          Blender.Draw.Create(2),
		'key_fill_rim':      Blender.Draw.Create(0),
		'all_double_sided':  Blender.Draw.Create(0),
		'no_all_lights':     Blender.Draw.Create(0),
	}

def registry_save():
	global permanents
	rdict = dict()
	for name, value in permanents.iteritems():
		rdict[name] = value.val
	Blender.Registry.SetKey(KEYREGISTER, rdict, True)

def registry_load():
	global permanents
	rdict = Blender.Registry.GetKey(KEYREGISTER, True)
	if (rdict):
		for name, value in rdict.iteritems():
			permanents[name] = Blender.Draw.Create(value)

# main

if __name__ == '__main__':
	global KEYREGISTER, SHADOWMAP_EXT, GSO_AMBOCCLUDE, GELATO, GSOINFO, FILENAME
	global shader_ambocclude, permanents, pyg

	PYTHON_MAJOR = 2
	PYTHON_MINOR = 4

	if sys.version_info < (PYTHON_MAJOR, PYTHON_MINOR):
		print 'Error: Python version %d.%d or greater is required' % (PYTHON_MAJOR, PYTHON_MINOR)
		print 'Python version is', sys.version
	else:
		KEYREGISTER = 'BlenderGelato'

		SHADOWMAP_EXT  = '.sm'
		GSO_AMBOCCLUDE = 'ambocclude.gso'

		# programs

		if (os.name == 'nt'):
			exe = '.exe'
		else:
			exe = ''

		GELATO  = 'gelato'  + exe
		GSOINFO = 'gsoinfo' + exe

		GELATOHOME = os.getenv('GELATOHOME')

		if (GELATOHOME):
			GELATO         = os.path.join(GELATOHOME, 'bin',     GELATO)
			GSOINFO        = os.path.join(GELATOHOME, 'bin',     GSOINFO)
			GSO_AMBOCCLUDE = os.path.join(GELATOHOME, 'shaders', GSO_AMBOCCLUDE)

		# file name

		try:
			blend_file_name = Blender.Get('filename')
			file_ext = os.path.splitext(blend_file_name)
			name = file_ext[0]
		except:
			name = 'gelato'

		FILENAME = name + '.pyg'

		# shader

		try:
			shader_ambocclude = shader(GSO_AMBOCCLUDE, 5000)

			shader_ambocclude['samples']       = 512
			shader_ambocclude['occlusionname'] = 'localocclusion'
			shader_ambocclude['bias']          = 0.01
		except:
			shader_ambocclude = None

		# permanents data

		registry_default()
		registry_load()
		registry_save()

		# gelato convert

		pyg = gelato_pyg()

		# GUI

		Blender.Draw.Register(draw_gui, handle_event, handle_button_event)

