"""
Moving Picture Experts Group (MPEG) video version 1 and 2 parser.

Information:
- http://www.mpucoder.com/DVD/
- http://dvd.sourceforge.net/dvdinfo/
- http://www.mit.jyu.fi/mweber/leffakone/software/parsempegts/
- http://homepage.mac.com/rnc/EditMpegHeaderIFO.html

Author: Victor Stinner
Creation date: 15 september 2006
"""

from hachoir_parser import Parser
from hachoir_core.field import (FieldSet,
    FieldError, ParserError,
    Bit, Bits, Bytes, PaddingBits, NullBits,
    UInt8, UInt16,
    RawBytes, PaddingBytes,
    Enum)
from hachoir_core.endian import BIG_ENDIAN
from hachoir_core.text_handler import textHandler, hexadecimal

class Timestamp(FieldSet):
    static_size = 36

    def createValue(self):
        return (self["c"].value << 30) + (self["b"].value << 15) + self["a"].value

    def createFields(self):
        yield Bits(self, "c", 3)
        yield Bit(self, "sync[]") # =True
        yield Bits(self, "b", 15)
        yield Bit(self, "sync[]") # =True
        yield Bits(self, "a", 15)
        yield Bit(self, "sync[]") # =True

class SCR(FieldSet):
    static_size = 35

    def createFields(self):
        yield Bits(self, "scr_a", 3)
        yield Bit(self, "sync[]") # =True
        yield Bits(self, "scr_b", 15)
        yield Bit(self, "sync[]") # =True
        yield Bits(self, "scr_c", 15)

class ProgramStream(FieldSet):
    def createFields(self):
        if self.stream.readBits(self.absolute_address, 2, self.endian) == 1:
            # MPEG version 2
            yield Bits(self, "sync[]", 2)
            yield SCR(self, "scr")
            yield Bit(self, "sync[]")
            yield Bits(self, "scr_ext", 9)
            yield Bit(self, "sync[]")
            yield Bits(self, "mux_rate", 22)
            yield Bits(self, "sync[]", 2)
            yield PaddingBits(self, "reserved", 5, pattern=1)
            yield Bits(self, "stuffing_length", 3)
            count = self["stuffing_length"].value
            if count:
                yield PaddingBytes(self, "stuffing", count, pattern="\xff")
        else:
            # MPEG version 1
            yield Bits(self, "sync[]", 4)
            yield Bits(self, "scr_a", 3)
            yield Bit(self, "sync[]")
            yield Bits(self, "scr_b", 15)
            yield Bit(self, "sync[]")
            yield Bits(self, "scr_c", 15)
            yield Bits(self, "sync[]", 2)
            yield Bits(self, "mux_rate", 22)
            yield Bit(self, "sync[]")

    def validate(self):
        if self["mux_rate"].value == 0:
            return "Invalid mux rate"
        sync0 = self["sync[0]"]
        if (sync0.size == 2 and sync0.value == 1):
            # MPEG2
            pass
            if not self["sync[1]"].value \
            or not self["sync[2]"].value \
            or self["sync[3]"].value != 3:
                return "Invalid synchronisation bits"
        elif (sync0.size == 4 and sync0.value == 2):
            # MPEG1
            if not self["sync[1]"].value \
            or not self["sync[2]"].value \
            or self["sync[3]"].value != 3 \
            or not self["sync[4]"].value:
                return "Invalid synchronisation bits"
        else:
            return "Unknown version"
        return True

class defaultParser(FieldSet):
    def createFields(self):
        yield RawBytes(self, "data", self["../length"].value)

class Padding(FieldSet):
    def createFields(self):
        yield PaddingBytes(self, "data", self["../length"].value)

class VideoExtension2(FieldSet):
    def createFields(self):
        yield Bit(self, "sync[]") # =True
        yield Bits(self, "ext_length", 7)
        yield NullBits(self, "reserved[]", 8)
        size = self["ext_length"].value
        if size:
            yield RawBytes(self, "ext_bytes", size)

class VideoExtension1(FieldSet):
    def createFields(self):
        yield Bit(self, "has_private")
        yield Bit(self, "has_pack_lgth")
        yield Bit(self, "has_pack_seq")
        yield Bit(self, "has_pstd_buffer")
        yield Bits(self, "sync[]", 3) # =7
        yield Bit(self, "has_extension2")

        if self["has_private"].value:
            yield RawBytes(self, "private", 16)

        if self["has_pack_lgth"].value:
            yield UInt8(self, "pack_lgth")

        if self["has_pack_seq"].value:
            yield Bit(self, "sync[]") # =True
            yield Bits(self, "pack_seq_counter", 7)
            yield Bit(self, "sync[]") # =True
            yield Bit(self, "mpeg12_id")
            yield Bits(self, "orig_stuffing_length", 6)

        if self["has_pstd_buffer"].value:
            yield Bits(self, "sync[]", 2) # =1
            yield Enum(Bit(self, "pstd_buffer_scale"),
                {True: "128 bytes", False: "1024 bytes"})
            yield Bits(self, "pstd_size", 13)

