"""
Compiled Java classes parser.

Author: Thomas de Grenier de Latour (TGL) <degrenier@easyconnect.fr>
Creation: 2006/11/01
Last-update: 2006/11/06

Introduction:
 * This parser is for compiled Java classes, aka .class files.  What is nice
   with this format is that it is well documented in the official Java VM specs.
 * Some fields, and most field sets, have dynamic sizes, and there is no offset
   to directly jump from an header to a given section, or anything like that.
   It means that accessing a field at the end of the file requires that you've
   already parsed almost the whole file.  That's not very efficient, but it's
   okay given the usual size of .class files (usually a few KB).
 * Most fields are just indexes of some "constant pool" entries, which holds
   most constant datas of the class.  And constant pool entries reference other
   constant pool entries, etc.  Hence, a raw display of this fields only shows
   integers and is not really understandable.  Because of that, this parser
   comes with two important custom field classes:
    - CPInfo are constant pool entries.  They have a type ("Utf8", "Methodref",
      etc.), and some contents fields depending on this type.  They also have a
      "__str__()" method, which returns a syntetic view of this contents.
    - CPIndex are constant pool indexes (UInt16).  It is possible to specify
      what type of CPInfo they are allowed to points to.  They also have a
      custom display method, usually printing something like "->  foo", where
      foo is the str() of their target CPInfo.

References:
 * The Java Virtual Machine Specification, 2nd edition, chapter 4, in HTML:
   http://java.sun.com/docs/books/vmspec/2nd-edition/html/ClassFile.doc.html
    => That's the spec i've been implementing so far. I think it is format
       version 46.0 (JDK 1.2).
 * The Java Virtual Machine Specification, 2nd edition, chapter 4, in PDF:
   http://java.sun.com/docs/books/vmspec/2nd-edition/ClassFileFormat.pdf
    => don't trust the URL, this PDF version is more recent than the HTML one.
       It highligths some recent additions to the format (i don't know the
       exact version though), which are not yet implemented in this parser.
 * The Java Virtual Machine Specification, chapter 4:
   http://java.sun.com/docs/books/vmspec/html/ClassFile.doc.html
    => describes an older format, probably version 45.3 (JDK 1.1).

TODO/FIXME:
 * Google for some existing free .class files parsers, to get more infos on
   the various formats differences, etc.
 * Write/compile some good tests cases.
 * Rework pretty-printing of CPIndex fields.  This str() thing sinks.
 * Add support of formats other than 46.0 (45.3 seems to already be ok, but
   there are things to add for later formats).
 * Make parsing robust: currently, the parser will die on asserts as soon as
   something seems wrong.  It should rather be tolerant, print errors/warnings,
   and try its best to continue.  Check how error-handling is done in other
   parsers.
 * Gettextize the whole thing.
 * Check whether Float32/64 are really the same as Java floats/double. PEP-0754
   says that handling of +/-infinity and NaN is very implementation-dependent.
   Also check how this values are displayed.
 * Make the parser edition-proof.  For instance, editing a constant-pool string
   should update the length field of it's entry, etc.  Sounds like a huge work.
"""

from hachoir_parser import Parser
from hachoir_core.field import (
        ParserError, FieldSet, StaticFieldSet,
        Enum, RawBytes, PascalString16, Float32, Float64,
        UInt8, UInt16, Int32, UInt32, Int64,
        Bit, NullBits )
from hachoir_core.endian import BIG_ENDIAN
from hachoir_core.text_handler import textHandler, hexadecimal

###############################################################################
def parse_flags(flags, flags_dict, show_unknown_flags=True, separator=" "):
    """
    Parses an integer representing a set of flags.  The known flags are
    stored with their bit-mask in a dictionnary.  Returns a string.
    """
    flags_list = []
    mask = 0x01
    while mask <= flags:
        if flags & mask:
            if mask in flags_dict:
                flags_list.append(flags_dict[mask])
            elif show_unknown_flags:
                flags_list.append("???")
        mask = mask << 1
    return separator.join(flags_list)


###############################################################################
code_to_type_name = {
    'B': "byte",
    'C': "char",
    'D': "double",
    'F': "float",
    'I': "int",
    'J': "long",
    'S': "short",
    'Z': "boolean",
    'V': "void",
}

