#!/usr/bin/env python3

from enum import Enum
from collections import namedtuple
import struct
import pprint
import datetime

class RecordType(Enum):
    SerializedStreamHeader = 0
    ClassWithId = 1
    SystemClassWithMembers = 2
    ClassWithMembers = 3
    SystemClassWithMembersAndTypes = 4
    ClassWithMembersAndTypes = 5
    BinaryObjectString = 6
    BinaryArray = 7
    MemberPrimitiveTyped = 8
    MemberReference = 9
    ObjectNull = 10
    MessageEnd = 11
    BinaryLibrary = 12
    ObjectNullMultiple256 = 13
    ObjectNullMultiple = 14
    ArraySinglePrimitive = 15
    ArraySingleObject = 16
    ArraySingleString = 17
    MethodCall = 21
    MethodReturn = 22

class BinaryType(Enum):
    Primitive = 0
    String = 1
    Object = 2
    SystemClass = 3
    Class = 4
    ObjectArray = 5
    StringArray = 6
    PrimitiveArray = 7

class BinaryArrayType(Enum):
    Single = 0
    Jagged = 1
    Rectangular = 2
    SingleOffset = 3
    JaggedOffset = 4
    RectangularOffset = 5

class PrimitiveType(Enum):
    Boolean = 1
    Byte = 2
    Char = 3
    Decimal = 5
    Double = 6
    Int16 = 7
    Int32 = 8
    Int64 = 9
    SByte = 10
    Single = 11
    TimeSpan = 12
    DateTime = 13
    UInt16 = 14
    UInt32 = 15
    UInt64 = 16
    Null = 17
    String = 18

def readstruct(f, s):
    s = '<' + s
    return struct.unpack(s, f.read(struct.calcsize(s)))

def readvarstr(f):
    n = 0
    v = 0
    while 1:
        c = ord(f.read(1))
        n += (c & 0x7f) << v
        if c & 0x80:
            v += 7
        else:
            break
    return f.read(n).decode('utf-8')

def indentstr(s, i):
    return '\n'.join(' '*i + line for line in s.split('\n'))

LIBRARIES = {}
OBJECTS = {}

class SerializedStreamHeader(namedtuple('SerializedStreamHeader', 'TopId HeaderId MajorVersion MinorVersion')):
    @classmethod
    def fromfile(cls, f):
        return cls(*readstruct(f, 'iiii'))

class BinaryLibrary(namedtuple('BinaryLibrary', 'LibraryId LibraryName')):
    @classmethod
    def fromfile(cls, f):
        libraryid, = readstruct(f, 'i')
        libraryname = readvarstr(f)
        ret = cls(libraryid, libraryname)
        LIBRARIES[libraryid] = ret
        return ret

class ClassInfo(namedtuple('ClassInfo', 'ObjectId Name MemberCount MemberNames')):
    @classmethod
    def fromfile(cls, f):
        objid, = readstruct(f, 'i')
        name = readvarstr(f)
        membercount, = readstruct(f, 'i')
        members = [readvarstr(f) for _ in range(membercount)]
        return cls(objid, name, membercount, members)

class ClassTypeInfo(namedtuple('ClassTypeInfo', 'TypeName LibraryId')):
    @classmethod
    def fromfile(cls, f):
        name = readvarstr(f)
        libraryid, = readstruct(f, 'i')
        return cls(name, libraryid)

def AdditionalTypeInfo(f, type):
    if type in (BinaryType.Primitive, BinaryType.PrimitiveArray):
        info = PrimitiveType(ord(f.read(1)))
    elif type == BinaryType.SystemClass:
        info = readvarstr(f)
    elif type == BinaryType.Class:
        info = ClassTypeInfo.fromfile(f)
    else:
        info = None
    return info

class MemberTypeInfo(namedtuple('MemberTypeInfo', 'BinaryTypeEnums AdditionalInfos')):
    @classmethod
    def fromfile(cls, f, classinfo):
        types = [BinaryType(ord(f.read(1))) for _ in range(classinfo.MemberCount)]
        infos = [AdditionalTypeInfo(f, t) for t in types]
        return cls(types, infos)

