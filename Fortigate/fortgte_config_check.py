mport paramiko
import csv
import time
import re
import subprocess

def generate_token():
    result = subprocess.run(['stoken', 'tokencode'], capture_output=True, text=True)
    if result.returncode != 0:
        raise Exception("Failed to generate token")
    return result.stdout.strip()

def vdom_exists(ssh, vdom):
    command = 'config global\nshow system vdom-property\nend'
    stdin, stdout, stderr = ssh.exec_command(command)
    output = wait_for_command_completion(stdout)
   
    vdom_list = []
    for line in output.splitlines():
        if line.strip().startswith('edit'):
            vdom_name = line.split('"')[1]
            vdom_list.append(vdom_name)

    return vdom in vdom_list

def wait_for_command_completion(stdout):
    output = ''
    while not stdout.channel.exit_status_ready():
        if stdout.channel.recv_ready():
            output += stdout.channel.recv(1024).decode('utf-8')
        time.sleep(0.1)
    return output

def clean_output(output):
    lines = output.splitlines()
    cleaned_lines = []
    for line in lines:
        if "current vt=" in line:
            continue
        cleaned_line = re.sub(r'^\S+\(\S+\)#\s*', '', line)
        if re.match(r'^\S+ #$', cleaned_line):
            continue
        cleaned_lines.append(cleaned_line)
    return '\n'.join(cleaned_lines)

def execute_global_commands(ssh, commands):
    print("Executing global commands")
    full_output = []
    stdin, stdout, stderr = ssh.exec_command('config global')
    wait_for_command_completion(stdout)
   
    for command in commands:
        complete_command = f'{command.strip()}\n'
        stdin, stdout, stderr = ssh.exec_command(complete_command)
        output = wait_for_command_completion(stdout)
        output = clean_output(output)
        full_output.append((command.strip(), output))
   
    stdin, stdout, stderr = ssh.exec_command('end')
    wait_for_command_completion(stdout)
   
    return full_output

def execute_vdom_commands(ssh, vdom, commands):
    print(f"Entering VDOM context: {vdom}")
    stdin, stdout, stderr = ssh.exec_command(f'config vdom\nedit {vdom}')
    wait_for_command_completion(stdout)
   
    full_output = []
    for command in commands:
        complete_command = f'{command.strip()}\n'
        stdin, stdout, stderr = ssh.exec_command(complete_command)
        output = wait_for_command_completion(stdout)
        output = clean_output(output)
        full_output.append((command.strip(), output))
   
    stdin, stdout, stderr = ssh.exec_command('end')
    wait_for_command_completion(stdout)
   
    return full_output

def get_fortigate_output(host, username, password, vdom):
    print(f"Connecting to host: {host}")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, username=username, password=password)
   
    if vdom.lower() != 'global' and not vdom_exists(ssh, vdom):
        ssh.close()
        print(f"VDOM {vdom} does not exist on {host}")
        return [(f"VDOM {vdom} does not exist on {host}", "")]

    commands_file = 'global_command.txt' if vdom.lower() == 'global' else 'vdom_command.txt'
    with open(commands_file, 'r') as file:
        commands = file.readlines()

    if vdom.lower() == 'global':
        full_output = execute_global_commands(ssh, commands)
    else:
        full_output = execute_vdom_commands(ssh, vdom, commands)

    ssh.close()
    return full_output

def write_to_csv(data, csv_file):
    with open(csv_file, 'w', newline='') as csvfile:
        csvwriter = csv.writer(csvfile)
        csvwriter.writerow(['Hostname', 'VDOM', 'Command', 'Output'])
        for row in data:
            for command_output in row[2]:
                if len(command_output) >= 2:
                    csvwriter.writerow([row[0], row[1], command_output[0], command_output[1]])
                else:
                    csvwriter.writerow([row[0], row[1], command_output[0], ""])

def read_input_csv(input_csv):
    with open(input_csv, newline='') as csvfile:
        csvreader = csv.reader(csvfile)
        next(csvreader)  # Skip the header
        devices = [row for row in csvreader]
    return devices

def main():
    username = 'your_username'
    input_csv = 'input.csv'
    output_csv = 'output.csv'

    devices = read_input_csv(input_csv)
    all_data = []

    for host, vdom in devices:
        token = generate_token()
        password = token
        print(f"Working on host: {host}, VDOM: {vdom}")
        output = get_fortigate_output(host, username, password, vdom)
        all_data.append([host, vdom, output])
        print("Waiting 1 minute before connecting to the next device...")
        time.sleep(60)  # Wait for 1 minute

    write_to_csv(all_data, output_csv)
    print(f'Data written to {output_csv}')

if __name__ == '__main__':
    main()