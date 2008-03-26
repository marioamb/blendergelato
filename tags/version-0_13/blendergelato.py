#!BPY

"""
Name: 'Blender Gelato'
Blender: 242
Group: 'Render'
Tooltip: 'Render with NVIDIA Gelato(TM)'
"""

__author__ = 'Mario Ambrogetti'
__version__ = '0.13'
__url__ = ['']
__bpydoc__ = """\
Blender to NVIDIA Gelato(TM)
"""

# NVIDIA Gelato(TM) Exporter
#
# Original By: Mario Ambrogetti
# Date:        Sun, 10 Dec 2006 11:18:39 +0100
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
import sys, os, datetime, fnmatch, struct, copy
import xml.dom.minidom
from math import degrees, radians, atan2

try:
	import xml.dom.ext
	USE_XML_DOM_EXT = True
except:
	USE_XML_DOM_EXT = False

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
		return str([(self.names[idx], idx) for idx in xrange(len(self.names))])

	def has_key(self, key):
		return self.__contains__(key)

class shader(object):
	class parameter(object):
		__slots__ = ['type', 'help', 'default', 'widget', 'change', 'id']
		def __init__(self, type, value, help):
			self.type    = type
			self.help    = help
			self.default = value
			self.widget  = Blender.Draw.Create(value)
			self.change  = False
			self.id      = get_gui_id()

	__slots__ = ['literals', 'types', 'file', 'nameid', 'verbose', 'size', 'parameters', 'type', 'name']
	def __init__(self, file = None, nameid = '', verbose = 1):
		self.literals = enum_type('float', 'string', 'color', 'point', 'vector', 'normal', 'matrix')
		self.types    = enum_type('surface', 'displacement', 'volume', 'light', 'generic')

		self.file       = file
		self.nameid     = nameid
		self.verbose    = verbose
		self.size       = 210
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
			if (self.verbose > 1):
				print 'Error: null shader'
			return ''

		slist = []
		for name, par in self.parameters.iteritems():

			# skip if no change

			if (not par.change):
				continue

			type = par.type

			# float

			if (type is self.literals.float):
				try:
					slist.append('Parameter ("float %s", %s)\n' %
						(name, float(par.widget.val)))
				except ValueError:
					if (self.verbose > 1):
						print 'Error: parameter not valid "%s"' % par.widget.val
					continue

			# string

			elif (type is self.literals.string):
				slist.append('Parameter ("string %s", "%s")\n' %
					(name, par.widget.val.strip()))

			# color, point vector, normal

			elif ((type is self.literals.color) or
				(type is self.literals.point) or
				(type is self.literals.vector) or
				(type is self.literals.normal)):
					lpar = par.widget.val.strip().split(' ')
					if (len(lpar) == 3):
						slist.append('Parameter ("%s %s", (%s))\n' %
							(self.literals[type], name, ', '.join(lpar)))
					else:
						if (self.verbose > 1):
							print 'Error: parameter not valid "%s"' % par.widget.val
						continue

			# TODO matrix

			else:
				if (self.verbose > 1):
					print 'Error: unknow parameter "%s"' % name

		type = self.type

		# Shader: surface, displacement, volume

		if ((type is self.types.surface) or
			(type is self.types.displacement) or
			(type is self.types.volume)):
				slist.append('Shader ("%s", "%s")\n' % (self.types[type], self.name))

		# Light

		elif (type is self.types.light):
			slist.append('Light ("%s", "%s")\n' % (self.nameid, self.name))

		# TODO generic

		else:
			if (self.verbose > 1):
				print 'Error: unknow type shader "%s"' % self.types[type]
			return ''

		return ''.join(slist)

	def set_verbose(self, verbose):
		self.verbose = verbose

	def default(self):
		for val in self.parameters.itervalues():
			val.widget = Blender.Draw.Create(val.default)
			val.change = False

	def update(self, id):
		for val in self.parameters.itervalues():
			if (val.id == id):
				val.change = True
				return

	def gui(self, x, y, h, s):
		Blender.BGL.glColor3f(0.0, 0.0, 0.0)
		Blender.BGL.glRasterPos2i(x+2, y+h/2-4)
		txt = 'Shader type "%s" name: ' % self.types[self.type]
		Blender.Draw.Text(txt)
		Blender.BGL.glColor3f(1.0, 1.0, 0.8)
		Blender.BGL.glRasterPos2i(x+Blender.Draw.GetStringWidth(txt)+6, y+h/2-4)
		Blender.Draw.Text(self.name)
		Blender.BGL.glColor3f(1.0, 1.0, 1.0)
		y += s

		i = j = 0
		for name in sorted(self.parameters, key=str.lower, reverse=True):
			par  = self.parameters[name]
			type = par.type

			# float

			if (type is self.literals.float):
				par.widget = Blender.Draw.String(name + ': ', par.id, x + j, y,
					self.size, h, par.widget.val, 80, par.help)
				i += 1

			# string

			elif (type is self.literals.string):
				par.widget = Blender.Draw.String(name + ': ', par.id, x + j, y,
					self.size, h, par.widget.val, 128, par.help)
				i += 1

			# color, point, vector, normal

			elif ((type is self.literals.color) or
				(type is self.literals.point) or
				(type is self.literals.vector) or
				(type is self.literals.normal)):
					par.widget = Blender.Draw.String(name + ': ', par.id, x + j, y,
						self.size, h, par.widget.val, 256, par.help)
					i += 1
			else:
				if (self.verbose > 1):
					print 'Error: unknow parameter "%s"' % name
				continue

			if (i % 3):
				j += self.size + 10
			else:
				j = 0
				y += s

		if (j == 0):
			y -= s

		return y

	def parse_file(self):
		cmd='"%s" "%s"' % (GSOINFO, self.file)

		# open file

		try:
			fd = os.popen(cmd, 'r')
		except:
			if (self.verbose > 0):
				print 'Error: command "%s"' % cmd
			return

		# read first line

		line = fd.readline().strip()

		try:
			(type, name) = line.strip().split(' ')
		except ValueError:
			return

		if (not self.types.has_key(type)):
			if (self.verbose > 1):
				print 'Error: unknow shader type "%s" name "%s"' % (type, name)
			return

		# shader e name type

		self.type = self.types[type]
		self.name = name

		i = 0
		for line in fd:
			elements = line.strip().split(' ')

			if (not self.literals.has_key(elements[0])):
				if (self.verbose > 1):
					print 'Error: unknow parameter type "%s"' % elements
				continue

			lit = self.literals[elements[0]]

			par      = None
			par_name = None

			# float

			if (lit is self.literals.float):
				par_name = elements[1]
				par = self.parameter(lit, elements[2], 'float %s' % par_name)

			# string

			elif (lit is self.literals.string):
				par_name = elements[1]
				par = self.parameter(lit, elements[2][1:-1], 'string %s' % par_name)

			# color, point, vector, normal

			elif ((lit is self.literals.color) or
				(lit is self.literals.point) or
				(lit is self.literals.vector) or
				(lit is self.literals.normal)):
					if (elements[2] == '[' and elements[6] == ']'):
						val = '%s %s %s' % (elements[3], elements[4], elements[5])
					else:
						val = elements[2]

					par_name = elements[1]
					par = self.parameter(lit, val, '%s %s' % (self.literals[lit], par_name))

			# TODO matrix

			if ((par is not None) and (par_name is not None)):
				self.parameters[par_name] = par
				i += 1
			else:
				if (self.verbose > 1):
					print 'Error: unknow parameter "%s"' % elements

		fd.close()

	def toxml(self, document, root):
		if (not self.file):
			return False

		# file

		el = document.createElement('file')
		root.appendChild(el)
		el.appendChild(document.createTextNode(self.file))

		# nameid

		if (self.nameid):
			el = document.createElement('nameid')
			root.appendChild(el)
			el.appendChild(document.createTextNode(self.nameid))

		# shader's parameter

		for name, par in self.parameters.iteritems():
			if (not par.change):
				continue

			el = document.createElement('parameter')
			root.appendChild(el)
			el.setAttribute('name', name)

			el.appendChild(document.createTextNode(par.widget.val))

		return True

	def fromxml(self, document, root):

		# file

		el = root.getElementsByTagName('file')
		if (len(el) == 0):
			return False

		el[0].normalize()
		fd = el[0].firstChild.data.strip()

		# nameid

		nid = ''
		el = root.getElementsByTagName('nameid')
		if (len(el) > 0):
			el[0].normalize()
			nid = el[0].firstChild.data.strip()

		# re-init object

		self.__init__(fd, nid)

		# shader's parameter

		el = root.getElementsByTagName('parameter')
		for attr in el:
			name = attr.getAttribute('name')
			if (self.parameters.has_key(name)):
				attr.normalize()
				self.parameters[name].widget = Blender.Draw.Create(attr.firstChild.data.strip())
				self.parameters[name].change = True

		return True

