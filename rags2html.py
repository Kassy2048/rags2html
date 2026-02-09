#!/usr/bin/env python3

'''
Convert RAGS game files into HTML games.
'''

import sys
import os
import re
import json
import datetime
import base64
import gzip
import shutil
import xml.etree.ElementTree as ET
from enum import Enum
from types import DynamicClassAttribute
import asyncio  # Using asyncio for web version
from copy import deepcopy

import sdf
from compat import Color, TextFont
from vendor.net_nrbf import File as NrbfFile

def print_err(msg):
    print(str(msg), file=sys.stderr)

def key_gen(key_str, val=129):
    key = bytearray(key_str.encode('ascii'))
    for i in range(len(key)):
        key[i] ^= val

    # Convert to utf-16 (not really)
    wkey = bytearray()
    for b in key:
        wkey.append(b)
        wkey.append(0)

    return wkey

def json_encode(v):
    if isinstance(v, datetime.datetime):
        # Convert to POSIX timestamp in ms (same as what JS uses)
        return round(v.timestamp() * 1000)
    raise TypeError('Object of type %s is not JSON serializable' % (type(v),))

# XML parsing and validation classes

class DictNode:
    def __init__(self, tag, children, xor=None):
        self.tag = tag
        self.childMap = {}
        for child in children:
            if child.tag in self.childMap:
                raise RuntimeError('child %s defined twice in %s' % (child.tag, self.tag))
            self.childMap[child.tag] = child

        self.xorMap = {}
        if xor is not None:
            id = 1
            for tags in xor:
                for tag in tags:
                    mask = self.xorMap.get(tag)
                    if mask is None:
                        mask = id
                    else:
                        mask |= id
                    self.xorMap[tag] = mask
                id <<= 1

    def convert(self, node):
        rv = {}
        xorMask = None
        xorNodes = set()

        if len(node.attrib) != 0:
            raise RuntimeError('unexpected node %s with attributes' % (node,))
        if node.text is not None and len(node.text):
            raise RuntimeError('unexpected node %s with text' % (node,))

        for child in node:
            if child.tag in rv:
                raise RuntimeError('child "%s" appear multiple times in %s' % (child.tag, node))

            childNode = self.childMap.get(child.tag)
            if childNode is None:
                raise RuntimeError('child "%s" unexpected in %s' % (child.tag, node))

            mask = self.xorMap.get(child.tag)
            if mask is not None:
                if xorMask is None:
                    xorMask = mask
                elif (xorMask & mask) == 0:
                    raise RuntimeError('child "%s" is incompatible with %s in %s'
                            % (child.tag, xorNodes, node))
                xorNodes.add(child.tag)

            data = childNode.convert(child)
            if data is not None:
                rv[child.tag] = data

        return rv if len(rv) > 0 else None

    def add(self, *children):
        for child in children:
            if child.tag in self.childMap:
                raise RuntimeError('child %s defined twice in %s' % (child.tag, self.tag))
            self.childMap[child.tag] = child
        return self

class TextNode:
    def __init__(self, tag):
        self.tag = tag

    def convert(self, node):
        if len(node.attrib) != 0:
            raise RuntimeError('unexpected node %s with attributes' % (node,))
        if len(list(node.items())) != 0:
            raise RuntimeError('unexpected node %s with children (%s)' % (node, list(node.items())))
        return node.text

class ListNode(DictNode):
    def convert(self, node):
        rv = []
        xorMask = None
        xorNodes = set()

        if len(node.attrib) != 0:
            raise RuntimeError('unexpected node %s with attributes' % (node,))
        if node.text is not None and len(node.text):
            raise RuntimeError('unexpected node %s with text' % (node,))

        for child in node:
            childNode = self.childMap.get(child.tag)
            if childNode is None:
                raise RuntimeError('child %s unexpected in %s (%s)' % (child.tag, node))

            mask = self.xorMap.get(child.tag)
            if mask is not None:
                if xorMask is None:
                    xorMask = mask
                elif (xorMask & mask) == 0:
                    raise RuntimeError('child "%s" is incompatible with %s in %s'
                            % (child.tag, xorNodes, node))
                xorNodes.add(child.tag)

            data = childNode.convert(child)
            if data is not None:
                rv.append({child.tag: data})

        return rv if len(rv) > 0 else None

XML_EnhancedInputData = DictNode('EnhancedInputData', [
    TextNode('BackgroundColor'),
    TextNode('TextColor'),
    TextNode('Imagename'),
    TextNode('UseEnhancedGraphics'),
    TextNode('AllowCancel'),
    TextNode('NewImage'),
    TextNode('TextFont'),
])

XML_CustomChoices = ListNode('CustomChoices', [
    DictNode('CustomChoice', [
        TextNode('Name'),
    ]),
])

XML_PassCommands = ListNode('PassCommands', [])
XML_FailCommands = ListNode('FailCommands', [])
XML_Command = DictNode('Command', [
    TextNode('CmdType'),
    TextNode('CommandText'),
    TextNode('Part2'),
    TextNode('Part3'),
    TextNode('Part4'),
    XML_EnhancedInputData,
    XML_CustomChoices,
])
XML_Condition = DictNode('Condition', [
    TextNode('Name'),
    ListNode('Checks', [
        DictNode('Check', [
            TextNode('CondType'),
            TextNode('CkType'),
            TextNode('Step2'),
            TextNode('Step3'),
            TextNode('Step4'),
        ]),
    ]),
    XML_PassCommands,
    XML_FailCommands,
])
XML_PassCommands.add(
    XML_Command,
    XML_Condition
)
XML_FailCommands.add(
    XML_Command,
    XML_Condition
)

XML_Action = DictNode('Action', [
    TextNode('Name'),
    TextNode('OverrideName'),
    TextNode('actionparent'),
    TextNode('Active'),
    TextNode('FailOnFirst'),
    TextNode('InputType'),
    TextNode('CustomChoiceTitle'),
    XML_CustomChoices,
    XML_EnhancedInputData,
    XML_PassCommands,
    XML_FailCommands,
    ListNode('Conditions', [
        XML_Condition,
    ]),
])

def xml_convert_action(data):
    # First 4 bytes store the decompression size
    try:
        compressed = not data.startswith('<Action>')
        if compressed:
            data = gzip.decompress(base64.b64decode(data)[4:]).decode('utf-8')
        else:
            data = data.rstrip('\x00')

        # print('-'*100)
        # print(data)

        # Convert XML data into a structure to be serialized with JSON
        root = ET.fromstring(data)

        return XML_Action.convert(root)
    except:
        print_err(data)
        print_err('compressed=%s' % (compressed,))
        raise

XML_VarArray = ListNode('ArrayItems', [
    TextNode('ArrayItem'),
])

def xml_convert_vararray(data, varType):
    varType = VarType(varType)
    if not (varType == VarType.VT_NUMBERARRAY or varType == VarType.VT_STRINGARRAY
            or varType == VarType.VT_DATETIMEARRAY):
        return None

    if len(data) == 0:
        return []

    try:
        root = ET.fromstring(data)
        if root.tag != 'ArrayItems':
            raise RuntimeError('unexpected root tag "%s" for VarArray' % (root.tag,))
        result = []
        for item in root:
            if item.tag != 'ArrayItem':
                raise RuntimeError('unexpected root tag "%s" for VarArray item' % (item.tag,))

            item = item.text
            if item is None:
                item = ''

            if item.find('*S*E*P*') != -1:
                # Array of array
                items = []
                for v in item.split('*S*E*P*'):
                    items.append(v)
                result.append(items)
            else:
                result.append(item)
        return result
    except:
        print_err(data)
        raise

