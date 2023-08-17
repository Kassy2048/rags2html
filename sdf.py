#!/usr/bin/env python3

'''
This module parses Microsoft SQL CE database file format (SDF).
B-Tree pages are not supported, and only version 3.5 or earlier have been tested.
'''

import sys
import struct
import math
import os
import re
from collections import defaultdict
from functools import cmp_to_key
from datetime import datetime, timedelta

# pip3 install cryptography
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

# Trace calls in case of errors
DEBUG_TRACE = True
DEBUG_TRACE_LEN = 20

def QWORD(buf, pos=0):
    return (buf[pos]
            | (buf[pos + 1] << 8)
            | (buf[pos + 2] << 16)
            | (buf[pos + 3] << 24)
            | (buf[pos + 4] << 32)
            | (buf[pos + 5] << 40)
            | (buf[pos + 6] << 48)
            | (buf[pos + 7] << 56)
    )

def DWORD(buf, pos=0):
    return (buf[pos]
            | (buf[pos + 1] << 8)
            | (buf[pos + 2] << 16)
            | (buf[pos + 3] << 24)
    )

def WORD(buf, pos=0):
    return buf[pos] | (buf[pos + 1] << 8)

def BYTE(buf, pos=0):
    return buf[pos]

def print_err(msg):
    print(str(msg), file=sys.stderr)

def debug_trace(msg, *args):
    if not DEBUG_TRACE:
        return

    debug_trace.history.append(msg % args)
    if len(debug_trace.history) > 2 * DEBUG_TRACE_LEN:
        debug_trace.history = debug_trace.history[-DEBUG_TRACE_LEN:]
# TODO Use a queue instead?
debug_trace.history = []
debug_trace.lastTable = None
debug_trace.lastPage = None

default_iv = bytearray(16)  # 16 zero bytes
def decrypt_bytes(key_hash, data_key, data):
    hash1 = key_hash.copy()
    hash1.update(data_key)
    hash1 = hash1.finalize()

    # Wincrypt key derviation for AES
    # <https://learn.microsoft.com/en-us/windows/win32/api/wincrypt/nf-wincrypt-cryptderivekey#remarks>
    buffer1 = bytearray([0x36] * 64)
    # buffer2 = bytearray([0x5c] * 64)
    for i in range(len(hash1)):
        buffer1[i] ^= hash1[i]
        # buffer2[i] ^= hash1[i]

    digest = hashes.Hash(hashes.SHA1())
    digest.update(buffer1)
    key = digest.finalize()
    # digest = hashes.Hash(hashes.SHA1())
    # digest.update(buffer2)
    # key += digest.finalize()

    decryptor = Cipher(algorithms.AES(key[:16]), modes.CBC(default_iv)).decryptor()
    return decryptor.update(data) + decryptor.finalize()

def check_key(fpath, key):
    key_hash = hashes.Hash(hashes.SHA1())
    key_hash.update(key)

    with open(fpath, 'rb') as fh:
        page = fh.read(4096)
        if len(page) != 4096:
            return False

        # Check key from header
        data_key = page[188:188+4]
        key_check = page[76:76+0x60]
        key_check = decrypt_bytes(key_hash, data_key, key_check)
        if key != key_check[:len(key)]:
            return False

    return True

def do_checksum(data):
    i = 0
    sum1 = 0
    sum2 = 0
    for i in range(0, len(data) - 1, 2):
        word = data[i] | (data[i + 1] << 8)
        sum1 += word
        sum2 += sum1

    if len(data) & 1 != 0:
        sum1 += data[-1]
        sum2 += sum1

    while(sum1 > 0xFFFF): sum1 = (sum1 & 0xFFFF) + (sum1 >> 16)
    while(sum2 > 0xFFFF): sum2 = (sum2 & 0xFFFF) + (sum2 >> 16)

    if sum1 == 0xFFFF: sum1 = 0
    if sum2 == 0xFFFF: sum2 = 0

    return sum1 * 0xFFFF + sum2

class PageType:
    HEADER  = 0
    MAPA    = 1
    MAPB    = 2
    TABLE   = 3
    DATA    = 4
    LV      = 5  # LongValue
    BTREE   = 6  # Not supported
    BITMAP  = 8
    LVMAP   = 9

    def __init__(self, value):
        self.value = value

    def __str__(self):
        for name in dir(self.__class__):
            if name.startswith('_'):
                continue
            if getattr(self, name) == self.value:
                return name
        return 'TYPE_%d' % (self.value,)

class Page:
    def __init__(self, id, type, data, address=None, decrypted=True):
        self.id = id
        self.type = type
        self.data = data
        self.address = address
        self.decrypted = decrypted

    def __repr__(self):
        return 'Page<id=%05x, type=%s, address=%08x>' % (self.id, PageType(self.type), self.address)

    def __str__(self):
        return repr(self)

class DataPage:
    '''
    A DATA page stores a list of arbitraty data entries (blocs).
    An full entry can be stored on multiple pages.
    '''
    def __init__(self, page):
        '''
        DATA table:
            After the page header, the data header is 8 bytes:
                Offset  Size    Info
                0000    4       tablePageId (first 20 bits), next 12 bits is free size
                0004    4       first 12 lsb is entries count, next 12 bits is page data size
            At the end of the DATA pages, there is a list of 4 bytes per entries.
            For each 4 bytes (starting from last page dword):
                Bits 11-00: entry offset from start of data (16+8+data_offset?)
                Bits 23-12: entry size
                Bits 31-24: flags, only the first 2 bits should be set. If bit 0 is set, entry is empty (free?).

            The tables schema is stored in DATA pages as 0x5D bytes+strings for each entry.
        '''

        debug_trace('DataPage(%s)', page)
        debug_trace.lastPage = self

        self.page = page

        if page.type != PageType.DATA:
            raise ValueError('page %05x (at %08x) is not a DATA page' % (page.id, page.address))

        dword = DWORD(page.data, 16)
        self.tablePageId = dword & 0xFFFFF
        self.freeSize = dword >> 20
        dword = DWORD(page.data, 16+4)
        self.entriesCount = dword & 0xFFF
        self.dataSize = (dword >> 12) & 0xFFF

        # DEBUG
        self.lastEntry = None
        self.lastEntryOffset = None

    def __repr__(self):
        return 'DataPage<page=%s>' % (self.page)

    def __str__(self):
        return repr(self)

    def validate(self, db):
        debug_trace('DataPage.validate(%s)', self.page)
        debug_trace.lastPage = self

        pos = 4096
        total_size = 0
        for _ in range(self.entriesCount):
            pos -= 4
            dword = DWORD(self.page.data, pos)
            entryOffset = dword & 0xFFF
            entrySize = (dword >> 12) & 0xFFF
            flags = dword >> 24
            if (flags & 0xFC) != 0 or entryOffset + entrySize > self.dataSize:
                raise RuntimeError('invalid DATA page content for page %05x (at %08x)'
                        % (self.page.id, self.page.address))
            if (flags & 1) == 0:
                total_size += entrySize

        if total_size + self.freeSize != self.dataSize:
            raise RuntimeError('invalid DATA page content for page %05x (at %08x)'
                    % (self.page.id, self.page.address))

    def __iter__(self):
        for i in range(self.entriesCount):
            yield self.getEntry(i)

    def getEntry(self, i):
        debug_trace('DataPage.getEntry(%s, %d)', self.page, i)
        debug_trace.lastPage = self

        if i < 0 or i >= self.entriesCount:
            raise IndexError('index out of range')

        pos = 4096 - 4 - 4 * i
        if pos < 0:
            print_err('Warning: negative offset for entry %d in page %05x (at %08x)'
                    % (i, self.page.id, self.page.address))
        dword = DWORD(self.page.data, pos)
        entryOffset = dword & 0xFFF
        entrySize = (dword >> 12) & 0xFFF
        flags = dword >> 24

        if (flags & 1) == 1:
            # Empty/Free?
            return (flags, None)

        if (flags & 2) == 0:
            # The entry is the continuation of previous entry
            pass

        start = entryOffset + 16 + 8
        end = start + entrySize

        self.lastEntry = i
        self.lastEntryOffset = start

        return (flags, self.page.data[start:end])