class gelato_pyg(object):

	class data_geometry(object):
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

	class data_texture(object):
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
		self.SHADOWMAP_EXT = '.sm'
		self.TEXTURE_EXT   = '.tx'

		if (sys.byteorder == 'little'):
			self.BINARY_INT   = 0200
			self.BINARY_FLOAT = 0202
		else:
			self.BINARY_INT   = 0201
			self.BINARY_FLOAT = 0203

		# FIXME
		self.convert_extend = dict([
			(Blender.Texture.ExtendModes.REPEAT,   'periodic'),
			(Blender.Texture.ExtendModes.CLIP,     'black'),
			(Blender.Texture.ExtendModes.CLIPCUBE, 'mirror'),
			(Blender.Texture.ExtendModes.EXTEND,   'clamp'),
#			(Blender.Texture.ExtendModes.CHECKER,  'periodic'),
		])

	@staticmethod
	def fix_file_name(name):
		if (os.path.sep == '\\'):
			return name.replace('\\', '\\\\')
		else:
			return name

	def write_matrix(self, matrix):
		"""
		Write 16 elements of matrix.
		"""
		self.file.write('(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)\n' % (
			matrix[0][0], matrix[0][1], matrix[0][2], matrix[0][3],
			matrix[1][0], matrix[1][1], matrix[1][2], matrix[1][3],
			matrix[2][0], matrix[2][1], matrix[2][2], matrix[2][3],
			matrix[3][0], matrix[3][1], matrix[3][2], matrix[3][3]))

	def write_set_transform(self, matrix):
		self.file.write('SetTransform ')
		self.write_matrix(matrix)

	def write_append_transform(self, matrix):
		self.file.write('AppendTransform ')
		self.write_matrix(matrix)

	def write_translation(self, matrix):
		trans  = matrix.translationPart()
		self.file.write('Translate (%s, %s, %s)\n' %
			(trans.x, trans.y, trans.z))

	def write_move_scale_rotate(self, matrix):
		trans = matrix.translationPart()
		scale = matrix.scalePart()
		euler = matrix.toEuler()

		if ((trans.x != 0.0) or (trans.y != 0.0) or (trans.z != 0.0)):
			self.file.write('Translate (%s, %s, %s)\n' %
				(trans.x, trans.y, trans.z))

		self.file.write('Scale (%s, %s, %s)\n' %
			(scale.x, scale.y, -scale.z))

		if (euler.z != 0.0):
			self.file.write('Rotate (%s, 0, 0, 1)\n' %
				euler.z)

		if (euler.y != 0.0):
			self.file.write('Rotate (%s, 0, 1, 0)\n' %
				-euler.y)

		if (euler.x != 0.0):
			self.file.write('Rotate (%s, 1, 0, 0)\n' %
				-euler.x)

	def write_array(self, array, prefix = None):
		l = len(array)
		if (l == 0):
			return

		if (prefix):
			self.file.write(prefix)

		ty = type(array[0])

		if (self.enable_binary):
			if (ty is type(int())):
				self.file.write(struct.pack('=BL', self.BINARY_INT, l))
				for i in array:
					self.file.write(struct.pack('=i', i))
			elif (ty is type(float())):
				self.file.write(struct.pack('=BL', self.BINARY_FLOAT, l))
				for f in array:
					try:
						s = struct.pack('=f', f)
					except:
						s = struct.pack('=f', 0.0)
					self.file.write(s)
		else:
			if (ty is type(int())):
				self.file.write('(%s' % array[0])
				for i in xrange(1, l):
					self.file.write(',%s' % array[i])
				self.file.write(')')
			elif (ty is type(float())):
				self.file.write('(%s' % round(array[0], self.PRECISION))
				for i in xrange(1, l):
					self.file.write(',%s' % round(array[i], self.PRECISION))
				self.file.write(')')

	def output_filename(self, frame = None):
		if (frame is None):
			if (self.passes_on_len == 1):
				if (self.pass_ao):
					return self.filename_ao
				return self.filename
			else:
				if (self.pass_beauty):
					return self.filename_beauty
				elif (self.pass_shadows):
					return self.filename_shadows
				elif (self.pass_ao):
					return self.filename_ao
		else:
			if (self.passes_on_len == 1):
				if (self.pass_ao):
					return self.filename_ao_mask % frame
				return self.filename_mask % frame
			else:
				if (self.pass_beauty):
					return self.filename_beauty_mask % frame
				elif (self.pass_shadows):
					return self.filename_shadows_mask % frame
				elif (self.pass_ao):
					return self.filename_ao_mask % frame

	@staticmethod
	def instance_name(name, instance):
		if (instance):
			return '__' + name + '-' + str(instance) + '__'
		else:
			return name

	@staticmethod
	def camera_shadows_name(name, instance):
		if (instance):
			return '__' + name + '-shadows-' + str(instance) + '__'
		else:
			return '__' + name + '-shadows' + '__'

	def file_shadows_name(self, name, instance, frame):
		if ((instance is None) and (frame is None)):
			return os.path.join(self.directory, name + self.SHADOWMAP_EXT)
		elif ((instance is not None) and (frame is None)):
			return os.path.join(self.directory, name + '-' + str(instance) + self.SHADOWMAP_EXT)
		elif ((instance is None) and (frame is not None)):
			return os.path.join(self.directory, name + '.' + str(frame) + self.SHADOWMAP_EXT)
		else:
			return os.path.join(self.directory, name + '-' + str(instance) + '.' + str(frame) + self.SHADOWMAP_EXT)

	def write_shadow_name(self, name = None, instance = None, frame = None):
		shadowname = None
		if (name and (self.shadow_maps or self.shadow_woo)):
			shadowname = self.file_shadows_name(name, instance, frame)
		elif (self.shadow_ray_traced):
			shadowname = 'shadows'

		if (shadowname):
			self.file.write('Parameter ("string shadowname", "%s")\n' %
				shadowname)

	def write_ray_traced(self):
		self.file.write('Attribute ("int ray:maxdepth", %d)\n' %
			self.ray_traced_max_depth)

		if (self.shadow_ray_traced):
			self.file.write('Attribute ("float shadow:bias", %s)\n' %
				round(self.ray_traced_shadow_bias, self.PRECISION))

		self.file.write('Attribute ("string geometryset", "+reflection")\n')
		self.file.write('Attribute ("string geometryset", "+refraction")\n')

	def write_shadow_ray_traced(self):
		self.file.write('\nAttribute ("string geometryset", "+shadows")\n')

	def write_key_fill_rim(self):
		self.file.write('\nInput ("cameralights.pyg")\n')

	def write_ambient_occlusion_pass1(self):
		global materials_link

		shader_ambocclude = materials_link[0]['ambient_occlusion']

		if (shader_ambocclude):
			self.file.write('\nAttribute ("string geometryset", "+%s")\n' %
				shader_ambocclude['occlusionname'])

			self.file.write(str(shader_ambocclude))
		else:
			self.file.write('\nAttribute ("string geometryset", "+localocclusion")\n')
			self.file.write('Shader ("surface", "ambocclude", "string occlusionname", "localocclusion")\n')

	def write_ambient_occlusion_pass2(self, frame):
		global materials_link

		if (not self.format):
			raise GelatoError, 'No file format for ambient occlusion'

		if (frame is None):
			output = self.output_ao_tx
		else:
			output = self.output_ao_tx_mask % frame

		self.file.write('\n')

		shader_envlight = materials_link[0]['environment_light']
		if (shader_envlight):
			shader_envlight['occlusionmap'] = output

			shader_ambocclude = materials_link[0]['ambient_occlusion']
			if (shader_ambocclude):
				shader_envlight['occlusionname'] = shader_ambocclude['occlusionname']

			self.file.write(str(shader_envlight))
		else:
			self.file.write('Light ("__envlight_pass2__", "envlight", "string occlusionmap", "%s" )\n' %
				output)

	def write_indirect_light(self):
		global materials_link

		self.file.write('\nAttribute ("string geometryset", "+indirect")\n')
		self.file.write('Attribute ("int indirect:minsamples", %d)\n' %
			self.indirect_minsamples)

		shader_indirectlight = materials_link[0]['indirect_light']
		if (shader_indirectlight):
			self.file.write(str(shader_indirectlight))
		else:
			self.file.write('Light ("__indirectlight__", "indirectlight")\n')

	def write_background_color(self):
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

	def write_ambientlight(self):
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

	def write_pointlight(self, obj, lamp, matrix, instance, frame):
		name = obj.name

		self.file.write('\nPushTransform ()\n')

		self.write_translation(matrix)
		self.write_shadow_name(name, instance, frame)

		self.file.write('Light ("%s", "pointlight", '
				'"float falloff", 2.0, '
				'"float intensity", %s, '
				'"color lightcolor", (%s, %s, %s))\n' % (
			self.instance_name(name, instance),
			lamp.getEnergy() * self.lights_factor,
			lamp.R, lamp.G, lamp.B))

		self.file.write('PopTransform ()\n')

	def write_distantlight(self, obj, lamp, matrix, instance, frame):
		name = obj.name

		self.file.write('\nPushTransform ()\n')

		self.write_move_scale_rotate(matrix)
		self.write_shadow_name(name, instance, frame)

		self.file.write('Light ("%s", "distantlight", '
				'"float intensity", %s, '
				'"color lightcolor", (%s, %s, %s), '
				'"float shadowsamples", %s, '
				'"float shadowbias", %s)\n' % (
			self.instance_name(name, instance),
			lamp.getEnergy() * self.lights_factor,
			lamp.R, lamp.G, lamp.B,
			float(lamp.samples),
			lamp.bias * self.SCALEBIAS))

		self.file.write('PopTransform ()\n')

	def write_spotlight(self, obj, lamp, matrix, instance, frame):
		name = obj.name

		self.file.write('\nPushTransform ()\n')

		self.write_move_scale_rotate(matrix)
		self.write_shadow_name(name, instance, frame)

		self.file.write('Light ("%s", "spotlight", '
				'"float falloff", 2.0, '
				'"float intensity", %s, '
				'"color lightcolor", (%s, %s, %s), '
				'"float coneangle", %s, '
				'"float conedeltaangle", %s, '
				'"float shadowsamples", %s, '
				'"float shadowbias", %s)\n' % (
			self.instance_name(name, instance),
			lamp.getEnergy() * self.lights_factor,
			lamp.R, lamp.G, lamp.B,
			radians(lamp.spotSize / 2.0),
			radians(lamp.spotBlend * lamp.spotSize / 4.0),
			float(lamp.samples),
			lamp.bias * self.SCALEBIAS))

		self.file.write('PopTransform ()\n')

	def write_device(self, output_name, driver, data, camera_name):
		self.file.write('\n')

		if (driver != 'null'):

			self.file.write('Parameter ("string filter", "%s")\n' %
				self.filter)

			self.file.write('Parameter ("float[2] filterwidth", (%s, %s))\n' %
				(round(self.filterwidth_x, self.PRECISION), round(self.filterwidth_y, self.PRECISION)))

			self.file.write('Parameter ("float gain", %s)\n' %
				round(self.gain, self.PRECISION))

			self.file.write('Parameter ("float gamma", %s)\n' %
				round(self.gamma, self.PRECISION))

			if (driver != 'iv'):
				if (self.compression):
					self.file.write('Parameter ("string compression", "%s")\n' %
						self.compression)

			if (driver != 'OpenEXR'):
				self.file.write('Parameter ("float dither", %s)\n' %
					self.dither)

				self.file.write('Parameter ("int[4] quantize", (%s, %s, %s, %s))\n' % (
					int(self.quantize_zero),
					int(self.quantize_one),
					int(self.quantize_min),
					int(self.quantize_max)))

		self.file.write('Output ("%s", "%s", "%s", "%s")\n' %
			(output_name, driver, data, camera_name))

	def write_camera(self, obj):
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

		self.write_move_scale_rotate(matrix)

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

		if (self.enable_dof):
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

	def write_camera_light(self, obj, lamp, name, matrix, instance, frame):
		self.file.write('\nPushTransform ()\n')

		self.write_move_scale_rotate(matrix)

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

		if (self.enable_dynamic):
			self.file.write('Parameter ("int dynamic", 1)\n')

		shadow_data = 'z'
		if (self.shadow_woo):
			shadow_data = 'avgz'

		self.file.write('Output ("%s", '
				'"shadow", "%s", "%s", '
				'"string compression", "%s", '
				'"string filter", "min", '
				'"float[2] filterwidth", (1.0, 1.0), '
				'"float dither", 0.0, '
				'"int[4] quantize", (0, 0, 0, 0))\n' % (
			self.file_shadows_name(name, instance, frame),
			shadow_data,
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
				self.write_camera_light(obj, lamp, name, mat, instance, frame)

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
			self.write_pointlight(obj, lamp, mat, instance, frame)
		elif (ltype is Blender.Lamp.Types.Sun):
			self.write_distantlight(obj, lamp, mat, instance, frame)
		elif (ltype is Blender.Lamp.Types.Spot):
			self.write_spotlight(obj, lamp, mat, instance, frame)

	def write_mesh(self, name, transform, single_sided, interpolation, nverts,\
			verts, points, normals = [], vertexcolor = [], holes = []):

		self.write_set_transform(transform)

		if (single_sided):
			self.file.write('Attribute ("int twosided", 0)\n')

		self.file.write('Mesh ("%s"' % interpolation)

		self.write_array(nverts,',')
		self.write_array(verts, ',')
		self.write_array(points, ',"vertex point P",')
		self.write_array(normals, ',"vertex normal N",')
		self.write_array(vertexcolor, ',"vertex color C",')
		self.write_array(holes, ',"int[%d] holes",' % len(holes))

		self.file.write(')\n')

	def write_st(self, s, t):
		if (s):
			self.file.write('Parameter (')
			self.write_array(s, '"vertex float s",')
			self.file.write(')\n')
		if (t):
			self.file.write('Parameter (')
			self.write_array(t, '"vertex float t",')
			self.file.write(')\n')

	def mesh(self, obj, matrix = None, instance = None, frame = None):
		global materials_link

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
		if (not (self.all_double_sided or (mesh.mode & Blender.NMesh.Modes.TWOSIDED))):
			single_sided = True

		# vertex colors

		vtcolor = mesh.hasVertexColours()

		# face UV

		faceuv = mesh.hasFaceUV()

		# get property catmull_clark

		catmull_clark = get_property_bool(obj, 'gelato:catmull_clark')

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
		db_geometry = {}

		i = 0
		for face in mesh.faces:
			if (face.smooth):
				smooth = True

			l = len(face.v)
			nverts.append(l)
			mat_idx = face.materialIndex

			if (db_geometry.has_key(mat_idx)):
				db_geometry[mat_idx].append(i, l)
			else:
				db_geometry[mat_idx] = self.data_geometry(i, l)

			for vert in face.v:
				verts.append(vert.index)
				db_geometry[mat_idx].append_vert(vert.index)

			if (vtcolor):
				for j in xrange(len(face.v)):
					c = face.col[j]
					nlist_col[face.v[j].index] = [c.r, c.g, c.b]
			i += 1

		# points

		points = []
		nlist_nor = []
		for vert in mesh.verts:
			nlist_nor.append(vert.no)
			points.extend([vert.co.x, vert.co.y, vert.co.z])

		# normals

		normals = []
		if (smooth and (not catmull_clark)):
			for face in mesh.faces:
				if (face.smooth):
					continue
				for vert in face.v:
					nlist_nor[vert.index] = face.no

			for nor in nlist_nor:
				normals.extend([nor[0], nor[1], nor[2]])

		# vertex color

		vertexcolor = []
		if (vtcolor):
			for c in nlist_col:
				try:
					vertexcolor.extend([c[0]/255.0, c[1]/255.0, c[2]/255.0])
				except:
					vertexcolor.extend([0.0, 0.0, 0.0])

		self.file.write('\nPushAttributes ()\n')

		self.file.write('Attribute ("string name", "%s")\n' %
			self.instance_name(name, instance))

		if ((not self.pass_ao) and (not self.pass_shadows) and mesh.materials):

			# materials

			multiple_mat = len(mesh.materials) > 1
			if (multiple_mat and catmull_clark):
				set_mat = set(range(nfaces))

			for i, geo in db_geometry.iteritems():

				try:
					mat = mesh.materials[i]
				except:
					continue

				if (not mat):
					continue

				flags = mat.getMode()

				self.file.write('PushAttributes ()\n')

				# vertex color

				if (not flags & Blender.Material.Modes.VCOL_PAINT):
					vertexcolor = []

				# multiple materials on a single mesh

				if (multiple_mat and catmull_clark):
					holes = list(set_mat - set(geo.materials))
				else:
					holes = []

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
							filename = Blender.sys.expandpath(image.getFilename())
							if (mtex.mapto is Blender.Texture.MapTo.COL):
								textures_color.append(self.data_texture(mtex.tex.getName(),
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
							for j in xrange(len(face.v)):
								i = face.v[j].index
								uv_cor = face.uv[j]
								tex_s[i] = round(uv_cor[0], self.PRECISION)
								tex_t[i] = round(1.0 - uv_cor[1], self.PRECISION)

				# shader surface (FIXME)

				if (self.enable_textures and textures_color):
					self.file.write('ShaderGroupBegin ()\n')

					for ftex in textures_color:
						if (self.verbose > 0):
							self.file.write('## Texture: "%s"\n' % ftex.name)
						self.file.write('Shader ("surface", "pretexture", "string texturename", "%s", "string wrap", "%s")\n' %
							(ftex.file, self.convert_extend[ftex.extend]))

				if (self.verbose > 0):
					self.file.write('## Material: "%s"\n' % mat.name)

				if (self.enable_shaders and not self.enable_debug_shaders):

					if (not flags & Blender.Material.Modes.SHADELESS):
						if (materials_link[1].has_key(mat.name) and
							(materials_link[1][mat.name] is not None)):
								self.file.write(str(materials_link[1][mat.name]))
						else:
							self.file.write('Shader ("surface", "plastic")\n')

				if (self.enable_textures and textures_color):
					self.file.write('ShaderGroupEnd ()\n')

				# FIXME MA_ONLYCAST ???
				if (flags & 0x2000):
					self.file.write('Attribute ("string geometryset", "-camera")\n')

				if (not flags & Blender.Material.Modes.TRACEABLE):
					self.file.write('Attribute ("string geometryset", "-shadows")\n')

				if (flags & Blender.Material.Modes.TRANSPSHADOW):
					self.file.write('Attribute ("int ray:opaqueshadows", 0)\n')

				# textures UV coordinates

				if (self.enable_textures and use_uv):
					self.write_st(tex_s, tex_t)

				# geometry

				if (catmull_clark):
					self.write_mesh(name, transform, single_sided, interpolation, nverts,
						verts,     points, normals, vertexcolor, holes)
				else:
					self.write_mesh(name, transform, single_sided, interpolation, geo.nverts,
						geo.verts, points, normals, vertexcolor)

				self.file.write('PopAttributes ()\n')
		else:
			self.write_mesh(name, transform, single_sided, interpolation, nverts, verts, points, normals)

		self.file.write('PopAttributes ()\n')

	def visible(self, obj):
		if ((obj.users > 1) and ((set(obj.layers) & self.viewlayer) == set())):
			if (self.verbose > 1):
				print 'Info: Object "%s" invisible' % obj.name
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
		if ((frame is not None) and nframe):
			bar += ' (%d/%d)' % (frame, nframe)

		self.write_ambientlight()

		Blender.Window.DrawProgressBar(0.0, bar)
		n = float(len(self.objects))
		i = 0
		for obj in self.objects:
			self.build(obj, 'light', frame)
			Blender.Window.DrawProgressBar(i / n, bar)
			i += 1

	def geometries(self, frame, nframe):
		bar = 'Geometries ...'
		if ((frame is not None) and (nframe is not None)):
			bar += ' (%d/%d)' % (frame, nframe)
		Blender.Window.DrawProgressBar(0.0, bar)
		n = float(len(self.objects))
		i = 0
		for obj in self.objects:
			if (self.verbose > 1):
				print 'Info: Object "%s" type "%s"' % (obj.name, obj.getType())
			self.build(obj, 'mesh', frame)
			Blender.Window.DrawProgressBar(i / n, bar)
			i += 1

	def write_head(self, frame, nframe):
		"""
		Write pyg header.
		"""

		curcam  = self.scene.getCurrentCamera()

		try:
			self.camera_name = curcam.name
		except:
			raise GelatoError, 'No camera present'

		scale  = self.context.getRenderWinSize() / 100.0

		self.file.write('## Exported by Blender Gelato %s\n##\n' % __version__)

		try:
			self.file.write(datetime.datetime.today().strftime('## Date: %F %T\n'))
		except:
			pass

		if (self.pass_beauty):
			pass_render = 'Beauty'
		elif (self.pass_shadows):
			pass_render = 'Shadows'
		elif (self.pass_ao):
			pass_render = 'Ambient Occlusion'
		else:
			pass_render = 'Unknow'

		self.file.write('## Pass: %s\n' % pass_render)

		if ((frame is not None) and (nframe is not None)):
			self.file.write('## Frame: %d/%d\n' %
				(frame, nframe))


		self.file.write('\nAttribute ("int verbosity", %d)\n' %
			self.verbose)

		if (self.path_shader):
			self.file.write('Attribute ("string path:shader", "%s")\n' %
				self.path_shader)

		if (self.path_texture):
			self.file.write('Attribute ("string path:texture", "%s")\n' %
				self.path_texture)

		if (self.path_inputs):
			self.file.write('Attribute ("string path:input", "%s")\n' %
				self.path_inputs)

		if (self.path_imageio):
			self.file.write('Attribute ("string path:imageio", "%s")\n' %
				self.path_imageio)

		if (self.path_generator):
			self.file.write('Attribute ("string path:generator", "%s")\n' %
				self.path_generator)

		self.file.write('Attribute ("int[2] resolution", (%d, %d))\n' %
			(int(self.sizex * scale), int(self.sizey * scale)))

		if (self.context.borderRender):
			self.file.write('Attribute ("float[4] crop", (%s, %s, %s, %s))\n' % (
				self.context.border[0],
				self.context.border[2],
				1.0 - self.context.border[3],
				1.0 - self.context.border[1]))

		self.file.write('Attribute ("int[2] spatialquality", (%d, %d))\n' %
			(self.antialiasing_x , self.antialiasing_y))

		if (self.enable_preview):
			self.file.write('Attribute ("float preview", %s)\n' %
				round(self.preview_quality, self.PRECISION))

		if (self.enable_shaders):
			self.file.write('Attribute ("float shadingquality", %s)\n' %
				round(self.shadingquality, self.PRECISION))

		self.file.write('Attribute ("string bucketorder", "%s")\n' %
			self.bucketorder)

		self.file.write('Attribute ("string orientation", "outside")\n')
		self.file.write('Attribute ("int twosided", 1)\n')

		if (self.enable_textures):
			self.file.write('Attribute ("int texture:automipmap", %d)\n' %
				self.enable_automipmap)

		if (self.units_length):
			self.file.write('Attribute ("string units:length", "%s")\n' %
				self.units_length)

			self.file.write('Attribute ("float units:lengthscale", %s)\n' %
				round(float(self.units_lengthscale), self.PRECISION))

		self.file.write('Attribute ("int ray:opaqueshadows", 1)\n')

		if (self.enable_ray_traced):
				self.write_ray_traced()

		if (self.pass_shadows):
			self.write_device(self.title, 'null', self.data_color, self.camera_name)
		else:
			if (self.enable_viewer):
				self.write_device(self.title, 'iv', self.data_color, self.camera_name)

			if (self.pass_ao):
				if (self.format):
					if (frame is None):
						output = self.output_ao
					else:
						output = self.output_ao_mask % frame

					self.write_device(output, self.format, self.data_color, self.camera_name)
				elif (self.passes_on_len > 1):
					raise GelatoError, 'No file format for ambient occlusion'
			else:
				if (self.format):
					if (frame is None):
						outfile_color = self.output_color
						outfile_z     = self.output_z
					else:
						outfile_color = self.output_color_mask % frame
						outfile_z     = self.output_z_mask     % frame

					self.write_device(outfile_color, self.format, self.data_color, self.camera_name)

					if (self.data_z):
						self.write_device(outfile_z, self.format, self.data_z, self.camera_name)

		self.write_camera(curcam)

		if (self.pass_shadows or self.enable_dynamic):
			self.cameras_shadows(frame)

		self.file.write('\nWorld ()\n')

	def write_tail(self):
		"""
		Write the final part of pyg file.
		"""
		self.file.write('\nRender ("%s")\n\n'
			% self.camera_name)

	def sequence(self, frame, nframe):
		fileout = self.output_filename(frame)

		try:
			self.file = open(fileout, 'w')
		except IOError:
			raise GelatoError, 'Cannot write file "%s"' % fileout

		self.write_head(frame, nframe)

		if (self.pass_ao):
			self.write_ambient_occlusion_pass1()

		if (self.pass_beauty):
			if (self.enable_sky):
				self.write_background_color()

			if (self.enable_ao):
				self.write_ambient_occlusion_pass2(frame)

			if (self.enable_indirect_light):
				self.write_indirect_light()

			if (self.enable_key_fill_rim):
				self.write_key_fill_rim()

			if (self.enable_lights):
				self.lights(frame, nframe)

			if (self.shadow_ray_traced):
				self.write_shadow_ray_traced()

		if (self.enable_debug_shaders and gelato_gui.debug_shader is not None):
			self.file.write('\n')
			self.file.write(str(gelato_gui.debug_shader))

		self.geometries(frame, nframe)

		self.write_tail()

		self.file.close()

	def sequence_pass(self, frame = None, nframe = None):
		self.pass_beauty  = False
		self.pass_shadows = False
		self.pass_ao      = False

		if (self.passes_on_len == 1):
			if ('beauty' in self.passes_on):
				self.pass_beauty = True
			elif ('shadows' in self.passes_on):
				self.pass_shadows = True
			elif ('ambient_occlusion' in self.passes_on):
				self.pass_ao = True

			self.sequence(frame, nframe)
		else:
			if ('shadows' in self.passes_on):
				self.pass_shadows = True
				self.sequence(frame, nframe)
				self.pass_shadows = False

			if ('ambient_occlusion' in self.passes_on):
				self.pass_ao = True
				self.sequence(frame, nframe)
				self.pass_ao = False

			if ('beauty' in self.passes_on):
				self.pass_beauty = True
				self.sequence(frame, nframe)
				self.pass_beauty = False

	def setup(self):
		global permanents, gelato_gui

		for name, value in permanents.iteritems():
			if (name[0] == '_'):
				setattr(self, name[1:], value.val)
			else:
				setattr(self, name, value.val)

		# compression

		comp = gelato_gui.menu_format.convert(self.format)[2]
		if (comp):
			self.compression = comp.convert(self.compression)
		else:
			self.compression = None

		self.compression_shadow = gelato_gui.menu_compression_tiff.convert(self.compression_shadow)

		# output file name image

		(self.format, self.suffix) = gelato_gui.menu_format.convert(self.format)[0:2]

		# output data

		(self.data_color, self.data_z) = gelato_gui.menu_data.convert(self.data)

		# bucketorder

		self.bucketorder = gelato_gui.menu_bucketorder.convert(self.bucketorder)

		# pixel filter

		self.filter = gelato_gui.menu_filter2.convert(self.filter)

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

		# pass

		beauty_on  = False
		shadows_on = False
		ao_on      = False

		self.passes_on = set()
		if (self.pass_beauty):
			self.passes_on |= set(['beauty'])
			beauty_on = True
		if (self.pass_shadows):
			self.passes_on |= set(['shadows'])
			shadows_on = True
		if (self.pass_ao):
			self.passes_on |= set(['ambient_occlusion'])
			ao_on = True

		self.passes_on_len = len(self.passes_on)
		if (self.passes_on_len == 0):
			raise GelatoError, 'No pass select'

		staframe = Blender.Get('staframe')
		curframe = Blender.Get('curframe')
		endframe = Blender.Get('endframe')

		mask = '.%%0%dd' % len('%d' % endframe)

		# file names, title and directoty

		(base, ext) = os.path.splitext(self.filename)

		self.filename_mask = base + mask + ext

		self.filename_beauty      = base + '_beauty'        + ext
		self.filename_beauty_mask = base + '_beauty' + mask + ext

		self.filename_shadows      = base + '_shadows'        + ext
		self.filename_shadows_mask = base + '_shadows' + mask + ext

		self.filename_ao      = base + '_ao'        + ext
		self.filename_ao_mask = base + '_ao' + mask + ext

		self.title = os.path.basename(base)

		if (self.suffix):
			self.output_color      = base +        self.suffix
			self.output_color_mask = base + mask + self.suffix

			self.output_z      = base + '_z' +        self.suffix
			self.output_z_mask = base + '_z' + mask + self.suffix

			self.output_ao      = base + '_ao' +        self.suffix
			self.output_ao_mask = base + '_ao' + mask + self.suffix

			self.output_ao_tx      = base + '_ao' +        self.TEXTURE_EXT
			self.output_ao_tx_mask = base + '_ao' + mask + self.TEXTURE_EXT

		(directory, file) = os.path.split(self.filename)
		self.directory = directory

		if (self.verbose > 0):
			timestart = Blender.sys.time()
			print 'Info: starting Gelato pyg export to "%s"' % self.filename

		# shaders

		for mat in materials_link:
			for sd in mat.itervalues():
				sd.set_verbose(self.verbose)

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

			nframe = endframe - staframe + 1

			if (nframe <= 0):
				raise GelatoError, 'Invalid frame length'

			# all frames

			try:
				for f in xrange(staframe, endframe + 1):
					Blender.Set('curframe', f)

					if (self.verbose > 1):
						print 'Info: exporting frame %d' % f

					self.sequence_pass(f, nframe)
			except:
				Blender.Set('curframe', curframe)
				Blender.Window.DrawProgressBar(1.0, '')
				raise

			Blender.Set('curframe', curframe)

			# command file

			try:
				self.file = open(self.filename, 'w')
			except IOError:
				raise GelatoError, 'Cannot write file "%s"' % self.filename

			if ((self.passes_on_len == 1) and (not ao_on)):
				for f in xrange(staframe, endframe + 1):
					self.file.write('Command ("system", "string[2] argv", ("%s", "%s"))\n' %
						(GELATO, self.filename_mask % f))
			else:
				for f in xrange(staframe, endframe + 1):
					if (shadows_on):
						self.file.write('Command ("system", "string[2] argv", ("%s", "%s"))\n' %
							(GELATO, self.filename_shadows_mask % f))

					if (ao_on):
						self.file.write('Command ("system", "string[2] argv", ("%s", "%s"))\n' %
							(GELATO, self.filename_ao_mask % f))
						self.file.write('Command ("system", "string[3] argv", ("%s", "%s", "%s"))\n' %
							(MAKETX, self.output_ao_mask % f, self.output_ao_tx_mask % f))

					if (beauty_on):
						self.file.write('Command ("system", "string[2] argv", ("%s", "%s"))\n' %
							(GELATO, self.filename_beauty_mask % f))
			self.file.close()

		else:
			self.sequence_pass()

			if ((self.passes_on_len > 1) or ao_on):

				# command file

				try:
					self.file = open(self.filename, 'w')
				except IOError:
					raise GelatoError, 'Cannot write file "%s"' % self.filename

				if (shadows_on):
					self.file.write('Command ("system", "string[2] argv", ("%s", "%s"))\n' %
						(GELATO, self.filename_shadows))

				if (ao_on):
					self.file.write('Command ("system", "string[2] argv", ("%s", "%s"))\n' %
						(GELATO, self.filename_ao))
					self.file.write('Command ("system", "string[3] argv", ("%s", "%s", "%s"))\n' %
						(MAKETX, self.output_ao, self.output_ao_tx))

				if (beauty_on):
					self.file.write('Command ("system", "string[2] argv", ("%s", "%s"))\n' %
						(GELATO, self.filename_beauty))

				self.file.close()

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
			slist = []

			if (title):
				slist.append('%s %%t' % title)

			i = 0
			self.store = {}
			self.food  = {}
			for (name, data) in options:
				slist.append('|%s %%x%d' % (name, i))
				self.store[i] = data
				self.food[name] = i
				i += 1

			self.cookie = ''.join(slist)

		def convert(self, id):
			return self.store.get(id)

		def val(self, name):
			return self.food.get(name)

	def __init__(self):
		self.x0 = 10	# start cursor x
		self.y0 = 10	# start cursor y
		self.h  = 22	# height button
		self.s  = 30	# step y
		self.m  = 10	# margin button

		self.panels = [
			self.panel('Output',         '_panel_output', self.panel_output, 'Panel output data'),
			self.panel('Geometries',     '_panel_geometries', self.panel_geometries, 'Panel geometries'),
			self.panel('Lights',         '_panel_lights', self.panel_lights, 'Panel lights'),
			self.panel('Shadows',        '_panel_shadows', self.panel_shadows, 'Panel select shadows type'),
			self.panel('Textures',       '_panel_textures', self.panel_textures, 'Panel textures'),
			self.panel('Shaders',        '_panel_shaders', self.panel_shaders, 'Panel shaders'),
			self.panel('Pass',           '_panel_pass', self.panel_pass, 'Panel select pass'),
			self.panel('AO',             '_panel_ambient_occlusion', self.panel_ambient_occlusion, 'Panel ambient occlusion'),
			self.panel('Ray traced',     '_panel_ray_traced', self.panel_ray_traced, 'Panel ray traced'),
			self.panel('Indirect Light', '_panel_indirectlight', self.panel_indirect_light, 'Panel Indirect Light'),
			self.panel('Depth of Field', '_panel_dof', self.panel_dof, 'Panel Depth of Field'),
			self.panel('Environment',    '_panel_environment', self.panel_environment, 'Panel environment'),
		]

		# ambient occlusion shader

		try:
			fd = search_file('ambocclude.gso', permanents['path_shader'].val)
			if (fd):
				sd = shader(fd)
				sd['occlusionname'] = 'localocclusion'
		except:
			sd = None

		materials_link[0]['ambient_occlusion'] = sd

		# envlight shader

		try:
			fd = search_file('envlight.gso', permanents['path_shader'].val)
			if (fd):
				sd = shader(fd, '__envlight_pass2__')
				sd['occlusionmap'] = '$FILE_PASS1'
		except:
			sd = None

		materials_link[0]['environment_light'] = sd

		# indirect light shader

		try:
			fd = search_file('indirectlight.gso', permanents['path_shader'].val)
			if (fd):
				sd = shader(fd, '__indirectlight__')
		except:
			sd = None

		materials_link[0]['indirect_light'] = sd

		# debug shaders

		self.debug_shader      = None
		self.menu_debug_shader = None

		list_sd = []
		for name in ['shownormals', 'showfacing', 'showst', 'showuv', 'showdudv', 'showgrids', 'raygoggles']:
			fd = search_file(name + '.gso', permanents['path_shader'].val)
			if (fd):
				try:
					sd = shader(fd)

					# only surface shader

					if (sd.type is sd.types.surface):
						list_sd.append([name, sd])
				except:
					continue

		if (len(list_sd) > 0):
			self.menu_debug_shader = self.bake_menu('Debug shaders', list_sd)

		# avanable shaders

		self.menu_shader   = None
		self.menu_material = None

		self.available_shader = find_files(permanents['path_shader'].val, '*.gso')
		if (self.available_shader):
			list_sd = []
			for name in sorted(self.available_shader):
				fd = os.path.join(self.available_shader[name], name)
				try:
					sd = shader(fd)

					# only surface shader

					if (sd.type is sd.types.surface):
						list_sd.append([name[:-4], sd])
				except:
					continue

			if (len(list_sd) > 0):
				self.menu_shader = self.bake_menu('Shaders', list_sd)

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
			['TARGA',   ['targa',   '.tga',  None, '']],
			['JPEG',    ['jpg',     '.jpg',  None, '']],
			['PNG',     ['png',     '.png',  None, '']],
			['PPM',     ['ppm',     '.ppm',  None, '']],
			['SGI',     ['DevIL',   '.sgi',  None, '']],
			['BMP',     ['DevIL',   '.bmp',  None, '']],
			['PCX',     ['DevIL',   '.pcx',  None, '']],
			['DDS',     ['DevIL',   '.dds',  None, '']],
			['RAW',     ['DevIL',   '.raw',  None, '']],
			['IFF',     ['iff',     '.iff',  None, '']],
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

		# units

		self.menu_units = self.bake_menu('Units', [
			['None',       None],
			['Millimeter', 'mm'],
			['Centimeter', 'cm'],
			['Meter',      'm'],
			['Kilometer',  'km'],
			['Inch',       'in'],
			['Foot',       'ft'],
			['Mile',       'mi'],
		])

		self.home()
		self.reset_id()

	def home(self):
		self.x = self.x0
		self.y = self.y0

	def inc_x(self, i = 0):
		self.x += i

	def inc_y(self, i = 0):
		self.y += i

	def line_feed(self, gap = True):
		self.x = self.x0
		if (gap):
			self.inc_y(self.s)
		else:
			self.inc_y(self.h)

	def blank(self, x = 0):
		self.inc_x(x + self.m)

	def reset_id(self):
		self.id_buttons = dict()

	def get_id(self, func = None):
		id = get_gui_id()
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
		if (sep is None):
			self.inc_x(size + self.m)
		else:
			self.inc_x(size + sep)
		return id

	def draw_number(self, s, size, min, max, name, func = None, help = '', sep = None):
		id = self.get_id(func)
		permanents[name] = Blender.Draw.Number(s, id, self.x, self.y, size, self.h,
			permanents[name].val, min, max, help)
		if (sep is None):
			self.inc_x(size + self.m)
		else:
			self.inc_x(size + sep)
		return id

	def draw_slider(self, s, size, min, max, name, func = None, help = '', sep = None):
		id = self.get_id(func)
		permanents[name] = Blender.Draw.Slider(s, id, self.x, self.y, size, self.h,
			permanents[name].val, min, max, 0, help)
		if (sep is None):
			self.inc_x(size + self.m)
		else:
			self.inc_x(size + sep)
		return id

	def draw_button(self, s, size, func = None, help = '', sep = None):
		id = self.get_id(func)
		Blender.Draw.PushButton(s, id, self.x, self.y, size, self.h, help)
		if (sep is None):
			self.inc_x(size + self.m)
		else:
			self.inc_x(size + sep)
		return id

	def draw_toggle(self, s, size, name, func = None, help = '', sep = None):
		id = self.get_id(func)
		permanents[name] = Blender.Draw.Toggle(s, id, self.x, self.y, size, self.h,
			permanents[name].val, help)
		if (sep is None):
			self.inc_x(size + self.m)
		else:
			self.inc_x(size + sep)
		return id

	def draw_menu(self, bake, size, name, func = None, help = '', sep = None):
		id = self.get_id(func)
		permanents[name] = Blender.Draw.Menu(bake.cookie, id, self.x, self.y, size, self.h,
			permanents[name].val, help)
		if (sep is None):
			self.inc_x(size + self.m)
		else:
			self.inc_x(size + sep)
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
				xml_save()
				Blender.Draw.Exit()

	def handle_button_event(self, evt):
		global materials_link

		if (self.id_buttons.has_key(evt)):
			func = self.id_buttons[evt]
			if (func):
				func(evt)

		if (permanents['format'].val == self.val_format_null):
			permanents['enable_viewer'].val = 1

		if (permanents['enable_dynamic'].val or permanents['shadow_ray_traced'].val):
			permanents['pass_shadows'].val = 0

		if (not permanents['enable_ao'].val):
			permanents['pass_ao'].val = 0

		if (not (permanents['pass_beauty'].val or
			permanents['pass_shadows'].val or
			permanents['pass_ao'].val)):
				permanents['pass_beauty'].val = 1

		if (permanents['data'].val < self.val_data_z):
			if (permanents['filter'].val >= self.val_filter_min):
				permanents['filter'].val = 0 # Gaussian

		for sd in materials_link[0].itervalues():
			sd.update(evt)

		if (self.menu_material):
			material_name = self.menu_material.convert(permanents['_select_material'].val)
			if (materials_link[1].has_key(material_name) and (materials_link[1][material_name] is not None)):
				materials_link[1][material_name].update(evt)

		if ((permanents['_enable_debug_shaders'].val) and (self.debug_shader is not None)):
			self.debug_shader.update(evt)

		xml_save()
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
		global GELATO, permanents

		try:
			pyg.export(Blender.Scene.GetCurrent())
			if (os.path.isfile(permanents['filename'].val)):
				os.system('"%s" "%s"&' % (GELATO, permanents['filename'].val))
		except GelatoError, strerror:
			Blender.Draw.PupMenu('Error%t|"' + str(strerror) + '"')

	def cb_link(self, id):
		global permanents, materials_link

		material_name = self.menu_material.convert(permanents['_select_material'].val)
		sd = self.menu_shader.convert(permanents['_select_shader'].val)

		if (sd is not None):
			# copy object no reference
			materials_link[1][material_name] = copy.copy(sd)

	def cb_remove(self, id):
		global permanents, materials_link

		ret = Blender.Draw.PupMenu('Remove link ?%t|no%x1|yes%x2')
		if (ret != 2):
			return

		material_name = self.menu_material.convert(permanents['_select_material'].val)
		try:
			del materials_link[1][material_name]
		except:
			pass

	def cb_menu_shader(self, id):
#		ret = Blender.Draw.PupMenu('Link shader ?%t|no%x1|yes%x2')
#		if (ret != 2):
#			return
		self.cb_link(id)

	def cb_shader_default(self, id):
		global permanents, materials_link

		material_name = self.menu_material.convert(permanents['_select_material'].val)
		try:
			materials_link[1][material_name].default()
		except:
			pass

	def cb_debug_shader(self, id):
		sd = self.menu_debug_shader.convert(permanents['_select_debug_shader'].val)
		if (sd is not None):
			if ((self.debug_shader is not None) and (self.debug_shader is sd)):
				return
			self.debug_shader = sd

	def cb_ao_default(self, id):
		materials_link[0]['ambient_occlusion'].default()

	def cb_shader_envlight_default(self, id):
		materials_link[0]['environment_light'].default()

	def cb_shader_indirectlight_default(self, id):
		materials_link[0]['indirect_light'].default()

	def cb_catmull_clark(self, id):
		set_property_bool('gelato:catmull_clark')

	def cb_shadows(self, id):
		if (id != self.id_shadow_maps):
			permanents['shadow_maps'].val = 0
		if (id != self.id_shadow_woo):
			permanents['shadow_woo'].val = 0
		if (id != self.id_shadow_raytraced):
			permanents['shadow_ray_traced'].val = 0

	def cb_panel(self, id):
		for pan in self.panels:
			if (pan.id != id):
				permanents[pan.reg_name].val = 0

	def cb_select(self, name):
		global permanents

		permanents['filename'].val = os.path.abspath(name)

	def cb_filename(self, id):
		global permanents

		Blender.Window.FileSelector(self.cb_select, '.pyg', permanents['filename'].val)

	def panel_common(self):
		self.draw_text('Blender Gelato v' + __version__, 130, 2, 6)

		self.draw_button('Save', 70,
			self.cb_save, 'Save pyg file')

		self.draw_button('Render', 80,
			self.cb_render, 'Save and render pyg file')

		self.blank(170)

		self.draw_button('Default', 80, self.cb_default,
			'Set all items to default values')

		self.draw_button('Exit', 70, self.cb_exit,
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

		i = 0
		for pan in self.panels:
			pan.id = self.draw_toggle(pan.name, 100, pan.reg_name, self.cb_panel, pan.help)

			i += 1
			if ((i % 6 == 0) and (i != 12)):
				self.line_feed()

		self.line_feed()

		Blender.BGL.glColor3f(.2392, .3098, 1.0)
		self.draw_rect(0, 4, 650, 10)
		Blender.BGL.glColor3f(1.0, 1.0, 1.0)

		self.line_feed()

		func()

	def panel_output(self):
		self.draw_toggle('Viewer', 100, 'enable_viewer',
			help = 'Enable window viewer')

		self.draw_toggle('Anim', 100, 'anim',
			help = 'Enable sequence render')

		self.draw_menu(self.menu_data, 100, 'data',
			help = 'Output data')

		self.draw_menu(self.menu_format, 100, 'format',
			help = 'Output format')

		(comp, comp_help) = self.menu_format.convert(permanents['format'].val)[2:4]
		if (comp):
			self.draw_menu(comp, 100, 'compression',
				help = comp_help)

		self.line_feed()

		self.draw_toggle('Binary', 100, 'enable_binary',
			help = 'Enable binary file')

		self.draw_toggle('Preview', 100, 'enable_preview',
			help = 'Enable preview')

		if (permanents['enable_preview'].val):
			self.draw_slider('Preview quality: ', 320, 0.0, 1.0, 'preview_quality',
				help = 'Preview quality')

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

		v = permanents['format'].val
		if ((v != self.val_format_null) and (v != self.val_format_openEXR)):
			self.line_feed()

			self.draw_number('Dither: ', 100, 0.0, 10.0, 'dither',
				help = 'Dither amplitude')

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

		self.draw_button('Filename:', 100, self.cb_filename,
			'Select file name', 0)

		self.draw_string('', 550, 200, 'filename',
			help = 'File name')

		self.line_feed()

		self.draw_string('Path inputs: ', 650, 250, 'path_inputs',
			help = 'Search path for scene files')

		self.line_feed()

		self.draw_string('Path textures: ', 650, 250, 'path_texture',
			help = 'Search path for texture files')

		self.line_feed()

		self.draw_string('Path shader: ', 650, 250, 'path_shader',
			help = 'Search path for compiled shaders')

		self.line_feed()

		self.draw_string('Path imageio: ', 650, 250, 'path_imageio',
			help = 'Search path for image format input/output DSO\'s')

		self.line_feed()

		self.draw_string('Path generator: ', 650, 250, 'path_generator',
			help = 'Search path for generators DSO\'s')

	def panel_pass(self):
		c = 0
		if (permanents['shadow_maps'].val or permanents['shadow_woo'].val):
			c += 1
		if (permanents['enable_ao'].val):
			c += 1

		if (c == 0):
			c = 1

		self.draw_toggle('Beauty', 130 * c, 'pass_beauty',
			help = 'Enable beauty pass')

		self.line_feed(False)

		if (permanents['shadow_maps'].val or permanents['shadow_woo'].val):
			self.draw_toggle('Shadows', 130, 'pass_shadows',
				help = 'Enable shadows pass', sep = 0)

		if (permanents['enable_ao'].val):
			self.draw_toggle('Ambient Occlusion', 130, 'pass_ao',
				help = 'Enable ambient occlusion pass', sep = 0)

	def panel_geometries(self):
		self.draw_toggle('All double sided', 130, 'all_double_sided',
			help = 'Enable all double sided faces')

		self.draw_toggle('DupliVerts', 130, 'dup_verts',
			help = 'Enable DupliVerts')

		self.line_feed()

		self.draw_button('Catmull Clark', 130,
			self.cb_catmull_clark, 'Enable catmull-clark property of all selected objects')

	def panel_lights(self):
		self.draw_toggle('Enable', 90, 'enable_lights',
			help = 'Enable all lights')

		self.draw_toggle('Key Fill Rim', 90, 'enable_key_fill_rim',
			help = 'Enable Key Fill Rim 3-lights')

		if (permanents['enable_lights'].val):
			self.draw_slider('Lights factor: ', 255, 0.0, 1000.0, 'lights_factor',
				help = 'Lights factor')

	def panel_shadows(self):
		self.id_shadow_maps = self.draw_toggle('Maps', 100, 'shadow_maps',
			self.cb_shadows, 'Enable shadow maps', sep = 0)

		self.id_shadow_woo = self.draw_toggle('Woo', 100, 'shadow_woo',
			self.cb_shadows, 'Enable Woo (average) shadow', sep = 0)

		self.id_shadow_raytraced = self.draw_toggle('Ray traced', 100, 'shadow_ray_traced',
			self.cb_shadows, 'Enable ray traced shadows')

		if (permanents['shadow_maps'].val or permanents['shadow_woo'].val):
			self.line_feed(False)

			self.draw_toggle('Dynamics', 200, 'enable_dynamic',
				help = 'Enable dynamic map')

			if (not permanents['enable_dynamic'].val):
				self.line_feed()

				self.draw_menu(self.menu_compression_tiff, 100, 'compression_shadow',
					help = 'Shadow compression')

	def panel_textures(self):
		self.draw_toggle('Enable', 90, 'enable_textures',
			help = 'Enable all textures')

		if (permanents['enable_textures'].val):
			self.draw_toggle('Automipmap', 90, 'enable_automipmap',
				help = 'Automatically generate mipmaps')

	def panel_shaders(self):
		global materials_link

		self.draw_toggle('Enable', 100, 'enable_shaders',
			help = 'Enable all shaders')

		if (permanents['enable_shaders'].val):

			self.draw_number('Shading quality: ', 160, 0.0, 16.0, 'shadingquality',
				help = 'Shading quality')

			self.line_feed()

			self.draw_toggle('Enable debug', 100, '_enable_debug_shaders',
				help = 'Enable debug shaders')

			if (permanents['_enable_debug_shaders'].val):

				if (self.menu_debug_shader):
					self.draw_menu(self.menu_debug_shader, 100, '_select_debug_shader',
						self.cb_debug_shader, help = 'Select debug shader')

					if (self.debug_shader is not None):
						self.line_feed()

						self.y = self.debug_shader.gui(self.x, self.y, self.h, self.s)
			else:
				if (self.menu_shader):

					# get all materials

					materials = Blender.Material.Get()
					if (materials):
						self.menu_material = self.bake_menu('Materials',
							[[m.name, m.name] for m in sorted(materials)])

						self.draw_menu(self.menu_material, 100, '_select_material',
							help = 'Selct material')

						material_name = self.menu_material.convert(permanents['_select_material'].val)
						if (materials_link[1].has_key(material_name)):
							self.draw_button('Remove', 100,
								self.cb_remove, 'Remove material')

							self.line_feed()

							y = materials_link[1][material_name].gui(self.x, self.y, self.h, self.s)

							self.blank(540)

							self.draw_button('Default', 100,
								self.cb_shader_default, 'Default values')

							self.y = y
						else:
							self.draw_button('Link', 100,
								self.cb_link, 'Link material')

							self.draw_menu(self.menu_shader, 100, '_select_shader',
								self.cb_menu_shader, 'Select shader')

	def panel_dof(self):
		self.draw_toggle('Enable', 90, 'enable_dof', help = 'Enable Depth Of Field')

		if (permanents['enable_dof'].val):
			self.draw_string('F/Stop: ', 100, 20, 'fstop',
				help = 'F/Stop for depth of field')

			self.draw_string('Focal length: ', 160, 20, 'focallength',
				help = 'Lens focal length')

			self.draw_string('Focal distance: ', 160, 20, 'focaldistance',
				help = 'Distance to sharp focus')

			self.line_feed()

			self.draw_number('Quality: ', 90, 1, 128, 'dofquality',
				help = 'Number of lens values for DoF')

	def panel_environment(self):
		self.draw_toggle('Sky', 60, 'enable_sky',
			help = 'Enable background color')

		self.draw_menu(self.menu_units, 100, 'units_length',
			help = 'Physical length units of "common" space')

		if (permanents['units_length'].val):
			self.draw_string('Length scale: ', 140, 20, 'units_lengthscale',
				help = 'Length unit scale of "common" space units')

	def panel_ambient_occlusion(self):
		global materials_link

		self.draw_toggle('Enable', 90, 'enable_ao',
			help = 'Enable ambient occlusion')

		if (permanents['enable_ao'].val):

			shader_ambocclude = materials_link[0]['ambient_occlusion']
			if (shader_ambocclude):
				self.line_feed()

				y = shader_ambocclude.gui(self.x, self.y, self.h, self.s)

				self.blank(540)

				self.draw_button('Default', 100,
					self.cb_ao_default, 'Ambient occlusion default values')

				self.y = y

			shader_envlight = materials_link[0]['environment_light']
			if (shader_envlight):
				self.line_feed()

				y = shader_envlight.gui(self.x, self.y, self.h, self.s)

				self.blank(540)

				self.draw_button('Default', 100,
					self.cb_shader_envlight_default, 'Environment light default values')

				self.y = y

	def panel_indirect_light(self):
		self.draw_toggle('Enable', 90, 'enable_indirect_light',
			help = 'Enable indirect light')

		shader_indirectlight = materials_link[0]['indirect_light']
		if (shader_indirectlight and (permanents['enable_indirect_light'].val)):

			self.draw_number('Min samples: ', 140, 0, 16, 'indirect_minsamples',
				help = 'The minimum number of nearby samples')

			self.line_feed()

			y = shader_indirectlight.gui(self.x, self.y, self.h, self.s)

			self.blank(540)

			self.draw_button('Default', 100,
				self.cb_shader_indirectlight_default, 'Indirect light default values')

			self.y = y

	def panel_ray_traced(self):
		self.draw_toggle('Enable', 90, 'enable_ray_traced',
			help = 'Enable ray traced reflections and refractions')

		if (permanents['enable_ray_traced'].val):
			if (permanents['shadow_ray_traced'].val):
				self.draw_number('Shadow bias: ', 140, 0, 16, 'ray_traced_shadow_bias',
					help = 'Ray traced shadow bias')

			self.draw_number('Raytraced max depth: ', 170, 0, 16, 'ray_traced_max_depth',
				help = 'Ray traced max depth')

# property

def set_property_bool(name):
	for obj in Blender.Object.GetSelected():
		type = obj.getType()
		if ((type != 'Mesh') and (type != 'Surf')):
			continue
		try:
			try:
				prop = obj.getProperty(name)
				obj.removeProperty(prop)
			except:
				pass

			obj.addProperty(name, 1, 'BOOL')
			Blender.Redraw()
			Blender.RedrawAll()
		except:
			pass

def get_property_bool(obj, name):
	try:
		prop = obj.getProperty(name)
		if (prop.getType() == 'BOOL'):
			return prop.getData()
	except:
		pass

	return False

# registry

def registry_default():
	global permanents, FILENAME_PYG

	permanents = {
		'filename':                   Blender.Draw.Create(FILENAME_PYG),
		'anim':                       Blender.Draw.Create(0),
		'bucketorder':                Blender.Draw.Create(2),		# Spiral

		'enable_binary':              Blender.Draw.Create(1),

		'enable_preview':             Blender.Draw.Create(0),
		'preview_quality':            Blender.Draw.Create(0.1),

		'enable_viewer':              Blender.Draw.Create(1),
		'format':                     Blender.Draw.Create(0),		# Null
		'data':                       Blender.Draw.Create(0),		# RGB

		'compression':                Blender.Draw.Create(1),		# ZIP
		'compression_shadow':         Blender.Draw.Create(1),		# ZIP

		'shadow_maps':                Blender.Draw.Create(0),
		'shadow_woo':                Blender.Draw.Create(0),
		'shadow_ray_traced':          Blender.Draw.Create(0),
		'enable_dynamic':             Blender.Draw.Create(0),

		'antialiasing_x':             Blender.Draw.Create(4),
		'antialiasing_y':             Blender.Draw.Create(4),

		'filter':                     Blender.Draw.Create(0),		# Gaussian
		'filterwidth_x':              Blender.Draw.Create(2.0),
		'filterwidth_y':              Blender.Draw.Create(2.0),

		'gamma':                      Blender.Draw.Create(1.0),
		'gain':                       Blender.Draw.Create(1.0),

		'dither':                     Blender.Draw.Create(0.5),

		'quantize_zero':              Blender.Draw.Create('0'),
		'quantize_one':               Blender.Draw.Create('255'),
		'quantize_min':               Blender.Draw.Create('0'),
		'quantize_max':               Blender.Draw.Create('255'),

		'all_double_sided':           Blender.Draw.Create(0),
		'dup_verts':                  Blender.Draw.Create(1),

		'enable_ray_traced':          Blender.Draw.Create(0),
		'ray_traced_max_depth':       Blender.Draw.Create(1),
		'ray_traced_shadow_bias':     Blender.Draw.Create(0.01),

		'lights_factor':              Blender.Draw.Create(50.0),
		'enable_key_fill_rim':        Blender.Draw.Create(0),
		'enable_lights':              Blender.Draw.Create(1),

		'enable_shaders':             Blender.Draw.Create(1),
		'shadingquality':             Blender.Draw.Create(1.0),
		'_enable_debug_shaders':      Blender.Draw.Create(0),
		'_select_debug_shader':       Blender.Draw.Create(0),
		'_select_material':           Blender.Draw.Create(0),
		'_select_shader':             Blender.Draw.Create(0),

		'enable_ao':                  Blender.Draw.Create(0),

		'enable_indirect_light':      Blender.Draw.Create(0),
		'indirect_minsamples':        Blender.Draw.Create(3),

		'enable_textures':            Blender.Draw.Create(1),
		'enable_automipmap':          Blender.Draw.Create(1),

		'enable_dof':                 Blender.Draw.Create(0),
		'fstop':                      Blender.Draw.Create('4.0'),
		'focallength':                Blender.Draw.Create('0.032'),
		'focaldistance':              Blender.Draw.Create(''),
		'dofquality':                 Blender.Draw.Create(16),

		'enable_sky':                 Blender.Draw.Create(1),
		'units_length':               Blender.Draw.Create(0),
		'units_lengthscale':          Blender.Draw.Create('1.0'),

		'enable_full_path':           Blender.Draw.Create(1),

		'path_shader':                Blender.Draw.Create(os.path.pathsep.join(['.', '$GELATOHOME/shaders', '&'])),
		'path_texture':               Blender.Draw.Create(os.path.pathsep.join(['.', '$GELATOHOME/textures', '&'])),
		'path_inputs':                Blender.Draw.Create(os.path.pathsep.join(['.', '$GELATOHOME/inputs', '&'])),
		'path_imageio':               Blender.Draw.Create(os.path.pathsep.join(['.', '$GELATOHOME/lib', '&'])),
		'path_generator':             Blender.Draw.Create(os.path.pathsep.join(['.', '$GELATOHOME/lib', '&'])),

		'pass_beauty':                Blender.Draw.Create(1),
		'pass_shadows':               Blender.Draw.Create(0),
		'pass_ao':                    Blender.Draw.Create(0),

		'_panel_output':              Blender.Draw.Create(1),
		'_panel_pass':                Blender.Draw.Create(0),
		'_panel_ambient_occlusion':   Blender.Draw.Create(0),
		'_panel_geometries':          Blender.Draw.Create(0),
		'_panel_lights':              Blender.Draw.Create(0),
		'_panel_shadows':             Blender.Draw.Create(0),
		'_panel_textures':            Blender.Draw.Create(0),
		'_panel_shaders':             Blender.Draw.Create(0),
		'_panel_dof':                 Blender.Draw.Create(0),
		'_panel_environment':         Blender.Draw.Create(0),
		'_panel_indirectlight':       Blender.Draw.Create(0),
		'_panel_ray_traced':          Blender.Draw.Create(0),
	}

	for sd in materials_link[1].itervalues():
		sd.default()

def xml_save():
	global ROOT_ELEMENT, FILENAME_XML, USE_XML_DOM_EXT
	global permanents, materials_link

	# write xml file

	dom = xml.dom.minidom.getDOMImplementation()
	doctype = dom.createDocumentType(ROOT_ELEMENT, None, None)

	doc = dom.createDocument(None, ROOT_ELEMENT, doctype )

	root = doc.documentElement
	doc.appendChild(root)

	root.setAttribute('version', __version__)

	try:
		root.setAttribute('timestamp', datetime.datetime.today().strftime('%F %T'))
	except:
		pass

	head = doc.createElement('config')
	root.appendChild(head)

	for name in sorted(permanents.iterkeys()):
		# skip internal's names
		if (name[0] == '_'):
			continue

		elem = doc.createElement(name)
		head.appendChild(elem)
		elem.appendChild(doc.createTextNode(str(permanents[name].val).strip()))

	# materials list

	i = 0
	for ml in materials_link:
		materials = doc.createElement('materials')
		root.appendChild(materials)
		materials.setAttribute('index', str(i))

		for mat, sd in materials_link[i].iteritems():
			material = doc.createElement('material')
			materials.appendChild(material)
			material.setAttribute('name', mat)

			sd.toxml(doc, material)

		i += 1

	# write XML file

	try:
		fxml = open(FILENAME_XML, 'w')

	except IOError:

		print 'Error: Cannot write file "%s"' % FILENAME_XML
		return

	if (USE_XML_DOM_EXT):
		xml.dom.ext.PrettyPrint(doc, fxml)
	else:
		doc.writexml(fxml, addindent='  ', newl='\n')

def xml_load():
	global ROOT_ELEMENT, FILENAME_XML
	global permanents, materials_link

	# read xml file

	try:
		doc = xml.dom.minidom.parse(FILENAME_XML)
	except:
		print 'Info: XML config file "%s" not found, will use default settings' % FILENAME_XML
		return

	if (doc.documentElement.tagName != ROOT_ELEMENT):
		print 'Error: file "%s", invalid root element "%s"' % (FILENAME_XML, doc.documentElement.tagName)
		return

	head = doc.getElementsByTagName('config')
	if (len(head) == 0):
		print 'Error: file "%s", not element "config"' % FILENAME_XML
	else:
		for name in permanents.keys():
			# skip internal's names
			if (name[0] == '_'):
				continue

			el = head[0].getElementsByTagName(name)
			if (len(el) == 0):
				continue

			el[0].normalize()
			nd = el[0].firstChild
			if (nd.nodeType != xml.dom.Node.TEXT_NODE):
				continue

			t = type(permanents[name].val)
			if (t is type(int())):
				permanents[name] = Blender.Draw.Create(int(nd.data))
			elif (t is type(float())):
				permanents[name] = Blender.Draw.Create(float(nd.data))
			elif (t is type(str())):
				permanents[name] = Blender.Draw.Create(nd.data.strip())
			else:
				print 'Error: file "%s", element "%s" type "%s" unknow' % (FILENAME_XML, name, t)

	# materials list

	for material in doc.getElementsByTagName('materials'):
		index = material.getAttribute('index')
		if (index is None):
			print 'Error: file "%s", not attribute "index" element "materials"' % FILENAME_XML
			continue

		idx = int(index)

		for mat in material.getElementsByTagName('material'):
			name = mat.getAttribute('name')
			if (name is None):
				continue

			sd = shader()

			if (not sd.fromxml(doc, mat)):
				continue

			materials_link[idx][name] = sd

# utility

uniq_gui_id = 0
def get_gui_id():
	global uniq_gui_id
	uniq_gui_id += 1
	if (uniq_gui_id > 16382):
		uniq_gui_id = 1
	return uniq_gui_id

def search_file(name, paths):
	for p in paths.split(os.path.pathsep):
		try:
			path = os.path.expandvars(p)
			file = os.path.join(path, name)
			if (os.path.exists(file)):
				return file
		except:
			continue
	return None

def find_files(paths, pattern):
	fdict = {}
	for p in paths.split(os.path.pathsep):
		try:
			path = os.path.expandvars(p)
			files = os.listdir(path)
			for f in fnmatch.filter(files, pattern):
				fdict[f] = path
		except:
			continue
	return fdict

# main

def main():
	global ROOT_ELEMENT, FILENAME_PYG, FILENAME_XML
	global GELATO, GSOINFO, MAKETX
	global permanents, materials_link, gelato_gui, pyg

	PYTHON_MAJOR = 2
	PYTHON_MINOR = 4

	if sys.version_info < (PYTHON_MAJOR, PYTHON_MINOR):
		raise ('Error: Python version %d.%d or greater is required\nPython version is %s' % (PYTHON_MAJOR, PYTHON_MINOR, sys.version))

	ROOT_ELEMENT = 'BlenderGelato'

	# programs

	GELATO  = 'gelato'
	GSOINFO = 'gsoinfo'
	MAKETX  = 'maketx'

	if (os.name == 'nt'):
		exe = '.exe'
		GELATO  += exe
		GSOINFO += exe
		MAKETX  += exe

	gelatohome = os.getenv('GELATOHOME')
	if (gelatohome):
		GELATO  = os.path.join(gelatohome, 'bin', GELATO)
		GSOINFO = os.path.join(gelatohome, 'bin', GSOINFO)
		MAKETX  = os.path.join(gelatohome, 'bin', MAKETX)

	# file name

	try:
		blend_file_name = Blender.Get('filename')
		(base, ext) = os.path.splitext(blend_file_name)
		if (ext.lower() == '.gz'):
			(base, ext) = os.path.splitext(base)
	except:
		base = 'gelato'

	FILENAME_PYG = base + '.pyg'
	FILENAME_XML = base + '.xml'

	gelato_gui = None

	# material's set

	materials_link = [{}, {}]

	# data permanents

	registry_default()

	# gelato convert

	pyg = gelato_pyg()

	# GUI

	gelato_gui = cfggui()

	# data permanents

	xml_load()
	xml_save()

	# start

	Blender.Draw.Register(gelato_gui.draw, gelato_gui.handle_event, gelato_gui.handle_button_event)

if __name__ == '__main__':
	try:
		import psyco
		psyco.full()
	except:
		pass

	main()