class ActionCode:
    '''
    A class used to convert action logic into JS-like code.
    '''
    NEXT_ID = 0
    INTERACTIVE_CMDS = set([
        'CT_PAUSEGAME', 
        'CT_SETVARIABLE_NUMERIC_BYINPUT', 
        'CT_SETVARIABLEBYINPUT'
    ])

    def __init__(self, action, indent=''):
        self.action = action
        self.indent = indent

        self.FailOnFirst = action.get('bConditionFailOnFirst', None)  # v1
        if self.FailOnFirst is None:
            self.FailOnFirst = action.get('FailOnFirst', 'False') == 'True'

        self.text = ''

        self.id = ActionCode.NEXT_ID
        ActionCode.NEXT_ID += 1

        self.generate()

    def incr_indent(self):
        self.indent += '  '

    def decr_indent(self):
        self.indent = self.indent[:-2]

    def add_line(self, line=''):
        if len(line) > 0:
            self.text += self.indent + line + '\n'
        else:
            self.text += '\n'

    @staticmethod
    def param_quote(value):
        def repl(m):
            c = m.group(1)
            if c == '\n':
                return r'\n'
            elif c == "'":
                return r"\'"
            elif c == '\t':
                return r'\t'
            elif c == '\r':
                return r'\r'

        # Replace special GUID with their name
        if value == '00000000-0000-0000-0000-000000000001':
            return 'CURRENT_ROOM'
        elif value == '00000000-0000-0000-0000-000000000002':
            return 'VOID_ROOM'
        elif value == '00000000-0000-0000-0000-000000000004':
            return 'SELF_OBJECT'

        return ("'" + re.sub(r"(\n|\r|\t|')", repl, str(value)) + "'")

    def generate(self):
        # print(self.action)
        self.text = ''

        Conditions = self.action.get('Conditions', [])
        PassCommands = self.action.get('PassCommands', [])
        FailCommands = self.action.get('FailCommands', [])

        if len(Conditions) > 0:
            self.add_line('let actionPassed = %s;' % ('true' if self.FailOnFirst else 'false'))
            self.add_line()

            for condition in Conditions:
                condition = condition.get('Condition', condition)
                self.add_condition_code(condition, True)

            self.add_line()

            self.add_branch('actionPassed', PassCommands, FailCommands, True)

        elif len(PassCommands) > 0:
            self.add_commands_code(PassCommands)

        self.text = self.text.rstrip()

    def add_branch(self, testExpr, PassCommands, FailCommands, is_root=False, name=''):
        # Always show the check if this is not "actionPassed" in case it has side effects
        if len(PassCommands) > 0 or len(FailCommands) > 0 or testExpr != 'actionPassed':
            if len(name) > 0:
                self.add_line('// ' + re.sub(r'[\r\n]', ' ', name))

            self.add_line('if(' + testExpr + ') {')
            self.incr_indent()
            self.add_commands_code(PassCommands)

            if is_root and not self.FailOnFirst:
                if len(PassCommands) > 0:
                    self.add_line()
                self.add_line('actionPassed = true;')

            self.decr_indent()

            if len(FailCommands) > 0 or (is_root and self.FailOnFirst):
                self.add_line('} else {')
                self.incr_indent()
                self.add_commands_code(FailCommands)

                if is_root and self.FailOnFirst:
                    if len(FailCommands) > 0:
                        self.add_line()
                    self.add_line('actionPassed = false;')

                self.decr_indent()

            self.add_line('}')

    def add_condition_code(self, condition, is_root=False):
        Checks = condition.get('Checks', [])
        PassCommands = condition.get('PassCommands', [])
        FailCommands = condition.get('FailCommands', [])
        Name = condition.get('Name', condition.get('conditionname', ''))

        if len(Checks) > 0:
            code = ''

            for check in Checks:
                check = check.get('Check', check)
                CondType = check['CondType']
                Step2 = check.get('ConditionStep2', check.get('Step2'))
                Step3 = check.get('ConditionStep3', check.get('Step3'))
                Step4 = check.get('ConditionStep4', check.get('Step4'))

                if len(code) != 0:
                    if check['CkType'] == 'Or' or check['CkType'] == 2:
                        code += ' || '
                    else:
                        code += ' && '

                params = []
                if Step2 is not None:
                    params.append(self.param_quote(Step2))
                if Step3 is not None:
                    params.append(self.param_quote(Step3))
                if Step4 is not None:
                    params.append(self.param_quote(Step4))

                if CondType == 'CT_AdditionalDataCheck':
                    params.insert(0, self.param_quote(self.action['InputType']))

                code += CondType + '(' + ', '.join(params) + ')'

            if is_root and self.FailOnFirst:
                code = 'actionPassed && ' + code

            self.add_branch(code, PassCommands, FailCommands, is_root, name=Name)

        else:
            # Unexpected?
            self.add_commands_code(PassCommands)

    def add_commands_code(self, commands):
        first = True
        needNewline = False
        for commandOrCondition in commands:
            # print(commandOrCondition)
            condition = commandOrCondition.get('Condition')
            if condition is None and 'Checks' in commandOrCondition:
                condition = commandOrCondition  # v1
            if condition is not None:
                if not first:
                    self.add_line()
                first = False
                needNewline = True

                self.add_condition_code(condition)
                continue

            if needNewline:
                self.add_line()
            first = False
            needNewline = False

            command = commandOrCondition.get('Command', commandOrCondition)
            CmdType = command.get('cmdtype')  # v1
            if CmdType is None:
                CmdType = command['CmdType']
            CommandText = command.get('CommandText')
            Part2 = command.get('CommandPart2', command.get('Part2'))
            Part3 = command.get('CommandPart3', command.get('Part3'))
            Part4 = command.get('CommandPart4', command.get('Part4'))
            CustomChoices = command.get('CustomChoices', [])

            code = CmdType + '('

            params = []
            if CommandText is not None:
                params.append(self.param_quote(CommandText))
            if Part2 is not None:
                params.append(self.param_quote(Part2))
            if Part3 is not None:
                params.append(self.param_quote(Part3))
            if Part4 is not None:
                params.append(self.param_quote(Part4))
            if len(CustomChoices) > 0:
                # Only used with CT_SETVARIABLE_NUMERIC_BYINPUT and CT_SETVARIABLEBYINPUT
                choices = []
                for choice in CustomChoices:
                    if isinstance(choice, dict):
                        choices.append(self.param_quote(choice['CustomChoice']['Name']))
                    else:
                        # Old RAGS version
                        choices.append(self.param_quote(choice))
                params.append('[' + ', '.join(choices) + ']')

            code += ', '.join(params) + ');'

            self.add_line(code)

            # Add a new line after interaction commands
            if CmdType in ActionCode.INTERACTIVE_CMDS:
                needNewline = True

def js_str(val):
    return json.dumps(re.sub(r'\r?\n\r?', '<br>', str(val)))

def js_bool(val):
    return json.dumps(True if val else False)

def float_safe(txt):
    if isinstance(txt, float):
        return txt
    if txt is None or len(txt.strip()) == 0:
        # return 0.0
        return 0
    # XXX RAGS strips the decimal part on some numbers in arrays, but not all!
    return float(txt) if txt.find('.') != -1 else int(txt)

class VarType(Enum):
    VT_UNINITIALIZED = 0
    VT_NUMBER        = 1
    VT_STRING        = 2
    VT_DATETIME      = 3
    VT_NUMBERARRAY   = 4
    VT_STRINGARRAY   = 5
    VT_DATETIMEARRAY = 6

class Direction(Enum):
    Empty = 0
    North = 1
    South = 2
    East = 3
    West = 4
    Up = 5
    Down = 6
    NorthEast = 7
    NorthWest = 8
    SouthWest = 9
    SouthEast = 10
    In = 11
    Out = 12

class CharGender(Enum):
    Male = 0
    Female = 1
    Other = 2

class TimerType(Enum):
    TT_RUNALWAYS = 0
    TT_LENGTH = 1

class LocationType(Enum):
    LT_NULL = 0
    LT_IN_OBJECT = 1
    LT_ON_OBJECT = 2
    LT_ROOM = 3
    LT_PLAYER = 4
    LT_CHARACTER = 5
    LT_PORTAL = 6

class ActionInputType(Enum):
    _None=0
    Object=1
    Character=2
    ObjectOrCharacter=3
    Text=4
    Custom=5
    Inventory=6

    @DynamicClassAttribute
    def name(self):
        # Rename "_None" to "None"
        return 'None' if self.value == 0 else super().name

class CheckType(Enum):
    CT_Uninitialized = 0
    And = 1
    Or = 2

