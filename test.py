#!/usr/bin/env python
# -*- coding: utf-8 -*-
import pexpect
import re
import os
from switch import graph
from device.olt import Huawei, Zte


def get_main_card():
    nodes = graph.cypher.execute('match (n:Olt) where n.company="zte" return n.ip as ip')
    ips = [x['ip'] for x in nodes]
    with open('test/test.txt', 'w') as flog:
        for ip in ips:
            mark, rslt, ip = Zte.get_main_card(ip)
            flog.write('{ip}:{mark}:{rslt}\n'.format(ip=ip, mark=mark, rslt=rslt))
