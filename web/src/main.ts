import { createApp } from "vue";
import * as frame from "hanafubuki-frame";
import { frameUi } from "hanafubuki-ui";
import App from "./App.vue";
import "./style.css";

// The bundle's components take their labels and Browse from the frame client.
createApp(App).use(frameUi(frame)).mount("#app");
