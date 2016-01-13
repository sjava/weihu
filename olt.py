#!/usr/bin/env python
# -*- coding: utf-8 -*-
import configparser
import os
import multiprocessing
from multiprocess import Pool, Manager
from py2neo import Graph, Node
from py2neo import authenticate
from toolz import compose, map, partial
from device.olt import Zte, Huawei

config = configparser.ConfigParser()
config.read('config.ini')
neo4j_username = config.get('neo4j', 'username')
neo4j_password = config.get('neo4j', 'password')

zte_olt_username = config.get('olt', 'zte_username')
zte_olt_password = config.get('olt', 'zte_password')
hw_olt_username = config.get('olt', 'hw_username')
hw_olt_password = config.get('olt', 'hw_password')

olts_file, log_file, result_file = ('olts.txt', 'result/olt_log.txt',
                                    'result/olt_info.txt')

authenticate('61.155.48.36:7474', neo4j_username, neo4j_password)
graph = Graph("http://61.155.48.36:7474/db/data")


def clear_log():
    for f in [log_file, result_file]:
        if os.path.exists(f):
            os.remove(f)
        os.mknod(f)

######################card check################################
zte_card_check = partial(Zte.card_check,
                         username=zte_olt_username,
                         password=zte_olt_password)
hw_card_check = partial(Huawei.card_check,
                        username=hw_olt_username,
                        password=hw_olt_password)


def get_card(olt):
    functions = dict(zte=zte_card_check, hw=hw_card_check)
    no_company = lambda x: ['fail', None]
    ip, company = olt[:2]
    return functions.get(company, no_company)(ip) + [','.join(olt)]


def card_entry(info):
    create_card_node = lambda x: graph.create(
        Node('Card', slot=x[0], name=x[1]))[0]
    mark, result, olt = info
    with open(log_file, 'a') as logging:
        logging.write("{0}:{1}\n".format(olt, mark))
    if result and mark == 'success':
        ip = olt.split(',')[0]
        node = graph.find_one(
            'Olt', property_key='ip', property_value=ip)
        card_nodes = map(create_card_node, result)
        list(map(lambda x: graph.create((node, 'HAS', x)), card_nodes))


def card_entry_m(lock, info):
    create_card_node = lambda x: graph.create(
        Node('Card', slot=x[0], name=x[1]))[0]
    mark, result, olt = info
    with lock:
        with open(log_file, 'a') as logging:
            logging.write("{0}:{1}\n".format(olt, mark))
    if result and mark == 'success':
        ip = olt.split(',')[0]
        with lock:
            node = graph.find_one(
                'Olt', property_key='ip', property_value=ip)
            card_nodes = map(create_card_node, result)
            list(map(lambda x: graph.create((node, 'HAS', x)), card_nodes))


def card_check():
    clear_log()
    #  nodes = graph.find('Olt', property_key='ip', property_value='218.92.130.130')
    nodes = graph.find('Olt')
    #  nodes = graph.find('Olt', property_key='company', property_value='zte')
    olts = [(x['ip'], x['company'], x['area']) for x in nodes]
    #  list(map(compose(card_entry, get_card), olts))
    pool = multiprocessing.Pool(8)
    lock = multiprocessing.Manager().Lock()
    func = partial(card_entry_m, lock)
    list(pool.map(compose(func, get_card), olts))
    pool.close()
    pool.join()

#############power check###################################

hw_power_check = partial(Huawei.power_check,
                         username=hw_olt_username,
                         password=hw_olt_password)


def get_power(olt):
    functions = dict(hw=hw_power_check)
    no_company = lambda x: ['fail', None]
    ip, company = olt[:2]
    return functions.get(company, no_company)(ip) + [','.join(olt)]


def output_power_info(info):
    mark, result, olt = info
    with open(log_file, 'a') as logging:
        logging.write("{0}:{1}\n".format(olt, mark))
    if result and result[0] == 'Alarm' and mark == 'success':
        with open(result_file, 'a') as frslt:
            frslt.write("{0}:单电源或单路供电.\n".format(olt, ))


def power_check():
    clear_log()
    nodes = graph.find('Olt', property_key='company',
                       property_value='hw')
    olts = [(x['ip'], x['company'], x['area']) for x in nodes]
    funcy.lmap(funcy.compose(output_power_info, get_power), olts)

###################svlan check#############################
zte_epon_svlan = partial(Zte.epon_svlan,
                         username=zte_olt_username,
                         password=zte_olt_password)
zte_gpon_svlan = partial(Zte.gpon_svlan,
                         username=zte_olt_username,
                         password=zte_olt_password)
hw_svlan = partial(Huawei.svlan,
                   username=hw_olt_username,
                   password=hw_olt_password)


def get_svlan(olt):
    functions = dict(hw=hw_svlan, zte=zte_epon_svlan)
    no_company = lambda x: ['fail', None]
    ip, company = olt[:2]
    return functions.get(company, no_company)(ip) + [','.join(olt)]