def eat_descriptor(descr):
    """
    Read head of a field/method descriptor.  Returns a pair of strings, where
    the first one is a human-readable string representation of the first found
    type, and the second one is the tail of the parameter.
    """
    array_dim = 0
    while descr[0] == '[':
        array_dim += 1
        descr = descr[1:]
    if (descr[0] == 'L'):
        try: end = descr.find(';')
        except: raise ParserError("Not a valid descriptor string: " + descr)
        type = descr[1:end]
        descr = descr[end:]
    else:
        global code_to_type_name
        try:
            type = code_to_type_name[descr[0]]
        except KeyError:
            raise ParserError("Not a valid descriptor string: %s" % descr)
    return (type.replace("/", ".") + array_dim * "[]", descr[1:])

def parse_field_descriptor(descr, name=None):
    """
    Parse a field descriptor (single type), and returns it as human-readable
    string representation.
    """
    assert descr
    (type, tail) = eat_descriptor(descr)
    assert not tail
    if name:
        return type + " " + name
    else:
        return type

def parse_method_descriptor(descr, name=None):
    """
    Parse a method descriptor (params type and return type), and returns it
    as human-readable string representation.
    """
    assert descr and (descr[0] == '(')
    descr = descr[1:]
    params_list = []
    while descr[0] != ')':
        (param, descr) = eat_descriptor(descr)
        params_list.append(param)
    (type, tail) = eat_descriptor(descr[1:])
    assert not tail
    params = ", ".join(params_list)
    if name:
        return "%s %s(%s)" % (type, name, params)
    else:
        return "%s (%s)" % (type, params)

def parse_any_descriptor(descr, name=None):
    """
    Parse either a field or method descriptor, and returns it as human-
    readable string representation.
    """
    assert descr
    if descr[0] == '(':
        return parse_method_descriptor(descr, name)
    else:
        return parse_field_descriptor(descr, name)


###############################################################################
class FieldArray(FieldSet):
    """
    Holds a fixed length array of fields which all have the same type.  This
    type may be variable-length.  Each field will be named "foo[x]" (with x
    starting at 0).
    """
    def __init__(self, parent, name, elements_class, length,
            **elements_extra_args):
        """Create a FieldArray of <length> fields of class <elements_class>,
        named "<name>[x]".  The **elements_extra_args will be passed to the
        constructor of each field when yielded."""
        FieldSet.__init__(self, parent, name)
        self.array_elements_class = elements_class
        self.array_length = length
        self.array_elements_extra_args = elements_extra_args

    def createFields(self):
        for i in range(0, self.array_length):
            yield self.array_elements_class(self, "%s[%d]" % (self.name, i),
                    **self.array_elements_extra_args)

class ConstantPool(FieldSet):
    """
    ConstantPool is similar to a FieldArray of CPInfo fields, but:
    - numbering starts at 1 instead of zero
    - some indexes are skipped (after Long or Double entries)
    """
    def __init__(self, parent, name, length):
        FieldSet.__init__(self, parent, name)
        self.constant_pool_length = length
    def createFields(self):
        i = 1
        while i < self.constant_pool_length:
            name = "%s[%d]" % (self.name, i)
            yield CPInfo(self, name)
            i += 1
            if self[name].constant_type in ("Long", "Double"):
                i += 1


###############################################################################
class CPIndex(UInt16):
    """
    Holds index of a constant pool entry.
    """
    def __init__(self, parent, name, description=None, target_types=None,
                target_text_handler=(lambda x: x), allow_zero=False):
        """
        Initialize a CPIndex.
        - target_type is the tuple of expected type for the target CPInfo
          (if None, then there will be no type check)
        - target_text_handler is a string transformation function used for
          pretty printing the target str() result
        - allow_zero states whether null index is allowed (sometimes, constant
          pool index is optionnal)
        """
        UInt16.__init__(self, parent, name, description)
        if isinstance(target_types, str):
            self.target_types = (target_types,)
        else:
            self.target_types = target_types
        self.allow_zero = allow_zero
        self.target_text_handler = target_text_handler
        self.getOriginalDisplay = lambda: self.value

    def createDisplay(self):
        cp_entry = self.get_cp_entry()
        if self.allow_zero and not cp_entry:
            return "ZERO"
        assert cp_entry
        return "-> " + self.target_text_handler(str(cp_entry))

    def get_cp_entry(self):
        """
        Returns the target CPInfo field.
        """
        assert self.value < self["/constant_pool_count"].value
        if self.allow_zero and not self.value: return None
        cp_entry = self["/constant_pool/constant_pool[%d]" % self.value]
        assert isinstance(cp_entry, CPInfo)
        if self.target_types:
            assert cp_entry.constant_type in self.target_types
        return cp_entry


