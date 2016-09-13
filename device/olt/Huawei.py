#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import pexpect
import sys
import re
import os
import configparser
from funcy import re_find, re_all, lmap, partial
from funcy import lmapcat

prompter = "#"
pager = "---- More.*----"
logfile = sys.stdout

config = configparser.ConfigParser()
config.read(os.path.expanduser('~/.weihu/config.ini'))
username = config.get('olt', 'hw_username')
password = config.get('olt', 'hw_password')


def telnet(ip):
    child = pexpect.spawn(
        'telnet {0}'.format(ip), encoding='ISO-8859-1')
    child.logfile = logfile
    child.expect("User name:")
    child.sendline(username)
    child.expect("User password:")
    child.sendline(password)
    index = child.expect(['>', pager])
    if index == 1:
        child.send(' ')
        child.expect('>')
    child.sendline('enable')
    child.expect(prompter)
    child.sendline('undo terminal monitor')
    child.expect(prompter)
    return child


def do_some(child, cmd):
    result = []
    child.sendline(cmd)
    while True:
        index = child.expect([prompter, pager], timeout=120)
        result.append(child.before)
        if index == 0:
            break
        else:
            child.send(' ')
            continue
    rslt = ''.join(result).replace('\x1b[37D', '')
    return rslt.replace(cmd + '\r\n', '', 1)


def close(child):
    child.sendline('quit')
    child.expect('n]:')
    child.sendline('y')
    child.close()


def get_groups(ip):
    def _get_group(child, group):
        rslt = do_some(
            child, 'disp link-aggregation {group}'.format(group=group))
        desc = re_find(r'description:(\S+)', rslt)
        mode = re_find(r'work mode:\s+(\S+)', rslt)
        temp = re_all(r'(\d+/\d+)\s+(\d\S+)', rslt)
        temp1 = lmapcat(lambda x: ['{0}/{1}'.format(x[0], y)
                                   for y in x[1].split(',')], temp)
        return dict(name=group, desc=desc, mode=mode, infs=temp1)

    try:
        child = telnet(ip)
        temp = re_all(r'(\d+/\d+/\d+)', do_some(child,
                                                'disp link-aggregation all'))
        groups = lmap(partial(_get_group, child), temp)
        close(child)
    except (pexpect.EOF, pexpect.TIMEOUT) as e:
        return ('fail', None, ip)
    return ('success', groups, ip)


def get_infs(ip):
    def _get_inf(child, board):
        slot, boardName = board
        rslt = do_some(child, 'disp board 0/{slot}'.format(slot=slot))
        rslt = [re_find(r'(\d+).*-\s+(?:auto_)?(\d+)', x)
                for x in rslt.split('\r\n')
                if 'online' in x]
        if boardName.lower() == 'gic':
            boardName = 'giu'
        child.sendline('conf')
        child.expect(prompter)
        child.sendline(
            'interface {boardName} 0/{slot}'.format(boardName=boardName, slot=slot))
        child.expect(prompter)
        temp = []
        for x, y in rslt:
            traffic = do_some(child, 'disp port traffic {port}'.format(port=x))
            inTraffic, outTraffic = re_all(r'\(octets/s\)\s+=(\d+)', traffic)
            inTraffic = int(inTraffic) * 8 / 1e6
            outTraffic = int(outTraffic) * 8 / 1e6
            bw = int(y or 0)
            temp.append(dict(name='0/{slot}/{port}'.format(slot=slot, port=x),
                             desc='cannot set', bw=bw, state='up',
                             inTraffic=inTraffic, outTraffic=outTraffic))
        child.sendline('quit')
        child.expect(prompter)
        child.sendline('quit')
        child.expect(prompter)
        return temp

    try:
        child = telnet(ip)
        rslt = do_some(child, 'disp board 0')
        boards = re_all(r'(\d+)\s+\w+(eth|gic)\w+\s+normal', rslt, flags=re.I)
        infs = lmapcat(partial(_get_inf, child), boards)
        close(child)
    except (pexpect.EOF, pexpect.TIMEOUT) as e:
        return ('fail', None, ip)
    return ('success', infs, ip)


def get_main_card(ip):
    try:
        child = telnet(ip)
        rslt = do_some(child, 'display board 0')
        close(child)
    except (pexpect.EOF, pexpect.TIMEOUT) as e:
        return ('fail', None, ip)
    cards = re_all(r'(SCUL|SCUN)\s+(?:Standby_normal|Active_normal)', rslt)
    return ('success', len(cards), ip)


def get_power_info(ip):
    try:
        child = telnet(ip)
        child.sendline('conf')
        child.expect(prompter)
        child.sendline('interface emu 0')
        child.expect(prompter)
        temp = do_some(child, 'display fan alarm')
        child.sendline('quit')
        child.expect(prompter)
        child.sendline('quit')
        child.expect(prompter)
        close(child)
    except (pexpect.EOF, pexpect.TIMEOUT) as e:
        return ('fail', None, ip)
    rslt = re_find(r'Power fault\s+(\w+)', temp)
    if rslt is None:
        rslt = "alarm"
    return ('success', rslt.lower(), ip)


def no_shut(ip, inf):
    try:
        child = telnet(ip)
        slot, port = inf.rsplit('/', 1)
        rslt = do_some(child, 'display board {slot}'.format(slot=slot))
        name = re_find(r'Board Name\s+:\s\w+(ETH)\w+', rslt) or 'giu'
        do_some(child, 'conf')
        do_some(child, 'interface {name} {slot}'.format(name=name, slot=slot))
        do_some(child, 'undo shutdown {port}'.format(port=port))
        do_some(child, 'quit')
        do_some(child, 'quit')
        close(child)
    except (pexpect.EOF, pexpect.TIMEOUT):
        return ('fail', ip)
    return ('success', ip)


def get_inf(ip, inf):
    try:
        child = telnet(ip)
        slot, port = inf.rsplit('/', 1)
        rslt = do_some(child, 'display board {slot}'.format(slot=slot))
        name = re_find(r'Board Name\s+:\s\w+(ETH)\w+', rslt) or 'giu'
        do_some(child, 'conf')
        do_some(child, 'interface {name} {slot}'.format(name=name, slot=slot))
        info = do_some(child, 'disp port state {port}'.format(port=port))
        do_some(child, 'quit')
        do_some(child, 'quit')
        close(child)
    except (pexpect.EOF, pexpect.TIMEOUT):
        return ('fail', None, ip)
    state = 'up' if re_find(r'port is online', info) else 'down'
    return ('success', state, ip)
