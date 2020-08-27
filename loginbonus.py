#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import requests
from collections import defaultdict
import os
from datetime import date, timedelta
from slack import WebClient
import argparse
# from random import randrange
from bisect import bisect_right
import hashlib
import subprocess
import re

# Example:
# python loginbonus.py
#

post_to_slack = True
# update_link = True
slacktoken_file = 'slack_token'

excluded_members = set()

channel_name = '自動アナウンス'
appdir = '/var/loginbonus/'
base_dir = os.environ['HOME'] + appdir
history_dir = base_dir + 'history/'
history_file_format = '%d.txt' # date
ts_file = 'ts-loginbonus'
excluded_members_file = 'excluded_members.txt'
post_format = {
    'post_header_format' : '＊【%sのログインボーナス】＊',
    'post_line_format' : '<@%s> さん', # member
    'post_nobody' : 'ログインした人はいません。',
    'post_footer' : '\n以上の方にログインボーナスが付与されます。\nおめでとうございます！ :sparkles:',
}
post_format_list = {
    'post_header_format' : '＊【現在の利用者一覧】＊',
    'post_footer' : '以上、%d名です。 :sparkles:',
}

loginname_format = re.compile(r'u[0-9]{6}[a-z]')

def get_channel_list(client, limit=200):
    params = {
        'exclude_archived': 'true',
        'types': 'public_channel',
        'limit': str(limit),
        }
    channels = client.api_call('conversations.list', params=params)
    if channels['ok']:
        return channels['channels']
    else:
        return None

def get_channel_id(client, channel_name):
    channels = filter(lambda x: x['name']==channel_name , get_channel_list(client))
    target = None
    for c in channels:
        if target is not None:
            break
        else:
            target = c
    if target is None:
        return None
    else:
        return target['id']

def login_members(members, name, day):
    daystr = day.strftime('%Y%m%d')
    since = daystr + '000000'
    till = daystr + '235959'
    last_out = subprocess.run(
                    ['last', '-s', since, '-t', till],
                    encoding='utf-8', stdout=subprocess.PIPE,
                    ).stdout.splitlines()[:-2]
    logins = { line.split()[0] for line in last_out }
    ret = set()
    for m in members:
        m_name = name[m].strip()
        if not m_name:
            continue
        m_loginname = m_name.split('_')[-1]
        if loginname_format.fullmatch(m_loginname) and m_loginname in logins:
            ret.add(m)

    return ret


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--noslack', help='do not post to slack.',
                        action='store_true')
    parser.add_argument('--mute', help='post in thread without showing on channel.',
                        action='store_true')
    parser.add_argument('--solopost',
                        help='post an idependent message out of the thread, not destroying previous thread info',
                        action='store_true')
    parser.add_argument('--list', help='list all the members.',
                        action='store_true')
    parser.add_argument('-c', '--channel', default=channel_name,
                        help='slack channel to read & post.')
    parser.add_argument('-o', '--outchannel', default=None,
                        help='slack channel to post.')
    parser.add_argument('--slacktoken', default=None,
                        help='slack bot token.')
    args = parser.parse_args()

    if args.noslack:
        post_to_slack = False
    channel_name = args.channel

    # memberlist_file_path = base_dir + memberlist_file
    slacktoken_file_path = base_dir + slacktoken_file
    history_file_path_format = history_dir + history_file_format
    excluded_members_file_path = base_dir + excluded_members_file

    today = date.today() - timedelta(days=1) # actually yesterday
    ADfirst = date(1,1,1) # AD1.1.1 is Monday
    today_id = (today-ADfirst).days
    history_file_path = history_file_path_format % today_id

    if (not args.list) and os.path.exists(history_file_path):
        exit()
    if args.list:
        for k, v in post_format_list.items():
            post_format[k] = v
    for k, v in post_format.items():
        globals()[k] = v

    if args.slacktoken:
        token = args.slacktoken
    else:
        with open(slacktoken_file_path, 'r') as f:
            token = f.readline().rstrip()
    web_client = WebClient(token=token)
    channel_id = get_channel_id(web_client, channel_name)
    my_id = web_client.api_call('auth.test')['user_id']

    writers_dict = dict()
    if os.path.exists(excluded_members_file_path):
        with open(excluded_members_file_path, 'r') as f:
            lines = f.readlines()
            for line in lines:
                excluded_members.add(line.rstrip().split()[1])
    channel_info = web_client.api_call('channels.info', params={'channel':channel_id})['channel']
    # ensure I am a member of the channel.
    # if not channel_info['is_member']:
    #     return
    members = set(channel_info['members']) - excluded_members
    members.discard(my_id)
    if args.list:
        for d, writer in enumerate(next_writers(members, len(members), last_writer)):
            writers_dict[d] = writer
    else:
        writers = next_writers(members, len(relaydays), last_writer)
        lastwriter = writers[-1]
        for i, d in enumerate(relaydays):
            writers_dict[d] = writers[i]
        # write the new history
        with open(history_file_path, 'w') as f:
            for d, u in writers_dict.items():
                print(date_id + d, u, file=f)

    if args.list: week_id = max(week_id, lastweek_id + 1)
    post_lines = [post_header_format % week_str[week_id - thisweek_id]]
    if writers_dict:
        for d, writer in writers_dict.items():
            if args.list:
                post_lines.append(post_line_format % writer)
            else:
                date = startday + timedelta(d)
                post_lines.append(post_line_format % (date.month, date.day, weekdays[d], writer))
        post_lines.append(
            post_footer
        )
    else:
        post_lines.append(post_nobody)
    message = '\n'.join(post_lines)

    if post_to_slack:
        if args.outchannel:
            channel_id = get_channel_id(web_client, args.outchannel)
        params={
            'channel': channel_id,
            'text': message,
        }
        os.chdir(history_dir)
        if os.path.isfile(ts_file):
            with open(ts_file, 'r') as f:
                ts = f.readline().rstrip()
                if not args.solopost:
                    params['thread_ts'] = ts
                    if not args.mute:
                        params['reply_broadcast'] = 'True'
        else:
            ts = None
        response = web_client.api_call(
            'chat.postMessage',
            params=params
        )
        posted_data = response.data
        if ts is None:
            ts = posted_data['ts']
            with open(ts_file, 'w') as f:
                print(ts, file=f)
        # elif os.path.isfile(ts_file):
        #     os.remove(ts_file)
    else:
        print('App ID:', my_id)
        print(message)