###############################################################################
class CPInfo(FieldSet):
    """
    Holds a constant pool entry.  Entries all have a type, and various contents
    fields depending on their type.
    """
    def createFields(self):
        yield Enum(UInt8(self, "tag"), self.root.CONSTANT_TYPES)
        if self["tag"].value not in self.root.CONSTANT_TYPES:
            raise ParserError("Java: unknown constant type (%s)" % self["tag"].value)
        self.constant_type = self.root.CONSTANT_TYPES[self["tag"].value]
        if self.constant_type == "Utf8":
            yield PascalString16(self, "bytes", charset="UTF-8")
        elif self.constant_type == "Integer":
            yield Int32(self, "bytes")
        elif self.constant_type == "Float":
            yield Float32(self, "bytes")
        elif self.constant_type == "Long":
            yield Int64(self, "bytes")
        elif self.constant_type == "Double":
            yield Float64(self, "bytes")
        elif self.constant_type == "Class":
            yield CPIndex(self, "name_index", "Class or interface name", target_types="Utf8")
        elif self.constant_type == "String":
            yield CPIndex(self, "string_index", target_types="Utf8")
        elif self.constant_type == "Fieldref":
            yield CPIndex(self, "class_index", "Field class or interface name", target_types="Class")
            yield CPIndex(self, "name_and_type_index", target_types="NameAndType")
        elif self.constant_type == "Methodref":
            yield CPIndex(self, "class_index", "Method class name", target_types="Class")
            yield CPIndex(self, "name_and_type_index", target_types="NameAndType")
        elif self.constant_type == "InterfaceMethodref":
            yield CPIndex(self, "class_index", "Method interface name", target_types="Class")
            yield CPIndex(self, "name_and_type_index", target_types="NameAndType")
        elif self.constant_type == "NameAndType":
            yield CPIndex(self, "name_index", target_types="Utf8")
            yield CPIndex(self, "descriptor_index", target_types="Utf8")
        else:
            raise ParserError("Not a valid constant pool element type: "
                    + self["tag"].value)

    def __str__(self):
        """
        Returns a human-readable string representation of the constant pool
        entry.  It is used for pretty-printing of the CPIndex fields pointing
        to it.
        """
        if self.constant_type == "Utf8":
            return self["bytes"].value
        elif self.constant_type in ("Integer", "Float", "Long", "Double"):
            return self["bytes"].display
        elif self.constant_type == "Class":
            class_name = str(self["name_index"].get_cp_entry())
            return class_name.replace("/",".")
        elif self.constant_type == "String":
            return str(self["string_index"].get_cp_entry())
        elif self.constant_type == "Fieldref":
            return "%s (from %s)" % (self["name_and_type_index"], self["class_index"])
        elif self.constant_type == "Methodref":
            return "%s (from %s)" % (self["name_and_type_index"], self["class_index"])
        elif self.constant_type == "InterfaceMethodref":
             return "%s (from %s)" % (self["name_and_type_index"], self["class_index"])
        elif self.constant_type == "NameAndType":
            return parse_any_descriptor(
                    str(self["descriptor_index"].get_cp_entry()),
                    name=str(self["name_index"].get_cp_entry()))
        else:
            # FIXME: Return "<error>" instead of raising an exception?
            raise ParserError("Not a valid constant pool element type: "
                    + self["tag"].value)


###############################################################################
# field_info {
#        u2 access_flags;
#        u2 name_index;
#        u2 descriptor_index;
#        u2 attributes_count;
#        attribute_info attributes[attributes_count];
# }
class FieldInfo(FieldSet):
    def createFields(self):
        # Access flags (16 bits)
        yield NullBits(self, "reserved[]", 8)
        yield Bit(self, "transient")
        yield Bit(self, "volatile")
        yield NullBits(self, "reserved[]", 1)
        yield Bit(self, "final")
        yield Bit(self, "static")
        yield Bit(self, "protected")
        yield Bit(self, "private")
        yield Bit(self, "public")

        yield CPIndex(self, "name_index", "Field name", target_types="Utf8")
        yield CPIndex(self, "descriptor_index", "Field descriptor", target_types="Utf8",
                target_text_handler=parse_field_descriptor)
        yield UInt16(self, "attributes_count", "Number of field attributes")
        if self["attributes_count"].value > 0:
            yield FieldArray(self, "attributes", AttributeInfo,
                    self["attributes_count"].value)


