import socket

HOST = '10.200.99.2'
PORT = 49200
TIMEOUT = 10

def test_reqpos():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(TIMEOUT)
        print(f"Connecting to {HOST}:{PORT} ...")
        s.connect((HOST, PORT))
        print("Connected.")

        s.sendall(b'REQSTAT\r')
        response = s.recv(4096).decode('ascii')
        print(f"Response:\n{response}")

if __name__ == '__main__':
    test_reqpos()
