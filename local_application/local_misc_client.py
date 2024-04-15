"""
Creativity Optional
local audio client that runs a given command and sends the output to the server

please submit bugs to https://github.com/BCaven/creativity-optional/issues

this is supposed to be a background task started with cron/equivalent
settings should be changed either through the command line arguments or through
the creativity-optional frontend

Tasks:
[TODO] support for commands passed as command line arguments
[TODO] multiple commands running at different times/refresh rates
[TODO] remove all the audio functions (the base for this was `local_audio_client.py`)


"""
import sys
import requests
import logging
logging.basicConfig(format='[%(levelname)s] %(message)s')
logging.getLogger().setLevel(logging.DEBUG)



def usage(return_val: int):
    print("""
please write this...

""")
    sys.exit(return_val)


def main():
    """
    main function, wrangles commands and sends their outputs
    """
    DOCKER_IP="http://127.0.0.1:8000/"
    args = sys.argv[1:]
    while args:
        next = args.pop(0)
        if next == '-ip':
            try:
                DOCKER_IP = args.pop(0)
            except:
                logging.error("failed to parse command line arguments -ip used but no ip given")
                usage(1)
        else:
            usage(1)


if __name__ == "__main__":
    main()