def create_game_js(game, images=[], rooms=[], characters=[], objects=[], variables=[], timers=[],
        statusbars=[], layers=[], player=[], rags_compat=False):
    '''
    Create "Game.js" from the game data structures.
    '''
    imagedata = []
    roomdata = []
    playerdata = []
    chardata = []
    objectdata = []
    variabledata = []
    timerdata = []
    statusbardata = []
    # layeredclothingdata = game.get('ClothingZoneLevels', 'Upper Body,Mid Body,Lower Body').split(',')
    layeredclothingdata = game.get('ClothingZoneLevels', '').split(',')

    now = datetime.datetime.now()

    # Default can be "Microsoft Sans Serif, 8.25pt" or "Times New Roman, 12pt"
    GameFont = TextFont.convert(game.get('GameFont', '(none)'), 'Microsoft Sans Serif, 8.25pt')

    def str_escape(text):
        return re.sub(r'\r?\n\r?', '<br>', str(text))

    def float_conv(val):
        # RAGS strips decimal part if it is 0
        if (val % 1) == 0:
            return int(val)
        return val

    def bool_conv(val):
        # RAGS write "0" instead of "0.0" for float values
        return str(val).lower() == 'true'

    # Debug variable to see where conversion failed
    _last_node = [None]
    _last_data = None

    def convert_action(action):
        _last_node[0] = action
        '''[
            str(Name),  # default="default"
            bool(Active),  # default=True
            str(OverrideName),
            str(ActionParent),  # default="None"
            bool(ConditionFailOnFirst),  # default=True
            str(InputType),
            str(CustomChoiceTitle),
            [
                # For each pass command
                convert_command_or_condition(),
            ],
            [
                # For each fail command
                convert_command_or_condition(),
            ],
            [
                # For each condition
                convert_condition(),
            ],
            [
                # For each custom choice
                str(Text),
            ],
            convert_enhanced_input_data(EnhancedInputData),
        ], ...'''
        action = action.get('Data', action)  # XML abstraction
        return [
            action['Name'],
            bool_conv(action['Active']),
            action.get('OverrideName', ''),
            action.get('actionparent', 'None'),
            bool_conv(action.get('FailOnFirst', True)),
            action.get('InputType', 'None'),
            action.get('CustomChoiceTitle', ''),
            [
                convert_command_or_condition(Pass) for Pass in action.get('PassCommands', [])
            ],
            [
                convert_command_or_condition(Fail) for Fail in action.get('FailCommands', [])
            ],
            [
                convert_condition(Node.get('Condition', Node)) for Node in action.get('Conditions', [])
            ],
            [
                (Node if isinstance(Node, str) else Node['CustomChoice']['Name'])
                        for Node in action.get('CustomChoices', [])
            ],
            convert_enhanced_input_data(action.get('EnhancedInputData', {})),
        ]

    def convert_command_or_condition(c):
        _last_node[0] = c
        Command = c.get('Command')
        if Command is None:
            return convert_condition(c['Condition'])
        return convert_command(Command)

    def convert_command(command):
        _last_node[0] = command
        '''[
            "CMD",
            str(CmdType),
            str(CommandName),
            str_escape(CommandText),
            str(CommandPart2),
            str(CommandPart3),
            str_escape(CommandPart4),
            [
                # For each custom choice
                str(Text),
            ],
            convert_enhanced_input_data(EnhancedInputData),
        ]'''
        return [
            'CMD',
            command['CmdType'],
            command.get('CommandName', ''),
            str_escape(command.get('CommandText', '')),
            command.get('Part2', ''),
            command.get('Part3', ''),
            str_escape(command.get('Part4', '')),
            [
                (Node if isinstance(Node, str) else Node['CustomChoice']['Name'])
                        for Node in command.get('CustomChoices', [])
            ],
            convert_enhanced_input_data(command.get('EnhancedInputData', {})),
        ]

    def convert_condition(condition):
        _last_node[0] = condition
        '''[
            "COND",
            str_escape(Name),
            [
                # For each Check
                convert_check(),
            ],
            [
                # For each PassCommand
                convert_command_or_condition(),
            ],
            [
                # For each FailCommand
                convert_command_or_condition(),
            ],
        ]'''
        return [
            'COND',
            str_escape(condition.get('Name', '')),
            [
                convert_check(node.get('Check', node)) for node in condition.get('Checks', [])
            ],
            [
                convert_command_or_condition(c) for c in condition.get('PassCommands', [])
            ],
            [
                convert_command_or_condition(c) for c in condition.get('FailCommands', [])
            ],
        ]

    def convert_check(check):
        _last_node[0] = check
        '''[
            str(CondType),  # default=CT_Item_Held_By_Player
            str(CkType),
            str_escape(Step2),
            str_escape(Step3),
            str_escape(Step4),
        ]'''
        return [
            check['CondType'],
            check['CkType'],
            str_escape(check.get('Step2', '')),
            str_escape(check.get('Step3', '')),
            str_escape(check.get('Step4', '')),
        ]

    def convert_enhanced_input_data(data, BackgroundColor=None, TextColor=None):
        _last_node[0] = data
        if BackgroundColor is None:
            BackgroundColor = data.get('BackgroundColor', '')
        if TextColor is None:
            TextColor = data.get('TextColor', '')
        return [
            str(Color.toArgb(BackgroundColor, 'A=140, R=255, G=255, B=255')),
            str(Color.toArgb(TextColor, 'Black')),
            data.get('Imagename', ''),
            bool_conv(data.get('UseEnhancedGraphics', True)),
            bool_conv(data.get('AllowCancel', True)),  # XXX Not in table?
            data.get('NewImage', ''),
            # XXX Default TextFont should probably be "Times New Roman Bold, 12pt", not GameFont
            TextFont.convert(data.get('TextFont', '(none)'), GameFont)
        ]

    try:
        for image in images:
            _last_data = image
            # [Name,GroupName,[':'.join(LayeredImages)],[str(BackgroundColor.Argb),str(TextColor.Argb),Imagename,UseEnhancedGraphics,AllowCancel,NewImage,str(TextFont)]
            imagedata.append([
                image.get('Name', image.get('TheName', '')),
                image.get('GroupName', ''),
                # XXX RAGS join the images with ':' but JS code expects ','
                [':'.join(image.get('LayeredImages', []))] if rags_compat
                        else [','.join(image.get('LayeredImages', []))],
                # XXX RAGS forces colors to 0 for images, probably a bug...
                convert_enhanced_input_data(image, BackgroundColor='0' if rags_compat else None,
                        TextColor='0' if rags_compat else None),
            ])

        for room in rooms:
            _last_data = room
            '''[
                str_escape(SDesc),
                str_escape(Description),
                str_escape(Name),
                str(Group),  # default="None"
                str(RoomPic),  # default="None"
                str(LayeredRoomPic),  # default="None"
                bool(EnterFirstTime),
                bool(LeaveFirstTime),
                str(UniqueID),
                [
                    # For each exit
                    [
                        str(Direction),
                        bool(Active),
                        str(DestinationRoom),
                        str(PortalObjectName),  # default="<None>"
                    ],
                ],
                [
                    # For each property
                    [
                        str(Name),
                        str(Value),
                    ],
                ],
                [
                    # For each action
                    convert_action(),
                ],
            ]'''
            roomdata.append([
                str_escape(room.get('SDesc', '')),
                str_escape(room.get('Description', '')),
                str_escape(room.get('Name', '')),
                room.get('Group', 'None'),
                room.get('RoomPic', 'None'),
                room.get('LayeredRoomPic', 'None'),
                bool_conv(room.get('EnterFirstTime', False)),
                bool_conv(room.get('LeaveFirstTime', False)),
                room['UniqueID'],
                [
                    [
                        Direction(exit.get('Direction', 0)).name,
                        bool_conv(exit.get('Active', False)),
                        exit.get('DestinationRoom', ''),
                        exit.get('PortalObjectName', '<None>'),
                    ] for exit in room.get('Exits', [])
                    # TODO Remove exits with empty DestinationRoom and PortalObjectName?
                ],
                [
                    [
                        prop.get('Name', ''),
                        prop.get('Value', ''),
                    ] for prop in room.get('Properties', [])
                ],
                [
                    convert_action(action) for action in room.get('Actions', [])
                ],
            ])

        for character in characters:
            _last_data = character
            '''[
                str(Charname),
                str(CharnameOverride),
                str_escape(Description),
                str(CharGender),  # default=Other
                str(CurrentRoom),  # default=00000000-0000-0000-0000-000000000002
                bool(AllowInventoryInteraction),
                str(CharPortrait),
                [
                    # For each property
                    [
                        str(Name),
                        str(Value),
                    ],
                ],
                [
                    # For each action
                    [
                        convert_action(),
                    ],
                ],
            ]'''
            chardata.append([
                character['Charname'],
                character.get('CharnameOverride', ''),
                str_escape(character.get('Description', '')),
                CharGender(character.get('CharGender', CharGender.Other)).name,
                character.get('CurrentRoom', '00000000-0000-0000-0000-000000000002'),
                bool_conv(character.get('AllowInventoryInteraction', False)),
                character.get('CharPortrait', ''),
                [
                    [
                        prop.get('Name', ''),
                        prop.get('Value', ''),
                    ] for prop in character.get('Properties', [])
                ],
                [
                    convert_action(action) for action in character.get('Actions', [])
                ],
            ])

        for timer in timers:
            _last_data = timer
            '''[
                str(Name),
                str(TType),
                bool(Active),
                bool(Restart),
                int(TurnNumber),
                int(Length),
                bool(LiveTimer),
                int(TimerSeconds),  # default=1
                [
                    # For each property
                    [
                        str(Name),
                        str(Value),
                    ],
                ],
                [
                    # For each action
                    [
                        convert_action(),
                    ],
                ],
            ]'''
            timerdata.append([
                timer['Name'],
                TimerType(timer['TType']).name,
                bool_conv(timer.get('Active', False)),
                bool_conv(timer.get('Restart', False)),
                timer.get('TurnNumber', 0),
                timer.get('Length', 0),
                bool_conv(timer.get('LiveTimer', False)),
                timer.get('TimerSeconds', 1),
                [
                    [
                        prop.get('Name', ''),
                        prop.get('Value', ''),
                    ] for prop in timer.get('Properties', [])
                ],
                [
                    convert_action(action) for action in timer.get('Actions', [])
                ],
            ])

        _last_data = player
        '''[
            str(Name),
            str_escape(Description),
            str(StartingRoom),
            str(PlayerGender),
            str(PlayerLayeredImage),
            bool(PromptForName),
            bool(PromptForGender),
            str(PlayerPortrait),
            bool(EnforceWeight),
            float(WeightLimit),  # default=100.5
            [
                # For each property
                [
                    str_escape(Name),
                    str_escape(Value),
                ],
            ],
            [
                # For each action
                [
                    convert_action(),
                ],
            ],
        ]'''
        playerdata = [
            player['Name'],
            str_escape(player['Description']),
            player['StartingRoom'],
            CharGender(player['PlayerGender']).name,
            player['PlayerLayeredImage'],
            bool_conv(player['PromptForName']),
            bool_conv(player['PromptForGender']),
            player['PlayerPortrait'],
            bool_conv(player['EnforceWeight']),
            float_conv(player.get('WeightLimit', 100.5)),
            [
                [
                    str_escape(prop.get('Name', '')),
                    str_escape(prop.get('Value', '')),
                ] for prop in player.get('Properties', [])
            ],
            [
                convert_action(action) for action in player.get('Actions', [])
            ],
        ]

        for obj in objects:
            _last_data = obj
            '''[
                str_escape(Name),
                str(UniqueID),
                str(LocationType),
                str(LocationName),
                str_escape(Description),
                str_escape(SDesc),
                str(Preposition),  # default="a"
                bool(Carryable),
                bool(Wearable),
                bool(Openable),
                bool(Lockable),
                bool(Enterable),
                bool(Readable),
                bool(Container),
                float(Weight),
                bool(Worn),
                bool(Read),
                bool(Locked),
                bool(Open),
                bool(Visible),  # default=True
                [
                    ':'.join(LayeredZoneLevels)
                ],
                [
                    # For each property
                    [
                        str_escape(Name),
                        str_escape(Value),
                    ],
                ],
                [
                    # For each action
                    [
                        convert_action(),
                    ],
                ],
            ]'''
            objectdata.append([
                str_escape(obj['Name']),
                obj['UniqueID'],
                LocationType(obj.get('LocationType', 0)).name,
                obj.get('LocationName', ''),
                str_escape(obj.get('Description', '')),
                str_escape(obj.get('SDesc', '')),
                obj.get('Preposition', 'a'),
                bool_conv(obj.get('Carryable', False)),
                bool_conv(obj.get('Wearable', False)),
                bool_conv(obj.get('Openable', False)),
                bool_conv(obj.get('Lockable', False)),
                bool_conv(obj.get('Enterable', False)),
                bool_conv(obj.get('Readable', False)),
                bool_conv(obj.get('Container', False)),
                float_conv(obj.get('Weight', 0.0)),
                bool_conv(obj.get('Worn', False)),
                bool_conv(obj.get('Read', False)),
                bool_conv(obj.get('Locked', False)),
                bool_conv(obj.get('Open', False)),
                bool_conv(obj.get('Visible', True)),
                # XXX RAGS joins the layers with ':' but JS code expects an array
                #     (RAGS joins them with an empty string actually because of a bug)
                [''.join(obj.get('ItemLayeredZoneLevels', []))] if rags_compat
                            else obj.get('ItemLayeredZoneLevels', []),
                [
                    [
                        str_escape(prop.get('Name', '')),
                        str_escape(prop.get('Value', '')),
                    ] for prop in obj.get('Properties', [])
                ],
                [
                    convert_action(action) for action in obj.get('Actions', [])
                ],
            ])

        for variable in variables:
            _last_data = variable
            # Convert array variables
            varType = VarType(variable.get('VarType', 0))
            if (varType == VarType.VT_NUMBERARRAY or varType == VarType.VT_STRINGARRAY
                    or varType == VarType.VT_DATETIMEARRAY):
                is_string = varType != VarType.VT_NUMBERARRAY
                VarArray = []
                for v in variable['VarArray']:
                    if isinstance(v, list):
                        VarArray.append([x if is_string else float_safe(x) for x in v])
                    else:
                        VarArray.append(v if is_string else float_safe(v))
            else:
                VarArray = None

            # Convert dtDateTime to a representation without zero padding
            # (expect for minutes and seconds)
            dtDateTime = variable.get('dtDateTime', now)
            # Convert hour here because '%l' is not officialy supported by Python
            # and '%I' adds 0 padding
            if dtDateTime.hour == 0:
                # 12 AM
                hour = 12
            elif dtDateTime.hour > 12:
                # PM
                hour = dtDateTime.hour - 12
            else:
                # AM
                hour = dtDateTime.hour
            dtDateTime = ('{d.month}/{d.day}/{d.year} {h}:{d.minute:02}:{d.second:02} {d:%p}'
                    .format(d=dtDateTime, h=hour))

            # [NumType,str(Min),str(Max),String,varname,GroupName,EnforceRestrictions,
            #  str(dtDateTime),str(vartype),str(VarComment),VarArray,[[customProperty.Name,str(customProperty.Value)],...]]
            variabledata.append([
                float_conv(variable.get('NumType', 0)),
                str(variable.get('Min', 0.0)),
                str(variable.get('Max', 100.0)),
                str_escape(variable.get('String', '')),
                str_escape(variable.get('VarName', '')),
                variable.get('GroupName', ''),
                bool_conv(variable.get('EnforceRestrictions', False)),
                dtDateTime,
                varType.name,
                str_escape(variable.get('VarComment', '')),
                VarArray,
                [[p['Name'], p['Value']] for p in variable.get('VariableProperties', [])],
            ])

        for info in statusbars:
            _last_data = info
            # [Name, Text, bVisible, Width]
            statusbardata.append([
                info.get('Name', ''),
                info.get('Text', ''),
                bool_conv(info.get('Visible', True)),
                info.get('Width', 0),
            ])

    except Exception:
        import pprint
        pp = pprint.PrettyPrinter(indent=2, stream=sys.stderr)
        print_err('While converting:\n')
        pp.pprint(_last_data)
        pp.pprint(_last_node[0])

        raise

    return '''var TheGame = null;

function game() {
    this.Title = "None";
    this.OpeningMessage = "None";
    this.HideMainPicDisplay = false;
    this.UseInlineImages = false;
    this.HidePortrait = false;
    this.AuthorName = "None";
    this.GameVersion = "0.0";
    this.GameInformation = "None";
    this.bgMusic = false;
    this.bRepeatbgMusic = false;
    this.Rooms = new Array();
    this.Player = new player();
    this.Characters = new Array();
    this.Objects = new Array();
    this.Images = new Array();
    this.Variables=new Array();
    this.Timers=new Array();
    this.StatusBarItems=new Array();
    this.LayeredClothingZones=new Array();
    this.RagsVersion = 0.0;

}

function SetupGameData() {
    TheGame = new game();
    TheGame.Title = %s;
    TheGame.OpeningMessage = %s;
    TheGame.HideMainPicDisplay = %s;
    TheGame.UseInlineImages = %s;
    TheGame.HidePortrait = %s;
    TheGame.AuthorName = %s;
    TheGame.GameVersion = %s;
    TheGame.GameInformation = %s;
    TheGame.bgMusic = %s;
    TheGame.bRepeatbgMusic = %s;
    TheGame.RagsVersion = %s;
    var numimages = 0;

    var imagedata=%s;
    var roomdata=%s;
    var playerdata=%s;
    var chardata=%s;
    var objectdata=%s;
    var variabledata=%s;
    var timerdata=%s;
    var statusbardata=%s;
    var layeredclothingdata=%s;

    for(var _i=0;_i<imagedata.length;_i++)
    {
        TheGame.Images.length = numimages + 1;
        TheGame.Images[numimages] = SetupImageData(imagedata[_i]);
        numimages++;
    }

    numimages = 0;
    for(_i=0;_i<roomdata.length;_i++)
    {
        TheGame.Rooms.length = numimages + 1;
        TheGame.Rooms[numimages] = SetupRoomData(roomdata[_i]);
        numimages++;
    };

    TheGame.Player = SetupPlayerData(playerdata);
    numimages = 0;
    for(_i=0;_i<chardata.length;_i++)
    {
        TheGame.Characters.length = numimages + 1;
        TheGame.Characters[numimages] = SetupCharacterData(chardata[_i]);
        numimages++;
    };

    numimages = 0;
    for(_i=0;_i<objectdata.length;_i++)
    {
        TheGame.Objects.length = numimages + 1;
        TheGame.Objects[numimages] = SetupObjectData(objectdata[_i]);
        numimages++;
    };

    numimages = 0;
    for(_i=0;_i<variabledata.length;_i++)
    {
        TheGame.Variables.length = numimages + 1;
        TheGame.Variables[numimages] = SetupVariableData(variabledata[_i]);
        numimages++;
    };

    numimages = 0;
    for(_i=0;_i<timerdata.length;_i++)
    {
        TheGame.Timers.length = numimages + 1;
        TheGame.Timers[numimages] = SetupTimerData(timerdata[_i]);
        numimages++;
    };

    numimages = 0;
    for(_i=0;_i<statusbardata.length;_i++)
    {
        TheGame.StatusBarItems.length = numimages + 1;
        TheGame.StatusBarItems[numimages] = SetupStatusBarData(statusbardata[_i]);
        numimages++;
    };

    numimages = 0;
    for(_i=0;_i<layeredclothingdata.length;_i++)
    {
        TheGame.LayeredClothingZones.length = numimages + 1;
        TheGame.LayeredClothingZones[numimages] = layeredclothingdata[_i];
        numimages++;
    };

    return TheGame;
}
''' % (
            js_str(game.get('Title', '')),
            js_str(game.get('OpeningMessage', '')),
            js_bool(game.get('HideMainPicDisplay', False)),
            js_bool(game.get('UseInlineImages', False)),
            js_bool(game.get('HidePortrait', False)),
            js_str(game.get('AuthorName', '')),
            js_str(game.get('GameVersion', '')),
            js_str(game.get('GameInformation', '')),
            js_str(game.get('bgMusic', '')),
            js_bool(game.get('RepeatbgMusic', False)),
            float('.'.join(game.get('ObjectVersionNumber', '0.0').split('.')[0:2])),
            json.dumps(imagedata,           default=json_encode, separators=(',', ':')),
            json.dumps(roomdata,            default=json_encode, separators=(',', ':')),
            json.dumps(playerdata,          default=json_encode, separators=(',', ':')),
            json.dumps(chardata,            default=json_encode, separators=(',', ':')),
            json.dumps(objectdata,          default=json_encode, separators=(',', ':')),
            json.dumps(variabledata,        default=json_encode, separators=(',', ':')),
            json.dumps(timerdata,           default=json_encode, separators=(',', ':')),
            json.dumps(statusbardata,       default=json_encode, separators=(',', ':')),
            json.dumps(layeredclothingdata, default=json_encode, separators=(',', ':')),
    )