class ClassWithMembersAndTypes(namedtuple('ClassWithMembersAndTypes', 'ClassInfo MemberTypeInfo LibraryId')):
    @classmethod
    def fromfile(cls, f):
        classinfo = ClassInfo.fromfile(f)
        memberinfo = MemberTypeInfo.fromfile(f, classinfo)
        libraryid, = readstruct(f, 'i')
        ret = cls(classinfo, memberinfo, libraryid)
        OBJECTS[classinfo.ObjectId] = ret
        ret.memberdata = ret.read_members(f)
        return ret

    def read_members(self, f):
        mi = self.MemberTypeInfo
        return [read_typed_member(f, mi.BinaryTypeEnums[i], mi.AdditionalInfos[i]) for i in range(self.ClassInfo.MemberCount)]

    def format_member(self, i, memberdata=None):
        if memberdata is None:
            memberdata = self.memberdata
        type = self.MemberTypeInfo.BinaryTypeEnums[i]
        info = self.MemberTypeInfo.AdditionalInfos[i]
        if type == BinaryType.Class:
            t = info.TypeName
        elif type == BinaryType.SystemClass:
            t = info
        elif type == BinaryType.Primitive:
            t = info.name
        elif type == BinaryType.PrimitiveArray:
            t = info.name + '[]'
        else:
            t = type.name
        return t + ' ' + self.ClassInfo.MemberNames[i] + '\n' + indentstr(str(memberdata[i]), 4)

    def __str__(self):
        ci = self.ClassInfo
        memberstr = indentstr('\n'.join(self.format_member(i) for i in range(ci.MemberCount)), 4)
        return '%s LibraryId=%d ObjectId=%d Name=%s:\n%s' % (type(self).__name__, self.LibraryId, ci.ObjectId, ci.Name, memberstr)

class ClassWithMembers(namedtuple('ClassWithMembers', 'ClassInfo LibraryId')):
    @classmethod
    def fromfile(cls, f):
        classinfo = ClassInfo.fromfile(f)
        libraryid, = readstruct(f, 'i')
        ret = cls(classinfo, libraryid)
        OBJECTS[classinfo.ObjectId] = ret
        ret.memberdata = ret.read_members(f)
        return ret

    def read_members(self, f):
        return [read_unknown_member(f, self.ClassInfo.Name, self.ClassInfo.MemberNames[i]) for i in range(self.ClassInfo.MemberCount)]

    def format_member(self, i, memberdata=None):
        if memberdata is None:
            memberdata = self.memberdata
        return self.ClassInfo.MemberNames[i] + ' = ' + str(memberdata[i])

    def __str__(self):
        ci = self.ClassInfo
        memberstr = indentstr('\n'.join(self.format_member(i) for i in range(ci.MemberCount)), 4)
        return '%s LibraryId=%d ObjectId=%d Name=%s:\n%s' % (type(self).__name__, self.LibraryId, ci.ObjectId, ci.Name, memberstr)

class SystemClassWithMembers(namedtuple('SystemClassWithMembers', 'ClassInfo')):
    @classmethod
    def fromfile(cls, f):
        classinfo = ClassInfo.fromfile(f)
        ret = cls(classinfo)
        OBJECTS[classinfo.ObjectId] = ret
        ret.memberdata = ret.read_members(f)
        return ret

    def read_members(self, f):
        return read_system_class_members(f, self.ClassInfo.Name)

    def format_member(self, i, memberdata=None):
        if memberdata is None:
            memberdata = self.memberdata
        return self.ClassInfo.MemberNames[i] + ' = ' + str(memberdata[i])

    def __str__(self):
        ci = self.ClassInfo
        memberstr = indentstr('\n'.join(self.format_member(i) for i in range(ci.MemberCount)), 4)
        return '%s ObjectId=%d Name=%s:\n%s' % (type(self).__name__, ci.ObjectId, ci.Name, memberstr)

class SystemClassWithMembersAndTypes(namedtuple('SystemClassWithMembersAndTypes', 'ClassInfo MemberTypeInfo')):
    @classmethod
    def fromfile(cls, f):
        classinfo = ClassInfo.fromfile(f)
        memberinfo = MemberTypeInfo.fromfile(f, classinfo)
        ret = cls(classinfo, memberinfo)
        OBJECTS[classinfo.ObjectId] = ret
        ret.memberdata = ret.read_members(f)
        return ret

    def read_members(self, f):
        mi = self.MemberTypeInfo
        return [read_typed_member(f, mi.BinaryTypeEnums[i], mi.AdditionalInfos[i]) for i in range(self.ClassInfo.MemberCount)]

    def format_member(self, i, memberdata=None):
        if memberdata is None:
            memberdata = self.memberdata
        type = self.MemberTypeInfo.BinaryTypeEnums[i]
        info = self.MemberTypeInfo.AdditionalInfos[i]
        if type == BinaryType.Class:
            t = info.TypeName
        elif type == BinaryType.SystemClass:
            t = info
        elif type == BinaryType.Primitive:
            t = info.name
        elif type == BinaryType.PrimitiveArray:
            t = info.name + '[]'
        else:
            t = type.name
        return t + ' ' + self.ClassInfo.MemberNames[i] + '\n' + indentstr(str(memberdata[i]), 4)

    def __str__(self):
        ci = self.ClassInfo
        memberstr = indentstr('\n'.join(self.format_member(i) for i in range(ci.MemberCount)), 4)
        return '%s ObjectId=%d Name=%s:\n%s' % (type(self).__name__, ci.ObjectId, ci.Name, memberstr)

