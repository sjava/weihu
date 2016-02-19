#!/usr/bin/env python
# -*- coding: utf-8 -*-
import pexpect
import configparser
import sys
import re
from funcy import re_all, ldistinct, re_find, lmap, partial

pager = "--More--"
prompter = "#"
logfile = sys.stdout

config = configparser.ConfigParser()
config.read('config.ini')
username = config.get('switch', 'username')
password = config.get('switch', 'passwd')
super_password = config.get('switch', 'super_passwd')


def telnet(ip):
    child = pexpect.spawn(
        'telnet {0}'.format(ip), encoding='ISO-8859-1')
    child.logfile = logfile

    child.expect('Username:')
    child.sendline(username)
    child.expect('Password:')
    child.sendline(password)
    index = child.expect(['>', '#'])
    if index == 0:
        child.sendline('enable')
        child.expect('Password:')
        child.sendline(super_password)
        child.expect('#')
    return child


def do_some(child, command):
    result = []
    child.sendline(command)
    while True:
        index = child.expect([prompter, pager], timeout=120)
        result.append(child.before)
        if index == 0:
            break
        else:
            child.send(' ')
            continue
    rslt = ''.join(result).replace('\x08', '')
    return rslt.replace(command + '\r\n', '', 1)


def close(child):
    child.sendcontrol('z')
    child.expect('#')
    child.sendline('exit')
    child.close()


def get_groups(ip):
    def _get_desc(child, group):
        name = group['name']
        rslt = do_some(child, 'show running-config-interface {name}'.format(name=name))
        desc = re_find(r'description\s(\S+)', rslt)
        mode = re_find(r'lacp\smode\s(\S+)', rslt)
        group['desc'] = desc
        group['mode'] = mode
        return group

    try:
        child = telnet(ip)
        rslt = do_some(child, 'show interface | in smartgroup')
        temp = [dict(name=x) for x in
                re_all(r'(smartgroup\d+)', rslt)]
        groups = lmap(partial(_get_desc, child), temp)
        close(child)
    except (pexpect.EOF, pexpect.TIMEOUT) as e:
        return ('fail', None, ip)
    return ('success', groups, ip)


def get_infs(ip):
    def _get_desc(child, inf):
        name = inf['name']
        rslt = do_some(child, 'show running-config-interface {name}'.format(name=name))
        desc = re_find(r'description\s(\S+)', rslt)
        group = re_find(r'(smartgroup\s\d+)', rslt)
        if group is not None:
            group = group.replace(' ', '')
        inf['desc'] = desc
        inf['group'] = group
        return inf

    try:
        child = telnet(ip)
        rslt = do_some(child, 'show interface | in (xg|g)ei-')
        temp = [dict(name=x)
                for x in re_all(r'(x?gei-\S+)', rslt)]
        infs = lmap(partial(_get_desc, child), temp)
        close(child)
    except (pexpect.EOF, pexpect.TIMEOUT) as e:
        return ('fail', None, ip)
    return ('success', infs, ip)


def get_traffics(ip, infs):
    def _get_traffic(child, inf):
        rslt = do_some(child, 'show interface {inf}'.format(inf=inf))
        state = re_find(r'{inf}\sis\s(\w+\s?\w+),'.format(inf=inf), rslt).lower()
        bw = int(re_find(r'BW\s(\d+)\sKbps', rslt)) / 1000
        inTraffic = int(re_find(r'120s input.*:\s(\d+)Bps', rslt)) * 8 / 1000000
        outTraffic = int(re_find(r'120s output.*:\s(\d+)Bps', rslt)) * 8 / 1000000
        infDict = dict(name=inf, state=state, bw=bw, inTraffic=inTraffic, outTraffic=outTraffic)
        return infDict

    try:
        child = telnet(ip)
        rslt = lmap(partial(_get_traffic, child), infs)
        close(child)
    except (pexpect.EOF, pexpect.TIMEOUT) as e:
        return ('fail', None, ip)
    return ('success', rslt, ip)
