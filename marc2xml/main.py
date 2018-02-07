#!/usr/bin/env python
# -*- coding: utf8 -*-

"""A tool for converting files of MARC (.lex) records to MARC XML."""

# Import required modules
# These should all be contained in the standard library
import datetime
import getopt
import html
import locale
import os
import re
import subprocess
import sys
import unicodedata

# Set locale to assist with sorting
locale.setlocale(locale.LC_ALL, '')

# ====================
#      Constants
# ====================

LEADER_LENGTH, DIRECTORY_ENTRY_LENGTH = 24, 12
SUBFIELD_INDICATOR, END_OF_FIELD, END_OF_RECORD = chr(0x1F), chr(0x1E), chr(0x1D)
ALEPH_CONTROL_FIELDS = ['DB ', 'SYS']

XML_START = '<?xml version="1.0" encoding="UTF-8"?>\n' \
            '<marc:collection xmlns:marc="http://www.loc.gov/MARC21/slim" ' \
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" ' \
            'xsi:schemaLocation="http://www.loc.gov/MARC21/slim http://www.loc.gov/standards/marcxml/schema/MARC21slim.xsd">\n'

XML_END = '</marc:collection>\n'

# ====================
#      Exceptions
# ====================


class RecordLengthError(Exception):
    def __str__(self): return 'Invalid record length in first 5 bytes of record'


class LeaderError(Exception):
    def __str__(self): return 'Error reading record leader'


class DirectoryError(Exception):
    def __str__(self): return 'Record directory is invalid'


class FieldsError(Exception):
    def __str__(self): return 'Error locating fields in record'


class BaseAddressLengthError(Exception):
    def __str__(self): return 'Base address exceeds size of record'


class BaseAddressError(Exception):
    def __str__(self): return 'Error locating base address of record'


# ====================
#       Classes
# ====================


class FilePath:
    def __init__(self, path=None, role='input', ext='.lex'):
        self.path = None
        self.role = role
        self.folder, self.filename, self.ext = '', '', ext
        if path: self.set_path(path)

    def set_path(self, path):
        self.path = path
        self.folder, self.filename, self.ext = check_file_location(self.path, self.role, self.ext, 'output' not in self.role)

class MARCReader(object):

    def __init__(self, marc_target):
        super(MARCReader, self).__init__()
        if hasattr(marc_target, 'read') and callable(marc_target.read):
            self.file_handle = marc_target

    def __iter__(self):
        return self

    def close(self):
        if self.file_handle:
            self.file_handle.close()
            self.file_handle = None

    def __next__(self):
        first5 = self.file_handle.read(5)
        if not first5: raise StopIteration
        if len(first5) < 5: raise RecordLengthError
        return Record(first5 + self.file_handle.read(int(first5) - 5))