def escape_ctrl(msg):
    '''Escape control characters for debug print'''
    ctrl_chars = {
        '\n': '\\n',
        '\r': '\\r',
        '\t': '\\t',
        '\\': '\\\\',
    }
    def repl(m):
        return ctrl_chars[m.group(0)]

    return re.sub(r'[\r\n\t\\]', repl, msg)

TABLE_KEYS = {
    # Specify column name to use a key for tables whose first column should not be the key
    'ItemGroups': 'Name',
    'MediaGroups': 'Name',
    'ItemLayeredZoneLevels': 'ItemID',
    'PlayerProperties': 'Name',
    'VariableGroups': 'Name',
}

ACTION_KEYS = {
    'RoomActions': 'RoomID',
    'ItemActions': 'ItemID',
    'CharacterActions': 'Charname',
    'TimerActions': 'Name',
    'PlayerActions': None,
}

PROPERTIES_KEYS = {
    'CharacterProperties': 'Charname',
    'ItemProperties': 'ItemID',
    'RoomProperties': 'RoomID',
    'TimerProperties': 'TimerName',
    'VariableProperties': 'VarName',
    'ItemLayeredZoneLevels': ('ItemID', 'Data')
}

async def process_file(fpath, keys, args, progress=None):
        if args.out_dir is not None:
            dir_name = os.path.splitext(os.path.basename(fpath))[0]
            out_dir = os.path.join(args.out_dir, dir_name)
        else:
            out_dir = os.path.splitext(fpath)[0]
        media_dir = os.path.join(out_dir, 'images')
        if args.data_debug:
            data_dir = os.path.join(out_dir, 'data')

        key = None
        for k in keys:
            if sdf.check_key(fpath, k):
                key = k
                break

        if key is None:
            # Games made with older RAGS versions (< 1.7?)
            # The whole game file is encrypted with AES-256-CBC
            # Its content is made from BinaryFormatter, not a sqlce DB

            # Decrypt and load the whole file in memory as RAGS does (files are small enough)

            print('Decrypting file...')
            if progress is not None:
                progress(0.0, 'Decrypting file...', -1)

            from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

            key = bytes.fromhex('B4BDC259B1104A6531F8109C851BCF9AD09BDD208851C9CBAB782AEC356CC1E3')
            iv = bytes.fromhex('31F8109C851BCF9A203D6C71A7BD1487')
            decryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()

            # Decrypt the file in memory
            # (old game files are small so they should fit in memory)
            with open(fpath, 'rb') as fh:
                data = decryptor.update(fh.read()) + decryptor.finalize()

            if args.decrypt_only:
                out_fpath = fpath + '.bin'
                print('Writing decrypted file to "%s"...' % (out_fpath,))
                with open(out_fpath, 'wb') as out:
                    out.write(data)

                return

            game_fields = set(('GameFont', 'ObjectVersionNumber', 'OpeningMessage',
                    'Title', 'GamePassword', 'bPasswordProtected', 'HideMainPicDisplay',
                    'UseInlineImages', 'HidePortrait', 'AuthorName', 'GameVersion',
                    'GameInformation', 'bgMusic', 'bRepeatbgMusic'))
            game_tables = set(('PictureList', 'VariableList', 'StatusBarItems', 'RoomList',
                    'CharacterList', 'TimerList', 'ObjectList', 'ThePlayer',
                    'LayeredClothingZones', 'RoomGroups'))

            print('Loading file...')
            if progress is not None:
                progress(0.2, 'Loading file...', -1)

            with NrbfFile.from_bytes(data) as nrfb:
                game = nrfb.convert()

                if args.info:
                    print('')
                    for fieldName in game_fields:
                        if fieldName not in game:
                            continue

                        if fieldName == 'GamePassword':
                            # Password is stored as cleartext in some old files, do not show it
                            # (the password hash is stored instead in more recent versions)
                            continue

                        v = game[fieldName]
                        if isinstance(v, str):
                            v = escape_ctrl(v)
                        print('%s: %s' % (fieldName, v))

                    return

                make_folder(out_dir)
                make_folder(media_dir)
                if args.data_debug:
                    make_folder(data_dir)

                # Extract medias and remove data from game
                print('Extracting medias...')
                if progress is not None:
                    progress(0.4, 'Extracting medias...', -1)
                media_fpaths = set()
                for entry in game['PictureList']:
                    # {'TheImage': {'Data': [int, ...]}, 'TheName': str}
                    # Move content into a file
                    name = entry['TheName']
                    TheImage = entry.get('TheImage')
                    if TheImage is None:
                        img_data = bytes(entry['ImageData'])
                        del entry['ImageData']
                    else:
                        # Old format
                        img_data = bytes(TheImage['Data'])
                        del TheImage['Data']

                    fname = re.sub(r'[/\\]', '', name)
                    if fname != name:
                        # TODO Add an Name to Path mapping in JS
                        print_err('Warning: renamed "%s" to "%s"' % (name, fname))
                        await asyncio.sleep(0)

                    media_fpath = os.path.join(media_dir, fname)
                    if media_fpath in media_fpaths:
                        print_err('Warning: file "%s" exist multiple times' % (media_fpath))
                        await asyncio.sleep(0)
                        continue
                    media_fpaths.add(media_fpath)

                    if not args.skip_media:
                        with open(media_fpath, 'wb') as out:
                            out.write(img_data)
                    entry['FilePath'] = 'images/' + fname

                def getID(obj, *propNames):
                    # For very old games, there is no UID, so use object name instead
                    for name in propNames:
                        id = obj.get(name)
                        if id is not None:
                            return id

                    raise RuntimeError('Failed to find ID using %s: %s' % (propNames, obj))

                # Fix circular references

                for entry in game['RoomList']:
                    for exit in entry['Exits']:
                        DestinationRoom = exit['DestinationRoom']
                        if DestinationRoom is None:
                            exit['DestinationRoom'] = ''
                        elif not isinstance(DestinationRoom, str):
                            # A reference to the Room object is sometimes used instead of its UID
                            exit['DestinationRoom'] = getID(DestinationRoom, 'UniqueID', 'Name')

                # Extract raw JSON files from the game for debug
                if args.data_debug:
                    game_data = {}
                    for k, v in game.items():
                        if isinstance(v, (list, dict)) and k != 'GameFont' and not re.search(r'[/\\:]', k):
                            if k not in game_tables:  # DEBUG
                                print_err('WARNING: unexpected game object "%s" (%s)' % (k, v))
                            with open(os.path.join(data_dir, k + '.json'), 'wt') as out:
                                out.write(json.dumps(v, default=json_encode, sort_keys=True, indent=2))

                            if isinstance(v, list) and len(v) > 0:
                                entry = v[0]
                                has_actions = isinstance(entry, dict) and 'Actions' in entry
                            else:
                                # ThePlayer
                                has_actions = isinstance(v, dict) and 'Actions' in v

                            if has_actions:
                                out_path = os.path.join(data_dir, k + '-code.js')
                                with open(out_path, 'wt') as out:
                                    # Creating JS files instead of JSON so we can load them from file:// URLs
                                    out.write('rags.tables.%s = ' % (k,));

                                    actionCodes = {}
                                    data_code = deepcopy(v)

                                    def process_action(action, indent):
                                        action_data = action
                                        code = ActionCode(action_data, indent)
                                        if len(code.text) > 0:
                                            actionCodes[code.id] = code
                                            action['execute'] = '__ACTION_CODE_%d__' % (code.id)

                                        # Remove properties that have been converted to code
                                        if 'Conditions' in action_data:
                                            del action_data['Conditions']
                                        if 'PassCommands' in action_data:
                                            del action_data['PassCommands']
                                        if 'FailCommands' in action_data:
                                            del action_data['FailCommands']

                                    if isinstance(v, dict):
                                        for action in data_code['Actions']:
                                            process_action(action, '        ')
                                        # FIXME Also do StartingRoom.Actions
                                    else:
                                        for entry in data_code:
                                            for action in entry['Actions']:
                                                process_action(action, '          ')

                                    content = json.dumps(data_code, default=json_encode, sort_keys=True, indent=2)

                                    def repl_execute(m):
                                        indent = m.group(1)
                                        prefix = m.group(2)
                                        id = int(m.group(3))
                                        return (indent + prefix + 'function() {\n'
                                                + actionCodes[id].text + '\n'
                                                + indent + '}')

                                    content = re.sub(r'( +)("execute":\s*)"__ACTION_CODE_(\d+)__"', repl_execute, content)
                                    out.write(content)

                        else:
                            if k not in game_fields:  # DEBUG
                                print_err('WARNING: unexpected game property "%s" (%s)' % (k, v))
                            game_data[k] = v

                    with open(os.path.join(data_dir, 'Game.json'), 'wt') as out:
                        out.write(json.dumps(game_data, default=json_encode, sort_keys=True, indent=2))

                # Convert "game" into arguments for create_game_js()

                ThePlayer = game['ThePlayer']
                StartingRoom = ThePlayer['StartingRoom']
                if not isinstance(StartingRoom, str):
                    # A reference to the Room object is sometimes used instead of its UID
                    ThePlayer['StartingRoom'] = getID(StartingRoom, 'UniqueID', 'Name')

                print('Converting old format...')
                if progress is not None:
                    progress(0.6, 'Converting old format...', -1)

                action_fields = set(('Conditions', 'CustomChoiceTitle', 'CustomChoices',
                        'EnhancedInputData', 'FailCommands', 'InputType', 'PassCommands',
                        'bActive', 'bConditionFailOnFirst', 'name'))
                def js_convert_action(entry):
                    for k in entry.keys():  # DEBUG
                        if k not in action_fields:
                            print_err('WARNING: action field "%s" was unexpected (%s: %s)'
                                    % (k, type(entry[k]), entry[k]))
                    #   {Name, Active, OverrideName, actionparent, FailOnFirst, InputType,
                    #   CustomChoiceTitle, PassCommands, FailCommands, Conditions, CustomChoices,
                    #   EnhancedInputData}
                    return {
                        'Name': entry['name'],
                        'Active': entry['bActive'],
                        'FailOnFirst': entry['bConditionFailOnFirst'],
                        'InputType': ActionInputType(entry['InputType']).name,
                        'CustomChoiceTitle': entry.get('CustomChoiceTitle', 'Please make a selection:'),
                        'PassCommands': [js_convert_command_or_condition(c) for c in entry['PassCommands']],
                        'FailCommands': [js_convert_command_or_condition(c) for c in entry['FailCommands']],
                        'Conditions': [js_convert_condition(c) for c in entry['Conditions']],
                        'CustomChoices': entry['CustomChoices'],
                        'EnhancedInputData': js_convert_enhanced_input_data(entry.get('EnhancedInputData', {})),
                    }

                def js_convert_command_or_condition(entry):
                    if entry.get('Checks') is not None:
                        return {'Condition': js_convert_condition(entry)}
                    return {'Command': js_convert_command(entry)}

                command_fields = set(('cmdtype', 'CommandName', 'CommandPart2', 'CommandPart3',
                        'CommandPart4', 'CommandText', 'CustomChoices', 'EnhancedInputData'))
                def js_convert_command(entry):
                    for k in entry.keys():  # DEBUG
                        if k not in command_fields:
                            print_err('WARNING: command field "%s" was unexpected (%s: %s)'
                                    % (k, type(entry[k]), entry[k]))

                    return {
                        'CmdType': entry['cmdtype'],
                        'CommandName': entry['CommandName'],
                        'CommandText': entry['CommandText'],
                        'Part2': entry['CommandPart2'],
                        'Part3': entry['CommandPart3'],
                        'Part4': entry['CommandPart4'],
                        'CustomChoices': entry['CustomChoices'],  # TOCHECK
                        'EnhancedInputData': js_convert_enhanced_input_data(entry.get('EnhancedInputData', {})),
                    }

                condition_fields = set(('Checks', 'conditionname', 'FailCommands', 'PassCommands'))
                def js_convert_condition(entry):
                    for k in entry.keys():  # DEBUG
                        if k not in condition_fields:
                            print_err('WARNING: condition field "%s" was unexpected (%s: %s)'
                                    % (k, type(entry[k]), entry[k]))

                    return {
                        'Name': entry['conditionname'],
                        'Checks': [js_convert_check(c) for c in entry['Checks']],
                        'PassCommands': [js_convert_command_or_condition(c) for c in entry['PassCommands']],
                        'FailCommands': [js_convert_command_or_condition(c) for c in entry['FailCommands']],
                    }

                check_fields = set(('CkType', 'ConditionStep2', 'ConditionStep3', 'ConditionStep4',
                        'CondType'))
                def js_convert_check(entry):
                    for k in entry.keys():  # DEBUG
                        if k not in check_fields:
                            print_err('WARNING: check field "%s" was unexpected (%s: %s)'
                                    % (k, type(entry[k]), entry[k]))

                    return {
                        'CondType': entry['CondType'],
                        'CkType': CheckType(entry['CkType']).name,
                        'Step2': entry['ConditionStep2'],
                        'Step3': entry['ConditionStep3'],
                        'Step4': entry['ConditionStep4'],
                    }

                eid_fields = set(('BackgroundColor', 'Imagename', 'NewImage', 'TextColor',
                        'TextFont', 'UseEnhancedGraphics'))
                def js_convert_enhanced_input_data(entry):
                    for k in entry.keys():  # DEBUG
                        if k not in eid_fields:
                            print_err('WARNING: EID field "%s" was unexpected (%s: %s)'
                                    % (k, type(entry[k]), entry[k]))

                    return {
                        'BackgroundColor': entry.get('BackgroundColor', ''),
                        'TextColor': entry.get('TextColor', ''),
                        'Imagename': entry.get('Imagename', ''),
                        'UseEnhancedGraphics': entry.get('UseEnhancedGraphics', True),
                        'NewImage': entry.get('NewImage', ''),
                        'TextFont': entry.get('TextFont', '(none)'),
                    }

                js_game = {
                    'Title': game['Title'],
                    'OpeningMessage': game['OpeningMessage'],
                    'ObjectVersionNumber': game['ObjectVersionNumber'],
                    'GameFont': game.get('GameFont', 'Microsoft Sans Serif, 8.25pt'),
                    'ClothingZoneLevels': ','.join(game.get('LayeredClothingZones', ['Upper Body', 'Mid Body', 'Lower Body'])),
                    'HideMainPicDisplay': game.get('HideMainPicDisplay', False),
                    'UseInlineImages': game.get('UseInlineImages', False),
                    'HidePortrait': game.get('HidePortrait', False),
                    'AuthorName': game.get('AuthorName', ''),
                    'GameVersion': game.get('GameVersion', ''),
                    'GameInformation': game.get('GameInformation', ''),
                    'bgMusic': game.get('bgMusic', ''),
                    'RepeatbgMusic': game.get('RepeatbgMusic', ''),
                }

                images = []
                images_fields = set(('TheName', 'TheImage', 'LayeredImages', 'FilePath'))
                for entry in game['PictureList']:
                    for k in entry.keys():  # DEBUG
                        if k not in images_fields:
                            print_err('WARNING: image field "%s" was unexpected (%s: %s)'
                                    % (k, type(entry[k]), entry[k]))
                    # {Name, GroupName, LayeredImages, BackgroundColor, TextColor, ImageName,
                    #  UseEnhancedGraphics, AllowCancel, NewImage, TextFont}
                    images.append({
                        'Name': entry['TheName'],
                        'LayeredImages': entry.get('LayeredImages', []),
                    })

                variables = []
                variables_fields = set(('varname', 'vartype', 'VarComment', 'VarArray', 'sString',
                        'dtDateTime', 'dNumType', 'dMin', 'dMax', 'CustomProperties',
                        'bEnforceRestrictions'))
                for entry in game['VariableList']:
                    for k in entry.keys():  # DEBUG
                        if k not in variables_fields:
                            print_err('WARNING: variable field "%s" was unexpected (%s: %s)'
                                    % (k, type(entry[k]), entry[k]))
                    # {VarType, VarArray, dtDateTime, NumType, Min, Max, String, VarName,
                    # GroupName, EnforceRestrictions, VarComment, VariableProperties}
                    variables.append({
                        'VarType': entry['vartype'],
                        'VarArray': entry.get('VarArray', None),
                        'dtDateTime': entry['dtDateTime'],
                        'NumType': entry['dNumType'],
                        'Min': entry.get('dMin', 0.0),
                        'Max': entry.get('dMax', 100.0),
                        'String': entry['sString'],
                        'VarName': entry['varname'],
                        'EnforceRestrictions': entry.get('bEnforceRestrictions', False),
                        'VarComment': entry.get('VarComment', ''),
                        'VariableProperties': entry.get('CustomProperties', []),
                    })

                statusbars = []
                statusbars_fields = set(('Name', 'Text', 'Width'))
                for entry in game['StatusBarItems']:
                    for k in entry.keys():  # DEBUG
                        if k not in statusbars_fields:
                            print_err('WARNING: statusbar field "%s" was unexpected (%s: %s)'
                                    % (k, type(entry[k]), entry[k]))
                    # {Name, Text, Visible, Width}
                    statusbars.append({
                        'Name': entry['Name'],
                        'Text': entry['Text'],
                        'Width': entry['Width'],
                    })

                rooms = []  # RoomList
                rooms_fields = set(('Actions', 'bEnterFirstTime', 'bLeaveFirstTime',
                        'CustomProperties', 'Description', 'Exits', 'Group', 'LayeredRoomPic',
                        'Name', 'RoomPic', 'SDesc', 'UniqueID'))
                for entry in game['RoomList']:
                    for k in entry.keys():  # DEBUG
                        if k not in rooms_fields:
                            print_err('WARNING: room field "%s" was unexpected (%s: %s)'
                                    % (k, type(entry[k]), entry[k]))

                    exits = []
                    for exit in entry['Exits']:
                        exits.append({
                            'Direction': exit['Direction'],
                            'Active': exit['bActive'],
                            'DestinationRoom': exit['DestinationRoom'],
                            'PortalObjectName': exit['PortalObjectName'],
                        })

                    # {SDesc, Description, Name, Group, RoomPic, LayeredRoomPic, EnterFirstTime,
                    #   LeaveFirstTime, UniqueID, Exits: [{Direction, Active, DestinationRoom,
                    #   PortalObjectName}], Properties: [{Name, Value}], Actions: []}
                    rooms.append({
                        'SDesc': entry['SDesc'],
                        'Description': entry['Description'],
                        'Name': entry['Name'],
                        'Group': entry.get('Group', 'None'),
                        'RoomPic': entry['RoomPic'],
                        'LayeredRoomPic': entry.get('LayeredRoomPic', 'None'),
                        'EnterFirstTime': entry['bEnterFirstTime'],
                        'LeaveFirstTime': entry['bLeaveFirstTime'],
                        'UniqueID': getID(entry, 'UniqueID', 'Name'),
                        'Exits': exits,
                        'Properties': entry.get('CustomProperties', []),
                        'Actions': [js_convert_action(action) for action in entry['Actions']],
                    })


                characters = []  # CharacterList
                characters_fields = set(('Actions', 'bAllowInventoryInteraction',
                        'bEnterFirstTime', 'bLeaveFirstTime', 'CharGender', 'CharnameOverride',
                        'Charname', 'CurrentRoom', 'CustomProperties', 'Description', 'Inventory'))
                for entry in game['CharacterList']:
                    for k in entry.keys():  # DEBUG
                        if k not in characters_fields:
                            print_err('WARNING: character field "%s" was unexpected (%s: %s)'
                                    % (k, type(entry[k]), entry[k]))

                    characters.append({
                        'Charname': entry['Charname'],
                        'CharnameOverride': entry.get('CharnameOverride', ''),
                        'Description': entry['Description'],
                        'CharGender': entry['CharGender'],
                        'CurrentRoom': entry['CurrentRoom'],
                        'AllowInventoryInteraction': entry.get('bAllowInventoryInteraction', False),
                        'Properties': entry.get('CustomProperties', []),
                        'Actions': [js_convert_action(action) for action in entry['Actions']],
                    })

                timers = []  # TimerList
                timers_fields = set(('Actions', 'Active', 'CustomProperties', 'Length',
                        'LiveTimer', 'Name', 'Restart', 'TimerSeconds', 'TType', 'TurnNumber'))
                # The order of timers is important, do not change it!
                for entry in game['TimerList']:
                    for k in entry.keys():  # DEBUG
                        if k not in timers_fields:
                            print_err('WARNING: timer field "%s" was unexpected (%s: %s)'
                                    % (k, type(entry[k]), entry[k]))

                    timers.append({
                        'Name': entry['Name'],
                        'TType': entry['TType'],
                        'Active': entry['Active'],
                        'Restart': entry['Restart'],
                        'TurnNumber': entry['TurnNumber'],
                        'Length': entry['Length'],
                        'LiveTimer': entry.get('LiveTimer', False),
                        'TimerSeconds': entry.get('TimerSeconds', 1),
                        'Properties': entry.get('CustomProperties', []),
                        'Actions': [js_convert_action(action) for action in entry['Actions']],
                    })

                objects = []  # ObjectList
                objects_fields = set(('Actions', 'bCarryable', 'bContainer', 'bEnterable',
                        'bEntered', 'bEnterFirstTime', 'bLeaveFirstTime', 'bLockable', 'bLocked',
                        'bOpenable', 'bOpen', 'bReadable', 'bRead', 'bVisible', 'bWearable',
                        'bWorn', 'CustomProperties', 'description', 'dWeight', 'LayeredZoneLevels',
                        'locationname', 'locationtype', 'name', 'preposition', 'sdesc',
                        'UniqueIdentifier'))
                for entry in game['ObjectList']:
                    for k in entry.keys():  # DEBUG
                        if k not in objects_fields:
                            print_err('WARNING: object field "%s" was unexpected (%s: %s)'
                                    % (k, type(entry[k]), entry[k]))

                    objects.append({
                        'Name': entry['name'],
                        'UniqueID': getID(entry, 'UniqueIdentifier', 'name'),
                        'LocationType': entry['locationtype'],
                        'LocationName': entry['locationname'],
                        'Description': entry['description'],
                        'SDesc': entry['sdesc'],
                        'Preposition': entry.get('preposition', 'a'),
                        'Carryable': entry['bCarryable'],
                        'Wearable': entry['bWearable'],
                        'Openable': entry['bOpenable'],
                        'Lockable': entry['bLockable'],
                        'Enterable': entry['bEnterable'],
                        'Readable': entry['bReadable'],
                        'Container': entry['bContainer'],
                        'Weight': entry['dWeight'],
                        'Worn': entry['bWorn'],
                        'Read': entry['bRead'],
                        'Locked': entry['bLocked'],
                        'Open': entry['bOpen'],
                        'Visible': entry.get('bVisible', True),
                        'ItemLayeredZoneLevels': entry.get('LayeredZoneLevels', []),
                        'Properties': entry.get('CustomProperties', []),
                        'Actions': [js_convert_action(action) for action in entry['Actions']],
                    })

                player_fields = set(('Actions', 'bEnforceWeight', 'bPromptForGender',
                        'bPromptForName', 'CustomProperties', 'Description', 'dWeightLimit',
                        'Name', 'PlayerGender', 'PlayerLayeredImage', 'PlayerPortrait',
                        'StartingRoom', 'CurrentRoom'))
                for k, v in ThePlayer.items():  # DEBUG
                    if k not in player_fields:
                        print_err('WARNING: player field "%s" was unexpected (%s: %s)'
                                % (k, type(v), v))

                player = {
                    'Name': ThePlayer['Name'],
                    'Description': ThePlayer['Description'],
                    'StartingRoom': ThePlayer['StartingRoom'],  # CurrentRoom?
                    'PlayerGender': ThePlayer['PlayerGender'],
                    'PlayerLayeredImage': ThePlayer.get('PlayerLayeredImage', ''),
                    'PromptForName': ThePlayer['bPromptForName'],
                    'PromptForGender': ThePlayer['bPromptForGender'],
                    'PlayerPortrait': ThePlayer['PlayerPortrait'],
                    'EnforceWeight': ThePlayer['bEnforceWeight'],
                    'WeightLimit': ThePlayer['dWeightLimit'],
                    'Properties': ThePlayer.get('CustomProperties', []),
                    'Actions': [js_convert_action(action) for action in ThePlayer['Actions']],
                }

                game = js_game

        else:
            row = None
            try:
                print('Loading file...')
                if progress is not None:
                    progress(0, 'Loading file...', -1)
                await asyncio.sleep(0)
                if args.decrypt_only:
                    sdf.DataBase(fpath, key, _decrypt_only=True)
                    return

                with sdf.DataBase(fpath, key) as db:
                    if args.info:
                        table = db.tables['GameData']
                        page = db.readPage(table.pageId)
                        if page is None:
                            raise RuntimeError('cannot read TABLE page for %s' % (table,))
                        tablePage = sdf.TablePage(page, db)
                        row = table.extractRow(tablePage.getRecord(0), sortByIndex=True)
                        print()
                        for k, v in row.items():
                            if isinstance(v, sdf.LvData):
                                v = v.extract(db)
                            if isinstance(v, str):
                                v = escape_ctrl(v)
                            print('%s: %s' % (k, v))
                        return

                    make_folder(out_dir)
                    make_folder(media_dir)
                    if args.data_debug:
                        make_folder(data_dir)

                    game = None
                    images = None
                    variables = None
                    variableProperties = None
                    statusbars = None
                    rooms = None
                    roomExits = None
                    roomProperties = None
                    roomActions = None
                    characters = None
                    characterActions = None
                    characterProperties = None
                    timers = None
                    timerActions = None
                    timerProperties = None
                    objects = None
                    objectActions = None
                    objectProperties = None
                    objectLayers = None
                    player = None
                    playerActions = None
                    playerProperties = None

                    for table_num, table in enumerate(db.tables.values()):
                        skip_media = args.skip_media and table.name == 'Media'

                        print('Extracting %s...' % (table.name,))
                        if progress is not None:
                            start_progress = 0.1 + 0.7 * table_num / len(db.tables)
                            progress_step = 0.7 * 1 / len(db.tables)
                            progress_task = 'Extracting %s...' % (table.name,)
                            progress(start_progress, progress_task, -1)
                        await asyncio.sleep(0)

                        if re.search(r'[/\\:]', table.name):
                            raise RuntimeError('dubious table name "%s"' % (table.name,))

                        data = {}
                        is_action = table.name.endswith('Actions')

                        page = db.readPage(table.pageId)
                        if page is None:
                            raise RuntimeError('cannot read TABLE page for %s' % (table,))
                        tablePage = sdf.TablePage(page, db)
                        media_fpaths = set()
                        rows = []
                        for idx, record in enumerate(tablePage):
                            if progress is not None:
                                cur_progress = start_progress + progress_step * idx / tablePage.getCount()
                                progress(cur_progress, progress_task, idx, tablePage.getCount())
                            await asyncio.sleep(0)

                            if record is None:
                                continue

                            row = table.extractRow(record, sortByIndex=True)
                            entry = {}
                            for name, value in row.items():
                                if isinstance(value, sdf.LvData):
                                    if not (skip_media and name == 'Data'):
                                        value = value.extract(db)

                                if is_action and name == 'Data':
                                    value = xml_convert_action(value)

                                entry[name] = value

                            if table.name == 'Media':
                                # Move content into a file
                                fname = re.sub(r'[/\\]', '', entry['Name'])
                                if fname != entry['Name']:
                                    # TODO Add an Name to Path mapping in JS
                                    print_err('Warning: renamed "%s" to "%s"' % (entry['Name'], fname))
                                    await asyncio.sleep(0)

                                media_fpath = os.path.join(media_dir, fname)
                                if media_fpath in media_fpaths:
                                    print_err('Warning: file "%s" exist multiple times' % (media_fpath))
                                    await asyncio.sleep(0)
                                    continue
                                media_fpaths.add(media_fpath)

                                if not skip_media:
                                    with open(media_fpath, 'wb') as out:
                                        out.write(entry['Data'])
                                del entry['Data']
                                entry['FilePath'] = 'images/' + fname

                            rows.append(entry)

                        # print(rows)

                        if table.name == 'Variables':
                            # Convert VarArray from XML
                            for row in rows:
                                row['VarArray'] = xml_convert_vararray(row['VarArray'], row['VarType'])

                        if table.name == 'GameData' or table.name == 'Player':
                            if len(rows) != 1:
                                raise RuntimeError('%s table must only contain 1 row (not %d)'
                                        % (table.name, len(rows),))
                            data = rows[0]

                        elif table.name in ACTION_KEYS:
                            objectIdName = ACTION_KEYS[table.name]
                            for row in rows:
                                if objectIdName is None:
                                    # For PlayerActions (there is only 1 player)
                                    actions = data
                                else:
                                    objectId = row[objectIdName]
                                    actions = data.get(objectId)
                                    if actions is None:
                                        actions = data[objectId] = {}

                                name = row['Data']['Name']
                                if name in actions:
                                    print_err(actions[name])
                                    print_err('-'*50)
                                    print_err(row)
                                    raise RuntimeError('multiple actions "%s" for "%s" in "%s"'
                                            % (name, objectId, table.name))

                                actions[name] = row

                        elif table.name in PROPERTIES_KEYS:
                            keys = PROPERTIES_KEYS[table.name]
                            if type(keys) is tuple:
                                key1, key2 = keys
                            else:
                                key1 = keys
                                key2 = 'Name'

                            for row in rows:
                                objectId = row[key1]
                                properties = data.get(objectId)
                                if properties is None:
                                    properties = data[objectId] = {}

                                name = row[key2]
                                if name in properties:
                                    print_err(properties[name])
                                    print_err(row)
                                    print_err('Warning: multiple properties "%s" for "%s" in "%s"'
                                            % (name, objectId, table.name))
                                    # Ignore it as RAGS stops lookup at first match in list
                                else:
                                    properties[name] = row

                        elif table.name == 'RoomExits':
                            # RoomID: {direction: row, ...}
                            for row in rows:
                                roomId = row['RoomID']
                                direction = row['Direction']
                                exits = data.get(roomId)
                                if exits is None:
                                    exits = data[roomId] = {}
                                if direction in exits:
                                    raise RuntimeError('multiple exits "%s" for "%s" in "%s"'
                                            % (direction, roomId, table.name))
                                exits[direction] = row

                        elif table.name == 'StatusBarItems':
                            data = sorted(rows, key=lambda row: row['ID'])

                        else:
                            # Use first column as the table key by default
                            key_col = TABLE_KEYS.get(table.name, table.columns[0].name)

                            for row in rows:
                                row_key = row[key_col]
                                if row_key in data:
                                    print_err('key "%s" found multiple times in %s' % (row_key, table.name))
                                    await asyncio.sleep(0)
                                    continue

                                data[row_key] = row

                        if args.data_debug:
                            out_path = os.path.join(data_dir, table.name + '.js')
                            with open(out_path, 'wt') as out:
                                # Creating JS files instead of JSON so we can load them from file:// URLs
                                out.write('rags.tables.%s = ' % (table.name,));
                                out.write(json.dumps(data, default=json_encode, sort_keys=True, indent=2))

                            if(table.name.endswith('Actions')):
                                out_path = os.path.join(data_dir, table.name + '-code.js')
                                with open(out_path, 'wt') as out:
                                    # Creating JS files instead of JSON so we can load them from file:// URLs
                                    out.write('rags.tables.%s = ' % (table.name,));

                                    actionCodes = {}
                                    data_code = deepcopy(data)

                                    def process_action(action, indent):
                                        action_data = action['Data']
                                        code = ActionCode(action_data, indent)
                                        if len(code.text) > 0:
                                            actionCodes[code.id] = code
                                            action['execute'] = '__ACTION_CODE_%d__' % (code.id)

                                        # Remove properties that have been converted to code
                                        if 'Conditions' in action_data:
                                            del action_data['Conditions']
                                        if 'PassCommands' in action_data:
                                            del action_data['PassCommands']
                                        if 'FailCommands' in action_data:
                                            del action_data['FailCommands']

                                    if(table.name == 'PlayerActions'):
                                        for action in data_code.values():
                                            process_action(action, '      ')
                                    else:
                                        for entry in data_code.values():
                                            for action in entry.values():
                                                process_action(action, '        ')

                                    content = json.dumps(data_code, default=json_encode, sort_keys=True, indent=2)

                                    def repl_execute(m):
                                        indent = m.group(1)
                                        prefix = m.group(2)
                                        id = int(m.group(3))
                                        return (indent + prefix + 'function() {\n'
                                                + actionCodes[id].text + '\n'
                                                + indent + '}')

                                    content = re.sub(r'( +)("execute":\s*)"__ACTION_CODE_(\d+)__"', repl_execute, content)
                                    out.write(content)

                        if table.name == 'GameData':
                            game = rows[0]
                        elif table.name == 'Media':
                            images = rows
                        elif table.name == 'StatusBarItems':
                            statusbars = rows

                        elif table.name == 'Variables':
                            variables = rows
                        elif table.name == 'VariableProperties':
                            variableProperties = data

                        elif table.name == 'Rooms':
                            rooms = list(data.values())
                        elif table.name == 'RoomExits':
                            roomExits = data
                        elif table.name == 'RoomProperties':
                            roomProperties = data
                        elif table.name == 'RoomActions':
                            roomActions = data

                        elif table.name == 'Characters':
                            characters = list(data.values())
                        elif table.name == 'CharacterProperties':
                            characterProperties = data
                        elif table.name == 'CharacterActions':
                            characterActions = data

                        elif table.name == 'Timer':
                            timers = list(data.values())
                        elif table.name == 'TimerProperties':
                            timerProperties = data
                        elif table.name == 'TimerActions':
                            timerActions = data

                        elif table.name == 'Items':
                            objects = list(data.values())
                        elif table.name == 'ItemProperties':
                            objectProperties = data
                        elif table.name == 'ItemActions':
                            objectActions = data
                        elif table.name == 'ItemLayeredZoneLevels':
                            objectLayers = data

                        elif table.name == 'Player':
                            player = data
                        elif table.name == 'PlayerProperties':
                            playerProperties = data
                        elif table.name == 'PlayerActions':
                            playerActions = data


                print('COVER: ' + db.pageCoverStats())
                await asyncio.sleep(0)

            except:
                if sdf.DEBUG_TRACE:
                    print_err('---------- DEBUG TRACE: begin ----------')
                    for msg in sdf.debug_trace.history:
                        print_err(msg)
                    print_err('')
                    print_err('lastPage: %s' % (sdf.debug_trace.lastPage,))
                    print_err('lastTable: %s' % (sdf.debug_trace.lastTable,))
                    print_err('lastRow: %s' % (row,))
                    print_err('---------- DEBUG TRACE: end ----------')
                raise

            if None in (game, images, statusbars, variables, variableProperties,
                    rooms, roomExits, roomProperties, roomActions,
                    characters, characterActions, characterProperties,
                    timers, timerActions, timerProperties,
                    objects, objectActions, objectProperties, objectLayers,
                    player, playerActions, playerProperties
                    ):
                raise RuntimeError('missing some tables')

            # Merge some tables

            for v in variables:
                props = variableProperties.get(v['VarName'])
                if props is None:
                    v['VariableProperties'] = []
                    continue
                v['VariableProperties'] = [props[k] for k in props.keys()]

            for room in rooms:
                id = room['UniqueID']
                room['Exits'] = list(roomExits.get(id, {}).values())
                room['Properties'] = list(roomProperties.get(id, {}).values())
                room['Actions'] = list(roomActions.get(id, {}).values())

            for character in characters:
                name = character['Charname']
                character['Properties'] = list(characterProperties.get(name, {}).values())
                character['Actions'] = list(characterActions.get(name, {}).values())

            # The order of timers is important, do not change it!
            for timer in timers:
                name = timer['Name']
                timer['Properties'] = list(timerProperties.get(name, {}).values())
                timer['Actions'] = list(timerActions.get(name, {}).values())

            for obj in objects:
                id = obj['UniqueID']
                obj['Properties'] = list(objectProperties.get(id, {}).values())
                obj['Actions'] = list(objectActions.get(id, {}).values())
                obj['ItemLayeredZoneLevels'] = list(objectLayers.get(id, {}).keys())

            player['Properties'] = list(playerProperties.values())
            player['Actions'] = list(playerActions.values())

        print('Converting game data to JS...')
        if progress is not None:
            progress(0.8, 'Converting game data to JS...', -1)
        await asyncio.sleep(0)

        game_js = create_game_js(game, images=images, variables=variables, statusbars=statusbars,
                rooms=rooms, characters=characters, timers=timers, objects=objects, player=player,
                rags_compat=args.rags_compat)

        print('Copying Regalia files...')
        if progress is not None:
            progress(0.9, 'Copying Regalia files...', -1)
        await asyncio.sleep(0)

        vendor_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'vendor')
        regalia_path = os.path.join(vendor_path, 'regalia')
        shutil.copytree(regalia_path, out_dir, dirs_exist_ok=True)

        # Remove .git file due to the regalia folder being a Git submodule
        git_path = os.path.join(out_dir, '.git')
        if os.path.isfile(git_path):
            os.remove(git_path)

        def copy_missing(src, dst, *args, **kwargs):
            '''Only copy file if target does not exist already'''
            if os.path.exists(dst):
                return
            return shutil.copy2(src, dst, *args, **kwargs)

        rags_path = os.path.join(vendor_path, 'rags')
        shutil.copytree(os.path.join(rags_path, 'images'), media_dir, dirs_exist_ok=True,
                copy_function=copy_missing)

        out_path = os.path.join(out_dir, 'regalia', 'game', 'Game.js')
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, 'wt') as out:
            out.write(game_js)

