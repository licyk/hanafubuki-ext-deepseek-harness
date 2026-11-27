import { createApp } from "vue";
import * as frame from "hanafubuki-frame";
import { frameUi } from "hanafubuki-ui";
import { currentPage } from "./pages";
import ConfigurationPage from "./screens/ConfigurationPage.vue";
import NodePage from "./screens/NodePage.vue";
import VersionsPage from "./screens/VersionsPage.vue";
import "./style.css";

// The extension has three management sections, each its own frame: dsh's
// versions, the Node.js it runs, and its configuration. They share this
// bundle (one build, one copy of the strings and the store), and the page
// the host opened picks which one mounts. Adding a fourth is a view, a
// `PAGES` entry and a `ui` entry in the manifest.
const VIEWS = { versions: VersionsPage, node: NodePage, configuration: ConfigurationPage };

// The bundle's components take their labels and Browse from the frame client.
createApp(VIEWS[currentPage()]).use(frameUi(frame)).mount("#app");
