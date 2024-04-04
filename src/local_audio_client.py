"""
Creativity Optional
local audio client based on soundcard

tested on windows and linux, unreliable on mac

please submit bugs to https://github.com/BCaven/creativity-optional/issues

this is supposed to be a background task started with cron/equivalent
settings should be changed either through the command line arguments or through
the creativity-optional frontend

TODO: finish transition to functions
TODO: look into async httpx
TODO: command line arguments
"""
import soundcard as sc
import numpy as np
import sys
import requests
import logging



def usage(return_val):
    print("""
please write this...

""")
    sys.exit(return_val)


def send_settings(ip, settings) -> bool:
    """
    Send all settings
    Runs when the application starts and if it is requested by the server

    Returns if the function ran successfully
    """
    # send the list
    # for now we do not care about the response
    try:
        _ = requests.post(ip + "audio_source", json=settings)
    except requests.exceptions.ConnectionError:
        logging.warning("The server did not respond, is it running?")
        return False
    return True


def send_audio(chosen_mic, ip, settings) -> bool:
    """
    Continuously send audio from the current settings until the server responds with new settings
    the actual number of frames in each chunk is the block size
    higher blocksize = easier on the system
    higher blocksizes inherently have latency because they have to 
    record the data before sending it
    but smaller block sizes eventually have infinite latency because
    the system cannot process the audio fast enough

    this function should block until the server turns off or sends new settings
    """
    logging.info(f"listening to {chosen_mic.id} : {chosen_mic.name}")
    with chosen_mic.recorder(samplerate=settings['samplerate'], blocksize=settings['blocksize']) as mic:
            while True:
                data = np.abs(mic.record(numframes=None))
                avg = np.average(np.abs(data))
                peak = np.max(np.abs(data))

                payload = {
                    "avg": float(avg),
                    "peak": float(peak),
                    "data": data.tolist(),
                }
                try:
                    response = requests.post(ip + "audio_in", json=payload).json()
                except requests.exceptions.ConnectionError:
                    logging.error("server did not respond, exiting...")
                    return False
                
                if "settings" in response:
                    # change all of the modified settings and return
                    for item in response['settings']:
                        if item in settings:
                            settings[item] = response['settings'][item]
                        else:
                            logging.warn(f"trying to update a setting that does not exist\nunable to find key: {item}")
                    logging.info("restarting with new settings")
                    return True

def main():
    """
    main function, wrangles send_audio and send_settings
    """
    # BUG: fuzzy search grabs loopback devices when given the name of the actual device (non-loopback)
    DOCKER_IP="http://127.0.0.1:8000/"
    loopback = False

    settings = {
        'loopback': loopback,
        'blocksize': 2048,
        'samplerate': 48000,
        'mics': {m.id: m.name for m in sc.all_microphones(include_loopback=loopback)},
        'source': sc.default_microphone().id
    }
    args = sys.argv[1:]
    if len(args) > 0:
        logging.warn("support for command line arguments has not been implemented yet")
    
    if not send_settings(DOCKER_IP, settings):
        return
    
    while True:
        chosen_mic = sc.get_microphone(settings['source'], include_loopback=settings['loopback'])
        # send_audio should block
        if not send_audio(chosen_mic, DOCKER_IP, settings):
            return
        
        # if send_audio stopped and returned true then the settings got updated
        # send the new settings back to the server to update the frontend
        if not send_settings(DOCKER_IP, settings):
            return


if __name__ == "__main__":
    main()