class Video(FieldSet):
    def createFields(self):
        yield Bits(self, "sync[]", 2) # =2
        if self["sync[0]"].value != 2:
            raise ParserError("Unknown video elementary data")
        yield Bits(self, "is_scrambled", 2)
        yield Bits(self, "priority", 1)
        yield Bit(self, "alignment")
        yield Bit(self, "is_copyrighted")
        yield Bit(self, "is_original")
        yield Bit(self, "has_pts", "Presentation Time Stamp")
        yield Bit(self, "has_dts", "Decode Time Stamp")
        yield Bit(self, "has_escr", "Elementary Stream Clock Reference")
        yield Bit(self, "has_es_rate", "Elementary Stream rate")
        yield Bit(self, "dsm_trick_mode")
        yield Bit(self, "has_copy_info")
        yield Bit(self, "has_prev_crc", "If True, previous PES packet CRC follows")
        yield Bit(self, "has_extension")
        yield UInt8(self, "size")

        # Time stamps
        if self["has_pts"].value:
            yield Bits(self, "sync[]", 4) # =2, or 3 if has_dts=True
            yield Timestamp(self, "pts")
        if self["has_dts"].value:
            if not(self["has_pts"].value):
                raise ParserError("Invalid PTS/DTS values")
            yield Bits(self, "sync[]", 4) # =1
            yield Timestamp(self, "dts")

        if self["has_escr"].value:
            yield Bits(self, "sync[]", 2) # =0
            yield SCR(self, "escr")

        if self["has_es_rate"].value:
            yield Bit(self, "sync[]") # =True
            yield Bits(self, "es_rate", 14) # in units of 50 bytes/second
            yield Bit(self, "sync[]") # =True

        if self["has_copy_info"].value:
            yield Bit(self, "sync[]") # =True
            yield Bits(self, "copy_info", 7)

        if self["has_prev_crc"].value:
            yield textHandler(UInt16(self, "prev_crc"), hexadecimal)

        # --- Extension ---
        if self["has_extension"].value:
            yield VideoExtension1(self, "extension")
            if self["extension/has_extension2"].value:
                yield VideoExtension2(self, "extension2")
        yield Chunk(self, "chunk[]")

class Chunk(FieldSet):
    ISO_END_CODE = 0xB9
    tag_info = {
# SLICE_START_CODE_MIN : 0x01
# SLICE_START_CODE_MAX : 0xAF
#define SYSTEM_START_CODE_MIN   0x1B9
#define SYSTEM_START_CODE_MAX   0x1FF

        0x00: ("pict_start[]",   None,          "Picture start"),
        0xB2: ("data_start[]",   None,          "Data start"),
        0xB3: ("seq_hdr[]",      None,          "Sequence header"),
        0xB4: ("seq_err[]",      None,          "Sequence error"),
        0xB5: ("ext_start[]",    None,          "Extension start"),
        0xB7: ("seq_end[]",      None,          "Sequence end"),
        0xB8: ("group_start[]",  None,          "Group start"),
        0xB9: ("end",            None,          "End"),
        0xBA: ("pack_start[]",   ProgramStream, "Pack start"),
        0xBB: ("system_start[]", None,          "System start"),
        0xBE: ("padding[]",      Padding,       "Padding"),
        0xC0: ("audio[]",        None,          "Audio"),
        0xE0: ("video[]",        Video,         "Video elementary"),
        0xFF: ("directory[]",    None,          "Program Stream Directory"),
    }

    def __init__(self, *args):
        FieldSet.__init__(self, *args)
        tag = self["tag"].value
        if tag in self.tag_info:
            self._name, self.parser, self._description = self.tag_info[tag]
            if not self.parser:
                self.parser = defaultParser
        else:
            self.parser = defaultParser
        if self.parser and self.parser != ProgramStream and "length" in self:
            self._size = (6 + self["length"].value) * 8

    def createFields(self):
        yield Bytes(self, "sync", 3)
        yield textHandler(UInt8(self, "tag"), hexadecimal)
        if self.parser:
            if self.parser != ProgramStream:
                yield UInt16(self, "length")
                if not self["length"].value:
                    return
            yield self.parser(self, "content")

    def createDescription(self):
        return "Chunk: tag %s" % self["tag"].display

class MPEGVideoFile(Parser):
    PARSER_TAGS = {
        "id": "mpeg_video",
        "category": "video",
        "file_ext": ("mpeg", "mpg", "mpe", "vob"),
        "mime": (u"video/mpeg", u"video/mp2p"),
        "min_size": 12*8,
#TODO:        "magic": xxx,
        "description": "MPEG video, version 1 or 2"
    }
    endian = BIG_ENDIAN
    version = None

    def createFields(self):
        while self.current_size < self.size:
            yield Chunk(self, "chunk[]")

    def validate(self):
        try:
            pack = self[0]
        except FieldError:
            return "Unable to create first chunk"
        if pack.name != "pack_start[0]":
            return "Invalid first chunk"
        if pack["sync"].value != "\0\0\1":
            return "Invalid synchronisation"
        return pack["content"].validate()

    def getVersion(self):
        if not self.version:
            if self["pack_start[0]/content/sync[0]"].size == 2:
                self.version = 2
            else:
                self.version = 1
        return self.version

    def createDescription(self):
        if self.getVersion() == 2:
            return "MPEG-2 video"
        else:
            return "MPEG-1 video"

