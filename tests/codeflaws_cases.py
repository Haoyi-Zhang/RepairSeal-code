"""Explicit mathematical normalizations of two reviewed natural source pairs.

These are project-authored scalar models, not redistributed upstream translation
units or a general C frontend. Original source identity, I/O and integer-range
premises are recorded separately. No held-out data constructs these functions.
"""
from __future__ import annotations

CASES = {
    '4-A': {
        'subject': '4-A-bug-18258406-18258457', 'input': 'w',
        'sources': {'buggy': ('4-A-18258406.c','0713806f76a4bf8c22a3ee7ca6a2585b2d08e2073b02094f6c7337ec1d0c24df'),
                    'supplied': ('4-A-18258457.c','6f74c3b6969296535b12ca5393e781fa0c8ce783f1c40f2dd4d2247634c31486')},
        'domain': list(range(1,61))+[97,98,99,100],
        'guard': 'w == 2u',
        'body': {
            'buggy': 'unsigned r = 0u; if ((w >= w) && (w % 2u == 0u)) { r = 1u; } else { r = 0u; } return r;',
            'supplied': 'unsigned r = 0u; if ((w >= 4u) && (w % 2u == 0u)) { r = 1u; } else { r = 0u; } return r;',
            'reference': 'unsigned r = 0u; if ((w > 2u) && (w % 2u == 0u)) { r = 1u; } else { r = 0u; } return r;'},
        'statement': 'https://codeforces.com/problemset/problem/4/A',
    },
    '84-A': {
        'subject': '84-A-bug-9385928-9385933', 'input': 'n',
        'sources': {'buggy': ('84-A-9385928.c','1686ffd63ba4033a98d5b3d6b96b8e28a89764b99ae523958191a99d68e56431'),
                    'supplied': ('84-A-9385933.c','c6cacf09a2c35fa5e4071b10e0cf1b361060f1bf62dcf57375b23ee2cec34c90')},
        'domain': list(range(2,121,2))+[99999994,99999996,99999998,100000000],
        'guard': 'n == n',
        'body': {'buggy':'return (3u / 2u) * n;', 'supplied':'return n + n / 2u;', 'reference':'return (3u * n) / 2u;'},
        'statement': 'https://codeforces.com/problemset/problem/84/A',
    },
}

def function(case: str, role: str) -> str:
    c=CASES[case]
    return 'unsigned f(unsigned '+c['input']+') { '+c['body'][role]+' }'

def request(case: str, candidate: str) -> dict:
    if candidate not in {'buggy','supplied'}:raise ValueError('candidate origin')
    c=CASES[case]
    return {'id':'codeflaws-'+case+'-'+candidate,'word_bits':32,'inputs':{c['input']:list(c['domain'])},
            'original':function(case,'buggy'),'candidate':function(case,candidate),
            'reference':function(case,'reference'),'repair_guard':c['guard']}

def value(case: str, role: str, x: int) -> int:
    if type(x) is not int or not legal_input(case,x):raise ValueError('input outside task range')
    if role not in {'buggy','supplied','reference'}:raise ValueError('source role')
    if case=='4-A':return int(x%2==0 and (role=='buggy' or x>=4))
    return x if role=='buggy' else x+x//2

def trace(case: str, role: str, x: int) -> list:
    return [[0,value(case,role,x)]] if case=='4-A' else []

def legal_input(case: str, x: int) -> bool:
    if type(x) is not int:return False
    if case=='4-A':return 1<=x<=100
    if case=='84-A':return 2<=x<=100000000 and x%2==0
    raise ValueError('case')

def decode_output(case: str, raw: bytes) -> int:
    if len(raw)>128:raise ValueError('output bound')
    text=raw.decode('ascii').strip()
    if case=='4-A':
        if text not in {'YES','NO'}:raise ValueError('output label')
        return int(text=='YES')
    if not text or not text.isascii() or not text.isdecimal():raise ValueError('numeric output')
    return int(text)
