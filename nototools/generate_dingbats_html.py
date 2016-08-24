#!/usr/bin/python
#
# Copyright 2016 Google Inc. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import argparse
import codecs
import collections
import re
import string
import sys

from fontTools import ttLib

from os import path

from nototools import cmap_data
from nototools import font_data
from nototools import tool_utils
from nototools import unicode_data

"""Generate html comparison of codepoints in various fonts.

Currently hardwired for select target and comparison fonts."""


_HTML_HEADER_TEMPLATE = """<!DOCTYPE html>
<html lang='en'>
<head>
  <meta charset="utf-8">
  <title>$title</title>
  <style>
  $styles
  </style>
  <style>
    table { background-color: #eee; font-size: 20pt }
    tr.head { font-weight: bold; font-size: 12pt;
              border-style: solid; border-width: 1px; border-color: black }
    .code, .age, .name { font-size: 12pt }
    .star { text-align: center }
    .key { background-color: white; font-size: 12pt; border-collapse: separate;
           margin-top: 0; border-spacing: 10px 0 }
  </style>
</head>
<body>
  <h3>$title</h3>
"""


_HTML_FOOTER = """
</body>
</html>
"""


def _read_codefile(codefile):
  """Codefile contains lines with one or two codepoints separated by
  semicolon. the first is the codepoint to use in the text, the second
  if present is the one to use for unicode info like name and age
  (otherwise the first is used).  This is to deal with PUA cmaps where
  there are equivalent unicode codepoints.  Blank lines and text after
  '#' are discarded.  Returns a list of tuples of the codepoints.
  Order is preserved, this is the preferred display order."""
  with open(codefile, 'r') as f:
    result = []
    for line in f:
      ix = line.find('#')
      if ix != -1:
        line = line[:ix]
      line = line.strip()
      if not line:
        continue
      result.append(tuple(int(s, 16) for s in line.split(';')))
  return result


def _load_targets(targets, data_dir):
  """Each target is a tuple of two to four items.  The first item is the
  short name or key, the second is the name of the font file in
  data_dir.  The third item is the name to use for the font, if not
  present or None the name from the name table will be used. The fourth
  optional item is the name of the code file in the data_dir, if not
  present it is the basename of the font file in lower case with the
  suffix '_codes.txt'.  Exceptions are thrown if there are duplicate
  keys or the font or codefile are missing or cannot be read.  Returns a
  list of tuples of key, filepath, codelist."""

  def _load_target(target):
    key, fname = target[:2]
    fontpath = path.join(data_dir, fname)
    if not path.isfile(fontpath):
      raise Exception('target "%s" font "%s" not found' % (
          key, fontpath))
    if len(target) > 2:
      name = target[2]
    else:
      name = None
    if len(target) > 3:
      codefile = target[3]
    else:
      codefile = path.splitext(fname)[0].lower() + '_codes.txt'
    codefile = path.join(data_dir, codefile)
    if not path.isfile(codefile):
      raise Exception('target "%s" code file "%s" not found' % (
          key, codefile))
    codes = _read_codefile(codefile)
    if not name:
      font = ttLib.TTFont(fontpath)
      names = font_data.get_name_records(font)
      print 'font:', fontpath
      print names
      name = names[16] if 16 in names else names[1] if 1 in names else None
      if not name:
        raise Exception('no name found in font "%s"' % fontpath)
    return key, fontpath, name, codes

  result = [_load_target(t) for t in targets]

  keys = set()
  for t in result:
    key = t[0]
    if key in keys:
      raise Exception('two targets with same key: "%s"' % key)
    keys.add(key)
  return result


def _read_cmapfile(filename):
  with open(filename, 'r') as f:
    text = f.read()
    return tool_utils.parse_int_ranges(text)


def _load_references(references, data_dir):
  """Each reference is a tuple of two to four items.  The first item is
  the key, the second is the name of the font file in data_dir.  The
  second can be None, otherwise it must exist.  The third item, if
  present, is the name to use for the font, otherwise it will be read
  from the font, it must be present where there is no font.  The
  fourth item, if present, is the name of a cmap file, it must be present
  where there is no font.  The cmap file is one or more lines
  listing ranges.  When not present the unicode cmap from the font is
  used.  Returns a list of tuples of key, keyinfo, where keyinfo is
  a list of tuples of filepath, name, cmap.  Unlike with targets, multiple
  references can share the same key."""

  def _load_reference(ref):
    key, fname = ref[:2]
    if len(ref) > 2:
      name = ref[2]
    else:
      name = None
    if len(ref) > 3:
      cmapfile = ref[3]
    else:
      cmapfile = None

    if not fname:
      if not name:
        raise Exception('must have name if no font provided')
      if not cmapfile:
        raise Exception('must have cmap file if no font provided')
      fontpath = None
    else:
      fontpath = path.join(data_dir, fname)
      if not path.isfile(fontpath):
        raise Exception('reference font "%s" not found' % fontpath)
    if cmapfile:
      cmapfile = path.join(data_dir, cmapfile)
      if not path.isfile(cmapfile):
        raise Exception('reference "%s" cmap file "%s" not found' % (
          key, cmapfile))
      cmap = _read_cmapfile(cmapfile)
    if fname and (not cmapfile or not name):
      font = ttLib.TTFont(fontpath)
      if not name:
        names = font_data.get_name_records(font)
        name = names[16] if 16 in names else names[1] if 1 in names else None
        if not name:
          raise Exception('cannot read name from font "%s"' % fontpath)
      if not cmapfile:
        cmap = font_data.get_cmap(font)

    return key, fontpath, name, cmap

  # group by key
  keyorder = []
  keyinfo = collections.defaultdict(list)
  for ref in references:
    key, fontpath, name, cmap = _load_reference(ref)
    if key not in keyinfo:
      keyorder.append(key)
    keyinfo[key].append((fontpath, name, cmap))
  return [(key, keyinfo[key]) for key in keyorder]


