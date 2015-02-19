#!/usr/bin/env python
""" Protocol class """

import binascii




class Packet(object):
    """ Class proceed packet by protocol"""
    # is_begin
    # is_end
    # crc
    # data
    # data_len
    # prefix
    # postfix

    def __init__(self):
        # preinit
        self.is_begin = False
        self.is_end = False
        self.crc = None
        self.data = ""
        self.data_len = None
        self.prefix = "begin_data_prefix"
        self.postfix = "end_data_postfix"


    def new_packet(self, part):
        """ New packet adding """
        # proceed packet
        try:
            # get size
            tmp = part.partition("\n\r")
            local_size = int(tmp[0])
            part = tmp[2]

            # find prefix
            begin = part.find(self.prefix)
            if begin != -1:
                # divide data if something before begin and prefix
                from_i = begin + len(self.prefix)
                part = part[from_i:]
                # reset flags
                self.is_begin = True
                self.is_end = False
                self.data = ""
                # get size
                tmp = part.partition("\n\r")
                self.data_len = int(tmp[0])
                part = tmp[2]                
                # get crc
                tmp = part.partition("\n\r")
                self.crc = int(tmp[0])
                part = tmp[2]

            # bad size?
            if local_size != self.data_len:
                raise Exception("Part size error")

            # find postfix
            end = part.find(self.postfix)
            if end != -1:
                # divide postfix
                part = part[:end]
                self.is_end = True

            self.data += part
            # check if it is end
            if self.is_end:
                if self.data_len != len(self.data):
                    raise Exception("Total size error")
                if binascii.crc32(self.data) != self.crc:
                    raise Exception("CRC error")
                return self.data
            else:
                return None


        except Exception:
            # if something wrong - skip packet
            self.is_begin = False
            self.is_end = False
            return None
        else:
            # if something wrong - skip packet
            self.is_begin = False
            self.is_end = False
            return None

