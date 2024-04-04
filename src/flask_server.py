"""
Server that runs in the docker container

This server should call the blackbox processes and receive requests from the audio client
NOTE: technically, the "client" application "serves" raw audio to this application


Technical:
audio is posted to ip/audio_in
video should be available at ip/video/id

A Vue site should be the only thing that has direct communication with this application
it should not be available outside of the docker container (except MAYBE the video stream)
although for now it is available because the Vue site doesnt exist and I needed to test
the audio input

might want to open a second port for the audio if we are *slow* because of the constant audio requests
- this is not a concern at the moment

Server: Flask
"""
from flask import Flask, render_template, request, jsonify
import numpy as np


flask_app = Flask(__name__, template_folder='.')

audio_str = ""
audio_source = ""
audio_raw_max = 0
AUDIO_SAVED_CHUNKS = 5
audio_last = []
audio_max_last = audio_raw_max
# TODO: find a good way to store many past chunks (preferably both push and pop are o(1))
audio_chunk = []
all_audio = {}
@flask_app.route("/")
def main_page():
    return render_template('index.html')

@flask_app.route("/audio_source", methods = ['GET', 'POST'])
def get_audio_source():
    """
    This might end up being obsolete, but adding the header for now
    """
    global all_audio
    global audio_source
    if request.method == "POST":
        data = request.form
        if "mics" in data:
            all_audio = data["mics"]
        if "source" in data:
            audio_source = data["source"]
        return jsonify({"source": audio_source, "mics": all_audio})
    else:
        return jsonify({"source": audio_source, "mics": all_audio})


@flask_app.route("/audio_in", methods=['GET', 'POST'])
def audio_in():
    """
    HTTP implementation to send audio data to server
    Keeping it for compatability
    How the local application to the server.
    It is also called by the frontend UI to test the dynamic site,
    although this will might change in the future.
    When compared to performance of minimal udp packets, there was only a difference of 0.01 seconds of latency (0.22 vs 0.21)


    TODO: change how setting changes are communicated back to the client
    client is expecting 'settings' key that contains any updated settings
    """
    # TODO: change this later, it is just for testing and the MVP apparently
    global audio_str
    global audio_source
    global audio_chunk
    global audio_raw_max
    global audio_last
    global audio_max_last
    global AUDIO_SAVED_CHUNKS
    if request.method == 'POST':
        data = request.json
        audio_chunk = np.array(data['data']).reshape(-1)
        rpeak = float(data['peak'])
        ravg = float(data['avg'])
        audio_raw_max = rpeak
        # NOTE: all of this computation is better done in a celery task, but since those arent set up yet,
        # doing basic analysis here
        audio_last.append(rpeak)
        if (len(audio_last) > AUDIO_SAVED_CHUNKS):
            audio_last.pop(0)

        audio_max_last = max(audio_last)
        bars = "#" * int(50 * ravg)
        mbars = "-" * int((50 * rpeak) - (50 * ravg))
        audio_str = bars + mbars

        response = {"bars": audio_str}
        if "source" in data:
            if data["source"] != audio_source:
                print(f"{audio_source} != {data['source']}")
                response["source"] = audio_source
        response = jsonify(response)
        return response
    else:
        response = jsonify({"bars": audio_str, "peak": audio_max_last, "source": audio_source})
        # TODO: the actual CORS policy
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response
    

@flask_app.route("/fft_audio", methods=['GET'])
def fft_audio():
    """
    Do a FFT and return the data
    TODO: shift array to only capture useful frequency range
    """
    num_motors = 8
    if len(audio_chunk) > 0:
        #return audio_chunk.tolist()
        fft = np.fft.fft(audio_chunk).real
        chunk_size = fft.size / num_motors
        avg_chunks = np.abs(np.average(fft.reshape(-1, int(chunk_size)), axis=1))
        normalized_chunks = avg_chunks # / avg_chunks.size
        return jsonify({"frequencies": normalized_chunks.tolist()})
    else:
        return jsonify({'frequencies': [0, 0, 0, 0, 0, 0, 0, 0]})


@flask_app.route("/output", methods=['GET'])
def output_page():
    """
    Display just the threejs scene.
    This is how other programs get our output
    """
    #TODO: tell the vue app to build a MPA
    return render_template("outputscene/outputscene.html")

@flask_app.route("/output/stream", methods=['GET'])
def output_stream():
    """
    Serve next frame of video

    Plan:
    use the server-side rendering aspects of threejs
    that most likely means we will have a node application constantly rendering the scene that output images to a folder
    this method then grabs the most recent one and sends it to the client

    this would *only* be useful when running the server on a second device because it would introduce more overhead
    that and, why send it back and forth if you are just rendering locally anyways
    """
    return jsonify({'error': 'not implemented, look at creativity-optional wiki'})
    

if __name__ == "__main__":
    flask_app.run()