class ClassWithId(namedtuple('ClassWithId', 'ObjectId MetadataId')):
    @classmethod
    def fromfile(cls, f):
        objid, mdid = readstruct(f, 'ii')
        ret = cls(objid, mdid)
        OBJECTS[objid] = ret
        ret.classref = OBJECTS[mdid]
        ret.memberdata = ret.read_members(f)
        return ret

    @property
    def ClassInfo(self):
        return self.classref.ClassInfo

    def read_members(self, f):
        return self.classref.read_members(f)

    def format_member(self, i):
        return self.classref.format_member(i, self.memberdata)

    def __str__(self):
        ci = self.ClassInfo
        memberstr = indentstr('\n'.join(self.format_member(i) for i in range(ci.MemberCount)), 4)
        return '%s ObjectId=%d Name=%s:\n%s' % (type(self).__name__, self.ObjectId, ci.Name, memberstr)
    
class MemberReference(namedtuple('MemberReference', 'IdRef')):
    @classmethod
    def fromfile(cls, f):
        return cls(*readstruct(f, 'i'))

class MemberPrimitiveTyped(namedtuple('MemberPrimitiveTyped', 'PrimitiveTypeEnum Value')):
    @classmethod
    def fromfile(cls, f):
        type = PrimitiveType(ord(f.read(1)))
        value = read_primitive(f, type)
        return cls(type, value)

class BinaryObjectString(namedtuple('BinaryObjectString', 'ObjectId Value')):
    @classmethod
    def fromfile(cls, f):
        objid, = readstruct(f, 'i')
        value = readvarstr(f)
        ret = cls(objid, value)
        OBJECTS[objid] = ret
        return ret

class ObjectNull(namedtuple('ObjectNull', '')):
    @classmethod
    def fromfile(cls, f):
        return cls()

class MessageEnd(namedtuple('MessageEnd', '')):
    @classmethod
    def fromfile(cls, f):
        return cls()

class ObjectNullMultiple(namedtuple('ObjectNullMultiple', 'NullCount')):
    @classmethod
    def fromfile(cls, f):
        return cls(readstruct(f, 'i')[0])

class ObjectNullMultiple256(namedtuple('ObjectNullMultiple256', 'NullCount')):
    @classmethod
    def fromfile(cls, f):
        return cls(readstruct(f, 'b')[0])

class BinaryArray(namedtuple('BinaryArray', 'ObjectId BinaryArrayTypeEnum Rank Lengths LowerBounds TypeEnum AdditionalTypeInfo')):
    @classmethod
    def fromfile(cls, f):
        objid, batype, rank = readstruct(f, 'ibi')
        batype = BinaryArrayType(batype)

        lengths = readstruct(f, 'i'*rank)
        if batype in (BinaryArrayType.SingleOffset, BinaryArrayType.JaggedOffset, BinaryArrayType.RectangularOffset):
            lowerbounds = readstruct(f, 'i'*rank)
        else:
            lowerbounds = None

        type = BinaryType(ord(f.read(1)))
        info = AdditionalTypeInfo(f, type)
        ret = cls(objid, batype, rank, lengths, lowerbounds, type, info)
        OBJECTS[objid] = ret
        ret.arraydata = ret.read_arraydata(f)
        return ret

    def read_arraydata(self, f):
        n = 1
        for i in self.Lengths:
            n *= i

        i = 0
        data = []
        while i < n:
            obj = read_typed_member(f, self.TypeEnum, self.AdditionalTypeInfo)
            if isinstance(obj, (ObjectNullMultiple, ObjectNullMultiple256)):
                i += obj.NullCount
                data.append([None] * obj.NullCount)
            else:
                i += 1
                data.append(obj)
        return data

    def __str__(self):
        memberstr = '\n'.join('    ' + str(d) for d in self.arraydata)
        return '%r\n%s' % (self, memberstr)

class ArrayInfo(namedtuple('ArrayInfo', 'ObjectId Length')):
    @classmethod
    def fromfile(cls, f):
        return cls(*readstruct(f, 'ii'))

