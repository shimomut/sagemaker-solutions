# Debugging Tools

This directory contains tools for debugging and profiling distributed training jobs.

## dump_pyspy.py

Dumps stack traces from Python processes using py-spy.

**Usage:**
```bash
python3 dump_pyspy.py [-p <pattern>] [-o <output_dir>] [--py-spy <path_to_py_spy>]
```

**Options:**
- `-p, --process-pattern`: Regex pattern to match process command line (default: `python`)
- `-o, --output-dir`: Directory to save dump files (default: current directory)
- `--py-spy`: Path to py-spy executable (default: py-spy)

**Features:**
- Automatically finds all processes matching the specified pattern
- Captures stack traces using py-spy
- Includes process and parent process information
- Captures top output for CPU usage analysis
- Names output files with hostname and PID for easy identification

**Examples:**
```bash
# Default: find all Python processes
python3 dump_pyspy.py -o /tmp/dumps

# Specific script: find myscript.py processes
python3 dump_pyspy.py -p "myscript\.py" -o /tmp/dumps

# Match train.py processes
python3 dump_pyspy.py -p "python.*train\.py" -o /tmp/dumps

# Match any Python process in a specific directory
python3 dump_pyspy.py -p "/home/user/.*\.py" -o /tmp/dumps
```

**Output files:**
- `{hostname}_{pid}.py-spy`: Stack trace for each process
- `{hostname}_top.txt`: CPU usage snapshot

## multi_node_dump_pyspy.py

Runs `dump_pyspy.py` on multiple cluster nodes in parallel.

**Usage:**
```bash
python3 multi_node_dump_pyspy.py --nodes <node_spec> [-p <pattern>] [--max-workers N] [--script-dir DIR]
```

**Options:**
- `--nodes`: Node specification (e.g., "ip-10-1-1-[1-10],ip-10-1-2-5")
- `-p, --process-pattern`: Regex pattern to match process command line (default: `python`)
- `--max-workers`: Maximum parallel SSH connections (default: 10)
- `--script-dir`: Directory containing dump_pyspy.py (default: script directory)

**Features:**
- Parallel execution across multiple nodes using threading
- Automatic timestamp-based output directory naming
- Progress tracking and summary reporting
- Thread-safe output for clean logs

**Examples:**
```bash
# Default: dump all Python processes on specified nodes
python3 multi_node_dump_pyspy.py --nodes "ip-10-1-4-218,ip-10-1-11-173" --max-workers 20

# Specific script: dump myscript.py processes
python3 multi_node_dump_pyspy.py --nodes "ip-10-1-4-[1-10]" -p "myscript\.py"

# Custom pattern: dump train.py processes
python3 multi_node_dump_pyspy.py --nodes "ip-10-1-4-[1-10]" -p "python.*train\.py"

# Match any Python process in a specific directory
python3 multi_node_dump_pyspy.py --nodes "ip-10-1-4-[1-10]" -p "/home/user/.*\.py"
```

This will create a directory like `pyspy-20260102-143025` with dumps from all nodes.
