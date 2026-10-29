import { createApp, defineAsyncComponent, h } from "vue";
import { createPinia } from "pinia";
import { ElConfigProvider } from "element-plus/es/components/config-provider/index.mjs";
import "element-plus/es/components/config-provider/style/css";
import zhCn from "element-plus/es/locale/lang/zh-cn";
import App from "./App.vue";
import "./style.css";
import "element-plus/es/components/message/style/css";
import { registerElementPlusComponents } from "./elementPlus";

// This explicit preview entry uses isolated in-memory data and never authenticates or calls business APIs.
const params = new URLSearchParams(window.location.search);
const Root = params.get('mode') === 'live' ? defineAsyncComponent(() => import('./views/live/LiveApp.vue'))
  : params.get('mode') === 'customer' ? defineAsyncComponent(() => import('./views/live/CustomerChat.vue'))
  : ['workbench', 'app'].includes(params.get('preview') || '')
  ? defineAsyncComponent(() => import('./views/preview/PreviewApp.vue'))
  : App;
const app = createApp({
  render: () => h(ElConfigProvider, { locale: zhCn }, () => h(Root)),
});

app.use(createPinia());
registerElementPlusComponents(app);
app.mount("#app");
