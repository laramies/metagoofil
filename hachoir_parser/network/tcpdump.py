"""
Tcpdump parser

Source:
 * libpcap source code (file savefile.c)
 * RFC 791 (IPv4)
 * RFC 792 (ICMP)
 * RFC 793 (TCP)
 * RFC 1122 (Requirements for Internet Hosts)

Author: Victor Stinner
Creation: 23 march 2006
"""

from hachoir_parser import Parser
from hachoir_core.field import (FieldSet, ParserError,
    Enum, Bytes, NullBytes, RawBytes,
    UInt8, UInt16, UInt32, Int32, TimestampUnix32,
    Bit, Bits, NullBits)
from hachoir_core.endian import NETWORK_ENDIAN, LITTLE_ENDIAN
from hachoir_core.tools import humanDuration
from hachoir_core.text_handler import textHandler, hexadecimal
from hachoir_core.tools import createDict
from hachoir_parser.network.common import MAC48_Address, IPv4_Address

def diff(field):
    return humanDuration(field.value*1000)

class Layer(FieldSet):
    endian = NETWORK_ENDIAN
    def parseNext(self, parent):
        return None

class ARP(Layer):
    opcode_name = {
        1: "request",
        2: "reply"
    }
    endian = NETWORK_ENDIAN

    def createFields(self):
        yield UInt16(self, "hw_type")
        yield UInt16(self, "proto_type")
        yield UInt8(self, "hw_size")
        yield UInt8(self, "proto_size")
        yield Enum(UInt16(self, "opcode"), ARP.opcode_name)
        yield MAC48_Address(self, "src_mac")
        yield IPv4_Address(self, "src_ip")
        yield MAC48_Address(self, "dst_mac")
        yield IPv4_Address(self, "dst_ip")

    def createDescription(self):
        desc = "ARP: %s" % self["opcode"].display
        opcode = self["opcode"].value
        src_ip = self["src_ip"].display
        dst_ip = self["dst_ip"].display
        if opcode == 1:
            desc += ", %s ask %s" % (dst_ip, src_ip)
        elif opcode == 2:
            desc += " from %s" % src_ip
        return desc

class TCP_Option(FieldSet):
    NOP = 1
    MAX_SEGMENT = 2
    WINDOW_SCALE = 3
    SACK = 4
    TIMESTAMP = 8

    code_name = {
        NOP: "NOP",
        MAX_SEGMENT: "Max segment size",
        WINDOW_SCALE: "Window scale",
        SACK: "SACK permitted",
        TIMESTAMP: "Timestamp"
    }

    def __init__(self, *args):
        FieldSet.__init__(self, *args)
        if self["code"].value != self.NOP:
            self._size = self["length"].value * 8
        else:
            self._size = 8

    def createFields(self):
        yield Enum(UInt8(self, "code", "Code"), self.code_name)
        code = self["code"].value
        if code == self.NOP:
            return
        yield UInt8(self, "length", "Option size in bytes")
        if code == self.MAX_SEGMENT:
            yield UInt16(self, "max_seg", "Maximum segment size")
        elif code == self.WINDOW_SCALE:
            yield UInt8(self, "win_scale", "Window scale")
        elif code == self.TIMESTAMP:
            yield UInt32(self, "ts_val", "Timestamp value")
            yield UInt32(self, "ts_ecr", "Timestamp echo reply")
        else:
            size = (self.size - self.current_size) // 8
            if size:
                yield RawBytes(self, "data", size)

    def createDescription(self):
        return "TCP option: %s" % self["code"].display

