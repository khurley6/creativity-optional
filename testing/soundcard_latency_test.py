"""
Results of this test:
the latency of this (continuous recording, no data processing or http post request)
is basically the same as the latency of any of the other clients.

based on this I am going to stop developing multithreaded/async clients and just use the synchronous client.
"""

import soundcard as sc
import numpy as np
loopback = False

settings = {
    'loopback': loopback,
    'blocksize': 2048,
    'samplerate': 48000,
    'mics': {m.id: m.name for m in sc.all_microphones(include_loopback=loopback)},
    'source': sc.default_microphone().id
}
    
chosen_mic = sc.get_microphone(settings['source'], include_loopback=settings['loopback'])
with chosen_mic.recorder(samplerate=settings['samplerate'], blocksize=settings['blocksize']) as mic:
    while True:
        data = np.abs(mic.record(numframes=None))
        avg = np.average(np.abs(data))
        peak = np.max(np.abs(data))
        print(f"latency: {mic.latency}")