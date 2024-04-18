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
two threads
Producer:
    restarts when settings change
    appends audio chunks to chunk_buffer
Consumer:
    sends latest chunk to the server and changes settings as needed

NOTE: since the pool_size is capped, there might be latency when audio chunks get 
recorded faster than they are sent to the server

TODO: test producer and consumer
NOTE: when in the same async runtime this performs the same/worse than the syncronous version
because the record_audio loop only awaits on the queue - everything else is syncronous which
completely defeats the purpose.
Going to try putting the workers in a different thread to see if that can remove some of the latency.

I have a sneaking suspicion that the latency is largely caused by things outside of this program.
"""
import soundcard as sc
import numpy as np
import sys
import httpx
import logging
import asyncio
import requests
# record audio appends chunks to this buffer, send audio pops them and sends them to the server
setting_change = False
loopback = False

settings = {
    'loopback': loopback,
    'blocksize': 2048,
    'samplerate': 48000,
    'mics': {m.id: m.name for m in sc.all_microphones(include_loopback=loopback)},
    'source': sc.default_microphone().id
}

def usage(return_val):
    print("""
please write this...

""")
    sys.exit(return_val)

async def stop(client, ret_val):
    await client.aclose()
    sys.exit(ret_val)


async def send_settings(ip, client) -> bool:
    """
    Send all settings
    Runs when the application starts and if it is requested by the server

    Returns if the function ran successfully
    """
    # send the list
    # for now we do not care about the response
    global settings
    try:
        r = await client.post(ip + "audio_source", json=settings)
        #r = requests.post(ip + "audio_source", json=settings)
        r.json()
    except httpx.RemoteProtocolError:
    #except requests.ConnectionError:
        logging.error("server did not respond... is it running?")
        return False
    return True


async def record_audio(mic, chunk_buffer) -> bool:
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
    await chunk_buffer.put(data)
    # see if there is a bug check we can do here
    # I am pretty sure soundcard fails silently if there is no mic input detected (it just returns an empty array)
    if mic.latency > 1:
        logging.warn(f"latency! {mic.latency}")
    return True
    
async def audio_handler(chunk_buffer) -> bool:
    """
    Handler for record_audio
    restarts when settings changed
    """
    global settings
    global setting_change
    chosen_mic = sc.get_microphone(settings['source'], include_loopback=settings['loopback'])
    with chosen_mic.recorder(samplerate=settings['samplerate'], blocksize=settings['blocksize']) as mic:
        while not setting_change:
            if not await record_audio(mic, chunk_buffer):
                return False
    return True


async def send_audio(chunk, client, ip) -> bool:
    """
    Send audio chunk to the server and process the response
    """
    global settings
    global setting_change

    avg = np.average(np.abs(chunk))
    peak = np.max(np.abs(chunk))
    payload = {
        "avg": float(avg),
        "peak": float(peak),
        "data": chunk.tolist(),
    }
    try:
        #r = requests.post(ip + "audio_in", json=payload)
        r = await client.post(ip + "audio_in", json=payload)
    except httpx.RemoteProtocolError:
        logging.warn("server did not respond")
        return False
    response = r.json()
    
    if "settings" in response:
        # change all of the modified settings and return
        for item in response['settings']:
            if item in settings:
                settings[item] = response['settings'][item]
                setting_change = True
            else:
                logging.warn(f"trying to update a setting that does not exist\nunable to find key: {item}")
        logging.info("restarting with new settings")
        # send the new settings back to the server
        if not await send_settings(ip, client):
            return False
    
    return True

async def worker(chunk_buffer, client, ip):
    """
    wait for another audio chunk before calling send_audio
    """
    while True:
        chunk = await chunk_buffer.get()
        r = await send_audio(chunk, client, ip)
        # if the server does not respond we want to stop the worker
        if not r:
            break


async def main():
    """
    main function, wrangles send_audio and send_settings
    """
    # BUG: fuzzy search grabs loopback devices when given the name of the actual device (non-loopback)
    DOCKER_IP="http://127.0.0.1:8000/"
    pool_size = 150
    
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

    # set up client
    client = httpx.AsyncClient()

    if not await send_settings(DOCKER_IP, client):
        await stop(client, 1)
    
    # idea: continuously send audio until one of them returns false
    # then update the settings and restart
    chunk_buffer = asyncio.Queue(100)
    workers = [
        asyncio.create_task(worker(chunk_buffer, client, DOCKER_IP)) for _ in range(pool_size)
    ]
    # all of these should stop when the server stops responding
    await asyncio.gather(
        audio_handler(chunk_buffer),
        *workers
    )
    
    await client.aclose()


if __name__ == "__main__":
    asyncio.run(main())