### How to switch on/off Python profiler on-demand in your training code

#### Overview

In Python's standard library, there is a useful profiling module `cProfile`. You can use this module to troubleshoot your application's performance problems.

But you don't want to enable this performance profiler all the time, because profiler itself has some performance overhead.

This demo showcases how to profile a single frame of training loop on-demand, by checking the existence of specific empty file.


#### How to run the demo

1. Open two terminals

1. In terminal A, run the demo application.

    ``` bash
    python3 single_frame_profile.py
    ```

1. In terminal B, trigger profiling by creating a file.

    ``` bash
    touch ./trigger.txt
    ```

1. Check output

    ```
    {'arg1': 123, 'arg2': {'aaa': 456}}
    {'arg1': 123, 'arg2': {'aaa': 456}}
            21 function calls in 5.000 seconds

    Ordered by: standard name

    ncalls  tottime  percall  cumtime  percall filename:lineno(function)
            1    0.000    0.000    5.000    5.000 <string>:1(<module>)
            1    0.000    0.000    0.000    0.000 __init__.py:183(dumps)
            1    0.000    0.000    0.000    0.000 __init__.py:299(loads)
            1    0.000    0.000    0.000    0.000 decoder.py:332(decode)
            1    0.000    0.000    0.000    0.000 decoder.py:343(raw_decode)
            1    0.000    0.000    0.000    0.000 encoder.py:183(encode)
            1    0.000    0.000    0.000    0.000 encoder.py:205(iterencode)
            1    0.000    0.000    5.000    5.000 single_frame_profile.py:33(single_frame)
            1    0.000    0.000    5.000    5.000 {built-in method builtins.exec}
            3    0.000    0.000    0.000    0.000 {built-in method builtins.isinstance}
            1    0.000    0.000    0.000    0.000 {built-in method builtins.len}
            1    5.000    5.000    5.000    5.000 {built-in method time.sleep}
            1    0.000    0.000    0.000    0.000 {method 'disable' of '_lsprof.Profiler' objects}
            2    0.000    0.000    0.000    0.000 {method 'end' of 're.Match' objects}
            1    0.000    0.000    0.000    0.000 {method 'join' of 'str' objects}
            2    0.000    0.000    0.000    0.000 {method 'match' of 're.Pattern' objects}
            1    0.000    0.000    0.000    0.000 {method 'startswith' of 'str' objects}


    {'arg1': 123, 'arg2': {'aaa': 456}}
    {'arg1': 123, 'arg2': {'aaa': 456}}
    {'arg1': 123, 'arg2': {'aaa': 456}}
    {'arg1': 123, 'arg2': {'aaa': 456}}    
    ```