from execute import execute

commands = ["iostat -w"]

def collect_system_data():
    res = []
    for cmd in commands:
        res.append(execute(cmd))
    return res
