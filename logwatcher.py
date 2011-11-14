#!/usr/bin/python
import datetime
import math
import os
import pickle
import sys
import string
import time
import re

#Constants
#log_filename = 'testlog'
log_filename = '/home/minecraft/server/server.log'
html_filename = '/var/www/worldmap/online/index.html'
#html_filename = '/var/www/worldmap/online/index2.html'
server_lock_file = '/home/minecraft/server/server.log.lck'
server_time_format = '%Y-%m-%d %H:%M:%S'
date_format = '%b %d, %Y at %I:%M%p'
data_file = 'logwatcher.dat'
#data_file = 'logwatcher2.dat'
in_label = 'in'
out_label = 'out'
in_order_label = 'in_order'
out_order_label = 'out_order'

pattern = re.compile(r'(?P<date>[0-9]{4}-[0-9]{2}-[0-9]{2})\s(?P<time>[0-9]{2}:[0-9]{2}:[0-9]{2})\s\[(?P<type>\w+)\]\s<?(?P<username>.+?)>?\s(\[/(?P<ip>\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}):(?P<port>\d{1,5})\]\s)?(?P<message>.+)')

Players = {}

class Player:
    def __init__(self, name, time):
        self.name = name
        self.online = True
        self.total_time_played = datetime.timedelta(0)
        self.connection_log = []
        self.add_connect_time(time)

    def add_connect_time(self, time):
        self.online = True
        
        if len(self.connection_log) > 0:
            #Something weird has happened where a user logged in twice without logging
            #in between. In this case, disregard the last login.
            if self.connection_log[-1][0] == in_label:
                self.connection_log.pop()

            #Check to see if the last logout time was less than a minute ago.  If so,
            #disregard the last logout and this login.
            if self.connection_log[-1][0] == out_label:
                if (datetime.datetime.now() - self.connection_log[-1][1]) < datetime.timedelta(0, 60):
                    self.connection_log.pop()
                    return

        self.last_login = time
        self.connection_log.append((in_label, time))

        #Update order lists
        remove_from_order_lists(self.name)
        Players[in_order_label].append(self.name)

    def add_disconnect_time(self, time):
        global Players_Logout_Order
        self.online = False
        
        if len(self.connection_log) > 0 and self.connection_log[-1][0] == out_label:
                raise TypeError('{} has not connected yet.'.format(self.name))

        self.last_logout = time
        self.connection_log.append((out_label, time))
        self.total_time_played += (time - self.last_login)

        #Update order lists
        remove_from_order_lists(self.name)
        Players[out_order_label].append(self.name)

    def current_time_played(self):
        if self.online:
            return datetime.datetime.now() - self.last_login
        else:
            return self.last_logout - self.last_login

def daemonize():
    if os.fork():
        os._exit(0)

    os.setsid()
    sys.stdin = sys.__stdin__ = open('/dev/null', 'r')
    sys.stdin = sys.__stdout__ = open('/dev/null', 'w')
    sys.stdout = sys.__stderr__ = os.dup(sys.stdout.fileno())