class TCP(FieldSet):
    port_name = {
        13: "daytime",
        20: "ftp data",
        21: "ftp",
        23: "telnet",
        25: "smtp",
        53: "dns",
        63: "dhcp/bootp",
        80: "HTTP",
        110: "pop3",
        119: "nntp",
        123: "ntp",
        139: "netbios session service",
        1863: "MSNMS",
        6667: "IRC"
    }
    endian = NETWORK_ENDIAN

    def createFields(self):
        yield Enum(UInt16(self, "src"), self.port_name)
        yield Enum(UInt16(self, "dst"), self.port_name)
        yield UInt32(self, "seq_num")
        yield UInt32(self, "ack_num")

        yield Bits(self, "hdrlen", 6, "Header lenght")
        yield NullBits(self, "reserved", 2, "Reserved")

        yield Bit(self, "cgst", "Congestion Window Reduced")
        yield Bit(self, "ecn-echo", "ECN-echo")
        yield Bit(self, "urg", "Urgent")
        yield Bit(self, "ack", "Acknowledge")
        yield Bit(self, "psh", "Push mmode")
        yield Bit(self, "rst", "Reset connection")
        yield Bit(self, "syn", "Synchronize")
        yield Bit(self, "fin", "Stop the connection")

        yield UInt16(self, "winsize", "Windows size")
        yield textHandler(UInt16(self, "checksum"), hexadecimal)
        yield UInt16(self, "urgent")

        size = self["hdrlen"].value*8 - self.current_size
        while 0 < size:
            option = TCP_Option(self, "option[]")
            yield option
            size -= option.size

    def parseNext(self, parent):
        return None

    def createDescription(self):
        src = self["src"].value
        dst = self["dst"].value
        if src < 32768:
            src = self["src"].display
        else:
            src = None
        if dst < 32768:
            dst = self["dst"].display
        else:
            dst = None
        desc = "TCP"
        if src != None and dst != None:
            desc += " (%s->%s)" % (src, dst)
        elif src != None:
            desc += " (%s->)" % (src)
        elif dst != None:
            desc += " (->%s)" % (dst)

        # Get flags
        flags = []
        if self["syn"].value:
            flags.append("SYN")
        if self["ack"].value:
            flags.append("ACK")
        if self["fin"].value:
            flags.append("FIN")
        if self["rst"].value:
            flags.append("RST")
        if flags:
            desc += " [%s]" % (",".join(flags))
        return desc

class UDP(FieldSet):
    port_name = {
        12: "daytime",
        22: "ssh",
        53: "DNS",
        67: "dhcp/bootp",
        80: "http",
        110: "pop3",
        123: "ntp",
        137: "netbios name service",
        138: "netbios datagram service"
    }
    endian = NETWORK_ENDIAN

    def createFields(self):
        yield Enum(UInt16(self, "src"), UDP.port_name)
        yield Enum(UInt16(self, "dst"), UDP.port_name)
        yield UInt16(self, "length")
        yield textHandler(UInt16(self, "checksum"), hexadecimal)

    def parseNext(self, parent):
        return None

    def createDescription(self):
        return "UDP (%s->%s)" % (self["src"].display, self["dst"].display)

class ICMP(FieldSet):
    REJECT = 3
    PONG = 0
    PING = 8
    type_desc = {
        PONG: "Pong",
        REJECT: "Reject",
        PING: "Ping"
    }
    reject_reason = {
        0: "net unreachable",
        1: "host unreachable",
        2: "protocol unreachable",
        3: "port unreachable",
        4: "fragmentation needed and DF set",
        5: "source route failed",
        6: "Destination network unknown error",
        7: "Destination host unknown error",
        8: "Source host isolated error",
        9: "Destination network administratively prohibited",
        10: "Destination host administratively prohibited",
        11: "Unreachable network for Type Of Service",
        12: "Unreachable host for Type Of Service.",
        13: "Communication administratively prohibited",
        14: "Host precedence violation",
        15: "Precedence cutoff in effect"
    }
    endian = NETWORK_ENDIAN

    def createFields(self):
        # Type
        yield Enum(UInt8(self, "type"), self.type_desc)
        type = self["type"].value

        # Code
        field = UInt8(self, "code")
        if type == 3:
            field = Enum(field, self.reject_reason)
        yield field

        # Options
        yield textHandler(UInt16(self, "checksum"), hexadecimal)
        if type in (self.PING, self.PONG): # and self["code"].value == 0:
            yield UInt16(self, "id")
            yield UInt16(self, "seq_num")
            # follow: ping data
        elif type == self.REJECT:
            yield NullBytes(self, "empty", 2)
            yield UInt16(self, "hop_mtu", "Next-Hop MTU")

    def createDescription(self):
        type = self["type"].value
        if type in (self.PING, self.PONG):
            return "%s (num=%s)" % (self["type"].display, self["seq_num"].value)
        else:
            return "ICMP (%s)" % self["type"].display

    def parseNext(self, parent):
        if self["type"].value == self.REJECT:
            return IPv4(parent, "rejected_ipv4")
        else:
            return None

