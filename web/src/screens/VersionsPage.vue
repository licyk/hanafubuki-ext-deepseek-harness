<script setup lang="ts">
// The instance's dsh versions: its own management section, so the rail lists
// it beside Node.js and the configuration.
import { ref } from "vue";

import App from "../App.vue";
import VersionsView from "../views/VersionsView.vue";

const showPrereleases = ref(true);
</script>

<template>
  <App>
    <VersionsView v-model:show-prereleases="showPrereleases" />
  </App>
</template>
