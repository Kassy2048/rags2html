import io
import datetime

from . import dump

class File:
    '''A NRBF file representation'''
    missObject = object()

    def __init__(self, fpath_fp):
        self.auto_close = False

        if isinstance(fpath_fp, str):
            self.fp = open(fpath_fp, 'rb')
            self.auto_close = True
        else:
            self.fp = fpath_fp

        self.libs = None
        self.objs = None
        self.root = None
        self.objCache = None

    def parse(self):
        if self.root is not None:
            return

        # Reset
        dump.LIBRARIES = {}
        dump.OBJECTS = {}

        topId = None
        while True:
            record = dump.read_record(self.fp)
            if isinstance(record, dump.SerializedStreamHeader):
                if topId is not None:
                    raise RuntimeError('multiple SerializedStreamHeader found')
                topId = record.TopId
            elif isinstance(record, dump.MessageEnd):
                break

        self.libs = dump.LIBRARIES
        self.objs = dump.OBJECTS

        # Reset
        dump.LIBRARIES = {}
        dump.OBJECTS = {}

        if topId is None:
            raise RuntimeError('TopId not found')

        self.root = self.objs[topId]
        self.objCache = {}
        return self.root

    def convert(self, root=None, idRef=None):
        '''Convert the NRBF content into Python data structures (dict and list)'''
        self.parse()

        if root is None:
            root = self.root

        if idRef is None:
            if hasattr(root, 'ObjectId') and root.ObjectId > 0:
                idRef = root.ObjectId
        elif idRef <= 0:
            idRef = None

        # Re-use reference from cache if available
        if idRef is not None:
            result = self.objCache.get(idRef, self.missObject)
            if result is not self.missObject:
                return result

        def conv_data(data):
            if isinstance(data, (str, int, float, bool, type(None), datetime.datetime)):
                # Basic data type
                return data
            elif isinstance(data, dump.MemberReference):
                # Object member
                return self.convert(self.objs[data.IdRef], data.IdRef)
            else:
                # Object
                return self.convert(data)

        if isinstance(root, (dump.ClassWithMembersAndTypes, dump.SystemClassWithMembersAndTypes,
                dump.ClassWithId)):
            if isinstance(root, dump.ClassWithId):
                classInfo = root.classref.ClassInfo
            else:
                classInfo = root.ClassInfo

            result = {}
            arrayList = None
            if (classInfo.Name == 'System.Collections.ArrayList'
                    or classInfo.Name.startswith('System.Collections.Generic.List')):
                # Convert ArrayList to list directly (the list needs to be cached)
                arrayList = result = []
            elif classInfo.Name == 'System.Guid':
                # Don't cache
                idRef = None

            if idRef is not None:
                # Cache it now to prevent infinite recursion
                self.objCache[idRef] = result

            if arrayList is not None:
                result = {}

            for i in range(classInfo.MemberCount):
                name = classInfo.MemberNames[i]
                data = root.memberdata[i]

                result[name] = conv_data(data)

            if arrayList is not None:
                arrayList += result['_items'][:result['_size']]
                result = arrayList
            elif classInfo.Name == 'System.Guid':
                # Replace with string GUID
                result = '%08x-%04x-%04x-%02x%02x-%02x%02x%02x%02x%02x%02x' % (
                        result['_a'] & 0xFFFFFFFF,
                        result['_b'] & 0xFFFF,
                        result['_c'] & 0xFFFF,
                        result['_d'] & 0xFF, result['_e'] & 0xFF,
                        result['_f'] & 0xFF, result['_g'] & 0xFF, result['_h'] & 0xFF,
                        result['_i'] & 0xFF, result['_j'] & 0xFF, result['_k'] & 0xFF)
            elif idRef is None and len(result) == 1 and 'value__' in result:
                # Enum, replace with the value directly
                result = result['value__']

        elif isinstance(root, (dump.ArraySingleObject, dump.ArraySinglePrimitive)):
            result = []
            if idRef is not None:
                # Cache it now to prevent infinite recursion
                self.objCache[idRef] = result

            if isinstance(root, dump.ArraySinglePrimitive):
                result += root.arraydata
            else:
                for data in root.arraydata:
                    result.append(conv_data(data))

        elif isinstance(root, (dump.BinaryObjectString, dump.MemberPrimitiveTyped)):
            result = root.Value

        elif isinstance(root, (dump.ObjectNull)):
            result = None

        else:
            raise RuntimeError('cannot convert %r' % (root,))

        if idRef is not None:
            self.objCache[idRef] = result

        return result

    def __enter__(self):
        self.parse()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.auto_close:
            self.fp.close()
            self.auto_close = False

        self.fp = None
        self.objs = None
        self.libs = None
        self.root = None
        self.objCache = None

    @staticmethod
    def from_bytes(data):
        return File(io.BytesIO(data))