class TablePage:
    '''
    A TABLE page stores references to DATA pages where the table rows are stored.
    They might also be referenced through BITMAP pages.
    '''
    def __init__(self, page, db):
        '''
        TABLE page:
            After the page header, the data header is 8 bytes:
                Offset  Size    Info
                0000    4       number of data pages
                0004    4       1 if a list of BITMAP pages follows (the list of DATA pages starts at 0x70 then)
            The data pages list follows, 8 bytes for 3 page ID:
                Bit 19-00: page ID N
                Bit 39-20: page ID N+1
                Bit 59-40: page ID N+2
            There might be more info at offset 0x130 (from page start)
        '''

        self.page = page
        self.db = db

        debug_trace('TablePage(%s)', self.page)
        debug_trace.lastPage = self

        if page.type != PageType.TABLE:
            raise ValueError('page %05x (at %08x) is not a TABLE page' % (page.id, page.address))

        self.dataListOffset = 16 + 8
        self.dataPageCount = DWORD(page.data, 16)
        self.flags = DWORD(page.data, 16 + 4)

        self.bmapPageCount = 0
        self.bmapListOffset = None
        if self.flags == 1:
            self.bmapPageCount = self.dataPageCount  # Number of DATA pages in bitmap PAGES
            self.bmapListOffset = self.dataListOffset

            self.dataListOffset += 0x60
            self.dataPageCount = DWORD(page.data, self.dataListOffset - 8)
            self.flags = DWORD(page.data, self.dataListOffset - 4)

        if self.flags != 0:
            # It might be a list of free bitmap pages for that table?
            self.dataPageCount = 0
            print_err('unsupported flags (%08x) for TABLE page %05x (at %08x)'
                    % (self.flags, self.page.id, self.page.address))

        self.lastDataPage = None
        self.records = []
        self.ready = False

    def __repr__(self):
        return 'TablePage<page=%s>' % (self.page)

    def __str__(self):
        return repr(self)

    def _initialize(self):
        if self.ready:
            return

        dataPageIds = []
        dataPageIdSet = set()
        for i in range(self.dataPageCount):
            pos = self.dataListOffset + (i // 3) * 8
            qword = QWORD(self.page.data, pos)
            id = (qword >> (20 * (i % 3))) & 0xFFFFF
            if id not in dataPageIdSet:
                dataPageIds.append(id)
                dataPageIdSet.add(id)

        if self.bmapPageCount:
            pageFound = 0
            i = 0
            pageIdBase = 0
            while pageFound < self.bmapPageCount:
                pos = self.bmapListOffset + (i // 3) * 8
                qword = QWORD(self.page.data, pos)
                id = (qword >> (20 * (i % 3))) & 0xFFFFF
                i += 1

                if id == 0:
                    print_err('Warning: found NULL pageId in BITMAP pages list for %s'
                            % (repr(self),))
                    # It means there are no DATA page in the current BITMAP range?
                else:
                    self.lastDataPage = bmapPage = BitmapPage(self.db.readPage(id, validate=True))
                    for dataPageId in bmapPage:
                        pageFound += 1
                        dataPageId += pageIdBase
                        if dataPageId not in dataPageIdSet:
                            dataPageIds.append(dataPageId)
                            dataPageIdSet.add(dataPageId)

                pageIdBase += 0x7F00  # (4096 - 32) * 8

            if pageFound != self.bmapPageCount:
                print_err('Warning: found more pages in BITMAP than expected for %s (%d > %d)'
                        % (repr(self), pageFound, self.bmapPageCount))

        self.records = []
        # Visit all the DATA pages to map the records to them
        for id in dataPageIds:
            self.lastDataPage = DataPage(self.db.readPage(id, validate=True))
            for idx, (flags, entry) in enumerate(self.lastDataPage):
                if entry is None:
                    continue

                if (flags & 2) == 0:
                    # Continuation of previous record
                    continue

                self.records.append([(id, idx)])

                nextChunk = DWORD(entry)
                nextChunk = (nextChunk >> 12, nextChunk & 0xFFF)  # pageId, entryId
                while nextChunk[0] != 0:
                    # Data continue in another page/entry
                    self.records[-1].append(nextChunk)
                    otherPage = DataPage(self.db.readPage(nextChunk[0], validate=True))
                    entry = otherPage.getEntry(nextChunk[1])[1]
                    nextChunk = DWORD(entry)
                    nextChunk = (nextChunk >> 12, nextChunk & 0xFFF)  # pageId, entryId

        self.ready = True

    def validate(self, db):
        debug_trace('TablePage.validate(%s)', self.page)
        debug_trace.lastPage = self

        if (self.dataPageCount & 0xFFFFFF00) != 0:
            raise RuntimeError('dubious page count (%08x) for TABLE page %05x (at %08x)'
                    % (self.dataPageCount, self.page.id, self.page.address))

        for i in range(self.dataPageCount):
            pos = self.dataListOffset + (i // 3) * 8
            qword = QWORD(self.page.data, pos)
            id = (qword >> (20 * (i % 3))) & 0xFFFFF
            if not db.checkId(id):
                raise RuntimeError('invalid DATA page %05x in TABLE page %05x (at %08x)'
                        % (id, self.page.id, self.page.address))

        if self.bmapPageCount:
            # TODO BITMAP pages
            pass

    def getCount(self):
        self._initialize()

        return len(self.records)

    def __iter__(self):
        self._initialize()

        for i in range(len(self.records)):
            yield self.getRecord(i)

    def getRecord(self, i):
        debug_trace('TablePage.getRecord(page=%s, i=%s)', self.page, i)
        debug_trace.lastPage = self

        self._initialize()

        record = self.records[i]
        data = bytearray()
        for (id, idx) in record:
            if not (self.lastDataPage is not None and self.lastDataPage.page.id == id):
                self.lastDataPage = DataPage(self.db.readPage(id, validate=False))
            entry = self.lastDataPage.getEntry(idx)[1]
            if len(data) > 0:
                # Remove the first 4 bytes when adding continuation entries
                entry = entry[4:]
            data += entry

        return data

class Table:
    '''
    A class to store a table definition and extract all the rows of that table.
    '''
    def __init__(self, name, pageId=None, nick=None, trackingType=None, ddlGranted=None,
            readOnly=False, compressed=False, columns=None):
        self.name = name
        self.pageId = pageId
        self.nick = nick
        self.trackingType = trackingType
        self.ddlGranted = ddlGranted
        self.readOnly = readOnly
        self.compressed = compressed
        self.columns = [] if columns is None else columns

        self.headerSize = None
        self.minRowSize = None
        self.bitfieldSize = None

        debug_trace('Table(name=%s, pageId=%s)', self.name, self.pageId)
        debug_trace.lastTable = self

        self._sortedColumns = []
        self.sortColumns()
        self.needValidate = True

    def __repr__(self):
        return 'Table<name=%s, pageId=%05x, columns=%s>' % (self.name,
                0xFFFFF if self.pageId is None else self.pageId, self.columns)

    def __str__(self):
        return repr(self)

    def addColumn(self, column):
        debug_trace('Table.addColumn(name=%s, column=%s)', self.name, column)
        debug_trace.lastTable = self

        self.columns.append(column)
        self.sortColumns()
        self.needValidate = True

    def sortColumns(self):
        # Sort by storage area and then by position
        def cmp(cola, colb):
            diff = cola.type.storage - colb.type.storage
            if diff == 0:
                diff = cola.position - colb.position
            return diff
        self._sortedColumns = sorted(self.columns, key=cmp_to_key(cmp))

        # Sorted by column index
        self.columns.sort(key=lambda c: c.index)

    def validate(self):
        debug_trace('Table.validate(name=%s, columns=%s)', self.name, self.columns)
        debug_trace.lastTable = self

        position = 0
        names = set()
        indexes = set()
        storage = 0

        # nextChunk + colCount + colMask
        self.headerSize = 4 + 4 + math.ceil(len(self.columns) / 8)
        self.minRowSize = self.headerSize

        self.bitfieldSize = 0
        minBitfieldSize = 0

        self.sortColumns()

        for col in self._sortedColumns:
            if storage != col.type.storage:
                if storage > col.type.storage:
                    debug_trace('column=%s', col)
                    raise RuntimeError('unexpected storage %d for column %s.%s'
                            % (col.type.storage, self.name, col.name))
                storage = col.type.storage
                position = 0

            if position != col.position:
                print_err(self._sortedColumns)
                debug_trace('column=%s', col)
                raise RuntimeError('unexpected position %d (/=%d) for column %s.%s'
                        % (col.position, position, self.name, col.name))

            if col.name.lower() in names:
                print_err('Warning: %s.%s found multiple times' % (self.name, col.name))
            names.add(col.name.lower())

            if col.index in indexes:
                debug_trace('column=%s', col)
                raise RuntimeError('column with index %d found multiple times in %s'
                        % (col.index, self.name))
            indexes.add(col.index)

            if storage == 0:
                position += 1
                minBitfieldSize = position
            elif storage == 1:
                position += col.size
                self.minRowSize += col.size
            else:
                position += 1
                self.minRowSize += 2

        index = 0
        for i in sorted(indexes):
            if i != index:
                debug_trace('columns=%s', self.columns)
                raise RuntimeError('no column with index %d in %s'
                        % (i, self.name))
            index += 1

        self.bitfieldSize = math.ceil(minBitfieldSize / 8)
        self.minRowSize += self.bitfieldSize

        self.needValidate = False

    def extractRow(self, data, sortByIndex=False, keyIndex=False):
        debug_trace('Table.extractRow(name=%s, data=%s)', self.name, data)
        debug_trace.lastTable = self

        if self.needValidate:
            self.validate()

        if len(data) < 8:
            raise RuntimeError('rows size (%d) is too small for table %s record (>=%d)'
                    % (len(data), self.name, 8))

        (nextChunk, colCount) = struct.unpack_from('<LL', data)
        nextChunk = (nextChunk >> 12, nextChunk & 0xFFF)  # pageId, entry index

        if colCount > len(self.columns):
            raise RuntimeError('number of columns (%d) is unexpected for table %s record (>=%d)'
                    % (colCount, self.name, len(self.columns)))

        if colCount == len(self.columns):
            headerSize = self.headerSize
            minRowSize = self.minRowSize
            bitfieldSize = self.bitfieldSize

        else:
            # The last columns are missing
            # Re-compute the sizes
            headerSize = 4 + 4 + math.ceil(colCount / 8)
            minRowSize = headerSize

            minBitfieldSize = 0
            position = 0
            storage = 0
            for i, col in enumerate(self._sortedColumns):
                if i >= colCount:
                    break

                if storage != col.type.storage:
                    storage = col.type.storage
                    position = 0

                if storage == 0:
                    position += 1
                    minBitfieldSize = position
                elif storage == 1:
                    position += col.size
                    minRowSize += col.size
                else:
                    position += 1
                    minRowSize += 2

            bitfieldSize = math.ceil(minBitfieldSize / 8)
            minRowSize += bitfieldSize

        if len(data) < headerSize:
            raise RuntimeError('rows size (%d) is too small for table %s record (>=%d)'
                    % (len(data), self.name, headerSize))

        colMaskBytes = data[8:headerSize]
        colMask = 0
        while len(colMaskBytes) > 0:
            # Invert it so 1=present and 0=missing
            colMask = (colMask << 8) | (colMaskBytes.pop() ^ 0xFF)
        # Columns marked as "missing" are actually present, but their value should be default?

        if len(data) < minRowSize:
            # FIXME What about compressed rows/columns/tables?
            raise RuntimeError('rows size (%d) is too small for table %s record (>=%d)'
                    % (len(data), self.name, minRowSize))

        pos = headerSize

        bitfield = 0
        if bitfieldSize > 0:
            for n in range(bitfieldSize):
                bitfield |= BYTE(data, pos) << (n * 8)
                pos += 1

        binData = data[minRowSize:]

        row = {}
        for i, col in enumerate(self._sortedColumns):
            if i >= colCount:
                # Column is missing, use default value
                row[col.index if keyIndex else col.name] = col.get_default()
                continue

            if col.type.storage == 0:
                debug_trace('parseBit(col=%s)', col)
                row[col.index if keyIndex else col.name] = True if ((bitfield >> col.position) & 1) != 0 else False
            elif col.type.storage == 1:
                colData = data[pos:pos+col.size]
                pos += col.size
                row[col.index if keyIndex else col.name] = col.parse(colData)
            else:
                if col.position == 0:
                    debug_trace('varmap=%s', data[pos:minRowSize])

                start = WORD(data, pos)
                ascii = (start & 0x8000) != 0
                start &= 0x7FFF
                pos += 2
                if pos < minRowSize:
                    end = WORD(data, pos) & 0x7FFF
                    if end > len(binData):
                        end = len(binData)
                else:
                    end = len(binData)

                if start < end:
                    # Field is present
                    if start > len(binData):
                        raise RuntimeError('start (%d) is too big for table %s record (<=%d)'
                                % (start, self.name, len(binData)))

                    colData = binData[start:end]
                else:
                    # Empty
                    colData = b''

                row[col.index if keyIndex else col.name] = col.parse(colData, ascii=ascii)

        if sortByIndex:
            # TODO Return a list instead?
            _row = {}
            for col in self.columns:
                key = col.index if keyIndex else col.name
                _row[key] = row[key]
            row = _row

        return row

class Column:
    '''
    Table column definition.
    '''
    class Type:
        def __init__(self, value, maxSize, names, storage, fixed=True):
            self.value = value
            self.names = names if isinstance(names, list) else [names]
            self.maxSize = maxSize
            self.fixed = fixed
            self.storage = storage

        def __repr__(self):
            return 'ColumnType<value=%s, names=%s, storage=%s>' % (self.value,
                    self.names, self.storage)

    class NumType(Type):
        '''Stored in the numeric area'''
        def __init__(self, value, maxSize, names, fixed=True):
            super().__init__(value, maxSize, names, 1, fixed=fixed)

    class BinType(Type):
        '''Stored in the data area'''
        def __init__(self, value, maxSize, names, fixed=True):
            super().__init__(value, maxSize, names, 2, fixed=fixed)

    class BitType(Type):
        '''Stored in the bitfield area'''
        def __init__(self, value, maxSize, names, fixed=True):
            super().__init__(value, maxSize, names, 0, fixed=fixed)

    TYPE_TINYINT            = NumType(0, 1, 'tinyint')
    TYPE_SMALLINT           = NumType(1, 2, 'smallint')
    TYPE_USHORT             = NumType(2, 2, 'ushort')
    TYPE_INTEGER            = NumType(3, 4, 'integer')
    TYPE_ULONG              = NumType(4, 4, 'ulong')
    TYPE_BIGINT             = NumType(5, 8, 'bigint')
    TYPE_UBIGINT            = NumType(6, 8, 'ubigint')
    TYPE_NCHAR              = BinType(7, 8000, 'nchar')
    TYPE_NVARCHAR           = BinType(8, 8000, 'nvarchar', fixed=False)
    TYPE_NTEXT              = BinType(9, 536870911, 'ntext', fixed=False)
    TYPE_BINARY             = NumType(10, 8000, 'binary')
    TYPE_VARBINARY          = BinType(11, 8000, 'varbinary', fixed=False)
    TYPE_IMAGE              = BinType(12, 1073741823, 'image')
    TYPE_DATETIME           = NumType(13, 8, 'datetime')  # size is 16 instead?
    TYPE_UNIQUEIDENTIFIER   = NumType(14, 16, 'uniqueidentifier')
    TYPE_BIT                = BitType(15, 2, 'bit')
    TYPE_REAL               = NumType(16, 4, 'real')
    TYPE_FLOAT              = NumType(17, 8, 'float')
    TYPE_MONEY              = NumType(18, 8, 'money')
    TYPE_NUMERIC            = NumType(19, 19, ['numeric', 'decimal', 'dec'])  # (p,s)
    TYPE_ROWVERSION         = NumType(20, 8, 'rowversion')

    TYPES = {}

    DATETIME_REF = datetime.fromisoformat('1900-01-01')

    def __init__(self, index, position, name, type, size=None, precision=None, scale=None,
            fixed=True, nullable=True, writeable=True, autoType=None, default=None,
            compressed=False):
        self.index = index
        self.name = name
        self.type = type
        self.size = type.maxSize if size is None else size
        self.precision = precision
        self.scale = scale
        self.fixed = fixed
        self.nullable = nullable
        self.writeable = writeable
        self.autoType = autoType
        self.position = position
        self.default = default
        self.compressed = compressed

        self.decWarned = False

    def __repr__(self):
        return 'Column<index=%s, name=%s, type=%s, size=%s, position=%s, default=%s>' % (self.index,
                self.name, self.type, self.size, self.position, self.default)

    def parse(self, data, ascii=False):
        debug_trace('Column.parse(self=%s, data=%s, ascii=%s)', self, data, ascii)

        def clean_string(str):
            # Remove extra characters after the first NUL character
            return str.split('\0', 1)[0]

        # TODO Use a lookup table instead of a big if/elif bloc?
        if self.type.value == self.TYPE_TINYINT.value:
            return BYTE(data)
        elif self.type.value == self.TYPE_SMALLINT.value:
            return struct.unpack_from('<h', data)[0]
        elif self.type.value == self.TYPE_USHORT.value:
            return WORD(data)
        elif self.type.value == self.TYPE_INTEGER.value:
            return struct.unpack_from('<l', data)[0]
        elif self.type.value == self.TYPE_ULONG.value:
            return DWORD(data)
        elif self.type.value == self.TYPE_BIGINT.value:
            return struct.unpack_from('<q', data)[0]
        elif self.type.value == self.TYPE_UBIGINT.value:
            return QWORD(data)
        elif self.type.value == self.TYPE_BINARY.value:
            return data
        elif self.type.value == self.TYPE_DATETIME.value:
            # 300 ticks per second
            ticks, days = struct.unpack_from('<ll', data)
            dt = self.DATETIME_REF + timedelta(days=days, milliseconds=ticks * 1000 / 300)
            return dt
        elif self.type.value == self.TYPE_UNIQUEIDENTIFIER.value:
            return data
        elif self.type.value == self.TYPE_REAL.value:
            return struct.unpack_from('<f', data)[0]
        elif self.type.value == self.TYPE_FLOAT.value:
            return struct.unpack_from('<d', data)[0]
        elif self.type.value == self.TYPE_MONEY.value:
            return struct.unpack_from('<q', data)[0] / 10000
        elif self.type.value == self.TYPE_NUMERIC.value:
            # FIXME Support NUMERIC type?
            if not self.decWarned:
                print_err('Warning: no support for numeric(p, s) in column %s' % (self.name,))
                self.decWarned = True
            return 0
        elif self.type.value == self.TYPE_ROWVERSION.value:
            return QWORD(data)
        elif self.type.value == self.TYPE_NCHAR.value:
            # XXX CP-1252 is a guess, we should probably infer the code page from LCID in DB header
            return clean_string(data.decode('cp1252' if ascii else 'utf-16'))
        elif self.type.value == self.TYPE_NVARCHAR.value:
            # XXX CP-1252 is a guess, we should probably infer the code page from LCID in DB header
            return clean_string(data.decode('cp1252' if ascii else 'utf-16'))
        elif self.type.value == self.TYPE_VARBINARY.value:
            return data
        elif self.type.value == self.TYPE_IMAGE.value or self.type.value == self.TYPE_NTEXT.value:
            if self.type.value == self.TYPE_NTEXT.value:
                # XXX CP-1252 is a guess, we should probably infer the code page from LCID in DB header
                encoding = 'cp1252' if ascii else 'utf-16'
            else:
                encoding = None

            if len(data) == 0:
                return b'' if encoding is None else ''

            size = QWORD(data)
            if size > 256-8:  # FIXME Might be wrong
                # Stored in LV page(s)
                pageCount = math.ceil(size / (4096 - 16))
                wordCount = math.ceil(pageCount / 3)
                if wordCount > (256 - 8) / 8:  # FIXME Might be wrong
                    # Stored in LV page(s) whose list is given in LVMAP page(s)

                    # FIXME There might be multiple levels of LVMAP to reach the max size
                    #       of 1073741823 bytes?
                    #       Max size for  1 LVMAP is   6230160 bytes
                    #       Max size for 31 LVMAP is 193134960 bytes
                    #       Max size for 31 LVMAP pointing to LVMAP is 294917083920 bytes

                    lvmapCount = math.ceil(pageCount / ((4096 - 16 - 8) / 8 * 3))
                    lvmapWordCount = math.ceil(lvmapCount / 3)
                    if len(data) != 8 + lvmapWordCount * 8:
                        raise RuntimeError('unexpected LVMAP data size (%d vs %d) for column %s'
                                % (len(data), 8 + lvmapWordCount * 8, self.name))
                    lvmapPageIds = []
                    for n in range(lvmapWordCount):
                        word = QWORD(data, 8 + n * 8)
                        for _ in range(3):
                            if len(lvmapPageIds) == lvmapCount:
                                break
                            lvmapPageIds.append(word & 0xFFFFF)
                            word >>= 20
                    debug_trace('lvmapCount=%s, lvmapWordCount=%s, lvmapPageIds=%s',
                            lvmapCount, lvmapWordCount, lvmapPageIds)
                    return LvMapData(lvmapPageIds, size, encoding)

                else:
                    if len(data) != 8 + wordCount * 8:
                        raise RuntimeError('unexpected data size (%d vs %d) for column %s'
                                % (len(data), 8 + wordCount * 8, self.name))
                    pageIds = []
                    for n in range(wordCount):
                        word = QWORD(data, 8 + n * 8)
                        for _ in range(3):
                            if len(pageIds) == pageCount:
                                break
                            pageIds.append(word & 0xFFFFF)
                            word >>= 20
                    return LvData(pageIds, size, encoding)
            else:
                # Stored in this page
                if len(data) != size + 8:
                    raise RuntimeError('unexpected data size (%d vs %d) for column %s'
                            % (len(data), size + 8, self.name))
                data = data[8:]
                if encoding is not None:
                    data = clean_string(data.decode(encoding))
            return data
        else:
            raise RuntimeError('unknown NumType %d' % (self.type.value,))

    def get_default(self):
        debug_trace('Column.get_default(self=%s)', self)

        # TODO Parse and return self.default is not None

        # TODO Use a lookup table instead of a big if/elif bloc?
        if self.type.value == self.TYPE_BIT.value:
            return False
        elif self.type.value == self.TYPE_TINYINT.value:
            return 0
        elif self.type.value == self.TYPE_SMALLINT.value:
            return 0
        elif self.type.value == self.TYPE_USHORT.value:
            return 0
        elif self.type.value == self.TYPE_INTEGER.value:
            return 0
        elif self.type.value == self.TYPE_ULONG.value:
            return 0
        elif self.type.value == self.TYPE_BIGINT.value:
            return 0
        elif self.type.value == self.TYPE_UBIGINT.value:
            return 0
        elif self.type.value == self.TYPE_BINARY.value:
            return b''
        elif self.type.value == self.TYPE_DATETIME.value:
            return self.DATETIME_REF
        elif self.type.value == self.TYPE_UNIQUEIDENTIFIER.value:
            return b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
        elif self.type.value == self.TYPE_REAL.value:
            return 0.0
        elif self.type.value == self.TYPE_FLOAT.value:
            return 0.0
        elif self.type.value == self.TYPE_MONEY.value:
            return 0.0
        elif self.type.value == self.TYPE_NUMERIC.value:
            return 0
        elif self.type.value == self.TYPE_ROWVERSION.value:
            return 0
        elif self.type.value == self.TYPE_NCHAR.value:
            return ''
        elif self.type.value == self.TYPE_NVARCHAR.value:
            return ''
        elif self.type.value == self.TYPE_VARBINARY.value:
            return b''
        elif self.type.value == self.TYPE_IMAGE.value or self.type.value == self.TYPE_NTEXT.value:
            if self.type.value == self.TYPE_NTEXT.value:
                return ''
            else:
                return b''
        else:
            raise RuntimeError('unknown NumType %d' % (self.type.value,))

# FIXME Use an enum instead?
for name in dir(Column):
    if not name.startswith('TYPE_'):
        continue
    t = getattr(Column, name)
    Column.TYPES[t.value] = t

class BitmapPage:
    '''
    A BITMAP page indicates which page is of interest within a range of pages through a big bits map.
    '''
    def __init__(self, page):
        '''
        BITMAP table:
            After the page header, the data header is 16 bytes:
                Offset  Size    Info
                0000    2       pageCount
                0002    2       firstPageId
                0004    2       lastPageId

            The rest of the page is a bitmap of 32256 bits, 1 bit for each pageId from 0 to 0x7DFF.
            When a bit is set, the associated page is included.
        '''

        debug_trace('BitmapPage(%s)', page)
        debug_trace.lastPage = self

        self.page = page

        if page.type != PageType.BITMAP:
            raise ValueError('page %05x (at %08x) is not a BITMAP page' % (page.id, page.address))

        self.pageCount = WORD(page.data, 16)
        self.firstPageId = WORD(page.data, 16+2)
        self.lastPageId = WORD(page.data, 16+4)

    def __repr__(self):
        return 'BitmapPage<page=%s>' % (self.page)

    def __str__(self):
        return repr(self)

    def __iter__(self):
        if self.pageCount == 0:
            return

        id = 0
        while id != self.lastPageId:
            id = self.getNext(id)
            yield id

    def getNext(self, id):
        debug_trace('BitmapPage.getNext(%s, %d)', self.page, id)
        debug_trace.lastPage = self

        if id < self.firstPageId:
            return self.firstPageId
        if id > self.lastPageId:
            return self.lastPageId
        if self.pageCount == 0:
            return None

        id += 1
        pos = 32 + id // 8
        bit_mask = 1 << (id & 0x7)
        while pos < len(self.page.data):
            # TODO Optimizations (skip the next 1/2/4/8-bytes word if 0)
            if (self.page.data[pos] & bit_mask) != 0:
                return id
            id += 1
            if bit_mask == 0x80:
                bit_mask = 1
                pos += 1
            else:
                bit_mask <<=1

        # Should not happen as we should end on self.lastPageId in the worse case
        raise RuntimeError('cannot find next page ID')

class ObjectType:
    TABLE       = 1
    COLUMN      = 4
    #INDEX       = 
    CONSTRAINT  = 8

# Hard-coded definition of the __SysObjects table
SysObjects_table = Table('__SysObjects')
SysObjects_table.addColumn(Column( 0,  0, 'ObjectType', Column.TYPE_USHORT))
SysObjects_table.addColumn(Column( 1,  0, 'ObjectOwner', Column.TYPE_NVARCHAR, size=256))
SysObjects_table.addColumn(Column( 2,  1, 'ObjectName', Column.TYPE_NVARCHAR, size=256))
SysObjects_table.addColumn(Column( 3,  0, 'ObjectIsSystem', Column.TYPE_BIT))
SysObjects_table.addColumn(Column( 4,  2, 'ObjectVersion', Column.TYPE_BINARY, size=8))
SysObjects_table.addColumn(Column( 5, 10, 'ObjectOrdinal', Column.TYPE_USHORT))
SysObjects_table.addColumn(Column( 6, 12, 'ObjectCedbInfo', Column.TYPE_ULONG))

SysObjects_table.addColumn(Column( 7, 16, 'TablePageId', Column.TYPE_ULONG))
SysObjects_table.addColumn(Column( 8, 20, 'TableNick', Column.TYPE_INTEGER))
SysObjects_table.addColumn(Column( 9, 24, 'TableTrackingType', Column.TYPE_USHORT))
SysObjects_table.addColumn(Column(10, 26, 'TableDdlGranted', Column.TYPE_ULONG))
SysObjects_table.addColumn(Column(11,  1, 'TableReadOnly', Column.TYPE_BIT))
SysObjects_table.addColumn(Column(12,  2, 'TableCompressed', Column.TYPE_BIT))

SysObjects_table.addColumn(Column(13, 30, 'ColumnType', Column.TYPE_USHORT))
SysObjects_table.addColumn(Column(14, 32, 'ColumnSize', Column.TYPE_USHORT))
SysObjects_table.addColumn(Column(15, 34, 'ColumnPrecision', Column.TYPE_TINYINT))
SysObjects_table.addColumn(Column(16, 35, 'ColumnScale', Column.TYPE_TINYINT))
SysObjects_table.addColumn(Column(17,  3, 'ColumnFixed', Column.TYPE_BIT))
SysObjects_table.addColumn(Column(18,  4, 'ColumnNullable', Column.TYPE_BIT))
SysObjects_table.addColumn(Column(19,  5, 'ColumnWriteable', Column.TYPE_BIT))
SysObjects_table.addColumn(Column(20, 36, 'ColumnAutoType', Column.TYPE_USHORT))
SysObjects_table.addColumn(Column(21, 38, 'ColumnPosition', Column.TYPE_USHORT))
SysObjects_table.addColumn(Column(22,  2, 'ColumnDefault', Column.TYPE_NVARCHAR, size=256))  # size is unknown
SysObjects_table.addColumn(Column(23,  6, 'ColumnCompressed', Column.TYPE_BIT))

SysObjects_table.addColumn(Column(24, 40, 'IndexRoot', Column.TYPE_ULONG))
SysObjects_table.addColumn(Column(25,  3, 'IndexKey', Column.TYPE_VARBINARY, size=256))  # size is unknown
SysObjects_table.addColumn(Column(26,  7, 'IndexUnique', Column.TYPE_BIT))
SysObjects_table.addColumn(Column(27, 44, 'IndexNullOption', Column.TYPE_USHORT))
SysObjects_table.addColumn(Column(28,  8, 'IndexPositional', Column.TYPE_BIT))
SysObjects_table.addColumn(Column(29,  4, 'IndexHistogram', Column.TYPE_IMAGE))

SysObjects_table.addColumn(Column(30, 46, 'ConstraintType', Column.TYPE_ULONG))
SysObjects_table.addColumn(Column(31,  5, 'ConstraintIndex', Column.TYPE_NVARCHAR, size=256))  # size is unknown
SysObjects_table.addColumn(Column(32,  6, 'ConstraintTargetIndex', Column.TYPE_NVARCHAR, size=256))  # size is unknown
SysObjects_table.addColumn(Column(33,  7, 'ConstraintTargetTable', Column.TYPE_NVARCHAR, size=256))  # size is unknown
SysObjects_table.addColumn(Column(34, 50, 'ConstraintOnDelete', Column.TYPE_ULONG))
SysObjects_table.addColumn(Column(35, 54, 'ConstraintOnUpdate', Column.TYPE_ULONG))
SysObjects_table.addColumn(Column(36,  8, 'ConstraintKey', Column.TYPE_VARBINARY, size=256))  # size is unknown
SysObjects_table.addColumn(Column(37,  9, 'ConstraintColumn', Column.TYPE_NVARCHAR, size=256))  # size is unknown

SysObjects_table.validate()

class LvData:
    '''
    This class represents a Long Value data that is stored in LV pages. The data is only extracted
    on demand.
    '''
    def __init__(self, pageIds, size, encoding=None):
        self.pageIds = pageIds
        self.size = size
        self.encoding = encoding

    def extract(self, db):
        data = bytearray()
        size = self.size
        if len(self.pageIds) * (4096 - 16) < size:
            raise RuntimeError('not enough LV pages (%d) for storing %d bytes'
                    % (len(self.pageIds), self.size))

        for pageId in self.pageIds:
            page = db.readPage(pageId)
            if page is None:
                raise RuntimeError('cannot read page %05x' % (pageId,))
            if page.type != PageType.LV:
                raise RuntimeError('page %05x is not LV type (%s)' % (pageId, PageType(page.type)))

            chunk_size = 4096 - 16
            if chunk_size > size:
                chunk_size = size
            data += page.data[16:16+chunk_size]
            size -= chunk_size

        if size != 0:
            raise RuntimeError('not enough LV pages (%d) for storing %d bytes'
                    % (len(self.pageIds), self.size))

        return data if self.encoding is None else data.decode(self.encoding)

class LvMapData(LvData):
    '''
    This class represents a Long Value data that is stored in LVMAP pages (which store a list of
    LV pages). The data is only extracted on demand.
    '''
    def __init__(self, lvmapPageIds, size, encoding=None):
        super().__init__([], size, encoding)
        self.lvmapPageIds = lvmapPageIds

    def extract(self, db):
        if len(self.pageIds) == 0:
            # Extract the page IDs from the LVMAP pages
            for lvmapPageId in self.lvmapPageIds:
                page = db.readPage(lvmapPageId)
                if page is None:
                    raise RuntimeError('cannot read page %05x' % (lvmapPageId,))
                if page.type != PageType.LVMAP:
                    raise RuntimeError('page %05x is not LVMAP type (%s)' % (lvmapPageId, PageType(page.type)))

                pageCount = QWORD(page.data, len(page.data) - 8)
                wordCount = math.ceil(pageCount / 3)
                debug_trace('lvmapPageId=%05x, pageCount=%s', lvmapPageId, pageCount)
                count = 0
                for n in range(wordCount):
                    word = QWORD(page.data, 16 + n * 8)
                    for _ in range(3):
                        if count == pageCount:
                            break
                        count += 1
                        self.pageIds.append(word & 0xFFFFF)
                        word >>= 20
            debug_trace('self.pageIds=%s', len(self.pageIds))

        return super().extract(db)

class DataBase:
    SysObjects_BTree = 1028

    def __init__(self, fpath, key=None, verify=False, _decrypt_only=False):
        self.fpath = fpath
        self.key = key

        if self.key is not None:
            if not check_key(self.fpath, self.key):
                raise RuntimeError('bad key')

            self.key_hash = hashes.Hash(hashes.SHA1())
            self.key_hash.update(self.key)

        self.pageToAddr = {0: 0}
        self.maxPageId = None
        self.tablePages = {}
        self.pageCache = {}
        self.pageCacheOrder = []
        self.pageCover = None

        self.fh = open(fpath, 'rb')

        '''
        pageId 0: always at pageAddr 0
        pageId 1: pageAddr is written in header (at 0x2c)
        pageId <= 1026 are mapped with MapA (== pageId 1)
        pageId > 1026 are mapped with MapB

        Page 1 is a MapA and pages 2-1026 are MapB
        Page 1027 is the PAGE table for SysObjects
        Page 1028 is a BTree (root for SysObjects)

        MapA contains the mapping of pages 2 to 1026. QWORD at offset 0x10 contains the pageAddr
        of pages 2, 3 and 4, QWORD at offset 0x18 contains the pageAddr of pages 5, 6 and 7, ...
        MapB contains the mapping of pages 1027+N*1527 to 1027+(N+1)*1527.
        Each QWORD in each map contains 3 pageAddr. The first 20 lsb are pageAddr of pageNum,
        the next 20 bits are pageAddr of pageNum+1 and the next 20 bits ar pageAddr of pageNum+2.

        HEADER page:
            Offset  Size    Info
              0x10     4    should be 0x357B9D or 0x357DD9
              0x18     4    should be 0x00000521 (version number?)
              0x1C     4    ???
              0x20     4    ???
              0x24     4    ??? (address of a page?)
              0x28     4    file locale (LCID)
              0x2C     4    address of page #1
              0x38     2    ???
              0x4C    96    key check (encrypted SHA1 hash of the key)
              0xBC     4    IV for key check
              0xB0     8    ???
             0x200   512    stats
        '''

        self.header = self.readPage(0)
        if self.header is None:
            raise RuntimeError('cannot read page 0')

        if _decrypt_only:
            # Only decrypt the file and store it in a BIN file
            # (the result is probably not usable by SQL CE Server)
            pageToAddr = defaultdict(list)
            out_fpath = fpath + '.bin'
            print('Writing decrypted file to "%s"...' % (out_fpath,))
            with open(out_fpath, 'wb') as out:
                addr = 0
                while True:
                    page = self.readPage(-1, addr=addr)
                    if page is None:
                        break

                    out.write(page.data)
                    if page.data[:4] != b'\x00\x00\x00\x00':
                        pageToAddr[page.id].append(addr)
                    addr += 1

            out_fpath = fpath + '.map'
            print('Writing page ID to file offset mapping to "%s"...' % (out_fpath,))
            with open(out_fpath, 'wt') as out:
                for id in sorted(pageToAddr.keys()):
                    addr = pageToAddr[id]
                    if len(addr) == 1:
                        print('%05x => %08x' % (id, addr[0] * 4096), file=out)
                    else:
                        print('%05x => (%s)' % (id, ', '.join(['%08x' % (a * 4096) for a in addr])), file=out)

            return

        self.pageToAddr[1] = DWORD(self.header.data, 0x2C) & 0xFFFFF

        mapA = self.readPage(1)
        if mapA is None:
            raise RuntimeError('cannot read page 1')

        pageCover = defaultdict(set)
        pageCover[PageType.HEADER].add(0)
        pageCover[PageType.MAPA].add(1)

        pageTypes = defaultdict(int)
        pageTypes[self.header.type] += 1
        pageTypes[mapA.type] += 1
        maxPageId = 1
        for i in range(1025):
            id = i + 2
            bits = QWORD(mapA.data, 16 + (i // 3) * 8)
            addr = (bits >> ((i % 3) * 20)) & 0xFFFFF
            # print('bits=%016x, i=%d, addr=%05x' % (bits, i, addr))
            if addr == 0:
                continue

            self.pageToAddr[id] = addr
            mapB = self.readPage(id)
            if mapB is None:
                raise RuntimeError('cannot read page %d (at %08x)' % (id, addr))

            pageCover[mapB.type].add(id)
            pageTypes[mapB.type] += 1

            id = 1027 + i * 1527 - 1
            for j in range(1528):
                id += 1
                bits = QWORD(mapB.data, 16 + (j // 3) * 8)
                addr = (bits >> ((j % 3) * 20)) & 0xFFFFF
                if addr == 0:
                    continue

                self.pageToAddr[id] = addr
                maxPageId = id

                page = self.readPage(id, validate=False, decrypt=False)
                if page is None:
                    raise RuntimeError('cannot read page %d (at %08x)' % (id, addr))
                pageTypes[page.type] += 1

                if page.type == PageType.DATA:
                    self.decryptPage(page)
                    DataPage(page).validate(self)
                elif page.type == PageType.TABLE:
                    self.decryptPage(page)
                    try:
                        tablePage = TablePage(page, self)
                        tablePage.validate(self)
                        self.tablePages[page.id] = tablePage
                        pageCover[page.type].add(page.id)
                    except RuntimeError as e:
                        print_err('Warning: %s' % (e,))

        self.maxPageId = maxPageId

        print('Found %d pages (maxPageId=%06x)' % (len(self.pageToAddr), self.maxPageId))
        print(', '.join(['%s: %d' % (PageType(t), pageTypes[t]) for t in sorted(pageTypes.keys())]))

        self.pageCover = pageCover

        # Try to find the TABLE page for __SysObjects
        # (we cannot parse BTREE pages yet, so using heuristics instead)

        # FIXME The TABLE page for SysObjects is always page 1027 it seems...

        # print('Looking for __SysObjects table...')
        self.SysObjectsPage = None
        for tablePage in self.tablePages.values():
            if tablePage.getCount() == 0:
                continue

            # print('Looking in TABLE page %05x (at %08x)'
            #         % (tablePage.page.id, tablePage.page.address))
            for idx, record in enumerate(tablePage):
                if record is None:
                    continue

                if len(record) < 93:
                    #TODO break
                    continue

                # TODO Try to parse the record with the Table method

                prefix = record[93:]
                end = prefix.find(0)
                if end != -1:
                    prefix = prefix[:end]

                if len(prefix) != 12:
                    continue

                try:
                    prefix = prefix.decode('utf8')
                except UnicodeDecodeError:
                    print_err('Decode error for record %d of TABLE page %05x (at %08x)'
                            % (idx, tablePage.page.id, tablePage.page.address))
                    print_err(record)
                    raise

                if prefix == '__SysObjects':
                    print('Found __SysObjects table at page %05x' % (tablePage.page.id,))
                    self.SysObjectsPage = tablePage
                    break

            if self.SysObjectsPage is not None:
                break

        if self.SysObjectsPage is None:
            raise RuntimeError('cannot find __SysObjects table')

        # Extract tables definition
        self.tables = {}
        for idx, record in enumerate(self.SysObjectsPage):
            if record is None:
                continue

            row = SysObjects_table.extractRow(record, sortByIndex=True)
            # print(row)
            if row['ObjectType'] == ObjectType.TABLE:
                table = Table(row['ObjectName'], pageId=row['TablePageId'], nick=row['TableNick'],
                        trackingType=row['TableTrackingType'], ddlGranted=row['TableDdlGranted'],
                        readOnly=row['TableReadOnly'], compressed=row['TableCompressed'])
                if table.name in self.tables:
                    raise RuntimeError('table %s found multiple times' % (table.name,))
                self.tables[table.name] = table

            elif row['ObjectType'] == ObjectType.COLUMN:
                column = Column(row['ObjectOrdinal'], row['ColumnPosition'], row['ObjectName'],
                        Column.TYPES[row['ColumnType']], size=row['ColumnSize'],
                        precision=row['ColumnPrecision'], scale=row['ColumnScale'],
                        fixed=row['ColumnFixed'], nullable=row['ColumnNullable'],
                        writeable=row['ColumnWriteable'], autoType=row['ColumnAutoType'],
                        default=row['ColumnDefault'], compressed=row['ColumnCompressed'])
                table = self.tables.get(row['ObjectOwner'])
                if table is None:
                    print_err(row)
                    raise RuntimeError('cannot find table %s for column %s'
                            % (row['ObjectOwner'], column.name))
                table.addColumn(column)

            elif row['ObjectType'] == ObjectType.CONSTRAINT:
                # Not supported
                pass

            else:
                print_err('Warning: ignoring unsupported object type %d (for %s)'
                        % (row['ObjectType'], row['ObjectName']))

        # Check all the tables
        for table in self.tables.values():
            table.validate()

            # TODO Dump the table schema in SQL format?

            # print('Visiting %s...' % (table.name,))

            # Warn if compression is used (we don't support it)
            if table.compressed:
                print_err('Warning: table %s is compressed' % (table.name,))
            for column in table.columns:
                if column.compressed:
                    print_err('Warning: column %s.%s is compressed' % (table.name, column.name))

            page = self.readPage(table.pageId)
            if page is None:
                raise RuntimeError('cannot read TABLE page %05x for %s'
                        % (table.pageId, table.name))
            tablePage = TablePage(page, self)
            tablePage.validate(self)

            if verify:
                for idx, record in enumerate(tablePage):
                    if record is None:
                        continue

                    row = table.extractRow(record, sortByIndex=True)

                    for n, v in row.items():
                        if isinstance(v, LvData):
                            v.extract(self)

                    # TODO Dump the table content in SQL format?

    def pageCoverStats(self):
        return ', '.join(['%s: %d' % (PageType(t), len(self.pageCover[t]))
                for t in sorted(self.pageCover.keys())])

    def readPage(self, id, validate=True, decrypt=True, addr=None):
        cachedPage = self.pageCache.get(id)
        if id >= 0 and cachedPage is not None:
            # Update page position in cache
            for i, pageId in enumerate(self.pageCacheOrder):
                if pageId == id:
                    self.pageCacheOrder = self.pageCacheOrder[:i] + self.pageCacheOrder[i+1:] + [id]
                    break
            return cachedPage

        if addr is None:
            addr = self.pageToAddr.get(id)
            if addr is None:
                # Not found
                debug_trace('readPage(id=%05x, address=n/a)', id)
                return None
        debug_trace('readPage(id=%05x, address=%08x)', id, addr)

        self.fh.seek(addr * 4096)
        data = self.fh.read(4096)
        if len(data) != 4096:
            return None

        dword_0 = DWORD(data, 0)
        dword_1 = DWORD(data, 4)

        checksum = dword_0
        pageId = dword_1 & 0xFFFFF
        pageType = (dword_1 >> 20) & 0xF

        decrypted = self.key is None
        if self.key is not None and pageType > 2 and decrypt:
            # Page is encrypted (using checksum as key)
            data = data[:16] + decrypt_bytes(self.key_hash, data[:4], data[16:])
            decrypted = True

        if decrypted and validate and checksum != do_checksum(data[4:]):
            raise RuntimeError('bad checksum for page %d (at %08x)' % (id, addr))

        page = Page(pageId, pageType, data, addr*4096, decrypted=decrypted)

        if id >= 0 and decrypted and validate and pageType != PageType.LV:
            # Cache the page
            self.pageCache[id] = page
            self.pageCacheOrder.append(id)
            if len(self.pageCacheOrder) > 100:
                # Remove oldest cached page
                del self.pageCache[self.pageCacheOrder[0]]
                self.pageCacheOrder = self.pageCacheOrder[1:]

        if self.pageCover is not None:
            self.pageCover[page.type].add(page.id)

        return page

    def decryptPage(self, page, validate=True):
        if page.decrypted:
            return

        if self.key is not None and page.type > 2:
            # Page is encrypted (using checksum as key)
            page.data = page.data[:16] + decrypt_bytes(self.key_hash, page.data[:4], page.data[16:])

        page.decrypted = True

        if validate:
            checksum = DWORD(page.data, 0)
            if checksum != do_checksum(page.data[4:]):
                raise RuntimeError('bad checksum for page %d (at %08x)' % (id, addr))

    def checkId(self, id):
        if id == 0xFFFF:
            return False
        if self.maxPageId is not None and id > self.maxPageId:
            return False
        return True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.fh.close()
        self.fh = None

def main(argv):
    # TODO Let user dump schema and full DB
    return 0

if __name__ == '__main__':
    sys.exit(main(sys.argv))