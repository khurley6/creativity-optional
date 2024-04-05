"""
Creativity Optional
local audio client based on soundcard

when this is complete, move it back over to local_audio_client.py

tested on windows and linux, unreliable on mac

please submit bugs to https://github.com/BCaven/creativity-optional/issues

this is supposed to be a background task started with cron/equivalent
settings should be changed either through the command line arguments or through
the creativity-optional frontend

architecture:
two process types
Producer:
    restarts when settings change
    appends audio chunks to chunk_buffer
Consumer:
    sends latest chunk to the server and changes settings as needed

there will only ever be one producer, but there will be several consumers

IDEA: it might be fun for the future to support multiple input devices (think mic + loopback) but that is an issue for later

NOTE: since the pool_size is capped, there might be latency when audio chunks get 
recorded faster than they are sent to the server


NOTE: development on this has been halted because the latency happens before the sound data ever reaches this program, so
this is not required because it has no major performance gains

keeping it in the testing folder in case it is needed in the future
"""
import soundcard as sc
import numpy as np
import sys
import logging
import requests
import multiprocessing as mp
from multiprocessing import Process, Manager


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
        r = requests.post(ip + "audio_source", json=settings)
        r.json()
    except requests.ConnectionError:
        logging.error("server did not respond... is it running?")
        return False
    return True


def record_audio(mic, chunk_buffer) -> bool:
    """
    send audio from the current settings until the server responds with new settings
    the actual number of frames in each chunk is the block size
    higher blocksize = easier on the system
    higher blocksizes inherently have latency because they have to 
    record the data before sending it
    but smaller block sizes eventually have infinite latency because
    the system cannot process the audio fast enough

    this function is called continuously by a handler
    """
    data = np.abs(mic.record(numframes=None))
    if chunk_buffer.qsize() > 50:
        logging.warn(f"buffer is behind! {chunk_buffer.qsize()}\nlatency: {mic.latency}")
    chunk_buffer.put(data)
    # see if there is a bug check we can do here
    # I am pretty sure soundcard fails silently if there is no mic input detected (it just returns an empty array)
    if mic.latency > 1:
        logging.warn(f"latency! {mic.latency}")
    return True
    
def audio_handler(chunk_buffer, settings, setting_change, running) -> bool:
    """
    Handler for record_audio
    restarts when settings changed
    quits when told to stop running
    """
    while running.value == 1:
        chosen_mic = sc.get_microphone(settings['source'], include_loopback=settings['loopback'])
        with chosen_mic.recorder(samplerate=settings['samplerate'], blocksize=settings['blocksize']) as mic:
            while not setting_change:
                if not record_audio(mic, chunk_buffer):
                    return False
                if running.value != 1:
                    return True
    return True


def send_audio(chunk, ip, settings, setting_change) -> bool:
    """
    Send audio chunk to the server and process the response
    """
    avg = np.average(np.abs(chunk))
    peak = np.max(np.abs(chunk))
    payload = {
        "avg": float(avg),
        "peak": float(peak),
        "data": chunk.tolist(),
    }
    try:
        r = requests.post(ip + "audio_in", json=payload)
    except requests.ConnectionError:
        logging.warn("server did not respond")
        return False
    response = r.json()
    
    if "settings" in response:
        # change all of the modified settings and return
        for item in response['settings']:
            if item in settings:
                settings[item] = response['settings'][item]
                with setting_change.get_lock():
                    setting_change.value = 1
            else:
                logging.warn(f"trying to update a setting that does not exist\nunable to find key: {item}")
        logging.info("restarting with new settings")
        # send the new settings back to the server
        if not send_settings(ip, settings):
            return False
    
    return True

def worker(chunk_buffer, ip, settings, setting_change, running):
    """
    wait for another audio chunk before calling send_audio
    """
    while running.value == 1:
        chunk = chunk_buffer.get()
        r = send_audio(chunk, ip, settings, setting_change)
        # if the server does not respond we want to stop the worker
        if not r:
            with running.get_lock():
                running.value = 0
            break


def main():
    """
    main function, wrangles send_audio and send_settings
    """
    # BUG: fuzzy search grabs loopback devices when given the name of the actual device (non-loopback)
    DOCKER_IP="http://127.0.0.1:8000/"
    pool_size = 2
    # record audio appends chunks to this buffer, send audio pops them and sends them to the server

    settings = {
        'loopback': False,
        'blocksize': 2048,
        'samplerate': 48000,
        'mics': {m.id: m.name for m in sc.all_microphones(include_loopback=False)},
        'source': sc.default_microphone().id
    }
    args = sys.argv[1:]
    while args:
        next = args.pop(0)
        if next == '-ip':
            try:
                DOCKER_IP = args.pop(0)
            except:
                logging.error("failed to parse command line arguments -ip used but no ip given")
                usage(1)
        elif next == '--loopback':
            settings['loopback'] = True
        elif next == '-b' or next == '--blocksize':
            try:
                settings['blocksize'] = int(args.pop(0))
            except:
                logging.error("failed to parse command line arguments - bad blocksize")
                usage(1)
        elif next == '--samplerate':
            try:
                settings['samplerate'] = int(args.pop(0))
            except:
                logging.error("failed to parse command line arguments - bad samplerate")
                usage(1)
        elif next == '-s' or next == '--source':
            try:
                settings['source'] = args.pop(0)
            except:
                logging.error("failed to parse command line arguments - bad source")
                usage(1)
        elif next == '-p' or next == '--poolsize':
            try:
                pool_size = int(args.pop(0))
            except:
                logging.error("failed to parse command line arguments - bad poolsize")
                usage(1)
        else:
            usage(1)


    if not send_settings(DOCKER_IP, settings):
        sys.exit(0)
    
    # idea: continuously send audio until one of them returns false
    # then update the settings and restart
    
    with Manager() as manager:
        shared_settings = manager.dict(settings)
        running = manager.Value('i', 1)
        setting_change = manager.Value('i', 0)
        print(running)
        print(running.value == 1)
        chunk_buffer = manager.Queue()
        workers = [
            mp.Process(target=worker, args=(chunk_buffer, DOCKER_IP, settings, setting_change, running,)) for _ in range(pool_size)
        ]
        producer = mp.Process(target=audio_handler, args=(chunk_buffer, settings, setting_change, running,))
        for w in workers:
            w.start()
        producer.start()
        for w in workers:
            w.join()
        producer.join()
    

if __name__ == "__main__":
    main()