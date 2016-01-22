#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import configparser
import os
import apsw
from multiprocess import Pool, Manager
from py2neo import Graph, Node, authenticate
from device.olt import Zte
from funcy import lmap, merge, partial, walk, lmapcat
from funcy import re_test

config = configparser.ConfigParser()
config.read('config.ini')
neo4j_username = config.get('neo4j', 'username')
neo4j_password = config.get('neo4j', 'password')

olts_file, log_file, result_file = (
    'olts.txt', 'result/olt_log.txt', 'result/olt_info.txt')

authenticate('61.155.48.36:7474', neo4j_username, neo4j_password)
graph = Graph("http://61.155.48.36:7474/db/data")


def clear_log():
    for f in [log_file, result_file]:
        if os.path.exists(f):
            os.remove(f)
        os.mknod(f)


nodes = graph.cypher.execute(
    'match (n:Olt) where n.company="zte" return n.ip')
olts = [x[0] for x in nodes]


def saveOnus_f(ip):
    mark, rslt = Zte.get_onus(ip)[:-1]
    if mark == 'success' and rslt:
        _ff = lambda x: walk(partial(merge, (ip, x[0])), x[1])
        rslt1 = lmapcat(_ff, rslt)
        with open(result_file, 'a') as frslt:
            for record in rslt1:
                ip, port, onuid, loid = record
                frslt.write("{ip},{port},{onuid},{loid}\n"
                            .format(ip=ip, port=port, onuid=onuid, loid=loid))
    with open(log_file, 'a') as flog:
        flog.write("{ip}:{mark}\n".format(ip=ip, mark=mark))


def in_to_DB():
    conn = apsw.Connection('db/onu.db')
    cursor = conn.cursor()
    records = [x.strip().split(',') for x in open(result_file)]
    cmd = "insert into onu values(?,?,?,?)"
    cursor.executemany(cmd, records)

def del_onu():
    records = (x.strip().split(',') for x in open('e8c_diff.csv'))
    for ip, port, onuid, loid in records:
        child = Zte.telnet(ip)
        rslt = Zte.do_some(child, 'show run {port}'.format(port=port))
        if re_test(r'onu\s{0}\stype\sE8C[PG]24\sloid\s{1}'.format(onuid, loid),
                   rslt):
            child.sendline('conf t')
            child.expect('#')
            child.sendline(port)
            child.expect('#')
            child.sendline('no onu {onuid}'.format(onuid=onuid))
            child.expect('#')
        Zte.close(child)



def main():
    #  clear_log()
    #  pool = Pool(256)
    #  list(pool.map(saveOnus_f, olts))
    #  pool.close()
    #  pool.join()
    pass

if __name__ == "__main__":
    main()
