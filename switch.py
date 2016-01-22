#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os, re, configparser
from multiprocess import Pool, Manager
from py2neo import Graph, Node, authenticate
from funcy import lmap, compose, partial
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
    node = Node('Switch', area=area, ip=ip, hostname=hostname, model=model)
    return node


def import_sw(file):
    switchs = (x.strip() for x in open(file))
    lmap(lambda x: graph.create(create_sw_node(x)), switchs)


def _model(funcs, device):
    no_model = lambda x: ('fail', None, x)
    ip, model = device
    model = model.replace('-', '_')
    return funcs.get(model, no_model)(ip)


def _add_groups(lock, record):
    mark, groups, ip = record
    statement = """match (s:Switch {ip:{ip}})
    merge (s)-[r:HAS]->(g:Group {name:{name}})
    on create set g.mode={mode},g.desc={desc},g.updated=timestamp()
    on match set g.mode={mode},g.desc={desc},g.updated=timestamp()"""

    with lock:
        if mark == 'success':
            tx = graph.cypher.begin()
            lmap(lambda x: tx.append(statement, ip=ip, **x), groups)
            tx.process()
            tx.commit()
        with open(log_file, 'a') as flog:
            flog.write('{ip}:{mark}\n'.format(ip=ip, mark=mark))


def add_groups():
    funcs=dict(S8508=S85.get_groups,S8505=S85.get_groups)
    get_groups=partial(_model,funcs)
    clear_log()
    nodes = graph.cypher.execute(
        "match(s:Switch) where s.model='S8508' return s.ip as ip,s.model as model limit 10")
    switchs = [(x['ip'],x['model']) for x in nodes]
    pool = Pool(4)
    lock = Manager().Lock()
    _ff = partial(_add_groups, lock)
    list(pool.map(compose(_ff, get_groups), switchs))
    pool.close()
    pool.join()


def _add_infs(lock, record):
    mark, infs, ip = record
    statement = """
    match (s:Switch {ip:{ip}})
    merge (s)-[:HAS]->(i:Inf {name:{name}})
    on create set i.desc={desc},i.updated=timestamp()
    on match set i.desc={desc},i.updated=timestamp()
    with s,i
    match (s)-->(g:Group {name:{group}})
    merge (g)-[r:OWNED]->(i)
    on create set r.updated=timestamp()
    on match set r.updated=timestamp()"""

    with lock:
        if mark == 'success':
            tx = graph.cypher.begin()
            lmap(lambda x: tx.append(statement, ip=ip, **x), infs)
            tx.process()
            tx.commit()
        with open(log_file, 'a') as flog:
            flog.write('{ip}:{mark}\n'.format(ip=ip, mark=mark))


def add_infs():
    funcs=dict(S8508=S85.get_infs,S8505=S85.get_infs)
    get_infs=partial(_model,funcs)
    clear_log()
    nodes = graph.cypher.execute(
        "match(s:Switch) where s.model='S8508' return s.ip as ip,s.model as model limit 10")
    switchs = [(x['ip'],x['model']) for x in nodes]
    pool = Pool(4)
    lock = Manager().Lock()
    _ff = partial(_add_infs, lock)
    lmap(compose(_ff, get_infs), switchs)
    pool.close()
    pool.join()


def main():
    pass
    add_groups()
    #  add_infs()


if __name__ == '__main__':
    main()
