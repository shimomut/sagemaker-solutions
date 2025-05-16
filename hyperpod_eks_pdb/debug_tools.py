import sys
import threading
import traceback


def print_table(headers, rows, min_width=12):
    # Calculate column widths
    col_widths = [max(min_width, len(str(header))) for header in headers]
    for row in rows:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(cell)))
    
    # Create horizontal separator
    separator = '+' + '+'.join('-' * (width + 2) for width in col_widths) + '+'
    
    # Print header
    print(separator)
    header_str = '|'
    for header, width in zip(headers, col_widths):
        header_str += f' {str(header):<{width}} |'
    print(header_str)
    print(separator)
    
    # Print rows
    for row in rows:
        row_str = '|'
        for cell, width in zip(row, col_widths):
            row_str += f' {str(cell):<{width}} |'
        print(row_str)
    
    # Print bottom separator
    print(separator)


def threads():
    threads = threading.enumerate()

    headers = ["ID", "Name", "IsAlive"]
    rows = []
    for t in threads:
        rows.append([
            t.ident,
            t.name,
            t.is_alive(),
        ])
    
    print_table(headers, rows)


def stack(tid):
    frame = sys._current_frames().get(tid)
    if frame:
        print("\nCall stack:")

        stack = traceback.extract_stack(frame)
        for filename, lineno, name, line in stack:
            print(f"  File '{filename}', line {lineno}, in {name}")
            if line:
                print(f"    {line}")
