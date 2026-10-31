"""
Роль каждого сервера ансамбля.
Запуск (из корня HW4): python src/zk_status.py
"""
import socket


SERVERS = [
    ("server1", 2181),
    ("server2", 2182),
    ("server3", 2183),
]


def ask_four_letter_command(port, command):
    with socket.create_connection(("localhost", port), timeout=2) as connection:
        connection.sendall(command.encode("ascii"))
        connection.settimeout(2)
        return connection.recv(65536).decode("utf-8")


def describe(port):
    try:
        reply = ask_four_letter_command(port, "srvr")
    except OSError:
        return "not running (connection refused)"

    for line in reply.splitlines():
        if line.startswith("Mode:"):
            return line
    return "not serving requests (no quorum)"


def main():
    for name, port in SERVERS:
        print(f"{name} localhost:{port}  {describe(port)}")


if __name__ == "__main__":
    main()
