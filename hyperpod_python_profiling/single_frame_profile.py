import os
import time
import json
import cProfile

class SingleFrameProfilingDemo:

    def __init__(self, trigger_filepath):
        self.trigger_filepath = trigger_filepath
        self.profile = False


    def run_loop(self):

        frame_count = 0
        while True:

            # Check if trigger file exists, enable profiling mode if exists
            if os.path.exists(self.trigger_filepath):
                os.unlink(self.trigger_filepath)
                self.profile = True

            arg1 = 123
            arg2 = { "aaa": 456 }

            # Run a single frame profiling if profiling mode is enabled,
            # otherwise, run a single frame normally.
            if self.profile:
                self.profile = False
                cProfile.runctx( "result = self.single_frame(arg1,arg2)", globals(), locals() )
            else:
                result = self.single_frame(arg1,arg2)

            print(f"frame {frame_count}: {result}")

            frame_count += 1

        
    def single_frame(self, arg1, arg2):
        d = { "arg1": arg1, "arg2": arg2 }
        s = json.dumps(d)
        d = json.loads(s)
        time.sleep(5)
        return d


def main():
    demo = SingleFrameProfilingDemo("./trigger.txt")
    demo.run_loop()


if __name__ == '__main__':
    main()