def svlan_entry(lock, info):
    cmd = "match (n:Olt{ip:{ip}}) create unique (n)-[:USE{port:{port}}]-(:Svlan{value:{value}})"
    mark, result, olt = info
    ip = olt.split(',')[0]
    with lock:
        with open(log_file, 'a') as logging:
            logging.write("{0}:{1}\n".format(olt, mark))
    if result and mark == 'success':
        with lock:
            list(map(lambda x: graph.cypher.execute(
                cmd, {"ip": ip, "port": x[0], "value": x[1]}), result))
            #  with open(result_file, 'a') as frslt:
            #  list(map(
            #  lambda x: frslt.write("{0},{1},{2}\n".format(ip, x[0], x[1])),
            #  result))


def svlan_check():
    clear_log()
    #  nodes = graph.find('Olt', property_key='ip', property_value='9.192.96.246')
    nodes = graph.find('Olt')
    #  nodes = graph.find('Olt', property_key='company', property_value='zte')
    olts = [(x['ip'], x['company'], x['area']) for x in nodes]
    #  list(map(compose(card_entry, get_card), olts))
    pool = Pool(16)
    lock = Manager().Lock()
    func = partial(svlan_entry, lock)
    list(pool.map(compose(func, get_svlan), olts))
    pool.close()
    pool.join()


def zte_gpon_svlan_check():
    clear_log()
    nodes = graph.cypher.execute(
        "match(n:Olt)--(c:Card) where c.name='GTGO' return n.ip,collect(c.slot)")
    olts = ((x[0], x[1]) for x in nodes)
    lzte_gpon_svlan = lambda x: zte_gpon_svlan(ip=x[0], slots=x[1])
    pool = Pool(8)
    lock = Manager().Lock()
    func = partial(svlan_entry, lock)
    list(pool.map(compose(func, lzte_gpon_svlan), olts))
    pool.close()
    pool.join()

###########################hostname#############################
zte_hostname = partial(Zte.hostname,
                       username=zte_olt_username,
                       password=zte_olt_password)
hw_hostname = partial(Huawei.hostname,
                      username=hw_olt_username,
                      password=hw_olt_password)


def get_hostname(olt):
    functions = dict(hw=hw_hostname, zte=zte_hostname)
    no_company = lambda x: ['fail', None, x]
    ip, company = olt[:2]
    return functions.get(company, no_company)(ip)


def hostname_entry(lock, info):
    cmd = "match (n:Olt{ip:{ip}}) create unique (n)-[:USE{port:{port}}]-(:Svlan{value:{value}})"
    mark, result, ip = info
    with lock:
        with open(log_file, 'a') as logging:
            logging.write("{0}:{1}\n".format(ip, mark))
    if result and mark == 'success':
        with lock:
            #  list(map(lambda x: graph.cypher.execute(cmd, {"ip": ip, "port": x[0], "value": x[1]}), result))
            with open(result_file, 'a') as frslt:
                frslt.write("{0},{1}\n".format(ip, result))


def hostname_check():
    clear_log()
    nodes = graph.find('Olt')
    #  nodes = graph.find('Olt', property_key='ip', property_value='172.18.0.46')
    olts = [(x['ip'], x['company']) for x in nodes]
    pool = Pool(16)
    lock = Manager().Lock()
    func = partial(hostname_entry, lock)
    list(pool.map(compose(func, get_hostname), olts))
    pool.close()
    pool.join()
    ip_hostname = (x.split(',') for x in open(result_file))
    cmd = "match (n:Olt) where n.ip={ip} set n.hostname={hostname}"
    list(map(lambda x: graph.cypher.execute(
        cmd, ip=x[0], hostname=x[1]), ip_hostname))

################################zhongji check###########################
zte_zhongji = partial(Zte.zhongji,
                      username=zte_olt_username,
                      password=zte_olt_password)
hw_zhongji = partial(Huawei.zhongji,
                     username=hw_olt_username,
                     password=hw_olt_password)


def get_zhongji(olt):
    functions = dict(hw=hw_zhongji, zte=zte_zhongji)
    no_company = lambda x: ['fail', None, x]
    ip, company = olt[:2]
    return functions.get(company, no_company)(ip)


def zhongji_entry(lock, info):
    mark, result, ip = info
    with lock:
        with open(log_file, 'a') as logging:
            logging.write("{ip}:{mark}\n".format(ip=ip, mark=mark))
    if result and mark == 'success':
        with lock:
            #  list(map(lambda x: graph.cypher.execute(cmd, {"ip": ip, "port": x[0], "value": x[1]}), result))
            with open(result_file, 'a') as frslt:
                for (k, v) in result.items():
                    for i in v:
                        frslt.write(
                            "{ip},{sm},{interface}\n".format(ip=ip, sm=k, interface=i))


