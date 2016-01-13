#!/usr/bin/env python
# -*- coding: utf-8 -*-
import configparser
import os
import re
from multiprocess import Pool, Manager
from py2neo import Graph, Node
from py2neo import authenticate
from funcy import lmap
from device.switch import S85


config = configparser.ConfigParser()
config.read('config.ini')
neo4j_username = config.get('neo4j', 'username')
neo4j_password = config.get('neo4j', 'password')

sw_file, log_file, result_file = ('sw.txt', 'result/sw_log.txt',
                                  'result/sw_info.txt')

authenticate('61.155.48.36:7474', neo4j_username, neo4j_password)
graph = Graph("http://61.155.48.36:7474/db/data")


def clear_log():
    for f in [log_file, result_file]:
        if os.path.exists(f):
            os.remove(f)
        os.mknod(f)


def create_sw_node(r):
    area, ip, hostname, model = r.split(',')
    node = Node('Switch', area=area, ip=ip,
                hostname=hostname, model=model)
    return node


def import_sw(file):
    switchs = (x.strip() for x in open(file))
    lmap(lambda x: graph.create(create_sw_node(x)), switchs)


def main():
    pass
    #  interface_check_m()

if __name__ == '__main__':
    main()
