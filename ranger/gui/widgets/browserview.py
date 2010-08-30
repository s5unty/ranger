# Copyright (C) 2009, 2010  Roman Zimbelmann <romanz@lavabit.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""The BrowserView manages a set of BrowserColumns."""
import curses
from ranger.ext.signal_dispatcher import Signal
from . import Widget
from .browsercolumn import BrowserColumn
from .pager import Pager
from ..displayable import DisplayableContainer

# Perspective    | Identifier | Description
# ---------------+------------+---------------------------------------
# Miller Columns | "miller"   | Several rows with preview and backview
# Dual Pane      | "dual"     | Two columns next to each other
# Long Listing   | "long"     | One column with extended information

# The first is also the default.
ALLOWED_PERSPECTIVES = "miller", "dual", "long"

class BrowserView(Widget, DisplayableContainer):
	ratios = None
	preview = True
	is_collapsed = False
	draw_bookmarks = False
	stretch_ratios = None
	need_clear = False
	pager = None
	columns = []

	def __init__(self, win, ratios, preview=True):
		DisplayableContainer.__init__(self, win)
		self.preview = preview
		self.create_perspective(self.settings.perspective)

		for option in ('preview_directories', 'preview_files'):
			self.settings.signal_bind('setopt.' + option,
					self._request_clear_if_has_borders, weak=True)

		self.fm.env.signal_bind('move', self.request_clear)
		self.settings.signal_bind('setopt.column_ratios', self.request_clear)
		self.settings.signal_bind('setopt.perspective',
				self.change_perspective, priority=0.1)

	def change_perspective(self, signal):
		if signal.previous != signal.value:
			if signal.value in ALLOWED_PERSPECTIVES:
				self.destroy_perspective()
				self.create_perspective(signal.value)
			else:
				raise Exception("No such perspective: " + str(signal.value))

	def destroy_perspective(self):
		if self.columns:
			for column in self.columns:
				column.destroy()
				self.remove_child(column)
		self.columns = []
		self.main_column = None
		if self.pager:
			self.pager.destroy()
		self.pager = None

	def create_perspective(self, which, **keywords):
		if which not in ALLOWED_PERSPECTIVES:
			which = ALLOWED_PERSPECTIVES[0]
		if which == 'miller':
			self._create_perspective_miller()
		if which == 'dual':
			self._create_perspective_dual()
		if which == 'long':
			self._create_perspective_long()

	def _create_perspective_dual(self):
		column = BrowserColumn(self.win, 0)
		self.main_column = column
		self.add_child(column)
		self.columns.append(column)
		column = BrowserColumn(self.win, 0)
		self.add_child(column)
		self.columns.append(column)
		self.resize(self.y, self.x, self.hei, self.wid)

	def _create_perspective_long(self):
		column = BrowserColumn(self.win, 0)
		self.main_column = column
		self.add_child(column)
		self.columns = [column]
		self.resize(self.y, self.x, self.hei, self.wid)

	def _create_perspective_miller(self):
		self.pager = Pager(self.win, embedded=True)
		self.pager.visible = False
		self.add_child(self.pager)

		ratios = self.settings.column_ratios
		ratio_sum = float(sum(ratios))
		self.ratios = tuple(x / ratio_sum for x in ratios)

		if len(self.ratios) >= 2:
			self.stretch_ratios = self.ratios[:-2] + \
					((self.ratios[-2] + self.ratios[-1] * 0.9),
					(self.ratios[-1] * 0.1))

		offset = 1 - len(ratios)
		if self.preview: offset += 1

		self.columns = []
		for level in range(len(ratios)):
			fl = BrowserColumn(self.win, level + offset)
			self.add_child(fl)
			self.columns.append(fl)

		try:
			self.main_column = self.columns[self.preview and -2 or -1]
		except IndexError:
			self.main_column = None
		else:
			self.main_column.display_infostring = True
			self.main_column.main_column = True

		self.resize(self.y, self.x, self.hei, self.wid)

	def change_ratios(self, ratios, resize=True):
		if isinstance(ratios, Signal):
			ratios = ratios.value

		if self.settings.perspective == 'miller':
			self.destroy_perspective()
			self.create_perspective('miller')

	def _request_clear_if_has_borders(self):
		if self.settings.draw_borders:
			self.request_clear()

	def request_clear(self):
		self.need_clear = True

	def draw(self):
		if self.draw_bookmarks:
			self._draw_bookmarks()
		else:
			if self.need_clear:
				self.win.erase()
				self.need_redraw = True
				self.need_clear = False
			DisplayableContainer.draw(self)
			if self.settings.draw_borders:
				self._draw_borders()

	def finalize(self):
		if self.pager and self.pager.visible:
			try:
				self.fm.ui.win.move(self.main_column.y, self.main_column.x)
			except:
				pass
		else:
			try:
				x = self.main_column.x
				y = self.main_column.y + self.main_column.target.pointer\
						- self.main_column.scroll_begin
				self.fm.ui.win.move(y, x)
			except:
				pass

	def _draw_bookmarks(self):
		self.color_reset()
		self.need_clear = True

		sorted_bookmarks = sorted(item for item in self.fm.bookmarks \
			if self.settings.show_hidden_bookmarks or '/.' not in item[1].path)

		def generator():
			return zip(range(self.hei-1), sorted_bookmarks)

		try:
			maxlen = max(len(item[1].path) for i, item in generator())
		except ValueError:
			return
		maxlen = min(maxlen + 5, self.wid)

		whitespace = " " * maxlen
		for line, items in generator():
			key, mark = items
			string = " " + key + ": " + mark.path
			self.addstr(line, 0, whitespace)
			self.addnstr(line, 0, string, self.wid)

		if self.settings.draw_bookmark_borders:
			self.win.hline(line+1, 0, curses.ACS_HLINE, maxlen)

			if maxlen < self.wid:
				self.win.vline(0, maxlen, curses.ACS_VLINE, line+1)
				self.addch(line+1, maxlen, curses.ACS_LRCORNER)

	def _draw_borders(self):
		win = self.win
		self.color('in_browser', 'border')

		left_start = 0
		right_end = self.wid - 1

		for child in self.columns:
			if not child.has_preview():
				left_start = child.x + child.wid
			else:
				break
		if not self.pager or not self.pager.visible:
			for child in reversed(self.columns):
				if not child.has_preview():
					right_end = child.x - 1
				else:
					break
			if right_end < left_start:
				right_end = self.wid - 1

		win.hline(0, left_start, curses.ACS_HLINE, right_end - left_start)
		win.hline(self.hei - 1, left_start, curses.ACS_HLINE,
				right_end - left_start)
		win.vline(1, left_start, curses.ACS_VLINE, self.hei - 2)

		for child in self.columns:
			if not child.has_preview():
				continue
			if child.main_column and self.pager and self.pager.visible:
				win.vline(1, right_end, curses.ACS_VLINE, self.hei - 2)
				break
			x = child.x + child.wid
			y = self.hei - 1
			try:
				win.vline(1, x, curses.ACS_VLINE, y - 1)
				win.addch(0, x, curses.ACS_TTEE, 0)
				win.addch(y, x, curses.ACS_BTEE, 0)
			except:
				# in case it's off the boundaries
				pass

		self.addch(0, left_start, curses.ACS_ULCORNER)
		self.addch(self.hei - 1, left_start, curses.ACS_LLCORNER)
		self.addch(0, right_end, curses.ACS_URCORNER)
		self.addch(self.hei - 1, right_end, curses.ACS_LRCORNER)

	def _collapse(self):
		# Should the last column be cut off? (Because there is no preview)
		return self.settings.collapse_preview and self.preview \
			and self.columns and not self.columns[-1].has_preview() \
			and self.stretch_ratios

	def resize(self, y, x, hei, wid):
		DisplayableContainer.resize(self, y, x, hei, wid)
		which = self.settings.perspective
		if which not in ALLOWED_PERSPECTIVES:
			which = ALLOWED_PERSPECTIVES[0]
		if which == 'miller':
			self._resize_miller(y, x, hei, wid)
		if which == 'long':
			self._resize_long(y, x, hei, wid)
		if which == 'dual':
			self._resize_dual(y, x, hei, wid)

	def _resize_dual(self, y, x, hei, wid):
		halfwid = int(self.wid / 2) - 1
		self.columns[0].resize(0, 0, self.hei, halfwid)
