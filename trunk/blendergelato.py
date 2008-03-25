#!BPY

"""
Name: 'Blender Gelato'
Blender: 242
Group: 'Render'
Tooltip: 'Render with NVIDIA Gelato(TM)'
"""

__author__ = 'Mario Ambrogetti'
__version__ = '0.11'
__url__ = ['']
__bpydoc__ = """\
Blender to NVIDIA Gelato(TM)
"""

# NVIDIA Gelato(TM) Exporter
#
# Original By: Mario Ambrogetti
# Date:        Tue, 10 Oct 2006 15:30:46 +0200
#
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

import Blender
import sys, os, datetime
from math import degrees, radians, atan2

class GelatoError(Exception):
	def __init__(self, message):
		self.message = message
	def __str__(self):
		return self.message

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
		if (type(key) is type(int())):
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

	__slots__ = ['literals', 'types', 'file', 'base_id', 'verbose', 'size', 'parameters', 'type', 'name']
	def __init__(self, file, base_id, verbose = 1):
		self.literals = enum_type('float', 'string', 'color', 'point', 'vector', 'normal', 'matrix')
		self.types    = enum_type('surface', 'displacement', 'volume', 'light')

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
				if (type is self.literals.float):
					s += ('Parameter ("%s %s", %s)\n' % (self.literals[type], name, float(par.widget.val)))
				elif (type is self.literals.string):
					s += ('Parameter ("%s %s", "%s")\n' % (self.literals[type], name, par.widget.val))
				else:
					if (self.verbose > 1):
						print 'Error: unknow parameter', name

		s += ('Shader ("%s", "%s")\n' % (self.types[self.type], self.name))

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
			if (type is self.literals.float):
				par.widget = Blender.Draw.String(name + ': ', par.id, x + j, y,
					self.size, h, par.widget.val, 80, par.tooltip)
				i += 1
			elif (type is self.literals.string):
				par.widget = Blender.Draw.String(name + ': ', par.id, x + j, y,
					self.size, h, par.widget.val, 128, par.tooltip)
				i += 1
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
		cmd='"%s" "%s"' % (GSOINFO, self.file)

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

			if (not self.literals.has_key(elements[0])):
				if (self.verbose > 1):
					print 'Error: unknow parameter type', elements
				continue

			lit = self.literals[elements[0]]

			par = None

			if (lit is self.literals.float):
				par = self.parameter(lit, elements[2], self.base_id + i, self.name + ' [float] ' + elements[1])
			elif (lit is self.literals.string):
				par = self.parameter(lit, elements[2][1:-1], self.base_id + i, self.name + ' [string] ' + elements[1])
			else:
				if (self.verbose > 1):
					print 'Error: unknow parameter', elements
				continue

			if (par):
				self.parameters[elements[1]] = par
				i += 1

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

	class texture(object):
		__slots__ = ['name', 'file', 'mapping', 'extend', 'texco']
		def __init__(self, name, file, mapping, extend, texco):
			self.name    = name
			self.file    = file
			self.mapping = mapping
			self.extend  = extend
			self.texco   = texco
	"""
	Gelato class export.
	"""
	def __init__(self):
		self.PRECISION     = 6
		self.SCALEBIAS     = 0.1
		self.FACTORAMBIENT = 200

		# FIXME
		self.convert_extend = dict([
			(Blender.Texture.ExtendModes.REPEAT,   'periodic'),
			(Blender.Texture.ExtendModes.CLIP,     'black'),
			(Blender.Texture.ExtendModes.CLIPCUBE, 'mirror'),
			(Blender.Texture.ExtendModes.EXTEND,   'clamp'),
#			(Blender.Texture.ExtendModes.CHECKER,  'periodic'),
		])

	def fix_file_name(self, name):
		return name.replace('\\', '\\\\')

	def head(self, frame, nframe):
		"""
		Write pyg header.
		"""
		curcam  = self.scene.getCurrentCamera()

		try:
			self.camera_name = curcam.name
		except:
			raise GelatoError, 'No camera present'

		try:
			scale = self.context.getRenderWinSize() / 100.0
		except:
			scale = 1.0

		try:
			strdate = ' (' + datetime.datetime.today().strftime('%a, %d %b %Y %H:%M:%S') + ')'
		except:
			strdate = ''

		self.file.write('## Exported by Blender Gelato %s%s\n' %
			(__version__, strdate))

		if (self.pass_beauty):
			self.file.write('## Pass: "beauty"\n')
		elif (self.pass_shadows):
			self.file.write('## Pass: "shadows"\n')
		elif (self.pass_ambient_occlusion):
			self.file.write('## Pass: "ambient occlusion"\n')

		if (frame and nframe):
			self.file.write('## Frame: %d/%d\n' %
				(frame, nframe))

		self.file.write('\n')

		self.file.write('Attribute ("int verbosity", %d)\n' %
			self.verbose)

		if (self.path_shader):
			self.file.write('Attribute ("string path:shader", "%s")\n' %
				self.path_shader)

		if (self.path_texture):
			self.file.write('Attribute ("string path:texture", "%s")\n' %
				self.path_texture)

		self.file.write('Attribute ("int[2] resolution", (%d, %d))\n' %
			(int(self.sizex * scale), int(self.sizey * scale)))

		self.file.write('Attribute ("int[2] spatialquality", (%d, %d))\n' %
			(self.spatialquality_x , self.spatialquality_y))

		self.file.write('Attribute ("string bucketorder", "%s")\n' %
			self.bucketorder)

		self.file.write('Attribute ("string orientation", "outside")\n')
		self.file.write('Attribute ("int twosided", 1)\n')

		self.file.write('Attribute ("int ray:maxdepth", %d)\n' %
			self.max_depth)

		self.file.write('\n')

		self.file.write('Parameter ("string filter", "%s")\n' %
			self.filter)

		self.file.write('Parameter ("float[2] filterwidth", (%s, %s))\n' %
			(self.filterwidth_x , self.filterwidth_y))

		self.file.write('Parameter ("float gain", %s)\n' %
			self.gain)

		self.file.write('Parameter ("float gamma", %s)\n' %
			self.gamma)

		if (self.format != 'OpenEXR'):
			self.file.write('Parameter ("float dither", %s)\n' %
				self.dither)

			self.file.write('Parameter ("int[4] quantize", (%s, %s, %s, %s))\n' % (
				int(self.quantize_zero),
				int(self.quantize_one),
				int(self.quantize_min),
				int(self.quantize_max)))

		if (self.compression):
			self.file.write('Parameter ("string compression", "%s")\n' %
				self.compression)

		if (self.pass_shadows):
				self.file.write('Output ("%s", "null", "%s", "%s")\n' %
					(self.title, self.data_color, self.camera_name))
		else:
			if (self.format):
				if (not frame):
					outfile_color = self.output
					outfile_z     = self.output_z
				else:
					outfile_color = self.output_mask   % frame
					outfile_z     = self.output_z_mask % frame

				self.file.write('Output ("%s", "%s", "%s", "%s")\n' %
					(outfile_color, self.format, self.data_color, self.camera_name))

				if (self.data_z):
					self.file.write('Output ("%s", "%s", "%s", "%s")\n' %
						(outfile_z, self.format, self.data_z, self.camera_name))

			if (self.preview):
				self.file.write('Output ("%s", "iv", "%s", "%s")\n' %
					(self.title, self.data_color, self.camera_name))

		self.camera(curcam)

		if (not self.pass_ambient_occlusion and \
			(self.pass_shadows or self.shadow_dynamic_maps)):
				self.cameras_shadows(frame)

		self.file.write('\nWorld ()\n')

		if (self.pass_ambient_occlusion):
			self.enable_ambient_occlusion()
		else:
			if (self.sky):
				self.background_color()
			if (self.key_fill_rim):
				self.enable_key_fill_rim()
			if (self.shadow_raytraced):
				self.enable_raytrace()

	def tail(self):
		"""
		Write the final part of pyg file.
		"""
		self.file.write('\nRender ("%s")\n\n'
			% self.camera_name)

	def join_list(self, l):
		return ', '.join([str(i) for i in l])

	def write_matrix(self, matrix):
		"""
		Write 16 elements of matrix.
		"""
		self.file.write('(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)\n' % (
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
		self.file.write('Translate (%s, %s, %s)\n' %
			(trans.x, trans.y, trans.z))

	def convert_matrix(self, matrix):
		euler = matrix.toEuler()
		scale = matrix.scalePart()
		trans = matrix.translationPart()

		self.file.write('Translate (%s, %s, %s)\n' %
			(trans.x, trans.y, trans.z))

		self.file.write('Scale (%s, %s, %s)\n' %
			(scale.x, scale.y, -scale.z))

		self.file.write('Rotate (%s, 0, 0, 1)\n' %
			euler.z)

		self.file.write('Rotate (%s, 0, 1, 0)\n' %
			-euler.y)

		self.file.write('Rotate (%s, 1, 0, 0)\n' %
			-euler.x)

	def instance_name(self, name, instance):
		if (not instance):
			return name
		else:
			return '__' + name + '-' + str(instance) + '__'

	def camera_shadows_name(self, name, instance):
		if (not instance):
			return '__' + name + '-shadows' + '__'
		else:
			return '__' + name + '-shadows-' + str(instance) + '__'

	def file_shadows_name(self, name, instance, frame):
		if ((instance == None) and (frame == None)):
			return os.path.join(self.directory, name + SHADOWMAP_EXT)
		elif ((instance != None) and (frame == None)):
			return os.path.join(self.directory, name + '-' + str(instance) + SHADOWMAP_EXT)
		elif ((instance == None) and (frame != None)):
			return os.path.join(self.directory, name + '_' + str(frame) + SHADOWMAP_EXT)
		else:
			return os.path.join(self.directory, name + '-' + str(instance) + '_' + str(frame) + SHADOWMAP_EXT)

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

		self.file.write('Attribute ("color C", (%s, %s, %s))\n' % (
			round(col[0], self.PRECISION),
			round(col[1], self.PRECISION),
			round(col[2], self.PRECISION)))

		self.file.write('Shader ("surface", "constant")\n')
		self.file.write('Input ("backplane.pyg")\n')

		self.file.write('PopAttributes ()\n')

	def shadow_name(self, name = None, instance = None, frame = None):
		shadowname = None
		if (name and (self.shadow_maps or self.shadow_dynamic_maps)):
			shadowname = self.file_shadows_name(name, instance, frame)
		elif (self.shadow_raytraced):
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
					'"float intensity", %s, '
					'"color lightcolor", (%s, %s, %s))\n' % (
				self.world.getName(),
				self.lights_factor / self.FACTORAMBIENT,
				col[0], col[1], col[2]))

	def pointlight(self, obj, lamp, matrix, instance, frame):
		name = obj.name

		self.file.write('\nPushTransform ()\n')

		self.convert_translation(matrix)
		self.shadow_name(name, instance, frame)

		self.file.write('Light ("%s", "pointlight", '
				'"float falloff", 2.0, '
				'"float intensity", %s, '
				'"color lightcolor", (%s, %s, %s))\n' % (
			self.instance_name(name, instance),
			lamp.getEnergy() * self.lights_factor,
			lamp.R, lamp.G, lamp.B))

		self.file.write('PopTransform ()\n')

	def distantlight(self, obj, lamp, matrix, instance, frame):
		name = obj.name

		self.file.write('\nPushTransform ()\n')

		self.convert_matrix(matrix)
		self.shadow_name(name, instance, frame)

		self.file.write('Light ("%s", "distantlight", '
				'"float intensity", %s, '
				'"color lightcolor", (%s, %s, %s), '
				'"float shadowbias", %s)\n' % (
			self.instance_name(name, instance),
			lamp.getEnergy() * self.lights_factor,
			lamp.R, lamp.G, lamp.B,
			lamp.bias * self.SCALEBIAS))

		self.file.write('PopTransform ()\n')

	def spotlight(self, obj, lamp, matrix, instance, frame):
		name = obj.name

		self.file.write('\nPushTransform ()\n')

		self.convert_matrix(matrix)
		self.shadow_name(name, instance, frame)

		self.file.write('Light ("%s", "spotlight", '
				'"float falloff", 2.0, '
				'"float intensity", %s, '
				'"color lightcolor", (%s, %s, %s), '
				'"float coneangle", %s, '
				'"float conedeltaangle", %s, '
				'"float shadowbias", %s)\n' % (
			self.instance_name(name, instance),
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

		name    = obj.name
		matrix  = obj.getMatrix()
		cam     = Blender.Camera.Get(obj.getData().name)

		ratio_x = self.context.aspectRatioX()
		ratio_y = self.context.aspectRatioY()
		ratio   = float(ratio_y) / float(ratio_x)

		self.file.write('\nPushTransform ()\n')
		self.file.write('PushAttributes ()\n')

		self.convert_matrix(matrix)

		self.file.write('Attribute ("float near", %s)\n' %
			round(cam.clipStart, self.PRECISION))

		self.file.write('Attribute ("float far", %s)\n' %
			round(cam.clipEnd, self.PRECISION))

		if (cam.getType()):
			# orthographic camera
			aspx = cam.scale / 2.0
			aspy = aspx * self.sizey / self.sizex * ratio

			self.file.write('Attribute ("string projection", "orthographic")\n')
			self.file.write('Attribute ("float[4] screen", (%s, %s, %s, %s))\n' %
				(-aspx, aspx, -aspy, aspy))
		else:
			# perspective camera
			if (ratio_x != ratio_y):
				aspx = self.sizex / self.sizey
				aspy = ratio
				self.file.write('Attribute ("float[4] screen", (%s, %s, %s, %s))\n' %
					(-aspx, aspx, -aspy, aspy))

			if (self.sizex > self.sizey):
				fac = self.sizey / self.sizex
			else:
				fac = 1.0

			fov = degrees(2.0 * atan2(16.0 * fac, cam.lens))

			self.file.write('Attribute ("string projection", "perspective")\n')
			self.file.write('Attribute ("float fov", %s)\n' %
				round(fov, self.PRECISION))

		self.file.write('Attribute ("float pixelaspect", %s)\n' %
			(1.0 / ratio))

		if (self.dof):
			self.file.write('Attribute ("int dofquality", %d)\n' %
				self.dofquality)

			if (self.fstop):
				self.file.write('Attribute ("float fstop", %s)\n' %
					float(self.fstop))
			if (self.focallength):
				self.file.write('Attribute ("float focallength", %s)\n' %
					float(self.focallength))
			if (self.focaldistance):
				self.file.write('Attribute ("float focaldistance", %s)\n' %
					float(self.focaldistance))

		self.file.write('Camera ("%s")\n' %
			name)

		self.file.write('PopAttributes ()\n')
		self.file.write('PopTransform ()\n')

	def camera_light(self, obj, lamp, name, matrix, instance, frame):
		self.file.write('\nPushTransform ()\n')

		self.convert_matrix(matrix)

		self.file.write('Camera ("%s", '
				'"int[2] resolution", (%d, %d), '
				'"int[2] spatialquality", (%d, %d), '
				'"string projection", "perspective", '
				'"float fov", %s, '
				'"float near", %s, '
				'"float far", %s)\n' % (
			self.camera_shadows_name(name, instance),
			lamp.bufferSize, lamp.bufferSize,
			lamp.samples, lamp.samples,
			lamp.spotSize,
			lamp.clipStart,
			lamp.clipEnd))

		self.file.write('PopTransform ()\n')

		if (self.shadow_dynamic_maps):
			self.file.write('Parameter ("int dynamic", 1)\n')

		self.file.write('Output ("%s", '
				'"shadow", "z", "%s", '
				'"string compression", "%s", '
				'"string filter", "min", '
				'"float[2] filterwidth", (1.0, 1.0), '
				'"float dither", 0.0, '
				'"int[4] quantize", (0, 0, 0, 0))\n' % (
			self.file_shadows_name(name, instance, frame),
			self.camera_shadows_name(name, instance),
			self.compression_shadow))

	def camera_shadows(self, obj, matrix = None, instance = None, frame = None):
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
		if (ltype is Blender.Lamp.Types.Spot or
			ltype is Blender.Lamp.Types.Sun or
			ltype is Blender.Lamp.Types.Lamp):
				self.camera_light(obj, lamp, name, mat, instance, frame)

	def light(self, obj, matrix = None, instance = None, frame = None):
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
		if (ltype is Blender.Lamp.Types.Lamp):
			self.pointlight(obj, lamp, mat, instance, frame)
		elif (ltype is Blender.Lamp.Types.Sun):
			self.distantlight(obj, lamp, mat, instance, frame)
		elif (ltype is Blender.Lamp.Types.Spot):
			self.spotlight(obj, lamp, mat, instance, frame)

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

	def mesh(self, obj, matrix = None, instance = None, frame = None):
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

		# face UV

		faceuv = mesh.hasFaceUV()

		# get property catmull_clark

		catmull_clark = get_property_catmull_clark(obj)

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
					nlist_col[face.v[j].index] = [c.r, c.g, c.b]

		# points

		nlist = []
		nlist_nor = []
		for vert in mesh.verts:
			nlist_nor.append(vert.no)
			nlist.append('(%s, %s, %s)' % (
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
				nlist.append('(%s, %s, %s)' % (
					round(nor[0], self.PRECISION),
					round(nor[1], self.PRECISION),
					round(nor[2], self.PRECISION)))
			normals = ', '.join(nlist)

		# vertex color

		vertexcolor = None
		if (vtcolor):
			nlist = []
			for c in nlist_col:
				try:
					nlist.append('(%s, %s, %s)' % (
						c[0] / 255.0,
						c[1] / 255.0,
						c[2] / 255.0))
				except:
					nlist.append('(0.0, 0.0, 0.0)')
			vertexcolor = ', '.join(nlist)

		self.file.write('\nPushAttributes ()\n')

		self.file.write('Attribute ("string name", "%s")\n' %
			self.instance_name(name, instance))

		if ((not self.pass_ambient_occlusion) and mesh.materials):

			# materials

			multiple_mat = len(mesh.materials) > 1
			if (multiple_mat and catmull_clark):
				set_mat = set(range(nfaces))

			for i, geo in dict_geometry.iteritems():

				try:
					mat = mesh.materials[i]
				except:
					continue

				flags = mat.getMode()

				self.file.write('PushAttributes ()\n')

				# vertex color

				if (not flags & Blender.Material.Modes.VCOL_PAINT):
					vertexcolor = None

				# multiple materials on a single mesh

				if (multiple_mat and catmull_clark):
					holes = list(set_mat - set(geo.materials))
				else:
					holes = None

				# color

				self.file.write('Attribute ("color C", (%s, %s, %s))\n' % (
					round(mat.R, self.PRECISION),
					round(mat.G, self.PRECISION),
					round(mat.B, self.PRECISION)))

				# alpha

				alpha = mat.alpha
				if (alpha < 1.0):
					alpha = round(alpha, self.PRECISION),
					self.file.write('Attribute ("color opacity", (%s, %s, %s))\n' %
						(alpha, alpha, alpha))

				# texture files (FIXME)

				use_uv = False
				textures_color = []
				list_tex = mat.getTextures()

				if (list_tex):
					for mtex in list_tex:
						if (not mtex):
							continue
						if (mtex.tex.type is Blender.Texture.Types.IMAGE):
							image = mtex.tex.getImage()
							if (not image):
								continue
							filename = image.getFilename()
							if ((filename[:2] == '//') or (filename[:2] == '\\\\')):
								filename = filename[2:]
							if (mtex.mapto is Blender.Texture.MapTo.COL):
								textures_color.append(self.texture(mtex.tex.getName(),
									filename,
									mtex.mapping,
									mtex.tex.extend,
									mtex.texco))
								if (mtex.texco is Blender.Texture.TexCo.UV):
									use_uv = True

				# UV coordinates (FIXME)

				if (use_uv):
					tex_s = range(len(mesh.verts))
					tex_t = range(len(mesh.verts))
					if (faceuv):
						for face in mesh.faces:
							for j in range(len(face.v)):
								i = face.v[j].index
								uv_cor = face.uv[j]
								tex_s[i] = round(uv_cor[0], self.PRECISION)
								tex_t[i] = round(1.0 - uv_cor[1], self.PRECISION)

				# shader surface (FIXME)

				if (textures_color):
					self.file.write('ShaderGroupBegin ()\n')
					for ftex in textures_color:
						if (self.verbose > 0):
							self.file.write('## Texture: "%s"\n' % ftex.name)
						self.file.write('Shader ("surface", "pretexture", "string texturename", "%s", "string wrap", "%s")\n' %
							(ftex.file, self.convert_extend[ftex.extend]))

				if (self.verbose > 0):
					self.file.write('## Material: "%s"\n' % mat.name)

				if (not flags & Blender.Material.Modes.SHADELESS):
					self.file.write('Shader ("surface", "plastic")\n')

				if (textures_color):
					self.file.write('ShaderGroupEnd ()\n')

				# textures UV coordinates

				if (use_uv):
					self.file.write('Parameter ("vertex float s", (%s))\n' %
						self.join_list(tex_s))
					self.file.write('Parameter ("vertex float t", (%s))\n' %
						self.join_list(tex_t))

				# geometry

				if (catmull_clark):
					self.mesh_geometry(name, transform, single_sided, interpolation, nverts,
						verts,     points, normals, vertexcolor, holes)
				else:
					self.mesh_geometry(name, transform, single_sided, interpolation, geo.nverts,
						geo.verts, points, normals, vertexcolor)

				self.file.write('PopAttributes ()\n')
		else:
			self.mesh_geometry(name, transform, single_sided, interpolation, nverts, verts, points, normals)

		self.file.write('PopAttributes ()\n')

	def visible(self, obj):
		if ((obj.users > 1) and ((set(obj.layers) & self.viewlayer) == set())):
			if (self.verbose > 1):
				print 'Info: Object', obj.name, 'invisible'
			return False
		return True

	def build(self, obj, method, frame):
		if (not self.visible(obj)):
			return

		if (self.dup_verts):
			try:
				# get duplicate object
				dupobjs = obj.DupObjects
			except:
				dupobjs = None

			if (dupobjs):
				i = 0
				for dobj, mat in dupobjs:
					exec('self.%s(dobj, mat, %d, frame)' % (method, i))
					i += 1
				return
			else:
				try:
					# skip object if DupObjects
					if (obj.parent and obj.parent.DupObjects):
						return
				except:
					pass

		exec('self.%s(obj, frame = frame)' % method)

	def cameras_shadows(self, frame):
		for obj in self.objects:
			self.build(obj, 'camera_shadows', frame)

	def lights(self, frame, nframe):
		bar = 'Lights ...'
		if (frame and nframe):
			bar += ' (%d/%d)' % (frame, nframe)
		self.ambientlight()
		Blender.Window.DrawProgressBar(0.0, bar)
		n = float(len(self.objects))
		for i, obj in enumerate(self.objects):
			self.build(obj, 'light', frame)
			Blender.Window.DrawProgressBar(i / n, bar)

	def geometries(self, frame, nframe):
		bar = 'Geometries ...'
		if (frame and nframe):
			bar += ' (%d/%d)' % (frame, nframe)
		Blender.Window.DrawProgressBar(0.0, bar)
		n = float(len(self.objects))
		for i, obj in enumerate(self.objects):
			if (self.verbose > 1):
				print 'Info: Object', obj.name, 'type', obj.getType()
			self.build(obj, 'mesh', frame)
			Blender.Window.DrawProgressBar(i / n, bar)

	def setup(self):
		global gelato_gui

		# anim sequence

		self.anim = permanents['anim'].val

		# beauty pass

		self.pass_beauty  = permanents['_pass_beauty'].val

		# shadows pass

		self.pass_shadows = permanents['_pass_shadows'].val

		# ambient occlusion pass

		self.pass_ambient_occlusion = permanents['_pass_ambient_occlusion'].val

		# output file name image, title and directoty

		(self.format, self.suffix) = gelato_gui.menu_format.convert(permanents['format'].val)[0:2]

		self.filename = permanents['filename'].val

		(base, ext) = os.path.splitext(self.filename)

		self.title = os.path.basename(base)
		self.filename_mask = base + '.%d' + ext

		if (os.path.sep == '\\'):
			self.filename      = self.fix_file_name(self.filename)
			self.filename_mask = self.fix_file_name(self.filename_mask)

		if (self.suffix):
			self.output      = base + self.suffix
			self.output_mask = base + '.%d' + self.suffix

			self.output_z      = base + '_z' + self.suffix
			self.output_z_mask = base + '_z' + '.%d' + self.suffix

			if (os.path.sep == '\\'):
				self.output        = self.fix_file_name(self.output)
				self.output_mask   = self.fix_file_name(self.output_mask)
				self.output_z      = self.fix_file_name(self.output_z)
				self.output_z_mask = self.fix_file_name(self.output_z_mask)

		(directory, file) = os.path.split(self.filename)
		self.directory = directory

		# output data

		(self.data_color, self.data_z) = gelato_gui.menu_data.convert(permanents['data'].val)

		# compression

		comp = gelato_gui.menu_format.convert(permanents['format'].val)[2]
		if (comp):
			self.compression = comp.convert(permanents['compression'].val)
		else:
			self.compression = None

		self.compression_shadow = gelato_gui.menu_compression_tiff.convert(permanents['compression_shadow'].val)

		# bucketorder

		self.bucketorder = gelato_gui.menu_bucketorder.convert(permanents['bucketorder'].val)

		# pixel filter

		self.filter = gelato_gui.menu_filter2.convert(permanents['filter'].val)

		# spatialquality

		self.spatialquality_x = int(permanents['antialiasing_x'].val)
		self.spatialquality_y = int(permanents['antialiasing_y'].val)

		# filterwidth

		self.filterwidth_x = float(permanents['filterwidth_x'].val)
		self.filterwidth_y = float(permanents['filterwidth_y'].val)

		# preview window

		self.preview = permanents['preview'].val

		# shadows

		self.shadow_maps         = permanents['shadow_maps'].val
		self.shadow_dynamic_maps = permanents['shadow_dynamic_maps'].val
		self.shadow_raytraced    = permanents['shadow_raytraced'].val

		# light factor

		self.lights_factor = permanents['lights_factor'].val

		# gamma and gain

		self.gamma = permanents['gamma'].val
		self.gain  = permanents['gain'].val

		# dither

		self.dither  = permanents['dither'].val

		# quantize

		self.quantize_zero = permanents['quantize_zero'].val
		self.quantize_one  = permanents['quantize_one'].val
		self.quantize_min  = permanents['quantize_min'].val
		self.quantize_max  = permanents['quantize_max'].val

		# max depth

		self.max_depth = permanents['max_depth'].val

		# background color

		self.sky = permanents['sky'].val

		# key-fill-rim lights

		self.key_fill_rim = permanents['key_fill_rim'].val

		# double side

		self.all_double_sided = permanents['all_double_sided'].val

		# dup_verts

		self.dup_verts = permanents['dup_verts'].val

		# no all lights

		self.all_lights = permanents['all_lights'].val

		# DoF

		self.dof           = permanents['dof'].val
		self.fstop         = permanents['fstop'].val
		self.focallength   = permanents['focallength'].val
		self.focaldistance = permanents['focaldistance'].val
		self.dofquality    = permanents['dofquality'].val

		# paths

		self.path_shader  = permanents['path_shader'].val
		self.path_texture = permanents['path_texture'].val

	def sequence(self, frame = None, nframe = None):
		if (frame == None):
			seqname = self.filename
		else:
			seqname = self.filename_mask % frame

		try:
			self.file = open(seqname, 'w')
		except IOError:
			raise GelatoError, 'Cannot write file ' + seqname

		self.head(frame, nframe)

		if ((not self.pass_ambient_occlusion) and \
			(not self.pass_shadows) and \
			self.all_lights):
				self.lights(frame, nframe)

		self.geometries(frame, nframe)

		self.tail()

		self.file.close()

	def export(self, scene):

		# leave edit mode before getting the mesh

		if (Blender.Window.EditMode()):
			Blender.Window.EditMode(0)

		# verbosity

		self.verbose = 1
		try:
			rt = Blender.Get('rt')
			if (rt == 42):
				self.verbose = 0
			if (rt == 43):
				self.verbose = 2
		except:
			pass

		self.scene = scene

		# setup variable from GUI

		self.setup()

		# shader ambocclude

		if (shader_ambocclude):
			shader_ambocclude.set_verbose(self.verbose)

		if (self.verbose > 0):
			timestart = Blender.sys.time()
			print 'Info: starting Gelato pyg export to', self.filename

		self.viewlayer = set(Blender.Window.ViewLayer())
		self.objects   = scene.getChildren()
		self.world     = Blender.World.GetCurrent()
		self.context   = self.scene.getRenderingContext()
		self.sizex     = float(self.context.imageSizeX())
		self.sizey     = float(self.context.imageSizeY())

		if (self.anim):

			if (not self.format):
				ret = Blender.Draw.PupMenu('Output null, continue ?%t|no%x1|yes%x2')
				if (ret != 2):
					return

			staframe = Blender.Get('staframe')
			curframe = Blender.Get('curframe')
			endframe = Blender.Get('endframe')

			nframe = endframe - staframe + 1

			# all frames

			try:
				for f in range(staframe, endframe + 1):
					Blender.Set('curframe', f)

					if (self.verbose > 1):
						print 'Info: exporting frame', f

					self.sequence(f, nframe)
			except:
				Blender.Set('curframe', curframe)
				Blender.Window.DrawProgressBar(1.0, '')
				raise

			Blender.Set('curframe', curframe)

			# command file

			try:
				self.file = open(self.filename, 'w')
			except IOError:
				raise GelatoError, 'Cannot write file ' + self.filename

			for f in range(staframe, endframe + 1):
				self.file.write('Command ("system", "string[2] argv", ("%s", "%s"))\n' %
					(GELATO, self.filename_mask % f))

			self.file.close()

		else:
			self.sequence()

		Blender.Window.DrawProgressBar(1.0, '')

		if (self.verbose > 0):
			print 'Info: finished Gelato pyg export (%.2fs)' % (Blender.sys.time() - timestart)

# GUI

class cfggui(object):
	class panel(object):
		__slots__ = ['name', 'reg_name', 'func', 'help', 'id']
		def __init__(self, name, reg_name, func, help):
			self.name     = name
			self.reg_name = reg_name
			self.func     = func
			self.help     = help
			self.id       = 0

	class bake_menu(object):
		__slots__ = ['cookie', 'store', 'food']
		def __init__(self, title = None, options = None,):
			if (title):
				str = '%s %%t' % title
			else:
				str = ''

			i = 0
			self.store = {}
			self.food = {}
			for (name, data) in options:
				str += '|%s %%x%d' % (name, i)
				self.store[i] = data
				self.food[name] = i
				i += 1

			self.cookie = str

		def get_cookie(self):
			return self.cookie

		def convert(self, id):
			if (self.store.has_key(id)):
				return self.store[id]
			else:
				return None

		def val(self, name):
			if (self.food.has_key(name)):
				return self.food[name]
			else:
				return None

	def __init__(self):
		self.x0 = 10		# start cursor x
		self.y0 = 10		# start cursor y
		self.h  = 22		# height button
		self.s  = 30		# step y
		self.m  = 10		# margin button
		self.id_first = 1000	# first id button

		self.panels = [
			self.panel('Output', '_pan_output',
				self.panel_output, 'Panel output data'),

			self.panel('Pass', '_pan_pass',
				self.panel_pass, 'Panel select pass'),

			self.panel('Geometries', '_pan_geometries',
				self.panel_geometries, 'Panel geometries'),

			self.panel('Lights', '_pan_lights',
				self.panel_lights, 'Panel lights'),

			self.panel('Shadows', '_pan_shadows',
				self.panel_shadows, 'Panel select shadows type'),

			self.panel('DoF', '_pan_dof',
				self.panel_dof, 'Panel Depth of Field'),

			self.panel('Environment', '_pan_environment',
				self.panel_environment, 'Panel environment'),
		]

		# compression

		self.menu_compression_tiff = self.bake_menu('TIFF compression', [
			['None', 'none'],
			['ZIP',  'zip'],
			['LZW',  'lzw'],
		])

		self.menu_compression_openexr = self.bake_menu('OpenEXR compression', [
			['None',  'none'],
			['ZIP',   'zip'],
			['ZIPS',  'zips'],
			['PIZ',   'piz'],
			['PXR24', 'pxr24'],
		])

		# formats

		self.menu_format = self.bake_menu('Output format', [
			['Null',    [None,      None,    None, '']],
			['TIFF',    ['tiff',    '.tif',  self.menu_compression_tiff, 'TIFF compression']],
			['JPEG',    ['jpg',     '.jpg',  None, '']],
			['TARGA',   ['targa',   '.tga',  None, '']],
			['PPM',     ['ppm',     '.ppm',  None, '']],
			['SGI',     ['DevIL',   '.sgi',  None, '']],
			['BMP',     ['DevIL',   '.bmp',  None, '']],
			['PCX',     ['DevIL',   '.pcx',  None, '']],
			['DDS',     ['DevIL',   '.dds',  None, '']],
			['OpenEXR', ['OpenEXR', '.exr',  self.menu_compression_openexr, 'OpenEXR compression']],
		])

		self.val_format_null    = self.menu_format.val('Null')
		self.val_format_openEXR = self.menu_format.val('OpenEXR')

		# data

		self.menu_data = self.bake_menu('Output data', [
			['RGB',      ['rgb',  None]],
			['RGBA',     ['rgba', None]],
			['Z',        ['z',    None]],
			['RGB + Z',  ['rgb',  'z']],
			['RGBA + Z', ['rgba', 'z']],
			['AvgZ',     ['avgz', None]],
			['VolZ',     ['volz', None]],
		])

		self.val_data_z = self.menu_data.val('Z')

		# bucket orders

		self.menu_bucketorder = self.bake_menu('Bucketorder', [
			['Horizontal', 'horizontal'],
			['Vertical',   'vertical'],
			['Spiral',     'spiral'],
		])

		# filters

		filter = [
			['Gaussian',        'gaussian'],
			['Box',             'box'],
			['Triangle',        'triangle'],
			['Catmull-Rom',     'catmull-rom'],
			['Sinc',            'sinc'],
			['Blackman-Harris', 'blackman-harris'],
			['Mitchell',        'mitchell'],
			['B-Spline',        'b-spline'],
		]

		self.menu_filter1 = self.bake_menu('Pixel filter', filter)

		filter.extend([
			['Min',             'min'],
			['Max',             'max'],
			['Average',         'average'],
		])

		self.menu_filter2 = self.bake_menu('Pixel filter', filter)

		self.val_filter_min = self.menu_filter2.val('Min')

		self.home()
		self.reset_id()

	def home(self):
		self.x = self.x0
		self.y = self.y0

	def inc_x(self, i = 0):
		self.x += i

	def inc_y(self, i = 0):
		self.y += i

	def line_feed(self):
		self.x = self.x0
		self.inc_y(self.s)

	def blank(self, x = 0):
		self.inc_x(x + self.m)

	def reset_id(self):
		self.id = self.id_first
		self.id_buttons = dict()

	def get_id(self, func = None):
		id = self.id
		self.id += 1
		self.id_buttons[id] = func
		return id

	def draw_rect(self, x, y, w, h):
		Blender.BGL.glRecti(self.x + x, self.y + y, self.x + x + w, self.y + y + h)
		self.inc_x(w + self.m)

	def draw_text(self, s, size, x = 0, y = 0):
		Blender.BGL.glRasterPos2i(self.x + x, self.y + y)
		Blender.Draw.Text(s)
		self.inc_x(size + self.m)

	def draw_string(self, s, size, length, name, func = None, help = '', sep = None):
		id = self.get_id(func)
		permanents[name] = Blender.Draw.String(s, id, self.x, self.y, size, self.h,
			permanents[name].val, length, help)
		if (not sep is None):
			self.inc_x(size + sep)
		else:
			self.inc_x(size + self.m)
		return id

	def draw_number(self, s, size, min, max, name, func = None, help = ''):
		id = self.get_id(func)
		permanents[name] = Blender.Draw.Number(s, id, self.x, self.y, size, self.h,
			permanents[name].val, min, max, help)
		self.inc_x(size + self.m)
		return id

	def draw_slider(self, s, size, min, max, name, func = None, help = ''):
		id = self.get_id(func)
		permanents[name] = Blender.Draw.Slider(s, id, self.x, self.y, size, self.h,
			permanents[name].val, min, max, 0, help)
		self.inc_x(size + self.m)
		return id

	def draw_button(self, s, size, func = None, help = '', sep = None):
		id = self.get_id(func)
		Blender.Draw.PushButton(s, id, self.x, self.y, size, self.h, help)
		if (not sep is None):
			self.inc_x(size + sep)
		else:
			self.inc_x(size + self.m)
		return id

	def draw_toggle(self, s, size, name, func = None, help = ''):
		id = self.get_id(func)
		permanents[name] = Blender.Draw.Toggle(s, id, self.x, self.y, size, self.h,
			permanents[name].val, help)
		self.inc_x(size + self.m)
		return id

	def draw_menu(self, bake, size, name, func = None, help = ''):
		id = self.get_id(func)
		permanents[name] = Blender.Draw.Menu(bake.get_cookie(), id, self.x, self.y, size, self.h,
			permanents[name].val, help)
		self.inc_x(size + self.m)
		return id

	def draw(self):
		self.home()
		self.reset_id()

		Blender.BGL.glClearColor(.5325, .6936, .0, 1.0)
		Blender.BGL.glClear(Blender.BGL.GL_COLOR_BUFFER_BIT)
		Blender.BGL.glColor3f(1.0, 1.0, 1.0)

		self.panel_common()
		self.line_feed()
		self.panel_select()

	def handle_event(self, evt, val):
		if ((evt == Blender.Draw.ESCKEY) or (evt == Blender.Draw.QKEY)):
			ret = Blender.Draw.PupMenu('OK?%t|Exit Blender Gelato%x1')
			if (ret == 1):
				registry_save()
				Blender.Draw.Exit()

	def handle_button_event(self, evt):
		if (self.id_buttons.has_key(evt)):
			func = self.id_buttons[evt]
			if (func):
				func(evt)

		if (permanents['format'].val == self.val_format_null):
			permanents['preview'].val = 1

		if (permanents['data'].val < self.val_data_z):
			if (permanents['filter'].val >= self.val_filter_min):
				permanents['filter'].val = 0 # Gaussian

		if (shader_ambocclude):
			shader_ambocclude.update(evt)

		registry_save()
		Blender.Draw.Redraw(1)

	def cb_exit(self, id):
		self.handle_event(Blender.Draw.ESCKEY, 0)

	def cb_default(self, id):
		registry_default()

	def cb_save(self, id):
		try:
			pyg.export(Blender.Scene.GetCurrent())
		except GelatoError, strerror:
			Blender.Draw.PupMenu('Error%t|"' + str(strerror) + '"')

	def cb_render(self, id):
		self.cb_save(id)
		if (os.path.isfile(permanents['filename'].val)):
			os.system('"%s" "%s"&' % (GELATO, permanents['filename'].val))

	def cb_catmull_clark(self, id):
		set_property_catmull_clark()

	def cb_pass(self, id):
		permanents['_pass_beauty'].val = 0
		permanents['_pass_shadows'].val = 0
		permanents['_pass_ambient_occlusion'].val = 0

		if (id == self.id_beauty):
			permanents['_pass_beauty'].val = 1
		elif (id == self.id_shadows):
			permanents['_pass_shadows'].val = 1
		elif (id == self.id_ambient_occlusion):
			permanents['_pass_ambient_occlusion'].val = 1

	def cb_shadows(self, id):
		if (id != self.id_shadow_maps):
			permanents['shadow_maps'].val = 0
		if (id != self.id_shadow_dynamic):
			permanents['shadow_dynamic_maps'].val = 0
		if (id != self.id_shadow_raytraced):
			permanents['shadow_raytraced'].val = 0

	def cb_panel(self, id):
		for pan in self.panels:
			if (pan.id != id):
				permanents[pan.reg_name].val = 0

	def cb_select(self, name):
		global permanents
		permanents['filename'].val = os.path.abspath(name)

	def cb_filename(self, id):
		Blender.Window.FileSelector(self.cb_select, '.pyg', permanents['filename'].val)

	def panel_common(self):
		self.draw_text('Blender Gelato v' + __version__, 120, 2, 6)

		self.draw_button('Save', 80,
			self.cb_save, 'Save pyg file')

		self.draw_button('Render', 80,
			self.cb_render, 'Save and render pyg file')

		self.draw_toggle('Anim', 80, 'anim',
			help = 'Enable sequence render')

		self.blank(180)

		self.draw_button('Default', 80, self.cb_default,
			'Set all items to default values')

		self.draw_button('Exit', 80, self.cb_exit,
			'Exit Python script')

	def panel_select(self):
		func = None
		for pan in self.panels:
			if (permanents[pan.reg_name].val):
				func = pan.func
				break

		if (func == None):
			permanents[self.panels[0].reg_name].val = 1
			func = self.panels[0].func

		for pan in self.panels:
			pan.id = self.draw_toggle(pan.name, 100, pan.reg_name, self.cb_panel, pan.help)

		self.line_feed()

		Blender.BGL.glColor3f(.2392, .3098, 1.0)
		self.draw_rect(0, 4, 760, 10)
		Blender.BGL.glColor3f(1.0, 1.0, 1.0)

		self.line_feed()

		func()

	def panel_output(self):
		self.draw_toggle('Preview', 100, 'preview',
			help = 'Enable window preview')

		self.draw_menu(self.menu_data, 100, 'data',
			help = 'Output data')

		self.draw_menu(self.menu_format, 100, 'format',
			help = 'Output format')

		(comp, comp_help) = self.menu_format.convert(permanents['format'].val)[2:4]
		if (comp):
			self.draw_menu(comp, 100, 'compression',
				help = comp_help)

		self.line_feed()

		self.draw_menu(self.menu_bucketorder, 100, 'bucketorder',
			help = 'Render Bucketorder')

		self.draw_number('AA X: ', 100, 1, 16, 'antialiasing_x',
			help = 'Spatial AntiAliasing x')

		self.draw_number('AA Y: ', 100, 1, 16, 'antialiasing_y',
			help = 'Spatial AntiAliasing y')

		self.draw_number('Gain: ', 100, 0.0, 10.0, 'gain',
			help = 'Image gain')

		self.draw_number('Gamma: ', 100, 0.0, 10.0, 'gamma',
			help = 'Image gamma')

		v = permanents['format'].val
		if ((v != self.val_format_null) and (v != self.val_format_openEXR)):
			self.line_feed()

			Blender.BGL.glColor3f(0.0, 0.0, 0.0)
			self.draw_text('Quantize', 50, 2, 6)
			Blender.BGL.glColor3f(1.0, 1.0, 1.0)

			len = 120
			len_max = 20

			self.draw_string('zero: ', len, len_max, 'quantize_zero',
				help = 'Quantization parameter zero', sep = 0)

			self.draw_string('one: ', len, len_max, 'quantize_one',
				help = 'Quantization parameter one', sep = 0)

			self.draw_string('min: ', len, len_max, 'quantize_min',
				help = 'Quantization parameter min', sep = 0)

			self.draw_string('max: ', len, len_max, 'quantize_max',
				help = 'Quantization parameter max')

		self.line_feed()

		if (permanents['data'].val < self.val_data_z):
			menu_filter = self.menu_filter1
		else:
			menu_filter = self.menu_filter2

		self.draw_menu(menu_filter, 130, 'filter',
			help = 'Pixel filter')

		self.draw_number('Filter X: ', 140, 0.0, 32.0, 'filterwidth_x',
			help = 'Filter width x')

		self.draw_number('Filter Y: ', 140, 0.0, 32.0, 'filterwidth_y',
			help = 'Filter width y')

		if ((v != self.val_format_null) and (v != self.val_format_openEXR)):
			self.draw_number('Dither: ', 100, 0.0, 10.0, 'dither',
				help = 'Dither amplitude')

		self.line_feed()

		self.draw_button('Filename:', 100, self.cb_filename,
			'Select file name', 0)

		self.draw_string('', 440, 200, 'filename',
			help = 'File name')

		self.line_feed()

		self.draw_string('Path shader: ', 540, 250, 'path_shader',
			help = 'Search path for compiled shaders')

		self.line_feed()

		self.draw_string('Path textures: ', 540, 250, 'path_texture',
			help = 'Search path for texture files')

	def panel_pass(self):
		self.id_beauty = self.draw_toggle('Beauty', 130, '_pass_beauty',
			self.cb_pass, 'Enable beauty pass')

		if (permanents['shadow_maps'].val):
			self.id_shadows = self.draw_toggle('Shadows', 130, '_pass_shadows',
				self.cb_pass, 'Enable shadows pass')
		else:
			self.id_shadows = -1

		self.id_ambient_occlusion = self.draw_toggle('Ambient Occlusion', 130, '_pass_ambient_occlusion',
			self.cb_pass, 'Enable ambient occlusion pass')

		self.line_feed()

		if (permanents['_pass_ambient_occlusion'].val and shader_ambocclude):
			shader_ambocclude.gui(self.x, self.y, self.h, self.s)

	def panel_geometries(self):
		self.draw_toggle('All double sided', 130, 'all_double_sided',
			help = 'Enable all double sided faces')

		self.draw_toggle('DupliVerts', 130, 'dup_verts',
			help = 'Enable DupliVerts')

		self.line_feed()

		self.draw_button('Catmull Clark', 130,
			self.cb_catmull_clark, 'Enable catmull-clark property')

	def panel_lights(self):
		self.draw_toggle('Enable', 90, 'all_lights',
			help = 'Enable all lights')

		self.draw_toggle('Key Fill Rim', 90, 'key_fill_rim',
			help = 'Enable Key Fill Rim lights')

		if (permanents['all_lights'].val):
			self.draw_slider('Lights factor: ', 255, 0.0, 1000.0, 'lights_factor',
				help = 'Lights factor')

	def panel_shadows(self):
		self.id_shadow_maps = self.draw_toggle('Maps', 100, 'shadow_maps',
			self.cb_shadows, 'Enable shadow maps')

		self.id_shadow_dynamic = self.draw_toggle('Dynamics', 100, 'shadow_dynamic_maps',
			self.cb_shadows, 'Enable dynamic shadow maps')

		self.id_shadow_raytraced = self.draw_toggle('Ray traced', 100, 'shadow_raytraced',
			self.cb_shadows, 'Enable ray traced shadows')

		if (permanents['shadow_maps'].val):
			self.line_feed()
			self.draw_menu(self.menu_compression_tiff, 100, 'compression_shadow',
				help = 'Shadow compression')

	def panel_dof(self):
		self.draw_toggle('Enable', 90, 'dof', help = 'Enable Depth Of Field')

		if (permanents['dof'].val):
			self.draw_string('F/stop: ', 100, 20, 'fstop',
				help = 'F/stop for depth of field')

			self.draw_string('Focal length: ', 160, 20, 'focallength',
				help = 'Lens focal length')

			self.draw_string('Focal distance: ', 160, 20, 'focaldistance',
				help = 'Distance to sharp focus')

			self.line_feed()

			self.draw_number('Quality: ', 90, 1, 128, 'dofquality',
				help = 'Number of lens values for DoF')

	def panel_environment(self):
		self.draw_toggle('Sky', 60, 'sky',
			help = 'Enable background color')

		self.draw_number('Raytrace max depth: ', 160, 0, 16, 'max_depth',
			help = 'Raytrace max depth')

# property

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

def get_property_catmull_clark(obj):
	try:
		prop = obj.getProperty('catmull_clark')
		if (prop.getType() == 'BOOL'):
			return prop.getData()
	except:
		pass

	return False

# registry

def registry_default():
	global permanents, FILENAME

	permanents = {
		'filename':                Blender.Draw.Create(FILENAME),
		'anim':                    Blender.Draw.Create(0),
		'bucketorder':             Blender.Draw.Create(2),		# Spiral
		'max_depth':               Blender.Draw.Create(2),

		'preview':                 Blender.Draw.Create(1),
		'format':                  Blender.Draw.Create(0),		# Null
		'data':                    Blender.Draw.Create(0),		# RGB

		'compression':             Blender.Draw.Create(1),		# ZIP
		'compression_shadow':      Blender.Draw.Create(1),		# ZIP

		'shadow_maps':             Blender.Draw.Create(0),
		'shadow_dynamic_maps':     Blender.Draw.Create(0),
		'shadow_raytraced':        Blender.Draw.Create(0),

		'antialiasing_x':          Blender.Draw.Create(4),
		'antialiasing_y':          Blender.Draw.Create(4),

		'filter':                  Blender.Draw.Create(0),		# Gaussian
		'filterwidth_x':           Blender.Draw.Create(2.0),
		'filterwidth_y':           Blender.Draw.Create(2.0),

		'gamma':                   Blender.Draw.Create(1.0),
		'gain':                    Blender.Draw.Create(1.0),

		'dither':                  Blender.Draw.Create(0.5),

		'quantize_zero':           Blender.Draw.Create('0'),
		'quantize_one':            Blender.Draw.Create('255'),
		'quantize_min':            Blender.Draw.Create('0'),
		'quantize_max':            Blender.Draw.Create('255'),

		'all_double_sided':        Blender.Draw.Create(0),
		'dup_verts':               Blender.Draw.Create(1),

		'lights_factor':           Blender.Draw.Create(50.0),
		'key_fill_rim':            Blender.Draw.Create(0),
		'all_lights':              Blender.Draw.Create(1),
		'sky':                     Blender.Draw.Create(1),

		'dof':                     Blender.Draw.Create(0),
		'fstop':                   Blender.Draw.Create('4.0'),
		'focallength':             Blender.Draw.Create('0.032'),
		'focaldistance':           Blender.Draw.Create(''),
		'dofquality':              Blender.Draw.Create(16),

		'path_shader':             Blender.Draw.Create('.:$GELATOHOME/shaders:&'),
		'path_texture':            Blender.Draw.Create('.:$GELATOHOME/textures:&'),

		'_pass_beauty':            Blender.Draw.Create(1),
		'_pass_shadows':           Blender.Draw.Create(0),
		'_pass_ambient_occlusion': Blender.Draw.Create(0),

		'_pan_output':             Blender.Draw.Create(1),
		'_pan_pass':               Blender.Draw.Create(0),
		'_pan_geometries':         Blender.Draw.Create(0),
		'_pan_lights':             Blender.Draw.Create(0),
		'_pan_shadows':            Blender.Draw.Create(0),
		'_pan_dof':                Blender.Draw.Create(0),
		'_pan_environment':        Blender.Draw.Create(0),
	}

def registry_save():
	global KEYREGISTER, permanents

	rdict = dict()
	for name, value in permanents.iteritems():
		# skip internal's names
		if (name[0] != '_'):
			rdict[name] = value.val

	Blender.Registry.SetKey(KEYREGISTER, rdict, True)

def registry_load():
	global KEYREGISTER, permanents

	rdict = Blender.Registry.GetKey(KEYREGISTER, True)
	if (rdict):
		for name, value in rdict.iteritems():
			if (permanents.has_key(name)):
				permanents[name] = Blender.Draw.Create(value)

# main

def main():
	global KEYREGISTER, SHADOWMAP_EXT, GSO_AMBOCCLUDE
	global GELATO, GSOINFO, MAKETX, FILENAME
	global shader_ambocclude, permanents, gelato_gui, pyg

	PYTHON_MAJOR = 2
	PYTHON_MINOR = 4

	if sys.version_info < (PYTHON_MAJOR, PYTHON_MINOR):
		raise ('Error: Python version %d.%d or greater is required\nPython version is %s' % (PYTHON_MAJOR, PYTHON_MINOR, sys.version))

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
	MAKETX  = 'maketx'  + exe

	GELATOHOME = os.getenv('GELATOHOME')

	if (GELATOHOME):
		GELATO         = os.path.join(GELATOHOME, 'bin',     GELATO)
		GSOINFO        = os.path.join(GELATOHOME, 'bin',     GSOINFO)
		GSO_AMBOCCLUDE = os.path.join(GELATOHOME, 'shaders', GSO_AMBOCCLUDE)

	# file name

	try:
		blend_file_name = Blender.Get('filename')
		(base, ext) = os.path.splitext(blend_file_name)
		if (ext.lower() == '.gz'):
			(base, ext) = os.path.splitext(base)
	except:
		base = 'gelato'

	FILENAME = base + '.pyg'

	# shader

	try:
		shader_ambocclude = shader(GSO_AMBOCCLUDE, 5000)

		shader_ambocclude['bias'] = 0.01
		shader_ambocclude['samples'] = 512
		shader_ambocclude['occlusionname'] = 'localocclusion'
	except:
		shader_ambocclude = None

	# data permanents

	registry_default()
	registry_load()
	registry_save()

	# gelato convert

	pyg = gelato_pyg()

	# GUI

	gelato_gui = cfggui()

	# start

	Blender.Draw.Register(gelato_gui.draw, gelato_gui.handle_event, gelato_gui.handle_button_event)

if __name__ == '__main__':
	try:
		import psyco
		psyco.full()
	except:
		pass

	main()

