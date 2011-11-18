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
#html_filename = '/var/www/worldmap/online/index.html'
html_filename = '/var/www/worldmap/online/index2.html'
server_lock_file = '/home/minecraft/server/server.log.lck'
server_time_format = '%Y-%m-%d %H:%M:%S'
date_format = '%b %d, %Y at %I:%M%p'
data_file = 'logwatcher.dat'
in_label = 'in'
out_label = 'out'
in_order_label = 'in_order'
out_order_label = 'out_order'
log_pos_label = 'log_pos'

pattern = re.compile(r'(?P<date>[0-9]{4}-[0-9]{2}-[0-9]{2})\s(?P<time>[0-9]{2}:[0-9]{2}:[0-9]{2})\s\[(?P<type>\w+)\]\s<?(?P<username>.+?)>?\s(\[/(?P<ip>\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}):(?P<port>\d{1,5})\]\s)?(?P<message>.+)')

class Player:
    """This class represents the player, which stores the player's data stored within Minecraft's log files."""
    def __init__(self, name, time):
        self.name = name
        self.online = True
        self.total_time_played = datetime.timedelta(0)
        self.connection_log = []
        self.add_connect_time(time)

    def add_connect_time(self, time):
        """Adds a connection time to the player's connectioin log."""
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

    def add_disconnect_time(self, time):
        """Adds a disconnection time to the player object's connection log."""
        self.online = False
        
        #Check to see if the player is already logged on.
        if len(self.connection_log) > 0 and self.connection_log[-1][0] == out_label:
            raise TypeError('{} has not connected yet.'.format(self.name))
        
        self.last_logout = time
        self.connection_log.append((out_label, time))
        self.total_time_played += (time - self.last_login)

    def current_time_played(self):
        """Calculates the current time played since last login.
        Will return the last duration played if player is offline."""
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

def main():
    players = {}
    players[in_order_label] = []
    players[out_order_label] = []
    list_changed = True
    
    print "Logwatcher is running..."

    #Open the log file 
    try:
        logfile = open(log_filename, 'r')
    except IOError:
        print "Could not open log file: {}".format(log_filename)
        
    watcher = os.stat(log_filename)
    this_modified = watcher.st_mtime
    last_modified = 0 #This will force the loop to run at least once at start.
     
    #If there's a saved data file, open it.
    if os.path.isfile(data_file):
        try:
            pickled_file = open(data_file, 'rb')            
        except EOFError:
            pass
        
        players = pickle.load(pickled_file)
        logfile.seek(players[log_pos_label])
            
    try:
        while 1:
            if not server_online:
                print "Minecraft server does not seem to be online."
                exit

            if this_modified > last_modified:
                last_modified = this_modified

                while 1:
                    line = logfile.readline()

                    if not line:
                        if list_changed:
                            list_changed = False
                            save_data_file(players)
                            write_html_file(players)

                        #Save the log position.
                        players[log_pos_label] = logfile.tell()
                        break

                    match = pattern.search(line)

                    if match:
                        name = match.group('username')
                        message = match.group('message')
                        parsed_time = datetime.datetime.strptime(match.group('date') + ' ' + match.group('time'), server_time_format)
 
                        if "logged in" in message:
                            if '/' in name:
                                continue
                            if name not in players:
                                players[name] = Player(name, parsed_time)
                            else:    
                                players[name].add_connect_time(parsed_time)

                            #Update order lists.
                            remove_from_order_lists(players, name)
                            players[in_order_label].append(name)

                            list_changed = True
                        elif "lost connection" in message:
                            #Don't do anything if "name" variable is an IP (starts with '/').
                            if '/' in name:
                                continue
                            
                            players[name].add_disconnect_time(parsed_time)

                            #Update order lists.
                            remove_from_order_lists(players, name)
                            players[out_order_label].append(name)
                            list_changed = True

            watcher = os.stat(log_filename)
            this_modified = watcher.st_mtime
            time.sleep(1)
    except KeyboardInterrupt:
        cleanup(players)

def save_data_file(players):
    try:
        pickle_file = open(data_file, 'w')
    except IOError:
        pickle_file.close()
        print "Could not open data file."

    pickle.dump(players, pickle_file)
    pickle_file.close()

def remove_from_order_lists(players, name):
    """Removes player names from both ordering lists."""
    try:
        players[out_order_label].remove(name)
    except:
        pass

    try:
        players[in_order_label].remove(name)
    except:
        pass
    
def get_player_list(logfile, players):
    """Sends the 'list' command to the server to get the currently online players"""
    #Consider removing this method; it's not being used.
    #Send 'list' command to server.
    os.system('screen -S minecraft -X stuff "list"\r')
    time.sleep(2)

    online_players = []

    while True:
        line = logfile.readline()
        
        if not line:
            return players

        match = re.search(r"Connected players:\s(?P<players>.+)?", line)

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
        html_file.write("No one is online.")
    else:
        html_file.write("{} player{} online:<br/>".format(num_online_players, '' if num_online_players == 1 else 's'))
    
        for player_key in players[in_order_label]:
            html_file.write("{} online since {}.<br/>".format(players[player_key].name,\
                                                                  players[player_key].last_login.strftime(date_format)))

    if len(players[out_order_label]) > 0:
        html_file.write("<br/><br/>Offline Players:<br/>")

        for player_key in reversed(players[out_order_label]):
            player = players[player_key]
            time_played = player.total_time_played.total_seconds()
            
            hours_played = int(time_played // 3600)
            minutes_played = int(time_played % 60)
            minutes_last_played = player.current_time_played().seconds / 60
            
            html_file.write("{} last seen on {}. Time played: {} minute{}. Total: {}h{}m.<br/>"\
                                .format(player.name, player.last_logout.strftime(date_format), minutes_last_played,\
                                            '' if minutes_last_played == 1 else 's',\
                                            hours_played, minutes_played))
        
    html_file.close()

def cleanup(players):
    save_data_file(players)
    html_file = open(html_filename, 'w')
    html_file.write("Logwatcher is offline.")
    html_file.close()    

def server_online():
    try:
        open(server_lock_file)
    except IOError as e:
        return False

    return True

    
if __name__ == '__main__':
#    daemonize()
    main()