def _get_driver(data_dir):
  """Hard code the driver data.  Should parse from a file."""
  title = 'Dingbats Comparison Tables'
  targets = [
      ('webd', 'webdings.ttf', 'Webdings'),
      ('wng1', 'wingding.ttf', 'Wingdings 1'),
      ('wng2', 'WINGDNG2.TTF', 'Wingdings 2'),
      ('wng3', 'WINGDNG3.TTF', 'Wingdings 3'),
      ('zdng', 'ZapfDingbats_x.ttf', 'Zapf Dingbats', 'zapfdingbats_codes.txt')
  ]
  references = [
      ('color', 'NotoColorEmoji.ttf'),
      ('b/w', 'NotoEmoji-Regular.ttf'),
      ('osym', 'NotoSansSymbols-Regular.ttf', 'Old Symbols'),
      ('noto', 'NotoSans-Regular.ttf', 'Noto LGC'),
      ('noto', None, 'Noto Sans Math', 'notosansmath_cmap.txt'),
      ('nsym', 'NotoSansSymbolsNew-Regular.ttf', 'New Symbols'),
      ('sym2', 'NotoSansSymbols2-Regular.ttf', 'Noto Sans Symbols2',
       'notosanssymbols2_cmap.txt')
  ]
  targets = _load_targets(targets, data_dir)
  references = _load_references(references, data_dir)
  return title, targets, references


def generate_text(outfile, title, targets, references, data_dir):
  emoji_only = (
      unicode_data.get_emoji() - unicode_data.get_unicode_emoji_variants())

  print >> outfile, title
  print >> outfile
  print >> outfile, 'Targets:'
  for key, font, name, _ in targets:
    rel_font = path.relpath(font, data_dir) if font else '(no font)'
    print >> outfile, '  %s: %s (%s)' % (key, name, rel_font)
  print >> outfile
  print >> outfile, 'References:'
  for key, keyinfos in references:
    for font, name, _ in keyinfos:
      rel_font = path.relpath(font, data_dir) if font else '(no font)'
      print >> outfile, '  %s: %s (%s)' % (key, name, rel_font)
  print >> outfile

  for tkey, font, name, codes in targets:
    print >> outfile
    print >> outfile, name
    index = 1
    for codepair in codes:
      cp0 = codepair[0]
      cp1 = cp0 if len(codepair) == 1 else codepair[1]
      print >> outfile, '%3d' % index,
      index += 1
      print >> outfile, '%5s' % ('%04x' % cp1),
      for rkey, keyinfos in references:
        match = any(cp1 in cmap for _, _, cmap in keyinfos)
        print >> outfile, rkey if match else ('-' * len(rkey)),
      print >> outfile, tkey,
      print >> outfile, unicode_data.age(cp1),
      name = unicode_data.name(cp1)
      if cp1 in emoji_only:
        name = '(emoji only) ' + name
      print >> outfile, name


def _generate_fontkey(targets, references, data_dir):
  lines = ['<p style="margin-bottom:5px"><b>Targets</b>']
  lines.append('<div style="margin-left:20px"><table class="key">')
  tid = 0
  for key, font, name, _ in targets:
    rel_font = path.relpath(font, data_dir) if font else '(no font)'
    lines.append(
        '<tr><th><a href="#target_%s">%s</a><td>%s<td>%s' % (
            tid, key, name, rel_font))
    tid += 1
  lines.append('</table></div>')

  lines.append('<p style="margin-bottom:5px"><b>References</b>')
  lines.append('<div style="margin-left:20px"><table class="key">')
  for key, keyinfos in references:
    for font, name, _ in keyinfos:
      rel_font = path.relpath(font, data_dir) if font else '(no font)'
      lines.append('<tr><th>%s<td>%s<td>%s' % (key, name, rel_font))
  lines.append('</table></div>')

  return '\n'.join(lines)


_nonalpha_re = re.compile(r'\W')
def replace_nonalpha(key):
  return _nonalpha_re.sub('_', key)


def _generate_styles(targets, references):
  face_pat = """@font-face {
    font-family: "%s"; src:url("file://%s")
  }"""

  facelines = []
  classlines = []
  for key, font, name, _ in targets:
    facelines.append(face_pat % (key, font))
    classlines.append(
        '.%s { font-family: "%s" }' % (replace_nonalpha(key), key))

  for key, keyinfos in references:
    index = 0
    for font, _, _ in keyinfos:
      if len(keyinfos) > 1:
        kname = '%s_%d' % (replace_nonalpha(key), index)
      else:
        kname = replace_nonalpha(key)
      index += 1
      if not font:
        classlines.append('.%s { font-size: 12pt }' % kname)
      else:
        facelines.append(face_pat % (kname, font))
        classlines.append('.%s { font-family: "%s" }' % (kname, kname))

  lines = []
  lines.extend(facelines)
  lines.append('')
  lines.extend(classlines)
  return '\n  '.join(lines)


def _generate_header(target, references):
  header_parts = ['<tr class="head"><th>CP']
  for r in references:
    header_parts.append('<th>' + r[0])
  header_parts.append('<th>' + target[0])
  header_parts.append('<th>Age<th>Name')
  return ''.join(header_parts)


def _generate_table(index, target, references, emoji_only):
  key, _, name, codes = target

  lines = ['<h3 id="target_%d">%s</h3>' % (index, name)]
  lines.append('<table>')
  header = _generate_header(target, references)
  linecount = 0
  for codepair in codes:
    if linecount % 20 == 0:
      lines.append(header)
    linecount += 1

    cp0 = codepair[0]
    cp1 = cp0 if len(codepair) == 1 else codepair[1]
    line = ['<tr>']
    line.append('<td class="code">U+%04x' % cp1)
    for rkey, keyinfos in references:
      cell_class = None
      cell_text = None
      index = 0
      for font, _, cmap in keyinfos:
        if cp1 in cmap:
          if len(keyinfos) > 1:
            cell_class = '%s_%d' % (rkey, index)
          else:
            cell_class = rkey
          cell_class = replace_nonalpha(cell_class)
          if font:
            cell_text = unichr(cp1)
          else:
            cell_text = ' * '
            cell_class += ' star'
          break
        index += 1
      if cell_class:
        line.append('<td class="%s">%s' % (cell_class, cell_text))
      else:
        line.append('<td>&nbsp;')
    line.append('<td class="%s">%s' % (replace_nonalpha(key), unichr(cp0)))
    line.append('<td class="age">%s' % unicode_data.age(cp1))
    name = unicode_data.name(cp1)
    if cp1 in emoji_only:
      name = '(emoji only) ' + name
    line.append('<td class="name">%s' % name)
    lines.append(''.join(line))
  lines.append('</table>')
  return '\n'.join(lines)


def generate_html(outfile, title, targets, references, data_dir):
  template = string.Template(_HTML_HEADER_TEMPLATE)
  styles = _generate_styles(targets, references)
  print >> outfile, template.substitute(title=title, styles=styles)

  print >> outfile, _generate_fontkey(targets, references, data_dir)

  emoji_only = (
      unicode_data.get_emoji() - unicode_data.get_unicode_emoji_variants())
  for index, target in enumerate(targets):
    print >> outfile, _generate_table(index, target, references, emoji_only)

  print >> outfile, _HTML_FOOTER


def generate(outfile, fmt, data_dir):
  if not path.isdir(data_dir):
    raise Exception('data dir "%s" does not exist' % data_dir)

  title, targets, references = _get_driver(data_dir)

  if fmt == 'txt':
    generate_text(outfile, title, targets, references, data_dir)
  elif fmt == 'html':
    generate_html(outfile, title, targets, references, data_dir)
  else:
    raise Exception('unrecognized format "%s"' % fmt)


def _call_generate(outfile, fmt, data_dir):
  if outfile:
    base, ext = path.splitext(outfile)
    if not ext:
      if not fmt:
        fmt = 'txt'
        ext = 'txt'
      else:
        ext = fmt
    elif not fmt:
      if ext not in ['html', 'txt']:
        raise Exception('don\'t understand "%s" format' % ext)
      fmt = ext
    elif ext != fmt:
      raise Exception('mismatching format "%s" and output extension "%s"' % (
          fmt, ext))
    outfile += '.' + ext
    print 'writing %s' % outfile
    with codecs.open(outfile, 'w', 'utf-8') as f:
      generate(f, fmt, data_dir)
  else:
    if not fmt:
      fmt = 'txt'
    generate(sys.stdout, fmt, data_dir)


def main():
  DEFAULT_OUT = 'dingbats_compare'

  parser = argparse.ArgumentParser()
  parser.add_argument(
      '-o', '--outfile', help='Path to output file (will use %s)' % DEFAULT_OUT,
      const=DEFAULT_OUT, metavar='file', nargs='?')
  parser.add_argument(
      '-t', '--output_type', help='output format (defaults based on outfile '
      'extension, else "txt")', choices=['txt', 'html'])
  parser.add_argument(
      '-d', '--data_dir', help='Path to directory containing fonts '
      'and data', metavar='dir', required=True)
  args = parser.parse_args()

  _call_generate(args.outfile, args.output_type, args.data_dir)


if __name__ == '__main__':
  main()
