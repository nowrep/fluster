#!/usr/bin/env python3

# fluxion - testing framework for codecs
# Copyright (C) 2020, Fluendo, S.A.
#  Author: Pablo Marcos Oltra <pmarcos@fluendo.com>, Fluendo, S.A.
#  Author: Andoni Morales Alastruey <amorales@fluendo.com>, Fluendo, S.A.
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Library General Public
# License as published by the Free Software Foundation; either
# version 2 of the License, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Library General Public License for more details.
#
# You should have received a copy of the GNU Library General Public
# License along with this library; if not, write to the
# Free Software Foundation, Inc., 59 Temple Place - Suite 330,
# Boston, MA 02111-1307, USA.

import argparse
from html.parser import HTMLParser
import os
import sys
import urllib.request

# pylint: disable=wrong-import-position
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from fluxion import utils
from fluxion.codec import Codec
from fluxion.test_suite import TestSuite, TestVector
# pylint: enable=wrong-import-position

BASE_URL = "https://www.itu.int/"
H265_URL = BASE_URL + "wftp3/av-arch/jctvc-site/bitstream_exchange/draft_conformance/"
H264_URL = BASE_URL + "wftp3/av-arch/jvt-site/draft_conformance/"
BITSTREAM_EXTS = ('.bin', '.bit', '.264', '.h264',
                  '.jvc', '.jsv', '.jvt', '.avc', '.26l')
MD5_EXTS = ('yuv.md5', '.md5', 'md5.txt')
MD5_EXCLUDES = ('__MACOSX', '.bin.md5', 'bit.md5')
RAW_EXTS = ('.yuv', '.qcif')


class HREFParser(HTMLParser):
    '''Custom parser to find href links'''
    links = []

    def error(self, message):
        print(message)

    def handle_starttag(self, tag, attrs):
        # Only parse the 'anchor' tag.
        if tag == "a":
            # Check the list of defined attributes.
            for name, value in attrs:
                # If href is defined, print it.
                if name == "href":
                    self.links.append(BASE_URL + value)


class JCTVTGenerator:
    '''Generates a test suite from the conformance bitstreams'''

    def __init__(self, name: str, suite_name: str, codec: Codec, description: str, site: str):
        self.name = name
        self.suite_name = suite_name
        self.codec = codec
        self.description = description
        self.site = site

    def generate(self, download):
        '''Generates the test suite and saves it to a file'''
        output_filepath = os.path.join(self.suite_name + '.json')
        test_suite = TestSuite(output_filepath,
                               self.suite_name, self.codec, self.description, list())

        hparser = HREFParser()
        print(f"Download list of bitstreams from {self.site + self.name}")
        with urllib.request.urlopen(self.site + self.name) as resp:
            data = str(resp.read())
            hparser.feed(data)

        for url in hparser.links[1:]:
            # The first item in the AVCv1 list is a readme file
            if '00readme_H' in url:
                continue
            file_url = url.split('/')[-1]
            name = file_url.split('.')[0]
            file_input = "{name}.bin".format(name=name)
            test_vector = TestVector(name, url, "", file_input, "")
            test_suite.test_vectors.append(test_vector)

        if download:
            test_suite.download('resources', verify=False)

        for test_vector in test_suite.test_vectors:
            dest_dir = os.path.join(
                'resources', test_suite.name, test_vector.name)
            dest_path = os.path.join(
                dest_dir, test_vector.source.split('/')[-1])
            test_vector.input = self._find_by_ext(dest_dir, BITSTREAM_EXTS)
            if not test_vector.input:
                raise Exception(f"Bitstream file not found in {dest_dir}")
            test_vector.source_hash = utils.file_checksum(dest_path)
            if self.codec == Codec.H265:
                self._fill_checksum_h265(test_vector, dest_dir)
            elif self.codec == Codec.H264:
                self._fill_checksum_h264(test_vector, dest_dir)

        test_suite.to_json_file(output_filepath)
        print("Generate new test suite: " + test_suite.name + '.json')

    def _fill_checksum_h264(self, test_vector, dest_dir):
        raw_file = self._find_by_ext(dest_dir, RAW_EXTS)
        if raw_file is None:
            raise Exception(f"RAW file not found in {dest_dir}")
        test_vector.result = utils.file_checksum(raw_file)

    def _fill_checksum_h265(self, test_vector, dest_dir):
        checksum_file = self._find_by_ext(dest_dir, MD5_EXTS, MD5_EXCLUDES)
        if checksum_file is None:
            raise Exception("MD5 not found")
        with open(checksum_file, 'r') as checksum_file:
            # The md5 is in several formats
            # Example 1
            # 158312a1a35ef4b20cb4aeee48549c03 *WP_A_Toshiba_3.bit
            # Example 2
            # MD5 (rec.yuv) = e5c4c20a8871aa446a344efb1755bcf9
            # Example 3
            # # MD5 checksums generated by MD5summer (http://www.md5summer.org)
            # # Generated 6/14/2013 4:22:11 PM
            # 29799285628de148502da666a7fc2df5 *DBLK_F_VIXS_1.bit
            while True:
                line = checksum_file.readline()
                if line.startswith(('#', '\n')):
                    continue
                if '=' in line:
                    test_vector.result = line.split('=')[-1].strip().upper()
                else:
                    test_vector.result = line.split(
                        ' ')[0].split('\n')[0].upper()
                break

    def _find_by_ext(self, dest_dir, exts, excludes=None):
        excludes = excludes or []
        for subdir, _, files in os.walk(dest_dir):
            for filename in files:
                filepath = subdir + os.sep + filename
                excluded = False
                for excl in excludes:
                    if excl in filepath:
                        excluded = True
                        break
                if not excluded and filepath.endswith(exts):
                    return filepath
        return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--skip-download', help='skip extracting tarball',
                        action='store_true', default=False)
    args = parser.parse_args()
    generator = JCTVTGenerator("HEVC_v1", "JCT-VC-HEVC_V1", Codec.H265,
                               "JCT-VC HEVC version 1", H265_URL)
    generator.generate(not args.skip_download)
    generator = JCTVTGenerator("AVCv1", "JVT-AVC_V1", Codec.H264,
                               "JVT AVC version 1", H264_URL)
    generator.generate(not args.skip_download)