###############################################################################
# method_info {
#        u2 access_flags;
#        u2 name_index;
#        u2 descriptor_index;
#        u2 attributes_count;
#        attribute_info attributes[attributes_count];
# }
class MethodInfo(FieldSet):
    def createFields(self):
        # Access flags (16 bits)
        yield NullBits(self, "reserved[]", 4)
        yield Bit(self, "strict")
        yield Bit(self, "abstract")
        yield NullBits(self, "reserved[]", 1)
        yield Bit(self, "native")
        yield NullBits(self, "reserved[]", 2)
        yield Bit(self, "synchronized")
        yield Bit(self, "final")
        yield Bit(self, "static")
        yield Bit(self, "protected")
        yield Bit(self, "private")
        yield Bit(self, "public")

        yield CPIndex(self, "name_index", "Method name", target_types="Utf8")
        yield CPIndex(self, "descriptor_index", "Method descriptor",
                target_types="Utf8",
                target_text_handler=parse_method_descriptor)
        yield UInt16(self, "attributes_count", "Number of method attributes")
        if self["attributes_count"].value > 0:
            yield FieldArray(self, "attributes", AttributeInfo,
                    self["attributes_count"].value)


###############################################################################
# attribute_info {
#        u2 attribute_name_index;
#        u4 attribute_length;
#        u1 info[attribute_length];
# }
# [...]
class AttributeInfo(FieldSet):
    def __init__(self, *args):
        FieldSet.__init__(self, *args)
        self._size = (self["attribute_length"].value + 6) * 8

    def createFields(self):
        yield CPIndex(self, "attribute_name_index", "Attribute name", target_types="Utf8")
        yield UInt32(self, "attribute_length", "Length of the attribute")
        attr_name = str(self["attribute_name_index"].get_cp_entry())

        # ConstantValue_attribute {
        #   u2 attribute_name_index;
        #   u4 attribute_length;
        #   u2 constantvalue_index;
        # }
        if attr_name == "ConstantValue":
            if self["attribute_length"].value != 2:
                    raise ParserError("Java: Invalid attribute %s length (%s)" \
                        % (self.path, self["attribute_length"].value))
            yield CPIndex(self, "constantvalue_index",
                    target_types=("Long","Float","Double","Integer","String"))

        # Code_attribute {
        #   u2 attribute_name_index;
        #   u4 attribute_length;
        #   u2 max_stack;
        #   u2 max_locals;
        #   u4 code_length;
        #   u1 code[code_length];
        #   u2 exception_table_length;
        #   {   u2 start_pc;
        #       u2 end_pc;
        #       u2  handler_pc;
        #       u2  catch_type;
        #   } exception_table[exception_table_length];
        #   u2 attributes_count;
        #   attribute_info attributes[attributes_count];
        # }
        elif attr_name == "Code":
            yield UInt16(self, "max_stack")
            yield UInt16(self, "max_locals")
            yield UInt32(self, "code_length")
            if self["code_length"].value > 0:
                yield RawBytes(self, "code", self["code_length"].value)
            yield UInt16(self, "exception_table_length")
            if self["exception_table_length"].value > 0:
                yield FieldArray(self, "exception_table", ExceptionTableEntry,
                        self["exception_table_length"].value)
            yield UInt16(self, "attributes_count")
            if self["attributes_count"].value > 0:
                yield FieldArray(self, "attributes", AttributeInfo,
                        self["attributes_count"].value)

        # Exceptions_attribute {
        #   u2 attribute_name_index;
        #   u4 attribute_length;
        #   u2 number_of_exceptions;
        #   u2 exception_index_table[number_of_exceptions];
        # }
        elif (attr_name == "Exceptions"):
            yield UInt16(self, "number_of_exceptions")
            yield FieldArray(self, "exception_index_table", CPIndex,
                    self["number_of_exceptions"].value, target_types="Class")
            assert self["attribute_length"].value == \
                2 + self["number_of_exceptions"].value * 2

        # InnerClasses_attribute {
        #   u2 attribute_name_index;
        #   u4 attribute_length;
        #   u2 number_of_classes;
        #   {   u2 inner_class_info_index;
        #       u2 outer_class_info_index;
        #       u2 inner_name_index;
        #       u2 inner_class_access_flags;
        #   } classes[number_of_classes];
        # }
        elif (attr_name == "InnerClasses"):
            yield UInt16(self, "number_of_classes")
            if self["number_of_classes"].value > 0:
                yield FieldArray(self, "classes", InnerClassesEntry,
                       self["number_of_classes"].value)
            assert self["attribute_length"].value == \
                2 + self["number_of_classes"].value * 8

        # Synthetic_attribute {
        #   u2 attribute_name_index;
        #   u4 attribute_length;
        # }
        elif (attr_name == "Synthetic"):
            assert self["attribute_length"].value == 0

        # SourceFile_attribute {
        #   u2 attribute_name_index;
        #   u4 attribute_length;
        #   u2 sourcefile_index;
        # }
        elif (attr_name == "SourceFile"):
            assert self["attribute_length"].value == 2
            yield CPIndex(self, "sourcefile_index", target_types="Utf8")

        # LineNumberTable_attribute {
        #   u2 attribute_name_index;
        #   u4 attribute_length;
        #   u2 line_number_table_length;
        #   {   u2 start_pc;
        #       u2 line_number;
        #   } line_number_table[line_number_table_length];
        # }
        elif (attr_name == "LineNumberTable"):
            yield UInt16(self, "line_number_table_length")
            if self["line_number_table_length"].value > 0:
                yield FieldArray(self, "line_number_table",
                        LineNumberTableEntry,
                        self["line_number_table_length"].value)
            assert self["attribute_length"].value == \
                    2 + self["line_number_table_length"].value * 4

        # LocalVariableTable_attribute {
        #   u2 attribute_name_index;
        #   u4 attribute_length;
        #   u2 local_variable_table_length;
        #   {   u2 start_pc;
        #       u2 length;
        #       u2 name_index;
        #       u2 descriptor_index;
        #       u2 index;
        #   } local_variable_table[local_variable_table_length];
        # }
        elif (attr_name == "LocalVariableTable"):
            yield UInt16(self, "local_variable_table_length")
            if self["local_variable_table_length"].value > 0:
                yield FieldArray(self, "local_variable_table",
                        LocalVariableTableEntry,
                        self["local_variable_table_length"].value)
            assert self["attribute_length"].value == \
                    2 + self["local_variable_table_length"].value * 10

        # Deprecated_attribute {
        #   u2 attribute_name_index;
        #   u4 attribute_length;
        # }
        elif (attr_name == "Deprecated"):
            assert self["attribute_length"].value == 0

        # Unkown attribute type.  They are allowed by the JVM specs, but we
        # can't say much about them...
        elif self["attribute_length"].value > 0:
            yield RawBytes(self, "info", self["attribute_length"].value)