def daemonize_log_watcher():
    global Players
    Players[in_order_label] = []
    Players[out_order_label] = []
    
    print 'Logwatcher is running...'
    force_update = False #In case there is no saved session, force scan of entire log.

    #Open the log file 
    try:
        logfile = open(log_filename, 'r')
    except IOError:
        print 'Could not open log file: {}'.format(log_filename)
        
    watcher = os.stat(log_filename)
    last_modified = this_modified = watcher.st_mtime
    list_changed = True
     
    #If there's a saved data file, open it.
    if os.path.isfile(data_file):
        try:
            pickled_file = open(data_file, 'rb')
            Players = pickle.load(pickled_file)
            logfile.seek(0, 2)
            Players = get_player_list(logfile, Players)
            write_html_file(Players)
            this_modified = watcher.st_mtime
            
        except EOFError:
            logfile.seek(0, 0)
            force_update = True
            
    else:
        logfile.seek(0, 0)
        force_update = True

    try:
        while 1:
            if not server_online:
                exit

            if this_modified > last_modified or force_update:
                last_modified = this_modified
                force_update = False

                while 1:
                    line = logfile.readline()

                    if not line:
                        if list_changed:
                            list_changed = False
                            save_data_file(Players)
                            write_html_file(Players)
                        break

                    match = pattern.search(line)

                    if match:
                        name = match.group('username')
                        message = match.group('message')
                        parsed_time = datetime.datetime.strptime(match.group('date') + ' ' + match.group('time'), server_time_format)
 
                        if "logged in" in message:
                            if '/' in name:
                                continue
                            if name not in Players:
                                Players[name] = Player(name, parsed_time)
                            else:    
                                Players[name].add_connect_time(parsed_time)

                            list_changed = True
                        elif "lost connection" in message:
                            if '/' in name:
                                continue
                            
                            Players[name].add_disconnect_time(parsed_time)
                            list_changed = True

            watcher = os.stat(log_filename)
            this_modified = watcher.st_mtime
            time.sleep(1)
    except KeyboardInterrupt:
        cleanup()

def save_data_file(players, shutting_down = False):
    try:
        pickle_file = open(data_file, 'w')
    except IOError:
        print 'Could not open data file.'

    #If we're shutting down, mark everyone as disconnected.
    if shutting_down:
        for key, player in players.iteritems():
            if player is Player and player.online:
                player.add_disconnect_time(datetime.datetime.now())
    
    pickle.dump(players, pickle_file)

def remove_from_order_lists(name):
    try:
        Players[out_order_label].remove(name)
    except:
        pass

    try:
        Players[in_order_label].remove(name)
    except:
        pass
    
def get_player_list(logfile, players):
    #Send 'list' command to server.
    os.system('screen -S minecraft -X stuff "list"\r')
    time.sleep(2)

    online_players = []

    while True:
        line = logfile.readline()
        
        if not line:
            return players

        match = re.search(r'Connected players:\s(?P<players>.+)?', line)

        if match:
            if match.group(1):
                online_players = string.split(match.group(1))
                for name in string.split(match.group(1)):
                    if name in players:
                        players[name].add_connect_time(datetime.datetime.now())
                    else:
                        players[name] = Player(name, datetime.datetime.now())
            return players
                    

def write_html_file(players):
    html_file = open(html_filename, 'w')
    num_online_players = len(players[in_order_label])

    if num_online_players == 0:
        html_file.write('No one is online.')
    else:
        html_file.write('{} player{} online:<br/>'.format(num_online_players, '' if num_online_players == 1 else 's'))
    
        for player_key in players[in_order_label]:
            html_file.write('{} online since {}.<br/>'.format(players[player_key].name,\
                                                                  players[player_key].last_login.strftime(date_format)))

    if len(players[out_order_label]) > 0:
        html_file.write('<br/><br/>Offline:<br/>')

        for player_key in reversed(players[out_order_label]):
            player = players[player_key]
            time_played = player.total_time_played.total_seconds()
            
            hours_played = int(time_played // 3600)
            minutes_played = int(time_played % 60)
            minutes_last_played = player.current_time_played().seconds / 60
            
            html_file.write('{} last seen on {}. Time played: {} minute{}. Total: {}h{}m.<br/>'\
                                .format(player.name, player.last_logout.strftime(date_format), minutes_last_played,\
                                            '' if minutes_last_played == 1 else 's',\
                                            hours_played, minutes_played))
        
    html_file.close()

def cleanup():
    global Players
    
    save_data_file(Players, True)
    html_file = open(html_filename, 'w')
    html_file.write('Logwatcher is offline.')
    html_file.close()    

def server_online():
    try:
        open(server_lock_file)
    except IOError as e:
        return False

    return True

    
if __name__ == '__main__':
#    daemonize()
    daemonize_log_watcher()
