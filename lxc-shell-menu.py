#!/usr/bin/env python3 

import argparse
import os
import readline
import shutil
import subprocess
import sys
import signal
import termios
import tty

original_terminal_settings = None

def capture_terminal_settings():
    global original_terminal_settings
    original_terminal_settings = termios.tcgetattr(sys.stdin)

def restore_terminal_settings_and_exit(*args):
    global original_terminal_settings
    if original_terminal_settings:
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, original_terminal_settings)
    sys.exit(1)

def install():
    script_path = os.path.abspath(__file__)
    target_path = "/usr/local/bin/lxc-shell-menu"
    try:
        subprocess.run(["cp", script_path, target_path], check=True)
        subprocess.run(["chmod", "755", target_path], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error: {e}")
        return
    
    print(f"Copied script to {target_path}")

    bashrc_path = os.path.expanduser("~/.bashrc")
    command = "lxc-shell-menu --bashrc"
    with open(bashrc_path, "r") as bashrc:
        if command not in bashrc.read():
            with open(bashrc_path, "a") as bashrc_append:
                bashrc_append.write(f"\n{command}\n")
            print(f"Added '{command}' to {bashrc_path}")
        else:
            print(f"'{command}' already exists in {bashrc_path}")

def show_list():
    try:
        result = subprocess.run(["lxc-ls"], capture_output=True, text=True, check=True)
        containers = result.stdout.split()
    except Exception as e:
        print(f"Error fetching container list: {e}")
        return

    containers.insert(0, "host")

    def completer(text, state):
        options = [c for c in containers if c.lower().startswith(text.lower())]
        if state < len(options):
            return options[state]
        return None

    readline.set_completer(completer)
    readline.parse_and_bind("tab: complete")

    print("Choose container to start:")
    terminal_width = shutil.get_terminal_size().columns
    col_width = max(len(c) for c in containers) + 2
    cols = max(1, terminal_width // col_width)
    for i, container in enumerate(containers, 1):
        print(f"{container:<{col_width}}", end="")
        if i % cols == 0:
            print()
    if len(containers) % cols != 0:
        print()

    choice = input()
    if choice == "host":
        sys.exit(0)
    elif choice in containers:
        try:
            subprocess.run(["lxc-start", choice], check=True)
        except subprocess.CalledProcessError as e:
            sys.exit(e.returncode)
        try:
            print(f"Attaching to container '{choice}'. Press Ctrl+D or type exit to leave.")
            subprocess.run(["lxc-attach", "-n", choice], check=True)
        except subprocess.CalledProcessError as e:
            sys.exit(e.returncode)
    else:
        print(f"Invalid choice: {choice}")

def main():
    capture_terminal_settings()
    signal.signal(signal.SIGINT, restore_terminal_settings_and_exit)

    parser = argparse.ArgumentParser(description="lxc-shell-menu")
    parser.add_argument("--install", action="store_true", help="Run installation process")
    parser.add_argument("--show-list", action="store_true", help="Display a list")
    parser.add_argument("--bashrc", action="store_true", help="Executed from .bashrc")

    args = parser.parse_args()

    if not any(vars(args).values()):
        parser.print_help()
        return
    
    if os.geteuid() != 0:
        try:
            subprocess.run(["sudo", sys.executable] + sys.argv, check=True)
        except subprocess.CalledProcessError as e:
            sys.exit(e.returncode)
        return

    if args.install:
        install()
    if args.show_list:
        show_list()
    if args.bashrc:
        show_list()

if __name__ == "__main__":
    main()