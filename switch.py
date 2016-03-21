#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os
import re
import time
import pexpect
import configparser
import easysnmp
from multiprocess import Pool, Manager
from py2neo import Graph, Node, authenticate
from funcy import lmap, compose, partial, re_find, select
from device.switch import S85, S93, T64, S89, S8905E

config = configparser.ConfigParser()
config.read(os.path.expanduser('~/.weihu/config.ini'))
community = config.get('switch', 'community')
neo4j_username = config.get('neo4j', 'username')
neo4j_password = config.get('neo4j', 'password')

authenticate('61.155.48.36:7474', neo4j_username, neo4j_password)
graph = Graph("http://61.155.48.36:7474/db/data")

processor = 128
sw_file, log_file, result_file = ('sw.txt', 'result/sw_log.txt',
                                  'result/sw_info.txt')


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


def add_snmp_read():
    clear_log()
    nodes = graph.cypher.execute("match (s:Switch) where s.model='T64G' return s.ip as ip")
    ips = [x['ip'] for x in nodes]
    for ip in ips:
        rslt = 'success'
        try:
            child = T64.telnet(ip)
            child.sendline('config t')
            child.expect('#')
            T64.do_some(child, 'snmp-server community weihu@YCIP view AllView ro')
            T64.close(child)
        except (pexpect.EOF, pexpect.TIMEOUT) as e:
            rslt = 'fail'
        session = easysnmp.Session(hostname=ip, community='weihu@YCIP', version=1)
        try:
            item = session.get('1.3.6.1.2.1.1.1.0')
        except (easysnmp.EasySNMPTimeoutError) as e:
            rslt = 'fail'
        with open(log_file, 'a') as flog:
            flog.write('{ip}:{rslt}\n'.format(ip=ip, rslt=rslt))


def update_model():
    clear_log()
    nodes = graph.cypher.execute("match (s:Switch) return s.ip as ip")
    switchs = [x['ip'] for x in nodes]
    for x in switchs:
        mark = 'success'
        try:
            session = easysnmp.Session(hostname=x, community=community, version=1)
            rslt = session.get('1.3.6.1.2.1.1.1.0').value
            model = re_find(r'(?:Quidway (S\d+)|ZXR10 (\w+) Software)', rslt)
            model = select(bool, model)[0]
            if model.startswith('8905'):
                model = 'S' + model
            hostname = session.get('1.3.6.1.2.1.1.5.0').value
        except (easysnmp.EasySNMPTimeoutError) as e:
            mark = 'fail'
        if mark == 'success':
            graph.cypher.execute("match (s:Switch) where s.ip={ip} set s.model={model},s.hostname={hostname}",
                                 ip=x, model=model, hostname=hostname)
        with open(log_file, 'a') as flog:
            flog.write('{ip}:{mark}\n'.format(ip=x, mark=mark))


def del_old_data():
    cmd1 = """
    match (:Switch)-->(i:Inf)
    where timestamp()-i.updated>=24*60*60*1000*2
    detach delete i
    """
    cmd2 = """
    match (:Switch)-->(g:Group)
    where timestamp()-g.updated>=24*60*60*1000*2
    detach delete g
    """
    cmd3 = """
    match (:Switch)-->(:Group)-[r]->(:Inf)
    where timestamp()-r.updated>=24*60*60*1000*2
    detach delete r
    """
    graph.cypher.execute(cmd1)
    graph.cypher.execute(cmd2)
    graph.cypher.execute(cmd3)


def _model(funcs, device):
    def no_model(**kw): return ('fail', None, kw['ip'])
    model = device.pop('model')
    return funcs.get(model, no_model)(**device)


def _add_groups(lock, record):
    mark, groups, ip = record
    statement = """match (s:Switch {ip:{ip}})
    merge (s)-[r:HAS]->(g:Group {name:{name}})
    on create set g.mode={mode},g.desc={desc},g.updated=timestamp()
    on match set g.mode={mode},g.desc={desc},g.updated=timestamp()
    with s,g
    match (s)-->(g)-[r:OWNED]->(i:Inf)
    delete r"""

    with lock:
        if mark == 'success':
            tx = graph.cypher.begin()
            lmap(lambda x: tx.append(statement, ip=ip, **x), groups)
            tx.process()
            tx.commit()
        with open(log_file, 'a') as flog:
            flog.write('{ip}:{mark}\n'.format(ip=ip, mark=mark))