#		self.columns[1].resize(y, x + halfwid + 1, hei, halfwid)
		self.columns[1].resize(0, 0 + halfwid + 1, self.hei, halfwid)

	def _resize_long(self, y, x, hei, wid):
		self.columns[0].resize(0, 0, self.hei, self.wid)

	def _resize_miller(self, y, x, hei, wid):
		"""Resize all the columns according to the given ratio"""
		borders = self.settings.draw_borders
		pad = 1 if borders else 0
		left = pad

		self.is_collapsed = self._collapse()
		if self.is_collapsed:
			generator = enumerate(self.stretch_ratios)
		else:
			generator = enumerate(self.ratios)

		last_i = len(self.ratios) - 1

		for i, ratio in generator:
			wid = int(ratio * self.wid)

			if i == last_i:
				wid = int(self.wid - left + 1 - pad)

			if i == last_i - 1:
				self.pager.resize(pad, left, hei - pad * 2, \
						max(1, self.wid - left - pad))

			try:
				self.columns[i].resize(pad, left, hei - pad * 2, \
						max(1, wid - 1))
			except KeyError:
				pass

			left += wid

	def click(self, event):
		if DisplayableContainer.click(self, event):
			return True
		direction = event.mouse_wheel_direction()
		if direction:
			self.main_column.scroll(direction)
		return False

	def open_pager(self):
		self.pager.visible = True
		self.pager.focused = True
		self.need_clear = True
		self.pager.open()
		try:
			self.columns[-1].visible = False
			self.columns[-2].visible = False
		except IndexError:
			pass

	def close_pager(self):
		self.pager.visible = False
		self.pager.focused = False
		self.need_clear = True
		self.pager.close()
		try:
			self.columns[-1].visible = True
			self.columns[-2].visible = True
		except IndexError:
			pass

	def poke(self):
		DisplayableContainer.poke(self)
		if self.preview and self.is_collapsed != self._collapse():
			self.resize(self.y, self.x, self.hei, self.wid)
