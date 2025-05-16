import time
import threading

import pdb_attach
pdb_attach.listen(5678)


class WorkerThread(threading.Thread):
    def __init__(self, name):
        super().__init__()
        self.name = name
    
    def func_a(self, arg1, arg2):
        self.func_b(arg1, arg2)

    def func_b(self, arg1, arg2):
        print(f"Hello from WorkerThread - {arg1}, {arg2}")

    def run(self):
        i = 0
        while True:
            self.func_a( self.name, i )
            time.sleep(5)
            i += 1

def main():
    workers = []
    for i in range(3):
        t = WorkerThread( f"worker-{i}" )
        t.start()
        workers.append(t)

    i = 0
    while True:
        print(f"Hello from MainThread - {i}")
        time.sleep(1)
        i += 1


main()
