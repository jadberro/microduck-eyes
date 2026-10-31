import time

from microduck_eyes.control.udp import UdpControl, send


def test_udp_round_trip():
    got = []
    ctl = UdpControl(got.append, port=0)
    port = ctl.sock.getsockname()[1]
    send({"cmd": "blink"}, port=port)
    send({"cmd": "look", "x": 1}, port=port)
    deadline = time.time() + 1.0
    n = 0
    while n < 2 and time.time() < deadline:
        n += ctl.poll()
        time.sleep(0.005)
    ctl.close()
    assert [m["cmd"] for m in got] == ["blink", "look"]


def test_udp_ignores_garbage():
    got = []
    ctl = UdpControl(got.append, port=0)
    port = ctl.sock.getsockname()[1]
    ctl.sock.sendto(b"not json\n[1,2]\n", ("127.0.0.1", port))
    time.sleep(0.02)
    ctl.poll()
    ctl.close()
    assert got == [] and ctl.errors == 1