class Record(object):
    
    def __init__(self, data='', leader=' ' * LEADER_LENGTH):
        self.leader = '{}22{}4500'.format(leader[0:10], leader[12:20])
        self.fields = list()
        self.pos = 0
        if len(data) > 0: self.decode_marc(data)

    def __getitem__(self, tag):
        fields = self.get_fields(tag)
        if len(fields) > 0: return fields[0]
        return None

    def __contains__(self, tag):
        fields = self.get_fields(tag)
        return len(fields) > 0

    def __iter__(self):
        self.__pos = 0
        return self

    def __next__(self):
        if self.__pos >= len(self.fields): raise StopIteration
        self.__pos += 1
        return self.fields[self.__pos - 1]

    def add_field(self, *fields):
        self.fields.extend(fields)

    def get_fields(self, *args):
        if len(args) == 0: return self.fields
        return [f for f in self.fields if
                (f.tag in args or (f.tag == '880' and '6' in f and str(f['6'])[:3] in args))]

    def decode_marc(self, marc):
        # Extract record leader
        try:
            self.leader = marc[0:LEADER_LENGTH].decode('ascii')
        except:
            print('Record has problem with Leader and cannot be processed')
        if len(self.leader) != LEADER_LENGTH: raise LeaderError

        # Extract the byte offset where the record data starts
        base_address = int(marc[12:17])
        if base_address <= 0: raise BaseAddressError
        if base_address >= len(marc): raise BaseAddressLengthError

        # Extract directory
        # base_address-1 is used since the directory ends with an END_OF_FIELD byte
        directory = marc[LEADER_LENGTH:base_address - 1].decode('ascii')

        # Determine the number of fields in record
        if len(directory) % DIRECTORY_ENTRY_LENGTH != 0:
            raise DirectoryError
        field_total = len(directory) / DIRECTORY_ENTRY_LENGTH

        # Add fields to record using directory offsets
        field_count = 0
        while field_count < field_total:
            entry_start = field_count * DIRECTORY_ENTRY_LENGTH
            entry_end = entry_start + DIRECTORY_ENTRY_LENGTH
            entry = directory[entry_start:entry_end]
            entry_tag = entry[0:3]
            entry_length = int(entry[3:7])
            entry_offset = int(entry[7:12])
            entry_data = marc[base_address + entry_offset:base_address + entry_offset + entry_length - 1]

            # Check if tag is a control field
            if str(entry_tag) < '010' and entry_tag.isdigit():
                field = Field(tag=entry_tag, data=entry_data.decode('utf-8'))
            elif str(entry_tag) in ALEPH_CONTROL_FIELDS:
                field = Field(tag=entry_tag, data=entry_data.decode('utf-8'))

            else:
                subfields = list()
                subs = entry_data.split(SUBFIELD_INDICATOR.encode('ascii'))
                # Missing indicators are recorded as blank spaces.
                # Extra indicators are ignored.

                subs[0] = subs[0].decode('ascii') + '  '
                first_indicator, second_indicator = subs[0][0], subs[0][1]

                for subfield in subs[1:]:
                    if len(subfield) == 0: continue
                    try:
                        code, data = subfield[0:1].decode('ascii'), subfield[1:].decode('utf-8', 'strict')
                    except:
                        print('Error in subfield code')
                    else:
                        subfields.append(code)
                        subfields.append(data)
                field = Field(
                    tag=entry_tag,
                    indicators=[first_indicator, second_indicator],
                    subfields=subfields,
                )
            self.add_field(field)
            field_count += 1

        if field_count == 0: raise FieldsError

    def as_marc(self):
        fields, directory = b'', b''
        offset = 0

        for field in self.fields:
            field_data = field.as_marc()
            fields += field_data
            if field.tag.isdigit(): directory += ('%03d' % int(field.tag)).encode('utf-8')
            else: directory += ('%03s' % field.tag).encode('utf-8')
            directory += ('%04d%05d' % (len(field_data), offset)).encode('utf-8')
            offset += len(field_data)

        directory += END_OF_FIELD.encode('utf-8')
        fields += END_OF_RECORD.encode('utf-8')
        base_address = LEADER_LENGTH + len(directory)
        record_length = base_address + len(fields)
        strleader = '%05d%s%05d%s' % (record_length, self.leader[5:12], base_address, self.leader[17:])
        leader = strleader.encode('utf-8')
        return leader + directory + fields


    def as_xml(self):
        xml = '\t<marc:record>\n'
        xml += '\t\t<marc:leader>{}</marc:leader>\n'.format(str(self.leader))
        for field in self.fields:
            xml += field.as_xml()
        return xml + '\t</marc:record>\n'