def add_groups():
    funcs = {'S8508': S85.get_groups,
             'S8505': S85.get_groups,
             'T64G': T64.get_groups,
             'S8905': S89.get_groups,
             'S8905E': S8905E.get_groups,
             'S9306': S93.get_groups,
             'S9303': S93.get_groups}
    get_groups = partial(_model, funcs)
    clear_log()
    nodes = graph.cypher.execute(
        "match(s:Switch) return s.ip as ip,s.model as model")
    switchs = [dict(ip=x['ip'], model=x['model']) for x in nodes]
    pool = Pool(processor)
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
    set i.desc={desc},i.updated=timestamp()
    with s,i
    match (s)-->(g:Group {name:{group}})
    merge (g)-[r:OWNED]->(i)
    set r.updated=timestamp()
    """

    with lock:
        if mark == 'success':
            tx = graph.cypher.begin()
            lmap(lambda x: tx.append(statement, ip=ip, name=x['name'], desc=x['desc'], group=x['group']), infs)
            tx.process()
            tx.commit()
        with open(log_file, 'a') as flog:
            flog.write('{ip}:{mark}\n'.format(ip=ip, mark=mark))


def add_infs():
    funcs = {'S8508': S85.get_infs,
             'S8505': S85.get_infs,
             'T64G': T64.get_infs,
             'S8905': S89.get_infs,
             'S8905E': S8905E.get_infs,
             'S9306': S93.get_infs,
             'S9303': S93.get_infs}
    get_infs = partial(_model, funcs)
    clear_log()
    nodes = graph.cypher.execute(
        "match(s:Switch) return s.ip as ip,s.model as model")
    switchs = [dict(ip=x['ip'], model=x['model']) for x in nodes]
    pool = Pool(processor)
    lock = Manager().Lock()
    _ff = partial(_add_infs, lock)
    list(pool.map(compose(_ff, get_infs), switchs))
    pool.close()
    pool.join()


def _add_traffics(lock, record):
    mark, rslt, ip = record
    cmd = """
    match (s:Switch {ip:{ip}})-->(i:Inf{name:{name}})
    set i.state={state},i.bw={bw},i.inTraffic={inTraffic},i.outTraffic={outTraffic},i.updated=timestamp()
    """
    with lock:
        if mark == 'success':
            tx = graph.cypher.begin()
            lmap(lambda x: tx.append(cmd, ip=ip, **x), rslt)
            tx.process()
            tx.commit()
        with open(log_file, 'a') as flog:
            flog.write('{ip}:{mark}\n'.format(ip=ip, mark=mark))


def add_traffics():
    funcs = {'S8508': S85.get_traffics,
             'S8505': S85.get_traffics,
             'T64G': T64.get_traffics,
             'S8905': S89.get_traffics,
             'S8905E': S8905E.get_traffics,
             'S9306': S93.get_traffics,
             'S9303': S93.get_traffics}
    get_traffics = partial(_model, funcs)
    clear_log()
    nodes = graph.cypher.execute(
        "match (s:Switch)--(i:Inf)  return s.ip as ip,collect(i.name) as infs,s.model as model")
    switchs = [dict(ip=x['ip'], infs=x['infs'], model=x['model']) for x in nodes]
    pool = Pool(processor)
    lock = Manager().Lock()
    _ff = partial(_add_traffics, lock)
    list(pool.map(compose(_ff, get_traffics), switchs))
    pool.close()
    pool.join()


def main():
    #  pass
    starttime = time.time()
    add_groups()
    #  add_infs()
    #  add_traffics()
    endtime = time.time()
    print(endtime - starttime)


if __name__ == '__main__':
    main()