def zhongji_check():
    clear_log()
    graph.cypher.execute(
        'match (n:Olt)--(s:Etrunk)--(p:Port) detach delete s,p')
    nodes = graph.find('Olt')
    #  nodes = graph.find('Olt', property_key='ip', property_value='172.18.0.46')
    olts = [(x['ip'], x['company']) for x in nodes]
    pool = Pool(16)
    lock = Manager().Lock()
    func = partial(zhongji_entry, lock)
    list(pool.map(compose(func, get_zhongji), olts))
    pool.close()
    pool.join()
    ports = (x.split(',') for x in open(result_file))
    cmd = """match(n: Olt) where n.ip = {ip} 
    merge(n) - [:HAS]->(m: Etrunk{name: {sm}}) 
    merge(m) - [:Include]->(p: Port{name: {interface}})"""
    list(map(lambda x: graph.cypher.execute(
        cmd, ip=x[0], sm=x[1], interface=x[2].strip()), ports))

#############################################traffic####################
zte_traffic = partial(Zte.get_traffics,
                      username=zte_olt_username,
                      password=zte_olt_password)
hw_traffic = partial(Huawei.get_traffics,
                     username=hw_olt_username,
                     password=hw_olt_password)


def get_traffic(olt):
    functions = dict(hw=hw_traffic, zte=zte_traffic)
    no_company = lambda x, y: ['fail', None, x]
    ip, company, ports = olt
    return functions.get(company, no_company)(ip=ip, ports=ports)


def traffic_output(lock, info):
    mark, result, ip = info
    with lock:
        with open(log_file, 'a') as logging:
            logging.write("{ip}:{mark}\n".format(ip=ip, mark=mark))
    if result and mark == 'success':
        with lock:
            for r in result:
                with open(result_file, 'a') as frslt:
                    frslt.write("{ip},{port},{down},{up}\n".format(
                        ip=ip, port=r['name'].strip(), down=r['in_traffic'], up=r['out_traffic']))


def traffic_check():
    clear_log()
    cmd = 'match(n:Olt)-[*]-(p:Port) return n.ip,n.company,collect(p.name)'
    nodes = graph.cypher.execute(cmd)
    olts = [(x[0], x[1], x[2]) for x in nodes]
    pool = Pool(16)
    lock = Manager().Lock()
    func = partial(traffic_output, lock)
    list(pool.map(compose(func, get_traffic), olts))
    pool.close()
    pool.join()

    records = (x.split(',') for x in open(result_file))
    cmd = "match (n:Olt)-[*]-(p:Port) where n.ip={ip} and p.name={name} set p.in_traffic={r},p.out_traffic={s}"
    list(map(lambda x: graph.cypher.execute(
        cmd, ip=x[0], name=x[1], r=float(x[2]), s=float(x[3])), records))


def hw_conf():
    clear_log()
    cmd = 'match(n:Olt{company:\'hw\'})--(c:Card) where c.name contains \'GPBD\' return distinct n.ip'
    nodes = graph.cypher.execute(cmd)
    olts = [x[0] for x in nodes]
    #  nodes = graph.find('Olt')
    #  nodes = graph.find('Olt', property_key='ip', property_value='172.18.0.46')
    for ip in olts:
        child = Huawei.telnet(ip, hw_olt_username, hw_olt_password)
        child.sendline('conf')
        child.expect('#')
        child.sendline(
            'traffic table ip name G130M cir 146432 pir 146432 priority 0 priority-policy local-Setting')
        child.expect('#')
        child.sendline(
            'traffic table ip name G160M cir 180224 pir 180224 priority 0 priority-policy local-Setting')
        child.expect('#')
        child.sendline(
            'traffic table ip name G190M cir 214016 pir 214016 priority 0 priority-policy local-Setting')
        child.expect('#')
        child.sendline('ont-lineprofile gpon profile-name G20M')
        child.expect('}:')
        child.sendline()
        child.expect('#')
        child.sendline('tcont 1 dba-profile-id  10')
        child.expect('#')
        child.sendline('commit')
        child.expect('#')
        child.sendline('quit')
        child.expect('#')
        child.sendline('quit')
        child.expect('#')
        child.sendline('quit')
        child.expect(']:')
        child.sendline('y')
        child.close()


def zte_conf():
    cmd = "match (n:Olt)--(c:Card) where c.name='GTGO' return n.ip"
    olts = graph.cypher.execute(cmd)
    for olt in olts:
        child = Zte.telnet(olt[0], zte_olt_username, zte_olt_password)
        child.sendline('conf t')
        child.expect('#')
        child.sendline('traffic-profile G130M ip cir 146432 pir 146432')
        child.expect('#')
        child.sendline('traffic-profile G160M ip cir 180224 pir 180224')
        child.expect('#')
        child.sendline('traffic-profile G190M ip cir 214016 pir 214016')
        child.expect('#')
        child.sendline('gpon')
        child.expect('#')
        child.sendline('profile tcont G20M type 2 assured 22528')
        child.expect('#')
        child.sendline('exit')
        child.expect('#')
        child.sendline('exit')
        child.expect('#')
        child.sendline('exit')
        child.close()


def main():
    #  zhongji_check()
    #  hw_gpon()
    #  pass
    traffic_check()
    #  hw_conf()

if __name__ == '__main__':
    main()