class IPv4(Layer):
    endian = NETWORK_ENDIAN
    PROTOCOL_INFO = {
        0x01: ("icmp", ICMP, "ICMP"),
        0x06: ("tcp",  TCP, "TCP"),
        0x11: ("udp",  UDP, "UDP"),
    }
    PROTOCOL_NAME = createDict(PROTOCOL_INFO, 2)

    precedence_name = {
        7: "Network Control",
        6: "Internetwork Control",
        5: "CRITIC/ECP",
        4: "Flash Override",
        3: "Flash",
        2: "Immediate",
        1: "Priority",
        0: "Routine",
    }

    def __init__(self, *args):
        FieldSet.__init__(self, *args)
        self._size = self["hdr_size"].value * 32

    def createFields(self):
        yield Bits(self, "version", 4, "Version")
        yield Bits(self, "hdr_size", 4, "Header size divided by 5")

        # Type of service
        yield Enum(Bits(self, "precedence", 3, "Precedence"), self.precedence_name)
        yield Bit(self, "low_delay", "If set, low delay, else normal delay")
        yield Bit(self, "high_throu", "If set, high throughput, else normal throughput")
        yield Bit(self, "high_rel", "If set, high relibility, else normal")
        yield NullBits(self, "reserved[]", 2, "(reserved for future use)")

        yield UInt16(self, "length")
        yield UInt16(self, "id")

        yield NullBits(self, "reserved[]", 1)
        yield Bit(self, "df", "Don't fragment")
        yield Bit(self, "more_frag", "There are more fragments? if not set, it's the last one")
        yield Bits(self, "frag_ofst_lo", 5)
        yield UInt8(self, "frag_ofst_hi")
        yield UInt8(self, "ttl", "Type to live")
        yield Enum(UInt8(self, "protocol"), self.PROTOCOL_NAME)
        yield textHandler(UInt16(self, "checksum"), hexadecimal)
        yield IPv4_Address(self, "src")
        yield IPv4_Address(self, "dst")

        size = (self.size - self.current_size) // 8
        if size:
            yield RawBytes(self, "options", size)

    def parseNext(self, parent):
        proto = self["protocol"].value
        if proto in self.PROTOCOL_INFO:
            name, parser, desc = self.PROTOCOL_INFO[proto]
            return parser(parent, name)
        else:
            return None

    def createDescription(self):
        return "IPv4 (%s>%s)" % (self["src"].display, self["dst"].display)

class Layer2(Layer):
    PROTO_INFO = {
        0x0800: ("ipv4", IPv4, "IPv4"),
        0x0806: ("arp",  ARP,  "ARP"),
    }
    PROTO_DESC = createDict(PROTO_INFO, 2)

    def parseNext(self, parent):
        try:
            name, parser, desc = self.PROTO_INFO[ self["protocol"].value ]
            return parser(parent, name)
        except KeyError:
            return None

