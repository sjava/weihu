#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os
import configparser
from multiprocess import Pool
from datetime import datetime
from device.bras import ME60, M6k
from py2neo import authenticate, Graph, Node
from funcy import lmap, partial, compose, map

basFile = 'bras.txt'
logFile = 'result/bas_log.txt'
infoFile = 'result/bas_info.txt'

conf = configparser.ConfigParser()
conf.read(os.path.expanduser('~/.weihu/config.ini'))
#  conf.read('config.ini')
neo4j_username = conf.get('neo4j', 'username')
neo4j_password = conf.get('neo4j', 'password')
authenticate('localhost:7474', neo4j_username, neo4j_password)
graph = Graph("http://localhost:7474/db/data")


def clear():
    for f in [logFile, infoFile]:
        if os.path.exists(f):
            os.remove(f)
        os.mknod(f)


def import_bras(file):
    bras = (x.strip().split(',') for x in open(file))
    brasNode = lambda x: graph.create(
        Node('Bras', **dict(zip(('name', 'ip', 'model', 'area'), x))))
    lmap(brasNode, bras)


def _model(funcs, device):
    no_model = lambda x: ('fail', None, x)
    ip, model = device
    return funcs.get(model, no_model)(ip)


def bingfa_check():
    funcs = {
        'ME60': ME60.get_bingfa,
        'ME60-X16': ME60.get_bingfa,
        'M6000': M6k.get_bingfa,
        'M6000-S': M6k.get_bingfa,
    }
    _get_bf = partial(_model, funcs)

    clear()
    nodes = graph.find('Bras')
    bras = [(x['ip'], x['model']) for x in nodes]
    rslt = map(_get_bf, bras)
    with open(logFile, 'w') as flog, open(infoFile, 'w') as frslt:
        for mark, record, ip in rslt:
            flog.write('{ip}:{mark}\n'.format(ip=ip, mark=mark))
            for slot, user, date in record:
                frslt.write('{ip},{slot},{user},{date}\n'.format(
                    ip=ip, slot=slot, user=user, date=date))


def _add_bingfa(rslt):
    cmd = """
    match (b:Bras {ip:{ip}})
    merge (b)-[:HAS]->(c:Card {slot:{slot}})
    set c.peakUsers={peakUsers},c.peakTime={peakTime},c.updated=timestamp()
    """
    mark, record, ip = rslt
    with open(logFile, 'a') as flog:
        flog.write('{ip}:{mark}\n'.format(ip=ip, mark=mark))
    if mark == 'success':
        tx = graph.cypher.begin()
        lmap(lambda x: tx.append(cmd, ip=ip, slot=x[
             0], peakUsers=x[1], peakTime=x[2]), record)
        tx.process()
        tx.commit()


def add_bingfa():
    funcs = {
        'ME60': ME60.get_bingfa,
        'ME60-X16': ME60.get_bingfa,
        'M6000-S': M6k.get_bingfa,
        'M6000': M6k.get_bingfa
    }
    _get_bf = partial(_model, funcs)

    clear()
    nodes = graph.find('Bras')
    bras = [(x['ip'], x['model']) for x in nodes]
    lmap(compose(_add_bingfa, _get_bf), bras)


def add_itv_online():
    devices = {'ME60': ME60, 'ME60-X16': ME60, 'M6000-S': M6k, 'M6000': M6k}
    action = 'get_itv_online'
    nodes = graph.find('Bras')
    bras = [(x['ip'], x['model']) for x in nodes]
    funcs = map(lambda x: partial(getattr(devices.get(x[1]), action), x[0]),
                bras)
    with Pool(16) as p:
        rslt = p.map(lambda f: f(), funcs)
    rslt = filter(lambda x: x[0] == 'success', rslt)
    update_time = datetime.now().strftime('%Y-%m-%d %H:%M')

    cmd = """
    match (b:Bras {ip:{ip}})
    merge (b)-[:HAS]->(i:ITV)
    set i.count={count},i.updateTime={time}
    """
    tx = graph.cypher.begin()
    lmap(lambda y: tx.append(cmd, ip=y[2], count=y[1], time=update_time), rslt)
    tx.process()
    tx.commit()


def main():
    #  pass
    add_bingfa()


if __name__ == '__main__':
    main()