def make_folder(path):
    if not os.path.exists(path):
        os.makedirs(path)
    elif not os.path.isdir(path):
        raise RuntimeError('"%s" already exists and is not a folder' % (path,))

async def main(argv, progress=None):
    import argparse

    parser = argparse.ArgumentParser(description='Convert RAG files into HTML game')
    parser.add_argument('rag_file', nargs='+')
    parser.add_argument('--skip-media', action='store_true', help='do not extract media files')
    parser.add_argument('-t', '--trace', type=int, help='trace history size (default: 0)', default=0)
    parser.add_argument('--data-debug', action='store_true', help='create debug JS files in the "data" folder')
    parser.add_argument('--info', action='store_true', help='only show game info')
    parser.add_argument('--decrypt-only', action='store_true', help='only decrypt the game file (for debugging)')
    parser.add_argument('--rags-compat', action='store_true', help='produce JS code as close as what RAGS produces')
    parser.add_argument('-o', '--out-dir', help='base output directory (default: game file folder)')

    args = parser.parse_args(args=argv[1:])

    if args.trace > 0:
        sdf.DEBUG_TRACE = True
        sdf.DEBUG_TRACE_LEN = args.trace
    else:
        sdf.DEBUG_TRACE = False

    keys = (key_gen('F1$asDDFHappy'), key_gen('DBPassword'))
    # Old versions use "DBPassword"

    for fpath in args.rag_file:
        try:
            print('[%s]' % (fpath,))
            await asyncio.create_task(process_file(fpath, keys, args, progress=progress))
        except Exception:
            import traceback
            traceback.print_exc()
            print_err('ERROR in %s' % (fpath,))

        if len(args.rag_file) > 0:
            print('')
            await asyncio.sleep(0)

    return 0

if __name__ == '__main__':
    sys.exit(asyncio.run(main(sys.argv)))