class Field(object):

    def __init__(self, tag, indicators=None, subfields=None, data=''):
        if indicators is None: indicators = []
        if subfields is None: subfields = []
        indicators = [str(x) for x in indicators]

        # Normalize tag to three digits
        self.tag = '%03s' % tag

        # Check if tag is a control field
        if self.tag < '010' and self.tag.isdigit():
            self.data = str(data)
        elif self.tag in ALEPH_CONTROL_FIELDS:
            self.data = str(data)
        else:
            self.indicator1, self.indicator2 = self.indicators = indicators
            self.subfields = subfields

    def __iter__(self):
        self.__pos = 0
        return self

    def __getitem__(self, subfield):
        subfields = self.get_subfields(subfield)
        if len(subfields) > 0: return subfields[0]
        return None

    def __contains__(self, subfield):
        subfields = self.get_subfields(subfield)
        return len(subfields) > 0

    def __next__(self):
        if not hasattr(self, 'subfields'):
            raise StopIteration
        while self.__pos < len(self.subfields):
            subfield = (self.subfields[self.__pos], self.subfields[self.__pos + 1])
            self.__pos += 2
            return subfield
        raise StopIteration

    def get_subfields(self, *codes):
        """Accepts one or more subfield codes and returns a list of subfield values"""
        values = []
        for subfield in self:
            if len(codes) == 0 or subfield[0] in codes:
                values.append(str(subfield[1]))
        return values

    def add_subfield(self, code, value):
        self.subfields.append(code)
        self.subfields.append(value)

    def is_control_field(self):
        if self.tag < '010' and self.tag.isdigit(): return True
        if self.tag in ALEPH_CONTROL_FIELDS: return True
        return False

    def as_marc(self):
        if self.is_control_field():
            return (self.data + END_OF_FIELD).encode('utf-8')
        marc = self.indicator1 + self.indicator2
        for subfield in self:
            marc += SUBFIELD_INDICATOR + subfield[0] + subfield[1]
        return (marc + END_OF_FIELD).encode('utf-8')

    def as_xml(self):
        if self.is_control_field():
            return '\t\t<marc:controlfield tag="{}">{}</marc:controlfield>\n'.format(self.tag, clean(self.data))
        xml = '\t\t<marc:datafield tag="{}" ind1="{}" ind2="{}">\n'.format(self.tag, self.indicator1, self.indicator2)
        for subfield in self:
            xml += '\t\t\t<marc:subfield code="{}">{}</marc:subfield>\n'.format(subfield[0], clean(subfield[1]))
        return xml + '\t\t</marc:datafield>\n'
       

# ====================
#      Functions
# ====================

def unescape(text):
    def fixup(m):
        text = m.group(0)
        if text[:2] == "&#":
            # character reference
            try:
                if text[:3] == "&#x":
                    return chr(int(text[3:-1], 16))
                else:
                    return chr(int(text[2:-1]))
            except ValueError:
                pass
        else:
            # named entity
            try:
                text = chr(html.entities.name2codepoint[text[1:-1]])
            except KeyError:
                pass
        return text # leave as is
    return re.sub("&#?\w+;", fixup, text)


def clean(string):
    """Function to clean text and escape characters that would be invalid in HTML"""
    if string is None or not string: return ''
    string = html.unescape(string)
    string = unicodedata.normalize('NFC', string)
    string = unescape(string)
    string = html.escape(string)
    string = unicodedata.normalize('NFC', string)
    return string

def check_file_location(path, role='input', ext='.lex', exists=False):
    """Function to check whether a file exists and has the correct file extension"""
    folder, file, e = '', '', ''
    if path == '': exit_prompt('Error: Could not parse path to {} file'.format(role))
    try:
        file, e = os.path.splitext(os.path.basename(path))
        folder = os.path.dirname(path)
    except:
        exit_prompt('Error: Could not parse path to {} file'.format(role))
    if e != '' and e != ext:
        exit_prompt('Error: The {} file should have the extension {}'.format(role, ext))
    if exists and not os.path.isfile(os.path.join(folder, file + e)):
        exit_prompt('Error: The specified {} file cannot be found'.format(role))
    return folder, file, e


def exit_prompt(message=''):
    """Function to exit the program after prompting the use to press Enter"""
    if message != '': print(str(message))
    input('\nPress [Enter] to exit...')
    sys.exit()


def is_number(string):
    """Function to test whether a string is a float number"""
    try:
        float(string)
        return True
    except ValueError: return False


# ====================


