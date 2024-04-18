<script setup>
// TODO: fix formatting bug where threejs canvas does not take up the entire screen

import { onMounted, onBeforeUnmount, ref } from "vue";
import light_example_scene from "../src/components/light_example_scene.vue";

// look into service workers as a way to automate the process of receiving data from the server
const server_route = "0.0.0.0:8000";
let sound_bar = ref("");
let sound_volume = ref(0);
let fft = ref([]);
const timer = ref();

async function updateSoundData() {
  // get the new sound data
  const response = await fetch("http://" + server_route + "/audio_in");
  //console.log(response.json());
  let r = await response.json();
  sound_volume.value = r.peak;
  //console.log(sound_bar.value);
}
async function updateFFTData() {
  const response = await fetch("http://" + server_route + "/fft_audio");
  let r = await response.json();
  fft.value = r['frequencies'];
}

function countDownFunc () {
  updateSoundData();
  updateFFTData();
}

// Instantiate
onMounted(() => {
  // could probably make this refresh faster given a better computer - I am testing this on my garbage laptop
  timer.value = setInterval(() => {
    countDownFunc();
  }, 60); // ~15 times every second
});

// Clean up
onBeforeUnmount(() => {
  timer.value = null;
});

</script>

<template>
  <main>
    <light_example_scene :volume="sound_volume"/>
  </main>
</template>

<style scoped>
header {
  line-height: 1.5;
}
</style>
