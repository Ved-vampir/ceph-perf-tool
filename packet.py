#!/usr/bin/env python
""" Protocol class """

import binascii
import logging

# packet has format:
# begin_data_prefixSIZE\n\nDATAend_data_postfix
# packet part has format:
# SIZE\n\rDATA


class PacketException(Exception):
    """ Exceptions from Packet"""
    pass


class Packet(object):
    """ Class proceed packet by protocol"""
    # is_begin
    # is_end
    # crc
    # data
    # data_len
    # prefix
    # postfix
    #logger_name

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
            local_size_s, _, part = part.partition("\n\r")
            local_size = int(local_size_s)

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
                data_len_s, _, part = part.partition("\n\r")
                self.data_len = int(data_len_s)
                # get crc
                crc_s, _, part = part.partition("\n\r")
                self.crc = int(crc_s)

            # bad size?
            if local_size != self.data_len:
                raise PacketException("Part size error")

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
                    raise PacketException("Total size error")
                if binascii.crc32(self.data) != self.crc:
                    raise PacketException("CRC error")
                return self.data
            else:
                return None


        except PacketException as e:
            # if something wrong - skip packet
            logger = logging.getLogger(__name__)
            logger.warning("Packet skipped: %s", e)
            self.is_begin = False
            self.is_end = False
            return None
        except:
            # if something at all wrong - skip packet
            logger = logging.getLogger(__name__)
            logger.warning("Packet skipped: something is wrong")
            self.is_begin = False
            self.is_end = False
            return None
