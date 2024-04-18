"""
Creativity Optional
local audio client that runs a given command and sends the output to the server

please submit bugs to https://github.com/BCaven/creativity-optional/issues

this is supposed to be a background task started with cron/equivalent
different options/inputs should be handled through an input file or command line arguments
this should not care about server responses (except for server not responding)

Tasks:
[DONE] support for commands passed as command line arguments
[DONE] multiple commands running at different times/refresh rates
[DONE] remove all the audio functions (the base for this was `local_audio_client.py`)
[TODO] support for reading commands from a file
[TODO] support for reading commands from stdin
[TODO] support for different output types (int, str, float, etc)
[TODO] multicast server IP detection
[TODO] make sure we are asking to keep the connection alive


Passing in commands:
Reading commands from a file
One command per line
[KEY] [SLEEP_PERIOD] [COMMAND]

Passing commands as arguments
-c [KEY] [SLEEP_PERIOD] [COMMAND] --close
breaks when an argument is '--close'

Passing commands via stdin
[KEY] [SLEEP_PERIOD] [COMMAND]

Handling different types:
Ideally we would be able to tell the server the type of the incoming data and have it process accordingly.
We can go one of two routes with this:
    Route 1: the server expects integer values between 0 and 100 and throws an error at anything else
        In this route it is the user's job to write a script that converts their output to a int range (0-100)
    
    Route 2: server comes prebuilt with several methods of interpreting values and the user can pick which one to use
        Now it is our job to write conversions for "often used" types (int, str, float, list)
    
    Route 1 is easier and I feel like it will end up being the default anyways when adding custom commands
    Going with route 1 for now
"""
import asyncio
import sys
import requests
import subprocess
import logging
import shlex
assert sys.version_info >= (3, 5)

logging.basicConfig(format='[%(levelname)s] %(message)s')
logging.getLogger().setLevel(logging.DEBUG)

running = True
session = requests.Session()
session.verify = True
# TODO: quality of life: multicast server detection
# http://0.0.0.0:8000/general_in
DOCKER_IP="http://127.0.0.1:8000/"


def usage(return_val: int):
    print("""
please write this...

""")
    sys.exit(return_val)

def process_command(command) -> str:
    """
    Run the given command and return the output

    The program will split the command for you if necessary

    TODO: shlex!
    TODO: test on windows
    """
    assert type(command) in [list, str], f"invalid command type {type(command)} only str and list are allowed"
    logging.debug(f"command before processing: {command}")
    processed_command = command
    if type(command) == str:
        processed_command = shlex.split(command) 
    logging.debug(f"command after processing: {processed_command}")
    result = subprocess.run(processed_command, stdout=subprocess.PIPE)
    return result.stdout.decode('utf-8')


async def command_thread(key, sleep_period, command,  command_type) -> bool:
    """
    Thread that processes a given command.

    Calls the command, sends it to the server, and sleeps for the specified time

    Returns a boolean - true if the process was killed normally, false if the process ended
    prematurely (e.g. if the server did not respond)
    """
    global running
    while running:
        result = process_command(command)
        jresult = {
            key: result,
            'type': command_type
        }
        try:
            response = session.post(DOCKER_IP + 'general_in', json=jresult)
        except requests.exceptions.ConnectionError:
            logging.warning("The server did not respond, exiting...")
            running = False
            return False
        await asyncio.sleep(sleep_period)
    return True



async def main():
    """
    main function, wrangles commands and sends their outputs
    """
    global DOCKER_IP
    args = sys.argv[1:]
    commands = dict()
    reading_command = False
    current_key = ""
    current_command = []
    current_sleep_period = 0
    while args:
        next = args.pop(0)
        if reading_command:
            if next == '--close':
                reading_command = False
                commands[current_key] = (current_sleep_period, 'int', current_command)
            else:
                current_command.append(next)
        elif next == '-ip':
            try:
                DOCKER_IP = args.pop(0)
            except:
                logging.error("failed to parse command line arguments -ip used but no ip given")
                usage(1)
        elif next == '-c':
            try:
                current_key = args.pop(0)
                current_sleep_period = int(args.pop(0))
                current_command = []
                reading_command = True
            except:
                usage(1)
        else:
            usage(1)
    async with asyncio.TaskGroup() as tg:
        tasks = []
        for key in commands:
            sleep_period, output_type, command = commands[key]
            tasks.append(command_thread(key, sleep_period, command, output_type))
        for task in tasks:
            tg.create_task(task)



if __name__ == "__main__":
    asyncio.run(main())