def usage():
    """Function to print information about the script"""
    print('Correct syntax is:\n')
    print('marc2xml -i <ifile> -o <ofile> [OPTIONS]\n')
    print('    -i    INPUT_PATH - Path to input file (must be a MARC .lex file).')
    print('    -o    OUTPUT_PATH - Path to save output file (must be a .xml file).')
    print('\nOptions:')
    print('    -x <xfile>  Apply XSLT during transformation.')
    print('    --debug     Debug mode.')
    print('    --help      Display this help message and exit.')
    print('\nIf -x is specified, the XSLT processor saxon.jar must be present\nin the same folder as the XSLT.')
    print('Use quotation marks (") around arguments which contain spaces.')
    exit_prompt()

# ====================
#      Main code
# ====================


def main(argv=None):
    if argv is None: name = str(sys.argv[1])

    ifile, ofile, xfile = None, None, None
    debug, transform = False, False

    print('========================================')
    print('marc2xml')
    print('========================================')
    print('A tool for converting files of MARC (.lex) records to MARC XML.\n')

    try:
        opts, args = getopt.getopt(argv, 'i:o:x:', ['ifile=', 'ofile=', 'xfile=', 'debug', 'help'])
    except getopt.GetoptError as err:
        exit_prompt('Error: {}'.format(err))
    if opts is None or not opts: usage()
    for opt, arg in opts:
        if opt == '--help':
            usage()
        elif opt == '--debug':
            debug = True
        elif opt in ['-i', '--ifile']:
            ifile = FilePath(arg)
        elif opt in ['-o', '--ofile']:
            ofile = FilePath(arg, role='output', ext='.xml')
        elif opt in ['-x', '--xfile']:
            transform = True
            xfile = FilePath(arg, role='xslt', ext='.xsl')
        else: exit_prompt('Error: Option {} not recognised'.format(opt))

    if ifile is None:
        exit_prompt('Error: No input file has been specified')
    if ofile is None:
        exit_prompt('Error: No output file has been specified')


    # --------------------
    # Parameters seem OK => start program        
    # --------------------

    # Check for XSLT processor
    if transform and not (os.path.isfile(os.path.join(xfile.folder, 'saxon.jar'))):
            exit_prompt('Error: Cannot find the XSLT processor saxon.jar')

    # Display confirmation information about the transformation
    print('Input file: {}'.format(ifile.path))
    print('Output file: {}'.format(ofile.path))
    if transform:
        print('XSLT: {}'.format(xfile.path))
    if debug: print('Debug mode')

    # --------------------
    # Main transformation
    # --------------------

    print('\n\nStarting transformation ...')
    print('----------------------------------------')
    print(str(datetime.datetime.now()))

    # Delete error.log file if it already exists
    try: os.remove('error.log')
    except: pass

    # Construct command line instruction to be used for XSLT
    if transform:
        xslt_command = 'java -jar saxon.jar -s:"__temp.xml" -xsl:"{}" 1>>"{}" 2>>error.log'.format(xfile.path, ofile.path)

    # Open input file
    ifile = open(ifile.path, 'rb')

    # Write start of MARC XML if XSLT is not to be used
    if not transform:
        ofile = open(ofile.path, 'w', encoding='utf-8', errors='replace')
        ofile.write(XML_START)

    # Iterate over MARC records
    reader = MARCReader(ifile)
    i = 0
    for record in reader:
        i += 1
        print('{} records converted'.format(str(i)), end='\r')
        # Convert record to MARC XML
        x = record.as_xml()

        if transform:
            # If XSLT is to be used, save record to temporary file, then transform temporary file
            tfile = open('__temp.xml', 'w', encoding='utf-8', errors='replace')
            tfile.write(XML_START + x + XML_END)
            tfile.close()
            subprocess.call(xslt_command, shell=True)
        else:
            # If XSLT is not to be used, write MARC XML directly to output file
            ofile.write(x)

    # Write end of MARC XML if XSLT is not to be used
    if not transform:
        ofile.write(XML_END)
        ofile.close()

    # Tidy up
    ifile.close()
    try: os.remove('__temp.xml')
    except: pass

    print('\n\nTransformation complete')
    print('----------------------------------------')
    print(str(datetime.datetime.now()))    
    sys.exit()
    
if __name__ == '__main__': main(sys.argv[1:])