class ExceptionTableEntry(FieldSet):
    static_size = 48 + CPIndex.static_size

    def createFields(self):
        yield textHandler(UInt16(self, "start_pc"), hexadecimal)
        yield textHandler(UInt16(self, "end_pc"), hexadecimal)
        yield textHandler(UInt16(self, "handler_pc"), hexadecimal)
        yield CPIndex(self, "catch_type", target_types="Class")

class InnerClassesEntry(StaticFieldSet):
    format = (
        (CPIndex, "inner_class_info_index",
                {"target_types": "Class", "allow_zero": True}),
        (CPIndex, "outer_class_info_index",
                {"target_types": "Class", "allow_zero": True}),
        (CPIndex, "inner_name_index",
                {"target_types": "Utf8", "allow_zero": True}),

        # Inner class access flags (16 bits)
        (NullBits, "reserved[]", 5),
        (Bit, "abstract"),
        (Bit, "interface"),
        (NullBits, "reserved[]", 3),
        (Bit, "super"),
        (Bit, "final"),
        (Bit, "static"),
        (Bit, "protected"),
        (Bit, "private"),
        (Bit, "public"),
    )

class LineNumberTableEntry(StaticFieldSet):
    format = (
        (UInt16, "start_pc"),
        (UInt16, "line_number")
    )

class LocalVariableTableEntry(StaticFieldSet):
    format = (
        (UInt16, "start_pc"),
        (UInt16, "length"),
        (CPIndex, "name_index", {"target_types": "Utf8"}),
        (CPIndex, "descriptor_index", {"target_types": "Utf8",
                "target_text_handler": parse_field_descriptor}),
        (UInt16, "index")
    )


