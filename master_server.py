import socket
import struct
import sys
import json
import os
import time
import requests
from urllib.parse import urlencode

#############################
# --- Main Configuration ---#
#############################
MASTER_HOST = '0.0.0.0'
MASTER_PORT = 55555
SERVERS_FILENAME = 'servers.json'

#############################
# --- Extra Configuration --#
#############################
API_REFRESH_INTERVAL = 30 
STEAM_API_KEY = '0000000000000000000000000'
STEAM_API_FILTER = r'gamedir\gmod9'
STEAM_API_LIMIT = 200
#############################

QUERY_HEADER = b'\x31\xff'
RESPONSE_HEADER = b'\xff\xff\xff\xff\x66\x0a'
TERMINATOR_IP = '0.0.0.0'
TERMINATOR_PORT = 0

# --- Global state ---
GAME_SERVERS = []
LAST_MODIFIED_TIME = 0
LAST_API_FETCH_TIME = 0

def fetch_and_update_servers():
    """
    Fetches the server list from the Steam Web API and writes it to the JSON file.
    """
    global LAST_API_FETCH_TIME
    print("\nAttempting to fetch server list from Steam API...")

    # Construct the URL
    base_url = 'https://api.steampowered.com/IGameServersService/GetServerList/v1/'
    params = {
        'key': STEAM_API_KEY,
        'filter': STEAM_API_FILTER,
        'limit': STEAM_API_LIMIT
    }
    
    try:
        # Make GET request to the Steam API
        response = requests.get(base_url, params=params, timeout=10)
        response.raise_for_status()  # Raises an exception for bad status codes (4xx or 5xx)
        
        api_data = response.json()
        
        # Validate response
        if 'response' not in api_data or 'servers' not in api_data['response']:
            print("[API ERROR] Unexpected JSON structure from Steam API.")
            return

        # Process the server list from the API response
        new_server_list_for_json = []
        for server in api_data['response']['servers']:
            if 'addr' in server:
                try:
                    ip, port_str = server['addr'].split(':')
                    port = int(port_str)
                    new_server_list_for_json.append({'ip': ip, 'port': port})
                except (ValueError, IndexError):
                    print(f"[API WARN] Could not parse address: {server.get('addr')}")

        # Write the new list to the JSON file
        with open(SERVERS_FILENAME, 'w') as f:
            json.dump(new_server_list_for_json, f, indent=2)
            
        print(f"Successfully fetched and saved {len(new_server_list_for_json)} servers to '{SERVERS_FILENAME}'.")
        LAST_API_FETCH_TIME = time.time()

    except requests.exceptions.RequestException as e:
        print(f"[API ERROR] Could not connect to Steam API: {e}")
    except json.JSONDecodeError:
        print("[API ERROR] Failed to decode JSON response from Steam API.")
    except IOError as e:
        print(f"[FILE ERROR] Could not write to '{SERVERS_FILENAME}': {e}")


def check_and_reload_servers():
    """Checks if the JSON file has been modified and reloads the in-memory list."""
    global LAST_MODIFIED_TIME, GAME_SERVERS
    try:
        if not os.path.exists(SERVERS_FILENAME):
            return # Do nothing if file doesn't exist yet

        mtime = os.path.getmtime(SERVERS_FILENAME)
        if mtime != LAST_MODIFIED_TIME:
            print(f"Detected change in '{SERVERS_FILENAME}'. Reloading server list...")
            with open(SERVERS_FILENAME, 'r') as f:
                data = json.load(f)
            
            # Re-populate the internal list
            new_list = []
            for entry in data:
                if 'ip' in entry and 'port' in entry:
                    new_list.append((str(entry['ip']), int(entry['port'])))
            
            GAME_SERVERS = new_list
            LAST_MODIFIED_TIME = mtime
            print(f"Reload complete. Now serving {len(GAME_SERVERS)} servers.")
            
    except (IOError, json.JSONDecodeError, KeyError) as e:
        print(f"[ERROR] Failed to reload '{SERVERS_FILENAME}': {e}. Using old list.")


def build_server_list_payload(seed_ip='0.0.0.0', seed_port=0):
    """Builds the binary payload for a page of servers, starting after the seed."""
    servers_to_send = []
    
    if seed_ip == '0.0.0.0' and seed_port == 0:
        servers_to_send = GAME_SERVERS
    else:
        try:
            seed_index = GAME_SERVERS.index((seed_ip, seed_port))
            servers_to_send = GAME_SERVERS[seed_index + 1:]
        except ValueError:
            servers_to_send = [] # Seed not found, send empty list
            
    payload = bytearray()
    for ip_str, port_int in servers_to_send:
        ip_bytes = socket.inet_aton(ip_str)
        port_bytes = struct.pack('>H', port_int)
        payload.extend(ip_bytes)
        payload.extend(port_bytes)

    payload.extend(socket.inet_aton(TERMINATOR_IP))
    payload.extend(struct.pack('>H', TERMINATOR_PORT))
    
    return bytes(payload)

def run_server():
    """Starts the UDP master server and the API fetching loop."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind((MASTER_HOST, MASTER_PORT))
        print(f"Master server listening on {MASTER_HOST}:{MASTER_PORT}...")
    except OSError as e:
        print(f"[FATAL] Could not bind to port {MASTER_PORT}: {e}")
        sys.exit(1)

    print(f"Will refresh server list from Steam API every {API_REFRESH_INTERVAL} seconds.")
    print("\nReady to receive queries. Press Ctrl+C to stop.")

    try:
        while True:
            # API fetching and file reloading
            current_time = time.time()
            if current_time - LAST_API_FETCH_TIME > API_REFRESH_INTERVAL:
                fetch_and_update_servers()
            
            check_and_reload_servers()

            # UDP packet handling logic
            sock.settimeout(1.0) # Use a timeout to keep the loop non-blocking
            try:
                data, client_address = sock.recvfrom(1024)
            except socket.timeout:
                continue # No packet, loop back to check timers

            print(f"\nReceived {len(data)} bytes from {client_address[0]}:{client_address[1]}")

            if data.startswith(QUERY_HEADER):
                seed_ip, seed_port = '0.0.0.0', 0
                try:
                    null_index = data.index(b'\x00', 2)
                    seed_str = data[2:null_index].decode('ascii')
                    if ':' in seed_str:
                        seed_ip, seed_port_str = seed_str.split(':')
                        seed_port = int(seed_port_str)
                except (ValueError, IndexError):
                    pass
                
                print(f"  - Received valid query with seed: {seed_ip}:{seed_port}")
                response_payload = build_server_list_payload(seed_ip, seed_port)
                full_response = RESPONSE_HEADER + response_payload
                
                print(f"  - Sending response ({len(full_response)} bytes).")
                sock.sendto(full_response, client_address)

    except KeyboardInterrupt:
        print("\nShutting down server.")
    finally:
        sock.close()
        print("Server socket closed.")

if __name__ == '__main__':
    run_server()
