#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import device.olt

with open('result/temp.txt') as f:
    olts = [x.split(',')[0] for x in f]


for ip in olts:
    child = device.olt.telnet_zte(ip, '', '')
    child.sendline('conf t')
    child.expect(device.olt.zte_prompt)
    child.sendline('no monitor session 1')
    child.expect(device.olt.zte_prompt)
    child.sendline('exit')
    child.expect(device.olt.zte_prompt)
    child.sendline('exit')
    child.close()