class ArraySinglePrimitive(namedtuple('ArraySinglePrimitive', 'ArrayInfo PrimitiveTypeEnum')):
    @classmethod
    def fromfile(cls, f):
        arrinfo = ArrayInfo.fromfile(f)
        type = PrimitiveType(ord(f.read(1)))
        ret = cls(arrinfo, type)
        OBJECTS[arrinfo.ObjectId] = ret
        ret.arraydata = ret.read_arraydata(f)
        return ret

    def read_arraydata(self, f):
        if self.PrimitiveTypeEnum == PrimitiveType.Byte:
            # Shortcut for files
            return f.read(self.ArrayInfo.Length)
        return [read_primitive(f, self.PrimitiveTypeEnum) for _ in range(self.ArrayInfo.Length)]

    def __str__(self):
        memberstr = ', '.join(str(d) for d in self.arraydata)
        return '%r = [%s]' % (self, memberstr)

class ArraySingleObject(namedtuple('ArraySingleObject', 'ArrayInfo')):
    @classmethod
    def fromfile(cls, f):
        arrinfo = ArrayInfo.fromfile(f)
        ret = cls(arrinfo)
        OBJECTS[arrinfo.ObjectId] = ret
        ret.arraydata = ret.read_arraydata(f)
        return ret

    def read_arraydata(self, f):
        array = []
        while len(array) < self.ArrayInfo.Length:
            record = read_record(f)

            if isinstance(record, BinaryLibrary):
                pass
            elif isinstance(record, (ObjectNullMultiple, ObjectNullMultiple256)):
                array += [None] * record.NullCount
            else:
                array.append(record)
        return array

    def __str__(self):
        memberstr = ', '.join(str(d) for d in self.arraydata)
        return '%r = [%s]' % (self, memberstr)

class ArraySingleString(ArraySingleObject):
    pass

def read_primitive(f, type):
    if type == PrimitiveType.Boolean:
        return bool(readstruct(f, 'b')[0])
    elif type == PrimitiveType.Byte:
        return readstruct(f, 'B')[0]
    elif type == PrimitiveType.UInt32:
        return readstruct(f, 'I')[0]
    elif type == PrimitiveType.Int32:
        return readstruct(f, 'i')[0]
    elif type == PrimitiveType.UInt16:
        return readstruct(f, 'H')[0]
    elif type == PrimitiveType.Int16:
        return readstruct(f, 'h')[0]
    elif type == PrimitiveType.UInt64:
        return readstruct(f, 'Q')[0]
    elif type == PrimitiveType.Int64:
        return readstruct(f, 'q')[0]
    elif type == PrimitiveType.Double:
        return readstruct(f, 'd')[0]
    elif type == PrimitiveType.Single:
        return readstruct(f, 'f')[0]
    elif type == PrimitiveType.DateTime:
        val = readstruct(f, 'Q')[0]

        kind = val >> 62
        val &= ~(3 << 62)
        if val & (1 << 61):
            val -= 1 << 62
        td = datetime.timedelta(microseconds=val/10.0)
        # ignore kind
        return datetime.datetime(1, 1, 1) + td
    else:
        raise ValueError("Can't read primitives of type %s" % type.name)

def read_record(f):
    rtype = f.read(1)
    if not rtype:
        raise EOFError()
    rtype = RecordType(ord(rtype))
    return globals()[rtype.name].fromfile(f)
    
def read_typed_member(f, type, info):
    if type == BinaryType.Primitive:
        return read_primitive(f, info)
    return read_record(f)

def read_system_class_members(f, name):
    if name == 'System.Guid':
        return readstruct(f, 'IHHBBBBBBBB')
    elif name == 'System.Version':
        return readstruct(f, 'iiii')      
    elif name.startswith('System.Collections.Generic.List`1'):
        return (read_record(f),) + readstruct(f, 'ii')
    else:
        raise ValueError("Can't read members of type %s" % name)

def read_unknown_member(f, clsname, membername):
    if membername == 'value__':
        # enum value?
        return readstruct(f, 'i')[0]
    elif membername == '_busyCount':
        # busy count in a Monitor struct
        return readstruct(f, 'i')[0]
    elif membername in ('_monitor', 'Collection`1+items'):
        # monitors in ObservableCollection
        return read_record(f)
    else:
        raise ValueError("Can't read unknown member %s.%s" % (clsname, membername))

def dump_record(record, indent):
    print(indentstr(str(record), indent))

def dump_file(f):
    print("Binary Serialization Format")
    while 1:
        try:
            print("@%d" % f.tell())
            record = read_record(f)
            dump_record(record, 2)
            if isinstance(record, MessageEnd):
                break
        except EOFError:
            break
        except Exception as e:
            print("Failed at position %d" % f.tell())
            raise

if __name__ == '__main__':
    import sys
    dump_file(open(sys.argv[1], 'rb'))
