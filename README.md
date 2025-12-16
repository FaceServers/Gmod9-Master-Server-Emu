# Gmod9 Master Server Emulator

Valve has broken the Master Servers for Source SDK 2006 and don't seem to have any intention on fixing it. This makes Gmod 9 unable to list servers when you go to the Internet Tab under Find Servers in game.
As the Master Servers now use a newer Steam Client version, we have written a master server emulator that gets the current list of Gmod 9 servers from Steam's API and serves it to Gmod 9 game clients requesting servers.

Make sure to edit STEAM_API_KEY to be your Steam API Key from https://steamcommunity.com/dev/apikey