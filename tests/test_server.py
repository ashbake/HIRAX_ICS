import re
import socket

TCP_IP = '127.0.0.1'
TCP_PORT = 5005
BUFFER_SIZE = 1024

REQPOS_RESPONSE = (
    b'UTC = 164 20:27:20.8, LST = 06:08:32.4\n'
    b'RA = 06:06:48.03, DEC = +33:21:27.6, HA = W00:00:00.0\n'
    b'air mass =  1.000\x00'
)

REQSTAT_RESPONSE = (
    b'UTC = 164 22:19:37.5\n'
    b'telescope ID = 200, focus = 48.65 mm, tube length = 00.00 mm\n'
    b'offset RA =       0.0 arcsec, DEC =       0.4 arcsec\n'
    b'rate RA =       0.0 arcsec/hr, DEC =       0.0 arcsec/hr\n'
    b'Cass ring angle = 143.66\x00'
)

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind((TCP_IP, TCP_PORT))
s.listen(1)
print(f'Listening on {TCP_IP}:{TCP_PORT}')

while True:
    conn, addr = s.accept()
    print('Connection address:', addr)

    while True:
        data = conn.recv(BUFFER_SIZE)
        if not data:
            break
        cmd = data.decode('ascii').strip()
        print(f'Received: {cmd!r}')

        if cmd == 'REQPOS':
            conn.sendall(REQPOS_RESPONSE)
        elif cmd == 'REQSTAT':
            conn.sendall(REQSTAT_RESPONSE)
        elif cmd == 'NAME':
            conn.sendall(b'NAME = Crab Nebula\n')
        elif re.match(r'^PT\s+-?\d+\.?\d*\s+-?\d+\.?\d*$', cmd):
            conn.sendall(b'0')
        else:
            print(f'Unknown command: {cmd!r}')

    conn.close()
    print('Client disconnected, waiting for next connection...')