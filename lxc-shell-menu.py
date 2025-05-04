#!/usr/bin/env python3 

import argparse
import os
import readline
import shutil
import subprocess
import sys
import signal
import termios

# Configs
display_container_status = True

original_terminal_settings = None

def capture_terminal_settings():
    global original_terminal_settings
    original_terminal_settings = termios.tcgetattr(sys.stdin)

def restore_terminal_settings_and_exit(*args):
    global original_terminal_settings
    if original_terminal_settings:
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, original_terminal_settings)
    print()
    sys.exit(1)

def install():
    if os.geteuid() != 0:
        try:
            subprocess.run(
                ["sudo", sys.executable] + sys.argv, 
                check=True
            )
        except subprocess.CalledProcessError as e:
            sys.exit(e.returncode)
        return

    target_path = "/usr/local/bin/lxc-shell-menu"

    try:
        subprocess.run(
            ["cp", os.path.abspath(__file__), target_path], 
            check=True
        )
        subprocess.run(
            ["chmod", "755", target_path], 
            check=True
        )
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

    sudoers_path = f"/etc/sudoers.d/lxc-shell-menu"
    sudoers_rule = f"{os.getlogin()} ALL=(ALL) NOPASSWD: {target_path} --bashrc\n"

    try:
        with open(sudoers_path, "w") as sudoers_file:
            sudoers_file.write(sudoers_rule)
        print(f"Added sudoers rule to {sudoers_path}")
    except Exception as e:
        print(f"Error adding sudoers rule: {e}")

def parse_mount_config(line):
    parts = line.split()
    if len(parts) >= 5:
        host_path = parts[2].rstrip('/')
        mount_target = parts[3].rstrip('/')
        host_cwd = os.getcwd().rstrip('/')

        if host_cwd.startswith(host_path):
            rel = os.path.relpath(host_cwd, host_path)
            mount_point = '/' + os.path.basename(mount_target)
            container_path = os.path.join(mount_point, rel)
            return container_path
    return None

def display_containers_in_grid(container_names):
    if display_container_status:
        container_names_with_status = container_names.copy()
        for i, container in enumerate(container_names):
            if i == 0:
                continue
            try:
                result = subprocess.run(
                    ["lxc-info", "-n", container], 
                    capture_output=True, 
                    text=True, 
                    check=True
                )
                if "RUNNING" in result.stdout:
                    container_names_with_status[i] = f"{container_names[i]} ✓"
                else:
                    container_names_with_status[i] = f"{container_names[i]} ✘"
            except subprocess.CalledProcessError as e:
                pass

    try: term_width = os.get_terminal_size().columns
    except OSError: term_width = 80

    max_len = max(len(c) for c in container_names) + 5
    num_columns = max(1, term_width // max_len)
    num_rows = (len(container_names) + num_columns - 1) // num_columns

    for row in range(num_rows):
        row_items = []
        for col in range(num_columns):
            index = row + col * num_rows
            if index < len(container_names):
                if display_container_status:
                    item = container_names_with_status[index].ljust(max_len)
                    item = item.replace("✓", "\033[92m●\033[0m").replace("✘", "\033[91m●\033[0m")
                else:
                    item = container_names[index].ljust(max_len)
                row_items.append(item)
        print(''.join(row_items))

def container_interface():
    if os.geteuid() != 0:
        subprocess.run(
            ["sudo"] + sys.argv
        )
        sys.exit(0)

    try:
        result = subprocess.run(
            ["lxc-ls"], 
            capture_output=True, 
            text=True, 
            check=True
        )
        container_names = result.stdout.split()
    except Exception as e:
        print(f"Error fetching container list: {e}")
        return

    container_names.insert(0, "host")

    def completer(text, state):
        options = [c for c in container_names if c.lower().startswith(text.lower())]
        if state < len(options):
            return options[state]
        return None

    readline.set_completer(completer)
    readline.parse_and_bind("tab: complete")

    print("Choose container to start:")
    display_containers_in_grid(container_names)

    while True:
        container_name = input("> ").strip()
        if container_name == "host":
            sys.exit(0)
        elif container_name in container_names:
            break
        else:
            print(f"Invalid choice: {container_name}. Please choose from the list above.")

    try:
        subprocess.run(
            ["lxc-start", container_name], 
            check=True,
            stderr=subprocess.DEVNULL
        )
    except subprocess.CalledProcessError as e:
        sys.exit(e.returncode)

    host_path = None
    destination_path = None
    config_path = f"/var/lib/lxc/{container_name}/config"

    try:
        with open(config_path, "r") as config_file:
            for line in config_file:
                if line.startswith("lxc.mount.entry"):
                    destination_path = parse_mount_config(line)
    except FileNotFoundError:
        print(f"Config file not found: {config_path}")
        return
    except Exception as e:
        print(f"Error: {e}")

    if destination_path is None:
        print(
             "To persist your current working directory in the container, add the correct configuration to container's config file.\n"
            f"The configuration file is located at {config_path}\n"
             "Example:\n"
            f"lxc.mount.entry = /home/{os.getlogin()}/ mnt/ none bind,create=dir 0 0\n"
        )

    print(f"Attaching to container '{container_name}'. Press Ctrl+D or type exit to leave.")
    shell = "/bin/bash"
    if destination_path is None:
        subprocess.run(
            ["lxc-attach", "-n", container_name, "--", shell]
        )
    else:
        subprocess.run(
            ["lxc-attach", "-n", container_name, "--", shell, "-c", f"cd {destination_path} && {shell}"]
        )

def main():
    capture_terminal_settings()
    signal.signal(signal.SIGINT, restore_terminal_settings_and_exit)

    parser = argparse.ArgumentParser(
        description="A convenient interactive menu for starting LXC containers",
        usage="%(prog)s [--install | --menu]",
    )
    parser.add_argument(
        "--install", 
        action="store_true", 
        help="install the script to /usr/local/bin and configure auto-start"
    )
    parser.add_argument(
        "--menu", 
        action="store_true", 
        help="launch the interactive container selection menu"
    )
    parser.add_argument(
        "--bashrc", 
        action="store_true", 
        help="alias for --menu, executed from .bashrc"
    )

    args = parser.parse_args()

    if not any(vars(args).values()):
        parser.print_help()
        return

    if args.install:
        install()

    if args.menu:
        container_interface()

    if args.bashrc:
        container_interface()

if __name__ == "__main__":
    main()