#!/usr/bin/env python
# -*- coding: utf-8 -*-
import configparser
import pexpect
import os
import multiprocessing
from multiprocess import Pool, Manager
from py2neo import Graph, Node
from py2neo import authenticate
from toolz import thread_last
from funcy import partial, compose, lmap, re_all, re_test
from device.olt import Zte, Huawei
import time

config = configparser.ConfigParser()
config.read(os.path.expanduser('~/.weihu/config.ini'))
neo4j_username = config.get('neo4j', 'username')
neo4j_password = config.get('neo4j', 'password')


olts_file, log_file, result_file = ('olts.txt', 'result/olt_log.txt',
                                    'result/olt_info.txt')

authenticate('61.155.48.36:7474', neo4j_username, neo4j_password)
graph = Graph("http://61.155.48.36:7474/db/data")


def clear_log():
    for f in [log_file, result_file]:
        if os.path.exists(f):
            os.remove(f)
        os.mknod(f)


def _company(funcs, device):
    def unknow_company(**kw): return ('fail', None, kw['ip'])
    company = device.pop('company')
    return funcs.get(company, unknow_company)(**device)


def _add_infs(lock, record):
    mark, infs, ip = record
    statement = """
    match(n:Olt {ip:{ip}})
    merge (n)-[:HAS]->(i:Inf {name:{name}})
    on create set i.desc={desc},i.state={state},i.bw={bw},
    i.inTraffic={inTraffic},i.outTraffic={outTraffic},i.updated=timestamp()
    on match set i.desc={desc},i.state={state},i.bw={bw},
    i.inTraffic={inTraffic},i.outTraffic={outTraffic},i.updated=timestamp()"""
    with lock:
        with open(log_file, 'a') as lf:
            lf.write('{ip}:{mark}\n'.format(ip=ip, mark=mark))
        if mark == 'success' and infs:
            tx = graph.cypher.begin()
            lmap(lambda x: tx.append(statement, ip=ip, **x), infs)
            tx.process()
            tx.commit()


def add_infs():
    funcs = {'zte': Zte.get_infs, 'hw': Huawei.get_infs}
    get_infs = partial(_company, funcs)

    clear_log()
    nodes = graph.cypher.execute(
        'match (n:Olt) return n.ip as ip,n.company as company')
    olts = [dict(ip=x['ip'], company=x['company']) for x in nodes]
    pool = Pool(128)
    lock = Manager().Lock()
    _add_infs_p = partial(_add_infs, lock)
    list(pool.map(compose(_add_infs_p, get_infs), olts))
    pool.close()
    pool.join()


def _add_groups(lock, record):
    mark, groups, ip = record
    stmt1 = """
    match(n:Olt {ip:{ip}})
    merge (n)-[:HAS]->(g:Group {name:{name}})
    set g.desc={desc},g.mode={mode},g.updated=timestamp()"""
    stmt2 = """
    match (i:Inf {name:{infName}})<--(n:Olt {ip:{ip}})-->(g:Group {name:{name}})
    merge (g)-[r:OWNED]->(i)
    set r.updated=timestamp()"""

    with lock:
        with open(log_file, 'a') as lf:
            lf.write('{ip}:{mark}\n'.format(ip=ip, mark=mark))
        if mark == 'success' and groups:
            tx = graph.cypher.begin()
            for x in groups:
                tx.append(stmt1, ip=ip, name=x['name'], desc=x['desc'], mode=x['mode'])
                for infName in x['infs']:
                    tx.append(stmt2, infName=infName, ip=ip, name=x['name'])
            tx.process()
            tx.commit()


def add_groups():
    funcs = {'zte': Zte.get_groups, 'hw': Huawei.get_groups}
    get_groups = partial(_company, funcs)

    clear_log()
    nodes = graph.cypher.execute(
        'match (n: Olt) return n.ip as ip, n.company as company')
    olts = [dict(ip=x['ip'], company=x['company'])
            for x in nodes]
    pool = Pool(128)
    lock = Manager().Lock()
    _add_groups_p = partial(_add_groups, lock)
    list(pool.map(compose(_add_groups_p, get_groups), olts))
    pool.close()
    pool.join()


def _add_main_card(lock, record):
    mark, rslt, ip = record
    stmt = """
    match (n:Olt) where n.ip={ip}
    set n.mainCard={rslt}
    """
    with lock:
        with open(result_file, 'a') as frslt:
            frslt.write('{ip}:{mark}\n'.format(ip=ip, mark=mark))
        if mark == 'success':
            tx = graph.cypher.begin()
            tx.append(stmt, ip=ip, rslt=rslt)
            tx.process()
            tx.commit()


def add_main_card():
    funcs = {'zte': Zte.get_main_card, 'hw': Huawei.get_main_card}
    get_main_card = partial(_company, funcs)
    clear_log()

    nodes = graph.cypher.execute(
        'match (n: Olt) return n.ip as ip, n.company as company')
    olts = [dict(ip=x['ip'], company=x['company'])
            for x in nodes]
    pool = Pool(128)
    lock = Manager().Lock()
    _add_main_card_p = partial(_add_main_card, lock)
    list(pool.map(compose(_add_main_card_p, get_main_card), olts))
    pool.close()
    pool.join()


def _add_power_info(lock, record):
    mark, rslt, ip = record
    stmt = """
    match (n:Olt) where n.ip={ip}
    set n.powerInfo={rslt}
    """
    with lock:
        with open(log_file, 'a') as frslt:
            frslt.write('{ip}:{mark}\n'.format(ip=ip, mark=mark))
        if mark == 'success':
            tx = graph.cypher.begin()
            tx.append(stmt, ip=ip, rslt=rslt)
            tx.process()
            tx.commit()


def add_power_info():
    funcs = {'zte': Zte.get_power_info, 'hw': Huawei.get_power_info}
    get_power_info = partial(_company, funcs)
    clear_log()

    nodes = graph.cypher.execute(
        'match (n: Olt) return n.ip as ip, n.company as company')
    olts = [dict(ip=x['ip'], company=x['company'])
            for x in nodes]
    pool = Pool(128)
    lock = Manager().Lock()
    _add_power_info_p = partial(_add_power_info, lock)
    list(pool.map(compose(_add_power_info_p, get_power_info), olts))
    pool.close()
    pool.join()


def main():
    #  pass
    start = time.time()
    #  add_infs()
    #  add_groups()
    #  add_main_card()
    add_power_info()
    print(time.time() - start)

if __name__ == '__main__':
    main()
