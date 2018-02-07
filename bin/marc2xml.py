#!/usr/bin/env python
# -*- coding: utf8 -*-

"""A tool for converting files of MARC (.lex) records to MARC XML."""

import marc2xml
import sys

__author__ = 'Victoria Morris'
__license__ = 'MIT License'
__version__ = '1.0.0'
__status__ = '4 - Beta Development'

marc2xml.main(sys.argv[1:])