class Unicast(Layer2):
    packet_type_name = {
        0: "Unicast to us"
    }
    def createFields(self):
        yield Enum(UInt16(self, "packet_type"), self.packet_type_name)
        yield UInt16(self, "addr_type", "Link-layer address type")
        yield UInt16(self, "addr_length", "Link-layer address length")
        length = self["addr_length"].value
        length = 8   # FIXME: Should we use addr_length or not?
        if length:
            yield RawBytes(self, "source", length)
        yield Enum(UInt16(self, "protocol"), self.PROTO_DESC)

class Ethernet(Layer2):
    static_size = 14*8
    def createFields(self):
        yield MAC48_Address(self, "dst")
        yield MAC48_Address(self, "src")
        yield Enum(UInt16(self, "protocol"), self.PROTO_DESC)

    def createDescription(self):
        return "Ethernet: %s>%s (%s)" % \
            (self["src"].display, self["dst"].display, self["protocol"].display)

class Packet(FieldSet):
    endian = LITTLE_ENDIAN

    def __init__(self, parent, name, parser, first_name):
        FieldSet.__init__(self, parent, name)
        self._size = (16 + self["caplen"].value) * 8
        self._first_parser = parser
        self._first_name = first_name

    def createFields(self):
        yield TimestampUnix32(self, "ts_epoch", "Timestamp (Epoch)")
        yield UInt32(self, "ts_nanosec", "Timestamp (nano second)")
        yield UInt32(self, "caplen", "length of portion present")
        yield UInt32(self, "len", "length this packet (off wire)")

        # Read different layers
        field = self._first_parser(self, self._first_name)
        while field:
            yield field
            field = field.parseNext(self)

        # Read data if any
        size = (self.size - self.current_size) // 8
        if size:
            yield RawBytes(self, "data", size)

    def getTimestamp(self):
        nano_sec = float(self["ts_nanosec"].value) / 100
        from datetime import timedelta
        return self["ts_epoch"].value + timedelta(microseconds=nano_sec)

    def createDescription(self):
        t0 = self["/packet[0]"].getTimestamp()
#        ts = max(self.getTimestamp() - t0, t0)
        ts = self.getTimestamp() - t0
        #text = ["%1.6f: " % ts]
        text = ["%s: " % ts]
        if "icmp" in self:
            text.append(self["icmp"].description)
        elif "tcp" in self:
            text.append(self["tcp"].description)
        elif "udp" in self:
            text.append(self["udp"].description)
        elif "arp" in self:
            text.append(self["arp"].description)
        else:
            text.append("Packet")
        return "".join(text)

class TcpdumpFile(Parser):
    PARSER_TAGS = {
        "id": "tcpdump",
        "category": "misc",
        "min_size": 24*8,
        "description": "Tcpdump file (network)",
        "magic": (("\xd4\xc3\xb2\xa1", 0),),
    }
    endian = LITTLE_ENDIAN

    LINK_TYPE = {
          1: ("ethernet", Ethernet),
        113: ("unicast", Unicast),
    }
    LINK_TYPE_DESC = createDict(LINK_TYPE, 0)

    def validate(self):
        if self["id"].value != "\xd4\xc3\xb2\xa1":
            return "Wrong file signature"
        if self["link_type"].value not in self.LINK_TYPE:
            return "Unknown link type"
        return True

    def createFields(self):
        yield Bytes(self, "id", 4, "Tcpdump identifier")
        yield UInt16(self, "maj_ver", "Major version")
        yield UInt16(self, "min_ver", "Minor version")
        yield Int32(self, "this_zone", "GMT to local time zone correction")
        yield Int32(self, "sigfigs", "accuracy of timestamps")
        yield UInt32(self, "snap_len", "max length saved portion of each pkt")
        yield Enum(UInt32(self, "link_type", "data link type"), self.LINK_TYPE_DESC)
        link = self["link_type"].value
        if link not in self.LINK_TYPE:
            raise ParserError("Unknown link type: %s" % link)
        name, parser = self.LINK_TYPE[link]
        while self.current_size < self.size:
            yield Packet(self, "packet[]", parser, name)