###############################################################################
# ClassFile {
#        u4 magic;
#        u2 minor_version;
#        u2 major_version;
#        u2 constant_pool_count;
#        cp_info constant_pool[constant_pool_count-1];
#        u2 access_flags;
#        u2 this_class;
#        u2 super_class;
#        u2 interfaces_count;
#        u2 interfaces[interfaces_count];
#        u2 fields_count;
#        field_info fields[fields_count];
#        u2 methods_count;
#        method_info methods[methods_count];
#        u2 attributes_count;
#        attribute_info attributes[attributes_count];
# }
class JavaCompiledClassFile(Parser):
    """
    Root of the .class parser.
    """

    endian = BIG_ENDIAN

    PARSER_TAGS = {
        "id": "java_class",
        "category": "program",
        "file_ext": ("class",),
        "mime": (u"application/java-vm",),
        "min_size": (32 + 3*16),
        "description": "Compiled Java class"
    }

    MAGIC = 0xCAFEBABE
    KNOWN_VERSIONS = {
        "45.3": "JDK 1.1",
        "46.0": "JDK 1.2",
        "47.0": "JDK 1.3",
        "48.0": "JDK 1.4",
        "49.0": "JDK 1.5"
    }

    # Constants go here since they will probably depend on the detected format
    # version at some point.  Though, if they happen to be really backward
    # compatible, they may become module globals.
    CONSTANT_TYPES = {
         1: "Utf8",
         3: "Integer",
         4: "Float",
         5: "Long",
         6: "Double",
         7: "Class",
         8: "String",
         9: "Fieldref",
        10: "Methodref",
        11: "InterfaceMethodref",
        12: "NameAndType"
    }

    def validate(self):
        if self["magic"].value != self.MAGIC:
            return "Wrong magic signature!"
        version = "%d.%d" % (self["major_version"].value, self["minor_version"].value)
        if version not in self.KNOWN_VERSIONS:
            return "Unknown version (%s)" % version
        return True

    def createDescription(self):
        version = "%d.%d" % (self["major_version"].value, self["minor_version"].value)
        if version in self.KNOWN_VERSIONS:
            return "Compiled Java class, %s" % self.KNOWN_VERSIONS[version]
        else:
            return "Compiled Java class, version %s" % version

    def createFields(self):
        yield textHandler(UInt32(self, "magic", "Java compiled class signature"),
            hexadecimal)
        yield UInt16(self, "minor_version", "Class format minor version")
        yield UInt16(self, "major_version", "Class format major version")
        yield UInt16(self, "constant_pool_count", "Size of the constant pool")
        if self["constant_pool_count"].value > 1:
            #yield FieldArray(self, "constant_pool", CPInfo,
            #        (self["constant_pool_count"].value - 1), first_index=1)
            # Mmmh... can't use FieldArray actually, because ConstantPool
            # requires some specific hacks (skipping some indexes after Long
            # and Double entries).
            yield ConstantPool(self, "constant_pool",
                    (self["constant_pool_count"].value))

        # Inner class access flags (16 bits)
        yield NullBits(self, "reserved[]", 5)
        yield Bit(self, "abstract")
        yield Bit(self, "interface")
        yield NullBits(self, "reserved[]", 3)
        yield Bit(self, "super")
        yield Bit(self, "final")
        yield Bit(self, "static")
        yield Bit(self, "protected")
        yield Bit(self, "private")
        yield Bit(self, "public")

        yield CPIndex(self, "this_class", "Class name", target_types="Class")
        yield CPIndex(self, "super_class", "Super class name", target_types="Class")
        yield UInt16(self, "interfaces_count", "Number of implemented interfaces")
        if self["interfaces_count"].value > 0:
            yield FieldArray(self, "interfaces", CPIndex,
                    self["interfaces_count"].value, target_types="Class")
        yield UInt16(self, "fields_count", "Number of fields")
        if self["fields_count"].value > 0:
            yield FieldArray(self, "fields", FieldInfo,
                    self["fields_count"].value)
        yield UInt16(self, "methods_count", "Number of methods")
        if self["methods_count"].value > 0:
            yield FieldArray(self, "methods", MethodInfo,
                    self["methods_count"].value)
        yield UInt16(self, "attributes_count", "Number of attributes")
        if self["attributes_count"].value > 0:
            yield FieldArray(self, "attributes", AttributeInfo,
                    self["attributes_count"].value)

# vim: set expandtab tabstop=4 shiftwidth=4 autoindent smartindent:
