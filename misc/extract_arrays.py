#!/usr/bin/env python3

'''
This script extracts the game arrays from "Game.js", then  sort and pretty print in files to help
compare the results between RAGS and rags2html.
'''

import sys
import re
import json
import os
import traceback

def print_err(msg):
    print(str(msg), file=sys.stderr)

# The only characters the json module expects to be escaped (without '/' though)
json_esc_set = set(['\\', '"', 'b', 't', 'n', 'r', 'f', 'u'])
def json_fix(data, stats=None):
    if stats != None:
        stats['empty'] = 0
        stats['sq_esc'] = 0
        stats['dq_fix'] = 0
        stats['bs_fix'] = 0

    pos = 0
    start = 0
    in_string = False
    need_value = False
    last_quote = None
    result = []
    while pos < len(data):
        c = data[pos]
        if need_value:
            need_value = False
            if c == ',' or c == ']':
                # json module does not expect empty elements, so replace them with null
                result.append(data[start:pos])
                result.append('null')
                start = pos
                if stats != None:
                    stats['empty'] += 1

        pos_inc = 1
        if in_string:
            if c == '"':
                in_string = False
                c2 = data[pos + 1]
                if last_quote is not None and c2 != ',' and c2 != ']':
                    # Unexpected end of string, rollback
                    print_err('Warning: fixing wrong double quote escaping at %d' % (last_quote[0] + 1,))
                    pos = last_quote[0]
                    result = result[:last_quote[1]]
                    result.append(data[last_quote[2]:pos])
                    result.append('\\\\')
                    start = pos + 1
                    pos_inc = 2
                    last_quote = None
                    if stats is not None:
                        stats['dq_fix'] += 1

            elif c == '\\':
                c2 = data[pos + 1]
                if c2 not in json_esc_set:
                    # json module only expects some characters to be escaped
                    if c2 == "'":
                        result.append(data[start:pos])
                        start = pos + 1
                        if stats != None:
                            stats['sq_esc'] += 1
                    else:
                        # RAGS does not escape the backslash character at all, so we might end here
                        print_err('Warning: not unescaping dubious "%s" character at %d' % (c2, pos + 1))
                        result.append(data[start:pos])
                        result.append('\\\\')
                        start = pos + 1
                        if stats != None:
                            stats['bs_fix'] += 1

                elif c2 == '"':
                    # As RAGS does not escape backslash, some double quotes can be escaped wrongly
                    # So keep track of last escaped double quote to rollback if needed
                    last_quote = (pos, len(result), start)

                pos_inc = 2
        elif c == '"':
            in_string = True
            last_quote = None
        elif c == ',':
            need_value = True

        pos += pos_inc

    if start < len(data):
        result.append(data[start:])

    return ''.join(result)

def process_file(fpath):
    print('[%s]' % (fpath,))

    with open(fpath, 'rt') as fh:
        out_folder = os.path.join(os.path.dirname(fpath), 'data')
        if not os.path.exists(out_folder):
            os.makedirs(out_folder)

        prev_line = None
        for line in fh:
            if prev_line is not None:
                # Fix wrong escaping of '\n' in RAGS
                line = prev_line + '<br>' + line
                prev_line = None

            m = re.match(r'\s*var (image|room|player|char|object|variable|timer|statusbar|layeredclothing)data\s*=\s*(.+)', line)
            if m is None:
                continue

            name = m.group(1) + 'data'
            data = m.group(2).rstrip('\r\n')
            if not data.endswith(';'):
                prev_line = line.rstrip('\r\n')
                continue

            # Remove ";"
            data = data[:-1]
            print('Found %s' % (name,))

            # Write raw data before parsing for debugging
            out_fpath_txt = os.path.join(out_folder, name + '.txt')
            with open(out_fpath_txt, 'wt') as out:
                out.write(data)

            stats = {}
            data = json_fix(data, stats)

            if any(stats.values()):
                print('  JSON fix stats: %s' % (stats,))

            try:
                data = json.loads(data)
            except json.decoder.JSONDecodeError:
                traceback.print_exc()
                continue

            if name == 'variabledata':
                # Sort by variable name
                data.sort(key=lambda var: var[4])
            elif name == 'playerdata':
                pass
            else:
                data.sort(key=str)

            out_fpath_json = os.path.join(out_folder, name + '.json')
            with open(out_fpath_json, 'wt') as out:
                out.write(json.dumps(data, sort_keys=True, indent=2))

            os.unlink(out_fpath_txt)

def main(argv):
    for path in argv[1:]:
        if os.path.isdir(path):
            for folder in ((path,), (path, 'js'), (path, 'data')):
                fpath = os.path.join(*(folder + ('Game.js',)))
                if os.path.exists(fpath):
                    break
                fpath = None

            if fpath is None:
                print_err('Error: cannot find "Game.js" in "%s"' % (path,))
                continue

            path = fpath

        process_file(path)

    return 0

if __name__ == '__main__':
    sys.exit(main(sys.argv))