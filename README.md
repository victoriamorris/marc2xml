# marc2xml
Tools for converting MARC .lex records to MARC XML

## Requirements

py2exe is required for installation.

If XSLT is to be used, the XSLT processor saxon.jar must be present in the same folder as the XSLT file.

## Installation

From GitHub:

    git clone https://github.com/victoriamorris/marc2xml
    cd marc2xml

To install as a Python package:

    python setup.py install
    
To create stand-alone executable (.exe) files for individual scripts:

    python setup.py py2exe
    
Executable files will be created in the folder marc2xml\dist, and should be copied to an executable path.

## Usage

### Running scripts

The following script can be run from anywhere, once the package is installed:

#### marc2xml

This utility converts a file of MARC .lex records to MARC XML.
    
    Usage: marc2xml -i INPUT_PATH -o OUTPUT_PATH [OPTIONS]
    
    Convert MARC .lex file specified by INPUT_PATH to MARC XML file at OUTPUT_PATH.

    Options:
      -x XSLT       Apply XSLT during transformation.
      --debug       Debug mode.
      --help        Show help message and exit.

### Notes
 
MARC input files must have .lex file extensions.

If -x is specified, the XSLT processor saxon.jar must be present in the same folder as the XSLT.

If XSLT is used, the output document will be a concatenation of the result of transforming individual MARC records.
There will be no root/wrapper element. The output document must therefore be edited before it can be used as valid XML.
