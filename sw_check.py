#!/usr/bin/env python
# -*- coding: utf-8 -*-
from device.switch import S85, S89, S8905E, S93, T64
from functools import reduce


def t64_vlan(ip):
    def _vlan(x, y):
        if '-' in y:
            start, stop = [int(x) for x in y.split('-')]
        else:
            start = int(y)
            stop = start
        return x | set(range(start, stop + 1))

    mark, rslt, ip = T64.get_infs(ip)
    if not mark:
        return None
    vlans = [x['vlan'] for x in rslt]
    vlans = reduce(lambda x, y: x | set(y), vlans, set())
    vlans = reduce(_vlan, vlans, set())
    return vlans
